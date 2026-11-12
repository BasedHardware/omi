"""Content-free summary debt metadata and post-commit receipts.

Presence means an overview or a rendered section body. Titles, actions and
calendar events alone never discharge the summary obligation.
"""

from __future__ import annotations

import math
import time
import os
from copy import deepcopy
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, cast
from utils.conversations import phase_shadow

from utils.observability.delivery import record_delivery

from prometheus_client import Counter, Gauge, Histogram
from config.refactor_modes import default_on
from config.summary_guarantee import deadline_seconds
from config.policy import FirstSummaryPolicy
from utils.conversations.minimum_derived import intentional_short_clip_minimum, waive_short_clip_summary_debt

Row = dict[str, Any]
PROJECTION_DEBT_ENV = 'SUMMARY_PROJECTION_DEBT_ENABLED'
MAX_EMPTY_REARMS = 2
EMPTY_BLOCKED_REASON = 'empty_output_exhausted'
EMPTY_LIFETIME_BLOCKED_REASON = 'empty_output_lifetime_exhausted'
EMPTY_BLOCKED_REASONS = frozenset({EMPTY_BLOCKED_REASON, EMPTY_LIFETIME_BLOCKED_REASON})

RECEIPTS = Counter(
    'omi_summary_terminal_total', 'Fenced durable summary outcomes', ['lane', 'reason', 'structured_present']
)
LATENCY = Histogram(
    'omi_accept_to_summary_seconds',
    'Acceptance to first durable summary',
    ['lane'],
    buckets=(30, 60, 120, 300, 600, 1800, 3600, 14400, 43200),
)
CLOSED_LATENCY = Histogram(
    'omi_closed_to_summary_seconds',
    'First durable summary after both server acceptance and last speech',
    ['lane'],
    buckets=(30, 60, 120, 180, 300, 600, 1800, 3600, 14400),
)
DEBT = Gauge('omi_summary_debt_overdue', 'Overdue summary debt in the bounded repair window')
OLDEST = Gauge('omi_summary_debt_oldest_age_seconds', 'Oldest overdue summary debt observed by repair')
SAMPLED_AT = Gauge('omi_summary_debt_sample_timestamp_seconds', "Timestamp of this replica's bounded debt sample")
EXPIRED_SEEN = Gauge('omi_summary_debt_expired_seen', 'Rows skipped as expired in the last claimed repair tick')
REPAIR = Counter('omi_summary_debt_repair_total', 'Summary debt repair tick outcomes', ['outcome'])
NEAR_EXPIRY_ADMITTED = Gauge(
    'omi_summary_debt_near_expiry_admitted', 'Successful urgent redrives in the last claimed repair tick'
)


PROCESS_CONTEXT: ContextVar[Row | None] = ContextVar('summary_process', default=None)
ACCEPT_CONTEXT: ContextVar[float | None] = ContextVar('summary_accept', default=None)
LANE_CONTEXT: ContextVar[str | None] = ContextVar('summary_lane', default=None)
REPAIR_CONTEXT: ContextVar[Row | None] = ContextVar('summary_repair', default=None)


def processing_fenced(existing: Row) -> bool:
    context = PROCESS_CONTEXT.get()
    return bool(context and context.get('claimed') and existing.get('summary_processing_owner') != context['owner'])


def repair_fenced(existing: Row) -> bool:
    context = REPAIR_CONTEXT.get()
    return context is not None and (
        refusal(existing) is not None
        or existing.get('sync_content_revision') != context.get('summary_expected_revision')
    )


class SummaryRepairSuperseded(RuntimeError):
    """A repair lost eligibility or its transcript generation; acknowledge its wake."""

    def __init__(self, message: str, *, retry_revision: int | None = None):
        super().__init__(message)
        self.retry_revision = retry_revision


class SummaryOutputUnavailable(RuntimeError):
    """A kept first-summary run returned no usable summary; retain its debt."""


def field(value: Any, name: str, default: Any = None) -> Any:
    return (
        cast(Mapping[str, Any], value).get(name, default)
        if isinstance(value, Mapping)
        else getattr(value, name, default)
    )


