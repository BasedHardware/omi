from __future__ import annotations

import os
from pathlib import Path
from collections.abc import Mapping
from typing import Any, TypeAlias, cast

import yaml
from pydantic import BaseModel, ConfigDict

from llm_gateway.gateway.schemas import FeatureBundle, GeneratedRouteOverride, LaneConfig, RouteArtifact
from utils.llm.gateway_client import feature_auto_lane_id
from utils.llm.model_config import (
    get_all_configured_features,
    get_model,
    get_provider,
    get_route_options,
    is_structured_output_feature,
)

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[1] / 'config'
PROD_ENV_VAR = 'OMI_LLM_GATEWAY_PROD'
GENERATED_ROUTE_OVERRIDES_FILE = 'generated_route_overrides.yaml'
ConfigItem: TypeAlias = dict[str, Any]


class ConfigValidationError(ValueError):
    pass


class GatewayConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')

    lanes: dict[str, LaneConfig]
    route_artifacts: dict[str, RouteArtifact]
    feature_bundles: dict[str, FeatureBundle]


def load_gateway_config(config_dir: str | Path | None = None, *, prod_mode: bool | None = None) -> GatewayConfig:
    resolved_config_dir = Path(config_dir) if config_dir is not None else DEFAULT_CONFIG_DIR
    resolved_prod_mode = _resolve_prod_mode(prod_mode)

    lane_items = _load_config_list(resolved_config_dir / 'lanes.yaml', 'lanes')
    artifact_items = _load_config_list(resolved_config_dir / 'route_artifacts.yaml', 'route_artifacts')
    bundle_items = _load_config_list(resolved_config_dir / 'feature_bundles.yaml', 'feature_bundles')

    generated_route_overrides = load_generated_route_overrides(resolved_config_dir)
    generated_lane_items, generated_artifact_items, generated_bundle_items = _generated_feature_route_items(
        generated_route_overrides
    )

    lanes = _parse_lanes([*generated_lane_items, *lane_items])
    route_artifacts = _parse_route_artifacts([*generated_artifact_items, *artifact_items], prod_mode=resolved_prod_mode)
    feature_bundles = _parse_feature_bundles([*generated_bundle_items, *bundle_items])

    _validate_lane_routes(lanes, route_artifacts)
    _validate_feature_bundles(feature_bundles, lanes)

    return GatewayConfig(lanes=lanes, route_artifacts=route_artifacts, feature_bundles=feature_bundles)


def load_generated_route_overrides(
    config_dir: str | Path | None = None,
) -> dict[str, GeneratedRouteOverride]:
    resolved_config_dir = Path(config_dir) if config_dir is not None else DEFAULT_CONFIG_DIR
    items = _load_optional_config_list(
        resolved_config_dir / GENERATED_ROUTE_OVERRIDES_FILE,
        'generated_route_overrides',
    )
    configured_features = get_all_configured_features()
    overrides: dict[str, GeneratedRouteOverride] = {}
    for item in items:
        override = GeneratedRouteOverride.model_validate(item)
        if override.feature not in configured_features:
            raise ConfigValidationError(f'gateway route override references unknown feature: {override.feature}')
        if override.feature in overrides:
            raise ConfigValidationError(f'duplicate gateway route override: {override.feature}')
        overrides[override.feature] = override
    return overrides


def _resolve_prod_mode(prod_mode: bool | None) -> bool:
    if prod_mode is not None:
        return prod_mode
    return os.getenv(PROD_ENV_VAR, '').strip().lower() in {'1', 'true', 'yes'}


def _load_config_list(path: Path, top_level_key: str) -> list[ConfigItem]:
    if not path.exists():
        raise ConfigValidationError(f'missing gateway config file: {path}')

    with path.open('r', encoding='utf-8') as handle:
        loaded = cast(object, yaml.safe_load(handle))

    raw_items: object
    if loaded is None:
        return []
    if isinstance(loaded, list):
        raw_items = cast(list[object], loaded)
    elif isinstance(loaded, dict) and top_level_key in loaded:
        loaded_mapping = cast(Mapping[str, object], loaded)
        raw_items = loaded_mapping[top_level_key]
    else:
        raise ConfigValidationError(f'{path} must contain a list or top-level {top_level_key} list')

    if not isinstance(raw_items, list):
        raise ConfigValidationError(f'{path} {top_level_key} must be a list')
    items = cast(list[object], raw_items)
    for item in items:
        if not isinstance(item, Mapping):
            raise ConfigValidationError(f'{path} {top_level_key} entries must be mappings')
    return [dict(cast(Mapping[str, Any], item)) for item in items]


