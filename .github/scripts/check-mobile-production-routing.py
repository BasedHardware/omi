#!/usr/bin/env python3
"""Fail closed when any production-family client can leave its data plane."""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOWS = (
    "ios-internal-auto",
    "android-internal-auto",
    "ios-prod-testflight",
    "android-prod-internal",
    "ios-prod-patch",
    "android-prod-patch",
    "macos-prod-appstore",
)
DESKTOP_WORKFLOW = "omi-desktop-swift-release"
PIN = "https://api.omi.me/"
DESKTOP_PIN = "https://api.omi.me"
DESKTOP_BACKEND_PIN = "https://desktop-backend-hhibjajaja-uc.a.run.app/"
RETIRED_GKE_DESKTOP_BACKEND_CHART_ROOTS = (
    "backend/charts",
    "desktop/macos/charts",
)
RETIRED_GKE_DESKTOP_BACKEND_WORKFLOW_ROOT = ".github/workflows"
RETIRED_GKE_DESKTOP_BACKEND_MANIFEST_SUFFIXES = {".tpl", ".yaml", ".yml"}
RETIRED_GKE_DESKTOP_BACKEND_MARKERS = ("desktop-api.omi.me", "desktop-backend")
GKE_WORKFLOW_MARKERS = ("gcloud container clusters", "helm ", "kubectl ")
LEGACY_BETA_ROUTING_PATHS = (
    "codemagic.yaml",
    "app/lib/env/dev_env.dart",
    "app/lib/env/prod_env.dart",
    "app/lib/main.dart",
    "app/lib/utils/environment_detector.dart",
    "desktop/macos/Desktop/Sources/DesktopBackendEnvironment.swift",
)
FORBIDDEN_ROUTING_TOKENS = (
    "OMI_BETA_RELEASE_RING",
    "api-beta.omi.me",
    "STAGING_API_URL",
)
REQUIRED_PRODUCTION_FRAGMENTS = {
    "desktop/macos/Desktop/Sources/AppBuild.swift": (
        'productionBundleIdentifier = "com.omi.computer-macos"',
        "externalPreviewBundleIdentifierPrefix",
    ),
    "desktop/macos/Desktop/Sources/GoogleService-Info.plist": (
        "<string>based-hardware</string>",
    ),
}
CANONICAL_MACOS_PRODUCTION_BUNDLE_IDENTIFIER = "com.omi.computer-macos"
# INV-BETA-1: the side-by-side Omi Beta app is the single sanctioned second
# production identity (founder decision, 2026-07-22). Any other divergent
# identity remains rejected.
SANCTIONED_MACOS_PRODUCTION_BUNDLE_IDENTIFIERS = {
    CANONICAL_MACOS_PRODUCTION_BUNDLE_IDENTIFIER,
    "com.omi.computer-macos.beta",
}
MACOS_PRODUCTION_BUNDLE_IDENTIFIER_PATTERN = re.compile(r'"(com\.omi\.computer-macos(?:\.[^"]+)?)"')


def _workflow_block(text: str, workflow: str) -> str | None:
    match = re.search(rf"(?ms)^  {re.escape(workflow)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", text)
    return match.group(1) if match else None


def _retired_gke_desktop_backend_manifests(root: Path) -> list[Path]:
    retired_manifests = []
    for chart_root in RETIRED_GKE_DESKTOP_BACKEND_CHART_ROOTS:
        manifests_root = root / chart_root
        if not manifests_root.is_dir():
            continue
        for manifest in manifests_root.rglob("*"):
            if not manifest.is_file() or manifest.suffix not in RETIRED_GKE_DESKTOP_BACKEND_MANIFEST_SUFFIXES:
                continue
            source = manifest.read_text(encoding="utf-8")
            if any(marker in source for marker in RETIRED_GKE_DESKTOP_BACKEND_MARKERS):
                retired_manifests.append(manifest.relative_to(root))

    workflow_root = root / RETIRED_GKE_DESKTOP_BACKEND_WORKFLOW_ROOT
    if workflow_root.is_dir():
        for workflow in workflow_root.glob("*.y*ml"):
            source = workflow.read_text(encoding="utf-8")
            if (
                any(marker in source for marker in RETIRED_GKE_DESKTOP_BACKEND_MARKERS)
                and any(marker in source for marker in GKE_WORKFLOW_MARKERS)
            ):
                retired_manifests.append(workflow.relative_to(root))
    return retired_manifests


