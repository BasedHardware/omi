#!/usr/bin/env python3
"""Guard the manual qualified-artifact Stable pointer promotion."""

from pathlib import Path

WORKFLOW = Path(".github/workflows/desktop_promote_prod.yml")
BETA_WORKFLOW = Path(".github/workflows/desktop_promote_beta.yml")

REQUIRED = (
    "on:\n  workflow_dispatch:",
    "confirm:",
    "promote-stable",
    "operation:",
    "expected_current_release_id:",
    "expected_generation:",
    "qualification_run_id:",
    "environment: prod",
    "Validate trusted qualification run for initial promotion",
    "Fetch exact retained qualified manifest",
    '"https://api.omi.me/v2/desktop/releases/$RELEASE_TAG"',
    "manifest_sha256",
    "Verify current beta and stable pointer compare-and-swap inputs",
    '"$BASE/macos-beta"',
    "check_stable_pointer_precondition.py",
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
    ".event",
    ".path",
    "--if-generation-match=0",
    'operation\": os.environ[\"OPERATION\"]',
)

ORDERED_STEPS = (
    "Fetch exact retained qualified manifest",
    "Verify current beta and stable pointer compare-and-swap inputs",
    "Publish immutable stable repair installer",
    "Advance explicit stable pointer",
    "Bridge stable for legacy desktop clients",
    "Publish latest stable repair route",
    "Verify exact pointer, hashes, and stable feed",
)

BETA_REQUIRED = (
    "on:\n  workflow_dispatch:",
    "automatic:",
    "qualification_run_id:",
    "environment: beta",
    "Validate automatic beta request",
    "desktop-qualification-evidence-${{ inputs.release_tag }}",
    "credentials_json: ${{ secrets.GCP_CREDENTIALS }}",
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
        errors.append("stable promotion must fetch and verify retained identity before pointer mutation, then bridge and verify")
    return errors


def validate_beta(text: str) -> list[str]:
    errors = [f"missing Beta pointer-promotion guard: {fragment}" for fragment in BETA_REQUIRED if fragment not in text]
    if "environment: prod" in text:
        errors.append("Beta pointer promotion must not request the protected prod environment")
    return errors


def main() -> int:
    errors = validate(WORKFLOW.read_text(encoding="utf-8"))
    errors.extend(validate_beta(BETA_WORKFLOW.read_text(encoding="utf-8")))
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("desktop Stable and Beta pointer-promotion policies OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
