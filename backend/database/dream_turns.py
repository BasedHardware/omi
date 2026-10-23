"""Transactional minute headroom and per-turn receipts under the owner lease.

Minute shards remain the local tokens-per-minute backstop. Dollar headroom is
the per-user daily cap, and only moves when an attempt has a real rate-card
price. Unpriced attempts do not post a zero charge.
"""

from datetime import datetime, timezone
from hashlib import sha256

from google.cloud import firestore

from database import dream_store, firestore_transaction_retry
from config.dream_agent import enabled
from utils.dream_cost import minute_burndown_tokens

HEADROOM_SHARDS = 64


def headroom_ref(database, shard):
    return database.collection('dream_scheduler').document('headroom-' + str(shard))


def headroom_quota(tokens_per_minute, shard):
    """Integer shard quotas sum exactly to the configured minute ceiling."""
    base, extra = divmod(tokens_per_minute, HEADROOM_SHARDS)
    return base + int(shard < extra)


def _held_usd(lease):
    return float(lease.get('budget_charge_usd', lease.get('reservation_usd', 0)))


def reserve(uid, run_id, tokens, caps, *, cost_micro_usd=None, now=None, firestore_client=None):
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
        budget = spend.get(transaction=tx).to_dict() or {}
        previous = _held_usd(lease)
        held = previous
        increase = 0.0
        if type(cost_micro_usd) is int and cost_micro_usd >= 0:
            settled = sum(
                int(row.get('cost_micro_usd') or 0)
                for row in lease.get('turn_receipts') or []
                if row.get('cost_status') == 'priced'
            )
            required = (settled + cost_micro_usd) / 1000000
            held = max(previous, required)
            increase = held - previous
            if float(budget.get('reserved_usd', 0)) + increase > caps.daily_usd:
                raise ValueError('dream_daily_budget')
        if increase:
            tx.set(spend, {**budget, 'reserved_usd': float(budget.get('reserved_usd', 0)) + increase})
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

    # The SDK retries commit aborts, but read-time shard contention escapes it.
    firestore_transaction_retry.run_with_transaction_contention_retry(
        database.transaction, claim, operation_name='dream_turn_reserve'
    )


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
        status = getattr(turn, 'cost_status', None) or 'unpriced'
        micro = getattr(turn, 'cost_micro_usd', None)
        row = {
            'tokens': turn.tokens,
            'accounted_tokens': charge,
            'cached_tokens': turn.cached_tokens,
            'cost_status': status,
        }
        if status == 'priced' and type(micro) is int and micro >= 0:
            row['cost_micro_usd'] = micro
        else:
            status = 'unpriced'
            row['cost_status'] = 'unpriced'
        # Known-zero attempts still refund their minute hold, but are not model
        # turns and must not consume receipt capacity during reservation retries.
        known_zero = turn.tokens == 0 and charge == 0 and status == 'priced' and micro == 0
        rows = list(lease.get('turn_receipts') or [])
        if not known_zero:
            rows.append(row)
        if len(rows) > 128:
            raise ValueError('dream_turn_cap')
        hold = lease.get('minute_hold') or {}
        capacities = []
        held_shards = list((hold.get('shards') or {}).items())
        # Post actual burndown, including reported cache savings and output's price ratio.
        # Admission is enforced by the uncached hold in reserve(), not by settlement.
        weighted = getattr(turn, 'price_weighted_tokens', None)
        completion = (
            turn.completion_tokens if type(turn.completion_tokens) is int and turn.completion_tokens >= 0 else 0
        )
        base = weighted if type(weighted) is int and 0 <= weighted <= charge else charge
        remaining = minute_burndown_tokens(
            'gemini', 'gemini-3.8-flash', weighted_tokens=base, completion_tokens=min(completion, base)
        )
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
        previous = _held_usd(lease)
        priced = (bool(rows) or known_zero) and all(item.get('cost_status') == 'priced' for item in rows)
        if priced and type(micro) is int:
            actual_usd = sum(int(item['cost_micro_usd']) for item in rows) / 1000000
            observed_add = micro / 1000000
        else:
            actual_usd = previous
            observed_add = 0
        tx.update(
            state,
            {
                'lease': {
                    **lease,
                    'turn_receipts': rows,
                    'budget_charge_usd': actual_usd,
                    'reservation_usd': actual_usd,
                    'minute_hold': None,
                    'cost_status': 'priced' if priced else 'unpriced',
                }
            },
        )
        tx.set(
            spend,
            {
                **budget,
                'observed_usd': float(budget.get('observed_usd', 0)) + observed_add,
                'reserved_usd': max(0, float(budget.get('reserved_usd', 0)) - previous + actual_usd),
            },
        )

    firestore_transaction_retry.run_with_transaction_contention_retry(
        database.transaction, receipt, operation_name='dream_turn_settle'
    )
