"""No dream route may use pay-as-you-go Gemini, before or after #20960."""

from copy import deepcopy

from llm_gateway.gateway.config_loader import load_gateway_config, _generated_desktop_vertex_items
from llm_gateway.gateway.dream_lanes import dream_lane_items


def test_default_dream_lanes_are_gateway_luna():
    config = load_gateway_config(prod_mode=False)
    for stage in ('triage', 'reasoning'):
        lane = config.lanes['omi:auto:dream-' + stage]
        route = config.route_artifacts[lane.active_route]
        assert route.primary.model == 'gpt-6-luna'
        assert route.primary.provider == 'openai'
        assert not route.fallbacks


def test_reserved_policy_is_inherited_only_with_dedicated_and_luna_fallback():
    lanes, artifacts = _generated_desktop_vertex_items()
    reserved = deepcopy(artifacts)
    reserved[0]['provider_options']['reserved_capacity_only'] = True
    reserved[0]['fallbacks'] = [{'provider': 'openai', 'model': 'gpt-6-luna'}]
    reserved[0]['fallback_policy']['fallback_on'].append('reserved_capacity_unavailable')
    _, dream = dream_lane_items(lanes, reserved)
    assert dream[0]['primary'] == {'provider': 'openai', 'model': 'gpt-6-luna'}
    assert dream[1]['primary']['provider'] == 'gemini'
    assert dream[1]['provider_options']['reserved_capacity_only'] is True
    assert dream[1]['fallbacks'] == [{'provider': 'openai', 'model': 'gpt-6-luna'}]
    reserved[0]['fallbacks'] = []
    _, unsafe = dream_lane_items(lanes, reserved)
    assert unsafe[1]['primary']['model'] == 'gpt-6-luna'
