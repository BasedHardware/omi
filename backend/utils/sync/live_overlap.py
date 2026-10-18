"""Metadata-only live overlap admission; never treats a near-time stub as proof."""

import os


def live_overlap_enabled() -> bool:
    return os.getenv('SYNC_LIVE_OVERLAP_ENABLED', 'true').strip().lower() in {'true', '1', 'yes', 'on'}


def compatible_capture(left: dict, right: dict) -> bool:
    # Unknown is a partition, not a wildcard: wildcard equality is non-transitive.
    return all(left.get(key) == right.get(key) for key in ('source', 'client_device_id')) and bool(
        left.get('is_locked')
    ) == bool(right.get('is_locked'))


def _strict_overlap_seconds(row: dict, incoming: dict) -> float:
    """Strict same-partition interval overlap; ignores content and provenance."""
    if (
        not incoming.get('client_device_id')
        or not compatible_capture(row, incoming)
        or row.get('deleted')
        or row.get('sync_merged_into')
        or row.get('status') not in ('completed', 'in_progress')
    ):
        return 0
    return max(
        0.0,
        (
            min(row['finished_at'], incoming['finished_at']) - max(row['started_at'], incoming['started_at'])
        ).total_seconds(),
    )


def live_overlap_seconds(row: dict, incoming: dict) -> float:
    if not (
        ((row.get('capture_evidence') or {}).get('origin') == 'live' or row.get('sync_live_target'))
        and row.get('has_content')
    ):
        return 0
    return _strict_overlap_seconds(row, incoming)


def discoverable_live_overlap(row: dict, incoming: dict) -> bool:
    """Coarse admission for discovery: same partition, strict overlap, live lifecycle.

    Deliberately content-agnostic: a same-device stub that has not written its
    first transcript yet must still be returned as a hint so the assignment
    transaction reads that document. The transaction's own re-read through
    :func:`choose_live_overlap` stays the only authority and keeps still-empty
    stubs excluded at commit time; reading them is what lets Firestore commit
    contention retry the assignment once the listen writer adds content, instead
    of publishing a twin the transaction never saw conflict on.
    """
    return _strict_overlap_seconds(row, incoming) > 0


def choose_live_overlap(rows: list[dict], incoming: dict) -> str | None:
    eligible = [(live_overlap_seconds(row, incoming), row) for row in rows]
    eligible = [(seconds, row) for seconds, row in eligible if seconds > 0]
    if not eligible:
        return None
    # Stable choice, with the greatest shared audio first. Other live identities
    # remain independent: an active listen connection may still write to them.
    return min(eligible, key=lambda pair: (-pair[0], pair[1]['started_at'], pair[1]['id']))[1]['id']
