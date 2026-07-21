#!/usr/bin/env python3
"""Tests for automatic desktop beta candidate validation."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("check-desktop-auto-beta-candidate.py")
SIGNED_SMOKE = Path(__file__).parents[2] / "desktop/macos/scripts/smoke-signed-desktop-artifact.sh"
SPEC = importlib.util.spec_from_file_location("check_desktop_auto_beta_candidate", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
REQUIRED_SMOKE_CHECKS = MODULE.REQUIRED_SMOKE_CHECKS
validate = MODULE.validate


TAG = "v0.12.99+12099-macos"
SHA = "a" * 40
ZIP_SHA = "b" * 64
DMG_SHA = "c" * 64


def fixtures(root: Path) -> argparse.Namespace:
    release = {
        "tagName": TAG,
        "isDraft": False,
        "isPrerelease": False,
        "publishedAt": "2026-07-10T12:00:00Z",
        "body": "<!-- KEY_VALUE_START\nisLive: false\nchannel: candidate\nKEY_VALUE_END -->",
        "assets": [
            {"name": "Omi.zip", "digest": f"sha256:{ZIP_SHA}"},
            {"name": "omi.dmg", "digest": f"sha256:{DMG_SHA}"},
        ],
    }
    smoke = {
        "ok": True,
        "release_tag": TAG,
        "source_sha": SHA,
        "expected_channel": "beta",
        "bundle_id": "com.omi.computer-macos",
        "version": "0.12.99",
        "build": "12099",
        "team_id": "9536L8KLMP",
        "checks": sorted(REQUIRED_SMOKE_CHECKS),
        "notification_callback_canary": {
            "schema": 1,
            "event": "user-notifications-settings-callback-completed",
            "bundle_id": "com.omi.computer-macos",
            "main_actor": True,
            "authorization_status": 2,
            "validated": True,
        },
        "artifacts": [
            {"label": "sparkle_zip", "sha256": ZIP_SHA},
            {"label": "dmg", "sha256": DMG_SHA},
        ],
    }
    release_path = root / "release.json"
    smoke_path = root / "smoke.json"
    release_path.write_text(json.dumps(release), encoding="utf-8")
    smoke_path.write_text(json.dumps(smoke), encoding="utf-8")
    return argparse.Namespace(
        release_json=str(release_path),
        smoke_result=str(smoke_path),
        release_tag=TAG,
        latest_tag=TAG,
        tag_sha=SHA,
        checkout_sha=SHA,
        output=str(root / "result.json"),
    )


def expect_failure(args: argparse.Namespace, fragment: str) -> None:
    try:
        validate(args)
    except SystemExit as exc:
        assert fragment in str(exc), str(exc)
    else:
        raise AssertionError(f"expected failure containing {fragment!r}")


def main() -> int:
    # omi-test-quality: source-inspection -- static contract: qualification labels must match signed-smoke output.
    smoke_labels = set(re.findall(r'^\s*pass "([^"]+)"\s*$', SIGNED_SMOKE.read_text(encoding="utf-8"), re.MULTILINE))
    missing_labels = sorted(REQUIRED_SMOKE_CHECKS - smoke_labels)
    assert not missing_labels, f"qualification requires labels not emitted by signed smoke: {missing_labels}"

    with tempfile.TemporaryDirectory() as temp_dir:
        args = fixtures(Path(temp_dir))
        result = validate(args)
        assert result["passed"] is True
        assert result["artifact_digests"]["Omi.zip"] == ZIP_SHA

        smoke_path = Path(args.smoke_result)
        smoke = json.loads(smoke_path.read_text())
        callback_canary = smoke.pop("notification_callback_canary")
        smoke_path.write_text(json.dumps(smoke))
        expect_failure(args, "missing UserNotifications callback canary evidence")
        smoke["notification_callback_canary"] = callback_canary
        smoke_path.write_text(json.dumps(smoke))

        stale = argparse.Namespace(**{**vars(args), "latest_tag": "v0.13.0+13000-macos"})
        expect_failure(stale, "newest tag")

        smoke = json.loads(smoke_path.read_text())
        smoke["artifacts"][0]["sha256"] = "d" * 64
        smoke_path.write_text(json.dumps(smoke))
        expect_failure(args, "Omi.zip digest")

        smoke["artifacts"][0]["sha256"] = ZIP_SHA
        smoke["notification_callback_canary"]["validated"] = False
        smoke_path.write_text(json.dumps(smoke))
        expect_failure(args, "callback canary validated mismatch")

        smoke["notification_callback_canary"]["validated"] = True
        smoke["source_sha"] = "d" * 40
        smoke_path.write_text(json.dumps(smoke))
        expect_failure(args, "source SHA does not match the candidate tag")

    # Beta is a channel designation for the single production Omi identity.
    # A candidate that reintroduces a second app/package identity must fail closed.
    with tempfile.TemporaryDirectory() as temp_dir:
        args = fixtures(Path(temp_dir))
        release_path = Path(args.release_json)
        release = json.loads(release_path.read_text())
        release["assets"].append({"name": "Omi.Beta.zip", "digest": f"sha256:{ZIP_SHA}"})
        release_path.write_text(json.dumps(release), encoding="utf-8")
        expect_failure(args, "unexpected dual-identity desktop assets")

    test_codemagic_beta_smoke_produces_gate_required_canaries()

    print("automatic desktop beta candidate tests OK")


def test_codemagic_beta_smoke_produces_gate_required_canaries() -> None:
    """Codemagic must smoke exactly the single Omi artifact promoted through both channels."""
    codemagic = (Path(__file__).resolve().parents[2] / "codemagic.yaml").read_text(encoding="utf-8")
    smoke_step = codemagic.split("- name: Smoke signed desktop artifact", 1)[1]
    smoke_step = smoke_step.split("- name: ", 1)[0]
    production_branch = smoke_step.split("else", 1)[1]
    invocations = production_branch.split("scripts/smoke-signed-desktop-artifact.sh")
    assert len(invocations) == 2, "expected exactly one production signed-artifact smoke invocation"
    stable_invocation = invocations[1]

    evidence_flags = ["--launch", "--auth-storage-canary", "--notification-callback-canary", "--source-sha", "--tag"]
    for flag in evidence_flags:
        assert flag in stable_invocation, f"stable smoke invocation lost {flag}; update this contract test"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
