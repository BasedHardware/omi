"""Transactional minute headroom and per-turn receipts under the owner lease."""

from datetime import datetime, timezone

from google.cloud import firestore

from database import dream_store
from config.dream_agent import enabled


def reserve(uid, run_id, tokens, caps, *, now=None, firestore_client=None):
    if not enabled() or type(tokens) is not int or tokens <= 0:
        raise ValueError('dream_disabled_or_budget')
    database = dream_store.client(firestore_client)
    state = dream_store.state_ref(database, uid)
    headroom = database.collection('dream_scheduler').document('headroom')
    minute = (now or datetime.now(timezone.utc)).strftime('%Y-%m-%dT%H:%M')

    @firestore.transactional
    def claim(tx):
        data = state.get(transaction=tx).to_dict() or {}
        capacity = headroom.get(transaction=tx).to_dict() or {}
        if (data.get('lease') or {}).get('run_id') != run_id:
            raise RuntimeError('dream_lease_lost')
        used = capacity.get('tokens', 0) if capacity.get('minute') == minute else 0
        if used + tokens > caps.tokens_per_minute:
            raise ValueError('dream_minute_headroom')
        lease = data['lease']
        spend = dream_store.spend_ref(database, uid, lease['day'])
        global_spend = dream_store.lease_global_ref(database, uid, lease)
        budget = spend.get(transaction=tx).to_dict() or {}
        global_budget = global_spend.get(transaction=tx).to_dict() or {}
        observed = sum(row['accounted_tokens'] for row in lease.get('turn_receipts', []))
        required = (observed + tokens) * lease['max_usd_per_token']
        previous = lease.get('budget_charge_usd', lease['reservation_usd'])
        held = max(previous, required)
        increase = held - previous
        if budget.get('reserved_usd', 0) + increase > caps.daily_usd or global_budget.get(
            'reserved_usd', 0
        ) + increase > lease.get('global_shard_cap', caps.global_daily_usd):
            raise ValueError('dream_daily_budget')
        tx.set(spend, {**budget, 'reserved_usd': budget.get('reserved_usd', 0) + increase})
        tx.set(global_spend, {**global_budget, 'reserved_usd': global_budget.get('reserved_usd', 0) + increase})
        tx.update(
            state,
            {
                'lease': {
                    **lease,
                    'budget_charge_usd': held,
                    'reservation_usd': held,
                    'minute_hold': {'minute': minute, 'tokens': tokens},
                }
            },
        )
        tx.set(headroom, {'minute': minute, 'tokens': used + tokens})

    claim(database.transaction())


def settle(uid, run_id, turn, *, firestore_client=None):
    database = dream_store.client(firestore_client)
    state = dream_store.state_ref(database, uid)

    @firestore.transactional
    def receipt(tx):
        data = state.get(transaction=tx).to_dict() or {}
        lease = data.get('lease') or {}
        if lease.get('run_id') != run_id:
            raise RuntimeError('dream_lease_lost')
        spend = dream_store.spend_ref(database, uid, lease['day'])
        budget = spend.get(transaction=tx).to_dict() or {}
        charge = turn.tokens if turn.accounted_tokens is None else turn.accounted_tokens
        if charge < turn.tokens or charge < 0:
            raise ValueError('dream_invalid_usage')
        receipt = {'tokens': turn.tokens, 'accounted_tokens': charge, 'cached_tokens': turn.cached_tokens}
        rows = [*(lease.get('turn_receipts') or []), receipt]
        if len(rows) > 128:
            raise ValueError('dream_turn_cap')
        rate = lease['max_usd_per_token']
        global_spend = dream_store.lease_global_ref(database, uid, lease)
        global_budget = global_spend.get(transaction=tx).to_dict() or {}
        headroom = database.collection('dream_scheduler').document('headroom')
        capacity = headroom.get(transaction=tx).to_dict() or {}
        hold = lease.get('minute_hold') or {}
        if capacity.get('minute') == hold.get('minute') and hold.get('tokens'):
            tx.set(headroom, {**capacity, 'tokens': max(0, capacity.get('tokens', 0) - hold['tokens'] + charge)})
        actual = sum(row['accounted_tokens'] for row in rows) * rate
        previous = lease.get('budget_charge_usd', lease['reservation_usd'])
        tx.update(
            state, {'lease': {**lease, 'turn_receipts': rows, 'budget_charge_usd': actual, 'reservation_usd': actual}}
        )
        tx.set(
            global_spend,
            {**global_budget, 'reserved_usd': max(0, global_budget.get('reserved_usd', 0) - previous + actual)},
        )
        # Reserved maximum remains held until finish, including unknown billed
        # failures. Observed spend is settled every turn in the admission day.
        tx.set(
            spend,
            {
                **budget,
                'observed_usd': budget.get('observed_usd', 0) + turn.tokens * rate,
                'reserved_usd': max(0, budget.get('reserved_usd', 0) - previous + actual),
            },
        )

    receipt(database.transaction())
