"""Single-pass, snapshot-cursor conversation reader for bounded scans.

People stats and speaker browsing walk the newest conversations. The retired
``fetch_page(limit, offset)`` contract made each page restart an unbounded
scan at the newest row and skip already-returned rows in Python, so a ten-page
scan re-read the same prefix ten times (5,500 documents for 1,000 visible
rows) and timed the People list out. ``iter_conversations`` instead streams
one bounded, newest-first pass: every page query carries a server-side
``limit``, pagination advances by ``start_after`` on the last raw snapshot —
never ``offset`` — and the caller's ``ListReadBudget`` bounds both raw
documents and wall-clock, so an exhausted budget returns the honest prefix
plus truncation state instead of hanging the request.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Iterator, Optional, Sequence

from google.api_core import exceptions as api_exceptions
from google.api_core import retry as api_retry
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import get_firestore_client
from .conversations import (
    document_data_with_revision,
    is_visible_conversation,
    prepare_conversation_for_read,
)
from utils.observability.fallback import record_fallback
from utils.people_stats import PEOPLE_STATS_SCAN_CAP
from utils.other.list_budget import (
    ListReadBudget,
    ListReadBudgetExhausted,
    budgeted_stream_iter,
    list_read_budget_for_request,
    resolve_list_read_budget_seconds,
    resolve_list_read_max_documents,
)

logger = logging.getLogger(__name__)

# Per-scan ceilings; an existing request budget only ever lowers them.
# The time ceiling is set from production: on the paged reader this scan
# replaced, People stats requests had p90 near 12 s and p99 near 20 s and all of
# them completed. 20 s keeps every one of those complete while staying inside
# the 30 s request deadline. Lower it once this reader's latency is measured.
CONVERSATION_SCAN_MAX_DOCUMENTS = 2000
CONVERSATION_SCAN_SECONDS = 20.0

# The speaker-browse recipe reads up to 1,000 visible rows in 50-row pages.
SPEAKER_BROWSE_SCAN_CAP = 1000
SPEAKER_BROWSE_BATCH = 50

# The People-stats recipe pages the projected scan in 100-row reads.
PEOPLE_STATS_BATCH = 100

# Fields the People-stats scan reads: visibility predicates (discarded,
# deleted), the lock gate, both transcript encodings plus their protection
# level, and the manual speaker-assignment receipt that rewrites person labels
# at read time. Anything else (title, structured) never reaches the aggregator.
PEOPLE_STATS_FIELD_PATHS = (
    'id',
    'is_locked',
    'discarded',
    'deleted',
    'started_at',
    'created_at',
    'transcript_segments',
    'transcript_segments_compressed',
    'data_protection_level',
    'manual_speaker_assignments',
    'manual_speaker_assignments_compressed',
)


def conversation_scan_budget(request: Any, *, route: str) -> ListReadBudget:
    """The request-scoped scan budget, anchored at the middleware start stamp."""
    return list_read_budget_for_request(
        request,
        route=route,
        seconds=min(CONVERSATION_SCAN_SECONDS, resolve_list_read_budget_seconds()),
        max_documents=min(CONVERSATION_SCAN_MAX_DOCUMENTS, resolve_list_read_max_documents()),
    )


def _scan_retry(budget: ListReadBudget) -> api_retry.Retry:
    """Retry transient transport failures inside the budget, never a deadline.

    Firestore's default query retry also retries ``DeadlineExceeded``, which
    would restart the budget-derived timeout instead of ending the scan. No
    retry at all would turn one transient ``UNAVAILABLE`` into a 500.
    """
    return api_retry.Retry(
        predicate=api_retry.if_exception_type(
            api_exceptions.InternalServerError,
            api_exceptions.ResourceExhausted,
            api_exceptions.ServiceUnavailable,
        ),
        initial=0.1,
        maximum=1.0,
        multiplier=1.3,
        timeout=max(budget.remaining_seconds, 0.0),
    )


def _record_scan_truncation() -> None:
    record_fallback(
        component='firestore_read',
        from_mode='conversation_scan',
        to_mode='truncated_prefix',
        reason='capacity_full',
        outcome='degraded',
        log=logger,
    )


def iter_conversations(
    uid: str,
    *,
    limit: int = 1000,
    batch: int = 100,
    include_discarded: bool = False,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    field_paths: Optional[Sequence[str]] = None,
    budget: ListReadBudget,
    firestore_client: Any = None,
) -> Iterator[Dict[str, Any]]:
    """Yield visible conversations newest-first as one bounded single pass.

    Pages advance by ``start_after`` on the last raw snapshot — invisible rows
    advance the cursor too, so tombstones inside a window cannot end the scan
    early. ``limit`` counts visible (yielded) rows. Iteration stops at the
    visible target, end of data, or budget exhaustion; exhaustion leaves the
    prefix yielded so far and marks ``budget.truncated``.
    """
    if limit < 0:
        raise ValueError('limit must be >= 0')
    if batch <= 0:
        raise ValueError('batch must be > 0')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    base_query = client.collection('users').document(uid).collection('conversations')
    if not include_discarded:
        base_query = base_query.where(filter=FieldFilter('discarded', '==', False))
    if start_date is not None:
        base_query = base_query.where(filter=FieldFilter('created_at', '>=', start_date))
    if end_date is not None:
        base_query = base_query.where(filter=FieldFilter('created_at', '<=', end_date))
    base_query = base_query.order_by('created_at', direction=firestore.Query.DESCENDING)
    if field_paths is not None:
        base_query = base_query.select(field_paths)

    def _scan() -> Iterator[Dict[str, Any]]:
        visible = 0
        last_snapshot: Any = None
        stream: Any = None
        try:
            while visible < limit:
                budget.check()
                remaining_documents = budget.remaining_documents
                if remaining_documents <= 0:
                    budget.mark_exhausted('documents')
                    _record_scan_truncation()
                    return
                page_limit = min(batch, limit - visible, remaining_documents)
                page_query = base_query
                if last_snapshot is not None:
                    page_query = page_query.start_after(last_snapshot)
                page_query = page_query.limit(page_limit)
                stream = budgeted_stream_iter(page_query, budget, retry=_scan_retry(budget))
                page_rows = 0
                try:
                    for snapshot in stream:
                        page_rows += 1
                        last_snapshot = snapshot
                        raw = document_data_with_revision(snapshot)
                        if raw is None or not is_visible_conversation(raw, include_discarded=include_discarded):
                            continue
                        budget.check()
                        prepared = prepare_conversation_for_read(raw, uid)
                        if prepared is None:
                            continue
                        # Decode already consumed budget time: a row prepared past
                        # the deadline must not ship.
                        budget.check()
                        visible += 1
                        yield prepared
                        budget.check()
                finally:
                    close = getattr(stream, 'close', None)
                    if callable(close):
                        close()
                if page_rows < page_limit:
                    return
        except ListReadBudgetExhausted as exc:
            budget.mark_exhausted(exc.reason)
            _record_scan_truncation()
            return

    return _scan()


def people_stats_scan(
    uid: str,
    *,
    budget: ListReadBudget,
    firestore_client: Any = None,
) -> Iterator[Dict[str, Any]]:
    """The People-stats recipe: the projection below over the shared reader."""
    return iter_conversations(
        uid,
        limit=PEOPLE_STATS_SCAN_CAP,
        batch=PEOPLE_STATS_BATCH,
        field_paths=PEOPLE_STATS_FIELD_PATHS,
        budget=budget,
        firestore_client=firestore_client,
    )


def speaker_browse_scan(
    uid: str,
    *,
    include_discarded: bool = False,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    budget: ListReadBudget,
    firestore_client: Any = None,
) -> Iterator[Dict[str, Any]]:
    """The speaker-browse recipe over the shared reader at its fixed cap/page shape."""
    return iter_conversations(
        uid,
        limit=SPEAKER_BROWSE_SCAN_CAP,
        batch=SPEAKER_BROWSE_BATCH,
        include_discarded=include_discarded,
        start_date=start_date,
        end_date=end_date,
        budget=budget,
        firestore_client=firestore_client,
    )
