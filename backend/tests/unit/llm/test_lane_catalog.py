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
        assert len(catalog.lanes) == 17

    def test_catalog_entries_have_required_fields(self):
        catalog = load_catalog()
        for entry in catalog.lanes:
            assert entry.lane_id.startswith("omi:auto:")
            assert entry.provider in {"openai", "anthropic", "tbd"}
            assert entry.surface in {"openai.chat_completions", "anthropic.messages", "unknown"}

    def test_catalog_has_two_prod_ready_lanes(self):
        catalog = load_catalog()
        prod_ready = catalog.prod_ready_lane_ids()
        assert prod_ready == {
            "omi:auto:chat-structured",
            "omi:auto:public-shared-conversation-chat",
        }

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
                            "eval_suite": "eval.test",
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
    """Cross-validation tests. R0.5 review fix: signature changed to take
    the full GatewayConfig so the check is association-based (per prod_ready
    lane), not count-based. The previous count-only check missed the
    'serving config has artifacts for non-prod_ready lanes but not for
    prod_ready' case.
    """

    def _minimal_serving_config(self, lane_id: str = "omi:auto:chat-structured"):
        """Build a minimal serving config with one lane and one artifact."""
        from llm_gateway.gateway.schemas import (
            Capabilities,
            CredentialPolicy,
            Evidence,
            FallbackPolicy,
            LaneConfig,
            Objective,
            ProviderRef,
            RetryPolicy,
            RolloutPolicy,
            RouteArtifact,
            StructuredOutputMode,
            Surface,
            TimeoutPolicy,
        )

        lane = LaneConfig(
            lane_id=lane_id,
            surface=Surface.OPENAI_CHAT_COMPLETIONS,
            capabilities=Capabilities(
                text_input=True,
                streaming=False,
                structured_output=StructuredOutputMode.NONE,
                tools=False,
            ),
            objective=Objective(quality=0.6, latency=0.2, cost=0.2),
            credential_policy=CredentialPolicy(
                mode="omi_paid",
                allow_byok_to_omi_paid_fallback=False,
                fallback_eligible_failure_classes=[],
                never_fallback_failure_classes=[],
            ),
            active_route=f"route.test.{lane_id}.001",
            last_known_good=f"route.test.{lane_id}.001",
        )
        art_id = f"route.test.{lane_id.split(':')[-1]}.001"
        artifact = RouteArtifact(
            route_artifact_id=art_id,
            artifact_digest="sha256:" + "0" * 64,
            lane_id=lane_id,
            surface=Surface.OPENAI_CHAT_COMPLETIONS,
            primary=ProviderRef(provider="openai", model="gpt-4.1-mini"),
            fallbacks=[],
            timeouts=TimeoutPolicy(request_ms=8000),
            retry=RetryPolicy(max_attempts=1),
            capabilities=Capabilities(
                text_input=True,
                streaming=False,
                structured_output=StructuredOutputMode.NONE,
                tools=False,
            ),
            evidence=Evidence(
                benchmark_snapshot="bench.test",
                eval_report="eval.test",
                benchmark_source="omi_eval",
                dev_only=False,
            ),
            rollout=RolloutPolicy(stage="shadow", percent=0),
            credential_policy=CredentialPolicy(
                mode="omi_paid",
                allow_byok_to_omi_paid_fallback=False,
                fallback_eligible_failure_classes=[],
                never_fallback_failure_classes=[],
            ),
            fallback_policy=FallbackPolicy(
                fallback_on=[],
                never_fallback_on=[],
            ),
        )
        return GatewayConfig(
            lanes={lane_id: lane},
            route_artifacts={art_id: artifact},
            feature_bundles={},
        )

    def test_valid_serving_config_passes(self):
        catalog = load_catalog()
        validate_serving_config(catalog, load_gateway_config(prod_mode=False))

    def test_serving_lane_surface_must_match_catalog(self):
        catalog = load_catalog()
        entry = catalog.get("omi:auto:chat-structured")
        assert entry is not None
        catalog = LaneCatalog(
            lanes=[
                entry.model_copy(update={"surface": Surface.ANTHROPIC_MESSAGES}) if lane == entry else lane
                for lane in catalog.lanes
            ]
        )
        with pytest.raises(ConfigValidationError, match="surface .* does not match catalog"):
            validate_serving_config(catalog, load_gateway_config(prod_mode=False))

    def test_serving_lane_active_provider_and_model_must_match_catalog(self):
        catalog = load_catalog()
        entry = catalog.get("omi:auto:chat-structured")
        assert entry is not None
        catalog = LaneCatalog(
            lanes=[
                entry.model_copy(update={"model": "gpt-4.1-mini"}) if lane == entry else lane for lane in catalog.lanes
            ]
        )
        with pytest.raises(ConfigValidationError, match="does not match catalog provider/model"):
            validate_serving_config(catalog, load_gateway_config(prod_mode=False))

    def test_serving_lane_not_in_catalog_is_rejected(self):
        catalog = load_catalog()
        cfg = self._minimal_serving_config(lane_id="omi:auto:not-in-catalog")
        # Start from the complete real config so all prod_ready catalog lanes
        # are present before adding the uncatalogued lane.
        base = load_gateway_config(prod_mode=False)
        base.lanes["omi:auto:not-in-catalog"] = cfg.lanes["omi:auto:not-in-catalog"]
        base.route_artifacts.update(cfg.route_artifacts)
        with pytest.raises(ConfigValidationError, match="is not catalogued"):
            validate_serving_config(catalog, base)

    def test_serving_lane_marked_dev_only_is_rejected(self):
        catalog = load_catalog()
        base = load_gateway_config(prod_mode=False)
        extra = self._minimal_serving_config(lane_id="omi:auto:memory-graph")
        base.lanes["omi:auto:memory-graph"] = extra.lanes["omi:auto:memory-graph"]
        base.route_artifacts.update(extra.route_artifacts)
        with pytest.raises(ConfigValidationError, match="only prod_ready lanes may serve"):
            validate_serving_config(catalog, base)

    def test_serving_lane_marked_planned_is_rejected(self):
        catalog = load_catalog()
        base = load_gateway_config(prod_mode=False)
        extra = self._minimal_serving_config(lane_id="omi:auto:stt-realtime")
        base.lanes["omi:auto:stt-realtime"] = extra.lanes["omi:auto:stt-realtime"]
        base.route_artifacts.update(extra.route_artifacts)
        with pytest.raises(ConfigValidationError, match="only prod_ready lanes may serve"):
            validate_serving_config(catalog, base)

    def test_model_config_generated_lanes_keep_serving_without_a_catalog_entry(self):
        """`utils.llm.model_config` owns the feature lanes it generates.

        Gating them on the catalog would stop serving every feature the model
        config routes through the gateway, so they are exempt from the catalog
        cross-check even when uncatalogued or catalogued as dev_only.
        """
        catalog = load_catalog()
        cfg = load_gateway_config(prod_mode=False)

        assert "omi:auto:chat-agent" in cfg.generated_lane_ids
        assert catalog.get("omi:auto:chat-agent") is None
        assert "omi:auto:chat-agent" in cfg.lanes
        # chat-extraction is catalogued dev_only but generated from model_config.
        assert "omi:auto:chat-extraction" in cfg.generated_lane_ids
        assert "omi:auto:chat-extraction" in cfg.lanes

        validate_serving_config(catalog, cfg)

    def test_prod_ready_lane_missing_from_serving_config_raises(self):
        """R0.5 review fix F2: the count-only check missed the case where
        a prod_ready catalog lane is entirely missing from the serving
        config. This test pins the fix.

        We build a serving config with 0 lanes and 0 artifacts (no
        dev_only triggers; the dev_only check sees an empty serving lane
        set and passes). The prod_ready check then catches the missing
        chat-structured.
        """
        catalog = load_catalog()
        from llm_gateway.gateway.config_loader import ConfigValidationError

        empty_cfg = GatewayConfig(lanes={}, route_artifacts={}, feature_bundles={})
        with pytest.raises(ConfigValidationError, match="no serving config entry"):
            validate_serving_config(catalog, empty_cfg)

    def test_prod_ready_lane_with_artifact_for_other_lane_raises(self):
        """R0.5 review fix F2: the count-only check missed the case where
        the serving config has an artifact for some other lane but NOT
        for the prod_ready one.

        Build a serving config that has a lane + artifact for the
        prod_ready chat-structured. The artifact's lane_id is
        chat-extraction (dev_only), so chat-structured has no artifact
        of its own. The count check would have passed this.
        """
        default_catalog = load_catalog()
        chat_structured = default_catalog.get("omi:auto:chat-structured")
        assert chat_structured is not None
        catalog = LaneCatalog(lanes=[chat_structured])
        from llm_gateway.gateway.config_loader import ConfigValidationError
        from llm_gateway.gateway.schemas import (
            Capabilities,
            CredentialPolicy,
            Evidence,
            FallbackPolicy,
            LaneConfig,
            Objective,
            ProviderRef,
            RetryPolicy,
            RolloutPolicy,
            RouteArtifact,
            StructuredOutputMode,
            Surface,
            TimeoutPolicy,
        )

        # Lane: chat-structured (prod_ready in the catalog)
        lane = LaneConfig(
            lane_id="omi:auto:chat-structured",
            surface=Surface.OPENAI_CHAT_COMPLETIONS,
            capabilities=Capabilities(
                text_input=True,
                streaming=False,
                structured_output=StructuredOutputMode.NONE,
                tools=False,
            ),
            objective=Objective(quality=0.6, latency=0.2, cost=0.2),
            credential_policy=CredentialPolicy(
                mode="omi_paid",
                allow_byok_to_omi_paid_fallback=False,
                fallback_eligible_failure_classes=[],
                never_fallback_failure_classes=[],
            ),
            active_route="route.test.chat-extraction.001",
            last_known_good="route.test.chat-extraction.001",
        )
        # Artifact: lane_id is chat-extraction (NOT chat-structured)
        # So chat-structured has 1 lane but 0 artifacts of its own.
        artifact = RouteArtifact(
            route_artifact_id="route.test.chat-extraction.001",
            artifact_digest="sha256:" + "0" * 64,
            lane_id="omi:auto:chat-extraction",
            surface=Surface.OPENAI_CHAT_COMPLETIONS,
            primary=ProviderRef(provider="openai", model="gpt-4.1-mini"),
            fallbacks=[],
            timeouts=TimeoutPolicy(request_ms=8000),
            retry=RetryPolicy(max_attempts=1),
            capabilities=Capabilities(
                text_input=True,
                streaming=False,
                structured_output=StructuredOutputMode.NONE,
                tools=False,
            ),
            evidence=Evidence(
                benchmark_snapshot="bench.test",
                eval_report="eval.test",
                benchmark_source="omi_eval",
                dev_only=False,
            ),
            rollout=RolloutPolicy(stage="shadow", percent=0),
            credential_policy=CredentialPolicy(
                mode="omi_paid",
                allow_byok_to_omi_paid_fallback=False,
                fallback_eligible_failure_classes=[],
                never_fallback_failure_classes=[],
            ),
            fallback_policy=FallbackPolicy(
                fallback_on=[],
                never_fallback_on=[],
            ),
        )
        cfg = GatewayConfig(
            lanes={"omi:auto:chat-structured": lane},
            route_artifacts={"route.test.chat-extraction.001": artifact},
            feature_bundles={},
        )
        with pytest.raises(ConfigValidationError, match="no serving route artifact"):
            validate_serving_config(catalog, cfg)

    def test_empty_catalog_with_no_serving_lanes_passes(self):
        """If the catalog has no prod_ready lanes, the serving config
        can be empty (no lanes to promote yet).
        """
        catalog = LaneCatalog(lanes=[])
        cfg = GatewayConfig(lanes={}, route_artifacts={}, feature_bundles={})
        validate_serving_config(catalog, cfg)


