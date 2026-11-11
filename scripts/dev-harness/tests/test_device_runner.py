from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Sequence

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
                if "--json-output" in command and response[0] == 0:
                    Path(command[command.index("--json-output") + 1]).write_text(response[1])
                    return 0, "human-readable output is deliberately ignored"
                return response
        if "--json-output" in command:
            Path(command[command.index("--json-output") + 1]).write_text(ios_inventory())
        return 0, ""


def ios_inventory(*devices: dict) -> str:
    return json.dumps({"result": {"devices": list(devices)}})


def ios_device(udid="00008110-000123456789ABCD", *, modern=False, **hardware):
    groups = {
        "hardwareProperties": {
            "udid": udid,
            "platform": "iOS",
            "reality": "physical",
            "deviceType": "iPhone",
            "marketingName": "iPhone 15 Pro Max",
            **hardware,
        },
        "deviceProperties": {"name": "Test Mac phone", "bootState": "booted"},
        "connectionProperties": {"pairingState": "paired", "transportType": "wired", "tunnelState": "disconnected"},
    }
    if modern:
        return {"properties": dict(zip(("hardware", "state", "connection"), groups.values()))}
    return groups


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
        runner = FakeRunner({"list devices": (0, ios_inventory())})
        report = dr.device_doctor(REPO_ROOT, ios=dr.IosTooling(runner), env=env)
        check = report["checks"][0]
        assert check["status"] == "operator-action-needed"
        assert "Developer Mode" in check["remedy"]

    @pytest.mark.parametrize("modern", [False, True])
    def test_ios_only_physical_paired_phones_and_table_names_do_not_matter(self, env: dict, modern: bool) -> None:
        phone = ios_device(modern=modern)
        simulator = ios_device("SIMULATED-1234", modern=modern, reality="simulated")
        watch = ios_device("WATCH-1234", modern=modern, platform="watchOS", deviceType="appleWatch")
        mac = ios_device("MAC-1234", modern=modern, platform="macOS", deviceType="mac")
        unknown = ios_device("UNKNOWN-1234", modern=modern, reality=None)
        runner = FakeRunner({"list devices": (0, ios_inventory(watch, simulator, phone, mac, unknown))})
        report = dr.device_doctor(REPO_ROOT, ios=dr.IosTooling(runner), env=env)
        assert [c["check"] for c in report["checks"]] == ["ios.device.00008110-000123456789ABCD"]
        assert "--json-output" in runner.commands[0]

    @pytest.mark.parametrize(
        "payload", ["not json", "{}", '{"result":{"devices":{}}}', '{"result":{"devices":[null]}}']
    )
    def test_ios_malformed_inventory_is_tooling_failure_not_no_devices(self, env: dict, payload: str) -> None:
        runner = FakeRunner({"list devices": (0, payload)})
        report = dr.device_doctor(REPO_ROOT, ios=dr.IosTooling(runner), env=env)
        assert report["checks"][0]["check"] == "ios.tooling"
        assert report["checks"][0]["status"] == "agent-remediable"

    def test_ios_unpaired_or_shutdown_devices_are_not_candidates(self) -> None:
        unpaired = ios_device()
        unpaired["connectionProperties"]["pairingState"] = "unpaired"
        shutdown = ios_device("SHUTDOWN-1234")
        shutdown["deviceProperties"]["bootState"] = "shutdown"
        runner = FakeRunner({"list devices": (0, ios_inventory(unpaired, shutdown))})
        assert dr.IosTooling(runner).connected() == []

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

    def test_pending_xcode_first_launch_is_operator_action_not_agent_remediable(self, env: dict) -> None:
        """Privileged install/license work is an operator action per contract.

        The CLI default runner diagnoses a pending Xcode first launch inside an
        xcrun timeout with the shared marker; device_doctor must classify that
        as operator-action-needed, not the blanket agent-remediable remedy.
        """

        def hung(_command: Sequence[str]) -> tuple[int, str]:
            raise dr.DeviceRunnerError(
                "devicectl list devices timed out after 180s. "
                f"{dr.XCODE_FIRST_LAUNCH_PENDING_MARKER}; completing it requires"
                " admin rights (operator action)."
            )

        report = dr.device_doctor(REPO_ROOT, ios=dr.IosTooling(hung), env=env)
        ios = report["checks"][0]
        assert ios["check"] == "ios.tooling"
        assert ios["status"] == "operator-action-needed"
        assert "sudo xcodebuild -runFirstLaunch" in ios["remedy"]

    def test_real_xcrun_timeout_diagnosis_flows_through_doctor_as_operator_action(
        self, env: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End-to-end: the runner's actual timeout diagnosis drives the doctor.

        An xcrun hang whose first-launch probe reports pending produces the
        shared marker via ms._default_device_runner; IosTooling surfaces it as
        a DeviceRunnerError; device_doctor must classify it as
        operator-action-needed. This pins the wording coupling between the two
        modules: editing the diagnosis or the marker fails here.
        """

        class Probe:
            returncode = 1  # first launch pending

        def run(command: Sequence[str], **_kwargs: object):
            if command[0] == "xcrun":
                raise subprocess.TimeoutExpired(cmd=list(command), timeout=25)
            if command[0] == "xcodebuild":
                return Probe()
            raise AssertionError(f"unexpected command: {command}")

        monkeypatch.setattr(ms.subprocess, "run", run)
        report = dr.device_doctor(
            REPO_ROOT,
            ios=dr.IosTooling(ms._default_device_runner),
            env=env,
        )
        ios = report["checks"][0]
        assert ios["check"] == "ios.tooling"
        assert ios["status"] == "operator-action-needed"
        assert dr.XCODE_FIRST_LAUNCH_PENDING_MARKER in ios["detail"]
        assert "sudo xcodebuild -runFirstLaunch" in ios["remedy"]

    def test_real_xcrun_timeout_with_first_launch_complete_keeps_timeout_remedy(
        self, env: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End-to-end: a completed first launch must not yield install-Xcode.

        Xcode was just probed successfully, so the doctor JSON must carry the
        timeout-specific retry/restart step instead of telling consumers to
        install Xcode (Codex P2 on the f487873 doctor wiring).
        """

        class Probe:
            returncode = 0  # first launch complete

        def run(command: Sequence[str], **_kwargs: object):
            if command[0] == "xcrun":
                raise subprocess.TimeoutExpired(cmd=list(command), timeout=25)
            if command[0] == "xcodebuild":
                return Probe()
            raise AssertionError(f"unexpected command: {command}")

        monkeypatch.setattr(ms.subprocess, "run", run)
        report = dr.device_doctor(
            REPO_ROOT,
            ios=dr.IosTooling(ms._default_device_runner),
            env=env,
        )
        ios = report["checks"][0]
        assert ios["check"] == "ios.tooling"
        assert ios["status"] == "agent-remediable"
        assert dr.XCODE_FIRST_LAUNCH_COMPLETE_MARKER in ios["detail"]
        assert "install Xcode" not in ios["remedy"]
        assert "retry" in ios["remedy"]

    def test_real_xcrun_timeout_with_hung_probe_keeps_timeout_remedy(
        self, env: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End-to-end: the status probe itself hanging is tooling evidence.

        xcodebuild started and hung, so the doctor JSON must carry the
        retry/restart remedy — never a fresh Xcode install (Codex P2 on
        d190f49's probe-unknown fallthrough).
        """

        def run(command: Sequence[str], **_kwargs: object):
            if command[0] == "xcrun":
                raise subprocess.TimeoutExpired(cmd=list(command), timeout=25)
            if command[0] == "xcodebuild":
                raise subprocess.TimeoutExpired(cmd=list(command), timeout=10)
            raise AssertionError(f"unexpected command: {command}")

        monkeypatch.setattr(ms.subprocess, "run", run)
        report = dr.device_doctor(
            REPO_ROOT,
            ios=dr.IosTooling(ms._default_device_runner),
            env=env,
        )
        ios = report["checks"][0]
        assert ios["check"] == "ios.tooling"
        assert ios["status"] == "agent-remediable"
        assert dr.XCODE_FIRST_LAUNCH_PROBE_TIMEOUT_MARKER in ios["detail"]
        assert "install Xcode" not in ios["remedy"]
        assert "retry" in ios["remedy"]

    def test_real_adb_timeout_keeps_server_remedy_not_reinstall(
        self, env: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End-to-end: an adb discovery timeout must not yield install advice.

        adb is installed and running; the doctor JSON must carry the
        server/USB retry step instead of reinstalling platform-tools
        (Codex P2 on the f487873 Android remedy).
        """

        def run(command: Sequence[str], **_kwargs: object):
            if command[0] == "adb":
                raise subprocess.TimeoutExpired(cmd=list(command), timeout=25)
            raise AssertionError(f"unexpected command: {command}")

        monkeypatch.setattr(ms.subprocess, "run", run)
        report = dr.device_doctor(
            REPO_ROOT,
            android=dr.AndroidTooling(ms._default_device_runner),
            env=env,
        )
        android = report["checks"][0]
        assert android["check"] == "android.tooling"
        assert android["status"] == "agent-remediable"
        assert dr.ADB_TIMEOUT_MARKER in android["detail"]
        assert "install Android SDK platform-tools" not in android["remedy"]
        assert "adb kill-server" in android["remedy"]


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
        runner = FakeRunner({"list devices": (0, ios_inventory(ios_device(udid)))})
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
