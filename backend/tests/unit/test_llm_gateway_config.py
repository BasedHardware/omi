from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from llm_gateway.gateway.config_loader import ConfigValidationError, load_gateway_config
from utils.llm.model_config import get_all_configured_features

LANE_ID = 'omi:auto:chat-structured'
ACTIVE_ROUTE = 'route.chat_structured.2026_06_27.001'
LKG_ROUTE = 'route.chat_structured.2026_06_20.001'


def test_loads_default_gateway_config():
    config = load_gateway_config(prod_mode=True)

    assert LANE_ID in config.lanes
    assert len(config.lanes) >= len(get_all_configured_features())
    lane = config.lanes[LANE_ID]
    assert lane.active_route == ACTIVE_ROUTE
    assert lane.last_known_good == LKG_ROUTE
    assert config.route_artifacts[ACTIVE_ROUTE].content_digest.startswith('sha256:')
    assert config.feature_bundles['chat_extraction.requires_context'].lane_id == LANE_ID


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
