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
in the lineage and canonicalize to their survivor. When several matches
canonicalize differently there is no reliable local clock ordering, so under
the safe-overlap gate the segment stays unbound with the ``ambiguous_pending``
token unless the phone's stamp names exactly one compatible canonical; without the
gate, or with no unique generation and no overlap, the segment keeps the
phone's stamp if it has one (the pre-#19424 behavior) and otherwise stays
unbound for temporal assignment, which never adopts live rows. A different
unique generation overrides the stamp.

The plan is a pure function of the lineage rows, the segment spans and the
stamp, so a retried job binds its remaining segments the same way against the
same rows. Any lookup or planning error fails open to that fallback; it never
fails the sync job by itself.
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from config.capture_evidence import capture_evidence_dark_write_enabled
from config.sync_lineage import (
    sync_lineage_resolve_enabled,
    sync_lineage_resolve_uid_allowed,
    sync_lineage_s1_required,
)
from config.sync_live_dedupe import sync_live_dedupe_active_for, sync_live_dedupe_enabled
from config.sync_telemetry import bounded_correlation_ref, bounded_exception_class
from utils.capture_evidence import parse_sync_file_claims
from utils.metrics import OMI_SYNC_LINEAGE_RESOLVE_TOTAL
from utils.observability.fallback import record_fallback
from utils.sync.lineage_diagnostics import classify_generation_row, probe_token
from utils.sync.lineage_intervals import pick_overlapping
from utils.sync.recording_session_target import (
    START_SKEW_SECONDS,
    TRAILING_AUDIO_SECONDS,
    clean_text,
    source_value,
    unix_seconds,
)

logger = logging.getLogger(__name__)


def _warning(message: str, *args: Any) -> None:
    try:
        logger.warning(message, *args)
    except Exception:
        pass


# Bound the potentially overlapping rows, rather than assuming older rows ended
# before newer ones started: stamp appends and smart merge can extend old rows.
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
    'not_allowlisted',
    's1_refused',
)

S1_REFUSAL_REASONS = ('no_claims', 'parse_failed', 'count_mismatch', 'filename_mismatch', 'not_admitted')


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
    filter_counts: dict[str, int] = field(default_factory=dict)
    binding_reasons: dict[str, str] = field(default_factory=dict)
    id_probe: str = 'not_run'


def _s1_claims_complete(capture_evidence_claims: Optional[Mapping], filenames: Sequence[str]) -> bool:
    """Complete validated S1 metadata for the exact uploaded basename set."""
    if (
        not capture_evidence_dark_write_enabled()
        or not isinstance(capture_evidence_claims, Mapping)
        or not capture_evidence_claims
        or not filenames
        or len(capture_evidence_claims) > 20
        or len(filenames) > 20
    ):
        return False
    try:
        payload = json.dumps(
            {'version': 1, 'files': [dict(claim, name=name) for name, claim in capture_evidence_claims.items()]}
        )
        parsed = parse_sync_file_claims(payload, filenames)
    except Exception:
        return False
    return len(parsed) == len(filenames) == len(capture_evidence_claims)


def _s1_refusal_reason(capture_evidence_claims: object, filenames: Sequence[str]) -> str:
    """Bounded reason for a false S1 gate; never raises and never leaks claim content.

    Claims rejected at the upload HTTP boundary arrive here as ``{}`` — the
    queued shape does not carry the earlier refusal, so those classify as
    ``no_claims`` rather than the original parse failure.
    """
    try:
        if not capture_evidence_dark_write_enabled():
            return 'not_admitted'
        if capture_evidence_claims is None:
            return 'no_claims'
        if not isinstance(capture_evidence_claims, Mapping):
            return 'parse_failed'
        if not capture_evidence_claims:
            return 'no_claims'
        for claim in capture_evidence_claims.values():
            if not isinstance(claim, Mapping):
                return 'parse_failed'
            try:
                uuid.UUID(str(claim['capture_root']))
                epoch, start, count, rate = (
                    claim[key] for key in ('clock_epoch', 'source_frame_start', 'frame_count', 'rate_hz')
                )
                if (
                    any(type(number) is not int or number < 0 for number in (epoch, start, count, rate))
                    or count == 0
                    or rate == 0
                    or claim['codec'] not in {'pcm16', 'opus'}
                    or claim.get('channel') != 'mono'
                ):
                    return 'parse_failed'
            except Exception:
                return 'parse_failed'
        try:
            claim_items = [dict(claim, name=name) for name, claim in capture_evidence_claims.items()]
        except Exception:
            return 'parse_failed'
        if not filenames or len(capture_evidence_claims) > 20 or len(filenames) > 20:
            return 'count_mismatch'
        if len(capture_evidence_claims) != len(filenames) or len(set(filenames)) != len(filenames):
            return 'count_mismatch'
        if set(capture_evidence_claims.keys()) != set(filenames):
            return 'filename_mismatch'
        try:
            payload = json.dumps({'version': 1, 'files': claim_items})
            if len(payload.encode('utf-8')) > 4096:
                return 'parse_failed'
        except Exception:
            return 'parse_failed'
        return 'parse_failed'
    except Exception:
        return 'parse_failed'


