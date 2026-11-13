"""Shared shadow reservations against the authoritative monthly billing snapshot.

No provider permission is granted here. Expired, unaccounted work retains its
hold until billing settles it: a worker crash must never manufacture credit.
All mutation retries contain Firestore reads/writes only, under erasure fences.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import math
from typing import Any, Callable, Sequence

from google.cloud import firestore

from database._client import get_firestore_client
from database import monthly_usage_totals

LEASE_SECONDS = 30
MAX_OPEN_LEASES = 128
BILLING_SOURCES = frozenset({'live', 'upload', 'batch', 'one_shot', 'ptt', 'unknown'})


@dataclass(frozen=True)
class Reference:
    uid: str
    month: str
    key: str


@dataclass(frozen=True)
class Lease(Reference):
    seconds: float
    expires_at: float


@dataclass(frozen=True)
class Decision:
    reason: str
    remaining: float
    lease: Lease | None = None


def reference(uid: str, operation: str, now: datetime, *, billing_period: str | None = None) -> Reference:
    """Server operation identity, distinct from permission to spend."""
    month, _ = _period(now)
    if billing_period is not None:
        stamp = datetime.strptime(billing_period, '%Y-%m').replace(tzinfo=timezone.utc)
        if stamp.strftime('%Y-%m') != billing_period or billing_period > month:
            raise ValueError('invalid billing period')
        month = billing_period
    return Reference(uid, month, hashlib.sha256(operation.encode()).hexdigest())


def _number(value: Any) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('finite nonnegative allowance seconds required')
    return float(value)


def _period(now: datetime) -> tuple[str, float]:
    if now.tzinfo is None:
        raise ValueError('aware UTC billing clock required')
    now = now.astimezone(timezone.utc)
    end = (now.replace(day=1) + timedelta(days=32)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return now.strftime('%Y-%m'), end.timestamp()


def _ref(user: Any, month: str) -> Any:
    return user.collection('free_allowance_months').document(month)


def _receipt(user: Any, month: str, key: str) -> Any:
    return user.collection('free_allowance_receipts').document(f'{month}_{key}')


def _operation(user: Any, key: str) -> Any:
    return user.collection('free_allowance_operations').document(key)


def _operation_months(data: Any) -> list[str]:
    if data is None:
        return []
    if not isinstance(data, dict) or data.get('status') not in {'active', 'settled'}:
        raise ValueError('invalid allowance operation')
    months = data.get('months')
    if not isinstance(months, list) or not 1 <= len(months) <= 3:
        raise ValueError('invalid operation periods')
    for month in months:
        if not isinstance(month, str) or datetime.strptime(month, '%Y-%m').strftime('%Y-%m') != month:
            raise ValueError('invalid operation period')
    if len(set(months)) != len(months):
        raise ValueError('duplicate operation period')
    return months


def _state(data: Any) -> dict:
    if data is None:
        return {'schema_version': 1, 'holds': {}, 'ptt_seconds': 0.0}
    if not isinstance(data, dict) or data.get('schema_version') != 1 or not isinstance(data.get('holds'), dict):
        raise ValueError('unreadable allowance ledger')
    if len(data['holds']) > MAX_OPEN_LEASES:
        raise ValueError('unbounded allowance ledger')
    _number(data.get('ptt_seconds'))
    for key, row in data['holds'].items():
        if not isinstance(key, str) or len(key) != 64 or not isinstance(row, dict):
            raise ValueError('invalid allowance hold')
        _number(row.get('seconds'))
        _number(row.get('expires_at'))
    return data


def _held(state: dict) -> float:
    # Expiry stops renewal, not accounting. Keep uncertain spend visible.
    return _number(sum(row['seconds'] for row in state['holds'].values()))


def reserve(
    uid: str,
    operation: str,
    seconds: float,
    limit: float,
    *,
    now: datetime | None = None,
    partial: bool = False,
    elapsed_seconds: float = 0,
    billing_period: str | None = None,
    firestore_client: Any = None,
) -> Decision:
    """Atomically reserve once across replicas; retries cannot duplicate a hold.

    A live caller may request the final partial window. Same-operation renewal
    cannot resurrect an expired or settled lease. No cohort or flag is read.
    """
    seconds, limit = _number(seconds), _number(limit)
    elapsed_seconds = _number(elapsed_seconds)
    if partial and elapsed_seconds > seconds:
        raise ValueError('reservation must cover its unbilled exposure')
    if not uid or not operation or len(operation) > 512 or seconds <= 0:
        raise ValueError('identified positive reservation required')
    now = now or datetime.now(timezone.utc)
    month, end = _period(now)
    now = now.astimezone(timezone.utc)
    billing_date = now
    if billing_period is not None:
        month = reference(uid, operation, now, billing_period=billing_period).month
        billing_date = datetime.strptime(month, '%Y-%m').replace(tzinfo=timezone.utc)
        if month < now.strftime('%Y-%m'):
            end = now.timestamp() + LEASE_SECONDS
    key = hashlib.sha256(operation.encode()).hexdigest()
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user = client.collection('users').document(uid)

    @firestore.transactional
    def commit(transaction: Any) -> Decision:
        with monthly_usage_totals.publication_fence(user, transaction, firestore_client=client):
            usage = monthly_usage_totals.month_ref(user, billing_date).get(transaction=transaction).to_dict()
            used = monthly_usage_totals.verified_transcription_seconds(usage, billing_date)
            state = _state(_ref(user, month).get(transaction=transaction).to_dict())
            receipt = _receipt(user, month, key).get(transaction=transaction)
            operation_ref = _operation(user, key)
            operation_data = operation_ref.get(transaction=transaction).to_dict()
            months = _operation_months(operation_data)
            remaining = max(0.0, limit - used - state['ptt_seconds'] - _held(state))
            if receipt.exists or (operation_data or {}).get('status') == 'settled':
                return Decision('already_settled', remaining)
            if month not in months:
                if len(months) >= 3:
                    return Decision('operation_too_old', remaining)
                months.append(month)

            def record(reason: str) -> None:
                # Refused shadow work still spends under today's serving policy.
                data: dict[str, Any] = {
                    'months': months,
                    'status': 'active',
                    'last_reason': reason,
                    'had_refusal': (operation_data or {}).get('had_refusal') is True or reason == 'allowance_exhausted',
                    'has_hold': (operation_data or {}).get('has_hold') is True
                    or previous is not None
                    or reason == 'reserved',
                }
                if not data['has_hold']:
                    data['expires_at'] = now + timedelta(days=90)
                transaction.set(operation_ref, data)

            previous = state['holds'].get(key)
            if previous is not None and previous['expires_at'] <= now.timestamp():
                record('lease_expired')
                return Decision('lease_expired', remaining)
            available = remaining + (previous['seconds'] if previous is not None else 0)
            amount = min(seconds, available) if partial else seconds
            if amount <= 0 or amount > available:
                record('allowance_exhausted')
                return Decision('allowance_exhausted', remaining)
            if previous is None and len(state['holds']) >= MAX_OPEN_LEASES:
                record('ledger_full')
                return Decision('ledger_full', remaining)
            # Existing leases may shrink only through billing settlement, never
            # through a retry with a smaller duration or a different provider.
            amount = max(amount, previous['seconds'] if previous is not None else 0)
            if amount > available:
                record('allowance_exhausted')
                return Decision('allowance_exhausted', remaining)
            expiry = min(now.timestamp() + LEASE_SECONDS, end)
            if partial:
                if amount <= elapsed_seconds:
                    record('allowance_exhausted')
                    return Decision('allowance_exhausted', remaining)
                expiry = min(expiry, now.timestamp() + amount - elapsed_seconds)
            state['holds'][key] = {'seconds': amount, 'expires_at': expiry}
            transaction.set(_ref(user, month), state)
            record('reserved')
            return Decision('reserved', max(0.0, available - amount), Lease(uid, month, key, amount, expiry))

    return commit(client.transaction(max_attempts=3))


def chargeable_seconds(uid: str, now: datetime, *, firestore_client: Any = None) -> float:
    """Summary/memory and speech observe the identical billing + holds ledger."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user = client.collection('users').document(uid)
    month, _ = _period(now)
    now = now.astimezone(timezone.utc)

    @firestore.transactional
    def read(transaction: Any) -> float:
        with monthly_usage_totals.publication_fence(user, transaction, firestore_client=client):
            usage = monthly_usage_totals.month_ref(user, now).get(transaction=transaction).to_dict()
            used = monthly_usage_totals.verified_transcription_seconds(usage, now)
            state = _state(_ref(user, month).get(transaction=transaction).to_dict())
            return used + state['ptt_seconds'] + _held(state)

    return read(client.transaction(max_attempts=3))


