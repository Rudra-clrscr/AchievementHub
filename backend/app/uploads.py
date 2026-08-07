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

Every image (standalone, PDF-embedded, or OOXML media) is first run
through a cheap classifier (see _classify_image) that buckets it as a
"photo", a "graphic", or near-bilevel "text" using a downsampled
grayscale histogram, then routed to the codec/quality suited to that
content -- one flat q=78 lossy pass is fine for a photo but visibly
rings around scanned text edges and wastes bits on flat screenshot
backgrounds. This is the same idea as Adobe's Mixed Raster Content
split (separate handling for text vs. background vs. photo layers),
scoped down to per-image routing rather than per-pixel layer
decomposition -- the latter would need numpy/opencv-grade image
segmentation, which is not worth the CPU on a 0.1 vCPU host.

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
import time
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
IMAGE_QUALITY = 90
EMBEDDED_IMAGE_SKIP_THRESHOLD = 100 * 1024
# BILINEAR over LANCZOS: this runs on a 0.1 vCPU free-tier host, where a
# multi-image PDF/pptx can spend a second-plus per image just resampling.
# BILINEAR is markedly faster and, for downscaling scanned photos/screenshots,
# not distinguishable from LANCZOS at the JPEG/WebP quality already in use.
RESIZE_FILTER = Image.BILINEAR
# WebP's method controls encoder search effort, separately from quality
# (the visual-fidelity target) -- higher method searches harder for the same
# quality, it doesn't raise it. Measured on a 2000x1500 photo: method=4 took
# ~800ms and produced 755KB; method=1 took ~200ms (4x faster) and produced
# 745KB -- i.e. no size/quality cost here, method=4's extra search just
# wasn't paying for itself on this content. Same story for lossless (~75ms
# either way, identical output) -- avoid method=0 there specifically, it
# skips a compression pass entirely and produces dramatically larger files.
WEBP_METHOD = 1

# Whole-file size target. Files at or under this are already within budget
# and skip compression entirely -- re-encoding is real CPU work on a 0.1
# vCPU host, not worth spending on a file that doesn't need it. Files above
# it are compressed down towards this ceiling; there's no separate "floor"
# enforcement (nothing pads a file back up to 250KB) since the quality
# floors below already stop us well short of over-compressing that far in
# the dominant real case (a handful of full-page scans per submission).
TARGET_MAX_FILE_SIZE = 500 * 1024
COMPRESS_SIZE_THRESHOLD = TARGET_MAX_FILE_SIZE
# For multi-image PDFs/OOXML files, TARGET_MAX_FILE_SIZE is split evenly
# across embedded images. Below this per-image floor, quality wins over
# hitting the whole-file target exactly -- a 20-page scanned PDF divided
# into a ~25KB-per-page budget would need to crush every page to mush to
# hit 500KB total, which damages legibility for no good reason.
MIN_PER_IMAGE_BUDGET = 60 * 1024

# Wall-clock ceiling on total time spent recompressing embedded images in a
# single PDF/OOXML file. Per-image work is already bounded (two-attempt
# ladder below), but nothing bounds the *count* of images -- a many-page
# scanned PDF/pptx can take long enough on a 0.1 vCPU host that the request
# gateway kills the connection before a response ever comes back, which the
# browser then reports as a CORS failure (no response at all means no CORS
# header either, even though CORS itself is configured fine). Once the
# budget is spent, any remaining images are left at their original encoding
# -- still a valid, complete file, just not optimized as far -- rather than
# risking an unbounded-length request.
RECOMPRESS_TIME_BUDGET_SECONDS = 20.0

