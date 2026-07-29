"""Lane catalog — the registry of all lanes (serving + planned).

Per David's 2026-07-02 feedback:
  - "I think we should separate lane catalog from serving config"
  - "Catalog is where we can list the future lanes / taxonomy we want"
  - "Serving config should only include lanes the gateway can actually execute today"
  - "No prod-loadable placeholder route artifacts"
  - "If a lane doesn't have the real surface / provider support / eval yet,
    keep it catalog-only"

This module defines the catalog data model (Pydantic), the loader
(`load_catalog`), and the cross-validation function
(`validate_serving_config`) that the gateway uses at startup to
enforce the split.

Promotion path: dev_only → internal eval gate → promotion PR →
prod_ready (in this catalog) → serving artifact added (in
route_artifacts.yaml) → human review + merge. (R4's cron proposes
the PR; humans merge.)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import yaml
from pydantic import BaseModel, ConfigDict, field_validator

from llm_gateway.gateway.schemas import LaneId

if TYPE_CHECKING:
    from llm_gateway.gateway.config_loader import GatewayConfig


# Default catalog location (relative to this file)
_PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_CATALOG_DIR = _PACKAGE_DIR.parent / "config"
DEFAULT_CATALOG_PATH = DEFAULT_CATALOG_DIR / "lanes_catalog.yaml"


class ProviderSupportStatus(str, Enum):
    """Lifecycle of a lane's provider support.

    - planned: lane is in the catalog only; no real surface, provider, or
      eval. Cannot be in the serving config.
    - dev_only: lane has a real surface and provider, but no internal
      eval yet. Cannot be in the serving config (per David's feedback:
      internal eval is required for promotion).
    - prod_ready: lane is fully supported (surface, provider, eval). Can
      be in the serving config.
    """

    PLANNED = "planned"
    DEV_ONLY = "dev_only"
    PROD_READY = "prod_ready"


class CatalogEntry(BaseModel):
    """One entry in the lane catalog.

    See `lanes_catalog.yaml` for the field semantics.
    """

    model_config = ConfigDict(extra="forbid")

    lane_id: LaneId
    description: str
    surface: str
    provider: str
    model: str
    provider_support_status: ProviderSupportStatus
    eval_suite: Optional[str] = None
    notes: str = ""
    promoted_at: Optional[datetime] = None

    @field_validator("promoted_at")
    @classmethod
    def _validate_promoted_at_status(cls, v: Optional[datetime], info) -> Optional[datetime]:
        # Cross-check: promoted_at should be set when status is prod_ready
        status = info.data.get("provider_support_status")
        if status == ProviderSupportStatus.PROD_READY and v is None:
            raise ValueError("promoted_at must be set when provider_support_status is prod_ready")
        if status != ProviderSupportStatus.PROD_READY and v is not None:
            raise ValueError(f"promoted_at must NOT be set when status is {status.value}")
        return v


class LaneCatalog(BaseModel):
    """The full lane catalog — all lanes (serving + planned)."""

    model_config = ConfigDict(extra="forbid")

    lanes: list[CatalogEntry]

    def get(self, lane_id: str) -> Optional[CatalogEntry]:
        """Look up a lane by id. Returns None if not present."""
        for entry in self.lanes:
            if entry.lane_id == lane_id:
                return entry
        return None

    def prod_ready_lane_ids(self) -> set[str]:
        """Return the set of lane_ids with prod_ready status."""
        return {e.lane_id for e in self.lanes if e.provider_support_status == ProviderSupportStatus.PROD_READY}


def load_catalog(catalog_path: Path | None = None) -> LaneCatalog:
    """Load the lane catalog from `catalog_path` (or the default).

    Raises ValueError if the file doesn't exist or doesn't parse.
    """
    path = Path(catalog_path) if catalog_path is not None else DEFAULT_CATALOG_PATH
    if not path.exists():
        raise FileNotFoundError(f"lanes catalog not found at {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "lanes" not in data:
        # Lazy import to avoid a circular dependency: config_loader imports
        # from this module (for validate_serving_config), so we can't
        # import config_loader at module-load time.
        from llm_gateway.gateway.config_loader import ConfigValidationError

        raise ConfigValidationError(f"{path} must contain a top-level 'lanes' key (got {type(data).__name__})")
    return LaneCatalog.model_validate(data)


def validate_serving_config(
    catalog: LaneCatalog,
    serving_cfg: "GatewayConfig",
) -> None:
    """Cross-check: every serving lane must be in the catalog with prod_ready
    status. Every prod_ready catalog entry must have at least one serving
    artifact (associated by lane_id, not just by total count).

    Raises ConfigValidationError on any mismatch (consistent with the rest
    of config_loader.py; not a plain ValueError). The mismatch detail
    names the lane so the operator can fix the catalog or the serving
    config.
    """
    # Lazy import to avoid a circular dependency: config_loader imports
    # from this module (for validate_serving_config), so we can't
    # import config_loader at module-load time.
    from llm_gateway.gateway.config_loader import ConfigValidationError

    prod_ready = catalog.prod_ready_lane_ids()
    serving_lane_ids = set(serving_cfg.lanes.keys())
    serving_lane_to_artifacts: dict[str, list[str]] = {}
    for art_id, art in serving_cfg.route_artifacts.items():
        serving_lane_to_artifacts.setdefault(art.lane_id, []).append(art_id)

    # Generated feature routes may not be catalogued yet. A catalogued lane,
    # however, must be promoted before it can enter the serving config.
    for lane_id in sorted(serving_lane_ids):
        entry = catalog.get(lane_id)
        if entry is not None and entry.provider_support_status != ProviderSupportStatus.PROD_READY:
            raise ConfigValidationError(
                f"serving lane {lane_id!r} is catalogued as "
                f"{entry.provider_support_status.value}; only prod_ready lanes may serve"
            )

    # Every prod_ready catalog entry must have at least one serving
    # artifact (ASSOCIATED by lane_id, not just by count). This catches the
    # case where the serving config has artifacts for some non-prod_ready
    # lanes but not for the prod_ready ones (the count-only check missed
    # this; see R0.5 review finding F2).
    for prod_ready_lane_id in sorted(prod_ready):
        if prod_ready_lane_id not in serving_lane_ids:
            raise ConfigValidationError(
                f"prod_ready catalog lane {prod_ready_lane_id!r} has no "
                f"serving config entry. Add it to lanes.yaml + route_artifacts.yaml."
            )
        if not serving_lane_to_artifacts.get(prod_ready_lane_id):
            raise ConfigValidationError(
                f"prod_ready catalog lane {prod_ready_lane_id!r} has no serving "
                f"route artifact. Add an artifact to route_artifacts.yaml with "
                f"lane_id={prod_ready_lane_id!r}."
            )
