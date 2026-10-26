"""Pure persisted-receipt admission policy shared by manual merge owners."""

from collections.abc import Mapping
from typing import Any


def source_has_merge_receipt(row: Mapping[str, Any]) -> bool:
    """A retained source already incorporated into a target is not fresh input."""
    return bool(row.get('transcript_corrections_moved_to') or row.get('dream_duplicate_of'))
