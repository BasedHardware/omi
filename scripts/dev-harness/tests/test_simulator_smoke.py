"""Hermetic V2 simulator-smoke orchestration. No real flutter/Xcode."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dev_harness import mobile_doctor as md, mobile_verify as mv, session_evidence as se, simulator_smoke as smoke

REPO_ROOT = Path(__file__).resolve().parents[3]
FAKE = Path(__file__).with_name("fake_sim_flutter.py")


class FakeChild(smoke.FlutterChild):
    def __init__(self, spec, mode="ok"):
        self.spec = spec
        fake = smoke.LaunchSpec(
            argv=(
                sys.executable,
                "-u",
                str(FAKE),
                mode,
                str(spec.cwd / "transcript.jsonl"),
                "app-smoke",
                spec.device_id,
            ),
            cwd=spec.cwd,
            env={},
            device_id=spec.device_id,
        )
        super().__init__(fake)


def _ready_doctor(**kwargs):
    return SimpleNamespace(overall="ready", checks=(), as_dict=lambda: {"overall": "ready"})


def _lease(tmp_path: Path) -> dict:
    apk = tmp_path / "bundle.app"
    apk.mkdir()
    (apk / "Info.plist").write_bytes(b"ios")
    return {
        "session_id": "oms-v2smoke",
        "platform": "ios-simulator",
        "flavor": "dev",
        "profile": "local_dev",
        "status": "seeded",
        "generation": 1,
        "app_id": "com.friend-app-with-wearable.ios12.development",
        "device": {"kind": "simulator", "udid": "SIM-1", "owner": "session"},
        "ports": {"backend": 8100, "auth": 9199, "firestore": 8185, "redis": 6479},
        "source_at_acquire": {"git_sha": "a" * 40, "dirty_digest": "clean"},
        "default_auth_uid": "fixture-user",
        "fixture_version": "v1",
    }


def _engine(tmp_path: Path, *, mode="ok", start_raises=None, **overrides):
    lease = _lease(tmp_path)
    released = []
    codegen_argv = []
    engine_state = {}

    def acquire(**kwargs):
        return dict(lease)

    def start(session_id, **kwargs):
        if start_raises:
            raise start_raises
        return dict(lease)

    def seed(session_id):
        return {"uid": "fixture-user"}

    def release(session_id):
        released.append(session_id)
        return {"released": True}

    def evidence(session_id, **kwargs):
        shot = tmp_path / "screenshots" / "smoke.png"
        bundle = tmp_path / "bundle.app"
        document = se.build_evidence(
            session_id=session_id,
            source={"git_sha": "a" * 40, "dirty_digest": "clean", "repo": "BasedHardware/omi"},
            target={
                "platform": "ios-simulator",
                "app_id": lease["app_id"],
                "flavor": "dev",
                "profile": "local_dev",
            },
            endpoints={
                "api_base_url": "http://127.0.0.1:8100/",
                "auth_emulator_host": "127.0.0.1:9199",
                "firestore_emulator_host": "127.0.0.1:8185",
                "egress_policy": "loopback-only",
            },
            fixtures={"fixture_version": "v1"},
            runners={"flutter": "3.44.5"},
            status={"state": "running"},
            timestamps={"created_at": "2026-09-17T00:00:00Z"},
            artifact={
                "kind": "ios-app-bundle",
                "sha256": se.file_sha256(bundle),
                "git_sha": "a" * 40,
                "path": "bundle.app",
            },
            artifacts={"screenshots": ["screenshots/smoke.png"]},
        )
        (tmp_path / "evidence.json").write_text(json.dumps(document), encoding="utf-8")
        return document

    def screenshot(device, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x89PNG\r\n\x1a\nsmoke")

    def codegen(app_dir: Path, repo_root: Path):
        codegen_argv.append("flutter pub run build_runner build --build-filter=lib/env/*")

    def factory(spec):
        engine_state["spec"] = spec
        return FakeChild(spec, mode=mode)

    kwargs = dict(
        doctor=_ready_doctor,
        acquire=acquire,
        start=start,
        seed=seed,
        release=release,
        evidence=evidence,
        factory=factory,
        screenshot=screenshot,
        codegen=codegen,
        uvicorn_ok=lambda root: True,
        startup_timeout_s=412,
        env={"OMI_LOCAL_STATE_ROOT": str(tmp_path / "state")},
    )
    kwargs.update(overrides)
    engine = smoke.SimulatorSmoke(tmp_path, **kwargs)
    engine._released = released
    engine._codegen_argv = codegen_argv
    engine._spec_holder = engine_state
    (tmp_path / "app").mkdir(exist_ok=True)
    bundle = tmp_path / "app" / "build" / "ios" / "iphonesimulator" / "Runner.app"
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / "Info.plist").write_bytes(b"ios")
    (tmp_path / "Makefile").write_text("setup-backend:\n\t@true\n", encoding="utf-8")
    return engine


def test_smoke_without_ready_infrastructure_blocks(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    class BlockedReport:
        overall = "blocked"
        checks = ()

        def as_dict(self) -> dict[str, str]:
            return {"overall": "blocked"}

    monkeypatch.setattr(mv.mobile_doctor, "run_doctor", lambda *a, **k: BlockedReport())
    monkeypatch.setattr(smoke, "uvicorn_importable", lambda root: True)
    args = argparse.Namespace(json=True, session=None, evidence_dir=None, journey_timeout=900, platform="ios-simulator")
    assert mv.cmd_smoke(REPO_ROOT, args) == mv.EXIT_BLOCKED
    capsys.readouterr()


def test_android_is_blocked_with_doctor_message(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    sdk = md.CheckResult(
        "android-sdk",
        md.AGENT_REMEDIABLE,
        "ANDROID_HOME/ANDROID_SDK_ROOT not set to an existing SDK",
        "export ANDROID_HOME=<sdk> ANDROID_SDK_ROOT=$ANDROID_HOME (scripts/dev-harness doctor does not guess a location)",
        (md.LANE_ANDROID,),
    )

    class Report:
        overall = "blocked"
        checks = (sdk,)

        def as_dict(self):
            return {"overall": "blocked", "checks": [sdk.as_dict()]}

    monkeypatch.setattr(smoke.mobile_doctor, "run_doctor", lambda *a, **k: Report())
    args = argparse.Namespace(json=True, session=None, evidence_dir=None, journey_timeout=900, platform="android")
    assert smoke.run_smoke(tmp_path, args) == mv.EXIT_BLOCKED
    out = capsys.readouterr()
    payload = json.loads(out.out)
    assert "ANDROID_HOME" in out.out + out.err
    assert "ANDROID_HOME" in payload["remedy"]
    assert payload["classification"] == md.AGENT_REMEDIABLE


def test_missing_lane_backend_prints_exact_remedy(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text("setup-backend:\n\t@true\n", encoding="utf-8")
    assert smoke.lane_backend_target_present(tmp_path) is False
    remedy = smoke.session_backend_remedy(tmp_path)
    assert "make lane-backend" in remedy
    assert "14349" in remedy
    engine = _engine(tmp_path, uvicorn_ok=lambda root: False)
    with pytest.raises(smoke.SmokeBlocked) as err:
        engine.run()
    assert "14349" in err.value.remedy
    assert engine._released == []


def test_uvicorn_block_releases_nothing_before_acquire(tmp_path: Path) -> None:
    engine = _engine(tmp_path, uvicorn_ok=lambda root: False)
    with pytest.raises(smoke.SmokeBlocked):
        engine.run()
    assert engine._released == []


def test_fake_flutter_signed_out_ready_and_screenshot(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    result = engine.run()
    assert result["outcome"] == "passed"
    assert result["controls"]["state"]["profile"] == "local_dev"
    assert result["controls"]["state"]["readiness"]["signedIn"] is False
    assert result["controls"]["state"]["readiness"]["routed"] is True
    assert result["controls"]["state"]["readiness"]["captureIdle"] is True
    assert Path(result["screenshot"]).is_file()
    assert result["screenshot_sha256"] == se.file_sha256(Path(result["screenshot"]))
    assert se.validate_evidence(result["evidence"]) == []
    assert result["evidence"]["artifacts"]["screenshots"] == ["screenshots/smoke.png"]
    assert result["artifact"] and result["artifact"].endswith("Runner.app")
    assert engine._released == ["oms-v2smoke"]
    assert engine._codegen_argv
    assert all("--delete-conflicting-outputs" not in item for item in engine._codegen_argv)
    spec = engine._spec_holder["spec"]
    assert "--dart-define=OMI_APP_PROFILE=local_dev" in spec.argv
    assert "--dart-define=OMI_DEV_CONTROLS=1" in spec.argv
    assert spec.device_id == "SIM-1"
    assert engine._timings["app_started_s"] >= 0


def test_signed_in_is_blocked_not_worked_around(tmp_path: Path) -> None:
    engine = _engine(tmp_path, mode="signed-in")
    with pytest.raises(smoke.SmokeBlocked, match="signedIn=false"):
        engine.run()
    assert engine._released == ["oms-v2smoke"]


def test_start_failure_still_releases(tmp_path: Path) -> None:
    engine = _engine(tmp_path, start_raises=smoke.SmokeBlocked("backend down", remedy="make lane-backend"))
    with pytest.raises(smoke.SmokeBlocked, match="backend down"):
        engine.run()
    assert engine._released == ["oms-v2smoke"]


def test_startup_timeout_cannot_go_below_measured_cold_start(tmp_path: Path) -> None:
    with pytest.raises(smoke.SmokeBlocked, match="412"):
        smoke.SimulatorSmoke(tmp_path, startup_timeout_s=200)


def test_codegen_refuses_delete_conflicting_outputs(tmp_path: Path) -> None:
    app = tmp_path / "app"
    (app / "lib" / "env").mkdir(parents=True)
    recorded = {}

    def runner(argv, cwd, timeout):
        recorded["argv"] = list(argv)
        if any("build_runner" in str(part) for part in argv):
            (app / "lib" / "env" / "dev_env.g.dart").write_text("// generated\n", encoding="utf-8")
            (app / "lib" / "env" / "prod_env.g.dart").write_text("// generated\n", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, "", "")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(smoke.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0] if a else [], 0, "", ""))
        smoke.ensure_generated_env(app, tmp_path, runner=runner)
    assert "--delete-conflicting-outputs" not in recorded["argv"]
    assert "--build-filter=lib/env/*" in recorded["argv"]


def test_cmd_smoke_uses_injected_engine_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    engine = _engine(tmp_path)

    def fake_run(repo_root, args):
        result = engine.run()
        print(json.dumps({"outcome": result["outcome"], "session_id": result["session_id"]}))
        return 0

    monkeypatch.setattr(smoke, "run_smoke", fake_run)
    args = argparse.Namespace(json=True, session=None, evidence_dir=None, journey_timeout=900, platform="ios-simulator")
    assert mv.cmd_smoke(tmp_path, args) == 0
    assert json.loads(capsys.readouterr().out)["outcome"] == "passed"
