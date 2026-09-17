from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_harness import device_lease as dl
from dev_harness import device_runner as dr
from dev_harness import mobile_session as ms

REPO_ROOT = Path(__file__).resolve().parents[3]


def _env(tmp_path: Path) -> dict[str, str]:
    return {"OMI_LOCAL_STATE_ROOT": str(tmp_path / "state")}


@pytest.fixture()
def env(tmp_path: Path) -> dict[str, str]:
    return _env(tmp_path)


class FakeRunner:
    """Records commands; answers from a scripted map of substrings."""

    def __init__(self, responses: dict[str, tuple[int, str]] | None = None) -> None:
        self.commands: list[list[str]] = []
        self.responses = responses or {}

    def __call__(self, command: list[str] | tuple[str, ...]) -> tuple[int, str]:
        self.commands.append(list(command))
        joined = " ".join(command)
        for needle, response in self.responses.items():
            if needle in joined:
                return response
        return 0, ""


def _register_and_lease(env: dict, platform: str = "android", device_id: str = "TESTPHONE01") -> dict:
    dl.register_device(REPO_ROOT, platform, device_id, label="test", os_version="15", confirm=True, env=env)
    return dl.acquire(
        REPO_ROOT, platform, device_id, purpose="qualification", env=env, process_exists=lambda pid: False
    )


def _running_session(env: dict, name: str = "devicerun", platform: str = "android") -> dict:
    session = ms.acquire(REPO_ROOT, env, name=name, platform_name=platform, listeners=lambda port: ())
    directory = ms.session_dir(REPO_ROOT, session["session_id"], env)
    lease = json.loads((directory / "lease.json").read_text("utf-8"))
    lease["status"] = "running"
    (directory / "lease.json").write_text(json.dumps(lease), "utf-8")
    return session


class TestDoctor:
    def test_android_no_device_is_operator_action_with_exact_step(self, tmp_path: Path, env: dict) -> None:
        runner = FakeRunner({"devices -l": (0, "List of devices attached\n\n")})
        report = dr.device_doctor(REPO_ROOT, android=dr.AndroidTooling(runner), env=env)
        check = report["checks"][0]
        assert check["status"] == "operator-action-needed"
        assert "USB debugging" in check["remedy"]

    def test_android_unregistered_connected_device_names_registration_step(self, tmp_path: Path, env: dict) -> None:
        runner = FakeRunner({"devices -l": (0, "List of devices attached\nTESTPHONE01 device usb:1\n")})
        report = dr.device_doctor(REPO_ROOT, android=dr.AndroidTooling(runner), env=env)
        check = report["checks"][0]
        assert check["status"] == "operator-action-needed"
        assert "register" in check["remedy"] and "--confirm-test-device" in check["remedy"]

    def test_android_registered_device_is_ready(self, tmp_path: Path, env: dict) -> None:
        _register_and_lease(env)
        dl.release(REPO_ROOT, "android", "TESTPHONE01", env=env)
        runner = FakeRunner({"devices -l": (0, "List of devices attached\nTESTPHONE01 device usb:1\n")})
        report = dr.device_doctor(REPO_ROOT, android=dr.AndroidTooling(runner), env=env)
        assert report["checks"][0]["status"] == "ready"

    def test_ios_no_device_is_operator_action(self, tmp_path: Path, env: dict) -> None:
        runner = FakeRunner({"list devices": (0, "No devices found.")})
        report = dr.device_doctor(REPO_ROOT, ios=dr.IosTooling(runner), env=env)
        check = report["checks"][0]
        assert check["status"] == "operator-action-needed"
        assert "Developer Mode" in check["remedy"]

    def test_ios_dashed_separator_row_is_not_a_device(self, tmp_path: Path, env: dict) -> None:
        runner = FakeRunner(
            {
                "list devices": (
                    0,
                    "Name           Hostname   Identifier                                    State               Model\n"
                    "----------------------------   --------   -------------------------------------------   ------------------\n"
                    "David's iPhone 15                         00008130-00060D893AE8001C (UDID)              available (paired)\n",
                )
            }
        )
        report = dr.device_doctor(REPO_ROOT, ios=dr.IosTooling(runner), env=env)
        assert [c["check"] for c in report["checks"]] == ["ios.device.00008130-00060D893AE8001C"]

    def test_missing_adb_binary_is_agent_remediable_not_a_traceback(self, tmp_path: Path, env: dict) -> None:
        """A runner that raises FileNotFoundError (raw subprocess) must not
        escape device_doctor — #14305 caught it only at the CLI default runner."""

        def missing(_command: list[str] | tuple[str, ...]) -> tuple[int, str]:
            raise FileNotFoundError(2, "No such file or directory", "adb")

        report = dr.device_doctor(
            REPO_ROOT, android=dr.AndroidTooling(missing), ios=dr.IosTooling(FakeRunner()), env=env
        )
        android = next(c for c in report["checks"] if c["check"] == "android.tooling")
        assert android["status"] == "agent-remediable"
        assert "adb" in android["detail"]
        ios = next(c for c in report["checks"] if c["check"].startswith("ios."))
        assert ios["check"] == "ios.device.attached"

    def test_missing_xcrun_binary_is_agent_remediable_and_android_still_runs(self, tmp_path: Path, env: dict) -> None:
        def missing(_command: list[str] | tuple[str, ...]) -> tuple[int, str]:
            raise FileNotFoundError(2, "No such file or directory", "xcrun")

        android = FakeRunner({"devices -l": (0, "List of devices attached\n\n")})
        report = dr.device_doctor(REPO_ROOT, android=dr.AndroidTooling(android), ios=dr.IosTooling(missing), env=env)
        assert report["checks"][0]["check"] == "android.device.attached"
        ios = next(c for c in report["checks"] if c["check"] == "ios.tooling")
        assert ios["status"] == "agent-remediable"
        assert "xcrun" in ios["detail"] or "devicectl" in ios["detail"]


