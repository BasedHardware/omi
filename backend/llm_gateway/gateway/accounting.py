"""Provider-neutral, cache-aware accounting primitives for the LLM gateway.

The gateway records a ledger event for every provider attempt.  These objects
intentionally contain only bounded routing and billing metadata; prompts,
provider payloads, headers, and credentials never enter the accounting path.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import yaml

RATE_CARD_FILE = Path(__file__).resolve().parents[1] / 'config' / 'cost_rate_cards.yaml'
MICRO_USD_PER_USD = 1_000_000
TOKENS_PER_MILLION = 1_000_000


class CacheStatus(StrEnum):
    HIT = 'hit'
    PARTIAL_HIT = 'partial_hit'
    MISS = 'miss'
    NO_CACHE_READ_OBSERVED = 'no_cache_read_observed'
    NOT_REQUESTED = 'not_requested'
    NOT_REPORTED = 'not_reported'
    NOT_APPLICABLE = 'not_applicable'


class UsageStatus(StrEnum):
    CONFIRMED = 'confirmed'
    NOT_REPORTED = 'not_reported'
    INDETERMINATE = 'indeterminate'


class CostStatus(StrEnum):
    ESTIMATED = 'estimated'
    UNPRICED = 'unpriced'
    INDETERMINATE = 'indeterminate'
    NOT_OMI_COST = 'not_omi_cost'


@dataclass(frozen=True)
class ProviderUsage:
    """Normalized billable units reported by an upstream provider."""

    prompt_tokens: int = 0
    cached_input_tokens: int = 0
    uncached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    output_tokens_include_reasoning: bool = False
    tool_use_prompt_tokens: int = 0
    cache_write_tokens: int = 0
    cache_write_ttl: str | None = None
    total_tokens: int = 0
    cache_status: CacheStatus = CacheStatus.NOT_REPORTED
    unit_type: str = 'tokens'
    image_count: int = 0
    image_size: str | None = None
    image_quality: str | None = None

    @property
    def billable_output_tokens(self) -> int:
        # OpenAI completion tokens already include its reasoning-token subset;
        # Vertex reports thought tokens separately from candidate output.
        return (
            self.output_tokens if self.output_tokens_include_reasoning else self.output_tokens + self.reasoning_tokens
        )


@dataclass(frozen=True)
class ProviderResponseMetadata:
    usage: ProviderUsage | None = None
    provider_response_id: str | None = None
    actual_model_version: str | None = None
    traffic_type: str | None = None


@dataclass(frozen=True)
class ProviderAttempt:
    ordinal: int
    provider: str
    configured_model: str
    route_artifact_id: str | None
    fallback_reason: str | None
    retry_ordinal: int
    outcome: str
    error_class: str
    usage: ProviderUsage | None = None
    usage_status: UsageStatus = UsageStatus.NOT_REPORTED
    provider_response_id: str | None = None
    actual_model_version: str | None = None
    traffic_type: str | None = None


@dataclass
class AttemptTrace:
    """Ordered attempt trace for one logical gateway invocation."""

    attempts: list[ProviderAttempt] = field(default_factory=list)

    def record(
        self,
        *,
        provider: str,
        configured_model: str,
        route_artifact_id: str | None,
        fallback_reason: str | None,
        retry_ordinal: int,
        outcome: str,
        error_class: str,
        metadata: ProviderResponseMetadata | None = None,
        usage_status: UsageStatus | None = None,
    ) -> ProviderAttempt:
        response_metadata = metadata or ProviderResponseMetadata()
        status = usage_status or (
            UsageStatus.CONFIRMED if response_metadata.usage is not None else UsageStatus.NOT_REPORTED
        )
        attempt = ProviderAttempt(
            ordinal=len(self.attempts) + 1,
            provider=provider,
            configured_model=configured_model,
            route_artifact_id=route_artifact_id,
            fallback_reason=fallback_reason,
            retry_ordinal=retry_ordinal,
            outcome=outcome,
            error_class=error_class,
            usage=response_metadata.usage,
            usage_status=status,
            provider_response_id=response_metadata.provider_response_id,
            actual_model_version=response_metadata.actual_model_version,
            traffic_type=response_metadata.traffic_type,
        )
        self.attempts.append(attempt)
        return attempt


@dataclass(frozen=True)
class AccountingContext:
    invocation_id: str
    request_id: str
    caller: str
    user_uid: str | None
    feature: str | None
    api_surface: str
    payer: str

    @classmethod
    def create(
        cls,
        *,
        request_id: str,
        caller: str,
        user_uid: str | None,
        feature: str | None,
        api_surface: str,
        payer: str,
    ) -> 'AccountingContext':
        return cls(
            invocation_id=str(uuid4()),
            request_id=request_id,
            caller=caller,
            user_uid=user_uid,
            feature=feature,
            api_surface=api_surface,
            payer=payer,
        )


@dataclass(frozen=True)
class RateCard:
    rate_card_id: str
    provider: str
    model: str
    input_micro_usd_per_million: int
    cached_input_micro_usd_per_million: int
    output_micro_usd_per_million: int
    cache_write_micro_usd_per_million: int | None = None
    cache_write_1h_micro_usd_per_million: int | None = None


@dataclass(frozen=True)
class ImageRateCard:
    rate_card_id: str
    provider: str
    model: str
    size: str
    quality: str
    micro_usd_per_image: int


@dataclass(frozen=True)
class AccountingEvent:
    attempt_id: str
    invocation_id: str
    occurred_at: str
    date: str
    request_id: str
    caller: str
    user_uid: str | None
    feature: str | None
    api_surface: str
    payer: str
    provider: str
    configured_model: str
    actual_model_version: str | None
    traffic_type: str | None
    route_artifact_id: str | None
    retry_ordinal: int
    fallback_reason: str | None
    outcome: str
    error_class: str
    usage_status: UsageStatus
    prompt_tokens: int
    cached_input_tokens: int
    uncached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    output_tokens_include_reasoning: bool
    tool_use_prompt_tokens: int
    cache_write_tokens: int
    cache_write_ttl: str | None
    total_tokens: int
    cache_status: CacheStatus
    unit_type: str
    image_count: int
    image_size: str | None
    image_quality: str | None
    cost_status: CostStatus
    estimated_cost_micro_usd: int | None
    estimated_cache_savings_micro_usd: int | None
    rate_card_id: str | None
    cost_basis: str
    provider_response_id: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            'attempt_id': self.attempt_id,
            'invocation_id': self.invocation_id,
            'occurred_at': self.occurred_at,
            'date': self.date,
            'request_id': self.request_id,
            'caller': self.caller,
            'user_uid': self.user_uid,
            'feature': self.feature,
            'api_surface': self.api_surface,
            'payer': self.payer,
            'provider': self.provider,
            'configured_model': self.configured_model,
            'actual_model_version': self.actual_model_version,
            'traffic_type': self.traffic_type,
            'route_artifact_id': self.route_artifact_id,
            'retry_ordinal': self.retry_ordinal,
            'fallback_reason': self.fallback_reason,
            'outcome': self.outcome,
            'error_class': self.error_class,
            'usage_status': self.usage_status.value,
            'prompt_tokens': self.prompt_tokens,
            'cached_input_tokens': self.cached_input_tokens,
            'uncached_input_tokens': self.uncached_input_tokens,
            'output_tokens': self.output_tokens,
            'reasoning_tokens': self.reasoning_tokens,
            'output_tokens_include_reasoning': self.output_tokens_include_reasoning,
            'tool_use_prompt_tokens': self.tool_use_prompt_tokens,
            'cache_write_tokens': self.cache_write_tokens,
            'cache_write_ttl': self.cache_write_ttl,
            'total_tokens': self.total_tokens,
            'cache_status': self.cache_status.value,
            'unit_type': self.unit_type,
            'image_count': self.image_count,
            'image_size': self.image_size,
            'image_quality': self.image_quality,
            'cost_status': self.cost_status.value,
            'estimated_cost_micro_usd': self.estimated_cost_micro_usd,
            'estimated_cache_savings_micro_usd': self.estimated_cache_savings_micro_usd,
            'rate_card_id': self.rate_card_id,
            'cost_basis': self.cost_basis,
            'provider_response_id': self.provider_response_id,
        }


def openai_usage_from_response(
    response: Mapping[str, Any],
    *,
    cache_requested: bool = False,
) -> ProviderResponseMetadata:
    usage_value = response.get('usage')
    if not isinstance(usage_value, Mapping):
        return ProviderResponseMetadata(provider_response_id=_string_or_none(response.get('id')))
    raw_usage = cast(Mapping[str, Any], usage_value)
    if not _has_any_field(
        raw_usage, 'prompt_tokens', 'input_tokens', 'completion_tokens', 'output_tokens', 'total_tokens'
    ):
        return ProviderResponseMetadata(
            provider_response_id=_string_or_none(response.get('id')),
            actual_model_version=_string_or_none(response.get('model')),
        )
    usage = _openai_usage(raw_usage, cache_requested=cache_requested)
    return ProviderResponseMetadata(
        usage=usage,
        provider_response_id=_string_or_none(response.get('id')),
        actual_model_version=_string_or_none(response.get('model')),
    )


def openai_usage_from_sse_payload(
    payload: Mapping[str, Any],
    *,
    cache_requested: bool = False,
) -> ProviderResponseMetadata | None:
    if not isinstance(payload.get('usage'), Mapping):
        return None
    return openai_usage_from_response(payload, cache_requested=cache_requested)


def vertex_usage_from_response(response: Mapping[str, Any]) -> ProviderResponseMetadata:
    usage_value = response.get('usageMetadata')
    if not isinstance(usage_value, Mapping):
        return ProviderResponseMetadata(
            provider_response_id=_string_or_none(response.get('responseId')),
            actual_model_version=_string_or_none(response.get('modelVersion')),
            traffic_type=_string_or_none(response.get('trafficType')),
        )
    raw = cast(Mapping[str, Any], usage_value)
    if not _has_any_field(
        raw,
        'promptTokenCount',
        'cachedContentTokenCount',
        'candidatesTokenCount',
        'thoughtsTokenCount',
        'toolUsePromptTokenCount',
        'totalTokenCount',
    ):
        return ProviderResponseMetadata(
            provider_response_id=_string_or_none(response.get('responseId')),
            actual_model_version=_string_or_none(response.get('modelVersion')),
            traffic_type=_string_or_none(response.get('trafficType')),
        )
    prompt = _nonnegative_int(raw.get('promptTokenCount'))
    cached = min(prompt, _nonnegative_int(raw.get('cachedContentTokenCount')))
    candidates = _nonnegative_int(raw.get('candidatesTokenCount'))
    thoughts = _nonnegative_int(raw.get('thoughtsTokenCount'))
    tool_use = _nonnegative_int(raw.get('toolUsePromptTokenCount'))
    total = _nonnegative_int(raw.get('totalTokenCount'))
    if total == 0:
        total = prompt + candidates + thoughts
    cache_status = _cache_status(
        prompt_tokens=prompt,
        cached_tokens=cached,
        cache_requested=False,
        cache_field_reported='cachedContentTokenCount' in raw,
    )
    return ProviderResponseMetadata(
        usage=ProviderUsage(
            prompt_tokens=prompt,
            cached_input_tokens=cached,
            uncached_input_tokens=max(prompt - cached, 0),
            output_tokens=candidates,
            reasoning_tokens=thoughts,
            tool_use_prompt_tokens=tool_use,
            total_tokens=total,
            cache_status=cache_status,
        ),
        provider_response_id=_string_or_none(response.get('responseId')),
        actual_model_version=_string_or_none(response.get('modelVersion')),
        traffic_type=_string_or_none(response.get('trafficType')),
    )


def anthropic_usage_from_response(
    response: Mapping[str, Any],
    *,
    cache_requested: bool,
    cache_write_ttl: str | None = None,
) -> ProviderResponseMetadata:
    usage_value = response.get('usage')
    if not isinstance(usage_value, Mapping):
        return ProviderResponseMetadata(
            provider_response_id=_string_or_none(response.get('id')),
            actual_model_version=_string_or_none(response.get('model')),
        )
    raw = cast(Mapping[str, Any], usage_value)
    if not _has_any_field(
        raw, 'input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens', 'output_tokens'
    ):
        return ProviderResponseMetadata(
            provider_response_id=_string_or_none(response.get('id')),
            actual_model_version=_string_or_none(response.get('model')),
        )
    uncached = _nonnegative_int(raw.get('input_tokens'))
    cached = _nonnegative_int(raw.get('cache_read_input_tokens'))
    cache_write = _nonnegative_int(raw.get('cache_creation_input_tokens'))
    output = _nonnegative_int(raw.get('output_tokens'))
    return ProviderResponseMetadata(
        usage=ProviderUsage(
            prompt_tokens=uncached + cached,
            cached_input_tokens=cached,
            uncached_input_tokens=uncached,
            output_tokens=output,
            cache_write_tokens=cache_write,
            cache_write_ttl=cache_write_ttl if cache_write else None,
            total_tokens=uncached + cached + output,
            cache_status=_cache_status(
                prompt_tokens=uncached + cached,
                cached_tokens=cached,
                cache_requested=cache_requested,
                cache_field_reported='cache_read_input_tokens' in raw,
            ),
        ),
        provider_response_id=_string_or_none(response.get('id')),
        actual_model_version=_string_or_none(response.get('model')),
    )


def image_usage(*, count: int, size: object, quality: object) -> ProviderUsage:
    return ProviderUsage(
        cache_status=CacheStatus.NOT_APPLICABLE,
        unit_type='images',
        image_count=max(count, 0),
        image_size=_string_or_none(size),
        image_quality=_string_or_none(quality),
    )


def cache_requested_for_openai_request(request: Mapping[str, Any]) -> bool:
    prompt_cache_key = request.get('prompt_cache_key')
    return isinstance(prompt_cache_key, str) and bool(prompt_cache_key.strip())


def cache_requested_for_anthropic_request(request: Mapping[str, Any]) -> bool:
    return any(_contains_cache_control(request.get(field)) for field in ('system', 'messages', 'tools'))


def cache_write_ttl_for_anthropic_request(request: Mapping[str, Any]) -> str | None:
    ttls = _cache_control_ttls([request.get(field) for field in ('system', 'messages', 'tools')])
    if len(ttls) == 1:
        return next(iter(ttls))
    return 'mixed' if ttls else None


def build_accounting_event(context: AccountingContext, attempt: ProviderAttempt) -> AccountingEvent:
    now = datetime.now(timezone.utc)
    usage = attempt.usage or ProviderUsage()
    cost_status, estimated_cost, cache_savings, rate_card_id, cost_basis = _estimate_cost(
        payer=context.payer,
        provider=attempt.provider,
        model=attempt.configured_model,
        usage=attempt.usage,
        usage_status=attempt.usage_status,
    )
    return AccountingEvent(
        attempt_id=f'{context.invocation_id}:{attempt.ordinal}',
        invocation_id=context.invocation_id,
        occurred_at=now.isoformat(),
        date=now.date().isoformat(),
        request_id=context.request_id,
        caller=context.caller,
        user_uid=context.user_uid,
        feature=context.feature,
        api_surface=context.api_surface,
        payer=context.payer,
        provider=attempt.provider,
        configured_model=attempt.configured_model,
        actual_model_version=attempt.actual_model_version,
        traffic_type=attempt.traffic_type,
        route_artifact_id=attempt.route_artifact_id,
        retry_ordinal=attempt.retry_ordinal,
        fallback_reason=attempt.fallback_reason,
        outcome=attempt.outcome,
        error_class=attempt.error_class,
        usage_status=attempt.usage_status,
        prompt_tokens=usage.prompt_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        uncached_input_tokens=usage.uncached_input_tokens,
        output_tokens=usage.output_tokens,
        reasoning_tokens=usage.reasoning_tokens,
        output_tokens_include_reasoning=usage.output_tokens_include_reasoning,
        tool_use_prompt_tokens=usage.tool_use_prompt_tokens,
        cache_write_tokens=usage.cache_write_tokens,
        cache_write_ttl=usage.cache_write_ttl,
        total_tokens=usage.total_tokens,
        cache_status=usage.cache_status,
        unit_type=usage.unit_type,
        image_count=usage.image_count,
        image_size=usage.image_size,
        image_quality=usage.image_quality,
        cost_status=cost_status,
        estimated_cost_micro_usd=estimated_cost,
        estimated_cache_savings_micro_usd=cache_savings,
        rate_card_id=rate_card_id,
        cost_basis=cost_basis,
        provider_response_id=attempt.provider_response_id,
    )


def _openai_usage(raw: Mapping[str, Any], *, cache_requested: bool) -> ProviderUsage:
    prompt = _nonnegative_int(raw.get('prompt_tokens', raw.get('input_tokens')))
    output = _nonnegative_int(raw.get('completion_tokens', raw.get('output_tokens')))
    details = raw.get('prompt_tokens_details', raw.get('input_tokens_details'))
    cached = _nonnegative_int(details.get('cached_tokens')) if isinstance(details, Mapping) else 0
    cached = min(prompt, cached)
    completion_details = raw.get('completion_tokens_details', raw.get('output_tokens_details'))
    reasoning = (
        _nonnegative_int(completion_details.get('reasoning_tokens')) if isinstance(completion_details, Mapping) else 0
    )
    # OpenAI reports reasoning tokens as a subset of completion tokens, so its
    # omitted total is prompt + completion (unlike Vertex thought tokens).
    total = _nonnegative_int(raw.get('total_tokens')) or prompt + output
    return ProviderUsage(
        prompt_tokens=prompt,
        cached_input_tokens=cached,
        uncached_input_tokens=max(prompt - cached, 0),
        output_tokens=output,
        reasoning_tokens=reasoning,
        output_tokens_include_reasoning=True,
        total_tokens=total,
        cache_status=_cache_status(
            prompt_tokens=prompt,
            cached_tokens=cached,
            cache_requested=cache_requested,
            cache_field_reported=isinstance(details, Mapping) and 'cached_tokens' in details,
        ),
    )


def _cache_status(
    *,
    prompt_tokens: int,
    cached_tokens: int,
    cache_requested: bool,
    cache_field_reported: bool,
) -> CacheStatus:
    if cached_tokens > 0:
        return CacheStatus.HIT if prompt_tokens > 0 and cached_tokens >= prompt_tokens else CacheStatus.PARTIAL_HIT
    if cache_requested:
        return CacheStatus.MISS
    if cache_field_reported:
        return CacheStatus.NO_CACHE_READ_OBSERVED
    return CacheStatus.NOT_REPORTED


def _contains_cache_control(value: object) -> bool:
    if isinstance(value, Mapping):
        if 'cache_control' in value:
            return True
        return any(_contains_cache_control(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_cache_control(item) for item in value)
    return False


def _cache_control_ttls(values: object) -> set[str]:
    ttls: set[str] = set()

    def collect(value: object) -> None:
        if isinstance(value, Mapping):
            cache_control = value.get('cache_control')
            if isinstance(cache_control, Mapping):
                ttl = cache_control.get('ttl')
                ttls.add(ttl if ttl in {'5m', '1h'} else '5m')
            for child in value.values():
                collect(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                collect(child)

    collect(values)
    return ttls


def _estimate_cost(
    *,
    payer: str,
    provider: str,
    model: str,
    usage: ProviderUsage | None,
    usage_status: UsageStatus,
) -> tuple[CostStatus, int | None, int | None, str | None, str]:
    if payer == 'byok':
        return CostStatus.NOT_OMI_COST, 0, 0, None, 'byok_not_omi_cogs'
    if usage_status == UsageStatus.INDETERMINATE:
        return CostStatus.INDETERMINATE, None, None, None, 'usage_indeterminate'
    if usage is None:
        return CostStatus.UNPRICED, None, None, None, 'provider_did_not_report_usage'
    if usage.unit_type == 'images':
        image_card = _image_rate_card_for(provider, model, usage.image_size, usage.image_quality)
        if image_card is None:
            return CostStatus.UNPRICED, None, None, None, 'image_rate_card_missing'
        return (
            CostStatus.ESTIMATED,
            usage.image_count * image_card.micro_usd_per_image,
            None,
            image_card.rate_card_id,
            (
                'per_image_generation_auto_estimate_excludes_prompt_input_tokens'
                if usage.image_size == 'auto' or usage.image_quality == 'auto'
                else 'per_image_generation_rate_excludes_prompt_input_tokens'
            ),
        )
    if usage.unit_type != 'tokens':
        return CostStatus.UNPRICED, None, None, None, 'non_token_unit_rate_missing'
    rate_card = _rate_card_for(provider, model)
    if rate_card is None:
        return CostStatus.UNPRICED, None, None, None, 'rate_card_missing'
    cache_write_rate = rate_card.cache_write_micro_usd_per_million
    if usage.cache_write_ttl == '1h':
        cache_write_rate = rate_card.cache_write_1h_micro_usd_per_million
    if usage.cache_write_tokens and (cache_write_rate is None or usage.cache_write_ttl == 'mixed'):
        return CostStatus.UNPRICED, None, None, rate_card.rate_card_id, 'cache_write_rate_missing_or_mixed_ttl'

    numerator = (
        usage.uncached_input_tokens * rate_card.input_micro_usd_per_million
        + usage.cached_input_tokens * rate_card.cached_input_micro_usd_per_million
        + usage.billable_output_tokens * rate_card.output_micro_usd_per_million
    )
    if cache_write_rate is not None:
        numerator += usage.cache_write_tokens * cache_write_rate
    cost = _rounded_micro_usd(numerator)
    savings = _rounded_micro_usd(
        usage.cached_input_tokens
        * max(rate_card.input_micro_usd_per_million - rate_card.cached_input_micro_usd_per_million, 0)
    )
    return CostStatus.ESTIMATED, cost, savings, rate_card.rate_card_id, 'marginal_token_rates_excludes_cache_storage'


def _rounded_micro_usd(numerator: int) -> int:
    return (numerator + TOKENS_PER_MILLION // 2) // TOKENS_PER_MILLION


@lru_cache(maxsize=1)
def _load_rate_cards() -> dict[tuple[str, str], RateCard]:
    with RATE_CARD_FILE.open('r', encoding='utf-8') as handle:
        raw = cast(object, yaml.safe_load(handle))
    if not isinstance(raw, Mapping) or not isinstance(raw.get('rate_cards'), list):
        raise ValueError(f'{RATE_CARD_FILE} must contain a rate_cards list')

    cards: dict[tuple[str, str], RateCard] = {}
    for item in cast(list[object], raw['rate_cards']):
        if not isinstance(item, Mapping):
            raise ValueError(f'{RATE_CARD_FILE} rate card entries must be mappings')
        card = RateCard(
            rate_card_id=_required_string(item, 'rate_card_id'),
            provider=_required_string(item, 'provider').lower(),
            model=_required_string(item, 'model'),
            input_micro_usd_per_million=_nonnegative_int(item.get('input_micro_usd_per_million')),
            cached_input_micro_usd_per_million=_nonnegative_int(item.get('cached_input_micro_usd_per_million')),
            output_micro_usd_per_million=_nonnegative_int(item.get('output_micro_usd_per_million')),
            cache_write_micro_usd_per_million=(
                _nonnegative_int(item['cache_write_micro_usd_per_million'])
                if item.get('cache_write_micro_usd_per_million') is not None
                else None
            ),
            cache_write_1h_micro_usd_per_million=(
                _nonnegative_int(item['cache_write_1h_micro_usd_per_million'])
                if item.get('cache_write_1h_micro_usd_per_million') is not None
                else None
            ),
        )
        key = (card.provider, card.model)
        if key in cards:
            raise ValueError(f'duplicate gateway rate card: {card.provider}/{card.model}')
        cards[key] = card
    return cards


def _rate_card_for(provider: str, model: str) -> RateCard | None:
    return _load_rate_cards().get((provider.strip().lower(), model.strip()))


@lru_cache(maxsize=1)
def _load_image_rate_cards() -> dict[tuple[str, str, str, str], ImageRateCard]:
    with RATE_CARD_FILE.open('r', encoding='utf-8') as handle:
        raw = cast(object, yaml.safe_load(handle))
    if not isinstance(raw, Mapping):
        raise ValueError(f'{RATE_CARD_FILE} must contain a mapping')
    entries = raw.get('image_rate_cards', [])
    if not isinstance(entries, list):
        raise ValueError(f'{RATE_CARD_FILE} image_rate_cards must be a list')
    cards: dict[tuple[str, str, str, str], ImageRateCard] = {}
    for item in entries:
        if not isinstance(item, Mapping):
            raise ValueError(f'{RATE_CARD_FILE} image rate card entries must be mappings')
        card = ImageRateCard(
            rate_card_id=_required_string(item, 'rate_card_id'),
            provider=_required_string(item, 'provider').lower(),
            model=_required_string(item, 'model'),
            size=_required_string(item, 'size'),
            quality=_required_string(item, 'quality'),
            micro_usd_per_image=_nonnegative_int(item.get('micro_usd_per_image')),
        )
        key = (card.provider, card.model, card.size, card.quality)
        if key in cards:
            raise ValueError(
                f'duplicate gateway image rate card: {card.provider}/{card.model}/{card.size}/{card.quality}'
            )
        cards[key] = card
    return cards


def _image_rate_card_for(provider: str, model: str, size: str | None, quality: str | None) -> ImageRateCard | None:
    if size is None or quality is None:
        return None
    return _load_image_rate_cards().get((provider.strip().lower(), model.strip(), size, quality))


def clear_rate_cards_for_tests() -> None:
    _load_rate_cards.cache_clear()
    _load_image_rate_cards.cache_clear()


def _required_string(item: Mapping[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'rate card {key} must be a non-empty string')
    return value.strip()


def _nonnegative_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    return 0


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _has_any_field(raw: Mapping[str, Any], *keys: str) -> bool:
    return any(key in raw for key in keys)