def emit_s1_refusal(reason: str) -> None:
    """One bounded s1_refused outcome per refused upload; no ids, names or claim content."""
    safe_reason = reason if reason in S1_REFUSAL_REASONS else 'parse_failed'
    _emit(LineagePlan(targets={}, outcome='s1_refused', reason=safe_reason), None, diagnostics=False)


def lineage_resolution_requested(
    uid: Optional[str],
    recording_session_id: Optional[str],
    audio_start_seconds: Optional[float],
    audio_end_seconds: Optional[float],
    *,
    job_id: Optional[str] = None,
    capture_evidence_claims: Optional[Mapping] = None,
    filenames: Sequence[str] = (),
) -> bool:
    """True when this upload binds per segment; otherwise records why for eligible uploads.

    Eligibility is exactly the population the whole-batch resolver serves:
    a recording id plus both audio bounds. The kill switch wins (``disabled``);
    with it on, a uid outside ``SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST`` records
    ``not_allowlisted`` and takes the same whole-batch path as the kill switch.
    That decision line carries no job reference, so it names no user or row.
    """
    if not recording_session_id or audio_start_seconds is None or audio_end_seconds is None:
        return False
    if not sync_lineage_resolve_enabled():
        _emit(
            LineagePlan(targets={}, outcome='disabled', reason='none'),
            job_id,
            diagnostics=sync_live_dedupe_active_for(uid),
        )
        return False
    if not sync_lineage_resolve_uid_allowed(uid):
        _emit(
            LineagePlan(targets={}, outcome='not_allowlisted', reason='none'),
            None,
            diagnostics=sync_live_dedupe_active_for(uid),
        )
        return False
    if sync_lineage_s1_required() and not _s1_claims_complete(capture_evidence_claims, filenames):
        emit_s1_refusal(_s1_refusal_reason(capture_evidence_claims, filenames))
        return False
    return True


# Durable refresh debt is distinct from permission to append more live content.
_PENDING_ENRICHMENT = 'lineage_enrichment_pending'


def merge_lineage_partial_results(*partials: dict) -> dict:
    keys = ('new_memories', 'updated_memories', 'fenced_conversation_ids', _PENDING_ENRICHMENT)
    result = {key: sorted({cid for partial in partials for cid in partial.get(key) or []}) for key in keys}
    if not result[_PENDING_ENRICHMENT]:
        result.pop(_PENDING_ENRICHMENT)
    return result


def restore_lineage_enrichment_intent(response: dict, partial: dict, requested: bool, language: str) -> None:
    pending = set(partial.get(_PENDING_ENRICHMENT) or []) & response['updated_memories']
    if requested:
        pending.update(response['updated_memories'])  # pre-marker admitted receipts
    if pending:
        response['_lineage_enrichment_pending'] = pending
    if requested or pending:
        response['_merged'] = {cid: language for cid in pending}