# ---------------------------------------------------------------------------
# load_gateway_config integration
# ---------------------------------------------------------------------------


class TestLoadGatewayConfigWithCatalog:
    def test_load_default_config_cross_validates_against_catalog(self):
        """The default config includes every prod-ready catalog lane."""
        cfg = load_gateway_config(prod_mode=False)
        assert "omi:auto:chat-structured" in cfg.lanes
        assert "omi:auto:public-shared-conversation-chat" in cfg.lanes
        assert len(cfg.route_artifacts) >= 2  # active + LKG (+ generated feature routes)

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
                            "eval_suite": "eval.test",
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
# Resolver derivation (F7: pin the post-R0.5 invariant)
# ---------------------------------------------------------------------------


class TestResolverDerivation:
    def test_resolver_supported_lane_ids_match_prod_ready_catalog_lanes(self):
        """The resolver allowlist is derived from the current prod-ready catalog."""
        from llm_gateway.gateway.resolver import get_supported_auto_lane_ids

        assert get_supported_auto_lane_ids() == {
            "omi:auto:chat-structured",
            "omi:auto:public-shared-conversation-chat",
        }

    def test_resolver_supported_lane_ids_excludes_placeholder_lanes(self):
        """Per David: 'No prod-loadable placeholder route artifacts'.
        The 3 R0 placeholders must NOT be in the allowlist.
        """
        from llm_gateway.gateway.resolver import get_supported_auto_lane_ids

        supported_lane_ids = get_supported_auto_lane_ids()
        assert "omi:auto:stt-realtime" not in supported_lane_ids
        assert "omi:auto:transcription" not in supported_lane_ids
        assert "omi:auto:screenshot-embedding" not in supported_lane_ids

    def test_resolver_supported_lane_ids_excludes_dev_only_lanes(self):
        """Per David: 'If a lane doesn't have the real surface / provider
        support / eval yet, keep it catalog-only'. The 12 R0 dev_only
        lanes must NOT be in the allowlist.
        """
        from llm_gateway.gateway.resolver import get_supported_auto_lane_ids

        supported_lane_ids = get_supported_auto_lane_ids()
        for dev_only_lane in [
            "omi:auto:chat-extraction",
            "omi:auto:daily-summary",
            "omi:auto:realtime-ptt",  # this one is special: anthropic
            "omi:auto:persona-chat",
        ]:
            assert (
                dev_only_lane not in supported_lane_ids
            ), f"{dev_only_lane} is dev_only in the catalog but in the allowlist"


# ---------------------------------------------------------------------------
# CatalogEntry Pydantic validation
# ---------------------------------------------------------------------------


class TestCatalogEntry:
    def test_lane_id_must_start_with_omi_auto(self):
        # Pydantic's LaneId regex (reused from schemas.py) rejects non-omi prefixes.
        with pytest.raises(ValueError, match="should match pattern"):
            CatalogEntry(
                lane_id="not-omi",
                description="x",
                surface="x",
                provider="x",
                model="x",
                provider_support_status=ProviderSupportStatus.PLANNED,
            )

    def test_lane_id_must_have_capability(self):
        # Pydantic's LaneId regex rejects empty capability (omi:auto: doesn't match).
        with pytest.raises(ValueError, match="should match pattern"):
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
                eval_suite="eval.test",
                promoted_at=None,
            )

    def test_prod_ready_requires_eval_suite(self):
        with pytest.raises(ValueError, match="eval_suite must be set"):
            CatalogEntry(
                lane_id="omi:auto:test",
                description="x",
                surface="openai.chat_completions",
                provider="openai",
                model="gpt-4.1-mini",
                provider_support_status=ProviderSupportStatus.PROD_READY,
                promoted_at="2026-07-01T00:00:00Z",
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
