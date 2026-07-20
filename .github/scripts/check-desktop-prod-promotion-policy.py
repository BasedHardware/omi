#!/usr/bin/env python3
"""Guard the manual qualified-artifact Stable pointer promotion."""

from pathlib import Path

WORKFLOW = Path(".github/workflows/desktop_promote_prod.yml")


def main() -> int:
    text = WORKFLOW.read_text(encoding="utf-8")
    required = (
        "on:\n  workflow_dispatch:",
        "confirm:",
        "promote-stable",
        "operation:",
        "expected_current_release_id:",
        "expected_generation:",
        "environment: prod",
        '"$BASE/macos-beta"',
        "Stable promotion requires the exact current qualified beta release ID.",
        "desktop_update_channels/macos-stable",
        "desktop_release_manifests/$RELEASE_TAG",
        "Register immutable release manifest",
        "Publish immutable stable repair installer",
        "Advance explicit stable pointer",
        "Bridge stable for legacy desktop clients",
        "Publish latest stable repair route",
        "Verify exact pointer, hashes, and stable feed",
        "https://api.omi.me/v2/desktop/channels/promote",
        "--if-generation-match=0",
        "operation\": os.environ[\"OPERATION\"]",
    )
    errors = [f"missing Stable pointer-promotion guard: {fragment}" for fragment in required if fragment not in text]
    for forbidden in ("break_glass", "Deploy Desktop Backend", "gcloud run deploy", "desktop-backend-prod-deployed"):
        if forbidden in text:
            errors.append(f"stable pointer promotion must not contain backend deployment or bypass path: {forbidden}")
    if "\n  push:" in text or "\n  schedule:" in text or "\n  release:" in text:
        errors.append("stable pointer promotion must remain manual-only")
    order = [text.find(fragment) for fragment in required[11:17]]
    if -1 in order or order != sorted(order):
        errors.append("stable promotion must publish exact artifacts before pointer, then bridge and verify")
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("desktop Stable pointer-promotion policy OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
