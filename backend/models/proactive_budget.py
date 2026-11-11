"""Pure budget arithmetic for Chat-first agent-initiated turns."""

from datetime import datetime, timedelta, timezone

from models.chat_first import ProactiveBudgetReservation, ProactiveBudgetState

DAILY_PROACTIVE_TURN_LIMIT = 10
ROLLING_30_MINUTE_PROACTIVE_TURN_LIMIT = 2
_RESERVATION_TTL = timedelta(days=1)
_RECENT_WINDOW = timedelta(minutes=30)


def normalized_budget_state(state: ProactiveBudgetState, *, now: datetime) -> ProactiveBudgetState:
    """Drop expired reservations and stale accounting outside the bounded horizon."""

    now_utc = _as_utc(now)
    oldest_materialization = now_utc - timedelta(days=2)
    return ProactiveBudgetState(
        account_generation=state.account_generation,
        materialized_at=[
            materialized_at
            for materialized_at in state.materialized_at
            if _as_utc(materialized_at) >= oldest_materialization
        ],
        reservations=[reservation for reservation in state.reservations if _as_utc(reservation.expires_at) > now_utc],
    )


def budget_allows(state: ProactiveBudgetState, *, now: datetime) -> bool:
    """Return whether one additional agent judgment may be evaluated.

    Outstanding reservations count against both limits. This prevents a burst of
    judged-but-not-yet-materialized intents from bypassing the mechanical cost
    gate, while receipts remain the only moment that records a consumed turn.
    """

    normalized = normalized_budget_state(state, now=now)
    now_utc = _as_utc(now)
    daily_turns = sum(1 for value in normalized.materialized_at if _as_utc(value).date() == now_utc.date())
    recent_turns = sum(1 for value in normalized.materialized_at if _as_utc(value) > now_utc - _RECENT_WINDOW)
    reserved_turns = len(normalized.reservations)
    return (
        daily_turns + reserved_turns < DAILY_PROACTIVE_TURN_LIMIT
        and recent_turns + reserved_turns < ROLLING_30_MINUTE_PROACTIVE_TURN_LIMIT
    )


def reserve_budget(
    state: ProactiveBudgetState,
    *,
    intent_id: str,
    now: datetime,
) -> ProactiveBudgetState:
    """Reserve one budget slot for an agent-tier intent in the creating transaction."""

    normalized = normalized_budget_state(state, now=now)
    if any(reservation.intent_id == intent_id for reservation in normalized.reservations):
        return normalized
    if not budget_allows(normalized, now=now):
        raise ValueError('proactive turn budget exhausted')
    return normalized.model_copy(
        update={
            'reservations': [
                *normalized.reservations,
                ProactiveBudgetReservation(intent_id=intent_id, expires_at=_as_utc(now) + _RESERVATION_TTL),
            ]
        }
    )


def account_materialization(
    state: ProactiveBudgetState,
    *,
    intent_id: str,
    now: datetime,
) -> ProactiveBudgetState:
    """Convert a reservation into a consumed turn after a kernel receipt."""

    normalized = normalized_budget_state(state, now=now)
    if any(reservation.intent_id == intent_id for reservation in normalized.reservations):
        reservations = [reservation for reservation in normalized.reservations if reservation.intent_id != intent_id]
    else:
        # A receipt may arrive after a bounded reservation expires. It still
        # represents a real materialized turn and must be counted once.
        reservations = normalized.reservations
    return normalized.model_copy(
        update={'reservations': reservations, 'materialized_at': [*normalized.materialized_at, now]}
    )


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


__all__ = [
    'DAILY_PROACTIVE_TURN_LIMIT',
    'ROLLING_30_MINUTE_PROACTIVE_TURN_LIMIT',
    'account_materialization',
    'budget_allows',
    'normalized_budget_state',
    'reserve_budget',
]
