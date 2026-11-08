"""Environment configuration. See .env.example for documentation of each value."""

from __future__ import annotations

from decimal import Decimal
from functools import cached_property
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# CAIP-2 identifiers used by x402 v2.
NETWORKS = {"base-sepolia": "eip155:84532", "base": "eip155:8453"}


def _split(value: str) -> frozenset[str]:
    return frozenset(item.strip() for item in value.split(",") if item.strip())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Every optional secret below fails closed: when unset, the feature it guards is off.
    wallet_private_key: SecretStr | None = None
    webhook_secret: SecretStr | None = None
    allowed_uids: str = ""
    allowed_domains: str = ""

    network: Literal["base-sepolia", "base"] = "base-sepolia"
    max_per_payment_usd: Decimal = Decimal("5")
    daily_limit_usd: Decimal = Decimal("20")
    auto_approve_usd: Decimal = Decimal("0")
    pending_ttl_seconds: int = 300

    database_path: str = "data/spraay.db"
    public_base_url: str = "https://YOUR_ENDPOINT"

    @cached_property
    def caip_network(self) -> str:
        return NETWORKS[self.network]

    @cached_property
    def allowed_uid_set(self) -> frozenset[str]:
        return _split(self.allowed_uids)

    @cached_property
    def allowed_domain_set(self) -> frozenset[str]:
        return frozenset(domain.lower() for domain in _split(self.allowed_domains))
