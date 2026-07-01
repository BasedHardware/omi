from __future__ import annotations

import pytest

from llm_gateway.routers.dependencies import (
    _resolve_prod_mode,
    close_provider_registry,
    get_provider_registry,
)


@pytest.mark.asyncio
async def test_provider_registry_is_cached_and_closed():
    get_provider_registry.cache_clear()
    first = get_provider_registry()
    second = get_provider_registry()

    assert first is second

    await close_provider_registry()

    assert get_provider_registry() is not first
    await close_provider_registry()


# ---------------------------------------------------------------------------
# _resolve_prod_mode: fail-safe default (per cubic-dev-ai review on PR #8746)
# ---------------------------------------------------------------------------


class TestResolveProdMode:
    """Production-by-default: a missing env var is treated as production.

    Dev environments must explicitly set OMI_LLM_GATEWAY_PROD to a dev-mode
    value ('0', 'false', 'no', 'dev', 'development') to opt out of
    production validation. A misconfigured deployment therefore rejects
    dev-only artifacts rather than silently accepting them.
    """

    def test_missing_env_var_defaults_to_production(self, monkeypatch):
        monkeypatch.delenv("OMI_LLM_GATEWAY_PROD", raising=False)
        assert _resolve_prod_mode() is True

    def test_empty_env_var_defaults_to_production(self, monkeypatch):
        monkeypatch.setenv("OMI_LLM_GATEWAY_PROD", "")
        assert _resolve_prod_mode() is True

    def test_unrecognized_env_var_defaults_to_production(self, monkeypatch):
        # Any value not in the dev-mode set is treated as production.
        monkeypatch.setenv("OMI_LLM_GATEWAY_PROD", "yes-please")
        assert _resolve_prod_mode() is True

    @pytest.mark.parametrize("dev_value", ["0", "false", "no", "dev", "development"])
    def test_dev_mode_values(self, monkeypatch, dev_value):
        monkeypatch.setenv("OMI_LLM_GATEWAY_PROD", dev_value)
        assert _resolve_prod_mode() is False

    @pytest.mark.parametrize(
        "prod_value",
        ["1", "true", "yes", "production", "PROD", "  1  ", "True"],
    )
    def test_prod_mode_values(self, monkeypatch, prod_value):
        # Any value not in the dev-mode set is production.
        monkeypatch.setenv("OMI_LLM_GATEWAY_PROD", prod_value)
        assert _resolve_prod_mode() is True
