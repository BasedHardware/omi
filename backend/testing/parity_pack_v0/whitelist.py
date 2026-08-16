"""Dev-only, explicit principal gate for future capture hooks."""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class CaptureWhitelist:
    enabled: bool
    environment: str
    principal_ids: frozenset[str]

    @classmethod
    def from_environ(cls, environ: dict[str, str] | None = None) -> "CaptureWhitelist":
        env = os.environ if environ is None else environ
        principals = frozenset(
            item.strip() for item in env.get("OMI_PARITY_PACK_ALLOWED_PRINCIPALS", "").split(",") if item.strip()
        )
        return cls(
            enabled=env.get("OMI_PARITY_PACK_CAPTURE", "").strip().lower() in {"1", "true", "yes"},
            environment=env.get("OMI_ENV_STAGE", "").strip().lower(),
            principal_ids=principals,
        )

    def allows(self, principal_id: str | None) -> bool:
        """Default deny: only explicit dev enablement plus an exact allow-list hit."""
        return bool(self.enabled and self.environment == "dev" and principal_id and principal_id in self.principal_ids)
