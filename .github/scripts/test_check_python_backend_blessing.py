#!/usr/bin/env python3
"""Tests for Python backend blessing gate."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github/scripts/check-python-backend-blessing.py"


def run_check(release: dict, sha: str, *extra: str) -> subprocess.CompletedProcess[str]:
    release_path = Path("/tmp/python-backend-blessing-test.json")
    release_path.write_text(json.dumps(release), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--release-json", str(release_path), "--target-sha", sha, *extra],
        text=True,
        capture_output=True,
    )


def blessing_release(sha: str, metadata: dict[str, str]) -> dict:
    lines = ["KEY_VALUE_START", *[f"{key}: {value}" for key, value in metadata.items()], "KEY_VALUE_END"]
    return {
        "tagName": f"python-backend-bless-{sha}",
        "isDraft": False,
        "isPrerelease": False,
        "body": "\n".join(lines),
        "assets": [{"name": f"python-backend-bless-evidence-{sha}.json"}],
    }


def test_blessed_backend_passes() -> None:
    sha = "a" * 40
    release = blessing_release(
        sha,
        {
            "blessed.python-backend": "true",
            "blessed.python-backend.sha": sha,
            "blessed.python-backend.at": "2026-07-07T00:00:00Z",
            "blessed.python-backend.tier": "unit+workflow-contracts+openapi",
            "blessed.python-backend.evidence": f"python-backend-bless-evidence-{sha}.json",
        },
    )
    result = run_check(release, sha)
    assert result.returncode == 0, result.stderr


def test_unblessed_backend_fails() -> None:
    sha = "b" * 40
    release = blessing_release(
        sha,
        {
            "blessed.python-backend.sha": sha,
            "blessed.python-backend.at": "2026-07-07T00:00:00Z",
        },
    )
    result = run_check(release, sha)
    assert result.returncode != 0
    assert "python-backend" in result.stderr


def test_sha_mismatch_fails() -> None:
    sha = "c" * 40
    release = blessing_release(
        sha,
        {
            "blessed.python-backend": "true",
            "blessed.python-backend.sha": "d" * 40,
            "blessed.python-backend.at": "2026-07-07T00:00:00Z",
        },
    )
    result = run_check(release, sha)
    assert result.returncode != 0
    assert "does not match" in result.stderr


def test_tag_sha_mismatch_fails() -> None:
    sha = "f" * 40
    release = blessing_release(
        sha,
        {
            "blessed.python-backend": "true",
            "blessed.python-backend.sha": sha,
            "blessed.python-backend.at": "2026-07-07T00:00:00Z",
            "blessed.python-backend.evidence": f"python-backend-bless-evidence-{sha}.json",
        },
    )
    result = run_check(release, sha, "--tag-sha", "0" * 40)
    assert result.returncode != 0
    assert "tag sha" in result.stderr


def test_override_requires_typed_confirm() -> None:
    sha = "e" * 40
    release = {"tagName": "wrong-tag", "body": ""}
    result = run_check(release, sha, "--override-unblessed", "--override-confirm", "nope")
    assert result.returncode != 0
    override = run_check(
        release,
        sha,
        "--override-unblessed",
        "--override-confirm",
        "I-ACCEPT-UNBLESSED-PROD-RISK",
    )
    assert override.returncode == 0, override.stderr


if __name__ == "__main__":
    test_blessed_backend_passes()
    test_unblessed_backend_fails()
    test_sha_mismatch_fails()
    test_tag_sha_mismatch_fails()
    test_override_requires_typed_confirm()
    print("check-python-backend-blessing tests OK")
