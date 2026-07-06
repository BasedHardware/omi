#!/usr/bin/env python3
"""Tests for desktop release promotion gate."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github/scripts/check-desktop-release-promotion.py"


def run_check(release: dict, tag: str, *extra: str) -> subprocess.CompletedProcess[str]:
    release_path = Path("/tmp/desktop-release-test.json")
    release_path.write_text(json.dumps(release), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--release-json", str(release_path), "--release-tag", tag, *extra],
        text=True,
        capture_output=True,
    )


def base_release(tag: str, metadata: dict[str, str]) -> dict:
    lines = ["KEY_VALUE_START", *[f"{key}: {value}" for key, value in metadata.items()], "KEY_VALUE_END"]
    return {
        "tagName": tag,
        "isDraft": False,
        "isPrerelease": False,
        "body": "\n".join(lines),
        "assets": [{"name": "Omi.zip"}, {"name": "omi.dmg"}],
    }


def test_unblessed_release_fails() -> None:
    tag = "v11.0.0+11000-macos"
    release = base_release(
        tag,
        {
            "channel": "beta",
            "isLive": "true",
            "edSignature": "sig",
        },
    )
    result = run_check(release, tag)
    assert result.returncode != 0
    assert "blessed" in result.stderr


def test_blessed_release_passes() -> None:
    tag = "v11.0+11000-macos"
    release = base_release(
        tag,
        {
            "channel": "beta",
            "isLive": "true",
            "edSignature": "sig",
            "blessed": "true",
            "blessedAt": "2026-07-06T00:00:00Z",
            "blessedSha": "abc123",
            "blessedTier": "2",
        },
    )
    result = run_check(release, tag)
    assert result.returncode == 0, result.stderr


def test_override_requires_typed_confirm() -> None:
    tag = "v11.0+11000-macos"
    release = base_release(
        tag,
        {
            "channel": "beta",
            "isLive": "true",
            "edSignature": "sig",
        },
    )
    result = run_check(release, tag, "--override-unblessed", "--override-confirm", "nope")
    assert result.returncode != 0
    override = run_check(
        release,
        tag,
        "--override-unblessed",
        "--override-confirm",
        "I-ACCEPT-UNBLESSED-PROD-RISK",
    )
    assert override.returncode == 0, override.stderr


if __name__ == "__main__":
    test_unblessed_release_fails()
    test_blessed_release_passes()
    test_override_requires_typed_confirm()
    print("check-desktop-release-promotion tests OK")
