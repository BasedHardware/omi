"""Content-free summary debt metadata and post-commit receipts.

Presence means an overview or a rendered section body. Titles, actions and
calendar events alone never discharge the summary obligation.
"""

from __future__ import annotations

import time
import os
from copy import deepcopy
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Mapping, cast

from prometheus_client import Counter, Gauge, Histogram
from config.summary_guarantee import deadline_seconds, enabled

Row = dict[str, Any]

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


def prepare(data: Row, uid: str, *, now: float | None = None) -> None:
    """Called on plaintext inside the existing write codec: zero reads."""
    if not enabled(uid) or 'structured' not in data:
        return
    current = time.time() if now is None else now
    structured = data['structured']
    data['summary_output_present'] = present(structured)
    if field(structured, 'title_provenance') == 'server_minimum' and not present(structured):
        data['summary_title_provenance'] = 'server_minimum'
        if data.get('discarded'):
            # Intake discards owe no summary. Keep them out of the indexed debt
            # prefix, while allowing a later keep to start a fresh obligation.
            data['summary_due_at'] = None
            data['summary_discard_receipted'] = True
            return
        if data.get('summary_blocked_reason') == 'empty_output_exhausted':
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


def refusal(row: Row) -> str | None:
    if row.get('status') != 'completed' or row.get('deleted') or row.get('discarded'):
        return 'lifecycle'
    if row.get('deferred') or row.get('is_locked') or row.get('processing_state') == 'local_pending':
        return 'local_only'
    if row.get('data_protection_level', 'enhanced') not in {'standard', 'enhanced'}:
        return 'privacy'
    if row.get('terminal_no_derived_effects') or row.get('client_processing'):
        return 'local_only'
    if row.get('user_title') is not None or row.get('user_overview') is not None:
        return 'manual'
    if row.get('summary_completed_at') or row.get('summary_output_present'):
        return 'already_enriched'
    if row.get('summary_blocked_reason') == 'empty_output_exhausted':
        return 'empty_output_exhausted'
    if row.get('summary_title_provenance') != 'server_minimum':
        return 'unknown_provenance'
    if row.get('finalization_job_id') or row.get('finalization_status') == 'blocked_byok':
        return 'generation_owned'
    return None


def finalization_pending(row: Row, uid: str, job_id: str) -> bool:
    """The current finalization lease may finish its own completed minimum.

    Completed is a lifecycle state, not proof of summary delivery. Never bypass
    another generation through the background repair path; the finalizer has
    already checked its job/revision/lease before calling this predicate.
    """
    if not enabled(uid) or row.get('finalization_job_id') != job_id or present(row.get('structured')):
        return False
    return refusal({**row, 'finalization_job_id': None}) is None


def creation_result(write: Row, uid: str) -> Row | None:
    # A deliberate minimum is durable debt, not a terminal summary receipt.
    if (
        write.get('summary_title_provenance') == 'server_minimum'
        and not write.get('summary_output_present')
        and not write.get('terminal_no_derived_effects')
        and write.get('processing_state') != 'local_pending'
        and not write.get('deferred')
    ):
        return None
    return merge_result({}, write, uid)


def merge_result(existing: Row, write: Row, uid: str, *, now: float | None = None) -> Row | None:
    """Inside the existing revision-fenced transaction, before its write."""
    if not enabled(uid) or 'summary_output_present' not in write:
        return None
    current = time.time() if now is None else now
    for name in ('summary_first_pending_at', 'summary_title_provenance', 'summary_completed_at', 'summary_due_at'):
        if name in existing:
            write[name] = existing[name]
    if write.get('status') != 'completed':
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
        and existing.get('summary_blocked_reason') != 'empty_output_exhausted'
    )
    if not rich and not discarded and obligation_open:
        raise SummaryOutputUnavailable('kept first-summary output is empty')
    if existing.get('summary_completed_at'):
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
            write['summary_output_present'] = bool(banked)
            write['summary_title_provenance'] = existing.get('summary_title_provenance') or 'generated'
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
