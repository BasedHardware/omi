"""Typed request/response models for the Open Food Facts chat tools (#13987).

The Pydantic field types give FastAPI a real validation boundary: malformed
payloads raise ``RequestValidationError``, which ``main.py`` translates into a
HTTP 200 ``ChatToolResponse`` error envelope for Omi chat-tool integration.

Normalization that must also hold for hand-constructed models (trimming,
page-size clamping, target checks) lives in explicit ``clean_*`` methods so it
does not depend on pydantic version-specific validator behavior.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


class ChatToolResponse(BaseModel):
    """Standard response envelope for Omi chat tool endpoints."""

    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None

    @classmethod
    def ok(cls, message: str, data: Optional[Dict[str, Any]] = None) -> "ChatToolResponse":
        return cls(success=True, message=message, data=data)

    @classmethod
    def fail(cls, message: str, data: Optional[Dict[str, Any]] = None) -> "ChatToolResponse":
        return cls(success=False, message=message, data=data or {"error": message})

    def as_dict(self) -> Dict[str, Any]:
        """Serialize across pydantic v1/v2 (and framework-only test stubs)."""
        if hasattr(self, "model_dump"):
            return self.model_dump()
        if hasattr(self, "dict"):
            return self.dict()
        return dict(self.__dict__)


class SearchFoodsRequest(BaseModel):
    query: Any = ""
    page_size: Any = 5

    def clean_query(self) -> str:
        return str(self.query or "").strip()

    def clamped_page_size(self) -> int:
        return _clamp_int(self.page_size, default=5, minimum=1, maximum=10)


class LookupBarcodeRequest(BaseModel):
    barcode: Any = ""

    def raw_barcode(self) -> str:
        return str(self.barcode or "")


class CompareFoodsRequest(BaseModel):
    barcodes: Optional[List[Any]] = None

    def barcodes_error(self) -> Optional[str]:
        if self.barcodes is None:
            return "barcodes is required"
        if not isinstance(self.barcodes, list):
            return "barcodes must be a list"
        if not self.barcodes:
            return "barcodes must be a non-empty list"
        return None

    def clean_barcodes(self, limit: int = 5) -> List[str]:
        if not isinstance(self.barcodes, list):
            return []
        return [str(item) for item in self.barcodes][:limit]


class CheckAllergensRequest(BaseModel):
    barcode: Optional[Any] = None
    query: Optional[Any] = None
    avoid: Optional[List[Any]] = None

    def clean_avoid(self) -> List[str]:
        if not isinstance(self.avoid, list):
            return []
        return [term for term in (str(item).strip() for item in self.avoid) if term]

    def has_barcode(self) -> bool:
        return bool(str(self.barcode or "").strip())

    def raw_barcode(self) -> str:
        return str(self.barcode or "")

    def clean_query(self) -> str:
        return str(self.query or "").strip()

    def target_error(self) -> Optional[str]:
        """At least one of barcode or query must be provided."""
        if not self.has_barcode() and not self.clean_query():
            return "provide a barcode or a query to check allergens"
        return None
