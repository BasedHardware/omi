"""Dream reasoning may use only the gateway's reserved Gemini capacity."""

from copy import deepcopy

from config.dream_agent import FULL_MODEL_SECONDS

from llm_gateway.gateway.config_loader import load_gateway_config, _generated_desktop_vertex_items
from llm_gateway.gateway.dream_lanes import dream_lane_items
from utils.dream_transport import TRIAGE_LANE, MAIN_LANE


def test_backend_transport_lanes_exist_in_same_commit_gateway_config():
    config = load_gateway_config(prod_mode=False)
    for name in (TRIAGE_LANE, MAIN_LANE):
        lane = config.lanes[name]
        assert lane.active_route in config.route_artifacts


def test_default_dream_lanes_use_luna_or_reserved_gemini():
    config = load_gateway_config(prod_mode=False)
    triage_lane = config.lanes['omi:auto:dream-triage']
    triage_route = config.route_artifacts[triage_lane.active_route]
    assert triage_route.primary.model == 'gpt-6-luna'
    assert triage_route.primary.provider == 'openai'
    assert not triage_route.fallbacks

    reasoning_lane = config.lanes['omi:auto:dream-reasoning']
    reasoning_route = config.route_artifacts[reasoning_lane.active_route]
    assert reasoning_route.primary.provider == 'gemini'
    assert reasoning_route.provider_options['reserved_capacity_only'] is True
    assert reasoning_route.fallbacks[0].model == 'gpt-6-luna'


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


def test_dream_reasoning_deadline_covers_full_model_while_triage_stays_bounded():
    config = load_gateway_config(prod_mode=True)
    triage = config.route_artifacts[config.lanes[TRIAGE_LANE].active_route]
    reasoning = config.route_artifacts[config.lanes[MAIN_LANE].active_route]
    assert triage.timeouts.request_ms == 60000
    assert reasoning.timeouts.request_ms == FULL_MODEL_SECONDS * 1000 == 480000
    assert reasoning.retry.max_attempts == 1