# Cheap element-type classification (see _classify_image) buckets each image
# as "photo", "graphic" (flat-color line art/screenshots), or near-bilevel
# "text" (plain scans), then routes it through a two-attempt quality/size
# ladder: attempt 0 uses a near-max-fidelity profile for that content type;
# if the result still exceeds its size budget, attempt 1 retries once more
# with a tighter profile and returns whatever that produces. Exactly two
# attempts, never an open-ended search -- this runs inline in the HTTP
# request on a 0.1 vCPU host, so bounded, predictable latency matters more
# than shaving the last few KB off an outlier image.
#
# Attempt 0 is deliberately high-quality rather than "aggressively small":
# the target is a 250-500KB *ceiling*, not a size to chase downward, and
# there's no floor enforcement below it -- an image genuinely low on detail
# (a flat poster/diagram) will legitimately land under 250KB even at max
# quality, and that's correct: padding it further would mean preserving
# source-JPEG noise, upscaling, or picking a deliberately worse encoder pass,
# none of which improve what a reviewer actually sees.
DIMENSION_LADDER = (MAX_IMAGE_DIMENSION, 1700)
# quality per element type, indexed by attempt number. For "text", these are
# only the *lossy fallback* qualities -- attempt 0 first tries lossless
# encoding (see TEXT_LOSSLESS_MAX_PIXELS) and only falls through to the
# quality number here if the image is too large for lossless to stay cheap.
QUALITY_LADDER = {
    "photo": (IMAGE_QUALITY, 72),
    "graphic": (95, 78),
    "text": (95, 88),
}
DOMINANT_BIN_RADIUS = 12
GRAPHIC_DOMINANT_FRACTION = 0.55
TEXT_DOMINANT_FRACTION = 0.85
# Pixel-count cap on the *working* (already downsized) image before we'll
# attempt lossless encoding for "text"-classified images. Lossless WebP/PNG
# is fast on genuinely near-bilevel content (little entropy to search) but
# the cost still scales with pixel count, so this bounds worst-case time on
# an oversized scan rather than trusting the classifier alone.
TEXT_LOSSLESS_MAX_PIXELS = 2_000_000

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


def _classify_image(image: Image.Image) -> str:
    """Cheap element-type heuristic modeled on Adobe's Mixed Raster Content
    split: a page/embedded image is either a "photo" (continuous tone, no
    single dominant band), a "graphic" (a flat background/UI-chrome tone
    covers most of it, but with real color content on top -- diagrams,
    screenshots, color scans), or near-bilevel "text" (a flat tone -- paper,
    typically -- covers almost all of it, e.g. an ordinary B&W scan).
    Computed on the full-resolution grayscale histogram -- deliberately
    *not* pre-downsampled: a resize blurs sharp black-on-white text into a
    wide spread of mid-grays before the histogram ever sees it, which
    washes out exactly the bimodal signal this heuristic looks for.
    Pillow's histogram() is a single fast C-level pass, so skipping the
    resize is both more accurate and cheaper (no interpolation cost)."""
    gray = image.convert("L")
    total = gray.width * gray.height
    if total == 0:
        return "photo"

    histogram = gray.histogram()
    peak = max(range(256), key=histogram.__getitem__)
    lo, hi = max(0, peak - DOMINANT_BIN_RADIUS), min(256, peak + DOMINANT_BIN_RADIUS + 1)
    dominant_fraction = sum(histogram[lo:hi]) / total

    if dominant_fraction >= TEXT_DOMINANT_FRACTION:
        return "text"
    if dominant_fraction >= GRAPHIC_DOMINANT_FRACTION:
        return "graphic"
    return "photo"


