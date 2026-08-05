"""Novelty feature: students/faculty may submit any file, of any size or
type (.png, .pdf, .docx, ...) -- there is no upload limit. Instead of
storing raw bytes in Postgres (which would bloat the database), every
upload is compressed to fit the *storage* need and pushed to Supabase
Storage; only the resulting public URL is ever persisted in a row.

Images are always re-encoded to WebP (near-universal browser support,
smaller than PNG/JPEG at equivalent visual quality) and capped to a
max dimension. PDFs get the same treatment applied to every embedded
image (most real submissions are phone-scanned notes/certificates,
which are just a handful of full-page JPEGs wrapped in a PDF shell --
lossless stream deflate alone does ~nothing for those, since the JPEGs
are already compressed) plus a final lossless stream deflate + unused-
object garbage collection pass. Word/PowerPoint/Excel files (.docx/
.pptx/.xlsx) are themselves just a zip of XML parts plus embedded
media -- same idea applies: only the media/*.{png,jpg} entries get
recompressed in place, every XML part and relationship stays byte-
identical, so the file still opens normally, just smaller. Any other
file type (zip, mp4, ...) has no safe generic compression available
without risking corruption, so it is stored unmodified -- the "no
restriction" guarantee still holds because it never touches the
database, only object storage.

Object storage (rather than the backend's own disk) is used specifically
so uploads survive a free-tier host's container being recycled between
requests -- a local-disk version of this was tried first and would have
silently lost every file the first time the process restarted.

Files at or under COMPRESS_SIZE_THRESHOLD skip compression entirely and
are stored as-is. Re-encoding is real CPU work, and the free-tier host
this runs on has 0.1 vCPU -- spending that on a certificate that's
already 200KB has no size benefit and only adds latency.
"""

import io
import logging
import uuid
import zipfile
from pathlib import Path

import fitz  # PyMuPDF
import httpx
from fastapi import HTTPException, UploadFile, status
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"}
PDF_EXTENSION = ".pdf"
OOXML_EXTENSIONS = {".docx", ".pptx", ".xlsx"}
OOXML_MEDIA_FORMATS = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG"}

MAX_IMAGE_DIMENSION = 2000
IMAGE_QUALITY = 78
COMPRESS_SIZE_THRESHOLD = 5 * 1024 * 1024
EMBEDDED_IMAGE_SKIP_THRESHOLD = 100 * 1024
# BILINEAR over LANCZOS: this runs on a 0.1 vCPU free-tier host, where a
# multi-image PDF/pptx can spend a second-plus per image just resampling.
# BILINEAR is markedly faster and, for downscaling scanned photos/screenshots,
# not distinguishable from LANCZOS at the JPEG/WebP quality already in use.
RESIZE_FILTER = Image.BILINEAR

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
        image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), RESIZE_FILTER)

    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "A" in image.mode else "RGB")

    buffer = io.BytesIO()
    # method=4 (Pillow's own default) trades a little compression ratio for
    # meaningfully less encode time versus method=6's max-effort search --
    # worth it on a 0.1 vCPU host where every second is felt by the user.
    image.save(buffer, format="WEBP", quality=IMAGE_QUALITY, method=4)
    return buffer.getvalue(), ".webp"


def _recompress_pdf_images(doc: fitz.Document) -> None:
    """Downsample/re-encode every embedded image in place. This is the part
    that actually matters for real submissions -- a scanned-notes PDF is
    just full-page JPEGs behind a thin PDF wrapper, and those pages are
    what the size budget is spent on, not the document structure. Small
    embedded images (icons, logos, watermarks) are skipped -- on a
    0.1 vCPU host, the decode/resample/encode cost isn't worth it for
    something that isn't driving the file's size in the first place."""
    seen_xrefs: set[int] = set()
    for page in doc:
        for image_info in page.get_images(full=True):
            xref = image_info[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            try:
                extracted = doc.extract_image(xref)
                if len(extracted["image"]) <= EMBEDDED_IMAGE_SKIP_THRESHOLD:
                    continue
                image = Image.open(io.BytesIO(extracted["image"]))
                image.load()

                if image.width > MAX_IMAGE_DIMENSION or image.height > MAX_IMAGE_DIMENSION:
                    image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), RESIZE_FILTER)
                if image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")

                buffer = io.BytesIO()
                image.save(buffer, format="JPEG", quality=IMAGE_QUALITY)
                page.replace_image(xref, stream=buffer.getvalue())
            except Exception:
                logger.warning("Skipping recompression of PDF image xref=%s", xref, exc_info=True)


def _compress_pdf(raw: bytes) -> tuple[bytes, str]:
    doc = fitz.open(stream=raw, filetype="pdf")
    try:
        _recompress_pdf_images(doc)
        return doc.tobytes(garbage=4, deflate=True, deflate_images=True, deflate_fonts=True), ".pdf"
    finally:
        doc.close()


def _compress_ooxml(raw: bytes, ext: str) -> tuple[bytes, str]:
    """Word/PowerPoint/Excel files are a zip of XML parts plus embedded
    media. Only media/*.{png,jpg,jpeg} entries are touched, re-saved in
    their *original* format (never converted) so the filename extension
    inside the zip stays truthful -- Office resolves each media part's
    codec from that extension via [Content_Types].xml, so silently
    swapping e.g. a .png entry for JPEG bytes would render as a broken
    image even though the zip itself stays well-formed. Every other
    entry (document.xml, relationships, styles, ...) is copied through
    byte-for-byte."""
    src = zipfile.ZipFile(io.BytesIO(raw))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            content = src.read(item.filename)
            media_format = OOXML_MEDIA_FORMATS.get(Path(item.filename).suffix.lower())
            if media_format and "media" in Path(item.filename).parts and len(content) > EMBEDDED_IMAGE_SKIP_THRESHOLD:
                try:
                    image = Image.open(io.BytesIO(content))
                    image.load()
                    if image.width > MAX_IMAGE_DIMENSION or image.height > MAX_IMAGE_DIMENSION:
                        image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), RESIZE_FILTER)
                    if media_format == "JPEG" and image.mode not in ("RGB", "L"):
                        image = image.convert("RGB")
                    out = io.BytesIO()
                    image.save(out, format=media_format, quality=IMAGE_QUALITY, optimize=True)
                    if len(out.getvalue()) < len(content):
                        content = out.getvalue()
                except Exception:
                    logger.warning("Skipping recompression of OOXML media %r", item.filename, exc_info=True)
            dst.writestr(item, content)
    return buffer.getvalue(), ext


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
        if original_size <= COMPRESS_SIZE_THRESHOLD:
            data = raw
        elif ext in IMAGE_EXTENSIONS:
            data, ext = _compress_image(raw)
        elif ext == PDF_EXTENSION:
            data, ext = _compress_pdf(raw)
        elif ext in OOXML_EXTENSIONS:
            data, ext = _compress_ooxml(raw, ext)
        else:
            data = raw
    except Exception:
        # Corrupt/unrecognized payload despite the extension -- fall back to
        # storing the original bytes rather than failing the submission.
        logger.warning("Compression failed for upload %r, storing original bytes", upload.filename, exc_info=True)
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
