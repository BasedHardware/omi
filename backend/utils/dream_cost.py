"""Per-attempt Dream cost from gateway rate cards, and tokenizer-free token estimates.

Serialized UTF-8 bytes are converted at 3.5 bytes per token, rounded up. 3.5 is
denser than the roughly 4 bytes/token English average, so the estimate sits
slightly above typical Gemini counts. It is not a byte-as-token ceiling.

gemini-3.8-flash is priced from the global-endpoint card in ``rate_cards``.
A model listed under ``unpriced_models`` still reports status ``unpriced``
and never a zero dollar cost. Cache storage uses the card's
``cache_storage_micro_usd_per_million_token_hours``.
"""

import math
from fractions import Fraction
from pathlib import Path

import yaml

from llm_gateway.gateway.accounting import rate_card_for, rounded_micro_usd
from utils.agent_capabilities.session import serialized_bytes
from utils.dream_verify import evidence

RATE_CARD_FILE = Path(__file__).resolve().parents[1] / 'llm_gateway' / 'config' / 'cost_rate_cards.yaml'
BYTES_PER_TOKEN = 3.5
TOKENS_PER_MILLION = 1_000_000
# Verifier run_loop refuses a call once fewer than this many tokens remain.
VERIFIER_CALL_FLOOR = 1024


def estimate_tokens(nbytes):
    if type(nbytes) is not int or nbytes <= 0:
        return 0
    return math.ceil(nbytes / BYTES_PER_TOKEN)


def _load_yaml():
    with RATE_CARD_FILE.open('r', encoding='utf-8') as handle:
        raw = yaml.safe_load(handle)
    return raw if isinstance(raw, dict) else {}


def unpriced_card(provider, model):
    """Return the unpriced-model entry, or None when the model is not listed there."""
    for item in _load_yaml().get('unpriced_models') or []:
        if not isinstance(item, dict):
            continue
        if item.get('provider') == provider and item.get('model') == model and item.get('status') == 'unpriced':
            return item
    return None