def prepare_settlement(
    transaction: Any,
    user: Any,
    leases: Sequence[Reference],
    billed_seconds: float,
    *,
    now: datetime,
    daily_ptt: bool = False,
    allow_unreserved: bool = False,
    source: str = 'unknown',
    decision: str = 'unobserved',
) -> Callable[[], bool]:
    """Read BEFORE billing writes; queue release in the SAME billing transaction.

    Called only by trusted usage writers holding their publication fence. The
    exact writer's billed units are stored in receipts; input duration estimates
    never become billed seconds. Unrelated usage cannot release these holds.
    PTT currently bills a separate daily counter; its shadow consumption is
    retained here without modifying monthly billing or the existing daily cap.
    """
    billed_seconds = _number(billed_seconds)
    if source not in BILLING_SOURCES or decision not in {'would_allow', 'would_refuse', 'unobserved'}:
        raise ValueError('bounded receipt dimensions required')
    unique = {(lease.month, lease.key): lease for lease in leases}
    if len(unique) > MAX_OPEN_LEASES or any(lease.uid != user.id for lease in unique.values()):
        raise ValueError('allowance settlement owner or size mismatch')
    states = {
        month: _state(_ref(user, month).get(transaction=transaction).to_dict())
        for month in {month for month, _ in unique}
    }
    receipts = {identity: _receipt(user, *identity).get(transaction=transaction).exists for identity in unique}
    pending = [identity for identity in unique if not receipts[identity]]
    if daily_ptt and len({key for _, key in unique}) != 1:
        raise ValueError('one PTT billing unit required')
    ptt_month, _ = _period(now)
    if daily_ptt and ptt_month not in states:
        states[ptt_month] = _state(_ref(user, ptt_month).get(transaction=transaction).to_dict())
    for month, key in pending:
        if key not in states[month]['holds'] and not allow_unreserved:
            raise ValueError('missing allowance hold')
        states[month]['holds'].pop(key, None)
    if daily_ptt and pending:
        states[ptt_month]['ptt_seconds'] += billed_seconds

    def queue() -> bool:
        for month in {month for month, _ in pending} | ({ptt_month} if daily_ptt and pending else set()):
            transaction.set(_ref(user, month), states[month])
        for index, (month, key) in enumerate(pending):
            transaction.set(
                _receipt(user, month, key),
                {
                    'billed_seconds': billed_seconds if index == 0 else 0,
                    'source': source,
                    'decision': decision,
                    'settled_at': now,
                    'expires_at': now + timedelta(days=90),
                },
            )
        return bool(pending)

    return queue


