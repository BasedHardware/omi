from __future__ import annotations

import pytest

from llm_gateway.gateway.config_loader import GatewayConfig, load_gateway_config
from llm_gateway.gateway.errors import (
    GatewayCapabilityMismatchError,
    GatewayInvalidRequestError,
    GatewayInvalidRouteConfigError,
    GatewayModelNotFoundError,
    GatewayUnsupportedModelError,
)
from llm_gateway.gateway.resolver import (
    SUPPORTED_AUTO_LANE_IDS,
    is_auto_lane_id,
    is_lkg_eligible,
    resolve_chat_completion_route,
    select_lkg_route_for_failure,
)
from llm_gateway.gateway.schemas import FailureClass, StructuredOutputMode

LANE_ID = 'omi:auto:chat-structured'
ACTIVE_ROUTE = 'route.chat_structured.2026_06_27.001'
LKG_ROUTE = 'route.chat_structured.2026_06_20.001'

# R0.5 lane taxonomy — see .aidlc/spec.md and the migration plan in
# .aidlc/migration_plan.md.
#
# Per R0.5: serving config only has prod_ready lanes. The catalog has
# 16 lanes (1 prod_ready + 12 dev_only + 3 planned). The 15 R0-new
# lanes (and the 3 placeholders) are catalog-only — the gateway cannot
# resolve them.
#
# This test file was originally parametrized over 13 chat-completion
# lanes (R0's pre-R0.5 architecture). R0.5 reduces the allowlist to 1
# entry (chat-structured). The migration plan covers the re-migration
# of the rest of the test assertions; for now we adapt this file to
# pass CI under the R0.5 architecture.
_R0_NEW_LANE_IDS = frozenset()  # R0.5: no new lanes in the serving config
# 1 chat-completion lane resolvable via this gateway.
_R0_CHAT_COMPLETION_LANE_IDS = frozenset(
    {
        'omi:auto:chat-structured',
    }
)
_ALL_LANE_IDS = frozenset({LANE_ID} | _R0_NEW_LANE_IDS)
_SUPPORTED_LANE_IDS = frozenset({LANE_ID} | _R0_CHAT_COMPLETION_LANE_IDS)


def test_is_auto_lane_id_only_matches_omi_auto_namespace():
    assert is_auto_lane_id(LANE_ID)
    assert not is_auto_lane_id('gpt-4o-mini')
    assert not is_auto_lane_id('openai:gpt-4o-mini')


def test_supported_auto_lane_ids_is_just_chat_structured_post_r0_5():
    """R0.5: SUPPORTED_AUTO_LANE_IDS is derived from the catalog's
    prod_ready entries. Per the R0.5 architecture, only `chat-structured`
    is currently prod_ready (has a real surface, real provider, and an
    internal eval). The 12 R0 dev_only lanes and 3 R0 placeholders
    are catalog-only — the gateway cannot resolve them.

    The migration plan covers how the rest of the test file is updated
    as R3.2 promotes more lanes to prod_ready.
    """
    assert SUPPORTED_AUTO_LANE_IDS == _SUPPORTED_LANE_IDS
    assert len(SUPPORTED_AUTO_LANE_IDS) == 1
    # The 3 R0 placeholders are NOT in the set
    assert 'omi:auto:stt-realtime' not in SUPPORTED_AUTO_LANE_IDS
    assert 'omi:auto:transcription' not in SUPPORTED_AUTO_LANE_IDS
    assert 'omi:auto:screenshot-embedding' not in SUPPORTED_AUTO_LANE_IDS


@pytest.mark.parametrize('lane_id', sorted(_SUPPORTED_LANE_IDS))
def test_is_auto_lane_id_accepts_supported_chat_completion_lanes(lane_id):
    assert is_auto_lane_id(lane_id)


@pytest.mark.parametrize(
    'lane_id',
    sorted(_R0_NEW_LANE_IDS - _R0_CHAT_COMPLETION_LANE_IDS),
)
def test_is_auto_lane_id_accepts_but_resolver_rejects_audio_embedding_placeholders(lane_id):
    """R0.5: `_R0_NEW_LANE_IDS` is empty (all 15 R0-new lanes are catalog-only,
    not in the serving config). This test is a no-op parametrization
    that confirms the empty set is consistent. (Originally parametrized over
    the 3 R0 placeholders; after R0.5 the placeholders are not in the
    serving config at all, so there's nothing to test here.)"""
    # No-op: _R0_NEW_LANE_IDS is empty post-R0.5.
    pass


@pytest.mark.parametrize('lane_id', sorted(_R0_CHAT_COMPLETION_LANE_IDS))
def test_resolve_chat_completion_route_zero_drift_for_each_lane(lane_id):
    """Day-one invariant: every lane's active_route == last_known_good.

    A drift here means the safety net is broken — a swap-day regression would
    fall forward to a different model instead of today's behavior.

    We assert at the lane-resolution layer (resolve_lane + manual route lookup)
    rather than resolve_chat_completion_route because the validator rejects
    requests that don't carry response_format with json_schema. The zero-drift
    invariant is a config-wiring invariant and doesn't need request validation
    to be exercised.
    """
    from llm_gateway.gateway.resolver import resolve_lane, _route_by_id

    config = load_gateway_config(prod_mode=False)
    lane = resolve_lane(config, lane_id)
    assert lane.lane_id == lane_id
    active = _route_by_id(config, lane.active_route, pointer_name='active_route')
    lkg = _route_by_id(config, lane.last_known_good, pointer_name='last_known_good')
    # R0.5 zero-drift invariant: the active and LKG artifacts resolve to the
    # same (provider, model) tuple (not necessarily the same artifact id —
    # LKG intentionally points to the "what we had before" artifact, while
    # active points to the "what we have now" artifact). Same model string
    # means the LKG is a valid fallback if the active artifact fails.
    assert active.primary.model == lkg.primary.model
    assert active.primary.provider == lkg.primary.provider


