"""Firestore-backed attempt and cost authority for qualification-only JIT.

The desktop agent may issue concurrent gateway requests, and Cloud Run may put
those requests on different instances.  The owner/run document is therefore
the only counter.  An active reservation is deliberately left in place when a
provider outcome is unknown: a later request cannot spend around a crash or an
unpriced response.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import secrets
from typing import Any, Literal

from google.cloud import firestore

from database._client import get_firestore_client
from llm_gateway.gateway.accounting import rate_card_for, rounded_micro_usd

_COLLECTION = 'jit_cloud_qa_budgets_v1'
MAX_ATTEMPTS = 3
MAX_SPEND_MICRO_USD = 50_000
MAX_INPUT_TOKENS = 32_768
MAX_OUTPUT_TOKENS = 2_048
_KNOWN_STATUSES = frozenset({'succeeded', 'failed', 'cancelled', 'released'})
SettlementStatus = Literal['succeeded', 'failed', 'cancelled', 'released']


@dataclass(frozen=True)
class JITAttemptReservation:
    """Opaque capability for settling one provider attempt."""

    owner_uid: str
    run_id: str
    contract_version: str
    ordinal: int
    max_attempts: int
    reservation_token: str
    reserved_micro_usd: int


def _doc_id(owner_uid: str, run_id: str) -> str:
    return sha256(f'{owner_uid}\x00{run_id}'.encode('utf-8')).hexdigest()


def _client() -> Any:
    """Use the selected Firestore client; never fall back to local state."""

    return get_firestore_client()


def _positive_int(value: object, *, name: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0 or value > maximum:
        raise ValueError(f'{name} must be an integer in the range 1..{maximum}')
    return value


def _nonnegative_int(value: object, *, name: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > maximum:
        raise ValueError(f'{name} must be an integer in the range 0..{maximum}')
    return value


def _worst_case_cost_micro_usd(
    *,
    provider: str,
    model: str,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int,
    cache_ttl: str | None,
) -> tuple[int, str]:
    """Price the caller's bounded token envelope using the checked-in card."""

    input_tokens = _nonnegative_int(input_tokens, name='input_tokens', maximum=MAX_INPUT_TOKENS)
    cached_input_tokens = _nonnegative_int(cached_input_tokens, name='cached_input_tokens', maximum=MAX_INPUT_TOKENS)
    output_tokens = _nonnegative_int(output_tokens, name='output_tokens', maximum=MAX_OUTPUT_TOKENS)
    cache_write_tokens = _nonnegative_int(cache_write_tokens, name='cache_write_tokens', maximum=MAX_INPUT_TOKENS)
    if cache_ttl not in {None, '5m', '1h'}:
        raise ValueError('cache_ttl must be absent, 5m, or 1h')
    total_context_tokens = input_tokens + cached_input_tokens + cache_write_tokens
    if total_context_tokens > MAX_INPUT_TOKENS:
        raise ValueError('JIT input token envelope exceeds the qualification ceiling')
    card = rate_card_for(provider, model)
    if card is None:
        raise ValueError('JIT provider/model has no trusted rate card')
    rates = card.effective_rates(total_context_tokens)
    cache_write_rate = (
        rates.cache_write_1h_micro_usd_per_million if cache_ttl == '1h' else rates.cache_write_micro_usd_per_million
    )
    if cache_write_tokens and cache_write_rate is None:
        raise ValueError('JIT cache-write envelope has no trusted rate')
    numerator = (
        input_tokens * rates.input_micro_usd_per_million
        + cached_input_tokens * rates.cached_input_micro_usd_per_million
        + output_tokens * rates.output_micro_usd_per_million
    )
    if cache_write_rate is not None:
        numerator += cache_write_tokens * cache_write_rate
    return max(rounded_micro_usd(numerator), 0), card.rate_card_id