class TestRun:
    def _artifact(self, tmp_path: Path) -> Path:
        artifact = tmp_path / "app-dev-debug.apk"
        artifact.write_bytes(b"fake apk bytes")
        return artifact

    def test_run_executes_install_reverse_permissions_launch_and_writes_evidence(
        self, tmp_path: Path, env: dict
    ) -> None:
        _register_and_lease(env)
        session = _running_session(env)
        artifact = self._artifact(tmp_path)
        runner = FakeRunner(
            {
                "devices -l": (0, "List of devices attached\nTESTPHONE01 device usb:1\n"),
                "getprop ro.product.model": (0, "Pixel 8\n"),
                "getprop ro.build.version.release": (0, "15\n"),
                "getprop ro.build.version.sdk": (0, "36\n"),
            }
        )
        receipt = dr.run(
            REPO_ROOT,
            session["session_id"],
            "android",
            "TESTPHONE01",
            artifact=artifact,
            env=env,
            android=dr.AndroidTooling(runner),
        )
        joined = [" ".join(c) for c in runner.commands]
        assert any("install -r -t" in c and str(artifact) in c for c in joined), "artifact must be installed"
        backend_port = session["ports"]["backend"]
        assert any(f"reverse tcp:{backend_port}" in c for c in joined), "session ports must be reversed to loopback"
        assert any("pm revoke com.friend.ios.dev android.permission.RECORD_AUDIO" in c for c in joined)
        assert any(
            "am start -n com.friend.ios.dev/.MainActivity" in c for c in joined
        ), "launch must be untethered am start"
        assert any("pm grant com.friend.ios.dev android.permission.RECORD_AUDIO" in c for c in joined)
        statuses = {step["name"]: step["status"] for step in receipt["steps"]}
        assert statuses["install"] == "ok" and statuses["launch"] == "ok"
        assert statuses["permission-deny"] == "ok" and statuses["permission-grant"] == "ok"
        assert receipt["artifact"]["sha256"] == dr.session_evidence.file_sha256(artifact)
        assert receipt["physical_acceptance"] == "pending-user-run-evidence"
        assert receipt["operator_steps"], "OS-level cases must be listed as operator steps, not faked"
        path = ms.sessions_root(REPO_ROOT, env) / session["session_id"] / "device-run.json"
        assert json.loads(path.read_text("utf-8"))["schema_version"] == dr.DEVICE_RUN_EVIDENCE_SCHEMA

    def test_run_refuses_foreign_app_id(self, tmp_path: Path, env: dict) -> None:
        _register_and_lease(env)
        session = _running_session(env)
        directory = ms.session_dir(REPO_ROOT, session["session_id"], env)
        lease = json.loads((directory / "lease.json").read_text("utf-8"))
        lease["app_id"] = "com.someone.personal.app"
        (directory / "lease.json").write_text(json.dumps(lease), "utf-8")
        with pytest.raises(dr.DeviceRunnerError, match="foreign app id"):
            dr.run(
                REPO_ROOT,
                session["session_id"],
                "android",
                "TESTPHONE01",
                artifact=self._artifact(tmp_path),
                env=env,
                android=dr.AndroidTooling(FakeRunner()),
            )

    def test_run_requires_device_lease_and_running_session(self, tmp_path: Path, env: dict) -> None:
        dl.register_device(REPO_ROOT, "android", "TESTPHONE01", label="t", os_version="15", confirm=True, env=env)
        session = _running_session(env)
        with pytest.raises(dr.DeviceRunnerError, match="device lease required"):
            dr.run(
                REPO_ROOT,
                session["session_id"],
                "android",
                "TESTPHONE01",
                artifact=self._artifact(tmp_path),
                env=env,
                android=dr.AndroidTooling(FakeRunner()),
            )
        _register_and_lease(env)
        idle = ms.acquire(REPO_ROOT, env, name="idle", listeners=lambda port: ())
        with pytest.raises(dr.DeviceRunnerError, match="not running"):
            dr.run(
                REPO_ROOT,
                idle["session_id"],
                "android",
                "TESTPHONE01",
                artifact=self._artifact(tmp_path),
                env=env,
                android=dr.AndroidTooling(FakeRunner()),
            )

    def test_run_refuses_lease_bound_to_other_session(self, tmp_path: Path, env: dict) -> None:
        _register_and_lease(env)
        other = _running_session(env)
        session = _running_session(env, name="other")
        runner = FakeRunner({"devices -l": (0, "List of devices attached\nTESTPHONE01 device usb:1\n")})
        dl.release(REPO_ROOT, "android", "TESTPHONE01", env=env)
        dl.acquire(
            REPO_ROOT,
            "android",
            "TESTPHONE01",
            purpose="q",
            session_id=other["session_id"],
            env=env,
            process_exists=lambda pid: False,
        )
        with pytest.raises(dr.DeviceRunnerError, match="bound to session"):
            dr.run(
                REPO_ROOT,
                session["session_id"],
                "android",
                "TESTPHONE01",
                artifact=self._artifact(tmp_path),
                env=env,
                android=dr.AndroidTooling(runner),
            )

    def test_run_writes_failed_evidence_when_install_fails(self, tmp_path: Path, env: dict) -> None:
        _register_and_lease(env)
        session = _running_session(env)
        runner = FakeRunner(
            {
                "devices -l": (0, "List of devices attached\nTESTPHONE01 device usb:1\n"),
                "install": (1, "INSTALL_FAILED_UPDATE_INCOMPATIBLE"),
            }
        )
        with pytest.raises(dr.DeviceRunnerError, match="INSTALL_FAILED"):
            dr.run(
                REPO_ROOT,
                session["session_id"],
                "android",
                "TESTPHONE01",
                artifact=self._artifact(tmp_path),
                env=env,
                android=dr.AndroidTooling(runner),
            )
        path = ms.sessions_root(REPO_ROOT, env) / session["session_id"] / "device-run.json"
        receipt = json.loads(path.read_text("utf-8"))
        assert receipt["steps"][-1]["status"] == "failed"
        assert "INSTALL_FAILED" in receipt["steps"][-1]["detail"]

    def test_ios_run_installs_and_launches_with_operator_permission_steps(self, tmp_path: Path, env: dict) -> None:
        udid = "00008110-000123456789ABCD"
        dl.register_device(REPO_ROOT, "ios", udid, label="iPhone", os_version="26", confirm=True, env=env)
        dl.acquire(REPO_ROOT, "ios", udid, purpose="q", env=env, process_exists=lambda pid: False)
        session = _running_session(env, platform="ios-simulator")
        artifact = tmp_path / "Runner.dev.ipa"
        artifact.write_bytes(b"fake ipa")
        runner = FakeRunner({"list devices": (0, f"{udid} iPhone 16 Pro\n")})
        receipt = dr.run(
            REPO_ROOT,
            session["session_id"],
            "ios",
            udid,
            artifact=artifact,
            env=env,
            ios=dr.IosTooling(runner),
        )
        joined = [" ".join(c) for c in runner.commands]
        assert any("device install app" in c and udid in c for c in joined)
        assert any("process launch" in c for c in joined)
        assert any("permission" in step.lower() for step in receipt["operator_steps"])