def lineage_partial_result(response: dict, active_for_uid: bool) -> dict:
    partial = {
        'new_memories': sorted(response['new_memories']),
        'updated_memories': sorted(response['updated_memories']),
        'fenced_conversation_ids': sorted(response['_fenced_conversation_ids']),
    }
    pending = set(response.get('_lineage_enrichment_pending') or [])
    if active_for_uid:
        pending.update(response.get('_merged') or {})
    pending &= response['updated_memories'] - response['_fenced_conversation_ids']
    if pending:
        partial[_PENDING_ENRICHMENT] = sorted(pending)
    return partial


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
    diagnostics: Optional[dict[str, int]] = None,
) -> list[_Generation]:
    """Provenance-compatible generations of ``origin_id`` with valid intervals.

    ``diagnostics`` receives truthful (uncapped) stage counts: the shared
    classifier's first exclusion per row, plus ``unstamped_origin`` for rows
    that predate the origin stamp but may still match through the legacy
    session id. Emission caps each count separately.
    """
    wanted_source = source_value(source)
    device_id = clean_text(client_device_id)
    redirects: dict[str, str] = {}
    candidates: list[tuple[str, float, float, bool]] = []
    for row in rows:
        row_id = clean_text(row.get('id'))
        reason = classify_generation_row(
            row,
            origin_id=origin_id,
            source=wanted_source,
            client_device_id=device_id,
            is_locked=bool(is_locked),
        )
        if diagnostics is not None:
            diagnostics['candidate_count_before'] = diagnostics.get('candidate_count_before', 0) + 1
            if reason is not None:
                diagnostics[reason] = diagnostics.get(reason, 0) + 1
            external = row.get('external_data')
            external = external if isinstance(external, Mapping) else {}
            if reason != 'dropped_invalid' and not clean_text(external.get('recording_origin_id')):
                diagnostics['unstamped_origin'] = diagnostics.get('unstamped_origin', 0) + 1
        if reason in ('dropped_invalid', 'dropped_unstamped', 'dropped_deleted'):
            continue
        redirect = clean_text(row.get('sync_merged_into'))
        if redirect:
            redirects[row_id] = redirect
        if reason is not None:
            continue
        start = unix_seconds(row.get('started_at'))
        end = unix_seconds(row.get('finished_at'))
        if start is None or end is None:
            continue
        candidates.append((row_id, start, end, bool(row.get('deleted'))))
    generations = [
        _Generation(row_id, start, end, _chain_end(row_id, redirects), deleted)
        for row_id, start, end, deleted in sorted(candidates)
    ]
    if diagnostics is not None:
        diagnostics['candidate_count_after'] = len(generations)
    return generations


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


def _bind(
    generations: list[_Generation],
    start: float,
    end: float,
    *,
    stamp: Optional[str] = None,
    safe_overlap: bool = False,
) -> tuple[Optional[str], bool]:
    """The explicit target, plus whether several distinct canonicals stayed undecidable."""
    strict = [g for g in generations if g.start <= start and end <= g.end]
    if strict:
        unique = _unique(strict)
        if unique is not None:
            return unique, False
        if not safe_overlap:
            return None, False
        pick = pick_overlapping(strict, stamp)
        return (_unique([pick]) if pick is not None else None), pick is None
    tolerant = [
        g
        for g in generations
        if start <= g.end
        and end >= g.start
        and start >= g.start - START_SKEW_SECONDS
        and end <= g.end + TRAILING_AUDIO_SECONDS
    ]
    if not tolerant:
        return None, False
    unique = _unique(tolerant)
    if unique is not None:
        return unique, False
    if not safe_overlap:
        return None, False
    pick = pick_overlapping(tolerant, stamp)
    return (_unique([pick]) if pick is not None else None), pick is None


