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
        beta_smoke_result="",
        release_tag=TAG,
        latest_tag=TAG,
        tag_sha=SHA,
        checkout_sha=SHA,
        output=str(root / "result.json"),
    )


BETA_ZIP_SHA = "e" * 64
BETA_DMG_SHA = "f" * 64


def beta_fixtures(root: Path) -> argparse.Namespace:
    """Fixtures for a release that ships the side-by-side Omi Beta assets."""
    args = fixtures(root)
    release_path = Path(args.release_json)
    release = json.loads(release_path.read_text())
    release["assets"] += [
        {"name": "Omi.Beta.zip", "digest": f"sha256:{BETA_ZIP_SHA}"},
        {"name": "omi-beta.dmg", "digest": f"sha256:{BETA_DMG_SHA}"},
    ]
    release_path.write_text(json.dumps(release), encoding="utf-8")

    beta_smoke = {
        "ok": True,
        "release_tag": TAG,
        "expected_channel": "beta",
        "bundle_id": "com.omi.computer-macos.beta",
        "version": "0.12.99",
        "build": "12099",
        "team_id": "9536L8KLMP",
        "checks": sorted(REQUIRED_SMOKE_CHECKS),
        "notification_callback_canary": {
            "schema": 1,
            "event": "user-notifications-settings-callback-completed",
            "bundle_id": "com.omi.computer-macos.beta",
            "main_actor": True,
            "authorization_status": 2,
            "validated": True,
        },
        "artifacts": [
            {"label": "sparkle_zip", "sha256": BETA_ZIP_SHA},
            {"label": "dmg", "sha256": BETA_DMG_SHA},
        ],
    }
    beta_smoke_path = root / "smoke-beta.json"
    beta_smoke_path.write_text(json.dumps(beta_smoke), encoding="utf-8")
    args.beta_smoke_result = str(beta_smoke_path)
    return args


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

    # Releases shipping the side-by-side Omi Beta assets: the beta artifact must
    # satisfy the same smoke contract as stable, under its own bundle id.
    with tempfile.TemporaryDirectory() as temp_dir:
        args = beta_fixtures(Path(temp_dir))
        result = validate(args)
        assert result["passed"] is True
        assert result["artifact_digests"]["Omi.Beta.zip"] == BETA_ZIP_SHA
        assert result["artifact_digests"]["omi-beta.dmg"] == BETA_DMG_SHA

        missing = argparse.Namespace(**{**vars(args), "beta_smoke_result": ""})
        expect_failure(missing, "no beta smoke result was provided")

        beta_smoke_path = Path(args.beta_smoke_result)
        original = beta_smoke_path.read_text()

        beta_smoke = json.loads(original)
        beta_smoke["bundle_id"] = "com.omi.computer-macos"
        beta_smoke_path.write_text(json.dumps(beta_smoke))
        expect_failure(args, "beta smoke result bundle_id mismatch")

        beta_smoke = json.loads(original)
        beta_smoke["ok"] = False
        beta_smoke_path.write_text(json.dumps(beta_smoke))
        expect_failure(args, "beta smoke result ok mismatch")

        beta_smoke = json.loads(original)
        beta_smoke["checks"] = beta_smoke["checks"][1:]
        beta_smoke_path.write_text(json.dumps(beta_smoke))
        expect_failure(args, "beta smoke result is missing required checks")

        beta_smoke = json.loads(original)
        beta_smoke["artifacts"][0]["sha256"] = "d" * 64
        beta_smoke_path.write_text(json.dumps(beta_smoke))
        expect_failure(args, "Omi.Beta.zip digest")

        # The canary must have run inside the beta artifact itself — evidence
        # missing entirely, or recorded under the stable bundle id, both fail.
        beta_smoke = json.loads(original)
        del beta_smoke["notification_callback_canary"]
        beta_smoke_path.write_text(json.dumps(beta_smoke))
        expect_failure(args, "beta smoke result is missing UserNotifications callback canary")

        beta_smoke = json.loads(original)
        beta_smoke["notification_callback_canary"]["bundle_id"] = "com.omi.computer-macos"
        beta_smoke_path.write_text(json.dumps(beta_smoke))
        expect_failure(args, "beta smoke UserNotifications callback canary bundle_id mismatch")

    test_codemagic_beta_smoke_produces_gate_required_canaries()

    print("automatic desktop beta candidate tests OK")


def test_codemagic_beta_smoke_produces_gate_required_canaries() -> None:
    """The beta smoke invocation in codemagic.yaml must produce every piece of
    evidence this gate requires of the beta smoke result. A stable-only flag
    addition (e.g. the notification callback canary) that skips the beta
    invocation would otherwise fail-close the first dual-identity release."""
    codemagic = (Path(__file__).resolve().parents[2] / "codemagic.yaml").read_text(encoding="utf-8")
    smoke_step = codemagic.split("- name: Smoke signed desktop artifact", 1)[1]
    smoke_step = smoke_step.split("- name: ", 1)[0]
    production_branch = smoke_step.split("else", 1)[1]
    invocations = production_branch.split("scripts/smoke-signed-desktop-artifact.sh")
    assert len(invocations) >= 3, "expected stable and beta smoke invocations in the production branch"
    stable_invocation, beta_invocation = invocations[1], invocations[2]

    evidence_flags = ["--launch", "--auth-storage-canary", "--notification-callback-canary", "--tag"]
    for flag in evidence_flags:
        assert flag in stable_invocation, f"stable smoke invocation lost {flag}; update this contract test"
        assert flag in beta_invocation, (
            f"beta smoke invocation is missing {flag}, but the candidate gate validates the "
            "evidence it produces — the first dual-identity release would fail qualification"
        )
    assert "--expected-bundle-id" in beta_invocation, "beta smoke must assert the beta bundle id"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
