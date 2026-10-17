"""Versioned immutable input-cost cards for shadow units, never admission authority."""

from __future__ import annotations

import hashlib
import json
import os
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_EVEN
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from config.rate_card_versions import RATE_CARD_SHA256
from config.plan_catalog_generated import ENTITLEMENT_VERSIONS
from config.stt_provider_policy import DEEPGRAM_CLOUD_PROVIDER, provider_for_model_token

EXCLUDED_FUNDING = frozenset({'byok', 'custom', 'on_device'})


def get_rate_card_version() -> str:
    """Return the selected immutable rate card; production defaults to v1."""
    version = os.getenv('RATE_CARD_VERSION', 'v1')
    if version not in RATE_CARD_SHA256:
        raise ValueError(f'unsupported RATE_CARD_VERSION: {version!r}')
    return version


def _resolve_rate_card_version(version: str | None = None) -> str:
    selected = get_rate_card_version() if version is None else version
    if selected not in RATE_CARD_SHA256:
        raise ValueError(f'unsupported rate card version: {selected!r}')
    return selected


@lru_cache(maxsize=2)
def _load_card(version: str) -> dict[str, Any]:
    if version not in RATE_CARD_SHA256:
        raise ValueError(f'unsupported rate card version: {version!r}')
    raw = Path(__file__).with_name(f'rate_card_{version}.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != RATE_CARD_SHA256[version]:
        raise ValueError(f'rate card {version} changed: publish a new version file')
    value = json.loads(raw)
    if value['version'] != version or value['unit_usd_micros'] != 1000:
        raise ValueError('invalid rate card identity or unit')
    return value


def _card(version: str | None = None) -> dict[str, Any]:
    return _load_card(_resolve_rate_card_version(version))


def get_rate_card(version: str | None = None) -> dict[str, Any]:
    """Return a detached card so a caller cannot mutate cached pricing."""
    from copy import deepcopy

    return deepcopy(_card(version))


def _d(value: Any) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError('nonnegative finite quantities required')
    return result


def _result(
    vendor_micro_usd: Decimal,
    status: str,
    *reasons: str,
    rate_card_version: str,
) -> dict[str, Any]:
    # One micro-unit is 1e-9 USD. Preserve fractions across hourly increments.
    micro_units = vendor_micro_usd * _d(_card(rate_card_version)['loading']['factor']) * 1000
    return {
        'micro_units': int(micro_units.to_integral_value(rounding=ROUND_HALF_EVEN)),
        'status': status,
        'reasons': list(reasons),
    }


def _funding(funding: str, *, rate_card_version: str) -> dict[str, Any] | None:
    if funding in EXCLUDED_FUNDING:
        return {
            'micro_units': 0,
            'status': 'complete',
            'reasons': ['excluded_funding'],
        }
    if funding != 'omi':
        return {
            'micro_units': 0,
            'status': 'missing',
            'reasons': ['funding_unknown'],
        }
    return None


def price_llm_attempt(event: Mapping[str, Any], *, rate_card_version: str | None = None) -> dict[str, Any]:
    """Price reported quantities at pinned list rates, never Flex/reservation rates."""
    version = _resolve_rate_card_version(rate_card_version)
    exclusion = _funding(str(event.get('payer', 'unknown')), rate_card_version=version)
    if exclusion is not None:
        return exclusion
    if event.get('usage_status') != 'confirmed':
        return _result(Decimal(0), 'missing', 'provider_usage_not_confirmed', rate_card_version=version)
    tool_reasons = ['tool_use_prompt_tokens_unpriced'] if _d(event.get('tool_use_prompt_tokens', 0)) else []
    key = f"{event.get('provider')}:{event.get('configured_model')}"
    rt = _card(version)['realtime_models'].get(key)
    if rt:
        modalities = event.get('modality_tokens')
        if isinstance(modalities, Mapping):
            rates = rt['rates_micro_usd_per_million']
            cost = Decimal(0)
            for modality in ('text', 'audio', 'image'):
                cached = _d(modalities.get(f'cached_{modality}', 0))
                uncached = max(_d(modalities.get(f'input_{modality}', 0)) - cached, Decimal(0))
                cost += uncached * rates[f'input_{modality}'] + cached * rates[f'cached_{modality}']
            output_text = _d(modalities.get('output_text', 0))
            if not event.get('output_tokens_include_reasoning', False):
                output_text += _d(event.get('reasoning_tokens', 0))
            cost += output_text * rates['output_text']
            cost += _d(modalities.get('output_audio', 0)) * rates['output_audio']
            if cost:
                return _result(
                    cost / 1_000_000,
                    'estimated' if tool_reasons else 'complete',
                    *tool_reasons,
                    rate_card_version=version,
                )
            reason = 'empty_provider_usage'
        else:
            reason = 'realtime_modality_counts_missing'
        # Legacy realtime events may retain a caller-priced amount instead of usable splits.
        if (
            event.get('rate_card_id') == rt['reference_rate_card_id']
            and event.get('estimated_cost_micro_usd') is not None
        ):
            return _result(
                _d(event['estimated_cost_micro_usd']), 'estimated', reason, *tool_reasons, rate_card_version=version
            )
        return _result(Decimal(0), 'missing', reason, *tool_reasons, rate_card_version=version)
    if event.get('unit_type') == 'images':
        cards = [
            c
            for c in _card(version)['images']
            if c['provider'] == event.get('provider')
            and c['model'] == event.get('configured_model')
            and c['size'] == event.get('image_size')
            and c['quality'] == event.get('image_quality')
        ]
        if not cards:
            return _result(Decimal(0), 'missing', 'image_card_missing', rate_card_version=version)
        return _result(
            _d(event.get('image_count', 0)) * cards[0]['micro_usd_per_image'],
            'estimated',
            'image_prompt_tokens_missing',
            rate_card_version=version,
        )
    card = _card(version)['models'].get(key)
    if not card:
        return _result(Decimal(0), 'missing', 'model_card_missing', rate_card_version=version)
    cached = _d(event.get('cached_input_tokens', 0))
    written = _d(event.get('cache_write_tokens', 0))
    uncached = _d(
        event.get('uncached_input_tokens', max(_d(event.get('prompt_tokens', 0)) - cached - written, Decimal(0)))
    )
    output = _d(event.get('output_tokens', 0))
    if not event.get('output_tokens_include_reasoning', False):
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
    if event.get('provider') == 'gemini':
        modalities = event.get('modality_tokens') or {}
        audio = (
            event.get('has_audio')
            or 'audio' in (event.get('input_modalities') or [])
            or any(
                _d(event.get(name, 0)) for name in ('input_audio_tokens', 'cached_audio_tokens', 'output_audio_tokens')
            )
            or any(_d(modalities.get(name, 0)) for name in ('input_audio', 'cached_audio', 'output_audio'))
        )
        if audio:
            reasons.append('audio_modality_rate_missing')
        reasons.extend(tool_reasons)
        if (audio or tool_reasons) and status != 'missing':
            status = 'estimated'
    return _result(cost / 1_000_000, status, *reasons, rate_card_version=version)


def normalize_transcription_provider(provider: Any) -> str:
    provider = str(getattr(provider, 'value', provider)).strip().lower()
    if provider == DEEPGRAM_CLOUD_PROVIDER or provider_for_model_token(provider) == DEEPGRAM_CLOUD_PROVIDER:
        provider = 'deepgram'
    return provider


def price_transcription(
    seconds: Any,
    *,
    provider: str = 'unknown',
    funding: str = 'omi',
    accepted: bool = False,
    rate_card_version: str | None = None,
) -> dict[str, Any]:
    version = _resolve_rate_card_version(rate_card_version)
    exclusion = _funding(funding, rate_card_version=version)
    if exclusion is not None:
        return exclusion
    provider = normalize_transcription_provider(provider)
    card = _card(version)['transcription'].get(provider, _card(version)['transcription']['unknown'])
    quantity = _d(seconds)
    if not accepted:
        quantity *= _d(_card(version)['speech_ratio'])
    status = card['status'] if accepted else 'estimated'
    if status == 'card':
        status = 'complete'
    reasons = [] if accepted else ['elapsed_times_speech_ratio']
    if provider not in _card(version)['transcription'] or provider == 'unknown':
        reasons.append('provider_unknown')
    if card['status'] == 'provisional':
        reasons.append('provisional_provider_rate')
    return _result(quantity * card['micro_usd_per_hour'] / 3600, status, *reasons, rate_card_version=version)


def price_request(
    feature: str, count: Any = 1, *, funding: str = 'omi', rate_card_version: str | None = None
) -> dict[str, Any]:
    version = _resolve_rate_card_version(rate_card_version)
    exclusion = _funding(funding, rate_card_version=version)
    if exclusion is not None:
        return exclusion
    card = _card(version)['requests'].get(feature)
    if card is None:
        return _result(Decimal(0), 'missing', 'request_card_missing', rate_card_version=version)
    # Infra placeholder is already loaded, so do not apply L a second time.
    return {
        'micro_units': int((_d(count) * card['micro_usd_per_request'] * 1000).to_integral_value()),
        'status': 'provisional',
        'reasons': ['request_volume_unmeasured'],
    }


def standard_chat_units(rate_card_version: str | None = None) -> Decimal:
    version = _resolve_rate_card_version(rate_card_version)
    standard = _card(version)['standard_chat']
    priced = price_llm_attempt(
        {**standard, 'payer': 'omi', 'configured_model': standard['model'], 'usage_status': 'confirmed'},
        rate_card_version=version,
    )
    return Decimal(priced['micro_units']) / 1_000_000


def free_budget_units(rate_card_version: str | None = None) -> int:
    version = _resolve_rate_card_version(rate_card_version)
    return _mix_budget_units(ENTITLEMENT_VERSIONS['ladder_v1']['monthly_budgets']['basic'], version)


def budget_units(entitlements: Mapping[str, Any], rate_card_version: str | None = None) -> int | None:
    version = _resolve_rate_card_version(rate_card_version)
    budget = entitlements.get('budget')
    if not budget:
        return None
    if budget['kind'] == 'units':
        return int(budget['value'])
    if budget['kind'] == 'rate_card_mix':
        return _mix_budget_units(budget, version)
    raise ValueError('unknown budget expression')


def _mix_budget_units(budget: Mapping[str, Any], rate_card_version: str) -> int:
    if budget['chat_tier'] != 'standard':
        raise ValueError('unknown budget chat tier')
    speech = price_transcription(
        budget['speech_seconds'],
        provider=_card(rate_card_version)['default_speech_provider'],
        accepted=True,
        rate_card_version=rate_card_version,
    )
    total = Decimal(speech['micro_units']) / 1_000_000 + _d(budget['chat_messages']) * standard_chat_units(
        rate_card_version
    )
    return int(total.to_integral_value(rounding=ROUND_CEILING))


def _speech_hour_units(mix: Mapping[str, Any], rate_card_version: str) -> Decimal:
    # Shares describe accepted speech, not session-start counts. No observed mix:
    # use the pinned conservative Free-routable managed maximum, never cheapest.
    shares = mix.get('speech_provider_shares')
    if shares is None:
        shares = {mix.get('speech_provider', _card(rate_card_version)['default_speech_provider']): 1}
    if not isinstance(shares, Mapping) or not shares:
        raise ValueError('speech_provider_shares must be a nonempty provider/share mapping')
    weights = {provider: _d(share) for provider, share in shares.items()}
    if sum(weights.values()) != 1:
        raise ValueError('speech_provider_shares must sum to 1')
    total = Decimal(0)
    for provider, share in weights.items():
        if provider not in _card(rate_card_version)['transcription'] or provider == 'unknown':
            raise ValueError('display speech provider requires a known rate')
        total += (
            share
            * Decimal(
                price_transcription(
                    3600,
                    provider=provider,
                    accepted=True,
                    rate_card_version=rate_card_version,
                )['micro_units']
            )
            / 1_000_000
        )
    return total


def display_equivalents(
    remaining_units: Any,
    mix: Mapping[str, Any] | None = None,
    *,
    rate_card_version: str | None = None,
) -> dict[str, float]:
    version = _resolve_rate_card_version(rate_card_version)
    mix = mix or {}
    remaining = _d(remaining_units)
    recording_hour = _speech_hour_units(mix, version) + _d(mix.get('recording_overhead_units_per_hour', 0))
    chat = standard_chat_units(version) + _d(mix.get('chat_overhead_units', 0))
    return {
        'recording_hours': float(remaining / recording_hour) if recording_hour else 0.0,
        'chat_messages': float(remaining / chat) if chat else 0.0,
    }


@lru_cache(maxsize=1)
def _recording_rate_card() -> dict[str, Any]:
    """Versioned presentation rates; v1 event pricing and historical identities stay intact."""
    raw = Path(__file__).with_name('rate_card_v2.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != RATE_CARD_SHA256['v2']:
        raise ValueError('recording card changed: publish a new version file')
    card = json.loads(raw)
    if card['version'] != 'v2' or card['unit_usd_micros'] != 1000:
        raise ValueError('invalid recording rate card')
    return card


def recording_rate_card() -> dict[str, Any]:
    from copy import deepcopy

    return deepcopy(_recording_rate_card())


def recording_units_per_hour(lane: str | None = None) -> Decimal:
    recording = recording_rate_card()['recording']
    rates = recording['units_per_recorded_hour']
    if lane == 'on_device':
        return _d(recording['on_device_transcription_units_per_hour'])
    live, batch = _d(rates['live']), _d(rates['batch'])
    if live <= 0 or batch <= 0:
        raise ValueError('cloud recording rates must be positive')
    if lane in {'live', 'batch'}:
        return live if lane == 'live' else batch
    if lane is not None:
        raise ValueError('unknown recording lane')
    background = _d(recording['background_share'])
    if background > 1:
        raise ValueError('background share must be at most one')
    return live * (1 - background) + batch * background
