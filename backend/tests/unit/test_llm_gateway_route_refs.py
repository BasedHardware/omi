from __future__ import annotations

import pytest

from utils.llm import model_config
from utils.llm.gateway_client import is_auto_lane_id
from utils.llm.model_config import (
    AutoLaneRouteRef,
    ExplicitRouteRef,
    get_model,
    get_provider,
    get_route_options,
    get_route_ref,
)


def test_known_feature_returns_explicit_route_ref_without_changing_model_or_provider():
    feature = 'conv_action_items'
    before_model = get_model(feature)
    before_provider = get_provider(feature)

    route_ref = get_route_ref(feature)

    assert route_ref == ExplicitRouteRef(
        feature=feature,
        model=before_model,
        provider=before_provider,
        options=get_route_options(feature, before_model, before_provider),
    )
    assert get_model(feature) == before_model
    assert get_provider(feature) == before_provider


def test_unknown_feature_route_ref_uses_default_explicit_route():
    feature = 'unknown_route_ref_feature'

    route_ref = get_route_ref(feature)

    assert route_ref == ExplicitRouteRef(
        feature=feature,
        model='gpt-4.1-mini',
        provider='openai',
        options={},
    )
    assert get_model(feature) == 'gpt-4.1-mini'
    assert get_provider(feature) == 'openai'


def test_pinned_feature_route_ref_preserves_pinned_route_and_options():
    route_ref = get_route_ref('fair_use')

    assert route_ref == ExplicitRouteRef(
        feature='fair_use',
        model='gpt-5.1',
        provider='openai',
        options={'extra_body': {"prompt_cache_retention": "24h"}},
    )
    assert get_model('fair_use') == 'gpt-5.1'
    assert get_provider('fair_use') == 'openai'


def test_route_ref_preserves_provider_route_options():
    openrouter_ref = get_route_ref('wrapped_analysis')
    gemini_ref = get_route_ref('followup')

    assert isinstance(openrouter_ref, ExplicitRouteRef)
    assert openrouter_ref.provider == 'openrouter'
    assert openrouter_ref.options == {'temperature': 0.7}

    assert isinstance(gemini_ref, ExplicitRouteRef)
    assert gemini_ref.provider == 'gemini'
    assert gemini_ref.options == {'thinking_budget': 0}


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        ('omi:auto:chat-structured', True),
        ('omi:auto:', True),
        ('gpt-4.1-mini', False),
        ('openai/gpt-4.1-mini', False),
        (' omi:auto:chat-structured', False),
        ('OMI:AUTO:chat-structured', False),
        (None, False),
    ],
)
def test_is_auto_lane_id_matches_gateway_namespace(value, expected):
    assert is_auto_lane_id(value) is expected
    assert model_config.is_auto_lane_id(value) is expected


def test_auto_lane_mapping_is_opt_in_and_does_not_change_existing_direct_helpers(monkeypatch):
    feature = 'chat_extraction'
    before_model = get_model(feature)
    before_provider = get_provider(feature)

    monkeypatch.setitem(model_config._AUTO_LANE_FEATURES, feature, 'omi:auto:chat-structured')

    route_ref = get_route_ref(feature)

    assert route_ref == AutoLaneRouteRef(feature=feature, lane_id='omi:auto:chat-structured')
    assert get_model(feature) == before_model
    assert get_provider(feature) == before_provider


def test_auto_lane_mapping_rejects_non_gateway_namespace(monkeypatch):
    monkeypatch.setitem(model_config._AUTO_LANE_FEATURES, 'chat_extraction', 'gpt-4.1-mini')

    with pytest.raises(ValueError, match='omi:auto'):
        get_route_ref('chat_extraction')