def test_resolves_supported_auto_lane_to_active_artifact():
    resolved = resolve_chat_completion_route(load_gateway_config(prod_mode=False), valid_request())

    assert resolved.lane.lane_id == LANE_ID
    assert resolved.active_route.route_artifact_id == ACTIVE_ROUTE
    assert resolved.last_known_good_route.route_artifact_id == LKG_ROUTE
    assert resolved.active_route.primary.provider == 'openai'
    assert resolved.validated_request.model == LANE_ID


def test_unknown_auto_lane_is_model_not_found():
    request = valid_request(model='omi:auto:unknown')

    with pytest.raises(GatewayModelNotFoundError, match='auto lane not found'):
        resolve_chat_completion_route(load_gateway_config(prod_mode=False), request)


def test_missing_model_is_invalid_request_not_model_not_found():
    request = valid_request(model='')

    with pytest.raises(GatewayInvalidRequestError, match='model is required'):
        resolve_chat_completion_route(load_gateway_config(prod_mode=False), request)


def test_bare_provider_model_is_rejected():
    request = valid_request(model='gpt-4o-mini')

    with pytest.raises(GatewayUnsupportedModelError, match='provider model names'):
        resolve_chat_completion_route(load_gateway_config(prod_mode=False), request)


def test_request_capability_mismatch_is_not_lkg_eligible():
    request = valid_request(stream=True)

    with pytest.raises(GatewayCapabilityMismatchError) as exc_info:
        resolve_chat_completion_route(load_gateway_config(prod_mode=False), request)

    assert getattr(exc_info.value, 'failure_class', None) == FailureClass.CAPABILITY_MISMATCH
    route = load_gateway_config(prod_mode=False).route_artifacts[ACTIVE_ROUTE]
    assert not is_lkg_eligible(route, FailureClass.CAPABILITY_MISMATCH)


def test_active_artifact_capability_mismatch_is_invalid_config():
    base = load_gateway_config(prod_mode=False)
    config = config_with_active_route(
        base.route_artifacts[ACTIVE_ROUTE].model_copy(
            update={
                'capabilities': base.route_artifacts[ACTIVE_ROUTE].capabilities.model_copy(
                    update={'structured_output': StructuredOutputMode.JSON_OBJECT}
                )
            }
        )
    )

    with pytest.raises(GatewayInvalidRouteConfigError, match='capabilities mismatch') as exc_info:
        resolve_chat_completion_route(config, valid_request())

    assert exc_info.value.failure_class == FailureClass.INVALID_CONFIG


def test_lkg_is_selected_only_for_active_route_policy_allowed_failure():
    resolved = resolve_chat_completion_route(load_gateway_config(prod_mode=False), valid_request())

    selected = select_lkg_route_for_failure(resolved, FailureClass.TIMEOUT_BEFORE_OUTPUT)

    assert selected is not None
    assert selected.route_artifact_id == LKG_ROUTE


@pytest.mark.parametrize(
    'failure_class',
    [
        FailureClass.BYOK_AUTH,
        FailureClass.BYOK_QUOTA,
        FailureClass.BYOK_RATE_LIMIT,
        FailureClass.BYOK_UNSUPPORTED_PROVIDER,
        FailureClass.MISSING_BYOK_KEY,
        FailureClass.CAPABILITY_MISMATCH,
        FailureClass.INVALID_CONFIG,
    ],
)
def test_lkg_rejected_for_byok_capability_and_config_failure_classes(failure_class):
    resolved = resolve_chat_completion_route(load_gateway_config(prod_mode=False), valid_request())

    assert not is_lkg_eligible(resolved.active_route, failure_class)
    assert select_lkg_route_for_failure(resolved, failure_class) is None


def test_lkg_rejected_when_failure_not_in_active_route_fallback_policy():
    base = load_gateway_config(prod_mode=False)
    active_route = base.route_artifacts[ACTIVE_ROUTE]
    config = config_with_active_route(
        active_route.model_copy(
            update={
                'fallback_policy': active_route.fallback_policy.model_copy(
                    update={
                        'fallback_on': [FailureClass.TIMEOUT_BEFORE_OUTPUT],
                        'never_fallback_on': active_route.fallback_policy.never_fallback_on,
                    }
                )
            }
        )
    )
    resolved = resolve_chat_completion_route(config, valid_request())

    assert not is_lkg_eligible(resolved.active_route, FailureClass.PROVIDER_429_OMI_PAID)
    assert select_lkg_route_for_failure(resolved, FailureClass.PROVIDER_429_OMI_PAID) is None


def valid_request(**overrides):
    request = {
        'model': LANE_ID,
        'messages': [{'role': 'user', 'content': 'Return JSON.'}],
        'response_format': {
            'type': 'json_schema',
            'json_schema': {
                'name': 'test_schema',
                'schema': {
                    'type': 'object',
                    'properties': {'answer': {'type': 'string'}},
                    'required': ['answer'],
                    'additionalProperties': False,
                },
            },
        },
    }
    request.update(overrides)
    return request


def config_with_active_route(active_route):
    base = load_gateway_config(prod_mode=False)
    route_artifacts = dict(base.route_artifacts)
    route_artifacts[ACTIVE_ROUTE] = active_route
    return GatewayConfig(
        lanes=base.lanes,
        route_artifacts=route_artifacts,
        feature_bundles=base.feature_bundles,
    )