def _compress_image(raw: bytes) -> tuple[bytes, str]:
    image = Image.open(io.BytesIO(raw))
    image.load()

    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "A" in image.mode else "RGB")

    # Resize to the attempt-0 cap before classifying: this resize has to
    # happen anyway for attempt 0's encode, and classifying on it instead of
    # the full original is ~5x cheaper with no accuracy loss (2000px is
    # still far higher resolution than would blur the sharp edges the
    # classifier looks for -- unlike the small thumbnail this function used
    # to (and must not) resize down to, see _classify_image's docstring).
    if image.width > MAX_IMAGE_DIMENSION or image.height > MAX_IMAGE_DIMENSION:
        image = image.copy()
        image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), RESIZE_FILTER)
    element_type = _classify_image(image)

    data = b""
    # Two-attempt size-budget ladder: attempt 0 uses the profile tuned for
    # this element type; only if that's still over TARGET_MAX_FILE_SIZE do
    # we retry once more, tighter. See the DIMENSION_LADDER/QUALITY_LADDER
    # comment above for why this stops at two attempts rather than
    # searching for an exact fit.
    for attempt, dimension_cap in enumerate(DIMENSION_LADDER):
        working = image
        if working.width > dimension_cap or working.height > dimension_cap:
            working = working.copy()
            working.thumbnail((dimension_cap, dimension_cap), RESIZE_FILTER)

        buffer = io.BytesIO()
        if element_type == "text" and attempt == 0 and working.width * working.height <= TEXT_LOSSLESS_MAX_PIXELS:
            # Near-bilevel scan: lossless WebP -- like JBIG2's template reuse
            # for repeated glyph shapes -- shrinks this far below what lossy
            # quantization would, without the ringing that blurs small text.
            working.save(buffer, format="WEBP", lossless=True, method=WEBP_METHOD)
        else:
            working.save(buffer, format="WEBP", quality=QUALITY_LADDER[element_type][attempt], method=WEBP_METHOD)
        data = buffer.getvalue()

        if len(data) <= TARGET_MAX_FILE_SIZE or attempt == len(DIMENSION_LADDER) - 1:
            break
    return data, ".webp"


