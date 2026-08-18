#!/usr/bin/env python3
"""Classify whether a commit can affect the admin Cloud Run deployment.

The admin workflow path filter is broader than the admin *runtime*: generated
OpenAPI clients under web/admin/ and shared public-build helper noise can start
a run that then waits on ``environment: prod``. This classifier is the
conservative allowlist used by the unprivileged scope job: skip green only when
every changed path is known not to affect admin runtime, image/build inputs,
this workflow, or the shared public-build deploy/prepare/promotion surface.
Uncertain input deploys.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import subprocess
import sys
from pathlib import Path

ZERO_SHA = re.compile(r"^0+$")

GENERATED_ADMIN_CLIENT_PATTERNS = (
    "web/admin/**/*.generated.ts",
    "web/admin/**/*.generated.js",
    "web/admin/**/*.generated.tsx",
)

ADMIN_RUNTIME_PREFIXES = ("web/admin/",)

ADMIN_WORKFLOW_PATHS = (
    ".github/workflows/gcp_admin.yml",
    ".github/scripts/check_admin_deploy_scope.py",
)

PUBLIC_BUILD_DEPLOY_PREFIXES = (
    ".github/actions/deploy-public-build/",
    ".github/actions/prepare-public-build/",
    ".github/actions/public-build-candidate-promotion/",
)

PUBLIC_BUILD_DEPLOY_FILES = (
    ".github/scripts/preflight_public_build_config.py",
    ".github/scripts/preflight_public_build_runtime.py",
    ".github/scripts/smoke_public_build_browser.py",
)

PUBLIC_BUILD_CONFIG_PATTERNS = ("config/public-build-*.json",)


def is_generated_admin_client(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in GENERATED_ADMIN_CLIENT_PATTERNS)


def is_admin_runtime_source(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if is_generated_admin_client(normalized):
        return False
    return any(normalized == prefix.rstrip("/") or normalized.startswith(prefix) for prefix in ADMIN_RUNTIME_PREFIXES)


def is_admin_workflow_or_gate(path: str) -> bool:
    return path.replace("\\", "/") in ADMIN_WORKFLOW_PATHS


def is_public_build_deploy_input(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if any(normalized.startswith(prefix) for prefix in PUBLIC_BUILD_DEPLOY_PREFIXES):
        return True
    if normalized in PUBLIC_BUILD_DEPLOY_FILES:
        return True
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in PUBLIC_BUILD_CONFIG_PATTERNS)


def path_can_affect_admin_deploy(path: str) -> bool:
    return is_admin_runtime_source(path) or is_admin_workflow_or_gate(path) or is_public_build_deploy_input(path)


def admin_deploy_applies(
    changed_files: list[str] | None,
    *,
    event_name: str,
    parent_available: bool = True,
) -> bool:
    """Return whether the admin deploy job should take the environment slot."""

    if event_name == "workflow_dispatch":
        return True
    if not parent_available:
        return True
    if changed_files is None:
        return True
    return any(path_can_affect_admin_deploy(path) for path in changed_files)


def _git(*args: str, cwd: str | Path | None = None) -> subprocess.CompletedProcess[str]:
    env = None
    if cwd is not None:
        # Fixture repos must not inherit a hook's GIT_DIR / GIT_INDEX_FILE.
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    return subprocess.run(["git", *args], check=False, capture_output=True, text=True, cwd=cwd, env=env)


def is_missing_or_zero_sha(value: str | None) -> bool:
    if value is None:
        return True
    stripped = value.strip()
    return not stripped or bool(ZERO_SHA.fullmatch(stripped))


def decide_from_git(
    *,
    event_name: str,
    sha: str | None = None,
    before: str | None = None,
    repo: str | Path | None = None,
) -> tuple[bool, str]:
    if event_name == "workflow_dispatch":
        return True, "workflow_dispatch is always in scope."

    target = sha or "HEAD"
    if _git("cat-file", "-e", f"{target}^{{commit}}", cwd=repo).returncode != 0:
        return True, f"could not resolve triggering commit {target}; deploying fail-closed."

    if is_missing_or_zero_sha(before):
        return True, "push before SHA is missing or zero; deploying fail-closed."

    before_sha = before.strip()
    if _git("cat-file", "-e", f"{before_sha}^{{commit}}", cwd=repo).returncode != 0:
        return True, f"could not resolve push before SHA {before_sha}; deploying fail-closed."

    diff = _git("diff", "--name-only", before_sha, target, cwd=repo)
    if diff.returncode != 0:
        return True, "could not diff the full push range; deploying fail-closed."

    changed = [line for line in diff.stdout.splitlines() if line.strip()]
    applies = admin_deploy_applies(changed, event_name=event_name, parent_available=True)
    if applies:
        return True, "the push range can affect admin runtime or deployment inputs."
    return False, "the push range cannot affect admin runtime or deployment inputs."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-name", default=os.environ.get("EVENT_NAME", ""))
    parser.add_argument("--sha", default=os.environ.get("ADMIN_SCOPE_SHA", ""))
    parser.add_argument("--before", default=os.environ.get("ADMIN_SCOPE_BEFORE", ""))
    parser.add_argument("--github-output", action="store_true")
    args = parser.parse_args()

    event_name = args.event_name or os.environ.get("GITHUB_EVENT_NAME", "")
    if not event_name:
        print("ERROR: event name is required", file=sys.stderr)
        return 1

    applies, reason = decide_from_git(
        event_name=event_name,
        sha=args.sha or None,
        before=args.before or None,
    )
    applies_value = "true" if applies else "false"
    print(f"applies={applies_value}")
    print(reason)

    if args.github_output:
        output = os.environ.get("GITHUB_OUTPUT")
        if not output:
            print("ERROR: GITHUB_OUTPUT is required with --github-output", file=sys.stderr)
            return 1
        Path(output).write_text(f"applies={applies_value}\n", encoding="utf-8")
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            title = "Admin deploy scope" if applies else "Admin deploy no-op"
            prefix = "In scope:" if applies else "Green no-op:"
            with Path(summary).open("a", encoding="utf-8") as handle:
                handle.write(f"### {title}\n{prefix} {reason}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
