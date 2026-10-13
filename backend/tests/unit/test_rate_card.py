import hashlib
from decimal import Decimal
from pathlib import Path

import pytest
from config.rate_card import (
    budget_units,
    display_equivalents,
    free_budget_units,
    get_rate_card,
    price_llm_attempt,
    price_request,
    price_transcription,
    standard_chat_units,
)


def event(**values):
    return {
        'payer': 'omi',
        'usage_status': 'confirmed',
        'provider': 'openai',
        'configured_model': 'gpt-6-luna',
        'uncached_input_tokens': 2048,
        'cached_input_tokens': 0,
        'output_tokens': 512,
        **values,
    }


def test_v1_bytes_are_immutable_and_loading_derivation_matches():
    raw = Path(__file__).parents[2].joinpath('config/rate_card_v1.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == '333f224bf4fec44954d92d2e76b1a99cc14d31651b71fa4ac778123281ecd258'
    c = get_rate_card()['loading']
    assert Decimal(c['factor']) == Decimal(c['numerator_usd']) / Decimal(c['denominator_usd'])
    assert c['window'] == ['2026-09-22', '2026-10-09']
    c['factor'] = '0'
    assert get_rate_card()['loading']['factor'] != '0'


def test_cache_reads_and_list_price_survive_flex_or_reservation():
    ordinary = price_llm_attempt(event())
    assert ordinary['micro_units'] == 1059799
    assert price_llm_attempt(event(traffic_type='flex')) == ordinary
    cached = price_llm_attempt(event(uncached_input_tokens=0, cached_input_tokens=2048))
    assert cached['micro_units'] < ordinary['micro_units']
    gemini = price_llm_attempt(event(provider='gemini', configured_model='gemini-2.5-flash', traffic_type='pt'))
    assert gemini['micro_units'] > 0


def test_reasoning_long_context_and_cache_write_are_not_lost_or_duplicated():
    assert (
        price_llm_attempt(event(output_tokens=0, reasoning_tokens=512, output_tokens_include_reasoning=False))[
            'micro_units'
        ]
        == 1059799
    )
    assert (
        price_llm_attempt(event(reasoning_tokens=512, output_tokens_include_reasoning=True))['micro_units'] == 1059799
    )
    short = price_llm_attempt(event(uncached_input_tokens=272000, output_tokens=0))
    long = price_llm_attempt(event(uncached_input_tokens=272001, output_tokens=0))
    assert long['micro_units'] > 1.99 * short['micro_units']
    known = price_llm_attempt(event(cache_write_tokens=100))
    mixed = price_llm_attempt(event(cache_write_tokens=100, cache_write_ttl='mixed'))
    assert known['micro_units'] > mixed['micro_units']
    assert mixed['status'] == 'missing'


@pytest.mark.parametrize('payer', ['byok', 'on_device', 'custom'])
def test_customer_funded_work_is_zero(payer):
    assert price_llm_attempt(event(payer=payer))['micro_units'] == 0
    assert price_transcription(100, funding=payer, accepted=True)['micro_units'] == 0


def test_missing_funding_or_quantities_are_not_complete_zeroes():
    assert price_llm_attempt(event(payer='unknown'))['status'] == 'missing'
    assert price_llm_attempt(event(usage_status='not_reported'))['status'] == 'missing'
    assert price_llm_attempt(event(configured_model='unpriced'))['status'] == 'missing'


def test_transcription_preserves_fractional_speech_and_labels_estimates():
    accepted = price_transcription('0.03125', provider='modulate', accepted=True)
    assert accepted['micro_units'] > 0 and accepted['status'] == 'complete'
    estimate = price_transcription(100, provider='modulate')
    assert estimate['status'] == 'estimated'
    assert estimate['micro_units'] == price_transcription(32, provider='modulate', accepted=True)['micro_units']
    assert 'provider_unknown' in price_transcription(10)['reasons']
    with pytest.raises(ValueError):
        price_transcription(-1)


def test_realtime_and_images_use_pinned_inputs_or_explicit_estimates():
    rt = event(configured_model='gpt-realtime-2', modality_tokens={'input_audio': 100, 'output_audio': 50})
    assert price_llm_attempt(rt)['status'] == 'complete'
    rt.pop('modality_tokens')
    rt.update(rate_card_id='openai.gpt-realtime-2.modality.2026-09-01', estimated_cost_micro_usd=6400)
    assert price_llm_attempt(rt)['status'] == 'estimated'
    rt['rate_card_id'] = 'different'
    assert price_llm_attempt(rt)['status'] == 'missing'
    img = event(
        configured_model='gpt-image-1',
        unit_type='images',
        image_count=1,
        image_size='1024x1024',
        image_quality='medium',
    )
    assert price_llm_attempt(img)['micro_units'] > 0
    assert price_llm_attempt(img)['status'] == 'estimated'


def test_free_and_equivalents_derive_from_card_and_mix():
    assert standard_chat_units() == Decimal('0.302974')
    assert free_budget_units() == 217
    assert budget_units({'budget': {'kind': 'rate_card_mix'}}) == 217
    assert budget_units({'budget': None}) is None
    assert budget_units({'budget': {'kind': 'units', 'value': 16360}}) == 16360
    baseline = display_equivalents(239)
    loaded = display_equivalents(239, {'recording_overhead_units_per_hour': 1, 'chat_overhead_units': 1})
    assert loaded['recording_hours'] < baseline['recording_hours']
    assert loaded['chat_messages'] < baseline['chat_messages']
    assert price_request('mcp_api')['micro_units'] == 1000000
    assert price_request('web_search_tool')['status'] == 'provisional'
