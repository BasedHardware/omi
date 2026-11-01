"""Pure persisted-receipt admission policy shared by manual merge owners."""

from collections.abc import Mapping
from typing import Any


def source_has_merge_receipt(row: Mapping[str, Any]) -> bool:
    """A retained source already incorporated into a target is not fresh input."""
    # Dream may mark semantic duplicates without transferring their content.
    # Only the atomic correction-transfer receipt proves incorporation.
    return bool(row.get('transcript_corrections_moved_to'))
