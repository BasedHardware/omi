from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from llm_gateway.gateway.config_loader import ConfigValidationError, load_gateway_config

LANE_ID = 'omi:auto:chat-structured'
ACTIVE_ROUTE = 'route.chat_structured.2026_06_27.001'
LKG_ROUTE = 'route.chat_structured.2026_06_20.001'

# R0 lane taxonomy — 15 new lanes added alongside the existing chat-structured lane.
# See PLAN.md §R0 (posted as PR comment). All new lanes ship in shadow mode (percent=0)
# with last_known_good == active_route (zero-drift day-one parity).
_R0_NEW_LANE_IDS = frozenset(
    {
        'omi:auto:chat-extraction',
        'omi:auto:daily-summary',
        'omi:auto:memories-extraction',
        'omi:auto:memory-graph',
        'omi:auto:conv-action-items',
        'omi:auto:conv-structure',
        'omi:auto:general-assistant',
        'omi:auto:reasoning',
        'omi:auto:stt-realtime',
        'omi:auto:transcription',
        'omi:auto:screenshot-understanding',
        'omi:auto:screenshot-embedding',
        'omi:auto:realtime-ptt',
        'omi:auto:persona-chat',
        'omi:auto:notification-classifier',
    }
)
_ALL_LANE_IDS = frozenset({LANE_ID} | _R0_NEW_LANE_IDS)


def test_loads_default_gateway_config():
    config = load_gateway_config(prod_mode=False)

    # R0 expansion: 15 lanes total (1 existing + 14 new). See .aidlc/spec.md.
    assert set(config.lanes) == _ALL_LANE_IDS
    lane = config.lanes[LANE_ID]
    assert lane.active_route == ACTIVE_ROUTE
    assert lane.last_known_good == LKG_ROUTE
    assert config.route_artifacts[ACTIVE_ROUTE].content_digest.startswith('sha256:')
    assert config.feature_bundles['chat_extraction.requires_context'].lane_id == LANE_ID


@pytest.mark.parametrize('lane_id', sorted(_ALL_LANE_IDS))
def test_objective_sums_to_one_for_all_lanes(lane_id):
    """Every lane's objective (quality+latency+cost) must sum to 1.0 within 1e-3."""
    cfg = load_gateway_config(prod_mode=False)
    obj = cfg.lanes[lane_id].objective
    assert abs(obj.quality + obj.latency + obj.cost - 1.0) < 1e-3


@pytest.mark.parametrize('lane_id', sorted(_R0_NEW_LANE_IDS))
def test_new_lane_has_active_route_equal_to_last_known_good(lane_id):
    """R0 day-one invariant: last_known_good == active_route for every new lane.

    This makes a swap-day regression in R1+ revert to today's behavior in one
    executor call. Drift here means the safety net is broken.
    """
    cfg = load_gateway_config(prod_mode=False)
    lane = cfg.lanes[lane_id]
    assert lane.last_known_good == lane.active_route


@pytest.mark.parametrize('lane_id', sorted(_R0_NEW_LANE_IDS))
def test_new_lane_is_shadow_zero_percent(lane_id):
    """R0 read-review-only: every new lane ships in shadow mode with percent=0.

    The gateway's shadow-mode behavior applies — no traffic shift. R3 lifts
    this to dual-path; R4's nightly cron never auto-merges.
    """
    cfg = load_gateway_config(prod_mode=False)
    lane = cfg.lanes[lane_id]
    # The lane itself doesn't carry rollout — that's per-artifact. Resolve
    # the artifact and assert its rollout shape.
    artifact = cfg.route_artifacts[lane.active_route]
    assert artifact.rollout.stage == 'shadow'
    assert artifact.rollout.percent == 0


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


def test_r0_placeholder_artifacts_load_in_all_modes():
    """R0 ships 3 placeholder artifacts (stt-realtime, transcription,
    screenshot-embedding) that are PROD-ELIGIBLE — they load in any prod_mode
    so the day-one shadow-mode contract holds (config loads in production,
    even though no traffic actually flows because rollout.percent=0).

    The "placeholder" marker is via `evidence.placeholder=True`, NOT via
    `dev_only=True`. Future promotion logic (R1 emitter, R4 cron) reads the
    `placeholder` field separately to know these need replacement before
    being promoted to active. See cubic P1 review on PR #8739.
    """
    cfg_dev = load_gateway_config(prod_mode=False)
    cfg_prod = load_gateway_config(prod_mode=True)
    assert len(cfg_dev.route_artifacts) == 17
    assert len(cfg_prod.route_artifacts) == 17  # All 17 load in production too
    placeholder_ids = {
        'route.stt_realtime.2026_07_01.001',
        'route.transcription.2026_07_01.001',
        'route.screenshot_embedding.2026_07_01.001',
    }
    for rid in placeholder_ids:
        assert rid in cfg_prod.route_artifacts, f'placeholder {rid} should load in prod_mode=True (day-one invariant)'
        assert cfg_prod.route_artifacts[rid].evidence.placeholder is True
        assert cfg_prod.route_artifacts[rid].evidence.is_prod_eligible() is True


def test_r0_placeholder_field_distinguishes_placeholders_from_real_artifacts():
    """Sanity check: the 3 placeholders carry placeholder=True; the other 14
    R0 artifacts + 2 existing chat-structured artifacts carry placeholder=False.

    This is the structural signal future promotion logic reads (NOT is_prod_eligible)
    to know which artifacts to replace vs preserve.
    """
    cfg = load_gateway_config(prod_mode=True)
    placeholder_route_ids = {
        'route.stt_realtime.2026_07_01.001',
        'route.transcription.2026_07_01.001',
        'route.screenshot_embedding.2026_07_01.001',
    }
    for rid, artifact in cfg.route_artifacts.items():
        if rid in placeholder_route_ids:
            assert artifact.evidence.placeholder is True, f'{rid} should be marked placeholder=True'
            assert (
                artifact.evidence.is_prod_eligible() is True
            ), f'{rid} must remain prod-eligible (placeholder ≠ dev_only)'
        else:
            assert artifact.evidence.placeholder is False, f'{rid} should default to placeholder=False'
            assert artifact.evidence.is_prod_eligible() is True


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
