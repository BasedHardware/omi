"""Content-free delivery terminal counters. No alarm is armed by this module."""

from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar, cast, overload

from prometheus_client import Counter
from utils.observability.reasons import DeliveryOutcome, ReasonFamily, reason_label, reason_values

DELIVERY_OUTCOME = Counter(
    'omi_delivery_outcome_total',
    'Durable summary, sync processing and action export terminal attempts',
    ['kind', 'outcome'],
)
KINDS = frozenset({'summary', 'sync', 'action_item_export'})
OUTCOMES = reason_values(DeliveryOutcome)
AsyncFunction = TypeVar('AsyncFunction', bound=Callable[..., Awaitable[Any]])
SyncFunction = TypeVar('SyncFunction', bound=Callable[..., Any])
Result = TypeVar('Result')


def record_delivery(kind: str, outcome: str, count: int = 1) -> None:
    # Reject unknown values before creating a child: IDs/text cannot become
    # labels, even when a future caller accidentally supplies them.
    if kind in KINDS and outcome in OUTCOMES and count > 0:
        DELIVERY_OUTCOME.labels(kind=kind, outcome=reason_label(ReasonFamily.DELIVERY, outcome, DeliveryOutcome)).inc(
            count
        )


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
            reason = row.get('reason') if isinstance(row, dict) else None
            reason = reason if isinstance(reason, str) else None
            if not isinstance(row, dict):
                outcome = 'failed'  # Observation must not turn an opaque result into a new exception.
            elif reason in {
                'already_exported',
                'no_default_integration',
                'integration_not_found',
                'integration_not_connected',
            }:
                outcome = 'no_op'
            elif reason in {'lease_lost', 'client_handles_sync'} or (row.get('synced') and row.get('pending_device')):
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
    if write.get('discarded'):
        return 'no_op'
    if (
        write.get('terminal_no_derived_effects')
        or write.get('deferred')
        or write.get('processing_deferred')
        or write.get('is_locked')
        or write.get('processing_state') == 'local_pending'
    ):
        return 'deferred'
    from utils.conversations.summary_delivery import present

    try:
        rich = write.get('summary_output_present')
        if rich is None:
            rich = present(write.get('structured'))
    except (AttributeError, TypeError, ValueError):
        return None  # Malformed observation must not reject an otherwise valid write.
    if not rich:
        from utils.conversations.minimum_derived import intentional_short_clip_minimum

        if intentional_short_clip_minimum(write):
            return 'no_op'
        return 'deferred'  # A kept minimum still owes its first summary.
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
                    # A sync write moved the revision mid-run; the enrichment consumer retries it.
                    'RefreshRevisionChanged',
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
    return sync_result(_sync_outcome(row, present), result)


def _sync_outcome(value: Any, present: Callable[[Any], bool]) -> str:
    from utils.conversations.summary_delivery import field

    if field(value, 'discarded', False) is True:
        return 'no_op'
    if (
        any(
            field(value, name, False) is True
            for name in (
                'deferred',
                'processing_deferred',
                'terminal_no_derived_effects',
                'is_locked',
            )
        )
        or field(value, 'processing_state') == 'local_pending'
    ):
        return 'deferred'
    try:
        return 'delivered' if present(field(value, 'structured')) else 'deferred'
    except (AttributeError, TypeError, ValueError):
        return 'deferred'


def sync_done(result: Result) -> Result:
    from utils.conversations.summary_delivery import present

    return sync_result(_sync_outcome(result, present), result)