def _load_optional_config_list(path: Path, top_level_key: str) -> list[ConfigItem]:
    if not path.exists():
        return []
    return _load_config_list(path, top_level_key)


def _parse_lanes(items: list[ConfigItem]) -> dict[str, LaneConfig]:
    lanes: dict[str, LaneConfig] = {}
    for item in items:
        lane = LaneConfig.model_validate(item)
        if lane.lane_id in lanes:
            raise ConfigValidationError(f'duplicate lane_id: {lane.lane_id}')
        lanes[lane.lane_id] = lane
    return lanes


def _parse_route_artifacts(items: list[ConfigItem], *, prod_mode: bool) -> dict[str, RouteArtifact]:
    route_artifacts: dict[str, RouteArtifact] = {}
    for item in items:
        artifact = RouteArtifact.model_validate(item)
        if artifact.route_artifact_id in route_artifacts:
            raise ConfigValidationError(f'duplicate route_artifact_id: {artifact.route_artifact_id}')
        if artifact.artifact_digest is not None and artifact.artifact_digest != artifact.content_digest:
            raise ConfigValidationError(
                f'artifact_digest mismatch for {artifact.route_artifact_id}: '
                f'expected {artifact.content_digest}, got {artifact.artifact_digest}'
            )
        if prod_mode and not artifact.evidence.is_prod_eligible():
            raise ConfigValidationError(f'route artifact {artifact.route_artifact_id} uses dev-only benchmark evidence')
        route_artifacts[artifact.route_artifact_id] = artifact
    return route_artifacts


def _parse_feature_bundles(items: list[ConfigItem]) -> dict[str, FeatureBundle]:
    feature_bundles: dict[str, FeatureBundle] = {}
    for item in items:
        bundle = FeatureBundle.model_validate(item)
        if bundle.feature in feature_bundles:
            raise ConfigValidationError(f'duplicate feature bundle: {bundle.feature}')
        feature_bundles[bundle.feature] = bundle
    return feature_bundles


def _validate_lane_routes(lanes: dict[str, LaneConfig], route_artifacts: dict[str, RouteArtifact]) -> None:
    for lane in lanes.values():
        active = _route_for_lane_pointer(lane, 'active_route', lane.active_route, route_artifacts)
        last_known_good = _route_for_lane_pointer(lane, 'last_known_good', lane.last_known_good, route_artifacts)
        _validate_route_matches_lane(lane, active, 'active_route')
        _validate_route_matches_lane(lane, last_known_good, 'last_known_good')


def _route_for_lane_pointer(
    lane: LaneConfig,
    pointer_name: str,
    route_artifact_id: str,
    route_artifacts: dict[str, RouteArtifact],
) -> RouteArtifact:
    artifact = route_artifacts.get(route_artifact_id)
    if artifact is None:
        raise ConfigValidationError(f'lane {lane.lane_id} {pointer_name} route not found: {route_artifact_id}')
    return artifact


def _validate_route_matches_lane(lane: LaneConfig, artifact: RouteArtifact, pointer_name: str) -> None:
    prefix = f'lane {lane.lane_id} {pointer_name} {artifact.route_artifact_id}'
    if artifact.lane_id != lane.lane_id:
        raise ConfigValidationError(f'{prefix} lane_id mismatch: {artifact.lane_id}')
    if artifact.surface != lane.surface:
        raise ConfigValidationError(f'{prefix} surface mismatch: {artifact.surface}')
    if artifact.capabilities.structured_output != lane.capabilities.structured_output:
        raise ConfigValidationError(f'{prefix} structured_output mismatch')
    if artifact.capabilities != lane.capabilities:
        raise ConfigValidationError(f'{prefix} capabilities mismatch')
    if artifact.credential_policy.mode != lane.credential_policy.mode:
        raise ConfigValidationError(f'{prefix} credential mode mismatch: {artifact.credential_policy.mode}')


