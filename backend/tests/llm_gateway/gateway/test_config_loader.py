import pytest
import yaml

from llm_gateway.gateway.config_loader import (
    ConfigValidationError,
    _capabilities_for_feature,
    _credential_policy,
    _desktop_overflow_origin_options,
    _generated_desktop_vertex_items,
    _generated_embedding_items,
    _generated_feature_route_items,
    _generated_systemone_items,
    _load_config_list,
    _output_budget_for_feature,
    _parse_feature_bundles,
    _parse_lanes,
    _parse_route_artifacts,
    _provider_model_name,
    _resolve_prod_mode,
    _surface_for_feature,
    _validate_feature_bundles,
    _validate_lane_routes,
    _validate_route_matches_lane,
    load_gateway_config,
    load_generated_route_overrides,
)
from llm_gateway.gateway.schemas import FeatureBundle, GeneratedRouteOverride, LaneConfig, ProviderRef, RouteArtifact
from utils.llm import vertex_pt_routing as ptr


def test_load_gateway_config_no_args():
    config = load_gateway_config()
    assert config is not None
    assert config.lanes
    assert config.route_artifacts
    assert config.feature_bundles


def test_load_gateway_config_prod_mode_env_var(monkeypatch):
    monkeypatch.setenv("OMI_LLM_GATEWAY_PROD", "1")
    config = load_gateway_config()
    assert config is not None


def test_load_config_list_missing_file(tmp_path):
    with pytest.raises(ConfigValidationError, match="missing gateway config file"):
        _load_config_list(tmp_path / "does_not_exist.yaml", "test_key")


def test_load_config_list_empty_file(tmp_path):
    f = tmp_path / "empty.yaml"
    f.write_text("")
    assert _load_config_list(f, "test_key") == []


def test_load_config_list_invalid_yaml(tmp_path):
    f = tmp_path / "invalid.yaml"
    f.write_text("invalid: [")
    with pytest.raises(yaml.parser.ParserError):
        _load_config_list(f, "test_key")


def test_load_config_list_not_a_list(tmp_path):
    f = tmp_path / "not_list.yaml"
    f.write_text("key: value")
    with pytest.raises(ConfigValidationError, match="must contain a list or top-level test_key list"):
        _load_config_list(f, "test_key")


def test_load_config_list_from_mapping(tmp_path):
    f = tmp_path / "mapping.yaml"
    f.write_text("test_key:\n  - {id: 1}\n  - {id: 2}")
    result = _load_config_list(f, "test_key")
    assert result == [{"id": 1}, {"id": 2}]


def test_load_config_list_from_list(tmp_path):
    f = tmp_path / "list.yaml"
    f.write_text("- id: 1\n- id: 2")
    result = _load_config_list(f, "test_key")
    assert result == [{"id": 1}, {"id": 2}]


