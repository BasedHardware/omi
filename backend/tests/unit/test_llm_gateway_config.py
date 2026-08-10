from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from llm_gateway.gateway import config_loader
from llm_gateway.gateway.config_loader import (
    SERVING_LANE_DROP_CONFIRM_ENV_VAR,
    ConfigValidationError,
    ServingLaneAllowlistError,
    feature_lane_id,
    load_gateway_config,
)
from llm_gateway.gateway.lane_catalog import ProviderSupportStatus, load_catalog
from llm_gateway.gateway.schemas import Capabilities, StructuredOutputMode, Surface
from utils.llm.model_config import get_all_configured_features, get_model, get_provider

LANE_ID = 'omi:auto:chat-structured'
ACTIVE_ROUTE = 'route.chat_structured.2026_06_27.001'
LKG_ROUTE = 'route.chat_structured.2026_06_20.001'


def test_loads_default_gateway_config():
    config = load_gateway_config(prod_mode=True)

    assert LANE_ID in config.lanes
    non_production = {
        entry.lane_id
        for entry in load_catalog().lanes
        if entry.provider_support_status != ProviderSupportStatus.PROD_READY
    }
    assert non_production.isdisjoint(set(config.lanes) - set(config.generated_lane_ids))
    lane = config.lanes[LANE_ID]
    assert lane.active_route == ACTIVE_ROUTE
    assert lane.last_known_good == LKG_ROUTE
    assert config.route_artifacts[ACTIVE_ROUTE].content_digest.startswith('sha256:')
    assert config.feature_bundles['chat_extraction.requires_context'].lane_id == LANE_ID
    assert config.route_artifacts[ACTIVE_ROUTE].primary.model == 'gpt-5.6-luna'
    assert config.route_artifacts[ACTIVE_ROUTE].provider_options['reasoning_effort'] == 'low'


def test_gateway_config_excludes_uncatalogued_model_config_lanes():
    config = load_gateway_config(prod_mode=True)

    assert get_model('conv_discard') == 'gpt-5-nano'
    assert get_model('memories') == 'gpt-5.6-luna'
    assert get_model('fair_use') == 'gpt-5.6-luna'
    assert get_model('chat_agent') == 'claude-sonnet-4-6'

    assert config.route_artifacts['route.conv_discard.model_config.001'].primary.model == 'gpt-5-nano'
    assert config.route_artifacts['route.memories.model_config.001'].primary.model == 'gpt-5.6-luna'
    assert config.route_artifacts['route.fair_use.model_config.001'].primary.model == 'gpt-5.6-luna'
    assert config.route_artifacts['route.chat_agent.model_config.001'].primary.provider == 'openai'
    assert config.route_artifacts['route.chat_agent.model_config.001'].primary.model == 'gpt-5.6-luna'
    assert config.route_artifacts['route.memory_l2.model_config.001'].provider_options['reasoning_effort'] == 'medium'
    assert config.route_artifacts['route.chat_agent.model_config.001'].provider_options == {
        'extra_body': {'prompt_cache_retention': '24h'},
        'reasoning_effort': 'none',
    }
    chat_agent_lane = config.lanes['omi:auto:chat-agent']
    assert chat_agent_lane.surface == Surface.OPENAI_CHAT_COMPLETIONS
    assert chat_agent_lane.capabilities.streaming is True
    assert chat_agent_lane.capabilities.tools is True


def test_memory_l2_gateway_lane_resolves_to_luna():
    config = load_gateway_config(prod_mode=True)

    assert get_model('memory_l2') == 'gpt-5.6-luna'
    assert get_provider('memory_l2') == 'openai'
    lane = config.lanes['omi:auto:memory-l2']
    route = config.route_artifacts[lane.active_route]
    assert lane.surface == Surface.OPENAI_CHAT_COMPLETIONS
    assert route.primary.model == 'gpt-5.6-luna'
    assert route.primary.provider == 'openai'


def test_translation_uses_the_gateway_translation_capability():
    config = load_gateway_config(prod_mode=True)

    assert get_model('translation') == 'gemini-2.5-flash-lite'
    assert get_provider('translation') == 'gemini'
    lane = config.lanes['omi:auto:translation']
    assert lane.capabilities.translation is True
    assert lane.capabilities.structured_output.value == 'json_schema'


def test_translation_capability_requires_json_schema_output():
    with pytest.raises(ValueError, match='translation lanes require json_schema'):
        Capabilities(
            text_input=True,
            streaming=False,
            structured_output=StructuredOutputMode.NONE,
            tools=False,
            translation=True,
        )