def ambiguous_binding_pending(uid: Optional[str], binding: Optional[str]) -> bool:
    """The pending overlap token, live only where safe overlap handling is active."""
    return binding == 'ambiguous_pending' and sync_live_dedupe_active_for(uid)


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
    safe_overlap: Optional[bool] = None,
) -> LineagePlan:
    """Pure per-segment plan: unique generation or stamp-disambiguated overlap, else the stamp or unbound."""
    if safe_overlap is None:
        safe_overlap = sync_live_dedupe_enabled()
    filter_counts: dict[str, int] = {}
    generations = (
        []
        if lookup_failed
        else _generations(
            rows,
            clean_text(origin_id),
            source=source,
            client_device_id=client_device_id,
            is_locked=is_locked,
            diagnostics=filter_counts,
        )
    )
    canonical_by_id = {generation.id: generation.canonical for generation in generations}
    stamp = clean_text(stamped_target) or None
    stamp_canonical = canonical_by_id.get(stamp, stamp) if stamp else None
    targets: dict[str, Optional[str]] = {}
    counts = {'bound': 0, 'stamp_overridden': 0, 'stamp_fallback': 0, 'unbound': 0}
    binding_reasons: dict[str, str] = {}
    bound_canonicals: set[str] = set()
    misses: set[str] = set()
    for key in sorted(spans):
        start, end = spans[key]
        bound = None
        pending = False
        if lookup_failed:
            misses.add('lookup_failed')
        elif not math.isfinite(start) or not math.isfinite(end) or end <= start:
            # A failed WAV-duration read returns zero; a point is not proof
            # that the actual speech fits this generation.
            misses.add('interval_miss')
        elif not generations:
            misses.add('no_rows')
        elif truncated_before is not None:
            misses.add('truncated')
        else:
            bound, pending = _bind(generations, start, end, stamp=stamp, safe_overlap=safe_overlap)
            if bound is None:
                misses.add('ambiguous_overlap' if pending else 'interval_miss')
        if bound is not None:
            canonical = canonical_by_id.get(bound, bound)
            bound_canonicals.add(canonical)
            binding = 'stamp_overridden' if stamp and stamp_canonical != canonical else 'bound'
            counts[binding] += 1
            targets[key] = bound
        elif pending:
            counts['unbound'] += 1
            binding = 'ambiguous_pending'
            targets[key] = None
        else:
            binding = 'stamp_fallback' if stamp else 'unbound'
            counts[binding] += 1
            targets[key] = stamp
        binding_reasons[key] = binding
    reason = next(
        (
            item
            for item in ('lookup_failed', 'no_rows', 'truncated', 'ambiguous_overlap', 'interval_miss')
            if item in misses
        ),
        'none',
    )
    if lookup_failed:
        outcome = 'lookup_failed'
    elif len(bound_canonicals) > 1:
        outcome = 'split_across_generations'
    elif bound_canonicals:
        outcome = 'stamp_overridden' if counts['stamp_overridden'] else 'bound'
    elif 'ambiguous_overlap' in misses:
        outcome = 'interval_miss'
    else:
        outcome = 'stamp_fallback' if stamp else reason
    return LineagePlan(
        targets=targets,
        outcome=outcome,
        reason=reason,
        counts=counts,
        generations=len(bound_canonicals),
        rows=len(generations),
        filter_counts=filter_counts,
        binding_reasons=binding_reasons,
    )


def _load_lineage(
    uid: str,
    origin_id: str,
    started_before: datetime,
    firestore_client: Any,
    finished_after: datetime,
    *,
    on_module: Any = None,
    include_capture_evidence: bool = False,
) -> tuple[list[dict[str, Any]], Optional[float], bool]:
    """Lineage rows, an incomplete-overlap marker, and whether the lookup degraded."""
    # Import on use, like recording_session_target: pipeline.py loads this module
    # while unit harnesses stub google.cloud and the database package.
    from database import sync_recording_lineage as lineage_db

    if on_module is not None:
        on_module(lineage_db)

    projection = {'include_capture_evidence': True} if include_capture_evidence else {}
    degraded = False
    try:
        rows = lineage_db.get_recording_generations(
            uid,
            origin_id,
            started_before=started_before,
            finished_after=finished_after,
            limit=GENERATION_LIMIT,
            firestore_client=firestore_client,
            **projection,
        )
    except Exception as exc:
        # E.g. the composite index is still building: keep the origin-row read,
        # the same candidate set the whole-batch resolver has always used.
        _warning('event=sync_lineage_lookup outcome=degraded exception_type=%s', bounded_exception_class(exc))
        rows, degraded = [], True
    truncated_before = None
    if len(rows) > GENERATION_LIMIT:
        rows = rows[:GENERATION_LIMIT]
        # An unread row can overlap any segment, regardless of its start. Never
        # establish uniqueness from an incomplete overlap set.
        truncated_before = math.inf
    if truncated_before is None and not any(
        clean_text((row.get('external_data') or {}).get('recording_session_id')) == origin_id for row in rows
    ):
        # A recording that began before the origin stamp existed: only the row
        # bound to R itself is findable. A truncated overlap set already proves
        # no target, so another read cannot make that plan decidable.
        legacy = lineage_db.get_origin_generation(
            uid, origin_id, limit=ORIGIN_ROW_LIMIT, firestore_client=firestore_client, **projection
        )
        if len(legacy) > ORIGIN_ROW_LIMIT:
            return rows, math.inf, degraded
        known = {row.get('id') for row in rows}
        rows += [row for row in legacy if row.get('id') not in known]
    return rows, truncated_before, degraded