def present(structured: Any) -> bool:
    overview = field(structured, 'overview')
    if isinstance(overview, str) and overview.strip():
        return True
    for section in cast(list[Any], field(structured, 'sections', []) or []):
        body = field(section, 'body_markdown')
        if isinstance(body, str) and body.strip():
            return True
    return False


def rearm_on_revision_change(existing: Row, write: Row, *, now: float | None = None) -> None:
    """Recompute exhausted debt inside the transaction that advances transcript content.

    Use the pipeline's existing revision, not wall-clock updates or a replay of
    the same transcript. Keeping this transition with the content write also
    recovers exhausted rows created before this escape hatch existed. Two
    lifetime re-arms permit at most three three-call empty-output budgets.
    """
    revision = write.get('sync_content_revision')
    if (
        existing.get('summary_blocked_reason') != EMPTY_BLOCKED_REASON
        or not isinstance(revision, int)
        or revision <= (existing.get('sync_content_revision') or 0)
        or existing.get('summary_completed_at')
        or existing.get('summary_output_present')
    ):
        return
    rearms = existing.get('summary_empty_rearms', 0)
    if rearms >= MAX_EMPTY_REARMS:
        write.update(summary_blocked_reason=EMPTY_LIFETIME_BLOCKED_REASON, summary_due_at=None)
        return
    current = time.time() if now is None else now
    write.update(
        summary_blocked_reason=None,
        summary_empty_failures=0,
        summary_empty_rearms=rearms + 1,
        summary_due_at=current + deadline_seconds(),
    )


def prepare(data: Row, uid: str, *, now: float | None = None) -> None:
    """Called on plaintext inside the existing write codec: zero reads."""
    if 'structured' not in data:
        return
    current = time.time() if now is None else now
    structured = data['structured']
    data['summary_output_present'] = present(structured)
    if field(structured, 'title_provenance') == 'server_minimum' and not present(structured):
        data['summary_title_provenance'] = 'server_minimum'
        if intentional_short_clip_minimum(data):
            data['summary_due_at'] = None
            return
        if data.get('discarded'):
            # Intake discards owe no summary. Keep them out of the indexed debt
            # prefix, while allowing a later keep to start a fresh obligation.
            data['summary_due_at'] = None
            data['summary_discard_receipted'] = True
            return
        if data.get('summary_blocked_reason') in EMPTY_BLOCKED_REASONS:
            data['summary_due_at'] = None
            return
        if data.get('summary_discard_receipted') and not data.get('discarded'):
            # A later explicit keep/append starts a new obligation after discard.
            data['summary_first_pending_at'] = current
            data['summary_due_at'] = current + deadline_seconds()
            data['summary_discard_receipted'] = False
        data.setdefault('summary_first_pending_at', current)
        data.setdefault('summary_due_at', data['summary_first_pending_at'] + deadline_seconds())
        data.setdefault('summary_lane', lane(data))


def projection_debt_enabled() -> bool:
    """Default on; false restores the pre-fix behavior for batch projections."""
    return default_on(PROJECTION_DEBT_ENV)


def _past_age_gate(created_at: Any, *, now: float) -> bool:
    """Mirror ``utils.enrichment.age_gate.expired`` for the created-at clock.

    Importing ``age_gate`` here would pull its lazy parking import into the
    batch worker's static source closure, and that path reaches a testing-only
    module the worker image does not ship. The cutoff and config are the same.
    """
    from config import enrichment as enrichment_config

    try:
        hours = float(enrichment_config.max_age_hours())
        seconds = hours * 3600
        if hours < 0 or not math.isfinite(seconds):
            seconds = 72 * 3600
    except ValueError:
        seconds = 72 * 3600
    if seconds == 0:
        return False
    cutoff = now - seconds
    value = created_at
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.timestamp()
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            value = parsed.replace(tzinfo=timezone.utc).timestamp() if parsed.tzinfo is None else parsed.timestamp()
        except ValueError:
            return False
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
        and value < cutoff
    )