def test_unknown_gateway_route_override_fails(tmp_path):
    write_config(
        tmp_path,
        generated_route_overrides=[
            {'feature': 'not_a_configured_feature', 'primary': {'provider': 'openai', 'model': 'gpt-5-nano'}}
        ],
    )

    with pytest.raises(ConfigValidationError, match='gateway route override references unknown feature'):
        load_gateway_config(tmp_path, prod_mode=False)


def test_chat_structured_routes_have_background_shadow_timeout_budget():
    config = load_gateway_config(prod_mode=True)

    assert config.route_artifacts[ACTIVE_ROUTE].timeouts.request_ms >= 30000
    assert config.route_artifacts[LKG_ROUTE].timeouts.request_ms >= 30000


def test_missing_active_route_fails(tmp_path):
    write_config(tmp_path, lane_overrides={'active_route': 'route.missing'})

    with pytest.raises(ConfigValidationError, match='active_route route not found'):
        load_gateway_config(tmp_path, prod_mode=False)


def test_missing_lkg_route_fails(tmp_path):
    write_config(tmp_path, lane_overrides={'last_known_good': 'route.missing'})

    with pytest.raises(ConfigValidationError, match='last_known_good route not found'):
        load_gateway_config(tmp_path, prod_mode=False)


def test_invalid_lkg_capability_fails(tmp_path):
    write_config(tmp_path, lkg_overrides={'capabilities': capabilities(structured_output='json_object')})

    with pytest.raises(ConfigValidationError, match='last_known_good.*structured_output mismatch'):
        load_gateway_config(tmp_path, prod_mode=False)


def test_invalid_lkg_credential_mode_fails(tmp_path):
    write_config(
        tmp_path,
        lkg_overrides={'credential_policy': credential_policy(mode='byok')},
    )

    with pytest.raises(ConfigValidationError, match='last_known_good.*credential mode mismatch'):
        load_gateway_config(tmp_path, prod_mode=False)


def test_duplicate_route_id_fails(tmp_path):
    active = route_artifact(ACTIVE_ROUTE)
    write_config(tmp_path, route_artifacts=[active, {**route_artifact(LKG_ROUTE), 'route_artifact_id': ACTIVE_ROUTE}])

    with pytest.raises(ConfigValidationError, match='duplicate route_artifact_id'):
        load_gateway_config(tmp_path, prod_mode=False)


def test_artifact_digest_is_stable_and_excludes_artifact_digest(tmp_path):
    artifact = route_artifact(ACTIVE_ROUTE)
    write_config(tmp_path, route_artifacts=[artifact, route_artifact(LKG_ROUTE, model='gpt-4o-mini')])
    first = load_gateway_config(tmp_path, prod_mode=False).route_artifacts[ACTIVE_ROUTE].content_digest

    write_config(
        tmp_path,
        route_artifacts=[
            {**artifact, 'artifact_digest': 'sha256:0000000000000000000000000000000000000000000000000000000000000000'},
            route_artifact(LKG_ROUTE, model='gpt-4o-mini'),
        ],
    )

    with pytest.raises(ConfigValidationError, match='artifact_digest mismatch'):
        load_gateway_config(tmp_path, prod_mode=False)

    write_config(tmp_path, route_artifacts=[{**artifact, 'artifact_digest': first}, route_artifact(LKG_ROUTE)])
    second = load_gateway_config(tmp_path, prod_mode=False).route_artifacts[ACTIVE_ROUTE].content_digest
    assert second == first


def test_mock_benchmark_evidence_rejected_in_prod_mode(tmp_path):
    write_config(
        tmp_path,
        active_overrides={
            'evidence': {
                'benchmark_snapshot': 'bench.dev.fixture',
                'eval_report': 'eval.dev.fixture',
                'benchmark_source': 'mock',
                'dev_only': True,
            }
        },
    )

    load_gateway_config(tmp_path, prod_mode=False)
    with pytest.raises(ConfigValidationError, match='dev-only benchmark evidence'):
        load_gateway_config(tmp_path, prod_mode=True)


@pytest.mark.parametrize(
    'rollout',
    [
        {'stage': 'active', 'percent': 99},
        {'stage': 'shadow', 'percent': 1},
        {'stage': 'disabled', 'percent': 1},
    ],
)
def test_invalid_rollout_stage_percent_combination_fails(tmp_path, rollout):
    write_config(tmp_path, active_overrides={'rollout': rollout})

    with pytest.raises(ValueError, match='rollout stage must use percent'):
        load_gateway_config(tmp_path, prod_mode=False)