def test_load_config_list_invalid_mapping_list(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("test_key: not a list")
    with pytest.raises(ConfigValidationError, match="test_key must be a list"):
        _load_config_list(f, "test_key")


def test_load_config_list_invalid_item(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("- not_a_mapping")
    with pytest.raises(ConfigValidationError, match="entries must be mappings"):
        _load_config_list(f, "test_key")


def test_parse_lanes_duplicate():
    with pytest.raises(ConfigValidationError, match="duplicate lane_id: omi:auto:test"):
        _parse_lanes(
            [
                {
                    "lane_id": "omi:auto:test",
                    "surface": "openai.chat_completions",
                    "capabilities": {
                        "text_input": True,
                        "streaming": False,
                        "structured_output": "none",
                        "tools": False,
                    },
                    "objective": {"quality": 1.0, "latency": 0.0, "cost": 0.0},
                    "credential_policy": {"mode": "omi_paid"},
                    "active_route": "r1",
                    "last_known_good": "r1",
                },
                {
                    "lane_id": "omi:auto:test",
                    "surface": "openai.chat_completions",
                    "capabilities": {
                        "text_input": True,
                        "streaming": False,
                        "structured_output": "none",
                        "tools": False,
                    },
                    "objective": {"quality": 1.0, "latency": 0.0, "cost": 0.0},
                    "credential_policy": {"mode": "omi_paid"},
                    "active_route": "r2",
                    "last_known_good": "r2",
                },
            ]
        )


def test_parse_route_artifacts_duplicate():
    with pytest.raises(ConfigValidationError, match="duplicate route_artifact_id: r1"):
        _parse_route_artifacts(
            [
                {
                    "route_artifact_id": "r1",
                    "lane_id": "omi:auto:test",
                    "surface": "openai.chat_completions",
                    "primary": {"provider": "p1", "model": "m1"},
                    "timeouts": {"request_ms": 100},
                    "retry": {"max_attempts": 1},
                    "capabilities": {
                        "text_input": True,
                        "streaming": False,
                        "structured_output": "none",
                        "tools": False,
                    },
                    "evidence": {"benchmark_snapshot": "s", "eval_report": "r", "benchmark_source": "omi_eval"},
                    "rollout": {"stage": "active", "percent": 100},
                    "credential_policy": {"mode": "omi_paid"},
                    "fallback_policy": {},
                },
                {
                    "route_artifact_id": "r1",
                    "lane_id": "omi:auto:test",
                    "surface": "openai.chat_completions",
                    "primary": {"provider": "p1", "model": "m1"},
                    "timeouts": {"request_ms": 100},
                    "retry": {"max_attempts": 1},
                    "capabilities": {
                        "text_input": True,
                        "streaming": False,
                        "structured_output": "none",
                        "tools": False,
                    },
                    "evidence": {"benchmark_snapshot": "s", "eval_report": "r", "benchmark_source": "omi_eval"},
                    "rollout": {"stage": "active", "percent": 100},
                    "credential_policy": {"mode": "omi_paid"},
                    "fallback_policy": {},
                },
            ],
            prod_mode=False,
        )


def test_parse_route_artifacts_dev_evidence_in_prod():
    with pytest.raises(ConfigValidationError, match="uses dev-only benchmark evidence"):
        _parse_route_artifacts(
            [
                {
                    "route_artifact_id": "r1",
                    "lane_id": "omi:auto:test",
                    "surface": "openai.chat_completions",
                    "primary": {"provider": "p1", "model": "m1"},
                    "timeouts": {"request_ms": 100},
                    "retry": {"max_attempts": 1},
                    "capabilities": {
                        "text_input": True,
                        "streaming": False,
                        "structured_output": "none",
                        "tools": False,
                    },
                    "evidence": {"benchmark_snapshot": "s", "eval_report": "r", "benchmark_source": "dev_fixture"},
                    "rollout": {"stage": "active", "percent": 100},
                    "credential_policy": {"mode": "omi_paid"},
                    "fallback_policy": {},
                }
            ],
            prod_mode=True,
        )


def test_parse_feature_bundles_duplicate():
    with pytest.raises(ConfigValidationError, match="duplicate feature bundle: f1"):
        _parse_feature_bundles(
            [
                {
                    "feature": "f1",
                    "lane_id": "omi:auto:test",
                    "prompt_version": "1",
                    "parser_version": "1",
                    "eval_suite": "1",
                },
                {
                    "feature": "f1",
                    "lane_id": "omi:auto:test",
                    "prompt_version": "1",
                    "parser_version": "1",
                    "eval_suite": "1",
                },
            ]
        )


def test_validate_lane_routes_missing_route():
    lane = LaneConfig.model_validate(
        {
            "lane_id": "omi:auto:test",
            "surface": "openai.chat_completions",
            "capabilities": {"text_input": True, "streaming": False, "structured_output": "none", "tools": False},
            "objective": {"quality": 1.0, "latency": 0.0, "cost": 0.0},
            "credential_policy": {"mode": "omi_paid"},
            "active_route": "r1",
            "last_known_good": "r1",
        }
    )
    with pytest.raises(ConfigValidationError, match="active_route route not found"):
        _validate_lane_routes({"omi:auto:test": lane}, {})


def test_validate_lane_routes_mismatch():
    lane = LaneConfig.model_validate(
        {
            "lane_id": "omi:auto:test",
            "surface": "openai.chat_completions",
            "capabilities": {"text_input": True, "streaming": False, "structured_output": "none", "tools": False},
            "objective": {"quality": 1.0, "latency": 0.0, "cost": 0.0},
            "credential_policy": {"mode": "omi_paid"},
            "active_route": "r1",
            "last_known_good": "r1",
        }
    )
    artifact = RouteArtifact.model_validate(
        {
            "route_artifact_id": "r1",
            "lane_id": "omi:auto:other",
            "surface": "openai.chat_completions",
            "primary": {"provider": "p1", "model": "m1"},
            "timeouts": {"request_ms": 100},
            "retry": {"max_attempts": 1},
            "capabilities": {"text_input": True, "streaming": False, "structured_output": "none", "tools": False},
            "evidence": {"benchmark_snapshot": "s", "eval_report": "r", "benchmark_source": "omi_eval"},
            "rollout": {"stage": "active", "percent": 100},
            "credential_policy": {"mode": "omi_paid"},
            "fallback_policy": {},
        }
    )
    with pytest.raises(ConfigValidationError, match="lane_id mismatch: omi:auto:other"):
        _validate_lane_routes({"omi:auto:test": lane}, {"r1": artifact})


def test_validate_feature_bundles_unknown_lane():
    bundle = FeatureBundle.model_validate(
        {
            "feature": "f1",
            "lane_id": "omi:auto:missing",
            "prompt_version": "1",
            "parser_version": "1",
            "eval_suite": "1",
        }
    )
    with pytest.raises(ConfigValidationError, match="feature bundle f1 references unknown lane: omi:auto:missing"):
        _validate_feature_bundles({"f1": bundle}, {})


def test_load_generated_route_overrides_missing_file(tmp_path):
    overrides = load_generated_route_overrides(tmp_path)
    assert overrides == {}


def test_load_generated_route_overrides_duplicate(tmp_path, monkeypatch):
    from utils.llm.model_config import get_all_configured_features

    # We just need any valid feature, say the first one
    configured = list(get_all_configured_features())
    feature = configured[0] if configured else "test_feature"

    monkeypatch.setattr("llm_gateway.gateway.config_loader.get_all_configured_features", lambda: {feature})
    f = tmp_path / "generated_route_overrides.yaml"
    f.write_text(f"""
generated_route_overrides:
  - feature: {feature}
    primary: {{provider: p1, model: m1}}
  - feature: {feature}
    primary: {{provider: p2, model: m2}}
""")
    with pytest.raises(ConfigValidationError, match="duplicate gateway route override"):
        load_generated_route_overrides(tmp_path)


def test_load_generated_route_overrides_unknown_feature(tmp_path, monkeypatch):
    monkeypatch.setattr("llm_gateway.gateway.config_loader.get_all_configured_features", lambda: {"known"})
    f = tmp_path / "generated_route_overrides.yaml"
    f.write_text("""
generated_route_overrides:
  - feature: unknown_feature
    primary: {provider: p1, model: m1}
""")
    with pytest.raises(ConfigValidationError, match="references unknown feature"):
        load_generated_route_overrides(tmp_path)


def test_output_budget_for_feature():
    assert _output_budget_for_feature("session_titles", "gemini") == {
        "experiment": "session_titles",
        "max_completion_tokens": 128,
    }
    assert _output_budget_for_feature("session_titles", "openai") is None
    assert _output_budget_for_feature("other", "gemini") is None


def test_surface_for_feature():
    assert _surface_for_feature("chat_agent", "anthropic") == "anthropic.messages"
    assert _surface_for_feature("chat_agent", "openai") == "openai.chat_completions"
    assert _surface_for_feature("other", "anthropic") == "openai.chat_completions"


def test_capabilities_for_feature():
    caps = _capabilities_for_feature("chat_agent", provider="anthropic", surface="anthropic.messages")
    assert caps["text_input"] is True
    assert caps["streaming"] is True
    assert caps["tools"] is True
    assert caps["translation"] is False

    caps = _capabilities_for_feature("translation", provider="openai", surface="openai.chat_completions")
    assert caps["translation"] is True
    assert caps["streaming"] is True


def test_credential_policy():
    policy = _credential_policy()
    assert policy["mode"] == "omi_paid"
    assert not policy["allow_byok_to_omi_paid_fallback"]
    assert "timeout_before_output" in policy["fallback_eligible_failure_classes"]
    assert "byok_auth" in policy["never_fallback_failure_classes"]


def test_provider_model_name():
    assert _provider_model_name("openrouter", "gemini-1.5-pro") == "google/gemini-1.5-pro"
    assert _provider_model_name("openrouter", "llama-3") == "llama-3"
    assert _provider_model_name("openai", "gpt-4") == "gpt-4"


def test_desktop_overflow_origin_options(monkeypatch):
    monkeypatch.setattr(
        "utils.llm.vertex_pt_routing.lane_overflow_origin", lambda x: "test_origin" if x == "a1" else None
    )

    assert _desktop_overflow_origin_options("a1") == {ptr.OVERFLOW_ORIGIN_OPTION: "test_origin"}
    assert _desktop_overflow_origin_options("a2") == {}


def test_generated_desktop_vertex_items(monkeypatch):
    monkeypatch.setattr("utils.llm.vertex_pt_routing.DESKTOP_TEXT_LANES", {"a1": "omi:auto:a1"})
    monkeypatch.setattr("utils.llm.vertex_pt_routing.lane_overflow_origin", lambda x: None)

    lanes, artifacts = _generated_desktop_vertex_items()
    assert len(lanes) == 1
    assert lanes[0]["lane_id"] == "omi:auto:a1"
    assert lanes[0]["surface"] == "openai.chat_completions"
    assert lanes[0]["active_route"] == "route.a1.vertex_pt.001"

    assert len(artifacts) == 1
    assert artifacts[0]["route_artifact_id"] == "route.a1.vertex_pt.001"
    assert artifacts[0]["lane_id"] == "omi:auto:a1"
    assert artifacts[0]["primary"] == {"provider": "gemini", "model": "a1"}


def test_generated_embedding_items():
    lanes, artifacts = _generated_embedding_items()
    assert len(lanes) == 2
    assert len(artifacts) == 2

    openai_lane = next(lane for lane in lanes if lane["lane_id"] == "omi:auto:openai-embeddings")
    assert openai_lane["surface"] == "openai.embeddings"
    assert not openai_lane["capabilities"]["streaming"]

    openai_artifact = next(artifact for artifact in artifacts if artifact["lane_id"] == "omi:auto:openai-embeddings")
    assert openai_artifact["primary"] == {"provider": "openai", "model": "text-embedding-3-large"}


def test_generated_systemone_items():
    lanes, artifacts = _generated_systemone_items()
    assert len(lanes) == 1
    assert len(artifacts) == 1

    lane = lanes[0]
    artifact = artifacts[0]

    assert lane["surface"] == "openrouter.systemone"
    assert not lane["capabilities"]["streaming"]

    assert artifact["surface"] == "openrouter.systemone"
    from config.jev_decisions import JEV_AUTO_LANE_ID, JEV_MODEL, JEV_PROVIDER

    assert artifact["lane_id"] == JEV_AUTO_LANE_ID
    assert artifact["primary"] == {"provider": JEV_PROVIDER, "model": JEV_MODEL}
    assert artifact["fallbacks"] == []


def test_generated_feature_route_items(monkeypatch):
    monkeypatch.setattr(
        "llm_gateway.gateway.config_loader.get_all_configured_features", lambda: {"test_feature1", "test_feature2"}
    )
    monkeypatch.setattr(
        "llm_gateway.gateway.config_loader.get_model",
        lambda f: "model1" if f == "test_feature1" else "model2",
    )
    monkeypatch.setattr(
        "llm_gateway.gateway.config_loader.get_provider",
        lambda f: "provider1" if f == "test_feature1" else "provider2",
    )
    monkeypatch.setattr(
        "llm_gateway.gateway.config_loader.get_route_options",
        lambda f, m, p: {"opt1": "val1"} if f == "test_feature1" else {},
    )
    monkeypatch.setattr("llm_gateway.gateway.config_loader.is_structured_output_feature", lambda f: True)

    route_overrides = {
        "test_feature2": GeneratedRouteOverride(
            feature="test_feature2",
            primary=ProviderRef(provider="provider2_ov", model="model2_ov"),
            provider_options={"opt2": "val2"},
            request_timeout_ms=50000,
        )
    }

    lanes, artifacts, bundles = _generated_feature_route_items(route_overrides)

    assert len(lanes) == 2
    assert len(artifacts) == 2
    assert len(bundles) == 2

    # Check test_feature1 (no override)
    lane1 = next(lane for lane in lanes if lane["lane_id"] == "omi:auto:test-feature1")
    artifact1 = next(
        artifact for artifact in artifacts if artifact["route_artifact_id"] == "route.test_feature1.model_config.001"
    )
    bundle1 = next(bundle for bundle in bundles if bundle["feature"] == "test_feature1")

    assert lane1["active_route"] == "route.test_feature1.model_config.001"
    assert artifact1["primary"] == {"provider": "provider1", "model": "model1"}
    assert artifact1["provider_options"] == {"opt1": "val1"}
    assert bundle1["lane_id"] == "omi:auto:test-feature1"

    # Check test_feature2 (with override)
    _lane2 = next(lane for lane in lanes if lane["lane_id"] == "omi:auto:test-feature2")
    artifact2 = next(
        artifact for artifact in artifacts if artifact["route_artifact_id"] == "route.test_feature2.model_config.001"
    )

    assert artifact2["primary"] == {"provider": "provider2_ov", "model": "model2_ov"}
    assert artifact2["provider_options"] == {"opt2": "val2"}
    assert artifact2["timeouts"]["request_ms"] == 50000


def test_resolve_prod_mode():
    assert _resolve_prod_mode(True) is True
    assert _resolve_prod_mode(False) is False
    assert _resolve_prod_mode(None) is False


def test_parse_route_artifacts_digest_mismatch():
    with pytest.raises(ConfigValidationError, match="artifact_digest mismatch"):
        _parse_route_artifacts(
            [
                {
                    "route_artifact_id": "r1",
                    "lane_id": "omi:auto:test",
                    "surface": "openai.chat_completions",
                    "primary": {"provider": "p1", "model": "m1"},
                    "timeouts": {"request_ms": 100},
                    "retry": {"max_attempts": 1},
                    "capabilities": {
                        "text_input": True,
                        "streaming": False,
                        "structured_output": "none",
                        "tools": False,
                    },
                    "evidence": {"benchmark_snapshot": "s", "eval_report": "r", "benchmark_source": "omi_eval"},
                    "rollout": {"stage": "active", "percent": 100},
                    "credential_policy": {"mode": "omi_paid"},
                    "fallback_policy": {},
                    "artifact_digest": "sha256:wrong_digest",
                }
            ],
            prod_mode=False,
        )


def test_validate_route_matches_lane_surface_mismatch():
    lane = LaneConfig.model_validate(
        {
            "lane_id": "omi:auto:test",
            "surface": "openai.chat_completions",
            "capabilities": {"text_input": True, "streaming": False, "structured_output": "none", "tools": False},
            "objective": {"quality": 1.0, "latency": 0.0, "cost": 0.0},
            "credential_policy": {"mode": "omi_paid"},
            "active_route": "r1",
            "last_known_good": "r1",
        }
    )
    artifact = RouteArtifact.model_validate(
        {
            "route_artifact_id": "r1",
            "lane_id": "omi:auto:test",
            "surface": "anthropic.messages",
            "primary": {"provider": "p1", "model": "m1"},
            "timeouts": {"request_ms": 100},
            "retry": {"max_attempts": 1},
            "capabilities": {"text_input": True, "streaming": False, "structured_output": "none", "tools": False},
            "evidence": {"benchmark_snapshot": "s", "eval_report": "r", "benchmark_source": "omi_eval"},
            "rollout": {"stage": "active", "percent": 100},
            "credential_policy": {"mode": "omi_paid"},
            "fallback_policy": {},
        }
    )
    with pytest.raises(ConfigValidationError, match="surface mismatch: Surface.ANTHROPIC_MESSAGES"):
        _validate_route_matches_lane(lane, artifact, "active_route")


def test_validate_route_matches_lane_structured_output_mismatch():
    lane = LaneConfig.model_validate(
        {
            "lane_id": "omi:auto:test",
            "surface": "openai.chat_completions",
            "capabilities": {
                "text_input": True,
                "streaming": False,
                "structured_output": "json_object",
                "tools": False,
            },
            "objective": {"quality": 1.0, "latency": 0.0, "cost": 0.0},
            "credential_policy": {"mode": "omi_paid"},
            "active_route": "r1",
            "last_known_good": "r1",
        }
    )
    artifact = RouteArtifact.model_validate(
        {
            "route_artifact_id": "r1",
            "lane_id": "omi:auto:test",
            "surface": "openai.chat_completions",
            "primary": {"provider": "p1", "model": "m1"},
            "timeouts": {"request_ms": 100},
            "retry": {"max_attempts": 1},
            "capabilities": {"text_input": True, "streaming": False, "structured_output": "none", "tools": False},
            "evidence": {"benchmark_snapshot": "s", "eval_report": "r", "benchmark_source": "omi_eval"},
            "rollout": {"stage": "active", "percent": 100},
            "credential_policy": {"mode": "omi_paid"},
            "fallback_policy": {},
        }
    )
    with pytest.raises(ConfigValidationError, match="structured_output mismatch"):
        _validate_route_matches_lane(lane, artifact, "active_route")


def test_validate_route_matches_lane_capabilities_mismatch():
    lane = LaneConfig.model_validate(
        {
            "lane_id": "omi:auto:test",
            "surface": "openai.chat_completions",
            "capabilities": {"text_input": True, "streaming": False, "structured_output": "none", "tools": False},
            "objective": {"quality": 1.0, "latency": 0.0, "cost": 0.0},
            "credential_policy": {"mode": "omi_paid"},
            "active_route": "r1",
            "last_known_good": "r1",
        }
    )
    artifact = RouteArtifact.model_validate(
        {
            "route_artifact_id": "r1",
            "lane_id": "omi:auto:test",
            "surface": "openai.chat_completions",
            "primary": {"provider": "p1", "model": "m1"},
            "timeouts": {"request_ms": 100},
            "retry": {"max_attempts": 1},
            "capabilities": {"text_input": True, "streaming": True, "structured_output": "none", "tools": False},
            "evidence": {"benchmark_snapshot": "s", "eval_report": "r", "benchmark_source": "omi_eval"},
            "rollout": {"stage": "active", "percent": 100},
            "credential_policy": {"mode": "omi_paid"},
            "fallback_policy": {},
        }
    )
    with pytest.raises(ConfigValidationError, match="capabilities mismatch"):
        _validate_route_matches_lane(lane, artifact, "active_route")


def test_validate_route_matches_lane_credential_policy_mismatch():
    lane = LaneConfig.model_validate(
        {
            "lane_id": "omi:auto:test",
            "surface": "openai.chat_completions",
            "capabilities": {"text_input": True, "streaming": False, "structured_output": "none", "tools": False},
            "objective": {"quality": 1.0, "latency": 0.0, "cost": 0.0},
            "credential_policy": {"mode": "byok"},
            "active_route": "r1",
            "last_known_good": "r1",
        }
    )
    artifact = RouteArtifact.model_validate(
        {
            "route_artifact_id": "r1",
            "lane_id": "omi:auto:test",
            "surface": "openai.chat_completions",
            "primary": {"provider": "p1", "model": "m1"},
            "timeouts": {"request_ms": 100},
            "retry": {"max_attempts": 1},
            "capabilities": {"text_input": True, "streaming": False, "structured_output": "none", "tools": False},
            "evidence": {"benchmark_snapshot": "s", "eval_report": "r", "benchmark_source": "omi_eval"},
            "rollout": {"stage": "active", "percent": 100},
            "credential_policy": {"mode": "omi_paid"},
            "fallback_policy": {},
        }
    )
    with pytest.raises(ConfigValidationError, match="credential mode mismatch: CredentialMode.OMI_PAID"):
        _validate_route_matches_lane(lane, artifact, "active_route")
