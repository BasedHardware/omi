#!/usr/bin/env python3
"""Guard the manual qualified-artifact Stable pointer promotion."""

from pathlib import Path

WORKFLOW = Path(".github/workflows/desktop_promote_prod.yml")

REQUIRED = (
    "on:\n  workflow_dispatch:",
    "confirm:",
    "promote-stable",
    "environment: prod",
    "Select and validate the exact trusted qualification",
    "Fetch exact retained qualified manifest",
    '"https://api.omi.me/v2/desktop/releases/$RELEASE_TAG"',
    "manifest_sha256",
    "Read current pointers and capture workflow-owned CAS inputs",
    '"$BASE/macos-beta"',
    "desktop_update_channels/macos-stable",
    "desktop_release_manifests/$RELEASE_TAG",
    "Publish immutable stable repair installer",
    "Advance explicit stable pointer",
    "Bridge stable for legacy desktop clients",
    "Publish latest stable repair route",
    "Verify exact pointer, hashes, and stable feed",
    "https://api.omi.me/v2/desktop/channels/promote",
    "Authorization: Bearer $ACCESS_TOKEN",
    "appcast.xml?identity=stable",
    "verify_stable_appcast.py",
    "desktop_qualification_admission.py",
    "--if-generation-match=0",
    "EXPECTED_RELEASE_ID",
    "EXPECTED_GENERATION",
    "Stable promotion requires the exact current qualified Beta release ID",
)

ORDERED_STEPS = (
    "Fetch exact retained qualified manifest",
    "Read current pointers and capture workflow-owned CAS inputs",
    "Publish immutable stable repair installer",
    "Advance explicit stable pointer",
    "Bridge stable for legacy desktop clients",
    "Publish latest stable repair route",
    "Verify exact pointer, hashes, and stable feed",
)

REMOVED_OPERATOR_INPUTS = (
    "operation:",
    "expected_current_release_id:",
    "expected_generation:",
    "qualification_run_id:",
    "repoint",
)


def validate(text: str) -> list[str]:
    errors = [f"missing Stable pointer-promotion guard: {fragment}" for fragment in REQUIRED if fragment not in text]
    for forbidden in ("break_glass", "Deploy Desktop Backend", "gcloud run deploy", "desktop-backend-prod-deployed"):
        if forbidden in text:
            errors.append(f"stable pointer promotion must not contain backend deployment or bypass path: {forbidden}")
    for removed in REMOVED_OPERATOR_INPUTS:
        if removed in text:
            errors.append(f"stable pointer promotion must not reintroduce collapsed operator input: {removed}")
    if "\n  push:" in text or "\n  schedule:" in text or "\n  release:" in text:
        errors.append("stable pointer promotion must remain manual-only")
    order = [text.find(fragment) for fragment in ORDERED_STEPS]
    if -1 in order or order != sorted(order):
        errors.append("stable promotion must fetch and verify retained identity before pointer mutation, then bridge and verify")
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
