"""The upload compression pipeline (`app/uploads.py`).

This is the most intricate code in the repo and every one of its documented
failure modes was found in production rather than in review, so the tests here
are shaped around the invariants that failure history actually produced:

* **Never store something bigger than what was uploaded.** Compression that
  backfires must not be persisted.
* **Never corrupt the container.** OOXML media parts keep their original
  format (Office resolves the codec from the entry's extension, so swapping
  PNG bytes for JPEG renders as a broken image), and every non-media part is
  copied through byte-for-byte.
* **Never fail a submission because compression failed.** A corrupt or
  mislabelled payload falls back to storing the original bytes.
* **Route by content, not by extension.** Photos go to JPEG, flat-colour
  graphics and near-bilevel scans stay on WebP.

Nothing here touches the network: `httpx.post` is replaced by a recorder, so
these tests also pin down exactly what would be sent to Supabase Storage.

The image builders are session-scoped because generating a realistic
multi-megapixel photo is the slowest thing in the suite by an order of
magnitude, and it does not change between tests.
"""

import io
import random
import zipfile

import fitz
import pytest
from fastapi import HTTPException
from PIL import Image, ImageChops, ImageDraw
from starlette.datastructures import Headers, UploadFile

from app import uploads
from app.models import EmployeeRole
from app.uploads import (
    COMPRESS_SIZE_THRESHOLD,
    EMBEDDED_IMAGE_SKIP_THRESHOLD,
    MAX_IMAGE_DIMENSION,
    TARGET_MAX_FILE_SIZE,
    _classify_image,
    _compress_image,
    _compress_ooxml,
    _compress_pdf,
    _generate_image_thumbnail,
    _generate_pdf_thumbnail,
    _upload_to_supabase,
    compress_and_store,
)

# --------------------------------------------------------------------------
# Synthetic source material
#
# Each builder targets one bucket of the classifier: a photo has no dominant
# grey band, a graphic is mostly one flat background tone with real colour on
# top, and a scan is ~90% paper. Those proportions are the whole heuristic, so
# the fixtures have to respect them to be testing anything real.
# --------------------------------------------------------------------------


def build_photo(width=2400, height=1800):
    """Continuous tone: a gradient per channel plus gaussian noise, which
    spreads the grey histogram wide enough that no band dominates."""
    ramp = Image.linear_gradient("L").resize((width, height))
    bands = [
        ImageChops.add(ramp.rotate(angle), Image.effect_noise((width, height), 45), scale=1.4)
        for angle in (0, 90, 180)
    ]
    return Image.merge("RGB", bands)


def build_graphic(width=1800, height=1200):
    """Flat UI-chrome background with solid shapes on top -- the screenshot and
    diagram case that JPEG's block DCT visibly rings on."""
    image = Image.new("RGB", (width, height), (240, 240, 245))
    draw = ImageDraw.Draw(image)
    for i in range(18):
        draw.rectangle(
            [50 + i * 90, 100 + (i % 5) * 180, 120 + i * 90, 400 + (i % 5) * 180],
            fill=(30 + i * 10, 90, 200 - i * 8),
        )
    draw.ellipse([200, 600, 900, 1100], fill=(220, 40, 60))
    return image


def build_scan(width=1700, height=2200):
    """Near-bilevel page of ink on paper. Ink coverage is kept around 10%,
    which is what real text runs at -- crank it higher and the image stops
    being bimodal and correctly classifies as a graphic instead."""
    rng = random.Random(11)
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    for line in range(46):
        y = 80 + line * 46
        x = 90
        while x < width - 200:
            word = rng.randint(28, 86)
            draw.rectangle([x, y, x + word, y + 5], fill=(20, 20, 20))
            x += word + 20
    return image


def encode(image, fmt="PNG", **kwargs):
    """Serialise a PIL image to bytes the way an upload would arrive."""
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, **kwargs)
    return buffer.getvalue()


@pytest.fixture(scope="session")
def photo_image():
    return build_photo()


@pytest.fixture(scope="session")
def photo_png(photo_image):
    return encode(photo_image)


@pytest.fixture(scope="session")
def graphic_png():
    return encode(build_graphic())


@pytest.fixture(scope="session")
def scan_png():
    return encode(build_scan())


