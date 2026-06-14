"""Source routing scaffold for memory ingestion.

V8-3 introduces explicit route provenance without changing behavior. Future
source-specific tickets can make effective_source_type or route implementation
selectable here, but this scaffold is intentionally passthrough.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from utils.memory_ingestion.models import SourceDescriptor

SOURCE_ROUTER_VERSION = "source_router.v1"


@dataclass(frozen=True)
class SourceRouteDecision:
    route_version: str
    declared_source_type: str
    effective_source_type: str
    reason: str
    metadata: dict[str, Any]

    def model_dump(self) -> dict[str, Any]:
        return {
            "route_version": self.route_version,
            "declared_source_type": self.declared_source_type,
            "effective_source_type": self.effective_source_type,
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


def route_source(source: SourceDescriptor, *, route_family: str = "current") -> SourceRouteDecision:
    """Return a route decision for V8 source routing.

    V8-4 freezes the current strict chat behavior under route_family='v7a'.
    Effective source type remains unchanged; future tickets may add behavior-changing
    voice/OCR route families.
    """
    metadata = source.metadata or {}
    return SourceRouteDecision(
        route_version=SOURCE_ROUTER_VERSION,
        declared_source_type=source.source_type,
        effective_source_type=source.source_type,
        reason="declared_source_type_passthrough",
        metadata={
            "source_id": source.source_id,
            "route_family": route_family,
            "benchmark_source_type": metadata.get("benchmark_source_type"),
            "benchmark_original_source_type": metadata.get("benchmark_original_source_type"),
            "benchmark_example_id": metadata.get("benchmark_example_id"),
        },
    )