def stamp_projection_debt(write: Row, *, now: float | None = None) -> bool:
    """Stamp first-summary debt when a batch projection lands a transcript on an untitled row.

    A batch row that completes with no title never passes through the
    server-minimum intake path, so it carries no debt: Home hides it and the
    repair refuses it as ``unknown_provenance``. The projection is the only
    write that sees the transcript land, so it stamps the same obligation the
    intake minimum would have. Rows that already carry debt or a summary,
    curated rows, discards, below-floor clips, blocked rows and local-only rows
    are untouched.

    The stamp records the row-level ``summary_title_provenance`` only. It does
    not write ``structured.title_provenance``: ``is_server_minimum`` gates
    apps, goals, memories, folders and vectors, and a projection stamp must not
    suppress those effects on a later reprocess. Home reads the row-level
    provenance together with the debt clock.

    A row whose ``created_at`` is already past the repair age gate gets the
    provenance but no debt. That is an honest non-debt disposition: the repair
    never sees it, so it cannot park it one-way, and Home hides it instead of
    presenting "Writing notes" forever.
    """
    if not projection_debt_enabled():
        return False
    if write.get('status') != 'completed' or write.get('deleted') or write.get('discarded'):
        return False
    if write.get('terminal_no_derived_effects') or write.get('deferred'):
        return False
    if write.get('processing_state') == 'local_pending':
        return False
    if write.get('data_protection_level', 'enhanced') not in {'standard', 'enhanced'}:
        return False
    if write.get('user_title') is not None or write.get('user_overview') is not None:
        return False
    if write.get('summary_completed_at') or write.get('summary_output_present'):
        return False
    if write.get('summary_due_at') is not None or write.get('summary_first_pending_at') is not None:
        return False
    blocked = write.get('summary_blocked_reason')
    if blocked is not None:
        # Every non-empty block is terminal for this write, including the
        # below-floor, local-only and BYOK reasons that are not in the empty set.
        return False
    structured = write.get('structured')
    if structured is None:
        structured = {}
    elif not isinstance(structured, dict):
        # Preserve non-dict structured data; only a dict can carry provenance.
        return False
    if str(structured.get('title') or '').strip() or present(structured):
        return False
    current = time.time() if now is None else now
    # Evaluate the exact eligibility the repair will use, with the provenance
    # this stamp would add. The candidate keeps the write untouched on refusal.
    candidate = {
        **write,
        'structured': {**structured, 'title_provenance': 'server_minimum'},
        'summary_title_provenance': 'server_minimum',
    }
    if _refusal(candidate) is not None:
        return False
    write['summary_title_provenance'] = 'server_minimum'
    if _past_age_gate(write.get('created_at'), now=current):
        return False
    write['summary_first_pending_at'] = current
    write['summary_due_at'] = current + deadline_seconds()
    write.setdefault('summary_lane', lane(write))
    return True


def _refusal(row: Row) -> str | None:
    if row.get('status') != 'completed' or row.get('deleted') or row.get('discarded'):
        return 'lifecycle'
    if row.get('deferred') or row.get('is_locked') or row.get('processing_state') == 'local_pending':
        return 'local_only'
    if intentional_short_clip_minimum(row):
        return 'content_below_floor'
    if row.get('data_protection_level', 'enhanced') not in {'standard', 'enhanced'}:
        return 'privacy'
    if row.get('terminal_no_derived_effects') or row.get('client_processing'):
        return 'local_only'
    if row.get('user_title') is not None or row.get('user_overview') is not None:
        return 'manual'
    if row.get('summary_completed_at') or row.get('summary_output_present'):
        return 'already_enriched'
    if row.get('summary_blocked_reason') in EMPTY_BLOCKED_REASONS:
        return row['summary_blocked_reason']
    if row.get('summary_title_provenance') != 'server_minimum':
        return 'unknown_provenance'
    if row.get('finalization_job_id') or row.get('finalization_status') == 'blocked_byok':
        return 'generation_owned'
    return None


@phase_shadow.compare('summary_repair', accepts=lambda result: result is None)
def refusal(row: Row) -> str | None:
    return _refusal(row)