def write_config(
    config_dir: Path,
    *,
    lane_overrides: dict | None = None,
    active_overrides: dict | None = None,
    lkg_overrides: dict | None = None,
    route_artifacts: list[dict] | None = None,
    generated_route_overrides: list[dict] | None = None,
) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    lane = {
        'lane_id': LANE_ID,
        'surface': 'openai.chat_completions',
        'capabilities': capabilities(),
        'objective': {'quality': 0.6, 'latency': 0.2, 'cost': 0.2},
        'credential_policy': credential_policy(),
        'active_route': ACTIVE_ROUTE,
        'last_known_good': LKG_ROUTE,
    }
    if lane_overrides:
        lane.update(lane_overrides)

    if route_artifacts is None:
        active = route_artifact(ACTIVE_ROUTE, model='gpt-4.1-mini')
        lkg = route_artifact(LKG_ROUTE, model='gpt-4o-mini')
        if active_overrides:
            active.update(active_overrides)
        if lkg_overrides:
            lkg.update(lkg_overrides)
        route_artifacts = [active, lkg]

    feature_bundle = {
        'feature': 'chat_extraction.requires_context',
        'lane_id': LANE_ID,
        'prompt_version': 'chat_extraction.requires_context.v1',
        'parser_version': 'RequiresContext.v1',
        'eval_suite': 'chat_extraction_requires_context.v1',
        'promotion_gates': {'schema_valid_rate': '>= 99.5%'},
    }

    write_yaml(config_dir / 'lanes.yaml', {'lanes': [lane]})
    write_yaml(config_dir / 'route_artifacts.yaml', {'route_artifacts': route_artifacts})
    write_yaml(config_dir / 'feature_bundles.yaml', {'feature_bundles': [feature_bundle]})
    if generated_route_overrides is not None:
        write_yaml(
            config_dir / 'generated_route_overrides.yaml', {'generated_route_overrides': generated_route_overrides}
        )


def capabilities(structured_output: str = 'json_schema') -> dict:
    return {
        'text_input': True,
        'streaming': False,
        'structured_output': structured_output,
        'tools': False,
    }


def credential_policy(mode: str = 'omi_paid') -> dict:
    return {
        'mode': mode,
        'allow_byok_to_omi_paid_fallback': False,
        'fallback_eligible_failure_classes': [
            'timeout_before_output',
            'provider_429_omi_paid',
            'provider_5xx_omi_paid',
        ],
        'never_fallback_failure_classes': [
            'byok_auth',
            'byok_quota',
            'byok_rate_limit',
            'byok_unsupported_provider',
            'missing_byok_key',
            'capability_mismatch',
            'invalid_config',
        ],
    }


def route_artifact(route_artifact_id: str, *, model: str = 'gpt-4.1-mini') -> dict:
    return {
        'route_artifact_id': route_artifact_id,
        'lane_id': LANE_ID,
        'surface': 'openai.chat_completions',
        'primary': {'provider': 'openai', 'model': model},
        'fallbacks': [],
        'timeouts': {'request_ms': 8000},
        'retry': {'max_attempts': 1},
        'capabilities': capabilities(),
        'evidence': {
            'benchmark_snapshot': 'bench.omi.chat_structured.2026_06_27',
            'eval_report': 'eval.memory_extraction.2026_06_27',
            'benchmark_source': 'omi_eval',
            'dev_only': False,
        },
        'rollout': {'stage': 'shadow', 'percent': 0},
        'credential_policy': credential_policy(),
        'fallback_policy': {
            'fallback_on': ['timeout_before_output', 'provider_429_omi_paid', 'provider_5xx_omi_paid'],
            'never_fallback_on': [
                'byok_auth',
                'byok_quota',
                'byok_rate_limit',
                'missing_byok_key',
                'capability_mismatch',
                'invalid_config',
            ],
        },
    }


def write_yaml(path: Path, payload: dict) -> None:
    with path.open('w', encoding='utf-8') as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


# --- Serving lane set: default breadth + opt-in narrowing -------------------
#
# Regression guard. A prior revision gated serving on `prod_ready` catalog
# entries, which on the merged tree cut the served set from every generated
# feature lane down to the two hand-authored ones — 40 production lanes
# silently disabled. These tests fail loudly if that recurs, and pin the opt-in
# narrowing mechanism to refusing rather than silently dropping.

