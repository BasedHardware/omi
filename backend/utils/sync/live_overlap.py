"""Metadata-only live overlap admission; never treats a near-time stub as proof."""

import os

from config import refactor_modes
from utils.capture.identity import compatible_keys, same_explicit_key
from utils.capture.shadow import compare

from utils.sync.clock_run import SYNC_CLOCK_RUN_FIELD


def live_overlap_enabled() -> bool:
    return os.getenv('SYNC_LIVE_OVERLAP_ENABLED', 'true').strip().lower() in {'true', '1', 'yes', 'on'}


def compatible_capture(left: dict, right: dict) -> bool:
    # Unknown is a partition, not a wildcard: wildcard equality is non-transitive.
    # An estimated-clock run (utils/sync/clock_run.py) is a partition too: its
    # times never prove adjacency to another run or to device-clocked audio.
    return all(
        left.get(key) == right.get(key) for key in ('source', 'client_device_id', SYNC_CLOCK_RUN_FIELD)
    ) and bool(left.get('is_locked')) == bool(right.get('is_locked'))


def _strict_overlap_seconds(row: dict, incoming: dict, *, require_device: bool = True) -> float:
    """Strict same-partition interval overlap; ignores content and provenance."""
    if (
        (require_device and not incoming.get('client_device_id'))
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
    return _strict_overlap_seconds(row, incoming) > 0 or (
        refactor_modes.shadow_or_serve('CAPTURE_COVERAGE_MODE')
        and same_explicit_key(row, incoming)
        and _strict_overlap_seconds(row, incoming, require_device=False) > 0
    )


def _legacy_choose_live_overlap(rows: list[dict], incoming: dict) -> str | None:
    eligible = [(live_overlap_seconds(row, incoming), row) for row in rows]
    eligible = [(seconds, row) for seconds, row in eligible if seconds > 0]
    if not eligible:
        return None
    # Stable choice, with the greatest shared audio first. Other live identities
    # remain independent: an active listen connection may still write to them.
    return min(eligible, key=lambda pair: (-pair[0], pair[1]['started_at'], pair[1]['id']))[1]['id']


def _new_live_overlap_seconds(row: dict, incoming: dict) -> float:
    if not compatible_keys(row, incoming):
        return 0
    keyed_open = same_explicit_key(row, incoming) and row.get('status') == 'in_progress'
    if keyed_open:
        # An OPEN occasion can bind before its first transcript. This chooses
        # an identity only; wall time never claims covered source frames.
        return _strict_overlap_seconds(row, incoming, require_device=False)
    return live_overlap_seconds(row, incoming)


def choose_live_overlap(rows: list[dict], incoming: dict, *, uid: str | None = None) -> str | None:
    # refactor: superseded by this module's keyed path when CAPTURE_COVERAGE_MODE=serve
    legacy = _legacy_choose_live_overlap(rows, incoming)
    if not refactor_modes.shadow_or_serve('CAPTURE_COVERAGE_MODE'):
        return legacy
    eligible = [(seconds, row) for row in rows if (seconds := _new_live_overlap_seconds(row, incoming)) > 0]
    proposed = (
        min(eligible, key=lambda pair: (-pair[0], pair[1]['started_at'], pair[1]['id']))[1]['id'] if eligible else None
    )
    compare('live_bind', 'agree' if proposed == legacy else 'disagree')
    return proposed if refactor_modes.serving_for('CAPTURE_COVERAGE_MODE', uid) else legacy
