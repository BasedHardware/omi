"""Estimate projection payload sizes and partition rows into bounded Firestore commits."""

import json
import logging

from utils.conversations.v3 import Conflict

logger = logging.getLogger(__name__)


def encoded_bytes(value):
    return len(json.dumps(value, default=str).encode())


def log_largest_write(staged, *, batch, batches):
    """Name the largest document the failed transaction staged: kind and estimated bytes, never ids or content."""
    sizes: list[tuple[str, int, int | None]] = [
        ('derived_row', encoded_bytes(row), None) for row in staged.get('rows') or []
    ]
    for current, update in (staged.get('recordings') or {}).values():
        merged = {**current, **update}
        sizes.append(('recording', encoded_bytes(merged), len(merged.get('claims') or [])))
    if staged.get('lease') is not None:
        sizes.append(('builder_lease', encoded_bytes({**staged['lease'][0], **staged['lease'][1]}), None))
    if not sizes:
        return
    kind, size, claims = max(sizes, key=lambda item: item[1])
    logger.warning(
        'v3 projection write too large kind=%s bytes=%d claims=%s batch=%d batches=%d staged_total_bytes=%d',
        kind,
        size,
        claims if claims is not None else '-',
        batch,
        batches,
        sum(item[1] for item in sizes),
    )


def partition_rows(
    rows,
    prepared,
    *,
    fixed,
    fixed_writes,
    max_writes,
    max_bytes,
    row_bytes,
    max_pointers,
    removals,
    settle,
    replacing_claimants,
):
    if removals and fixed_writes + bool(rows) > max_writes:
        raise Conflict('backfill_partition_budget')
    max_rows = max(1, max_writes - fixed_writes)
    batches, current, size, pointers = [], [], 0, 0
    for raw, encoded in zip(rows, prepared):
        amount = encoded_bytes(encoded)
        # Privacy filtering resolves each prepared pointer before the first write.
        pointer = isinstance(encoded.get('transcript_segments'), dict)
        if current and (
            size + amount > row_bytes
            or fixed + size + amount > max_bytes
            or len(current) >= max_rows
            or (pointer and pointers >= max_pointers)
        ):
            batches.append(current)
            current, size, pointers = [], 0, 0
        current.append((raw, encoded))
        size += amount
        pointers += pointer
    if current or not batches:
        batches.append(current)
    if settle and (len(batches) != 1 or fixed_writes + len(rows) > max_writes or fixed + size > max_bytes):
        # Settling a tile and giving its claims to the replacement must be a single commit.
        raise Conflict('request_too_large')
    if replacing_claimants and len(batches) > 1:
        raise Conflict('backfill_partition_budget')
    return batches