def rearm_after_refusal_clear(existing: Row, restored: Row) -> float | None:
    """Recover the original obligation inside the refusal-removal transaction.

    Never restart the deadline at undo time, replace an armed due, or enroll
    a row whose original acceptance is unknown or whose restored state refuses.
    """
    accepted = restored.get('summary_first_pending_at')
    if (
        existing.get('summary_due_at') is not None
        or refusal(restored) is not None
        or restored.get('summary_blocked_reason') == 'blocked_byok'
        or restored.get('finalization_status') in {'queued', 'leased'}
        or not isinstance(accepted, (int, float))
        or isinstance(accepted, bool)
        or not math.isfinite(accepted)
    ):
        return None
    policy = restored.get('first_summary_policy')
    deadline = (
        FirstSummaryPolicy.from_dict(policy).first_summary_deadline_seconds
        if policy is not None
        else deadline_seconds()
    )
    return accepted + deadline


def finalization_pending(row: Row, uid: str, job_id: str) -> bool:
    """The current finalization lease may finish its own completed minimum.

    Completed is a lifecycle state, not proof of summary delivery. Never bypass
    another generation through the background repair path; the finalizer has
    already checked its job/revision/lease before calling this predicate.
    """
    if (row.get('finalization_job_id') != job_id) or (present(row.get('structured'))):
        return False
    return refusal({**row, 'finalization_job_id': None}) is None


def creation_result(write: Row, uid: str) -> Row | None:
    # Intake minima owe summaries; audited short-clip floors intentionally waive that debt.
    if (
        write.get('summary_title_provenance') == 'server_minimum'
        and not write.get('summary_output_present')
        and not write.get('terminal_no_derived_effects')
        and write.get('processing_state') != 'local_pending'
        and not write.get('deferred')
        and not intentional_short_clip_minimum(write)
    ):
        return None
    return merge_result({}, write, uid)