@pytest.fixture(scope="session")
def scanned_pdf():
    """Two full-page JPEGs behind a thin PDF shell -- the shape of virtually
    every real submission, and the case the whole PDF path exists for."""
    page_jpeg = encode(build_photo(1600, 1200), "JPEG", quality=98)
    doc = fitz.open()
    try:
        for _ in range(2):
            page = doc.new_page(width=595, height=842)
            page.insert_image(fitz.Rect(0, 0, 595, 842), stream=page_jpeg)
        return doc.tobytes()
    finally:
        doc.close()


CONTENT_TYPES_XML = (
    b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/'
    b'package/2006/content-types"><Default Extension="png" ContentType="image/png"/>'
    b"</Types>"
)
DOCUMENT_XML = (
    b'<?xml version="1.0"?><w:document xmlns:w="x"><w:body><w:p>hello</w:p>'
    b"</w:body></w:document>"
)


def build_docx(media: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES_XML)
        archive.writestr("word/document.xml", DOCUMENT_XML)
        for name, content in media.items():
            archive.writestr(name, content)
    return buffer.getvalue()


@pytest.fixture(scope="session")
def docx_media_png():
    return encode(build_photo(900, 700))


@pytest.fixture
def docx_bytes(docx_media_png):
    return build_docx({"word/media/image1.png": docx_media_png})


