"""Content-free delivery terminal counters. No alarm is armed by this module."""

from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar, cast, overload

from prometheus_client import Counter

DELIVERY_OUTCOME = Counter(
    'omi_delivery_outcome_total',
    'Durable summary, sync processing and action export terminal attempts',
    ['kind', 'outcome'],
)
KINDS = frozenset({'summary', 'sync', 'action_item_export'})
OUTCOMES = frozenset({'delivered', 'no_op', 'deferred', 'failed'})
AsyncFunction = TypeVar('AsyncFunction', bound=Callable[..., Awaitable[Any]])
SyncFunction = TypeVar('SyncFunction', bound=Callable[..., Any])
Result = TypeVar('Result')


def record_delivery(kind: str, outcome: str, count: int = 1) -> None:
    # Reject unknown values before creating a child: IDs/text cannot become
    # labels, even when a future caller accidentally supplies them.
    if kind in KINDS and outcome in OUTCOMES and count > 0:
        DELIVERY_OUTCOME.labels(kind=kind, outcome=outcome).inc(count)


def observe_action_export(function: AsyncFunction) -> AsyncFunction:
    """Count the public single-item or batch terminal once, including no-ops."""

    @wraps(function)
    async def counted(*args: Any, **kwargs: Any) -> Any:
        try:
            result = await function(*args, **kwargs)
        except Exception:
            items = kwargs.get('action_items', args[1] if len(args) > 1 else None)
            record_delivery('action_item_export', 'failed', len(items) if isinstance(items, list) else 1)
            raise
        rows = result if isinstance(result, list) else [result[0] if isinstance(result, tuple) and result else result]
        for row in rows:
            if not isinstance(row, dict):
                outcome = 'failed'  # Observation must not turn an opaque result into a new exception.
            elif row.get('reason') in {
                'already_exported',
                'no_default_integration',
                'integration_not_found',
                'integration_not_connected',
            }:
                outcome = 'no_op'
            elif row.get('reason') in {'lease_lost', 'client_handles_sync'} or (
                row.get('synced') and row.get('pending_device')
            ):
                outcome = 'deferred'
            else:
                outcome = 'delivered' if row.get('synced') else 'failed'
            record_delivery('action_item_export', outcome)
        return result

    return cast(AsyncFunction, counted)


def summary_terminal_outcome(existing: dict[str, Any], write: dict[str, Any]) -> str | None:
    """Classify final committed processing output; no state/receipt changes."""
    if write.get('status') != 'completed' or not ({'summary_output_present', 'structured'} & write.keys()):
        return None
    if (
        write.get('terminal_no_derived_effects')
        or write.get('deferred')
        or write.get('processing_state') == 'local_pending'
    ):
        return 'deferred'
    from utils.conversations.summary_delivery import present

    rich = write.get('summary_output_present', present(write.get('structured')))
    if write.get('discarded') or not rich:
        return 'no_op'
    return (
        'no_op'
        if existing.get('structured') is not None and existing.get('structured') == write.get('structured')
        else 'delivered'
    )


def observe_sync_failures(function: SyncFunction) -> SyncFunction:
    """Successful/deferred returns are counted explicitly at their sites."""

    @wraps(function)
    def counted(*args: Any, **kwargs: Any) -> Any:
        try:
            return function(*args, **kwargs)
        except Exception as error:
            outcome = (
                'deferred'
                if type(error).__name__
                in {
                    'SummaryRepairSuperseded',
                    'SyncConversationPersistenceFenced',
                    'ProcessingDeferred',
                }
                else 'failed'
            )
            record_delivery('sync', outcome)
            raise

    return cast(SyncFunction, counted)


@overload
def sync_result(outcome: str) -> None: ...


@overload
def sync_result(outcome: str, result: Result) -> Result: ...


def sync_result(outcome: str, result: Any = None) -> Any:
    record_delivery('sync', outcome)
    return result


def sync_defer(context: dict[str, Any] | None, reason: str) -> None:
    if context is not None:
        context['defer_reason'] = reason
    return sync_result('deferred')


def sync_refreshed(
    row: dict[str, Any] | None,
    decode: Callable[[dict[str, Any]], Result],
    present: Callable[[Any], bool],
) -> Result | None:
    result = decode(row) if row else None
    outcome = (
        'delivered'
        if row and present(row.get('structured'))
        else 'no_op' if row and row.get('discarded') else 'deferred'
    )
    return sync_result(outcome, result)