def _storage_micro(card, token_seconds):
    if type(token_seconds) is not int or token_seconds < 0:
        return None, False
    if token_seconds == 0:
        return 0, True
    # Missing rate with positive storage is unpriced, never zero.
    rate = getattr(card, 'cache_storage_micro_usd_per_million_token_hours', None)
    if type(rate) is not int:
        return None, False
    return rounded_micro_usd(token_seconds * rate // 3600), True


def price_attempt(
    provider,
    model,
    *,
    prompt_tokens,
    cached_tokens,
    completion_tokens,
    cache_write_tokens=0,
    cache_storage_token_seconds=0,
    at=None,
):
    """Return ``(micro_usd, status)``. ``status`` is ``priced`` or ``unpriced``.

    Unpriced is never coerced to zero. Cache writes without a write rate, or
    storage seconds without a storage rate, make the attempt unpriced.
    """
    counts = (prompt_tokens, cached_tokens, completion_tokens, cache_write_tokens, cache_storage_token_seconds)
    if any(type(count) is not int or count < 0 for count in counts):
        return None, 'unpriced'
    if cached_tokens > prompt_tokens:
        return None, 'unpriced'
    if unpriced_card(provider, model) is not None:
        return None, 'unpriced'
    card = rate_card_for(provider or '', model or '', at=at)
    if card is None:
        return None, 'unpriced'
    rates = card.effective_rates(prompt_tokens)
    write_rate = rates.cache_write_micro_usd_per_million
    if cache_write_tokens and type(write_rate) is not int:
        return None, 'unpriced'
    storage_micro, storage_priced = _storage_micro(card, cache_storage_token_seconds)
    if not storage_priced or storage_micro is None:
        return None, 'unpriced'
    uncached = prompt_tokens - cached_tokens - cache_write_tokens
    if uncached < 0:
        return None, 'unpriced'
    numerator = (
        uncached * rates.input_micro_usd_per_million
        + cached_tokens * rates.cached_input_micro_usd_per_million
        + completion_tokens * rates.output_micro_usd_per_million
    )
    if cache_write_tokens and type(write_rate) is int:
        numerator += cache_write_tokens * write_rate
    micro = rounded_micro_usd(numerator) + storage_micro
    return micro, 'priced'


def cached_input_price_ratio(provider, model, prompt_tokens):
    """Return cached-input cost as a fraction of uncached input cost.

    This deliberately reads the same active rate card and context tier as
    ``price_attempt``. ``None`` means there is no verified ratio, so callers
    must count cached input at the full uncached rate.
    """
    if type(prompt_tokens) is not int or prompt_tokens < 0:
        return None
    card = rate_card_for(provider or '', model or '')
    if card is None:
        return None
    rates = card.effective_rates(prompt_tokens)
    uncached_rate = rates.input_micro_usd_per_million
    cached_rate = rates.cached_input_micro_usd_per_million
    if type(uncached_rate) is not int or uncached_rate <= 0 or type(cached_rate) is not int or cached_rate < 0:
        return None
    return Fraction(cached_rate, uncached_rate)


def price_weighted_tokens(
    provider,
    model,
    *,
    prompt_tokens,
    cached_tokens,
    completion_tokens,
    cache_reported=True,
):
    """Convert usage to uncached-input-price-equivalent tokens.

    Missing or unreported cache usage gets no discount. Rounding up keeps the
    pass budget conservative while preserving exact rate-card ratios.
    """
    if any(type(count) is not int or count < 0 for count in (prompt_tokens, completion_tokens)):
        raise ValueError('dream_invalid_usage')
    if cached_tokens is not None and (type(cached_tokens) is not int or cached_tokens < 0):
        raise ValueError('dream_invalid_cache_usage')
    if cached_tokens is not None and cached_tokens > prompt_tokens:
        raise ValueError('dream_invalid_cache_usage')
    discountable = cached_tokens or 0
    if not cache_reported or cached_tokens is None:
        discountable = 0
    ratio = cached_input_price_ratio(provider, model, prompt_tokens) if discountable else Fraction(1, 1)
    if ratio is None:
        ratio = Fraction(1, 1)
    return math.ceil(prompt_tokens - discountable + completion_tokens + discountable * ratio)


def minute_burndown_tokens(provider, model, *, weighted_tokens, completion_tokens, prompt_tokens=0):
    """Reserved-capacity burndown for the shared minute ceiling.

    ``weighted_tokens`` already counts cached input at its rate-card fraction and
    completion at 1; reserved burndown counts output at the output/input price
    ratio (5 for gemini-3.8-flash), so the completion is topped up to that ratio.
    Without a verified card the output is counted at 5, never less.
    """
    ratio = Fraction(5, 1)
    card = rate_card_for(provider or '', model or '')
    if card is not None:
        rates = card.effective_rates(max(0, int(prompt_tokens)))
        if (
            type(rates.input_micro_usd_per_million) is int
            and rates.input_micro_usd_per_million > 0
            and type(rates.output_micro_usd_per_million) is int
            and rates.output_micro_usd_per_million > 0
        ):
            ratio = max(Fraction(1, 1), Fraction(rates.output_micro_usd_per_million, rates.input_micro_usd_per_million))
    return math.ceil(weighted_tokens + completion_tokens * (ratio - 1))


def conservative_attempt_micro(provider, model, input_tokens, completion_tokens):
    """Unknown billed usage: the whole input at the uncached rate, plus completion.

    Returns ``(None, 'unpriced')`` when the model has no verified card.
    """
    return price_attempt(
        provider,
        model,
        prompt_tokens=max(0, input_tokens),
        cached_tokens=0,
        completion_tokens=max(0, completion_tokens),
    )


def verification_reserve_tokens(staged, *, completion_tokens):
    """Token hold for two verifier calls, computed from staged evidence only.

    Each call is charged the evidence-byte estimate plus its bounded completion,
    and at least the verifier's 1024-token start floor. Nothing is held during
    the main loop.
    """
    if not staged:
        return 0
    evidence_bytes = sum(serialized_bytes(evidence(item)) for item in staged)
    per_call = max(VERIFIER_CALL_FLOOR, estimate_tokens(evidence_bytes) + max(0, int(completion_tokens)))
    return per_call * 2


def charge_attempts(attempts, *, ceiling, provider, model):
    """Token charge and dollar status for one gateway turn.

    Complete attempts use their reported tokens. Incomplete billed attempts
    take the one-attempt ceiling when that is larger than the partial report.
    ``attempts is None`` means the caller should fall back to aggregates.
    """
    if attempts is None:
        return None
    tokens = 0
    cached = 0
    prompt = 0
    completion = 0
    unreported = 0
    micros = 0
    price_weighted = 0
    priced = True
    for attempt in attempts:
        if not isinstance(attempt, dict):
            raise ValueError('dream_invalid_usage')
        prompt_tokens = attempt.get('prompt_tokens', 0)
        cached_tokens = attempt.get('cached_tokens', 0)
        completion_tokens = attempt.get('completion_tokens', 0)
        counts = (prompt_tokens, cached_tokens, completion_tokens)
        if any(type(count) is not int or count < 0 for count in counts) or cached_tokens > prompt_tokens:
            raise ValueError('dream_invalid_usage')
        complete = attempt.get('usage_complete') is True
        partial = prompt_tokens + completion_tokens
        take = partial if complete else max(ceiling, partial)
        tokens += take
        if complete:
            price_weighted += price_weighted_tokens(
                attempt.get('provider') or provider,
                attempt.get('model') or model,
                prompt_tokens=prompt_tokens,
                cached_tokens=cached_tokens,
                completion_tokens=completion_tokens,
                cache_reported=attempt.get('cache_field_reported') is True,
            )
        else:
            # Partial or missing cache data is deliberately charged at full price.
            price_weighted += take
        if complete:
            prompt += prompt_tokens
            completion += completion_tokens
            cached += cached_tokens
            if attempt.get('cache_field_reported') is not True:
                unreported += max(0, prompt_tokens - cached_tokens)
        attempt_provider = attempt.get('provider') or provider
        attempt_model = attempt.get('model') or model
        if complete:
            micro, status = price_attempt(
                attempt_provider,
                attempt_model,
                prompt_tokens=prompt_tokens,
                cached_tokens=cached_tokens,
                completion_tokens=completion_tokens,
                cache_write_tokens=attempt.get('cache_write_tokens') or 0,
                cache_storage_token_seconds=attempt.get('cache_storage_token_seconds') or 0,
            )
        else:
            micro, status = conservative_attempt_micro(attempt_provider, attempt_model, take, 0)
        if status != 'priced' or micro is None:
            priced = False
        else:
            micros += micro
    return {
        'tokens': tokens,
        'price_weighted_tokens': price_weighted,
        'prompt_tokens': prompt,
        'completion_tokens': completion,
        'cached_tokens': cached,
        'cache_unreported_tokens': unreported,
        'cost_micro_usd': micros if priced else None,
        'cost_status': 'priced' if priced else 'unpriced',
    }