def validate(root: Path) -> list[str]:
    text = (root / "codemagic.yaml").read_text(encoding="utf-8")
    errors: list[str] = []
    for manifest in _retired_gke_desktop_backend_manifests(root):
        errors.append(
            f"{manifest} declares retired GKE desktop-backend ownership; production desktop-backend is Cloud Run"
        )
    for workflow in WORKFLOWS:
        block = _workflow_block(text, workflow)
        assignments = re.findall(r"(?m)^\s*echo API_BASE_URL=([^\s]+) >> \.env\s*$", block or "")
        if assignments != [PIN]:
            errors.append(
                f"{workflow} must contain exactly one immutable API_BASE_URL=https://api.omi.me/ assignment"
            )
    desktop_block = _workflow_block(text, DESKTOP_WORKFLOW)
    desktop_bundle_identifiers = re.findall(
        r"(?m)^\s*BUNDLE_ID:\s*[\"']?([^\"'\s]+)[\"']?\s*$", desktop_block or ""
    )
    if desktop_bundle_identifiers != [CANONICAL_MACOS_PRODUCTION_BUNDLE_IDENTIFIER]:
        errors.append(
            f"{DESKTOP_WORKFLOW} must contain exactly one immutable "
            f"BUNDLE_ID={CANONICAL_MACOS_PRODUCTION_BUNDLE_IDENTIFIER} assignment"
        )
    desktop_assignments = re.findall(r"(?m)^\s*OMI_PYTHON_API_URL:\s*[\"']?([^\"'\s]+)[\"']?\s*$", desktop_block or "")
    if desktop_assignments != [DESKTOP_PIN]:
        errors.append(
            f"{DESKTOP_WORKFLOW} must contain exactly one immutable OMI_PYTHON_API_URL=https://api.omi.me assignment"
        )
    desktop_backend_assignments = re.findall(
        r"(?m)^\s*OMI_DESKTOP_API_URL:\s*[\"']?([^\"'\s]+)[\"']?\s*$", desktop_block or ""
    )
    if desktop_backend_assignments != [DESKTOP_BACKEND_PIN]:
        errors.append(
            f"{DESKTOP_WORKFLOW} must contain exactly one immutable "
            "OMI_DESKTOP_API_URL=https://desktop-backend-hhibjajaja-uc.a.run.app/ assignment"
        )
    for relative_path in LEGACY_BETA_ROUTING_PATHS:
        source_path = root / relative_path
        if not source_path.is_file():
            errors.append(f"missing protected production-routing source {relative_path}")
            continue
        source = source_path.read_text(encoding="utf-8")
        for token in FORBIDDEN_ROUTING_TOKENS:
            if token in source:
                errors.append(f"{relative_path} must not contain legacy beta/staging routing token {token}")
    for relative_path, required_fragments in REQUIRED_PRODUCTION_FRAGMENTS.items():
        source_path = root / relative_path
        if not source_path.is_file():
            errors.append(f"missing protected production identity source {relative_path}")
            continue
        source = source_path.read_text(encoding="utf-8")
        for fragment in required_fragments:
            if fragment not in source:
                errors.append(f"{relative_path} must retain protected production identity fragment {fragment!r}")
        if relative_path == "desktop/macos/Desktop/Sources/AppBuild.swift":
            for bundle_identifier in MACOS_PRODUCTION_BUNDLE_IDENTIFIER_PATTERN.findall(source):
                if bundle_identifier not in SANCTIONED_MACOS_PRODUCTION_BUNDLE_IDENTIFIERS:
                    errors.append(
                        f"{relative_path} must not define divergent production-family bundle identity "
                        f"{bundle_identifier!r}"
                    )
    return errors


if __name__ == "__main__":
    raise SystemExit(1 if validate(Path(".")) else 0)
