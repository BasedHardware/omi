#!/usr/bin/env python3
"""Guard the desktop backend prod promotion workflow.

Prod desktop backend deploys must be a manual stable-promotion action. This
check is deliberately text-based and narrow: it fails on the risky regressions
we have already seen, without requiring PyYAML in CI.
"""

from pathlib import Path


WORKFLOW = Path(".github/workflows/desktop_promote_prod.yml")


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def require(needle: str, text: str, message: str) -> None:
    if needle not in text:
        fail(message)


def workflow_triggers(text: str) -> list[str]:
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line == "on:")
    except StopIteration:
        fail("workflow is missing top-level on: block")

    triggers: list[str] = []
    for line in lines[start + 1 :]:
        if not line.strip() or line.startswith("#"):
            continue
        if line and not line.startswith(" "):
            break
        if line.startswith("  ") and not line.startswith("    "):
            triggers.append(line.strip().split(":", 1)[0])
    return triggers


def main() -> int:
    text = WORKFLOW.read_text()
    triggers = workflow_triggers(text)

    require("on:\n  workflow_dispatch:", text, "prod promotion must be workflow_dispatch only")
    if triggers != ["workflow_dispatch"]:
        fail(f"prod promotion must allow only workflow_dispatch, got: {', '.join(triggers) or '<none>'}")
    require("release_tag:", text, "manual promotion must require an explicit release tag")
    require("confirm:", text, "manual promotion must require an explicit confirmation input")
    require("promote-stable", text, "manual promotion confirmation phrase must remain explicit")

    forbidden_triggers = [
        "\n  release:",
        "\n  schedule:",
        "\n  push:",
        "\n  pull_request:",
        "\n  pull_request_target:",
    ]
    for trigger in forbidden_triggers:
        if trigger in text:
            fail(f"desktop backend prod promotion must not use automatic trigger {trigger.strip()}")

    require("check-desktop-release-promotion.py", text, "workflow must run pre-release sanity checks")
    require("does not include /health release identity support", text, "workflow must reject tags that cannot report release identity")
    require("Preflight Firestore bridge release", text, "workflow must verify the Firestore bridge release before prod deploy")
    require("Deploy Desktop Backend to Production", text, "guard should cover the prod deploy workflow")
    require("Verify prod backend release identity", text, "prod deploy must verify the backend release identity before release metadata changes")
    require("Promote Firestore release stable", text, "workflow must promote the Rust appcast Firestore release")
    require("mark-desktop-release-stable.py", text, "workflow must mark the release stable only after backend verification")
    require("Clear desktop update cache", text, "workflow should clear Python desktop update cache after stable metadata changes")
    require("Advance prod-tracking tag", text, "workflow must move the prod tracking tag after promotion succeeds")
    require("grep -qE '^v.+-macos$'", text, "prod deploys must be limited to macOS desktop release tags")
    require("OMI_DESKTOP_RELEASE_TAG=", text, "prod deploy must stamp release tag into Cloud Run")
    require("OMI_DESKTOP_RELEASE_SHA=", text, "prod deploy must stamp release sha into Cloud Run")
    require("OMI_DESKTOP_RELEASE_CHANNEL=stable", text, "prod deploy must stamp stable channel into Cloud Run")
    require("RELEASE_SECRET=RELEASE_SECRET:latest", text, "prod deploy must expose release secret for Firestore promotion")

    if "gh release list" in text:
        fail("prod promotion must not scan old releases; deploy only the event/manual target")

    print("desktop prod promotion policy OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
