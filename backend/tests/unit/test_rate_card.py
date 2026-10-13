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
    assert hashlib.sha256(raw).hexdigest() == '782edb7e64afdd72be88e81d03cc7346b46df332881de836a5e7cd6fe8ae32a0'
    from config.rate_card_versions import RATE_CARD_SHA256

    assert RATE_CARD_SHA256['v1'] == '782edb7e64afdd72be88e81d03cc7346b46df332881de836a5e7cd6fe8ae32a0'
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
    assert free_budget_units() == 4853
    assert budget_units({'budget': {'kind': 'rate_card_mix'}}) == 4853
    assert budget_units({'budget': None}) is None
    assert budget_units({'budget': {'kind': 'units', 'value': 16360}}) == 16360
    baseline = display_equivalents(239)
    loaded = display_equivalents(239, {'recording_overhead_units_per_hour': 1, 'chat_overhead_units': 1})
    assert loaded['recording_hours'] < baseline['recording_hours']
    assert loaded['chat_messages'] < baseline['chat_messages']
    assert price_request('mcp_api')['micro_units'] == 1000000
    assert price_request('web_search_tool')['status'] == 'provisional'


def test_loader_rejects_revised_v1_bytes(monkeypatch):
    from config import rate_card

    raw = Path(rate_card.__file__).with_name('rate_card_v1.json').read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'read_bytes', lambda self: raw + b' ')
        rate_card._card.cache_clear()
        with pytest.raises(ValueError, match='publish a new version file'):
            get_rate_card()
    rate_card._card.cache_clear()


def test_deepgram_includes_always_enabled_diarization_and_modulate_sku():
    cards = get_rate_card()['transcription']
    assert cards['deepgram']['micro_usd_per_hour'] == 468000
    assert '$0.0058/min' in cards['deepgram']['source']
    assert '$0.0020/min' in cards['deepgram']['source']
    assert price_transcription(3600, provider='deepgram', accepted=True)['micro_units'] == 968722833
    assert cards['modulate']['micro_usd_per_hour'] == 60000
    assert 'velma-2-stt-streaming' in cards['modulate']['source']


def test_omitted_reasoning_inclusion_defaults_to_extra_tokens():
    implicit = price_llm_attempt(event(output_tokens=0, reasoning_tokens=512))
    explicit = price_llm_attempt(event(output_tokens=0, reasoning_tokens=512, output_tokens_include_reasoning=False))
    assert implicit == explicit
    assert implicit['micro_units'] == 1059799


@pytest.mark.parametrize(
    'audio',
    [
        {'has_audio': True},
        {'input_modalities': ['audio']},
        {'input_audio_tokens': 100},
        {'modality_tokens': {'input_audio': 100}},
    ],
)
def test_nonrealtime_gemini_audio_is_an_estimate(audio):
    priced = price_llm_attempt(event(provider='gemini', configured_model='gemini-2.5-flash', **audio))
    assert priced['status'] == 'estimated'
    assert 'audio_modality_rate_missing' in priced['reasons']


@pytest.mark.parametrize(
    'model, modalities',
    [
        ('gemini-2.5-flash', {}),
        ('gemini-3.1-flash-live-preview', {'input_audio': 100, 'output_audio': 50}),
    ],
)
def test_gemini_tool_tokens_are_not_complete_at_text_or_modality_rate(model, modalities):
    priced = price_llm_attempt(
        event(provider='gemini', configured_model=model, modality_tokens=modalities, tool_use_prompt_tokens=10)
    )
    assert priced['status'] == 'estimated'
    assert 'tool_use_prompt_tokens_unpriced' in priced['reasons']


def test_free_covers_five_hours_of_every_free_routable_provider():
    budget = free_budget_units()
    assert get_rate_card()['default_speech_provider'] == 'deepgram'
    assert budget == 4853
    for provider in ('deepgram', 'soniox', 'modulate', 'parakeet'):
        speech = Decimal(price_transcription(18000, provider=provider, accepted=True)['micro_units']) / 1000000
        assert budget >= speech + 30 * standard_chat_units()


def test_display_uses_routed_provider_shares_and_conservative_unknown_mix():
    units = 1000
    shares = {'modulate': Decimal('0.75'), 'soniox': Decimal('0.25')}
    hourly = sum(
        share * Decimal(price_transcription(3600, provider=provider, accepted=True)['micro_units']) / 1000000
        for provider, share in shares.items()
    )
    result = display_equivalents(units, {'speech_provider_shares': shares})
    assert result['recording_hours'] == float(Decimal(units) / hourly)
    assert (
        display_equivalents(units)['recording_hours']
        == display_equivalents(units, {'speech_provider': 'deepgram'})['recording_hours']
    )
    assert result['recording_hours'] < display_equivalents(units, {'speech_provider': 'parakeet'})['recording_hours']


@pytest.mark.parametrize('shares', [{}, {'modulate': 0.5}, {'unlisted': 1}, {'modulate': -1, 'soniox': 2}])
def test_invalid_display_mix_is_rejected(shares):
    with pytest.raises(ValueError):
        display_equivalents(100, {'speech_provider_shares': shares})
