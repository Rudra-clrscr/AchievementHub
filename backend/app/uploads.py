"""Novelty feature: students/faculty may submit any file, of any size or
type (.png, .pdf, .docx, ...) -- there is no upload limit. Instead of
storing raw bytes in Postgres (which would bloat the database), every
upload is compressed to fit the *storage* need and pushed to Supabase
Storage; only the resulting public URL is ever persisted in a row.

Images are always re-encoded to WebP (near-universal browser support,
smaller than PNG/JPEG at equivalent visual quality) and capped to a
max dimension. PDFs are recompressed in place via PyMuPDF's stream
deflate + unused-object garbage collection, which is lossless for the
document content. Any other file type (docx, pptx, zip, ...) has no
safe generic compression available without risking corruption, so it
is stored unmodified -- the "no restriction" guarantee still holds
because it never touches the database, only object storage.

Object storage (rather than the backend's own disk) is used specifically
so uploads survive a free-tier host's container being recycled between
requests -- a local-disk version of this was tried first and would have
silently lost every file the first time the process restarted.
"""

import io
import uuid
from pathlib import Path

import fitz  # PyMuPDF
import httpx
from fastapi import HTTPException, UploadFile, status
from PIL import Image

from app.config import settings

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"}
PDF_EXTENSION = ".pdf"

MAX_IMAGE_DIMENSION = 2000
WEBP_QUALITY = 78

CONTENT_TYPES = {
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}


class CompressedUpload:
    def __init__(self, url: str, original_size: int, stored_size: int, content_type: str):
        self.url = url
        self.original_size = original_size
        self.stored_size = stored_size
        self.content_type = content_type


def _compress_image(raw: bytes) -> tuple[bytes, str]:
    image = Image.open(io.BytesIO(raw))
    image.load()

    if image.width > MAX_IMAGE_DIMENSION or image.height > MAX_IMAGE_DIMENSION:
        image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.LANCZOS)

    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "A" in image.mode else "RGB")

    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=WEBP_QUALITY, method=6)
    return buffer.getvalue(), ".webp"


def _compress_pdf(raw: bytes) -> tuple[bytes, str]:
    doc = fitz.open(stream=raw, filetype="pdf")
    try:
        return doc.tobytes(garbage=4, deflate=True, deflate_images=True, deflate_fonts=True), ".pdf"
    finally:
        doc.close()


def _upload_to_supabase(data: bytes, path: str, content_type: str) -> str:
    upload_url = f"{settings.supabase_url}/storage/v1/object/{settings.supabase_storage_bucket}/{path}"
    response = httpx.post(
        upload_url,
        content=data,
        headers={
            "Authorization": f"Bearer {settings.supabase_service_key}",
            "apikey": settings.supabase_service_key,
            "Content-Type": content_type,
        },
        timeout=60.0,
    )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Storage upload failed: {response.text}",
        )
    return f"{settings.supabase_url}/storage/v1/object/public/{settings.supabase_storage_bucket}/{path}"


def compress_and_store(upload: UploadFile, subfolder: str) -> CompressedUpload:
    raw = upload.file.read()
    original_size = len(raw)
    ext = Path(upload.filename or "").suffix.lower()
    original_content_type = upload.content_type or "application/octet-stream"

    try:
        if ext in IMAGE_EXTENSIONS:
            data, ext = _compress_image(raw)
        elif ext == PDF_EXTENSION:
            data, ext = _compress_pdf(raw)
        else:
            data = raw
    except Exception:
        # Corrupt/unrecognized payload despite the extension -- fall back to
        # storing the original bytes rather than failing the submission.
        data, ext = raw, ext or ""

    content_type = CONTENT_TYPES.get(ext, original_content_type)
    path = f"{subfolder}/{uuid.uuid4().hex}{ext}"
    url = _upload_to_supabase(data, path, content_type)

    return CompressedUpload(
        url=url,
        original_size=original_size,
        stored_size=len(data),
        content_type=content_type,
    )
