"""Hard daily money authority; Redis leases never own or refund dollars."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import timedelta
from typing import Any

from google.cloud import firestore

from config.proactivity_v2 import AttemptEnvelope, ProactivityDenied, Reservation, producer_for, utc_now
from database import proactivity_redis
from database.llm_gateway_accounting import record_llm_gateway_attempt
from database.proactivity import (
    CONTROLS,
    DAYS,
    admission_records,
    client_or_default,
    data_at,
    item_ref,
    read_owner,
    source_visible,
    user_ref,
)

logger = logging.getLogger(__name__)

_RELEASE = "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) else return 0 end"


class BudgetAuthority:
    def __init__(self, *, firestore_client: Any = None, redis_client: Any = None, clock=utc_now):
        self.client = client_or_default(firestore_client)
        self.redis = redis_client if redis_client is not None else proactivity_redis.get_client()
        self.clock = clock

    def reserve(self, *, uid: str, item_id: str, producer: str, call_id: str, envelope: AttemptEnvelope) -> Reservation:
        now = self.clock()
        day = now.strftime('%Y-%m-%d')
        row = producer_for(producer)
        if (
            type(envelope.worst_case_micro_usd) is not int
            or envelope.worst_case_micro_usd <= 0
            or not call_id
            or '/' in call_id
            or len(call_id) > 64
        ):
            raise ProactivityDenied('invalid_envelope')
        owner_hash = hashlib.sha256(uid.encode()).hexdigest()
        key = f'proactivity:v2:{{{owner_hash}}}:admission:{day}:{item_id}:{call_id}'
        token = secrets.token_hex(24)
        try:
            acquired = self.redis.set(key, token, nx=True, px=30000)
        except Exception as exc:
            raise ProactivityDenied('unavailable') from exc
        if not acquired:
            raise ProactivityDenied('duplicate')
        ref = item_ref(self.client, uid, item_id)
        day_ref = user_ref(self.client, uid).collection(DAYS).document(day)

        @firestore.transactional
        def transact(tx: Any):
            generation, cap = admission_records(self.client, uid, row, tx, now)
            item = data_at(ref, tx)
            balance = data_at(day_ref, tx)
            if (
                not item
                or item['account_generation'] != generation
                or item['producer'] != producer
                or item['producer_version'] != row.version
            ):
                raise ProactivityDenied('not_found')
            visible = source_visible(self.client, uid, item, tx)
            if not visible or item['state'] != 'claimed' or now >= item['created_at'] + timedelta(hours=24):
                raise ProactivityDenied('expired')
            attempts = item['attempts']
            if call_id in attempts:
                raise ProactivityDenied('duplicate')
            if any(a['state'] in {'reserved', 'unknown'} for a in attempts.values()):
                raise ProactivityDenied('cost_unsettled')
            calls = balance.get('producer_calls', {})
            if len(attempts) >= row.max_calls_per_item or calls.get(producer, 0) >= row.max_calls_per_user_utc_day:
                raise ProactivityDenied('call_limit')
            amount = envelope.worst_case_micro_usd
            if balance.get('blocked') or balance.get('charged_micro_usd', 0) + amount > cap:
                raise ProactivityDenied('budget_exhausted')
            if balance and balance.get('account_generation') != generation:
                raise ProactivityDenied('unavailable')
            calls[producer] = calls.get(producer, 0) + 1
            balance.update(
                charged_micro_usd=balance.get('charged_micro_usd', 0) + amount,
                priced_micro_usd=balance.get('priced_micro_usd', 0),
                producer_calls=calls,
                blocked=False,
                account_generation=generation,
                policy_version=1,
                updated_at=now,
                expires_at=now + timedelta(days=90),
            )
            attempts[call_id] = dict(
                state='reserved',
                day=day,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                reserved_micro_usd=amount,
                charged_micro_usd=amount,
                estimated_cost_micro_usd=0,
                fingerprint=envelope.fingerprint,
                provider=envelope.provider,
                model=envelope.model,
                rate_card_id=envelope.rate_card_id,
                step=envelope.step,
                request_id=call_id,
            )
            item.update(
                reserved_micro_usd=item['reserved_micro_usd'] + amount,
                charged_micro_usd=item['charged_micro_usd'] + amount,
                cost_status='pending',
                unknown_count=1,
                updated_at=now,
            )
            tx.set(ref, item)
            tx.set(day_ref, balance)
            return Reservation(uid, item_id, producer, call_id, day, token, amount, generation)

        try:
            reservation = transact(self.client.transaction())
            logger.info(
                'proactivity_v2_budget_reserved producer=%s reserved_micro_usd=%s policy_version=1',
                producer,
                reservation.reserved_micro_usd,
            )
            return reservation
        except ProactivityDenied:
            raise
        except Exception as exc:
            raise ProactivityDenied('unavailable') from exc
        finally:
            try:
                self.redis.eval(_RELEASE, 1, key, token)
            except Exception:
                # The transaction, not lease expiry/release, fences duplicate spend.
                pass

    def settle(self, *, reservation: Reservation, event: Any) -> bool:
        payload = event.as_dict()
        if (
            payload['user_uid'] != reservation.uid
            or payload['request_id'] != reservation.call_id
            or payload['feature'] != f'proactivity_v2_{reservation.producer}'
            or payload['payer'] != 'omi'
        ):
            raise ProactivityDenied('settlement_identity')
        # Same event ID as the normal gateway sink. Failure retains the entire hold.
        record_llm_gateway_attempt(payload, firestore_client=self.client)
        cost = payload['estimated_cost_micro_usd'] if payload['cost_status'] == 'estimated' else None
        return self._settle(
            reservation,
            cost=cost,
            attempt_id=payload['attempt_id'],
            provider=payload['provider'],
            model=payload['configured_model'],
            released=False,
        )

    def release_unsent(self, *, reservation: Reservation) -> bool:
        return self._settle(reservation, cost=0, attempt_id='', provider='', model='', released=True)

    def _settle(
        self, reservation: Reservation, *, cost: int | None, attempt_id: str, provider: str, model: str, released: bool
    ) -> bool:
        now = self.clock()
        ref = item_ref(self.client, reservation.uid, reservation.item_id)
        day_ref = user_ref(self.client, reservation.uid).collection(DAYS).document(reservation.day)
        control_ref = self.client.collection(CONTROLS).document(reservation.producer)

        @firestore.transactional
        def transact(tx: Any):
            _, generation = read_owner(self.client, reservation.uid, tx)
            item = data_at(ref, tx)
            balance = data_at(day_ref, tx)
            control = data_at(control_ref, tx)
            if not item or not balance or generation != reservation.account_generation:
                raise ProactivityDenied('not_found')
            attempt = item['attempts'].get(reservation.call_id)
            if not attempt or attempt['token_hash'] != hashlib.sha256(reservation.token.encode()).hexdigest():
                raise ProactivityDenied('settlement_identity')
            if not released and (attempt['provider'] != provider or attempt['model'] != model):
                raise ProactivityDenied('settlement_identity')
            if attempt['state'] != 'reserved':
                if attempt.get('attempt_id', '') != attempt_id or attempt.get('actual_micro_usd') != cost:
                    raise ProactivityDenied('settlement_conflict')
                return attempt['state'] in {'settled', 'released'}
            if cost is not None and (type(cost) is not int or cost < 0):
                raise ProactivityDenied('invalid_cost')
            amount = attempt['reserved_micro_usd']
            charged = amount if cost is None else cost
            attempt.update(
                state='released' if released else 'unknown' if cost is None else 'settled',
                charged_micro_usd=charged,
                actual_micro_usd=cost,
                attempt_id=attempt_id,
                estimated_cost_micro_usd=cost or 0,
            )
            delta = charged - amount
            balance['charged_micro_usd'] += delta
            balance['priced_micro_usd'] += cost or 0
            balance['updated_at'] = now
            item['charged_micro_usd'] += delta
            item['estimated_cost_micro_usd'] += cost or 0
            item['reserved_micro_usd'] -= amount if cost is not None else 0
            unknown = any(a['state'] in {'reserved', 'unknown'} for a in item['attempts'].values())
            item.update(
                cost_status='indeterminate' if unknown else 'estimated', unknown_count=int(unknown), updated_at=now
            )
            over = cost is not None and cost > amount
            if over:
                balance['blocked'] = True
                control.update(state='killed', verdict='over_reserved', checked_at=now)
            tx.set(ref, item)
            tx.set(day_ref, balance)
            if over:
                tx.set(control_ref, control)
            return not unknown and not over

        result = transact(self.client.transaction())
        logger.info(
            'proactivity_v2_budget_settled producer=%s priced_micro_usd=%s result=%s policy_version=1',
            reservation.producer,
            cost,
            result,
        )
        if cost is not None and cost > reservation.reserved_micro_usd:
            logger.critical(
                'proactivity_v2_budget_invariant_failed producer=%s reason=over_reserved', reservation.producer
            )
        return result