HAND_AUTHORED_SERVING_LANES = {
    'omi:auto:chat-structured',
    'omi:auto:public-shared-conversation-chat',
}


def every_generated_lane_id() -> set[str]:
    return {feature_lane_id(feature) for feature in get_all_configured_features()}


def test_default_config_serves_every_generated_lane():
    config = load_gateway_config(prod_mode=True)

    expected_generated = every_generated_lane_id()
    assert set(config.generated_lane_ids) == expected_generated
    # Numeric floor: catches a collapse even if `model_config` itself shrinks.
    assert len(expected_generated) >= 40
    assert set(config.lanes) == expected_generated | HAND_AUTHORED_SERVING_LANES
    for lane_id, lane in config.lanes.items():
        assert lane.active_route in config.route_artifacts


def test_default_config_ignores_an_empty_serving_allowlist():
    baseline = load_gateway_config(prod_mode=True)
    explicit_empty = load_gateway_config(prod_mode=True, serving_lane_allowlist='')

    assert set(explicit_empty.lanes) == set(baseline.lanes)
    assert set(explicit_empty.generated_lane_ids) == set(baseline.generated_lane_ids)


def test_serving_allowlist_refuses_to_silently_drop_lanes():
    with pytest.raises(ServingLaneAllowlistError) as excinfo:
        load_gateway_config(prod_mode=True, serving_lane_allowlist='omi:auto:chat-structured')

    message = str(excinfo.value)
    assert 'refusing to start' in message
    assert SERVING_LANE_DROP_CONFIRM_ENV_VAR in message


def test_serving_allowlist_requires_the_exact_drop_set_to_be_confirmed():
    baseline = load_gateway_config(prod_mode=True)
    keep = sorted(HAND_AUTHORED_SERVING_LANES)
    dropped = sorted(set(baseline.lanes) - set(keep))

    with pytest.raises(ServingLaneAllowlistError):
        load_gateway_config(
            prod_mode=True,
            serving_lane_allowlist=keep,
            serving_lane_drop_confirm=dropped[:1],
        )


def test_serving_allowlist_rejects_lane_ids_the_config_does_not_generate():
    with pytest.raises(ServingLaneAllowlistError) as excinfo:
        load_gateway_config(prod_mode=True, serving_lane_allowlist='omi:auto:not-a-real-lane')

    assert 'does not generate' in str(excinfo.value)


def test_serving_allowlist_naming_every_lane_changes_nothing():
    baseline = load_gateway_config(prod_mode=True)
    restricted = load_gateway_config(prod_mode=True, serving_lane_allowlist=sorted(baseline.lanes))

    assert set(restricted.lanes) == set(baseline.lanes)
    assert set(restricted.route_artifacts) == set(baseline.route_artifacts)
    assert set(restricted.feature_bundles) == set(baseline.feature_bundles)


def test_confirmed_serving_allowlist_narrows_and_records_a_fallback(monkeypatch):
    baseline = load_gateway_config(prod_mode=True)
    keep = sorted(HAND_AUTHORED_SERVING_LANES)
    dropped = sorted(set(baseline.lanes) - set(keep))
    assert dropped, 'expected the generated lanes to be droppable'

    recorded: list[dict] = []
    monkeypatch.setattr(config_loader, 'record_fallback', lambda **kwargs: recorded.append(kwargs))

    restricted = load_gateway_config(
        prod_mode=True,
        serving_lane_allowlist=keep,
        serving_lane_drop_confirm=dropped,
    )

    assert set(restricted.lanes) == set(keep)
    assert restricted.generated_lane_ids == frozenset()
    assert all(art.lane_id in set(keep) for art in restricted.route_artifacts.values())
    assert all(bundle.lane_id in set(keep) for bundle in restricted.feature_bundles.values())
    assert len(recorded) == 1
    assert recorded[0]['component'] == 'llm_gateway'
    assert recorded[0]['outcome'] == 'degraded'
    assert recorded[0]['reason'] == 'policy'


def test_serving_allowlist_reads_the_environment_when_no_argument_is_passed(monkeypatch):
    monkeypatch.setenv(config_loader.SERVING_LANE_ALLOWLIST_ENV_VAR, 'omi:auto:chat-structured')

    with pytest.raises(ServingLaneAllowlistError):
        load_gateway_config(prod_mode=True)
