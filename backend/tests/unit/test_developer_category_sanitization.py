import pytest
from enum import Enum
from fastapi import HTTPException


class DummyCategory(Enum):
    BUSINESS = "business"
    PERSONAL = "personal"


def parse_category_safe(category_str: str):
    try:
        return [DummyCategory(c.strip()) for c in category_str.split(",") if c.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid memory category provided")


def test_parse_category_valid():
    cats = parse_category_safe("business, personal")
    assert len(cats) == 2
    assert cats[0] == DummyCategory.BUSINESS
    assert cats[1] == DummyCategory.PERSONAL


def test_parse_category_invalid_masks_raw_exception():
    with pytest.raises(HTTPException) as exc_info:
        parse_category_safe("unknown_category_<script>alert(1)</script>")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid memory category provided"
    assert "DummyCategory" not in exc_info.value.detail
    assert "<script>" not in exc_info.value.detail