def _batch_aggregate(
    transaction: Any,
    user: Any,
    content_id: str,
    expected_start: datetime | None,
    now: datetime,
    refused: bool,
    client: Any,
):
    """One monotonic receipt per committed content-billing generation.

    Unit receipts carry zero; an absent/previously settled chunk cannot own or
    lose the aggregate. Read the writer's actual integer billing counter, never
    a request estimate or a caller's stale partial delta.
    """
    from database.sync_ledger import sync_content_ledger_ref

    if not content_id or len(content_id) > 512:
        raise ValueError('batch billing identity required')
    billing = sync_content_ledger_ref(client, user.id, content_id).get(transaction=transaction).to_dict()
    if not billing or billing.get('usage_committed_at') is None:
        raise ValueError('confirmed batch billing required')
    total = _number(billing.get('allowance_billed_seconds'))
    started = billing.get('allowance_billing_started_at')
    if not isinstance(started, datetime) or started.tzinfo is None:
        raise ValueError('verified batch billing generation required')
    if expected_start != started:
        raise ValueError('batch billing generation changed')
    key = hashlib.sha256(f'{content_id}:{started.timestamp():.6f}'.encode()).hexdigest()
    ref = _receipt(user, 'batch', key)
    previous = ref.get(transaction=transaction).to_dict()
    prior = 0.0
    prior_decision = 'unobserved'
    if previous is not None:
        if previous.get('kind') != 'batch_aggregate' or previous.get('source') != 'batch':
            raise ValueError('invalid batch aggregate receipt')
        prior = _number(previous.get('billed_seconds'))
        prior_decision = previous.get('decision')
        if prior_decision not in {'unobserved', 'would_allow', 'would_refuse'}:
            raise ValueError('invalid batch aggregate decision')
    verdict = 'would_refuse' if refused else prior_decision
    if previous is not None and total <= prior and verdict == prior_decision:
        return None
    return ref, {
        'kind': 'batch_aggregate',
        'source': 'batch',
        'billed_seconds': max(total, prior),
        'decision': verdict,
        'settled_at': now,
        'expires_at': now + timedelta(days=90),
    }


