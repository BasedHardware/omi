"""Tests for the R0.5 lane catalog + serving config cross-validation."""

from __future__ import annotations

import pytest
import yaml
from pathlib import Path

from llm_gateway.gateway.lane_catalog import (
    CatalogEntry,
    LaneCatalog,
    ProviderSupportStatus,
    load_catalog,
    validate_serving_config,
)
from llm_gateway.gateway.config_loader import (
    ConfigValidationError,
    GatewayConfig,
    load_gateway_config,
)
from llm_gateway.gateway.schemas import (
    Capabilities,
    CredentialPolicy,
    LaneConfig,
    ProviderRef,
    RouteArtifact,
    StructuredOutputMode,
    Surface,
)

# ---------------------------------------------------------------------------
# Catalog loading
# ---------------------------------------------------------------------------


class TestLoadCatalog:
    def test_load_catalog_from_default_path(self):
        catalog = load_catalog()
        assert isinstance(catalog, LaneCatalog)
        assert len(catalog.lanes) == 16

    def test_catalog_entries_have_required_fields(self):
        catalog = load_catalog()
        for entry in catalog.lanes:
            assert entry.lane_id.startswith("omi:auto:")
            assert entry.provider in {"openai", "anthropic", "tbd"}
            assert entry.surface in {"openai.chat_completions", "unknown"}

    def test_catalog_has_one_prod_ready_lane(self):
        catalog = load_catalog()
        prod_ready = catalog.prod_ready_lane_ids()
        assert prod_ready == {"omi:auto:chat-structured"}

    def test_catalog_has_twelve_dev_only_lanes(self):
        catalog = load_catalog()
        dev_only = [e for e in catalog.lanes if e.provider_support_status == ProviderSupportStatus.DEV_ONLY]
        assert len(dev_only) == 12

    def test_catalog_has_three_planned_lanes(self):
        catalog = load_catalog()
        planned = [e for e in catalog.lanes if e.provider_support_status == ProviderSupportStatus.PLANNED]
        assert len(planned) == 3
        planned_ids = {e.lane_id for e in planned}
        assert planned_ids == {
            "omi:auto:stt-realtime",
            "omi:auto:transcription",
            "omi:auto:screenshot-embedding",
        }

    def test_prod_ready_lane_has_promoted_at(self):
        catalog = load_catalog()
        entry = catalog.get("omi:auto:chat-structured")
        assert entry is not None
        assert entry.provider_support_status == ProviderSupportStatus.PROD_READY
        assert entry.promoted_at is not None

    def test_non_prod_ready_lanes_have_no_promoted_at(self):
        catalog = load_catalog()
        for entry in catalog.lanes:
            if entry.provider_support_status != ProviderSupportStatus.PROD_READY:
                assert (
                    entry.promoted_at is None
                ), f"{entry.lane_id} is not prod_ready but has promoted_at={entry.promoted_at}"

    def test_load_catalog_from_custom_path(self, tmp_path):
        custom = tmp_path / "lanes_catalog.yaml"
        custom.write_text(
            yaml.safe_dump(
                {
                    "lanes": [
                        {
                            "lane_id": "omi:auto:test",
                            "description": "test",
                            "surface": "openai.chat_completions",
                            "provider": "openai",
                            "model": "gpt-4.1-mini",
                            "provider_support_status": "prod_ready",
                            "eval_suite": None,
                            "notes": "",
                            "promoted_at": "2026-07-01T00:00:00Z",
                        }
                    ]
                }
            )
        )
        catalog = load_catalog(custom)
        assert catalog.prod_ready_lane_ids() == {"omi:auto:test"}


# ---------------------------------------------------------------------------
# Cross-validation
# ---------------------------------------------------------------------------