def load_lineage(
    uid: str,
    origin_id: str,
    started_before: datetime,
    firestore_client: Any,
    finished_after: datetime,
    *,
    include_capture_evidence: bool = False,
) -> tuple[list[dict[str, Any]], Optional[float], bool]:
    """Public read seam for consumers of the bounded lineage lookup (e.g. WAL audio coverage)."""
    return _load_lineage(
        uid,
        origin_id,
        started_before,
        firestore_client,
        finished_after,
        include_capture_evidence=include_capture_evidence,
    )


def _id_probe(
    lineage_db: Any,
    uid: str,
    origin_id: str,
    *,
    source: Any,
    client_device_id: Optional[str],
    is_locked: bool,
    firestore_client: Any,
) -> str:
    """One metadata-only read of the document whose id is the recording origin.

    Diagnostic only: the token explains the observable state of that row; it
    never becomes a target and never changes the plan's outcome.
    """
    try:
        row = lineage_db.get_recording_id_probe(uid, origin_id, firestore_client=firestore_client)
    except Exception as exc:
        _warning('event=sync_lineage_probe outcome=failed exception_type=%s', bounded_exception_class(exc))
        return 'lookup_failed'
    return probe_token(
        row,
        origin_id=clean_text(origin_id),
        source=source_value(source),
        client_device_id=clean_text(client_device_id),
        is_locked=bool(is_locked),
    )


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
    binding_reasons: Optional[dict] = None,
) -> dict[str, Optional[str]]:
    """Per-segment explicit targets; blocking (one bounded indexed query, sometimes two)."""
    if not spans:
        return {}
    truncated_before: Optional[float] = None
    failed = True
    lineage_module: list = []
    try:
        try:
            started_before = datetime.fromtimestamp(
                max(end for _, end in spans.values()) + START_SKEW_SECONDS, tz=timezone.utc
            )
            finished_after = datetime.fromtimestamp(min(start for start, _ in spans.values()), tz=timezone.utc)
            rows, truncated_before, degraded = _load_lineage(
                uid,
                clean_text(origin_id),
                started_before,
                firestore_client,
                finished_after,
                on_module=lineage_module.append,
            )
            failed = False
        except Exception as exc:
            _warning('event=sync_lineage_lookup outcome=failed exception_type=%s', bounded_exception_class(exc))
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
            safe_overlap=sync_live_dedupe_active_for(uid),
        )
    except Exception as exc:
        _warning('event=sync_lineage_plan outcome=failed exception_type=%s', bounded_exception_class(exc))
        plan = LineagePlan(
            targets={key: stamped_target for key in spans}, outcome='lookup_failed', reason='lookup_failed'
        )
        degraded = False
    if binding_reasons is not None:
        binding_reasons.update(
            plan.binding_reasons or {key: 'stamp_fallback' if stamped_target else 'unbound' for key in spans}
        )
    if (
        lineage_module
        and not failed
        and plan.outcome != 'lookup_failed'
        and not degraded
        and truncated_before is None
        and plan.rows == 0
        and clean_text(origin_id)
        and sync_live_dedupe_active_for(uid)
    ):
        plan.id_probe = _id_probe(
            lineage_module[0],
            uid,
            origin_id,
            source=source,
            client_device_id=client_device_id,
            is_locked=is_locked,
            firestore_client=firestore_client,
        )
    if plan.outcome == 'lookup_failed' or degraded:
        plan.degraded = degraded
        record_fallback(
            component='other',
            from_mode='sync_lineage',
            to_mode='origin_row' if degraded else 'stamp' if stamped_target else 'temporal',
            reason='other',
            outcome='degraded',
        )
    _emit(plan, job_id, diagnostics=sync_live_dedupe_active_for(uid))
    return plan.targets


