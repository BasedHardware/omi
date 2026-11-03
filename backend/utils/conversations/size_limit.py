"""Shared encoded-document bound for unattended conversation absorption."""

from typing import Any, Mapping

from google.cloud.firestore_v1 import DELETE_FIELD

from utils.firestore_document_size import estimate_firestore_document_bytes

# Leave 224 KiB below Firestore's 1 MiB ceiling: the sync preflight's 124 KiB
# reserve plus another 100 KiB for later summaries and derived processing.
# This limits absorption, not ordinary appends (which retain the 900 KiB preflight).
CONVERSATION_ABSORPTION_BYTE_CAP = 800 * 1024
PROJECTED_SIZE_BUCKETS = frozenset({'lt_500k', '500_700k', '700_800k', '800_900k', '900k_1m', 'gt_1m'})


def projected_size_bucket(size: int) -> str:
    """Content-free KiB bands; exactly 1 MiB remains in the last non-overflow band."""
    for limit, bucket in ((500, 'lt_500k'), (700, '500_700k'), (800, '700_800k'), (900, '800_900k')):
        if size < limit * 1024:
            return bucket
    return '900k_1m' if size <= 1024 * 1024 else 'gt_1m'


def projected_document_bytes(
    reference: Any, payload: Mapping[str, Any], current: Mapping[str, Any] | None = None
) -> int:
    """Size the stored row after an encoded top-level update, including removals.

    Call only after the real write encoder and its projection invalidations.
    All absorption patches replace top-level fields; no extra document read.
    """
    stored = dict(current or {})
    for field, value in payload.items():
        if value is DELETE_FIELD:
            stored.pop(field, None)
        else:
            stored[field] = value
    path = getattr(reference, 'path', None)
    return estimate_firestore_document_bytes(stored, path if isinstance(path, str) else None)
