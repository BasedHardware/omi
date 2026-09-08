from io import BytesIO

import pytest
from fastapi import HTTPException
from PIL import Image

from routers.frame_requests import _canonicalize_frame_image, _validated_image_content_type


@pytest.mark.parametrize("image_format", ["JPEG", "PNG", "WEBP"])
def test_supported_uploads_decode_and_canonicalize_to_bounded_metadata_free_jpeg(image_format):
    source = BytesIO()
    Image.new("RGB", (2400, 1600), "red").save(source, format=image_format)
    payload = source.getvalue()
    assert _validated_image_content_type(payload).startswith("image/")
    canonical = _canonicalize_frame_image(payload)
    with Image.open(BytesIO(canonical)) as image:
        assert image.format == "JPEG"
        assert max(image.size) <= 1920
        assert image.width * image.height <= 2_500_000
        assert image.getexif() == {}


def test_spoofed_or_oversized_dimensions_fail_closed():
    with pytest.raises(HTTPException):
        _validated_image_content_type(b"not an image")
    source = BytesIO()
    Image.new("RGB", (5001, 5001)).save(source, format="PNG")
    with pytest.raises(HTTPException) as error:
        _validated_image_content_type(source.getvalue())
    assert error.value.status_code == 413
