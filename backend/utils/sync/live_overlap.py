"""Metadata-only live overlap admission; never treats a near-time stub as proof."""

import os


def live_overlap_enabled() -> bool:
    return os.getenv('SYNC_LIVE_OVERLAP_ENABLED', 'true').strip().lower() in {'true', '1', 'yes', 'on'}


def compatible_capture(left: dict, right: dict) -> bool:
    # Unknown is a partition, not a wildcard: wildcard equality is non-transitive.
    return all(left.get(key) == right.get(key) for key in ('source', 'client_device_id')) and bool(
        left.get('is_locked')
    ) == bool(right.get('is_locked'))


def live_overlap_seconds(row: dict, incoming: dict) -> float:
    if (
        not incoming.get('client_device_id')
        or not compatible_capture(row, incoming)
        or row.get('deleted')
        or row.get('sync_merged_into')
        or row.get('status') not in ('completed', 'in_progress')
        or not ((row.get('capture_evidence') or {}).get('origin') == 'live' or row.get('sync_live_target'))
        or not row.get('has_content')
    ):
        return 0
    return max(
        0.0,
        (
            min(row['finished_at'], incoming['finished_at']) - max(row['started_at'], incoming['started_at'])
        ).total_seconds(),
    )


def choose_live_overlap(rows: list[dict], incoming: dict) -> str | None:
    eligible = [(live_overlap_seconds(row, incoming), row) for row in rows]
    eligible = [(seconds, row) for seconds, row in eligible if seconds > 0]
    if not eligible:
        return None
    # Stable choice, with the greatest shared audio first. Other live identities
    # remain independent: an active listen connection may still write to them.
    return min(eligible, key=lambda pair: (-pair[0], pair[1]['started_at'], pair[1]['id']))[1]['id']