def _recompress_pdf_images(doc: fitz.Document) -> None:
    """Downsample/re-encode every embedded image in place. This is the part
    that actually matters for real submissions -- a scanned-notes PDF is
    just full-page JPEGs behind a thin PDF wrapper, and those pages are
    what the size budget is spent on, not the document structure. Small
    embedded images (icons, logos, watermarks) are skipped -- on a
    0.1 vCPU host, the decode/resample/encode cost isn't worth it for
    something that isn't driving the file's size in the first place.

    TARGET_MAX_FILE_SIZE is a *whole-file* target, so it's split evenly
    across the embedded images being recompressed (floored at
    MIN_PER_IMAGE_BUDGET -- see its definition for why)."""
    seen_xrefs: set[int] = set()
    xrefs: list[int] = []
    for page in doc:
        for image_info in page.get_images(full=True):
            xref = image_info[0]
            if xref not in seen_xrefs:
                seen_xrefs.add(xref)
                xrefs.append(xref)

    size_budget = max(TARGET_MAX_FILE_SIZE // max(len(xrefs), 1), MIN_PER_IMAGE_BUDGET)

    deadline = time.monotonic() + RECOMPRESS_TIME_BUDGET_SECONDS
    for i, xref in enumerate(xrefs):
        if time.monotonic() > deadline:
            logger.warning("PDF recompression time budget exceeded, leaving %d image(s) unrecompressed", len(xrefs) - i)
            break
        try:
            extracted = doc.extract_image(xref)
            if len(extracted["image"]) <= EMBEDDED_IMAGE_SKIP_THRESHOLD:
                continue
            image = Image.open(io.BytesIO(extracted["image"]))
            image.load()
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            # See _compress_image: resize to the attempt-0 cap before
            # classifying -- cheaper and just as accurate as classifying the
            # full-resolution extracted image.
            if image.width > MAX_IMAGE_DIMENSION or image.height > MAX_IMAGE_DIMENSION:
                image = image.copy()
                image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), RESIZE_FILTER)
            element_type = _classify_image(image)

            data = b""
            for attempt, dimension_cap in enumerate(DIMENSION_LADDER):
                working = image
                if working.width > dimension_cap or working.height > dimension_cap:
                    working = working.copy()
                    working.thumbnail((dimension_cap, dimension_cap), RESIZE_FILTER)

                buffer = io.BytesIO()
                if element_type == "text" and attempt == 0 and working.width * working.height <= TEXT_LOSSLESS_MAX_PIXELS:
                    # Lossless: PDF viewers decode PNG streams natively via
                    # replace_image, and near-bilevel scan content is cheap
                    # to encode losslessly (little entropy to search).
                    working.save(buffer, format="PNG", compress_level=6)
                else:
                    working.save(buffer, format="JPEG", quality=QUALITY_LADDER[element_type][attempt])
                data = buffer.getvalue()

                if len(data) <= size_budget or attempt == len(DIMENSION_LADDER) - 1:
                    break
            page.replace_image(xref, stream=data)
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

    def _is_eligible(item: zipfile.ZipInfo) -> bool:
        return bool(
            OOXML_MEDIA_FORMATS.get(Path(item.filename).suffix.lower())
            and "media" in Path(item.filename).parts
            and item.file_size > EMBEDDED_IMAGE_SKIP_THRESHOLD
        )

    eligible_count = sum(1 for item in src.infolist() if _is_eligible(item))
    size_budget = max(TARGET_MAX_FILE_SIZE // max(eligible_count, 1), MIN_PER_IMAGE_BUDGET)

    buffer = io.BytesIO()
    deadline = time.monotonic() + RECOMPRESS_TIME_BUDGET_SECONDS
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            content = src.read(item.filename)
            media_format = OOXML_MEDIA_FORMATS.get(Path(item.filename).suffix.lower())
            if media_format and _is_eligible(item) and time.monotonic() > deadline:
                logger.warning("OOXML recompression time budget exceeded, leaving %r unrecompressed", item.filename)
            elif media_format and _is_eligible(item):
                try:
                    image = Image.open(io.BytesIO(content))
                    image.load()
                    if media_format == "JPEG" and image.mode not in ("RGB", "L"):
                        image = image.convert("RGB")
                    # See _compress_image: resize to the attempt-0 cap before
                    # classifying -- cheaper and just as accurate.
                    if image.width > MAX_IMAGE_DIMENSION or image.height > MAX_IMAGE_DIMENSION:
                        image = image.copy()
                        image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), RESIZE_FILTER)
                    # PNG entries stay PNG -- format is fixed by the original
                    # extension (Office resolves codec from it) -- so
                    # classification only changes the JPEG quality ladder.
                    element_type = _classify_image(image) if media_format == "JPEG" else "graphic"

                    out_bytes = content
                    for attempt, dimension_cap in enumerate(DIMENSION_LADDER):
                        working = image
                        if working.width > dimension_cap or working.height > dimension_cap:
                            working = working.copy()
                            working.thumbnail((dimension_cap, dimension_cap), RESIZE_FILTER)

                        out = io.BytesIO()
                        if media_format == "JPEG":
                            working.save(out, format="JPEG", quality=QUALITY_LADDER[element_type][attempt], optimize=True)
                        else:
                            working.save(out, format="PNG", optimize=True)
                        out_bytes = out.getvalue()

                        if len(out_bytes) <= size_budget or attempt == len(DIMENSION_LADDER) - 1:
                            break

                    if len(out_bytes) < len(content):
                        content = out_bytes
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

    # Belt-and-suspenders: per-image budgets don't bound whole-file overhead
    # (PDF restructuring, zip re-deflation, etc.), so a "compressed" result
    # can still come out larger than the original -- e.g. a PDF whose images
    # were already tightly encoded, where re-encoding + xref rewriting adds
    # more than it saves. Never store something bigger than what was
    # uploaded.
    if len(data) >= original_size:
        data, ext = raw, Path(upload.filename or "").suffix.lower()

    content_type = CONTENT_TYPES.get(ext, original_content_type)
    path = f"{subfolder}/{uuid.uuid4().hex}{ext}"
    url = _upload_to_supabase(data, path, content_type)

    return CompressedUpload(
        url=url,
        original_size=original_size,
        stored_size=len(data),
        content_type=content_type,
    )
