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
DESKTOP_RUST_PIN = "https://desktop-backend-hhibjajaja-uc.a.run.app/"
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
MACOS_PRODUCTION_BUNDLE_IDENTIFIER_PATTERN = re.compile(r'"(com\.omi\.computer-macos(?:\.[^"]+)?)"')


def _workflow_block(text: str, workflow: str) -> str | None:
    match = re.search(rf"(?ms)^  {re.escape(workflow)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", text)
    return match.group(1) if match else None


def validate(root: Path) -> list[str]:
    text = (root / "codemagic.yaml").read_text(encoding="utf-8")
    errors: list[str] = []
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
    desktop_rust_assignments = re.findall(
        r"(?m)^\s*OMI_DESKTOP_API_URL:\s*[\"']?([^\"'\s]+)[\"']?\s*$", desktop_block or ""
    )
    if desktop_rust_assignments != [DESKTOP_RUST_PIN]:
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
                if bundle_identifier != CANONICAL_MACOS_PRODUCTION_BUNDLE_IDENTIFIER:
                    errors.append(
                        f"{relative_path} must not define divergent production-family bundle identity "
                        f"{bundle_identifier!r}"
                    )
    return errors


if __name__ == "__main__":
    raise SystemExit(1 if validate(Path(".")) else 0)