def reserve_jit_provider_attempt(
    *,
    owner_uid: str,
    run_id: str,
    contract_version: str,
    max_attempts: int,
    max_spend_micro_usd: int,
    provider: str,
    model: str,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int,
    cache_ttl: str | None = None,
) -> JITAttemptReservation | None:
    """Reserve one priced attempt atomically, or return ``None`` if blocked."""

    if not owner_uid or not run_id or not contract_version:
        raise ValueError('JIT budget identity is required')
    max_attempts = _positive_int(max_attempts, name='max_attempts', maximum=MAX_ATTEMPTS)
    max_spend_micro_usd = _positive_int(max_spend_micro_usd, name='max_spend_micro_usd', maximum=MAX_SPEND_MICRO_USD)
    reserved_micro_usd, rate_card_id = _worst_case_cost_micro_usd(
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        cache_write_tokens=cache_write_tokens,
        cache_ttl=cache_ttl,
    )
    if reserved_micro_usd <= 0 or reserved_micro_usd > max_spend_micro_usd:
        return None

    db = _client()
    ref = db.collection(_COLLECTION).document(_doc_id(owner_uid, run_id))
    transaction = db.transaction()
    reservation_token = secrets.token_urlsafe(18)

    @firestore.transactional
    def transact(tx: Any) -> int | None:
        snapshot = ref.get(transaction=tx)
        data = snapshot.to_dict() if snapshot.exists else {}
        if data:
            if (
                data.get('owner_uid') != owner_uid
                or data.get('run_id') != run_id
                or data.get('contract_version') != contract_version
                or int(data.get('max_attempts', max_attempts)) != max_attempts
                or int(data.get('max_spend_micro_usd', max_spend_micro_usd)) != max_spend_micro_usd
            ):
                raise ValueError('JIT budget identity changed during one execution')
        if data.get('blocked') is True or data.get('active_reservation'):
            return None
        attempts = int(data.get('reserved_attempts', 0))
        settled = int(data.get('settled_spend_micro_usd', 0))
        if attempts >= max_attempts or settled + reserved_micro_usd > max_spend_micro_usd:
            return None
        ordinal = attempts + 1
        tx.set(
            ref,
            {
                'owner_uid': owner_uid,
                'run_id': run_id,
                'contract_version': contract_version,
                'max_attempts': max_attempts,
                'max_spend_micro_usd': max_spend_micro_usd,
                'reserved_attempts': ordinal,
                'settled_attempts': int(data.get('settled_attempts', 0)),
                'settled_spend_micro_usd': settled,
                'blocked': False,
                'active_reservation': {
                    'token': reservation_token,
                    'ordinal': ordinal,
                    'reserved_micro_usd': reserved_micro_usd,
                    'rate_card_id': rate_card_id,
                },
            },
            merge=True,
        )
        return ordinal

    ordinal = transact(transaction)
    if ordinal is None:
        return None
    return JITAttemptReservation(
        owner_uid=owner_uid,
        run_id=run_id,
        contract_version=contract_version,
        ordinal=ordinal,
        max_attempts=max_attempts,
        reservation_token=reservation_token,
        reserved_micro_usd=reserved_micro_usd,
    )


def settle_jit_provider_attempt(
    *,
    reservation: JITAttemptReservation,
    cost_micro_usd: object,
    status: SettlementStatus,
) -> bool:
    """Settle a trusted result; unknown cost permanently blocks the run."""

    if status not in _KNOWN_STATUSES:
        raise ValueError('invalid JIT settlement status')
    if cost_micro_usd is not None:
        if isinstance(cost_micro_usd, bool) or not isinstance(cost_micro_usd, int) or cost_micro_usd < 0:
            raise ValueError('cost_micro_usd must be a nonnegative integer')
    db = _client()
    ref = db.collection(_COLLECTION).document(_doc_id(reservation.owner_uid, reservation.run_id))
    transaction = db.transaction()

    @firestore.transactional
    def transact(tx: Any) -> bool:
        snapshot = ref.get(transaction=tx)
        if not snapshot.exists:
            return False
        data = snapshot.to_dict() or {}
        if (
            data.get('owner_uid') != reservation.owner_uid
            or data.get('run_id') != reservation.run_id
            or data.get('contract_version') != reservation.contract_version
            or int(data.get('max_attempts', -1)) != reservation.max_attempts
        ):
            return False
        if data.get('blocked') is True:
            return False
        active = data.get('active_reservation')
        if not isinstance(active, dict) or active.get('token') != reservation.reservation_token:
            return False
        if int(active.get('ordinal', -1)) != reservation.ordinal:
            return False
        # A reservation that was never sent to a provider can be released
        # with a trusted zero cost.  Unknown provider outcomes continue to
        # block the run permanently; callers must opt into this path only
        # after checking the deadline before the provider call.
        if status == 'released' and cost_micro_usd == 0:
            tx.update(
                ref,
                {
                    'blocked': False,
                    'cost_status': 'released',
                    'settled_attempts': int(data.get('settled_attempts', 0)) + 1,
                    'active_reservation': None,
                },
            )
            return True
        if cost_micro_usd is None or status != 'succeeded':
            tx.update(
                ref,
                {
                    'blocked': True,
                    'cost_status': 'unknown' if cost_micro_usd is None else status,
                },
            )
            return False
        reserved = int(active.get('reserved_micro_usd', -1))
        settled = int(data.get('settled_spend_micro_usd', 0))
        limit = int(data.get('max_spend_micro_usd', MAX_SPEND_MICRO_USD))
        if cost_micro_usd > reserved or settled + cost_micro_usd > limit:
            tx.update(
                ref,
                {
                    'blocked': True,
                    'cost_status': 'over_reserved',
                    'settled_spend_micro_usd': settled + cost_micro_usd,
                    'active_reservation': None,
                },
            )
            return False
        tx.update(
            ref,
            {
                'blocked': False,
                'cost_status': status,
                'settled_attempts': int(data.get('settled_attempts', 0)) + 1,
                'settled_spend_micro_usd': settled + cost_micro_usd,
                'active_reservation': None,
            },
        )
        return True

    return bool(transact(transaction))
