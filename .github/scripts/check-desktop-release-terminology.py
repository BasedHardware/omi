#!/usr/bin/env python3
"""Guard canonical desktop release terminology and nomination boundaries."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OPERATOR_SURFACES = (
    "AGENTS.md",
    "codemagic.yaml",
    "desktop/macos/AGENTS.md",
    "desktop/macos/docs/agent-prod-promotion-runbook.md",
    "docs/doc/developer/desktop-updates.mdx",
    ".github/workflows/desktop_promote_beta.yml",
    ".github/workflows/desktop_promote_prod.yml",
    ".github/workflows/desktop_nominate_stable_candidate.yml",
    "web/admin/app/api/omi/releases/route.ts",
    "web/admin/app/(protected)/dashboard/releases/page.tsx",
)


def main() -> int:
    failures: list[str] = []
    legacy_term = re.compile(r"\bbless(?:ed|ing)?\b", re.IGNORECASE)
    for relative in OPERATOR_SURFACES:
        path = ROOT / relative
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if legacy_term.search(line) and "legacy" not in line.lower():
                failures.append(f"{relative}:{line_number}: desktop beta qualification uses legacy terminology")

    canonical_script = ROOT / "desktop/macos/scripts/qualify-desktop-beta.sh"
    legacy_script = ROOT / "desktop/macos/scripts/bless-release.sh"
    if not canonical_script.is_file():
        failures.append("desktop beta qualification script is missing")
    if legacy_script.exists():
        failures.append("legacy desktop beta qualification script still exists")

    nomination = (ROOT / ".github/workflows/desktop_nominate_stable_candidate.yml").read_text(encoding="utf-8")
    for forbidden in ("/v2/desktop/channels/promote", "mark-desktop-release-stable.py", "desktop_promote_prod.yml -f"):
        if forbidden in nomination:
            failures.append(f"stable-candidate nomination must not perform promotion action {forbidden!r}")
    for required in (
        "workflow_dispatch:",
        "desktop_update_channels/macos-beta",
        "desktop_release_manifests/${RELEASE_TAG}",
        "--beta-source-sha",
        "nominate-desktop-stable-candidate.py",
        "Stable visibility was not changed",
    ):
        if required not in nomination:
            failures.append(f"stable-candidate workflow is missing guard fragment {required!r}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("desktop release terminology and nomination boundaries OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