class TestValidateServingConfig:
    def test_valid_serving_config_passes(self):
        catalog = load_catalog()
        validate_serving_config(
            catalog,
            serving_lane_ids={"omi:auto:chat-structured"},
            serving_artifact_ids={"route.chat_structured.2026_06_27.001"},
        )

    def test_serving_lane_not_in_catalog_raises(self):
        catalog = load_catalog()
        with pytest.raises(ValueError, match="not in the catalog"):
            validate_serving_config(
                catalog,
                serving_lane_ids={"omi:auto:chat-structured", "omi:auto:does-not-exist"},
                serving_artifact_ids={"route.chat_structured.2026_06_27.001"},
            )

    def test_serving_lane_marked_dev_only_raises(self):
        """Per David: 'If a lane doesn't have the real surface / provider
        support / eval yet, keep it catalog-only'. A dev_only catalog entry
        must NOT be in the serving config.
        """
        catalog = load_catalog()
        with pytest.raises(ValueError, match="has catalog status 'dev_only'"):
            validate_serving_config(
                catalog,
                serving_lane_ids={"omi:auto:chat-structured", "omi:auto:chat-extraction"},
                serving_artifact_ids={"route.chat_structured.2026_06_27.001"},
            )

    def test_serving_lane_marked_planned_raises(self):
        """A planned catalog entry must NOT be in the serving config."""
        catalog = load_catalog()
        with pytest.raises(ValueError, match="has catalog status 'planned'"):
            validate_serving_config(
                catalog,
                serving_lane_ids={"omi:auto:chat-structured", "omi:auto:stt-realtime"},
                serving_artifact_ids={"route.chat_structured.2026_06_27.001"},
            )

    def test_prod_ready_catalog_lane_without_serving_artifact_raises(self):
        """Every prod_ready catalog lane must have at least one serving artifact."""
        catalog = load_catalog()
        with pytest.raises(ValueError, match="prod_ready lanes"):
            validate_serving_config(
                catalog,
                serving_lane_ids=set(),  # 0 lanes
                serving_artifact_ids=set(),  # 0 artifacts
            )

    def test_empty_catalog_with_no_serving_lanes_passes(self):
        """If the catalog has no prod_ready lanes, the serving config
        can be empty (no lanes to promote yet).
        """
        catalog = LaneCatalog(lanes=[])
        validate_serving_config(
            catalog,
            serving_lane_ids=set(),
            serving_artifact_ids=set(),
        )


# ---------------------------------------------------------------------------
# load_gateway_config integration
# ---------------------------------------------------------------------------


