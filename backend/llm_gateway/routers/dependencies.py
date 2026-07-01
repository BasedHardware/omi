from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from llm_gateway.gateway.config_loader import (
    DEFAULT_CONFIG_DIR,
    GatewayConfig,
    load_gateway_config,
)
from llm_gateway.gateway.config_reload import GatewayConfigReloader
from llm_gateway.gateway.executor import ProviderRegistry
from llm_gateway.gateway.providers import OpenAICompatibleChatCompletionProvider
from llm_gateway.gateway.resolver import SUPPORTED_AUTO_LANE_IDS

logger = logging.getLogger(__name__)


# Singleton reloader. Reads from the gateway's default config dir at module
# import time; replaces the previous @lru_cache(maxsize=1) pattern so the
# gateway picks up YAML changes on the next request after merge (R5b).
# The reloader is process-wide (one per gateway process); for tests, create
# a local GatewayConfigReloader pointing at a tmp_path config dir.
_config_reloader = GatewayConfigReloader(Path(DEFAULT_CONFIG_DIR))


async def get_gateway_config() -> GatewayConfig:
    """Return the current gateway config, hot-reloading on YAML mtime change.

    R5b: replaces the previous `@lru_cache(maxsize=1)` pattern (which only
    loaded once at startup) with the mtime-watched `GatewayConfigReloader`.
    This means nightly rotation PRs (R4) take effect on the next request
    after merge — no pod restart required.

    prod_mode=None means the OMI_LLM_GATEWAY_PROD env var decides. In
    dev/staging (env unset) all configs load; in prod (env set) configs
    with dev_only artifacts are rejected.
    """
    return await _config_reloader.get()


def reset_gateway_config_reloader() -> None:
    """Test helper + admin path: invalidate the reloader so the next get()
    reloads from disk (bypasses mtime check)."""
    _config_reloader.invalidate()


@lru_cache(maxsize=1)
def get_provider_registry() -> ProviderRegistry:
    return ProviderRegistry({'openai': OpenAICompatibleChatCompletionProvider()})


async def close_provider_registry() -> None:
    await get_provider_registry().aclose()
    get_provider_registry.cache_clear()