def make_upload(raw: bytes, filename: str, content_type: str = "application/octet-stream"):
    return UploadFile(
        file=io.BytesIO(raw),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


class FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


@pytest.fixture
def storage(monkeypatch):
    """Stands in for Supabase Storage and records every object that would be
    written, so the tests can assert on paths, headers and bytes."""

    class Recorder:
        def __init__(self):
            self.calls = []
            self.status_code = 200
            self.text = ""

        def post(self, url, content=None, headers=None, timeout=None):
            self.calls.append({"url": url, "content": content, "headers": headers})
            return FakeResponse(self.status_code, self.text)

        @property
        def paths(self):
            return [call["url"].split("/object/")[-1] for call in self.calls]

    recorder = Recorder()
    monkeypatch.setattr(uploads.httpx, "post", recorder.post)
    return recorder


# --------------------------------------------------------------------------
# Content classification
# --------------------------------------------------------------------------


def test_a_continuous_tone_image_is_a_photo(photo_image):
    assert _classify_image(photo_image) == "photo"


def test_a_flat_background_with_shapes_is_a_graphic():
    assert _classify_image(build_graphic()) == "graphic"


def test_a_mostly_white_page_of_ink_is_text():
    assert _classify_image(build_scan()) == "text"


def test_a_solid_colour_image_is_text_not_a_photo():
    """A blank page is the degenerate end of the scan case; it must not fall
    through to the photo branch and get JPEG'd."""
    assert _classify_image(Image.new("RGB", (800, 600), (255, 255, 255))) == "text"


def test_an_empty_image_does_not_divide_by_zero():
    assert _classify_image(Image.new("RGB", (0, 0))) == "photo"


# --------------------------------------------------------------------------
# Standalone image compression
# --------------------------------------------------------------------------


def test_photos_are_routed_to_jpeg(photo_png):
    """libjpeg-turbo measured 15-20x faster than libwebp for equivalent
    quality, which is the trade this 0.1 vCPU host wants on its commonest
    input."""
    data, ext = _compress_image(photo_png)

    assert ext == ".jpg"
    assert Image.open(io.BytesIO(data)).format == "JPEG"


def test_graphics_stay_on_webp(graphic_png):
    data, ext = _compress_image(graphic_png)

    assert ext == ".webp"
    assert Image.open(io.BytesIO(data)).format == "WEBP"


def test_scans_stay_on_webp(scan_png):
    """JPEG rings around the sharp edges small text is made of, so the speed
    win is not worth taking here."""
    data, ext = _compress_image(scan_png)

    assert ext == ".webp"
    assert Image.open(io.BytesIO(data)).format == "WEBP"


def test_a_large_photo_lands_under_the_size_ceiling(photo_png):
    data, _ = _compress_image(photo_png)

    assert len(data) <= TARGET_MAX_FILE_SIZE
    assert len(data) < len(photo_png)


def test_oversized_images_are_capped_to_the_max_dimension(photo_png):
    data, _ = _compress_image(photo_png)

    result = Image.open(io.BytesIO(data))
    assert result.width <= MAX_IMAGE_DIMENSION
    assert result.height <= MAX_IMAGE_DIMENSION


def test_a_small_image_is_not_upscaled():
    """There is no size floor: an image already under budget should come back
    at its own dimensions, not padded up to the cap."""
    data, _ = _compress_image(encode(build_graphic(400, 300)))

    result = Image.open(io.BytesIO(data))
    assert (result.width, result.height) == (400, 300)


def test_transparent_photos_are_composited_onto_white_not_black():
    """JPEG has no alpha. A bare mode convert keeps transparent pixels' raw
    RGB -- usually black -- instead of blending them, which turns a
    transparent margin into a black border."""
    base = build_photo(900, 700).convert("RGBA")
    base.putalpha(0)  # fully transparent
    data, ext = _compress_image(encode(base))

    assert ext == ".jpg"
    result = Image.open(io.BytesIO(data)).convert("RGB")
    assert result.getpixel((5, 5)) == (255, 255, 255)


@pytest.mark.parametrize(
    "mode,container",
    [("L", "PNG"), ("P", "PNG"), ("CMYK", "JPEG"), ("LA", "PNG"), ("1", "PNG")],
)
def test_images_in_any_colour_mode_survive_compression(mode, container):
    """Anything not already RGB/RGBA has to be converted before encoding, or
    Pillow raises on save. Scanners and Office exports produce all of these:
    greyscale and bilevel scans, palette screenshots, CMYK print artwork."""
    source = build_graphic(600, 400).convert(mode)

    data, ext = _compress_image(encode(source, container))

    assert data, f"{mode} produced no output"
    assert ext in (".jpg", ".webp")
    assert Image.open(io.BytesIO(data)).size == (600, 400)


# --------------------------------------------------------------------------
# PDF compression
# --------------------------------------------------------------------------


def test_a_scanned_pdf_shrinks_substantially(scanned_pdf):
    data, ext = _compress_pdf(scanned_pdf)

    assert ext == ".pdf"
    assert len(data) < len(scanned_pdf)


def test_a_compressed_pdf_still_opens_with_its_pages_and_images(scanned_pdf):
    """The recompression path rewrites embedded image streams in place, which
    is exactly the kind of surgery that can produce a file that is smaller and
    unreadable."""
    data, _ = _compress_pdf(scanned_pdf)

    assert data.startswith(b"%PDF")
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        assert doc.page_count == 2
        for page in doc:
            assert page.get_images(full=True), "an embedded image was dropped entirely"
    finally:
        doc.close()


def test_a_pdf_with_no_images_survives_recompression():
    doc = fitz.open()
    doc.new_page(width=595, height=842).insert_text((72, 72), "Text only, no images")
    raw = doc.tobytes()
    doc.close()

    data, ext = _compress_pdf(raw)

    assert ext == ".pdf"
    reopened = fitz.open(stream=data, filetype="pdf")
    try:
        assert reopened.page_count == 1
        assert "Text only" in reopened[0].get_text()
    finally:
        reopened.close()


# --------------------------------------------------------------------------
# OOXML compression
# --------------------------------------------------------------------------


def test_non_media_parts_are_copied_through_byte_for_byte(docx_bytes):
    """document.xml, relationships and [Content_Types].xml decide whether
    Office can open the file at all; nothing in this path may touch them."""
    data, ext = _compress_ooxml(docx_bytes, ".docx")

    assert ext == ".docx"
    archive = zipfile.ZipFile(io.BytesIO(data))
    assert archive.read("word/document.xml") == DOCUMENT_XML
    assert archive.read("[Content_Types].xml") == CONTENT_TYPES_XML


def test_media_entries_keep_their_original_format(docx_bytes):
    """The documented Office-breaking failure mode: a .png entry holding JPEG
    bytes leaves the zip well-formed and the image broken, because Office
    resolves the codec from the entry's extension."""
    data, _ = _compress_ooxml(docx_bytes, ".docx")

    media = zipfile.ZipFile(io.BytesIO(data)).read("word/media/image1.png")
    assert Image.open(io.BytesIO(media)).format == "PNG"


def test_media_entries_actually_shrink(docx_bytes, docx_media_png):
    data, _ = _compress_ooxml(docx_bytes, ".docx")

    media = zipfile.ZipFile(io.BytesIO(data)).read("word/media/image1.png")
    assert len(media) < len(docx_media_png)


def test_the_entry_list_is_preserved(docx_bytes):
    data, _ = _compress_ooxml(docx_bytes, ".docx")

    original = zipfile.ZipFile(io.BytesIO(docx_bytes)).namelist()
    rewritten = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert rewritten == original


def test_media_below_the_skip_threshold_is_left_alone():
    """Re-encoding is real CPU work on a 0.1 vCPU host; a small embedded icon
    has nothing to give back."""
    small = encode(build_graphic(120, 90))
    assert len(small) < EMBEDDED_IMAGE_SKIP_THRESHOLD
    raw = build_docx({"word/media/icon.png": small})

    data, _ = _compress_ooxml(raw, ".docx")

    assert zipfile.ZipFile(io.BytesIO(data)).read("word/media/icon.png") == small


def test_images_outside_a_media_folder_are_left_alone(docx_media_png):
    """Only media parts are image data; a .png sitting elsewhere in the
    package is not something to re-encode blind."""
    raw = build_docx({"customXml/image1.png": docx_media_png})

    data, _ = _compress_ooxml(raw, ".docx")

    assert zipfile.ZipFile(io.BytesIO(data)).read("customXml/image1.png") == docx_media_png


def test_a_corrupt_media_entry_does_not_break_the_whole_document():
    """One unreadable image must not cost the user their submission -- it is
    copied through untouched and the rest of the file still compresses."""
    junk = b"\x89PNG\r\n\x1a\n" + b"not actually a png" * 8000
    assert len(junk) > EMBEDDED_IMAGE_SKIP_THRESHOLD
    raw = build_docx({"word/media/broken.png": junk})

    data, ext = _compress_ooxml(raw, ".docx")

    assert ext == ".docx"
    archive = zipfile.ZipFile(io.BytesIO(data))
    assert archive.read("word/media/broken.png") == junk
    assert archive.read("word/document.xml") == DOCUMENT_XML


def test_unknown_media_extensions_are_left_alone(docx_media_png):
    """Only png/jpg/jpeg have a known-safe in-place re-encode; an .svg or
    .emf entry is copied through."""
    raw = build_docx({"word/media/diagram.emf": docx_media_png})

    data, _ = _compress_ooxml(raw, ".docx")

    assert zipfile.ZipFile(io.BytesIO(data)).read("word/media/diagram.emf") == docx_media_png


# --------------------------------------------------------------------------
# Thumbnails
# --------------------------------------------------------------------------


def test_an_image_thumbnail_is_a_bounded_webp(photo_png):
    data, ext = _generate_image_thumbnail(photo_png)

    assert ext == ".webp"
    thumb = Image.open(io.BytesIO(data))
    assert thumb.format == "WEBP"
    assert max(thumb.size) <= 800


def test_a_pdf_thumbnail_renders_the_first_page(scanned_pdf):
    data, ext = _generate_pdf_thumbnail(scanned_pdf)

    assert ext == ".webp"
    thumb = Image.open(io.BytesIO(data))
    assert thumb.format == "WEBP"
    assert max(thumb.size) <= 800


# A structurally valid PDF whose page tree is empty. PyMuPDF refuses to *write*
# one ("cannot save with zero pages") but opens one happily, and a stripped or
# partially-uploaded file can genuinely look like this.
EMPTY_PDF = b"\n".join(
    [
        b"%PDF-1.4",
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj",
        b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj",
        b"trailer<</Size 3/Root 1 0 R>>",
        b"%%EOF",
        b"",
    ]
)


def test_a_pdf_with_no_pages_yields_no_thumbnail():
    assert fitz.open(stream=EMPTY_PDF, filetype="pdf").page_count == 0

    assert _generate_pdf_thumbnail(EMPTY_PDF) == (b"", "")


def test_thumbnail_generation_never_raises_on_garbage():
    """A failed thumbnail is cosmetic; it must not take the upload down."""
    assert _generate_image_thumbnail(b"not an image") == (b"", "")
    assert _generate_pdf_thumbnail(b"not a pdf") == (b"", "")


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------


def test_upload_targets_the_configured_bucket_and_returns_a_public_url(storage):
    url = _upload_to_supabase(b"payload", "certificates/abc.jpg", "image/jpeg")

    assert storage.calls[0]["url"].endswith(
        "/storage/v1/object/test-achievements/certificates/abc.jpg"
    )
    assert storage.calls[0]["content"] == b"payload"
    assert url.endswith("/storage/v1/object/public/test-achievements/certificates/abc.jpg")
    assert "/public/" in url


def test_upload_sends_the_service_key_and_content_type(storage):
    _upload_to_supabase(b"payload", "certificates/abc.jpg", "image/jpeg")

    headers = storage.calls[0]["headers"]
    assert headers["Authorization"] == "Bearer test-service-key"
    assert headers["apikey"] == "test-service-key"
    assert headers["Content-Type"] == "image/jpeg"


def test_a_storage_failure_surfaces_as_a_bad_gateway(storage):
    storage.status_code = 503
    storage.text = "bucket unavailable"

    with pytest.raises(HTTPException) as raised:
        _upload_to_supabase(b"payload", "certificates/abc.jpg", "image/jpeg")

    assert raised.value.status_code == 502
    assert "bucket unavailable" in raised.value.detail


# --------------------------------------------------------------------------
# compress_and_store -- the end-to-end decision table
# --------------------------------------------------------------------------


def test_a_file_under_the_threshold_is_stored_untouched(storage, graphic_png):
    """Re-encoding a file that is already within budget spends CPU for nothing
    and can only lose quality."""
    assert len(graphic_png) <= COMPRESS_SIZE_THRESHOLD

    result = compress_and_store(make_upload(graphic_png, "diagram.png", "image/png"), "certificates")

    assert result.stored_size == result.original_size == len(graphic_png)
    assert storage.calls[0]["content"] == graphic_png


def test_a_large_photo_is_compressed_and_re_extensioned(storage, photo_png):
    result = compress_and_store(make_upload(photo_png, "scan.png", "image/png"), "certificates")

    assert result.original_size == len(photo_png)
    assert result.stored_size < result.original_size
    assert result.content_type == "image/jpeg"
    assert storage.paths[0].endswith(".jpg")


def test_an_unknown_file_type_is_stored_unmodified(storage):
    """The 'any file, any size' guarantee: there is no safe generic
    compression for a zip or an mp4, so it goes to object storage as-is."""
    payload = b"PK\x03\x04" + b"\x00" * (COMPRESS_SIZE_THRESHOLD + 1000)

    result = compress_and_store(make_upload(payload, "bundle.zip", "application/zip"), "achievements")

    assert result.stored_size == len(payload)
    assert storage.calls[0]["content"] == payload
    assert result.content_type == "application/zip"


def test_a_corrupt_payload_falls_back_to_the_original_bytes(storage):
    """A mislabelled or damaged file must not cost the user their submission."""
    payload = b"\x89PNG\r\n\x1a\n" + b"garbage" * 40000

    result = compress_and_store(make_upload(payload, "broken.png", "image/png"), "certificates")

    assert result.stored_size == len(payload)
    assert storage.calls[0]["content"] == payload


def test_a_compression_result_larger_than_the_original_is_discarded(
    storage, monkeypatch, photo_png
):
    """Per-image budgets do not bound whole-file overhead -- PDF restructuring
    and zip re-deflation can both add more than they save."""
    monkeypatch.setattr(
        uploads, "_compress_image", lambda raw: (b"x" * (len(raw) + 1), ".jpg")
    )

    result = compress_and_store(make_upload(photo_png, "scan.png", "image/png"), "certificates")

    assert result.stored_size == len(photo_png)
    assert storage.calls[0]["content"] == photo_png
    assert storage.paths[0].endswith(".png"), "the original extension has to come back too"


def test_stored_objects_get_a_unique_path_under_their_category(storage, photo_png):
    first = compress_and_store(make_upload(photo_png, "a.png", "image/png"), "patents")
    second = compress_and_store(make_upload(photo_png, "a.png", "image/png"), "patents")

    assert first.url != second.url
    assert all(path.startswith("test-achievements/patents/") for path in storage.paths)


def test_an_image_upload_also_stores_a_thumbnail(storage, photo_png):
    result = compress_and_store(make_upload(photo_png, "scan.png", "image/png"), "certificates")

    assert result.thumbnail_url is not None
    assert len(storage.calls) == 2
    assert "/thumbs/" in storage.paths[1]
    assert storage.paths[1].endswith("_thumb.webp")
    assert storage.calls[1]["headers"]["Content-Type"] == "image/webp"


def test_a_pdf_upload_also_stores_a_thumbnail(storage, scanned_pdf):
    result = compress_and_store(make_upload(scanned_pdf, "notes.pdf", "application/pdf"), "certificates")

    assert result.content_type == "application/pdf"
    assert result.stored_size < result.original_size
    assert result.thumbnail_url is not None
    assert "/thumbs/" in storage.paths[1]


def test_a_non_previewable_upload_gets_no_thumbnail(storage):
    payload = b"PK\x03\x04" + b"\x00" * (COMPRESS_SIZE_THRESHOLD + 1000)

    result = compress_and_store(make_upload(payload, "bundle.zip", "application/zip"), "achievements")

    assert result.thumbnail_url is None
    assert len(storage.calls) == 1


def test_an_empty_upload_is_stored_without_a_thumbnail(storage):
    result = compress_and_store(make_upload(b"", "empty.png", "image/png"), "certificates")

    assert result.original_size == 0
    assert result.stored_size == 0
    assert result.thumbnail_url is None


def test_a_storage_outage_fails_the_upload(storage, photo_png):
    storage.status_code = 500

    with pytest.raises(HTTPException) as raised:
        compress_and_store(make_upload(photo_png, "scan.png", "image/png"), "certificates")

    assert raised.value.status_code == 502


# --------------------------------------------------------------------------
# The HTTP endpoint
# --------------------------------------------------------------------------


def test_upload_endpoint_stores_a_file_and_reports_both_sizes(
    client, factory, as_student, storage, photo_png
):
    student = factory.student()

    response = client.post(
        "/uploads",
        data={"category": "certificates"},
        files={"file": ("scan.png", photo_png, "image/png")},
        headers=as_student(student),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["original_size"] == len(photo_png)
    assert body["stored_size"] < body["original_size"]
    assert body["content_type"] == "image/jpeg"
    assert body["file_url"].startswith("https://test.invalid/storage/v1/object/public/")
    assert body["thumbnail_url"] is not None


def test_upload_endpoint_rejects_an_unknown_category(client, factory, as_student, storage):
    student = factory.student()

    response = client.post(
        "/uploads",
        data={"category": "../../etc"},
        files={"file": ("x.png", b"payload", "image/png")},
        headers=as_student(student),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Unknown upload category"
    assert storage.calls == []


def test_upload_endpoint_requires_authentication(client, storage, graphic_png):
    response = client.post(
        "/uploads",
        data={"category": "certificates"},
        files={"file": ("x.png", graphic_png, "image/png")},
    )

    assert response.status_code == 401
    assert storage.calls == []


def test_upload_endpoint_rejects_a_pending_role_selection_token(
    client, factory, as_pending_employee, storage, graphic_png
):
    """Same rule as the rest of the app: no active role, no session."""
    employee = factory.employee(roles=[EmployeeRole.faculty, EmployeeRole.hod])

    response = client.post(
        "/uploads",
        data={"category": "certificates"},
        files={"file": ("x.png", graphic_png, "image/png")},
        headers=as_pending_employee(employee),
    )

    assert response.status_code == 401
    assert storage.calls == []


def test_faculty_can_upload_too(client, factory, as_employee, storage, graphic_png):
    employee = factory.employee(roles=[EmployeeRole.faculty])

    response = client.post(
        "/uploads",
        data={"category": "achievements"},
        files={"file": ("diagram.png", graphic_png, "image/png")},
        headers=as_employee(employee, EmployeeRole.faculty),
    )

    assert response.status_code == 201
    assert storage.paths[0].startswith("test-achievements/achievements/")