def settle_billed(
    leases: Sequence[Reference],
    seconds: float,
    *,
    now: datetime | None = None,
    daily_ptt: bool = False,
    registered_only: bool = False,
    source: str = 'unknown',
    decision: str = 'unobserved',
    batch_content_id: str | None = None,
    batch_billing_started_at: datetime | None = None,
    firestore_client: Any = None,
) -> bool:
    """Release ONLY after the trusted usage writer confirms its billing commit.

    This watch-only adapter deliberately follows billing in a separate fenced
    transaction. A lost reply retains excess holds (conservative); it cannot
    release credit before billing or roll back served usage on telemetry error.
    Unadmitted watch-only spend is still recorded once in the receipt.
    """
    if not leases:
        return False
    if batch_content_id is not None and (source != 'batch' or not registered_only or daily_ptt or seconds != 0):
        raise ValueError('batch aggregates require zero-valued registered unit settlement')
    now = now or datetime.now(timezone.utc)
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user = client.collection('users').document(leases[0].uid)

    @firestore.transactional
    def commit(transaction: Any) -> bool:
        with monthly_usage_totals.publication_fence(user, transaction, firestore_client=client):
            operations = {}
            expanded = []
            refused = decision == 'would_refuse'
            for lease in leases:
                if lease.uid != user.id:
                    raise ValueError('allowance settlement owner mismatch')
                if lease.key in operations:
                    continue
                data = _operation(user, lease.key).get(transaction=transaction).to_dict()
                if data is None and registered_only:
                    continue
                refused = refused or (data or {}).get('had_refusal') is True
                months = _operation_months(data) or [lease.month]
                operations[lease.key] = months
                expanded.extend(Reference(user.id, month, lease.key) for month in months)
            aggregate = (
                _batch_aggregate(transaction, user, batch_content_id, batch_billing_started_at, now, refused, client)
                if batch_content_id is not None and operations
                else None
            )
            queue = prepare_settlement(
                transaction,
                user,
                expanded,
                seconds,
                now=now,
                daily_ptt=daily_ptt,
                allow_unreserved=True,
                source=source,
                decision='would_refuse' if refused else decision,
            )
            changed = queue()
            for key, months in operations.items():
                transaction.set(
                    _operation(user, key),
                    {'months': months, 'status': 'settled', 'expires_at': now + timedelta(days=90)},
                )
            if aggregate is not None:
                transaction.set(*aggregate)
            return changed or aggregate is not None

    return commit(client.transaction(max_attempts=3))


def settle_daily_ptt(
    lease: Reference, seconds: float, *, now: datetime | None = None, firestore_client: Any = None
) -> bool:
    """Idempotently mirror successful daily PTT settlement, never monthly billing."""
    return settle_billed([lease], seconds, now=now, daily_ptt=True, firestore_client=firestore_client)