def merge_result(existing: Row, write: Row, uid: str, *, now: float | None = None) -> Row | None:
    """Inside the existing revision-fenced transaction, before its write."""
    if 'summary_output_present' not in write:
        return None
    current = time.time() if now is None else now
    for name in ('summary_first_pending_at', 'summary_title_provenance', 'summary_completed_at', 'summary_due_at'):
        if name in existing:
            write[name] = existing[name]
    if write.get('status') != 'completed':
        return None
    if (
        intentional_short_clip_minimum(write)
        and not write.get('summary_output_present')
        and not existing.get('summary_completed_at')
    ):
        waive_short_clip_summary_debt(write, PROCESS_CONTEXT.get())
        return None
    if (
        write.get('terminal_no_derived_effects')
        or write.get('deferred')
        or write.get('processing_state') == 'local_pending'
    ):
        context = PROCESS_CONTEXT.get()
        if context is not None:
            context['blocked_reason'] = 'local_only'
        write['summary_due_at'] = None
        write['summary_blocked_reason'] = 'local_only'
        if existing.get('summary_blocked_reason') != 'local_only':
            return dict(lane=lane(existing), reason='local_only', present=False, latency=None)
        return None
    accepted = existing.get('summary_first_pending_at', ACCEPT_CONTEXT.get())
    if existing.get('summary_discard_receipted') and ACCEPT_CONTEXT.get() is not None:
        accepted = ACCEPT_CONTEXT.get()
    if accepted is None and isinstance(existing.get('processing_admitted_at'), datetime):
        accepted = existing['processing_admitted_at'].timestamp()
    if accepted is not None:
        write['summary_first_pending_at'] = accepted
    rich = bool(write.get('summary_output_present'))
    discarded = bool(write.get('discarded'))
    # The fence guards an open first-summary obligation only. Rows outside the
    # server-minimum protocol, already-enriched rows, and rows whose empty
    # budget is exhausted have no caller that catches this exception — the
    # sync outbox alone records empty-output strikes — so raising there
    # strands the completed write instead of retaining recoverable debt.
    obligation_open = (
        write.get('summary_title_provenance') == 'server_minimum'
        and not write.get('summary_completed_at')
        and not existing.get('summary_output_present')
        and existing.get('summary_blocked_reason') not in EMPTY_BLOCKED_REASONS
    )
    if not rich and not discarded and obligation_open:
        raise SummaryOutputUnavailable('kept first-summary output is empty')
    if existing.get('summary_completed_at') or existing.get('summary_output_present'):
        write['summary_due_at'] = None
        # An enriched row already holds a usable summary. The old fence refused
        # the whole write to protect it, which stranded completed results in
        # every lane without an outbox. Commit instead, but never let an empty
        # reprocess overwrite the banked summary: re-apply its content and
        # receipts onto this write so `merge=True` restores what the empty
        # structured payload would otherwise clobber.
        if not rich and not discarded:
            banked = existing.get('structured')
            if banked:
                # The caller re-applies manual edits onto the write before this
                # merge; restoring the banked content must not bury them.
                from database.conversations import effective_user_title

                restored = deepcopy(banked)
                user_title = effective_user_title(existing.get('user_title'))
                if user_title is not None:
                    restored['title'] = user_title
                if existing.get('user_overview'):
                    restored['overview'] = existing['user_overview']
                write['structured'] = restored
            write['summary_output_present'] = bool(banked) or bool(existing.get('summary_output_present'))
            write['summary_title_provenance'] = existing.get('summary_title_provenance') or 'generated'
            if existing.get('summary_completed_at') is not None:
                write['summary_completed_at'] = existing['summary_completed_at']
            write['summary_discard_receipted'] = existing.get('summary_discard_receipted', False)
            write['summary_processing_lease_until'] = 0
        return None
    if discarded and existing.get('summary_discard_receipted'):
        return None
    if rich or discarded:
        write['summary_due_at'] = None
        if rich:
            write['summary_completed_at'] = current
        write['summary_discard_receipted'] = discarded and not rich
        write['summary_processing_lease_until'] = 0
        write['summary_blocked_reason'] = None
        if rich:
            write['summary_title_provenance'] = 'generated'
        finished = write.get('finished_at', existing.get('finished_at'))
        closed_latency = None
        if accepted is not None and isinstance(finished, datetime) and finished.timestamp() <= current:
            closed_latency = max(0, current - max(accepted, finished.timestamp()))
        return dict(
            lane=lane(existing),
            reason=('discarded' if discarded else 'summary') if accepted is not None else 'accept_unknown',
            present=rich,
            latency=max(0, current - accepted) if accepted is not None else None,
            closed_latency=closed_latency,
        )
    return None


def lane(row: Row) -> str:
    value = LANE_CONTEXT.get() or row.get('summary_lane')
    if value in {'live', 'fresh', 'backfill', 'integration', 'batch'}:
        return value
    if os.getenv('BATCH_PIPELINE_WORKER_ENABLED', 'false').strip().lower() == 'true':
        return 'batch'
    service = os.getenv('K_SERVICE', '')
    if service == 'backend-integration':
        return 'integration'
    if service == 'backend-sync-backfill':
        return 'backfill'
    if service == 'backend-sync':
        return 'fresh'
    return 'live' if not service or service == 'backend' else 'unknown'


def emit(receipt: Row | None) -> None:
    if receipt is None:
        return
    RECEIPTS.labels(receipt['lane'], receipt['reason'], str(receipt['present']).lower()).inc()
    if receipt['present'] and receipt['latency'] is not None:
        LATENCY.labels(receipt['lane']).observe(receipt['latency'])
    if receipt['present'] and receipt.get('closed_latency') is not None:
        CLOSED_LATENCY.labels(receipt['lane']).observe(receipt['closed_latency'])


def emit_result(
    uid: str,
    changed: bool,
    receipt: Row | None,
    outcome: str | None,
    invalidate: Callable[[str], None],
    persisted: bool = True,
) -> None:
    """Preserve post-commit housekeeping and count only committed terminals."""
    if changed:
        invalidate(uid)
    if persisted:
        emit(receipt)
        if outcome is not None:
            record_delivery('summary', outcome)