class TestLoadGatewayConfigWithCatalog:
    def test_load_default_config_cross_validates_against_catalog(self):
        """The default config (with 1 lane: chat-structured) loads
        successfully because the catalog has chat-structured as prod_ready.
        """
        cfg = load_gateway_config(prod_mode=False)
        assert "omi:auto:chat-structured" in cfg.lanes
        assert len(cfg.route_artifacts) == 2  # active + LKG

    def test_load_with_explicit_catalog(self, tmp_path):
        """load_gateway_config accepts an explicit catalog for tests."""
        # Use a minimal config + matching catalog. We precompute the artifact
        # digest so the loader's digest check passes.
        from llm_gateway.gateway.schemas import RouteArtifact

        config_dir = tmp_path
        (config_dir / "lanes_catalog.yaml").write_text(
            yaml.safe_dump(
                {
                    "lanes": [
                        {
                            "lane_id": "omi:auto:chat-structured",
                            "description": "test",
                            "surface": "openai.chat_completions",
                            "provider": "openai",
                            "model": "gpt-4.1-mini",
                            "provider_support_status": "prod_ready",
                            "eval_suite": None,
                            "notes": "",
                            "promoted_at": "2026-07-01T00:00:00Z",
                        }
                    ]
                }
            )
        )
        (config_dir / "lanes.yaml").write_text(
            yaml.safe_dump(
                {
                    "lanes": [
                        {
                            "lane_id": "omi:auto:chat-structured",
                            "surface": "openai.chat_completions",
                            "capabilities": {
                                "text_input": True,
                                "streaming": False,
                                "structured_output": "json_schema",
                                "tools": False,
                            },
                            "objective": {"quality": 0.6, "latency": 0.2, "cost": 0.2},
                            "credential_policy": {
                                "mode": "omi_paid",
                                "allow_byok_to_omi_paid_fallback": False,
                                "fallback_eligible_failure_classes": [],
                                "never_fallback_failure_classes": [],
                            },
                            "active_route": "route.chat_structured.2026_07_01.001",
                            "last_known_good": "route.chat_structured.2026_07_01.001",
                        }
                    ]
                }
            )
        )
        # Compute the digest by validating then reading content_digest.
        artifact_body = {
            "route_artifact_id": "route.chat_structured.2026_07_01.001",
            "artifact_digest": None,
            "lane_id": "omi:auto:chat-structured",
            "surface": "openai.chat_completions",
            "primary": {"provider": "openai", "model": "gpt-4.1-mini"},
            "fallbacks": [],
            "timeouts": {"request_ms": 8000},
            "retry": {"max_attempts": 1},
            "capabilities": {
                "text_input": True,
                "streaming": False,
                "structured_output": "json_schema",
                "tools": False,
            },
            "evidence": {
                "benchmark_snapshot": "bench.test",
                "eval_report": "eval.test",
                "benchmark_source": "omi_eval",
                "dev_only": False,
            },
            "rollout": {"stage": "active", "percent": 100},
            "credential_policy": {
                "mode": "omi_paid",
                "allow_byok_to_omi_paid_fallback": False,
                "fallback_eligible_failure_classes": [],
                "never_fallback_failure_classes": [],
            },
            "fallback_policy": {"fallback_on": [], "never_fallback_on": []},
        }
        artifact_body["artifact_digest"] = RouteArtifact.model_validate(artifact_body).content_digest
        (config_dir / "route_artifacts.yaml").write_text(yaml.safe_dump({"route_artifacts": [artifact_body]}))
        (config_dir / "feature_bundles.yaml").write_text(yaml.safe_dump({"feature_bundles": []}))
        # Load with explicit catalog to bypass the auto-load
        catalog = load_catalog(config_dir / "lanes_catalog.yaml")
        cfg = load_gateway_config(config_dir, prod_mode=False, catalog=catalog)
        assert "omi:auto:chat-structured" in cfg.lanes


# ---------------------------------------------------------------------------
# CatalogEntry Pydantic validation
# ---------------------------------------------------------------------------


class TestCatalogEntry:
    def test_lane_id_must_start_with_omi_auto(self):
        with pytest.raises(ValueError, match="must start with 'omi:auto:'"):
            CatalogEntry(
                lane_id="not-omi",
                description="x",
                surface="x",
                provider="x",
                model="x",
                provider_support_status=ProviderSupportStatus.PLANNED,
            )

    def test_lane_id_must_have_capability(self):
        with pytest.raises(ValueError, match="non-empty capability"):
            CatalogEntry(
                lane_id="omi:auto:",
                description="x",
                surface="x",
                provider="x",
                model="x",
                provider_support_status=ProviderSupportStatus.PLANNED,
            )

    def test_prod_ready_requires_promoted_at(self):
        with pytest.raises(ValueError, match="promoted_at must be set"):
            CatalogEntry(
                lane_id="omi:auto:test",
                description="x",
                surface="openai.chat_completions",
                provider="openai",
                model="gpt-4.1-mini",
                provider_support_status=ProviderSupportStatus.PROD_READY,
                promoted_at=None,
            )

    def test_dev_only_rejects_promoted_at(self):
        with pytest.raises(ValueError, match="must NOT be set"):
            CatalogEntry(
                lane_id="omi:auto:test",
                description="x",
                surface="openai.chat_completions",
                provider="openai",
                model="gpt-4.1-mini",
                provider_support_status=ProviderSupportStatus.DEV_ONLY,
                promoted_at="2026-07-01T00:00:00Z",
            )