def plan_segment_targets(
    segment_list: Sequence[str],
    timestamp_of: Any,
    duration_of: Any,
    uid: str,
    origin_id: str,
    stamped_target: Optional[str],
    source: Any,
    client_device_id: Optional[str],
    is_locked: bool,
    job_id: Optional[str],
    binding_reasons: Optional[dict],
) -> dict[str, Optional[str]]:
    """Blocking span construction plus per-segment lineage resolution for one upload.

    ``timestamp_of``/``duration_of`` are the caller's WAV clock functions; the
    ``binding_reasons`` dict collects each segment's binding token. A segment
    left ``ambiguous_pending`` gets up to three local rechecks against a fresh
    lineage read — newly visible metadata can decide it — then keeps the token
    for the existing failed-segment/re-upload path. A key proven pending in any
    pass keeps the token unless a later pass binds it; a degraded or ordinary
    miss cannot silently revert it to the stamp or temporal path.
    """
    spans = {path: (timestamp_of(path), timestamp_of(path) + duration_of(path)) for path in segment_list}
    proven_pending: set = set()
    pass_reasons: dict = {}
    targets: dict = {}
    for _attempt in range(3):
        pass_reasons = {}
        targets = resolve_segment_targets(
            uid,
            origin_id,
            spans,
            stamped_target=stamped_target,
            source=source,
            client_device_id=client_device_id,
            is_locked=is_locked,
            job_id=job_id,
            binding_reasons=pass_reasons,
        )
        proven_pending |= {key for key, token in pass_reasons.items() if token == 'ambiguous_pending'}
        if 'ambiguous_pending' not in pass_reasons.values():
            break
    for key in proven_pending:
        if pass_reasons.get(key) not in ('bound', 'stamp_overridden'):
            targets[key] = None
            pass_reasons[key] = 'ambiguous_pending'
    if binding_reasons is not None:
        binding_reasons.clear()
        binding_reasons.update(pass_reasons)
    return targets


def fallback_segment_targets(
    keys: Sequence[str],
    stamped_target: Optional[str],
    *,
    job_id: Optional[str] = None,
    binding_reasons: Optional[dict] = None,
) -> dict[str, Optional[str]]:
    """Fail-open at the coordinator boundary, including span/executor failures."""
    plan = LineagePlan(
        targets={key: stamped_target for key in keys},
        outcome='lookup_failed',
        reason='lookup_failed',
        counts={'stamp_fallback' if stamped_target else 'unbound': len(keys)},
        binding_reasons={key: 'stamp_fallback' if stamped_target else 'unbound' for key in keys},
    )
    if binding_reasons is not None:
        binding_reasons.update(plan.binding_reasons)
    record_fallback(
        component='other',
        from_mode='sync_lineage',
        to_mode='stamp' if stamped_target else 'temporal',
        reason='other',
        outcome='degraded',
    )
    _emit(plan, job_id)
    return plan.targets


def _emit(plan: LineagePlan, job_id: Optional[str], diagnostics: Optional[bool] = None) -> None:
    """One bounded metric and log line per decision; never ids, uids or transcript text."""
    if diagnostics is None:
        diagnostics = sync_live_dedupe_enabled()
    outcome = plan.outcome if plan.outcome in OUTCOMES else 'lookup_failed'
    try:
        OMI_SYNC_LINEAGE_RESOLVE_TOTAL.labels(outcome=outcome).inc()
    except Exception:
        pass
    counts = plan.counts
    if not diagnostics:
        try:
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
        except Exception:
            pass
        return
    filters = plan.filter_counts
    emitted = lambda key: min(filters.get(key, 0), 16)
    try:
        logger.info(
            'event=sync_lineage_resolve outcome=%s reason=%s segments=%d bound=%d stamp_overridden=%d '
            'stamp_fallback=%d unbound=%d generations=%d rows=%d window=%s candidates=%d accepted=%d '
            'dropped_invalid=%d dropped_unstamped=%d dropped_deleted=%d dropped_source=%d '
            'dropped_device=%d dropped_lock=%d dropped_interval=%d unstamped_origin=%d id_probe=%s '
            'job_ref=%s',
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
            emitted('candidate_count_before'),
            emitted('candidate_count_after'),
            emitted('dropped_invalid'),
            emitted('dropped_unstamped'),
            emitted('dropped_deleted'),
            emitted('dropped_source'),
            emitted('dropped_device'),
            emitted('dropped_lock'),
            emitted('dropped_interval'),
            emitted('unstamped_origin'),
            plan.id_probe,
            bounded_correlation_ref(job_id),
        )
    except Exception:
        pass
