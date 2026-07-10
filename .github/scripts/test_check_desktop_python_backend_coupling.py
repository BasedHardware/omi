#!/usr/bin/env python3
"""Hermetic tests for desktop ↔ python-backend coupling gate."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github/scripts/check-desktop-python-backend-coupling.py"
DESKTOP_SHA = "a" * 40
PYTHON_SHA = "b" * 40
OTHER_SHA = "c" * 40
BREAK_GLASS_CONFIRM = "I-ACCEPT-STABLE-PROMOTION-RISK"


def blessing_release(sha: str) -> dict:
    evidence = f"python-backend-bless-evidence-{sha}.json"
    lines = [
        "KEY_VALUE_START",
        "blessed.python-backend: true",
        f"blessed.python-backend.sha: {sha}",
        "blessed.python-backend.at: 2026-07-10T00:00:00Z",
        "blessed.python-backend.tier: unit+workflow-contracts+openapi",
        f"blessed.python-backend.evidence: {evidence}",
        "KEY_VALUE_END",
    ]
    return {
        "tagName": f"python-backend-bless-{sha}",
        "isDraft": False,
        "isPrerelease": False,
        "body": "\n".join(lines),
        "assets": [{"name": evidence}],
    }


def run_check(*extra: str, release: dict | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--desktop-target-sha",
        DESKTOP_SHA,
        *extra,
    ]
    with tempfile.TemporaryDirectory() as tmp:
        if release is not None:
            release_path = Path(tmp) / "python-backend-attestation.json"
            release_path.write_text(json.dumps(release), encoding="utf-8")
            cmd.extend(["--release-json", str(release_path)])
        return subprocess.run(cmd, text=True, capture_output=True)


def test_attested_ancestor_passes() -> None:
    result = run_check(
        "--python-backend-sha",
        PYTHON_SHA,
        "--tag-sha",
        PYTHON_SHA,
        "--test-is-ancestor",
        "true",
        release=blessing_release(PYTHON_SHA),
    )
    assert result.returncode == 0, result.stderr
    assert "coupling OK" in result.stdout


def test_missing_sha_fails() -> None:
    result = run_check()
    assert result.returncode != 0
    assert "python_backend_sha is required" in result.stderr


def test_missing_sha_with_break_glass_passes() -> None:
    result = run_check(
        "--break-glass",
        "--break-glass-confirm",
        BREAK_GLASS_CONFIRM,
        "--break-glass-reason",
        "urgent stable hotfix without attested backend",
    )
    assert result.returncode == 0, result.stderr
    assert "skipped by audited desktop break-glass" in result.stdout


def test_bad_attestation_fails() -> None:
    result = run_check(
        "--python-backend-sha",
        PYTHON_SHA,
        "--test-is-ancestor",
        "true",
        release={"tagName": "wrong-tag", "body": "", "assets": []},
    )
    assert result.returncode != 0
    assert "blessing tag mismatch" in result.stderr or "FAIL:" in result.stderr


def test_non_ancestor_fails() -> None:
    result = run_check(
        "--python-backend-sha",
        PYTHON_SHA,
        "--tag-sha",
        PYTHON_SHA,
        "--test-is-ancestor",
        "false",
        release=blessing_release(PYTHON_SHA),
    )
    assert result.returncode != 0
    assert "not an ancestor" in result.stderr


def test_non_ancestor_with_break_glass_passes() -> None:
    result = run_check(
        "--python-backend-sha",
        OTHER_SHA,
        "--test-is-ancestor",
        "false",
        "--break-glass",
        "--break-glass-confirm",
        BREAK_GLASS_CONFIRM,
        "--break-glass-reason",
        "promote despite non-ancestor attested sha",
        release=blessing_release(OTHER_SHA),
    )
    assert result.returncode == 0, result.stderr
    assert "skipped by audited desktop break-glass" in result.stdout


def test_break_glass_requires_stable_phrase() -> None:
    rejected = run_check(
        "--break-glass",
        "--break-glass-confirm",
        "I-ACCEPT-UNBLESSED-PROD-RISK",
        "--break-glass-reason",
        "wrong phrase must not skip coupling",
    )
    assert rejected.returncode != 0
    assert BREAK_GLASS_CONFIRM in rejected.stderr


def test_invalid_sha_format_fails() -> None:
    result = run_check(
        "--python-backend-sha",
        "abc123",
        "--test-is-ancestor",
        "true",
        release=blessing_release(PYTHON_SHA),
    )
    assert result.returncode != 0
    assert "40-char" in result.stderr


def test_break_glass_path_does_not_need_unblessed_phrase() -> None:
    result = run_check(
        "--python-backend-sha",
        PYTHON_SHA,
        "--break-glass",
        "--break-glass-confirm",
        BREAK_GLASS_CONFIRM,
        "--break-glass-reason",
        "skip coupling without unblessed override bridge",
    )
    assert result.returncode == 0, result.stderr
    combined = f"{result.stdout}\n{result.stderr}"
    assert "I-ACCEPT-UNBLESSED-PROD-RISK" not in combined
    assert "--override-unblessed" not in combined


if __name__ == "__main__":
    test_attested_ancestor_passes()
    test_missing_sha_fails()
    test_missing_sha_with_break_glass_passes()
    test_bad_attestation_fails()
    test_non_ancestor_fails()
    test_non_ancestor_with_break_glass_passes()
    test_break_glass_requires_stable_phrase()
    test_invalid_sha_format_fails()
    test_break_glass_path_does_not_need_unblessed_phrase()
    print("check-desktop-python-backend-coupling tests OK")
