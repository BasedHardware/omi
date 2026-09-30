"""Bind each segment of a safety-WAL upload to its live rollover generation.

One phone recording (origin id R, the ``client_conversation_id`` it sent to
``/v4/listen``) becomes many live conversations: every silence rollover mints a
new server recording id and row. The phone tags all WALs with R, and a batch of
WALs can straddle several generations. Resolving the whole batch against rows
whose recording id equals R (``recording_session_target``) therefore matched
only the first generation, dropped the phone's stamp on a miss, and created a
second, sync-owned conversation for speech live had already captured.

Here every VAD segment is bound on its own, against every generation of R
(``external_data.recording_origin_id == R``, plus the row bound to R itself for
generations created before that stamp existed). A generation binds only when
it is the unique canonical row whose interval holds the segment: strictly
first, then with the bounded edge allowance of ``recording_session_target``
(overlapping it, starting at most 5 s before it and ending at most 60 s after
its last word). Smart-merge donor tombstones stay
in the lineage and canonicalize to their survivor. When no unique generation
exists, the segment keeps the phone's stamp if it has one (the pre-#19424
behavior) and otherwise stays unbound for temporal assignment, which never
adopts live rows. A different unique generation overrides the stamp.

The plan is a pure function of the lineage rows, the segment spans and the
stamp, so a retried job binds its remaining segments the same way against the
same rows. Any lookup or planning error fails open to that fallback; it never
fails the sync job by itself.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from config.sync_lineage import sync_lineage_resolve_enabled
from config.sync_telemetry import bounded_correlation_ref, bounded_exception_class
from utils.metrics import OMI_SYNC_LINEAGE_RESOLVE_TOTAL
from utils.observability.fallback import record_fallback
from utils.sync.recording_session_target import (
    START_SKEW_SECONDS,
    TRAILING_AUDIO_SECONDS,
    clean_text,
    source_value,
    unix_seconds,
)

logger = logging.getLogger(__name__)

# A 5-WAL batch spans about five minutes and a rollover needs 120 s of silence,
# so a batch normally touches at most three generations. Older generations
# beyond this window cannot hold the batch's audio (see ``_decidable``).
GENERATION_LIMIT = 8
# Rows sharing the origin's own recording id; more than this is anomalous.
ORIGIN_ROW_LIMIT = 5

OUTCOMES = (
    'bound',
    'split_across_generations',
    'stamp_overridden',
    'stamp_fallback',
    'no_rows',
    'truncated',
    'interval_miss',
    'lookup_failed',
    'disabled',
)


@dataclass(frozen=True)
class _Generation:
    id: str
    start: float
    end: float
    canonical: str
    deleted: bool


@dataclass
class LineagePlan:
    targets: dict[str, Optional[str]]
    outcome: str
    reason: str
    counts: dict[str, int] = field(default_factory=dict)
    generations: int = 0
    rows: int = 0
    degraded: bool = False


def lineage_resolution_requested(
    recording_session_id: Optional[str],
    audio_start_seconds: Optional[float],
    audio_end_seconds: Optional[float],
    *,
    job_id: Optional[str] = None,
) -> bool:
    """True when this upload binds per segment; off records ``disabled`` for eligible uploads.

    Eligibility is exactly the population the whole-batch resolver serves:
    a recording id plus both audio bounds.
    """
    if not recording_session_id or audio_start_seconds is None or audio_end_seconds is None:
        return False
    if sync_lineage_resolve_enabled():
        return True
    _emit(LineagePlan(targets={}, outcome='disabled', reason='none'), job_id)
    return False


def _chain_end(row_id: str, redirects: Mapping[str, str]) -> str:
    seen = set()
    current = row_id
    while current in redirects and current not in seen:
        seen.add(current)
        current = redirects[current]
    return current


def _generations(
    rows: Sequence[Mapping[str, Any]],
    origin_id: str,
    *,
    source: Any,
    client_device_id: Optional[str],
    is_locked: bool,
) -> list[_Generation]:
    """Provenance-compatible generations of ``origin_id`` with valid intervals."""
    wanted_source = source_value(source)
    device_id = clean_text(client_device_id)
    redirects: dict[str, str] = {}
    candidates: list[tuple[str, float, float, bool]] = []
    for row in rows:
        row_id = clean_text(row.get('id'))
        external = row.get('external_data')
        external = external if isinstance(external, Mapping) else {}
        linked = origin_id in (
            clean_text(external.get('recording_origin_id')),
            clean_text(external.get('recording_session_id')),
        )
        if not row_id or not linked:
            continue
        redirect = clean_text(row.get('sync_merged_into'))
        if row.get('deleted') and not redirect:
            # Only redirect tombstones stay in the lineage; nothing else sets deleted.
            continue
        if redirect:
            redirects[row_id] = redirect
        if (
            source_value(row.get('source')) != wanted_source
            or clean_text(row.get('client_device_id')) != device_id
            or bool(row.get('is_locked')) != bool(is_locked)
        ):
            continue
        start, end = unix_seconds(row.get('started_at')), unix_seconds(row.get('finished_at'))
        if start is None or end is None or end < start:
            continue
        candidates.append((row_id, start, end, bool(row.get('deleted'))))
    return [
        _Generation(row_id, start, end, _chain_end(row_id, redirects), deleted)
        for row_id, start, end, deleted in sorted(candidates)
    ]


def _unique(matches: list[_Generation]) -> Optional[str]:
    """The explicit target for matches that all canonicalize to one row, else None."""
    canonicals = {generation.canonical for generation in matches}
    if len(canonicals) != 1:
        return None
    canonical = canonicals.pop()
    if any(generation.id == canonical and not generation.deleted for generation in matches):
        return canonical
    # Only donors matched: intake follows their redirect to the survivor (smart
    # merge keeps the source/device/lock partition) and supersedes the audio
    # when that survivor was deleted, so no deleted row is ever recreated.
    return min(generation.id for generation in matches)


def _bind(generations: list[_Generation], start: float, end: float) -> Optional[str]:
    strict = [g for g in generations if g.start <= start and end <= g.end]
    if strict:
        return _unique(strict)
    tolerant = [
        g
        for g in generations
        if start <= g.end
        and end >= g.start
        and start >= g.start - START_SKEW_SECONDS
        and end <= g.end + TRAILING_AUDIO_SECONDS
    ]
    return _unique(tolerant) if tolerant else None


def _decidable(start: float, truncated_before: Optional[float]) -> bool:
    # Unread generations started at or before the oldest row read, and a
    # recording's generations follow one another, so an unread one ended by
    # then. A match reaches at most the trailing allowance past a generation's
    # end; audio starting later than that cannot belong to an unread generation.
    # (A smart-merge survivor can end later, but its donors are in the window and
    # canonicalize to it.)
    return truncated_before is None or start - TRAILING_AUDIO_SECONDS >= truncated_before


def select_segment_targets(
    rows: Sequence[Mapping[str, Any]],
    origin_id: str,
    spans: Mapping[str, tuple[float, float]],
    *,
    stamped_target: Optional[str],
    source: Any,
    client_device_id: Optional[str],
    is_locked: bool,
    truncated_before: Optional[float] = None,
    lookup_failed: bool = False,
) -> LineagePlan:
    """Pure per-segment plan: unique generation, else the stamp, else unbound."""
    generations = (
        []
        if lookup_failed
        else _generations(
            rows, clean_text(origin_id), source=source, client_device_id=client_device_id, is_locked=is_locked
        )
    )
    canonical_by_id = {generation.id: generation.canonical for generation in generations}
    stamp = clean_text(stamped_target) or None
    stamp_canonical = canonical_by_id.get(stamp, stamp) if stamp else None
    targets: dict[str, Optional[str]] = {}
    counts = {'bound': 0, 'stamp_overridden': 0, 'stamp_fallback': 0, 'unbound': 0}
    bound_canonicals: set[str] = set()
    misses: set[str] = set()
    for key in sorted(spans):
        start, end = spans[key]
        bound = None
        if lookup_failed:
            misses.add('lookup_failed')
        elif not generations:
            misses.add('no_rows')
        elif not _decidable(start, truncated_before):
            misses.add('truncated')
        else:
            bound = _bind(generations, start, end)
            if bound is None:
                misses.add('interval_miss')
        if bound is not None:
            canonical = canonical_by_id.get(bound, bound)
            bound_canonicals.add(canonical)
            counts['stamp_overridden' if stamp and stamp_canonical != canonical else 'bound'] += 1
            targets[key] = bound
        else:
            counts['stamp_fallback' if stamp else 'unbound'] += 1
            targets[key] = stamp
    reason = next(
        (item for item in ('lookup_failed', 'no_rows', 'truncated', 'interval_miss') if item in misses), 'none'
    )
    if lookup_failed:
        outcome = 'lookup_failed'
    elif len(bound_canonicals) > 1:
        outcome = 'split_across_generations'
    elif bound_canonicals:
        outcome = 'stamp_overridden' if counts['stamp_overridden'] else 'bound'
    else:
        outcome = 'stamp_fallback' if stamp else reason
    return LineagePlan(
        targets=targets,
        outcome=outcome,
        reason=reason,
        counts=counts,
        generations=len(bound_canonicals),
        rows=len(generations),
    )


def _load_lineage(
    uid: str, origin_id: str, started_before: datetime, firestore_client: Any
) -> tuple[list[dict[str, Any]], Optional[float], bool]:
    """Lineage rows, the start before which the window is incomplete, and whether it degraded."""
    # Import on use, like recording_session_target: pipeline.py loads this module
    # while unit harnesses stub google.cloud and the database package.
    from database import sync_recording_lineage as lineage_db

    degraded = False
    try:
        rows = lineage_db.get_recording_generations(
            uid, origin_id, started_before=started_before, limit=GENERATION_LIMIT, firestore_client=firestore_client
        )
    except Exception as exc:
        # E.g. the composite index is still building: keep the origin-row read,
        # the same candidate set the whole-batch resolver has always used.
        logger.warning('event=sync_lineage_lookup outcome=degraded exception_type=%s', bounded_exception_class(exc))
        rows, degraded = [], True
    truncated_before = None
    if len(rows) > GENERATION_LIMIT:
        rows = rows[:GENERATION_LIMIT]
        truncated_before = unix_seconds(rows[-1].get('started_at'))
        if truncated_before is None:
            truncated_before = math.inf
    if truncated_before is None and not any(
        clean_text((row.get('external_data') or {}).get('recording_session_id')) == origin_id for row in rows
    ):
        # A recording that began before the origin stamp existed: only the row
        # bound to R itself is findable. A truncated window already starts after it.
        legacy = lineage_db.get_origin_generation(
            uid, origin_id, limit=ORIGIN_ROW_LIMIT, firestore_client=firestore_client
        )
        if len(legacy) > ORIGIN_ROW_LIMIT:
            return rows, math.inf, degraded
        known = {row.get('id') for row in rows}
        rows += [row for row in legacy if row.get('id') not in known]
    return rows, truncated_before, degraded


def resolve_segment_targets(
    uid: str,
    origin_id: str,
    spans: Mapping[str, tuple[float, float]],
    *,
    stamped_target: Optional[str],
    source: Any,
    client_device_id: Optional[str],
    is_locked: bool,
    job_id: Optional[str] = None,
    firestore_client: Any = None,
) -> dict[str, Optional[str]]:
    """Per-segment explicit targets; blocking (one bounded indexed query, sometimes two)."""
    if not spans:
        return {}
    try:
        try:
            started_before = datetime.fromtimestamp(
                max(end for _, end in spans.values()) + START_SKEW_SECONDS, tz=timezone.utc
            )
            rows, truncated_before, degraded = _load_lineage(
                uid, clean_text(origin_id), started_before, firestore_client
            )
            failed = False
        except Exception as exc:
            logger.warning('event=sync_lineage_lookup outcome=failed exception_type=%s', bounded_exception_class(exc))
            rows, truncated_before, degraded, failed = [], None, False, True
        plan = select_segment_targets(
            rows,
            origin_id,
            spans,
            stamped_target=stamped_target,
            source=source,
            client_device_id=client_device_id,
            is_locked=is_locked,
            truncated_before=truncated_before,
            lookup_failed=failed,
        )
    except Exception as exc:
        logger.warning('event=sync_lineage_plan outcome=failed exception_type=%s', bounded_exception_class(exc))
        plan = LineagePlan(
            targets={key: stamped_target for key in spans}, outcome='lookup_failed', reason='lookup_failed'
        )
        degraded = False
    if plan.outcome == 'lookup_failed' or degraded:
        plan.degraded = degraded
        record_fallback(
            component='other',
            from_mode='sync_lineage',
            to_mode='origin_row' if degraded else 'stamp' if stamped_target else 'temporal',
            reason='other',
            outcome='degraded',
        )
    _emit(plan, job_id)
    return plan.targets


def _emit(plan: LineagePlan, job_id: Optional[str]) -> None:
    """One bounded metric and log line per decision; never ids, uids or transcript text."""
    outcome = plan.outcome if plan.outcome in OUTCOMES else 'lookup_failed'
    try:
        OMI_SYNC_LINEAGE_RESOLVE_TOTAL.labels(outcome=outcome).inc()
    except Exception:
        pass
    counts = plan.counts
    logger.info(
        'event=sync_lineage_resolve outcome=%s reason=%s segments=%d bound=%d stamp_overridden=%d '
        'stamp_fallback=%d unbound=%d generations=%d rows=%d window=%s job_ref=%s',
        outcome,
        plan.reason,
        len(plan.targets),
        counts.get('bound', 0),
        counts.get('stamp_overridden', 0),
        counts.get('stamp_fallback', 0),
        counts.get('unbound', 0),
        plan.generations,
        plan.rows,
        'origin_row_only' if plan.degraded else 'lineage',
        bounded_correlation_ref(job_id),
    )