def _validate_feature_bundles(feature_bundles: dict[str, FeatureBundle], lanes: dict[str, LaneConfig]) -> None:
    for bundle in feature_bundles.values():
        if bundle.lane_id not in lanes:
            raise ConfigValidationError(f'feature bundle {bundle.feature} references unknown lane: {bundle.lane_id}')


def feature_lane_id(feature: str) -> str:
    return feature_auto_lane_id(feature)


def _generated_feature_route_items(
    route_overrides: Mapping[str, GeneratedRouteOverride],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    lanes: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    bundles: list[dict[str, Any]] = []
    for feature in sorted(get_all_configured_features()):
        legacy_model = get_model(feature)
        legacy_provider = get_provider(feature)
        override = route_overrides.get(feature)
        model = override.primary.model if override is not None else legacy_model
        provider = override.primary.provider if override is not None else legacy_provider
        lane_id = feature_lane_id(feature)
        route_id = f"route.{feature}.model_config.001"
        surface = _surface_for_feature(feature, provider)
        capabilities = _capabilities_for_feature(feature, provider=provider, surface=surface)
        credential_policy = _credential_policy()

        lanes.append(
            {
                'lane_id': lane_id,
                'surface': surface,
                'capabilities': capabilities,
                'objective': {'quality': 0.6, 'latency': 0.2, 'cost': 0.2},
                'credential_policy': credential_policy,
                'active_route': route_id,
                'last_known_good': route_id,
            }
        )
        primary = {'provider': provider, 'model': _provider_model_name(provider, model)}
        provider_options = get_route_options(feature, model, provider)
        if override is not None:
            provider_options.update(override.provider_options)
        artifacts.append(
            {
                'route_artifact_id': route_id,
                'lane_id': lane_id,
                'surface': surface,
                'primary': primary,
                'fallbacks': [],
                'provider_options': provider_options,
                'timeouts': {'request_ms': 120000 if capabilities['streaming'] else 30000},
                'retry': {'max_attempts': 1},
                'capabilities': capabilities,
                'evidence': {
                    'benchmark_snapshot': 'model_config.source_of_truth',
                    'eval_report': f'{feature}.gateway_coverage',
                    'benchmark_source': 'omi_eval',
                    'dev_only': False,
                },
                'rollout': {'stage': 'active', 'percent': 100},
                'credential_policy': credential_policy,
                'fallback_policy': {
                    'fallback_on': ['timeout_before_output', 'provider_429_omi_paid', 'provider_5xx_omi_paid'],
                    'never_fallback_on': [
                        'byok_auth',
                        'byok_quota',
                        'byok_rate_limit',
                        'byok_unsupported_provider',
                        'missing_byok_key',
                        'capability_mismatch',
                        'invalid_config',
                    ],
                },
            }
        )
        bundles.append(
            {
                'feature': feature,
                'lane_id': lane_id,
                'prompt_version': f'{feature}.model_config',
                'parser_version': 'callsite',
                'eval_suite': f'{feature}.gateway_coverage',
                'promotion_gates': {'inventory_status': 'gateway_managed'},
            }
        )
    return lanes, artifacts, bundles


def _surface_for_feature(feature: str, provider: str) -> str:
    if feature == 'chat_agent' and provider == 'anthropic':
        return 'anthropic.messages'
    return 'openai.chat_completions'


def _capabilities_for_feature(feature: str, *, provider: str, surface: str) -> dict[str, Any]:
    structured_output = 'json_schema' if is_structured_output_feature(feature) else 'none'
    anthropic_messages = surface == 'anthropic.messages'
    return {
        'text_input': True,
        'streaming': anthropic_messages or provider in {'openai', 'openrouter', 'perplexity', 'gemini'},
        'structured_output': structured_output,
        'tools': anthropic_messages or feature == 'memory_l2',
    }


def _credential_policy() -> dict[str, Any]:
    return {
        'mode': 'omi_paid',
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


def _provider_model_name(provider: str, model: str) -> str:
    if provider == 'openrouter' and model.startswith('gemini'):
        return f'google/{model}'
    return model
