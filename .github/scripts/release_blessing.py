#!/usr/bin/env python3
"""Shared release blessing metadata and dependency helpers."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from desktop_release_metadata import fail


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = ROOT / ".github/release-blessing-surfaces.json"
TRUE_VALUES = {"true", "1", "yes"}


@dataclass(frozen=True)
class BlessingSurface:
    id: str
    display_name: str
    depends_on: tuple[str, ...]
    promotion_workflows: tuple[str, ...]


@dataclass(frozen=True)
class SurfaceBlessing:
    surface_id: str
    blessed: bool
    sha: str
    blessed_at: str
    tier: str
    evidence: str


def load_surface_registry(path: Path = DEFAULT_REGISTRY_PATH) -> dict[str, BlessingSurface]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_surfaces = payload.get("surfaces")
    if not isinstance(raw_surfaces, dict) or not raw_surfaces:
        fail(f"{path} must contain a non-empty surfaces object")

    surfaces: dict[str, BlessingSurface] = {}
    for surface_id, config in raw_surfaces.items():
        if not isinstance(config, dict):
            fail(f"surface {surface_id!r} must be an object")
        depends_on = tuple(config.get("depends_on") or ())
        promotion_workflows = tuple(config.get("promotion_workflows") or ())
        surfaces[surface_id] = BlessingSurface(
            id=surface_id,
            display_name=str(config.get("display_name") or surface_id),
            depends_on=depends_on,
            promotion_workflows=promotion_workflows,
        )

    for surface in surfaces.values():
        for dependency in surface.depends_on:
            if dependency not in surfaces:
                fail(f"surface {surface.id!r} depends on unknown surface {dependency!r}")
            if dependency == surface.id:
                fail(f"surface {surface.id!r} cannot depend on itself")

    return surfaces


def namespaced_key(surface_id: str, field: str | None = None) -> str:
    if field is None or field == "blessed":
        return f"blessed.{surface_id}"
    return f"blessed.{surface_id}.{field}"


def parse_bool(value: str) -> bool:
    return value.strip().lower() in TRUE_VALUES


def surface_blessing_from_metadata(
    metadata: dict[str, str],
    surface_id: str,
    *,
    allow_legacy_desktop: bool = False,
) -> SurfaceBlessing:
    if (
        allow_legacy_desktop
        and surface_id == "desktop-macos"
        and namespaced_key(surface_id) not in metadata
        and "blessed" in metadata
    ):
        return SurfaceBlessing(
            surface_id=surface_id,
            blessed=parse_bool(metadata.get("blessed", "")),
            sha=metadata.get("blessedSha", "").strip(),
            blessed_at=metadata.get("blessedAt", "").strip(),
            tier=metadata.get("blessedTier", "").strip(),
            evidence=metadata.get("blessedEvidence", "").strip(),
        )

    return SurfaceBlessing(
        surface_id=surface_id,
        blessed=parse_bool(metadata.get(namespaced_key(surface_id), "")),
        sha=metadata.get(namespaced_key(surface_id, "sha"), "").strip(),
        blessed_at=metadata.get(namespaced_key(surface_id, "at"), "").strip(),
        tier=metadata.get(namespaced_key(surface_id, "tier"), "").strip(),
        evidence=metadata.get(namespaced_key(surface_id, "evidence"), "").strip(),
    )


def require_surface_blessed(blessing: SurfaceBlessing) -> None:
    if not blessing.blessed:
        fail(f"{blessing.surface_id} must be blessed before prod promotion")
    if not blessing.sha:
        fail(f"{blessing.surface_id} blessing is missing sha metadata")
    if not blessing.blessed_at:
        fail(f"{blessing.surface_id} blessing is missing at metadata")


def dependency_closure(surface_id: str, surfaces: dict[str, BlessingSurface]) -> list[str]:
    if surface_id not in surfaces:
        fail(f"unknown blessing surface: {surface_id}")

    ordered: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(current: str) -> None:
        if current in visited:
            return
        if current in visiting:
            fail(f"cycle detected in blessing surface dependencies at {current}")
        visiting.add(current)
        for dependency in surfaces[current].depends_on:
            visit(dependency)
        visiting.remove(current)
        visited.add(current)
        ordered.append(current)

    visit(surface_id)
    return ordered


def require_blessed_closure(surface_id: str, blessings: dict[str, SurfaceBlessing]) -> None:
    surfaces = load_surface_registry()
    for required_surface in dependency_closure(surface_id, surfaces):
        blessing = blessings.get(required_surface)
        if blessing is None:
            fail(f"{surface_id} promotion is missing blessing data for {required_surface}")
        if blessing.surface_id != required_surface:
            fail(f"{surface_id} promotion has {blessing.surface_id} blessing data for {required_surface}")
        require_surface_blessed(blessing)
