#!/usr/bin/env python3
"""Guard the manual current-Beta-to-Stable pointer promotion."""

from pathlib import Path

WORKFLOW = Path(".github/workflows/desktop_promote_prod.yml")

# Stable CAS inputs are workflow-owned and the requested release must already
# be the exact current Beta pointer target.
REQUIRED = (
    "on:\n  workflow_dispatch:",
    "confirm:",
    "promote-stable",
    "environment: prod",
    "Verify live desktop-backend chat compatibility",
    '.chat_contract_version == "1"',
    "Validate stable promotion request",
    "Fetch exact retained Beta manifest",
    '"https://api.omi.me/v2/desktop/releases/$RELEASE_TAG"',
    "manifest_sha256",
    "Read current pointers and capture workflow-owned CAS inputs",
    "Stable promotion requires the exact current Beta release ID",
    '"$BASE/macos-beta"',
    "EXPECTED_RELEASE_ID",
    "EXPECTED_GENERATION",
    "desktop_update_channels/macos-stable",
    "desktop_release_manifests/$RELEASE_TAG",
    "Publish immutable stable repair installer",
    "Advance explicit stable pointer",
    "Bridge stable for legacy desktop clients",
    "Publish latest stable repair route",
    "Verify exact pointer, hashes, and stable feed",
    "https://api.omi.me/v2/desktop/channels/promote",
    "appcast.xml?identity=stable",
    "verify_stable_appcast.py",
    "--if-generation-match=0",
)

ORDERED_STEPS = (
    "Verify live desktop-backend chat compatibility",
    "Validate stable promotion request",
    "Fetch exact retained Beta manifest",
    "Read current pointers and capture workflow-owned CAS inputs",
    "Publish immutable stable repair installer",
    "Advance explicit stable pointer",
    "Bridge stable for legacy desktop clients",
    "Publish latest stable repair route",
    "Verify exact pointer, hashes, and stable feed",
)


def validate(text: str) -> list[str]:
    errors = [f"missing Stable pointer-promotion guard: {fragment}" for fragment in REQUIRED if fragment not in text]
    for forbidden in ("break_glass", "Deploy Desktop Backend", "gcloud run deploy", "desktop-backend-prod-deployed"):
        if forbidden in text:
            errors.append(f"stable pointer promotion must not contain backend deployment or bypass path: {forbidden}")
    if "\n  push:" in text or "\n  schedule:" in text or "\n  release:" in text:
        errors.append("stable pointer promotion must remain manual-only")
    order = [text.find(fragment) for fragment in ORDERED_STEPS]
    if -1 in order or order != sorted(order):
        errors.append(
            "stable promotion must fetch and verify retained identity before pointer mutation, then bridge and verify"
        )
    return errors


def main() -> int:
    errors = validate(WORKFLOW.read_text(encoding="utf-8"))
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("desktop Stable pointer-promotion policy OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
