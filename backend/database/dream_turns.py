"""Transactional minute headroom and per-turn receipts under the owner lease."""

from datetime import datetime, timezone
from hashlib import sha256

from google.cloud import firestore

from database import dream_store
from config.dream_agent import enabled

HEADROOM_SHARDS = 64


def headroom_ref(database, shard):
    return database.collection('dream_scheduler').document('headroom-' + str(shard))


def headroom_quota(tokens_per_minute, shard):
    """Integer shard quotas sum exactly to the configured minute ceiling."""
    base, extra = divmod(tokens_per_minute, HEADROOM_SHARDS)
    return base + int(shard < extra)


def reserve(uid, run_id, tokens, caps, *, now=None, firestore_client=None):
    if not enabled() or type(tokens) is not int or tokens <= 0:
        raise ValueError('dream_disabled_or_budget')
    database = dream_store.client(firestore_client)
    state = dream_store.state_ref(database, uid)
    minute = (now or datetime.now(timezone.utc)).strftime('%Y-%m-%dT%H:%M')
    first_shard = int.from_bytes(sha256((uid + ':' + run_id).encode()).digest()[:8], 'big') % HEADROOM_SHARDS

    @firestore.transactional
    def claim(tx):
        data = state.get(transaction=tx).to_dict() or {}
        if (data.get('lease') or {}).get('run_id') != run_id:
            raise RuntimeError('dream_lease_lost')
        if tokens > caps.tokens_per_minute:
            raise ValueError('dream_minute_headroom')
        # Rotate the first shard per owner/run. Larger turns can span quotas;
        # ordinary turns only touch the few shards they need, never a global row.
        holds, capacities = {}, {}
        remaining = tokens
        for offset in range(HEADROOM_SHARDS):
            shard = (first_shard + offset) % HEADROOM_SHARDS
            quota = headroom_quota(caps.tokens_per_minute, shard)
            if not quota:
                continue
            capacity = headroom_ref(database, shard).get(transaction=tx).to_dict() or {}
            used = capacity.get('tokens', 0) if capacity.get('minute') == minute else 0
            take = min(remaining, max(0, quota - used))
            if take:
                holds[str(shard)] = take
                capacities[shard] = used + take
                remaining -= take
            if not remaining:
                break
        if remaining:
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
                    'minute_hold': {'minute': minute, 'tokens': tokens, 'shards': holds},
                }
            },
        )
        for shard, used in capacities.items():
            tx.set(headroom_ref(database, shard), {'minute': minute, 'tokens': used})

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
        hold = lease.get('minute_hold') or {}
        capacities = []
        held_shards = list((hold.get('shards') or {}).items())
        remaining = charge
        for index, (shard, held) in enumerate(held_shards):
            ref = headroom_ref(database, int(shard))
            capacity = ref.get(transaction=tx).to_dict() or {}
            # Attribute known/unknown usage to the reserved shards; any billed
            # excess stays charged on the final shard rather than disappearing.
            actual = remaining if index == len(held_shards) - 1 else min(held, remaining)
            remaining -= actual
            if capacity.get('minute') == hold.get('minute'):
                capacities.append((ref, {**capacity, 'tokens': max(0, capacity.get('tokens', 0) - held + actual)}))
        for ref, capacity in capacities:
            tx.set(ref, capacity)
        actual = sum(row['accounted_tokens'] for row in rows) * rate
        previous = lease.get('budget_charge_usd', lease['reservation_usd'])
        tx.update(
            state,
            {
                'lease': {
                    **lease,
                    'turn_receipts': rows,
                    'budget_charge_usd': actual,
                    'reservation_usd': actual,
                    'minute_hold': None,
                }
            },
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
