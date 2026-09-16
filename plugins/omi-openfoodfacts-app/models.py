"""Pydantic models for Open Food Facts Omi Integration."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


def clamp_page_size(value: Any, default: int = 5, minimum: int = 1, maximum: int = 10) -> int:
    """Safely clamp page size within [minimum, maximum]."""
    if value is None or value == "":
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def clean_barcode(barcode: Any) -> str:
    """Extract numeric digits from barcode string."""
    return "".join(char for char in str(barcode or "") if char.isdigit())


class ChatToolResponse(BaseModel):
    """Response model for Open Food Facts chat tool endpoints."""

    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


class SearchFoodsRequest(BaseModel):
    """Request model for searching foods by query."""

    query: str = Field(..., min_length=1, description="Food or product name to search for.")
    page_size: int = Field(default=5, ge=1, le=10, description="Number of products to return (1-10).")

    @field_validator("query", mode="before")
    @classmethod
    def validate_query(cls, v: Any) -> str:
        if v is None:
            raise ValueError("query is required")
        q = str(v).strip()
        if not q:
            raise ValueError("query cannot be empty")
        return q

    @field_validator("page_size", mode="before")
    @classmethod
    def validate_page_size(cls, v: Any) -> int:
        return clamp_page_size(v, default=5, minimum=1, maximum=10)


class LookupBarcodeRequest(BaseModel):
    """Request model for looking up a food by barcode."""

    barcode: str = Field(..., min_length=1, description="Product barcode.")

    @field_validator("barcode", mode="before")
    @classmethod
    def validate_barcode(cls, v: Any) -> str:
        if v is None:
            raise ValueError("barcode is required")
        cleaned = clean_barcode(v)
        if not cleaned:
            raise ValueError("barcode must contain at least one digit")
        return cleaned


class CompareFoodsRequest(BaseModel):
    """Request model for comparing multiple packaged foods by barcode."""

    barcodes: List[str] = Field(..., min_length=1, max_length=5, description="List of 1 to 5 product barcodes.")

    @field_validator("barcodes", mode="before")
    @classmethod
    def validate_barcodes(cls, v: Any) -> List[str]:
        if not isinstance(v, list) or not v:
            raise ValueError("barcodes must be a non-empty list")
        cleaned_list = []
        for item in v:
            c = clean_barcode(item)
            if c:
                cleaned_list.append(c)
        if not cleaned_list:
            raise ValueError("at least one valid barcode containing digits is required")
        return cleaned_list[:5]


class CheckAllergensRequest(BaseModel):
    """Request model for checking food allergens."""

    avoid: List[str] = Field(..., min_length=1, description="Allergens or ingredients to avoid.")
    barcode: Optional[str] = Field(default=None, description="Optional product barcode.")
    query: Optional[str] = Field(default=None, description="Optional search query.")

    @field_validator("avoid", mode="before")
    @classmethod
    def validate_avoid(cls, v: Any) -> List[str]:
        if not isinstance(v, list) or not v:
            raise ValueError("avoid must be a non-empty list")
        cleaned = [str(item).strip() for item in v if str(item).strip()]
        if not cleaned:
            raise ValueError("avoid must contain at least one non-empty term")
        return cleaned

    @field_validator("barcode", mode="before")
    @classmethod
    def validate_barcode(cls, v: Any) -> Optional[str]:
        if v is None or v == "":
            return None
        cleaned = clean_barcode(v)
        return cleaned if cleaned else None

    @field_validator("query", mode="before")
    @classmethod
    def validate_query(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        q = str(v).strip()
        return q if q else None

    @model_validator(mode="after")
    def validate_target(self) -> "CheckAllergensRequest":
        if not self.barcode and not self.query:
            raise ValueError("either barcode or query must be provided")
        return self
