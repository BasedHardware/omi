#!/usr/bin/env python3
"""Tests for shared release blessing helpers."""

from __future__ import annotations

from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from release_blessing import (  # noqa: E402
    SurfaceBlessing,
    dependency_closure,
    load_surface_registry,
    require_blessed_closure,
    surface_blessing_from_metadata,
)


def test_registry_loads_and_orders_dependencies() -> None:
    surfaces = load_surface_registry()
    assert "python-backend" in surfaces
    assert dependency_closure("desktop-macos", surfaces) == [
        "python-backend",
        "desktop-rust-backend",
        "desktop-macos",
    ]


def test_namespaced_python_backend_metadata() -> None:
    blessing = surface_blessing_from_metadata(
        {
            "blessed.python-backend": "true",
            "blessed.python-backend.sha": "abc123",
            "blessed.python-backend.at": "2026-07-07T00:00:00Z",
            "blessed.python-backend.tier": "unit+contracts",
            "blessed.python-backend.evidence": "backend-evidence.json",
        },
        "python-backend",
    )
    assert blessing.blessed
    assert blessing.sha == "abc123"
    assert blessing.blessed_at == "2026-07-07T00:00:00Z"
    assert blessing.tier == "unit+contracts"
    assert blessing.evidence == "backend-evidence.json"


def test_legacy_desktop_metadata_still_parses() -> None:
    blessing = surface_blessing_from_metadata(
        {
            "blessed": "true",
            "blessedSha": "desktop123",
            "blessedAt": "2026-07-07T00:00:00Z",
            "blessedTier": "2",
        },
        "desktop-macos",
        allow_legacy_desktop=True,
    )
    assert blessing.blessed
    assert blessing.sha == "desktop123"
    assert blessing.blessed_at == "2026-07-07T00:00:00Z"
    assert blessing.tier == "2"


def test_namespaced_desktop_metadata_preferred_over_legacy() -> None:
    blessing = surface_blessing_from_metadata(
        {
            "blessed": "true",
            "blessedSha": "stale",
            "blessedAt": "2026-07-06T00:00:00Z",
            "blessed.desktop-macos": "false",
            "blessed.desktop-macos.sha": "current",
            "blessed.desktop-macos.at": "2026-07-07T00:00:00Z",
        },
        "desktop-macos",
        allow_legacy_desktop=True,
    )
    assert not blessing.blessed
    assert blessing.sha == "current"
    assert blessing.blessed_at == "2026-07-07T00:00:00Z"


def test_closure_requires_every_surface_blessed() -> None:
    blessings = {
        "python-backend": SurfaceBlessing("python-backend", True, "py123", "2026-07-07T00:00:00Z", "unit", ""),
        "desktop-rust-backend": SurfaceBlessing(
            "desktop-rust-backend",
            True,
            "rust123",
            "2026-07-07T00:00:00Z",
            "contracts",
            "",
        ),
    }
    try:
        require_blessed_closure("desktop-macos", blessings)
    except SystemExit as exc:
        assert "desktop-macos" in str(exc)
    else:
        raise AssertionError("missing desktop-macos blessing should fail")


def test_closure_rejects_mismatched_blessing_surface() -> None:
    blessings = {
        "python-backend": SurfaceBlessing("desktop-macos", True, "py123", "2026-07-07T00:00:00Z", "unit", ""),
        "desktop-rust-backend": SurfaceBlessing(
            "desktop-rust-backend",
            True,
            "rust123",
            "2026-07-07T00:00:00Z",
            "contracts",
            "",
        ),
        "desktop-macos": SurfaceBlessing("desktop-macos", True, "desk123", "2026-07-07T00:00:00Z", "2", ""),
    }
    try:
        require_blessed_closure("desktop-macos", blessings)
    except SystemExit as exc:
        assert "desktop-macos promotion has desktop-macos blessing data for python-backend" in str(exc)
    else:
        raise AssertionError("mismatched blessing surface should fail")


if __name__ == "__main__":
    test_registry_loads_and_orders_dependencies()
    test_namespaced_python_backend_metadata()
    test_legacy_desktop_metadata_still_parses()
    test_namespaced_desktop_metadata_preferred_over_legacy()
    test_closure_requires_every_surface_blessed()
    test_closure_rejects_mismatched_blessing_surface()
    print("release blessing tests OK")
