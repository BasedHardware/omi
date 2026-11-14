"""Metadata-only live overlap admission; never treats a near-time stub as proof."""

import math
import os
from datetime import timedelta

from utils.conversations.recorded_time import conversation_span, segment_span, segment_span_is_exact

from config import refactor_modes
from utils.capture.identity import compatible_keys, same_explicit_key
from utils.capture.shadow import compare

from utils.sync.clock_run import SYNC_CLOCK_RUN_FIELD

# A tolerance beyond a day cannot describe a plausible capture window, so it is
# malformed rather than merely strict. Keeping the bound also keeps the
# datetime arithmetic below inside range.
MAX_TOLERANCE_SECONDS = 86_400.0


def _tolerance(tolerance_seconds: float) -> timedelta:
    """A malformed tolerance resolves strict (0) instead of raising or loosening."""
    try:
        value = float(tolerance_seconds)
    except (TypeError, ValueError, OverflowError):
        return timedelta(0)
    if not math.isfinite(value) or value < 0 or value > MAX_TOLERANCE_SECONDS:
        return timedelta(0)
    return timedelta(seconds=min(value, MAX_TOLERANCE_SECONDS))


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
        or row.get('status') not in ('completed', 'in_progress', 'processing')
    ):
        return 0
    left, right = conversation_span(row), conversation_span(incoming)
    if left is None or right is None:
        return 0
    return max(
        0.0,
        (min(left.recorded_end, right.recorded_end) - max(left.recorded_start, right.recorded_start)).total_seconds(),
    )


def span_contained(donor: dict, target: dict, *, tolerance_seconds: float = 0.0) -> bool:
    """Whether the donor's whole recorded span lies inside the target's.

    Both sides must prove their extent with placed transcript segments. A row
    whose only span is the ``finished_at`` wall-clock envelope is a coarse hint,
    not proof the target captured the donor's speech, so it refuses rather than
    authorizes the merge and the donor stays standalone.

    The donor must also carry no segment that proves no position. An
    ``unplaced`` segment has no proven offset, so it cannot be shown to be
    inside the target; the donor's extent would then cover only part of its
    speech and absorbing it would lose the rest.

    Tolerance tightens the target window and never loosens it, so it can only
    refuse more. Shrinking the donor span is never acceptable: a donor holding
    speech just outside the target would then pass and its audio would be lost.
    """
    donor_span = segment_span(donor)
    target_span = segment_span(target)
    if donor_span is None or target_span is None:
        return False
    if not segment_span_is_exact(donor):
        return False
    tolerance = _tolerance(tolerance_seconds)
    donor_start, donor_end = donor_span
    target_start, target_end = target_span
    # Clamp to half the target width before subtracting: a wider tolerance
    # inverts the window and refuses anyway, and the clamp keeps the arithmetic
    # inside datetime range.
    tolerance = min(tolerance, (target_end - target_start) / 2)
    return donor_start >= target_start + tolerance and donor_end <= target_end - tolerance


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
    if (
        not compatible_capture(row, incoming)
        or row.get('deleted')
        or row.get('sync_merged_into')
        or row.get('status') not in ('completed', 'in_progress', 'processing')
    ):
        return False
    if _strict_overlap_seconds(row, incoming) > 0:
        return True
    # Legacy metadata can over-discover; only the decoded recorded-span check
    # in choose_live_overlap authorizes membership. No wall-time ownership.
    return (
        row.get('started_at') is not None
        and row.get('finished_at') is not None
        and max(row['started_at'], incoming['started_at']) < min(row['finished_at'], incoming['finished_at'])
    )


def _legacy_choose_live_overlap(rows: list[dict], incoming: dict) -> str | None:
    eligible = [(live_overlap_seconds(row, incoming), row) for row in rows]
    eligible = [(seconds, row) for seconds, row in eligible if seconds > 0]
    if not eligible:
        return None
    # Stable choice, with the greatest shared audio first. Other live identities
    # remain independent: an active listen connection may still write to them.
    return min(eligible, key=lambda pair: (-pair[0], pair[1]['started_at'], pair[1]['id']))[1]['id']


def _live_binding_score(row: dict, incoming: dict) -> float:
    if not compatible_keys(row, incoming):
        return 0
    keyed_open = same_explicit_key(row, incoming) and row.get('status') == 'in_progress'
    if keyed_open and compatible_capture(row, incoming) and not row.get('deleted') and not row.get('sync_merged_into'):
        # Matching stream identity can bind an empty OPEN stub. The score floor
        # selects identity only; it is never a claim of recorded frame coverage.
        return _strict_overlap_seconds(row, incoming, require_device=False) or 1e-9
    return live_overlap_seconds(row, incoming)


def choose_live_overlap(
    rows: list[dict], incoming: dict, *, uid: str | None = None, record_comparison: bool = True
) -> str | None:
    # refactor: superseded by this module's keyed path when CAPTURE_COVERAGE_MODE=serve
    legacy = _legacy_choose_live_overlap(rows, incoming)
    if not refactor_modes.shadow_or_serve('CAPTURE_COVERAGE_MODE'):
        return legacy
    eligible = [(seconds, row) for row in rows if (seconds := _live_binding_score(row, incoming)) > 0]
    proposed = (
        min(eligible, key=lambda pair: (-pair[0], pair[1]['started_at'], pair[1]['id']))[1]['id'] if eligible else None
    )
    if record_comparison:
        # A caller that must stay side-effect-inert (the contained-donor shadow
        # pass) opts out: it may not inject live_bind disagreement samples into
        # the capture-coverage rollout's own evidence.
        compare('live_bind', 'agree' if proposed == legacy else 'disagree')
    return proposed if refactor_modes.serving_for('CAPTURE_COVERAGE_MODE', uid) else legacy
