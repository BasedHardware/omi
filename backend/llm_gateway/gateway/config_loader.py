from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable

import yaml
from pydantic import BaseModel, ConfigDict

from llm_gateway.gateway.schemas import FeatureBundle, LaneConfig, RouteArtifact

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[1] / 'config'
PROD_ENV_VAR = 'OMI_LLM_GATEWAY_PROD'


class ConfigValidationError(ValueError):
    pass


class GatewayConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')

    lanes: dict[str, LaneConfig]
    route_artifacts: dict[str, RouteArtifact]
    feature_bundles: dict[str, FeatureBundle]


def load_gateway_config(
    config_dir: str | Path | None = None,
    *,
    prod_mode: bool | None = None,
    required_lane_ids: Iterable[str] | None = None,
) -> GatewayConfig:
    """Load the gateway config from `config_dir`.

    Parameters:
        config_dir: Directory containing lanes.yaml, route_artifacts.yaml,
            feature_bundles.yaml. Defaults to the gateway's package config dir.
        prod_mode: If True, reject dev-only artifacts (production readiness check).
            If None, defer to the OMI_LLM_GATEWAY_PROD env var.
        required_lane_ids: Optional iterable of lane ids that MUST exist in
            lanes.yaml after load. Missing ids raise ConfigValidationError.
            Defaults to None (no cross-validation). The gateway's startup
            path passes SUPPORTED_AUTO_LANE_IDS here to fail fast if a
            supported lane is missing from YAML.
    """
    resolved_config_dir = Path(config_dir) if config_dir is not None else DEFAULT_CONFIG_DIR
    resolved_prod_mode = _resolve_prod_mode(prod_mode)

    lane_items = _load_config_list(resolved_config_dir / 'lanes.yaml', 'lanes')
    artifact_items = _load_config_list(resolved_config_dir / 'route_artifacts.yaml', 'route_artifacts')
    bundle_items = _load_config_list(resolved_config_dir / 'feature_bundles.yaml', 'feature_bundles')

    lanes = _parse_lanes(lane_items)
    route_artifacts = _parse_route_artifacts(artifact_items, prod_mode=resolved_prod_mode)
    feature_bundles = _parse_feature_bundles(bundle_items)

    _validate_lane_routes(lanes, route_artifacts)
    _validate_feature_bundles(feature_bundles, lanes)
    if required_lane_ids is not None:
        _validate_required_lane_ids(required_lane_ids, lanes)

    return GatewayConfig(lanes=lanes, route_artifacts=route_artifacts, feature_bundles=feature_bundles)


def _resolve_prod_mode(prod_mode: bool | None) -> bool:
    if prod_mode is not None:
        return prod_mode
    return os.getenv(PROD_ENV_VAR, '').strip().lower() in {'1', 'true', 'yes'}


def _load_config_list(path: Path, top_level_key: str) -> list[dict[str, Any]]:
    if not path.exists():
        raise ConfigValidationError(f'missing gateway config file: {path}')

    with path.open('r', encoding='utf-8') as handle:
        try:
            loaded = yaml.safe_load(handle)
        except yaml.YAMLError as e:
            raise ConfigValidationError(f'malformed YAML in {path}: {e}') from e

    if loaded is None:
        return []
    if isinstance(loaded, list):
        items = loaded
    elif isinstance(loaded, dict) and top_level_key in loaded:
        items = loaded[top_level_key]
    else:
        raise ConfigValidationError(f'{path} must contain a list or top-level {top_level_key} list')

    if not isinstance(items, list):
        raise ConfigValidationError(f'{path} {top_level_key} must be a list')
    for item in items:
        if not isinstance(item, dict):
            raise ConfigValidationError(f'{path} {top_level_key} entries must be mappings')
    return items


def _parse_lanes(items: list[dict[str, Any]]) -> dict[str, LaneConfig]:
    lanes: dict[str, LaneConfig] = {}
    for item in items:
        lane = LaneConfig.model_validate(item)
        if lane.lane_id in lanes:
            raise ConfigValidationError(f'duplicate lane_id: {lane.lane_id}')
        lanes[lane.lane_id] = lane
    return lanes


def _parse_route_artifacts(items: list[dict[str, Any]], *, prod_mode: bool) -> dict[str, RouteArtifact]:
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


def _parse_feature_bundles(items: list[dict[str, Any]]) -> dict[str, FeatureBundle]:
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


def _validate_required_lane_ids(
    required_lane_ids: Iterable[str],
    lanes: dict[str, LaneConfig],
) -> None:
    """Cross-check that every required lane id has a corresponding lanes.yaml entry.

    Per PLAN.md §R5b + cubic-dev-ai review on PR #8744: if a lane is in
    SUPPORTED_AUTO_LANE_IDS but missing from lanes.yaml, the config loads
    successfully and the failure is deferred to runtime. Cross-validate
    here so the failure surfaces at startup (or at the next reload).
    """
    required = set(required_lane_ids)
    missing = sorted(required - set(lanes.keys()))
    if missing:
        raise ConfigValidationError(
            f'lanes.yaml is missing required lane ids: {missing}. '
            f'Add them to lanes.yaml or remove them from the supported allowlist.'
        )
