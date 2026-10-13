"""Immutable input-cost card for shadow units; never an admission authority."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_EVEN
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

V1_SHA256 = '333f224bf4fec44954d92d2e76b1a99cc14d31651b71fa4ac778123281ecd258'
EXCLUDED_FUNDING = frozenset({'byok', 'custom', 'on_device'})


@lru_cache(maxsize=1)
def _card() -> dict[str, Any]:
    raw = Path(__file__).with_name('rate_card_v1.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != V1_SHA256:
        raise ValueError('rate card v1 changed: publish a new version file')
    value = json.loads(raw)
    if value['version'] != 'v1' or value['unit_usd_micros'] != 1000:
        raise ValueError('invalid rate card identity or unit')
    return value


def get_rate_card() -> dict[str, Any]:
    """Return a detached card so a caller cannot mutate cached pricing."""
    from copy import deepcopy

    return deepcopy(_card())


def _d(value: Any) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError('nonnegative finite quantities required')
    return result


def _result(vendor_micro_usd: Decimal, status: str, *reasons: str) -> dict[str, Any]:
    # One micro-unit is 1e-9 USD. Preserve fractions across hourly increments.
    micro_units = vendor_micro_usd * _d(_card()['loading']['factor']) * 1000
    return {
        'micro_units': int(micro_units.to_integral_value(rounding=ROUND_HALF_EVEN)),
        'status': status,
        'reasons': list(reasons),
    }


def _funding(funding: str) -> dict[str, Any] | None:
    if funding in EXCLUDED_FUNDING:
        return {'micro_units': 0, 'status': 'complete', 'reasons': ['excluded_funding']}
    if funding != 'omi':
        return {'micro_units': 0, 'status': 'missing', 'reasons': ['funding_unknown']}
    return None


def price_llm_attempt(event: Mapping[str, Any]) -> dict[str, Any]:
    """Price reported quantities at pinned list rates, never Flex/reservation rates."""
    exclusion = _funding(str(event.get('payer', 'unknown')))
    if exclusion is not None:
        return exclusion
    if event.get('usage_status') != 'confirmed':
        return _result(Decimal(0), 'missing', 'provider_usage_not_confirmed')
    key = f"{event.get('provider')}:{event.get('configured_model')}"
    rt = _card()['realtime_models'].get(key)
    if rt:
        modalities = event.get('modality_tokens')
        if not isinstance(modalities, Mapping):
            # Current realtime ledger retains a caller-priced list-card amount, not modality splits.
            if (
                event.get('rate_card_id') == rt['reference_rate_card_id']
                and event.get('estimated_cost_micro_usd') is not None
            ):
                return _result(_d(event['estimated_cost_micro_usd']), 'estimated', 'realtime_modality_counts_missing')
            return _result(Decimal(0), 'missing', 'realtime_modality_counts_missing')
        rates = rt['rates_micro_usd_per_million']
        cost = Decimal(0)
        for modality in ('text', 'audio', 'image'):
            cached = _d(modalities.get(f'cached_{modality}', 0))
            uncached = max(_d(modalities.get(f'input_{modality}', 0)) - cached, Decimal(0))
            cost += uncached * rates[f'input_{modality}'] + cached * rates[f'cached_{modality}']
        cost += _d(modalities.get('output_text', 0)) * rates['output_text']
        cost += _d(modalities.get('output_audio', 0)) * rates['output_audio']
        return _result(cost / 1_000_000, 'complete')
    if event.get('unit_type') == 'images':
        cards = [
            c
            for c in _card()['images']
            if c['provider'] == event.get('provider')
            and c['model'] == event.get('configured_model')
            and c['size'] == event.get('image_size')
            and c['quality'] == event.get('image_quality')
        ]
        if not cards:
            return _result(Decimal(0), 'missing', 'image_card_missing')
        return _result(
            _d(event.get('image_count', 0)) * cards[0]['micro_usd_per_image'],
            'estimated',
            'image_prompt_tokens_missing',
        )
    card = _card()['models'].get(key)
    if not card:
        return _result(Decimal(0), 'missing', 'model_card_missing')
    cached = _d(event.get('cached_input_tokens', 0))
    written = _d(event.get('cache_write_tokens', 0))
    uncached = _d(
        event.get('uncached_input_tokens', max(_d(event.get('prompt_tokens', 0)) - cached - written, Decimal(0)))
    )
    output = _d(event.get('output_tokens', 0))
    if not event.get('output_tokens_include_reasoning', True):
        output += _d(event.get('reasoning_tokens', 0))
    prefix = (
        'long_context_' if uncached + cached + written > card.get('long_context_threshold_tokens', float('inf')) else ''
    )
    cost = (
        uncached * card[prefix + 'input_micro_usd_per_million']
        + cached * card[prefix + 'cached_input_micro_usd_per_million']
        + output * card[prefix + 'output_micro_usd_per_million']
    )
    status = 'provisional' if card['status'] == 'provisional' else 'complete'
    reasons = []
    if written:
        suffix = (
            'cache_write_1h_micro_usd_per_million'
            if event.get('cache_write_ttl') == '1h'
            else 'cache_write_micro_usd_per_million'
        )
        rate = card.get(prefix + suffix)
        if rate is None or event.get('cache_write_ttl') == 'mixed':
            status = 'missing'
            reasons.append('cache_write_rate_missing')
        else:
            cost += written * rate
    # Token counts can be empty on a failed call whose provider bill is unknown.
    if not (uncached + cached + written + output):
        status = 'missing'
        reasons.append('empty_provider_usage')
    return _result(cost / 1_000_000, status, *reasons)


def price_transcription(
    seconds: Any, *, provider: str = 'unknown', funding: str = 'omi', accepted: bool = False
) -> dict[str, Any]:
    exclusion = _funding(funding)
    if exclusion is not None:
        return exclusion
    card = _card()['transcription'].get(provider, _card()['transcription']['unknown'])
    quantity = _d(seconds)
    if not accepted:
        quantity *= _d(_card()['speech_ratio'])
    status = card['status'] if accepted else 'estimated'
    if status == 'card':
        status = 'complete'
    reasons = [] if accepted else ['elapsed_times_speech_ratio']
    if provider not in _card()['transcription'] or provider == 'unknown':
        reasons.append('provider_unknown')
    if card['status'] == 'provisional':
        reasons.append('provisional_provider_rate')
    return _result(quantity * card['micro_usd_per_hour'] / 3600, status, *reasons)


def price_request(feature: str, count: Any = 1, *, funding: str = 'omi') -> dict[str, Any]:
    exclusion = _funding(funding)
    if exclusion is not None:
        return exclusion
    card = _card()['requests'][feature]
    # Infra placeholder is already loaded, so do not apply L a second time.
    return {
        'micro_units': int((_d(count) * card['micro_usd_per_request'] * 1000).to_integral_value()),
        'status': 'provisional',
        'reasons': ['request_volume_unmeasured'],
    }


def standard_chat_units() -> Decimal:
    standard = _card()['standard_chat']
    priced = price_llm_attempt(
        {**standard, 'payer': 'omi', 'configured_model': standard['model'], 'usage_status': 'confirmed'}
    )
    return Decimal(priced['micro_units']) / 1_000_000


def free_budget_units() -> int:
    speech = price_transcription(18000, provider=_card()['default_speech_provider'], accepted=True)
    total = Decimal(speech['micro_units']) / 1_000_000 + 30 * standard_chat_units()
    return int(total.to_integral_value(rounding=ROUND_CEILING))


def budget_units(entitlements: Mapping[str, Any]) -> int | None:
    budget = entitlements.get('budget')
    if not budget:
        return None
    if budget['kind'] == 'units':
        return int(budget['value'])
    if budget['kind'] == 'rate_card_mix':
        return free_budget_units()
    raise ValueError('unknown budget expression')


def display_equivalents(remaining_units: Any, mix: Mapping[str, Any] | None = None) -> dict[str, float]:
    mix = mix or {}
    remaining = _d(remaining_units)
    speech = price_transcription(
        3600, provider=mix.get('speech_provider', _card()['default_speech_provider']), accepted=True
    )
    recording_hour = Decimal(speech['micro_units']) / 1_000_000 + _d(mix.get('recording_overhead_units_per_hour', 0))
    chat = standard_chat_units() + _d(mix.get('chat_overhead_units', 0))
    return {
        'recording_hours': float(remaining / recording_hour) if recording_hour else 0.0,
        'chat_messages': float(remaining / chat) if chat else 0.0,
    }
