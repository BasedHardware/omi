from __future__ import annotations

from functools import lru_cache

from llm_gateway.gateway.config_loader import GatewayConfig, load_gateway_config
from llm_gateway.gateway.executor import ProviderRegistry


@lru_cache(maxsize=1)
def get_gateway_config() -> GatewayConfig:
    return load_gateway_config(prod_mode=True)


def get_provider_registry() -> ProviderRegistry:
    return ProviderRegistry()
