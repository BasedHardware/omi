"""Request-scoped budget for bounded list GET reads.

GET /v1/action-items, GET /v1/conversations, and GET /v3/memories can each
drive aggregate Firestore work that outlives the edge request budget
(``HTTP_GET_TIMEOUT``, 30s in prod) and come back as a bare middleware 504
(#11831). A :class:`ListReadBudget` is created once per request at the route
and threaded through the route's read path. It owns:

* a monotonic wall-clock deadline derived from the request start (leaving
  headroom under the middleware cutoff for response serialization),
* a remaining document allowance charged with every row that actually
  crosses the wire (including rows a Firestore ``offset()`` skips and rows a
  scan walks past without emitting),
* aggregate counters for telemetry (route, documents scanned, elapsed), and
* a typed exhaustion outcome (:class:`ListReadBudgetExhausted`).

Route adapters keep their query/pagination semantics; this module never
builds queries or response shapes. Exhaustion must map to the route's
explicit truncated outcome (``X-Omi-List-Truncated`` response header, plus
the optional ``truncated`` field on ``ActionItemsResponse``) — never to a
silent partial page that looks complete, and never to a catch-all handler
for unrelated exceptions. Only deadline exceptions raised by calls that were
given a budget-derived timeout are converted here; every other error keeps
its existing status.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Iterable, List, Optional

try:  # google-api_core ships with google-cloud-firestore
    from google.api_core.exceptions import DeadlineExceeded as _FirestoreDeadlineExceeded  # type: ignore[assignment]
except ImportError:  # pragma: no cover - defensive, the dependency is pinned

    class _FirestoreDeadlineExceeded(Exception):  # type: ignore[no-redef]
        """Fallback when google-api-core is unavailable."""


# Response header set on the three list routes when the read was cut short by
# the budget. Conversations and memories return bare arrays — the wire body
# cannot grow an envelope without breaking released clients — so the header is
# the truncation surface for those routes.
OMI_LIST_TRUNCATED_HEADER = 'X-Omi-List-Truncated'
# Response-header value. String (not bool) so intermediate proxies keep it verbatim.
OMI_LIST_TRUNCATED_VALUE = 'true'

# Middleware state key stamped by TimeoutMiddleware at request start so the
# internal deadline accounts for time spent before the route handler ran
# (auth, middleware chain) instead of restarting the clock mid-request.
REQUEST_STARTED_MONOTONIC_STATE_KEY = 'omi_request_started_monotonic'

# Serialization headroom kept between the internal read deadline and the
# middleware's hard cutoff: the response for a full 500–1000 item page must
# still serialize and flush after the last Firestore RPC returns.
LIST_READ_SERIALIZATION_HEADROOM_SECONDS = 6.0
# Internal read deadline used when HTTP_GET_TIMEOUT is not configured (the
# middleware then falls back to a 120s default; 24s stays safely inside it).
LIST_READ_DEFAULT_BUDGET_SECONDS = 24.0
# Aggregate document allowance across every query, window, and fallback in one
# request. Primary bound is the deadline; this stops pathological doc churn
# (re-scanned expansion windows, huge offsets) from billing unbounded reads.
LIST_READ_DEFAULT_MAX_DOCUMENTS = 25_000
# Do not start an RPC that cannot possibly finish before the deadline.
LIST_READ_MIN_RPC_SECONDS = 0.05

BudgetExhaustionReason = str  # 'deadline' | 'documents'


def _env_float(name: str) -> Optional[float]:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _env_int(name: str) -> Optional[int]:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def resolve_list_read_budget_seconds() -> float:
    """Internal read deadline for one list request.

    ``OMI_LIST_READ_BUDGET_SECONDS`` wins outright (tests and operators).
    Otherwise derive from the middleware's GET cutoff minus the serialization
    headroom, capped at the default.
    """
    override = _env_float('OMI_LIST_READ_BUDGET_SECONDS')
    if override is not None:
        return max(0.0, override)
    http_get = _env_float('HTTP_GET_TIMEOUT')
    if http_get is not None and http_get > 0:
        return min(LIST_READ_DEFAULT_BUDGET_SECONDS, max(1.0, http_get - LIST_READ_SERIALIZATION_HEADROOM_SECONDS))
    return LIST_READ_DEFAULT_BUDGET_SECONDS


def resolve_list_read_max_documents() -> int:
    override = _env_int('OMI_LIST_READ_MAX_DOCUMENTS')
    if override is not None and override > 0:
        return override
    return LIST_READ_DEFAULT_MAX_DOCUMENTS


class ListReadBudgetExhausted(Exception):
    """The request's list-read budget ran out; the read must return truncated.

    Distinct from every other exception on purpose: only deadline exceptions
    raised by RPCs that were given a budget-derived timeout (and document
    allowances charged here) produce it. Firestore/auth/validation failures
    never become truncation.
    """

    def __init__(self, reason: BudgetExhaustionReason):
        super().__init__(f"list read budget exhausted: {reason}")
        self.reason = reason


class ListReadBudget:
    """One request's wall-clock and document allowance for list reads."""

    def __init__(
        self,
        *,
        deadline_monotonic: float,
        max_documents: int = LIST_READ_DEFAULT_MAX_DOCUMENTS,
        route: str = '',
        clock: Callable[[], float] = time.monotonic,
        started_monotonic: Optional[float] = None,
    ) -> None:
        self.route = route
        self._deadline = float(deadline_monotonic)
        self._started = float(started_monotonic if started_monotonic is not None else deadline_monotonic)
        self._remaining_documents = int(max_documents)
        self._max_documents = int(max_documents)
        self._clock = clock
        # First exhaustion reason wins; a read that already reported truncation
        # stays truncated.
        self._exhaustion: Optional[BudgetExhaustionReason] = None
        # Aggregate counters (telemetry only — never user-identifying).
        self.docs_scanned = 0

    @classmethod
    def for_request(
        cls,
        request: Any,
        *,
        route: str,
        seconds: Optional[float] = None,
        max_documents: Optional[int] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> "ListReadBudget":
        """Build the route's budget from the middleware-stamped request start."""
        started = None
        state = getattr(request, 'state', None)
        if state is not None:
            started = getattr(state, REQUEST_STARTED_MONOTONIC_STATE_KEY, None)
        now = clock()
        if started is None or float(started) > now:
            # Direct handler calls (tests) have no middleware stamp.
            started = now
        budget_seconds = resolve_list_read_budget_seconds() if seconds is None else max(0.0, float(seconds))
        docs = resolve_list_read_max_documents() if max_documents is None else int(max_documents)
        return cls(
            deadline_monotonic=float(started) + budget_seconds,
            max_documents=docs,
            route=route,
            clock=clock,
            started_monotonic=float(started),
        )

    # -- inspection ---------------------------------------------------------

    @property
    def truncated(self) -> bool:
        """True once any charge or deadline check exhausted this budget."""
        return self._exhaustion is not None

    @property
    def exhaustion_reason(self) -> Optional[BudgetExhaustionReason]:
        return self._exhaustion

    @property
    def remaining_seconds(self) -> float:
        return self._deadline - self._clock()

    @property
    def remaining_documents(self) -> int:
        return max(0, self._remaining_documents)

    @property
    def max_documents(self) -> int:
        return self._max_documents

    # -- accounting ---------------------------------------------------------

    def mark_exhausted(self, reason: BudgetExhaustionReason) -> None:
        """Flag truncation without raising; partial results still ship."""
        if self._exhaustion is None:
            self._exhaustion = reason

    def check(self) -> None:
        """Raise :class:`ListReadBudgetExhausted` if the budget is spent."""
        if self._exhaustion is not None:
            raise ListReadBudgetExhausted(self._exhaustion)
        if self._remaining_documents < 0:
            self._exhaustion = 'documents'
            raise ListReadBudgetExhausted('documents')
        if self._clock() >= self._deadline:
            self._exhaustion = 'deadline'
            raise ListReadBudgetExhausted('deadline')

    def charge(self, documents: int = 1) -> None:
        """Charge rows that crossed the wire (emitted, suppressed, or skipped)."""
        if documents <= 0:
            self.check()
            return
        self.docs_scanned += int(documents)
        self._remaining_documents -= int(documents)
        self.check()

    # -- Firestore plumbing --------------------------------------------------

    def rpc_timeout(self) -> float:
        """Per-RPC timeout so a blocked call surfaces at the internal deadline.

        The middleware's hard cutoff stays the outer bound; this value makes
        the Firestore client itself raise ``DeadlineExceeded`` a headroom
        before that, which callers map to the truncated outcome.
        """
        remaining = self.remaining_seconds
        if remaining <= LIST_READ_MIN_RPC_SECONDS:
            self._exhaustion = 'deadline'
            raise ListReadBudgetExhausted('deadline')
        return remaining

    # -- telemetry -----------------------------------------------------------

    def observe(self, outcome: str) -> None:
        """Record route, documents scanned, and elapsed for this read.

        Labels carry only the route and outcome — never uid, query, payload,
        or raw URL fragments.
        """
        from utils.metrics import LIST_READ_DOCUMENTS_TOTAL, LIST_READ_REQUEST_TOTAL, LIST_READ_SECONDS

        if not self.route:
            return
        elapsed = max(0.0, self._clock() - self._started)
        LIST_READ_REQUEST_TOTAL.labels(route=self.route, outcome=outcome).inc()
        LIST_READ_DOCUMENTS_TOTAL.labels(route=self.route).inc(self.docs_scanned)
        LIST_READ_SECONDS.labels(route=self.route).observe(elapsed)


def list_read_budget_for_request(
    request: Any,
    *,
    route: str,
    seconds: Optional[float] = None,
    max_documents: Optional[int] = None,
    clock: Callable[[], float] = time.monotonic,
) -> ListReadBudget:
    """Route-facing factory: the one budget shared by a list GET's reads."""
    return ListReadBudget.for_request(
        request,
        route=route,
        seconds=seconds,
        max_documents=max_documents,
        clock=clock,
    )


def budgeted_stream_list(query: Any, budget: Optional[ListReadBudget]) -> List[Any]:
    """Materialize ``query.stream()`` under the budget.

    With a budget the stream gets the derived per-RPC timeout, its documents
    are charged, and a deadline exception from that call becomes the typed
    exhaustion. Without a budget the call is unchanged (legacy callers and
    pre-budget test fakes).
    """
    if budget is None:
        return list(query.stream())
    timeout = budget.rpc_timeout()
    try:
        iterator = query.stream(timeout=timeout)
    except TypeError:
        # Test fakes predating the budget seam do not accept a timeout kwarg;
        # the deadline still bites on the next charge/check.
        iterator = query.stream()
    try:
        docs = list(iterator)
    except _FirestoreDeadlineExceeded as exc:
        budget.mark_exhausted('deadline')
        raise ListReadBudgetExhausted('deadline') from exc
    budget.charge(len(docs))
    return docs


def budgeted_get_all(client: Any, refs: Iterable[Any], budget: Optional[ListReadBudget]) -> List[Any]:
    """Materialize ``client.get_all(refs)`` under the budget."""
    ref_list = list(refs)
    if budget is None:
        return list(client.get_all(ref_list))
    timeout = budget.rpc_timeout()
    try:
        snapshots = list(client.get_all(ref_list, timeout=timeout))
    except TypeError:
        snapshots = list(client.get_all(ref_list))
    except _FirestoreDeadlineExceeded as exc:
        budget.mark_exhausted('deadline')
        raise ListReadBudgetExhausted('deadline') from exc
    budget.charge(len(snapshots))
    return snapshots


def budgeted_document_get(reference: Any, budget: Optional[ListReadBudget]) -> Any:
    """``reference.get()`` under the budget."""
    if budget is None:
        return reference.get()
    timeout = budget.rpc_timeout()
    try:
        snapshot = reference.get(timeout=timeout)
    except TypeError:
        snapshot = reference.get()
    except _FirestoreDeadlineExceeded as exc:
        budget.mark_exhausted('deadline')
        raise ListReadBudgetExhausted('deadline') from exc
    if getattr(snapshot, 'exists', False):
        budget.charge(1)
    return snapshot


def budgeted_stream_iter(query: Any, budget: Optional[ListReadBudget]) -> Iterable[Any]:
    """Iterate ``query.stream()`` lazily under the budget, charging per row.

    Unlike :func:`budgeted_stream_list` the rows fetched before exhaustion are
    still yielded to the caller, so a page cut mid-stream can keep its honest
    prefix. Deadline exceptions from the budget-derived RPC timeout become the
    typed exhaustion after the partial rows have been produced.
    """
    if budget is None:
        yield from query.stream()
        return
    timeout = budget.rpc_timeout()
    try:
        iterator = query.stream(timeout=timeout)
    except TypeError:
        # Test fakes predating the budget seam do not accept a timeout kwarg.
        iterator = query.stream()
    while True:
        try:
            doc = next(iterator)
        except StopIteration:
            return
        except _FirestoreDeadlineExceeded as exc:
            budget.mark_exhausted('deadline')
            raise ListReadBudgetExhausted('deadline') from exc
        budget.charge(1)
        yield doc


def apply_truncation_header(headers: Any, budget: Optional[ListReadBudget]) -> None:
    """Set the documented truncation header on a mutable header mapping."""
    if budget is not None and budget.truncated:
        headers[OMI_LIST_TRUNCATED_HEADER] = OMI_LIST_TRUNCATED_VALUE
