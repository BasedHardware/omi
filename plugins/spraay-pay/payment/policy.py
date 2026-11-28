"""Spending limits and approval rules. Amounts are integer micro-USDC throughout."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from urllib.parse import urlsplit

from config import Settings

MICRO = Decimal(1_000_000)


def to_micro(amount: Decimal) -> int:
    return int(amount * MICRO)


def format_usd(micro: int) -> str:
    whole, fraction = f"{Decimal(micro) / MICRO:.6f}".rstrip("0").split(".")
    return f"${whole}.{fraction.ljust(2, '0')}"


class Source(str, Enum):
    VOICE = "voice"
    CHAT = "chat"


class Action(str, Enum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str = ""


class SpendingPolicy:
    def __init__(self, settings: Settings):
        self.max_per_payment = to_micro(settings.max_per_payment_usd)
        self.daily_limit = to_micro(settings.daily_limit_usd)
        self.auto_approve = to_micro(settings.auto_approve_usd)
        self.allowed_domains = settings.allowed_domain_set

    def _domain_allowed(self, host: str) -> bool:
        if not self.allowed_domains:
            return True
        return any(host == d or host.endswith(f".{d}") for d in self.allowed_domains)

    def evaluate(
        self,
        amount_micro: int,
        target_url: str,
        spent_today_micro: int,
        source: Source,
        confirmed: bool = False,
    ) -> Decision:
        parts = urlsplit(target_url)
        host = (parts.hostname or "").lower()
        if amount_micro <= 0:
            return Decision(Action.DENY, "The amount must be greater than zero.")
        if parts.scheme != "https" or not host:
            return Decision(Action.DENY, "Payments are only sent to https:// services.")
        if not self._domain_allowed(host):
            return Decision(Action.DENY, f"{host} is not on the allowed services list.")
        if amount_micro > self.max_per_payment:
            return Decision(
                Action.DENY,
                f"{format_usd(amount_micro)} is over the {format_usd(self.max_per_payment)} per-payment limit.",
            )
        if spent_today_micro + amount_micro > self.daily_limit:
            remaining = max(self.daily_limit - spent_today_micro, 0)
            return Decision(
                Action.DENY,
                f"That would exceed the daily limit. {format_usd(remaining)} remains today.",
            )
        if confirmed:
            return Decision(Action.ALLOW)
        # Speech can come from anyone in the room, so voice never pays without confirmation.
        if source is Source.VOICE or amount_micro > self.auto_approve:
            return Decision(Action.CONFIRM)
        return Decision(Action.ALLOW)
