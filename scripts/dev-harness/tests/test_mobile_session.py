from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_harness import mobile_session as ms
from dev_harness import session_evidence as se

REPO_ROOT = Path(__file__).resolve().parents[3]


def _env(tmp_path: Path) -> dict[str, str]:
    return {"OMI_LOCAL_STATE_ROOT": str(tmp_path / "state")}


def _no_listeners(port: int) -> tuple[int, ...]:
    return ()


@pytest.fixture()
def env(tmp_path: Path) -> dict[str, str]:
    return _env(tmp_path)


class TestAcquire:
    def test_acquire_creates_lease_claim_and_sentinel(self, tmp_path: Path, env: dict) -> None:
        lease = ms.acquire(REPO_ROOT, env, name="alpha", listeners=_no_listeners)
        directory = ms.session_dir(REPO_ROOT, lease["session_id"], env)
        assert (directory / "lease.json").is_file()
        assert (directory / ".omi-dev-harness-owned.json").is_file()
        claim = ms.sessions_root(REPO_ROOT, env) / "ports" / f"{lease['port_offset']}.json"
        assert json.loads(claim.read_text("utf-8"))["session_id"] == lease["session_id"]
        assert lease["status"] == "creating"
        assert lease["fixture_version"] == "v1"
        assert lease["ports"]["backend"] == 8000 + lease["port_offset"]

    def test_two_sessions_get_disjoint_ports_and_instances(self, tmp_path: Path, env: dict) -> None:
        first = ms.acquire(REPO_ROOT, env, name="one", listeners=_no_listeners)
        second = ms.acquire(REPO_ROOT, env, name="two", listeners=_no_listeners)
        assert first["port_offset"] != second["port_offset"]
        assert set(first["ports"].values()).isdisjoint(second["ports"].values())
        assert first["harness_instance"] != second["harness_instance"]

    def test_duplicate_name_is_refused_with_owner_hint(self, tmp_path: Path, env: dict) -> None:
        ms.acquire(REPO_ROOT, env, name="dup", listeners=_no_listeners)
        with pytest.raises(ms.SessionError, match="already exists"):
            ms.acquire(REPO_ROOT, env, name="dup", listeners=_no_listeners)

    def test_failed_acquire_leaves_no_half_state(self, tmp_path: Path, env: dict) -> None:
        root = ms.sessions_root(REPO_ROOT, env)
        claim_dir = root / "ports"
        claim_dir.mkdir(parents=True)
        (claim_dir / "100.json").write_text("{}", "utf-8")
        with pytest.raises(ms.SessionError, match="already claimed"):
            ms.acquire(REPO_ROOT, env, name="doomed", offset=100, listeners=_no_listeners)
        assert not (root / "oms-doomed" / "lease.json").exists()

    def test_invalid_offset_is_rejected(self, tmp_path: Path, env: dict) -> None:
        with pytest.raises(ms.SessionError, match="multiple of 100"):
            ms.acquire(REPO_ROOT, env, name="odd", offset=123, listeners=_no_listeners)
        with pytest.raises(ms.SessionError, match="outside"):
            ms.acquire(REPO_ROOT, env, name="low", offset=50, listeners=_no_listeners)

    def test_foreign_port_listener_is_refused_not_killed(self, tmp_path: Path, env: dict) -> None:
        sleeper = subprocess.Popen(["sleep", "30"])
        time.sleep(0.2)
        try:
            with pytest.raises(ms.SessionError, match="refused, not killed") as excinfo:
                ms.acquire(
                    REPO_ROOT,
                    env,
                    name="hopper",
                    offset=100,
                    listeners=lambda port: (sleeper.pid,) if port == 8100 else (),
                )
            assert str(sleeper.pid) in str(excinfo.value)
        finally:
            sleeper.kill()
            sleeper.wait()

    def test_auto_offset_skips_a_port_held_by_a_foreign_process(self, tmp_path: Path, env: dict) -> None:
        lease = ms.acquire(REPO_ROOT, env, name="skipper", listeners=lambda port: (424242,) if port == 8100 else ())
        assert lease["port_offset"] != 100


class TestOwnership:
    def _lease_path(self, env: dict, name: str) -> Path:
        return ms.sessions_root(REPO_ROOT, env) / f"oms-{name}" / "lease.json"

    def test_dead_owner_is_recoverable_with_generation_bump(self, tmp_path: Path, env: dict) -> None:
        lease = ms.acquire(REPO_ROOT, env, name="crashy", listeners=_no_listeners)
        path = self._lease_path(env, "crashy")
        data = json.loads(path.read_text("utf-8"))
        data["owner"]["pid"] = 999999  # provably not running
        path.write_text(json.dumps(data), "utf-8")

        # Same host + same user: an orphaned session continues under its lease,
        # so the seed proceeds to the backend liveness check and fails there.
        with pytest.raises(ms.SessionError, match="unreachable"):
            ms.seed(REPO_ROOT, lease["session_id"], env, probe=lambda url: (False, "connection refused"))

        recovered = ms.recover(REPO_ROOT, lease["session_id"], env)
        assert recovered["generation"] == 2
        assert recovered["owner"]["pid"] == __import__("os").getpid()

    def test_live_foreign_owner_is_never_reclaimed(self, tmp_path: Path, env: dict) -> None:
        lease = ms.acquire(REPO_ROOT, env, name="busy", listeners=_no_listeners)
        sleeper = subprocess.Popen(["sleep", "30"])
        time.sleep(0.2)
        try:
            path = self._lease_path(env, "busy")
            data = json.loads(path.read_text("utf-8"))
            data["owner"]["pid"] = sleeper.pid
            path.write_text(json.dumps(data), "utf-8")
            with pytest.raises(ms.SessionError, match="live foreign session"):
                ms.recover(REPO_ROOT, lease["session_id"], env)
        finally:
            sleeper.kill()
            sleeper.wait()

    def test_another_local_users_session_is_refused(self, tmp_path: Path, env: dict) -> None:
        lease = ms.acquire(REPO_ROOT, env, name="theirs", listeners=_no_listeners)
        path = self._lease_path(env, "theirs")
        data = json.loads(path.read_text("utf-8"))
        data["owner"]["user"] = "someone-else"
        path.write_text(json.dumps(data), "utf-8")
        with pytest.raises(ms.SessionError, match="another user's session"):
            ms.release(REPO_ROOT, lease["session_id"], env, stop_services=lambda *a: {})

    def test_foreign_host_takeover_is_refused(self, tmp_path: Path, env: dict) -> None:
        lease = ms.acquire(REPO_ROOT, env, name="remote", listeners=_no_listeners)
        path = self._lease_path(env, "remote")
        data = json.loads(path.read_text("utf-8"))
        data["owner"]["host"] = "some-other-mac.local"
        path.write_text(json.dumps(data), "utf-8")
        with pytest.raises(ms.SessionError, match="cross-host"):
            ms.recover(REPO_ROOT, lease["session_id"], env)


class TestSeedResetStop:
    def test_seed_requires_a_live_backend_and_blocks_the_lease(self, tmp_path: Path, env: dict) -> None:
        lease = ms.acquire(REPO_ROOT, env, name="seedless", listeners=_no_listeners)
        with pytest.raises(ms.SessionError, match="unreachable"):
            ms.seed(REPO_ROOT, lease["session_id"], env, probe=lambda url: (False, "connection refused"))
        stopped = json.loads((ms.session_dir(REPO_ROOT, lease["session_id"], env) / "lease.json").read_text("utf-8"))
        assert stopped["status"] == "blocked"
        assert "unreachable" in stopped["blocked_reason"]

    def test_seed_writes_a_credential_free_receipt(self, tmp_path: Path, env: dict) -> None:
        lease = ms.acquire(REPO_ROOT, env, name="seedy", listeners=_no_listeners)

        def post(url: str, form: dict) -> dict:
            return {"custom_token": "secret-minted-token", "uid": form["uid"], "provider": "local_dev"}

        receipt = ms.seed(REPO_ROOT, lease["session_id"], env, probe=lambda url: (True, "HTTP 200"), post=post)
        assert "secret-minted-token" not in json.dumps(receipt)
        stored = json.loads((ms.session_dir(REPO_ROOT, lease["session_id"], env) / "seed.json").read_text("utf-8"))
        assert "secret-minted-token" not in json.dumps(stored)
        assert stored["uid"] == "omi-fixture-v1-user-1"

    def test_reset_clears_only_this_session_and_is_idempotent(self, tmp_path: Path, env: dict) -> None:
        lease = ms.acquire(REPO_ROOT, env, name="resetty", listeners=_no_listeners)
        other = ms.acquire(REPO_ROOT, env, name="keeper", listeners=_no_listeners)
        directory = ms.session_dir(REPO_ROOT, lease["session_id"], env)
        (directory / "seed.json").write_text("{}", "utf-8")

        def fake_reset(namespace) -> int:
            assert namespace is not None
            return 0

        first = ms.reset(REPO_ROOT, lease["session_id"], env, harness_reset=fake_reset)
        second = ms.reset(REPO_ROOT, lease["session_id"], env, harness_reset=fake_reset)
        assert first["status"] == second["status"] == "reset"
        assert not (directory / "seed.json").exists()
        # The other session's lease is untouched.
        keeper = json.loads((ms.session_dir(REPO_ROOT, other["session_id"], env) / "lease.json").read_text("utf-8"))
        assert keeper["status"] == "creating"

    def test_stop_shuts_down_a_session_owned_simulator(
        self, tmp_path: Path, env: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lease = ms.acquire(REPO_ROOT, env, name="stoppy", platform_name="ios-simulator", listeners=_no_listeners)
        monkeypatch.setattr("dev_harness.cli.cmd_down", lambda namespace: 0)
        calls: list[tuple[str, ...]] = []

        class FakeDevices:
            def detach(self, platform_name: str, device_id: str) -> None:
                calls.append((platform_name, device_id))

        directory = ms.session_dir(REPO_ROOT, lease["session_id"], env)
        data = json.loads((directory / "lease.json").read_text("utf-8"))
        data["device"] = {"kind": "simulator", "udid": "AAA-BBB-CCC", "label": "iPhone", "owner": "session"}
        (directory / "lease.json").write_text(json.dumps(data), "utf-8")

        stopped = ms.stop(REPO_ROOT, lease["session_id"], env, devices=FakeDevices())
        assert stopped["status"] == "stopped"
        assert calls == [("ios-simulator", "AAA-BBB-CCC")]
        # Idempotent: stopping again does not fail or re-signal the device.
        ms.stop(REPO_ROOT, lease["session_id"], env, devices=FakeDevices())
        assert calls == [("ios-simulator", "AAA-BBB-CCC")]


class TestStart:
    def test_start_android_fails_closed_when_the_lane_is_not_ready(self, tmp_path: Path, env: dict) -> None:
        lease = ms.acquire(REPO_ROOT, env, name="dry", platform_name="android", listeners=_no_listeners)

        class NotReady:
            def android_ready(self, home: str) -> tuple[bool, str]:
                return False, "emulator engine missing"

        with pytest.raises(ms.SessionError, match="doctor"):
            ms.start(REPO_ROOT, lease["session_id"], env, devices=NotReady())
        stored = json.loads((ms.session_dir(REPO_ROOT, lease["session_id"], env) / "lease.json").read_text("utf-8"))
        assert stored["status"] == "blocked"

    def test_start_runs_harness_up_under_the_session_instance(
        self, tmp_path: Path, env: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lease = ms.acquire(REPO_ROOT, env, name="uppy", platform_name="ios-simulator", listeners=_no_listeners)
        seen: dict[str, str] = {}

        def fake_up(namespace) -> int:
            seen["instance"] = __import__("os").environ["OMI_LOCAL_INSTANCE"]
            seen["offset"] = __import__("os").environ["OMI_HARNESS_PORT_OFFSET"]
            seen["provider_mode"] = __import__("os").environ["PROVIDER_MODE"]
            return 0

        monkeypatch.setattr("dev_harness.cli.cmd_up", fake_up)

        class FakeDevices:
            def attach_ios_simulator(self, sid: str, device_type: str, runtime: str) -> tuple[str, str]:
                return "DEADBEEF-1234", "iPhone 17 Pro"

            def android_ready(self, home: str) -> tuple[bool, str]:
                return True, "ready"

            def detach(self, platform: str, device: str) -> None:
                pass

        started = ms.start(REPO_ROOT, lease["session_id"], env, devices=FakeDevices())
        assert started["status"] == "running"
        assert seen["instance"] == lease["harness_instance"]
        assert seen["offset"] == str(lease["port_offset"])
        assert seen["provider_mode"] == "offline"
        assert started["device"]["udid"] == "DEADBEEF-1234"

    def test_start_json_keeps_cmd_up_logs_off_stdout(
        self, tmp_path: Path, env: dict, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        lease = ms.acquire(REPO_ROOT, env, name="jsonup", platform_name="ios-simulator", listeners=_no_listeners)

        def fake_up(namespace) -> int:
            print("cmd_up: starting services")
            return 0

        monkeypatch.setattr("dev_harness.cli.cmd_up", fake_up)

        class FakeDevices:
            def attach_ios_simulator(self, sid: str, device_type: str, runtime: str) -> tuple[str, str]:
                return "DEADBEEF-1234", "iPhone 17 Pro"

            def android_ready(self, home: str) -> tuple[bool, str]:
                return True, "ready"

            def detach(self, platform: str, device: str) -> None:
                pass

        started = ms.start(REPO_ROOT, lease["session_id"], env, devices=FakeDevices(), json_stdout=True)
        assert started["status"] == "running"
        captured = capsys.readouterr()
        assert "cmd_up: starting services" in captured.err
        assert "cmd_up: starting services" not in captured.out

    def test_start_json_cli_stdout_is_pure_json(
        self, tmp_path: Path, env: dict, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        lease = ms.acquire(REPO_ROOT, env, name="jsoncli", listeners=_no_listeners)

        def fake_up(namespace) -> int:
            print("cmd_up: starting services")
            return 0

        monkeypatch.setattr("dev_harness.cli.cmd_up", fake_up)
        monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", env["OMI_LOCAL_STATE_ROOT"])
        monkeypatch.chdir(REPO_ROOT)
        assert ms.main(["start", lease["session_id"], "--json", "--no-device"]) == 0
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["session_id"] == lease["session_id"]
        assert payload["status"] == "running"
        assert "cmd_up: starting services" in captured.err


class TestEvidence:
    def test_ready_requires_an_artifact(self, tmp_path: Path, env: dict) -> None:
        lease = ms.acquire(REPO_ROOT, env, name="ev", listeners=_no_listeners)
        with pytest.raises(se.EvidenceError, match="artifact is required"):
            ms.evidence(REPO_ROOT, lease["session_id"], env, state="ready")

    def test_ready_binds_the_built_artifact(self, tmp_path: Path, env: dict) -> None:
        lease = ms.acquire(REPO_ROOT, env, name="ev2", listeners=_no_listeners)
        apk = tmp_path / "app-dev-debug.apk"
        apk.write_bytes(b"fake apk bytes")
        document = ms.evidence(REPO_ROOT, lease["session_id"], env, state="ready", artifact_path=apk)
        assert document["artifact"]["kind"] == "apk"
        assert document["artifact"]["sha256"] == se.file_sha256(apk)
        # Round-trips through the strict validator on read-back.
        path = ms.session_dir(REPO_ROOT, lease["session_id"], env) / "evidence.json"
        assert se.read_evidence(path)["session_id"] == lease["session_id"]

    def test_ready_binds_an_ios_app_bundle_directory(self, tmp_path: Path, env: dict) -> None:
        lease = ms.acquire(REPO_ROOT, env, name="iosapp", platform_name="ios-simulator", listeners=_no_listeners)
        bundle = tmp_path / "Runner.app"
        bundle.mkdir()
        (bundle / "Info.plist").write_bytes(b"ios-bundle")
        document = ms.evidence(REPO_ROOT, lease["session_id"], env, state="ready", artifact_path=bundle)
        assert document["artifact"]["kind"] == "ios-app-bundle"
        assert document["artifact"]["sha256"] == se.file_sha256(bundle)
        path = ms.session_dir(REPO_ROOT, lease["session_id"], env) / "evidence.json"
        assert se.validate_evidence(se.read_evidence(path)) == []

    def test_stale_source_cannot_report_ready(self, tmp_path: Path, env: dict, monkeypatch: pytest.MonkeyPatch) -> None:
        lease = ms.acquire(REPO_ROOT, env, name="stale", listeners=_no_listeners)
        apk = tmp_path / "app.apk"
        apk.write_bytes(b"x")

        def moved_source(repo_root: Path) -> dict[str, str]:
            identity = dict(lease["source_at_acquire"])
            identity["git_sha"] = "f" * 40
            return identity

        monkeypatch.setattr(se, "source_identity", moved_source)
        with pytest.raises(se.EvidenceError, match="source moved since acquire"):
            ms.evidence(REPO_ROOT, lease["session_id"], env, state="ready", artifact_path=apk)

    def test_endpoints_are_loopback_and_offset_derived(self, tmp_path: Path, env: dict) -> None:
        lease = ms.acquire(REPO_ROOT, env, name="ports", offset=200, listeners=_no_listeners)
        document = ms.evidence(REPO_ROOT, lease["session_id"], env)
        assert document["endpoints"]["api_base_url"] == "http://127.0.0.1:8200/"
        assert document["endpoints"]["auth_emulator_host"] == "127.0.0.1:9299"
        assert document["endpoints"]["egress_policy"] == "loopback-only"


class TestRelease:
    def test_release_is_idempotent_and_frees_the_port_claim(self, tmp_path: Path, env: dict) -> None:
        lease = ms.acquire(REPO_ROOT, env, name="gone", listeners=_no_listeners)
        root = ms.sessions_root(REPO_ROOT, env)
        claim = root / "ports" / f"{lease['port_offset']}.json"
        assert claim.exists()
        first = ms.release(REPO_ROOT, lease["session_id"], env, stop_services=lambda *a: {})
        second = ms.release(REPO_ROOT, lease["session_id"], env, stop_services=lambda *a: {})
        assert first["released"] and not first["already_absent"]
        assert second["already_absent"]
        assert not claim.exists()
        assert not (root / lease["session_id"]).exists()

    def test_release_refuses_a_claim_owned_by_another_session(self, tmp_path: Path, env: dict) -> None:
        lease = ms.acquire(REPO_ROOT, env, name="victim", offset=300, listeners=_no_listeners)
        root = ms.sessions_root(REPO_ROOT, env)
        claim = root / "ports" / "300.json"
        data = json.loads(claim.read_text("utf-8"))
        data["session_id"] = "oms-someone-else"
        claim.write_text(json.dumps(data), "utf-8")
        with pytest.raises(ms.SessionError, match="claimed by session"):
            ms.release(REPO_ROOT, lease["session_id"], env, stop_services=lambda *a: {})


class TestListAndCLI:
    def test_list_reports_leases(self, tmp_path: Path, env: dict) -> None:
        ms.acquire(REPO_ROOT, env, name="listed", listeners=_no_listeners)
        sessions = ms.list_sessions(REPO_ROOT, env)
        assert [s["session_id"] for s in sessions] == ["oms-listed"]

    def test_acquire_accepts_ios_as_ios_simulator_alias(self, tmp_path: Path, env: dict) -> None:
        lease = ms.acquire(REPO_ROOT, env, name="iosalias", platform_name="ios", listeners=_no_listeners)
        assert lease["platform"] == "ios-simulator"
        assert lease["app_id"] == ms.DEFAULT_APP_IDS["ios-simulator"]

    def test_acquire_rejects_unknown_platform_naming_valid_values(self, tmp_path: Path, env: dict) -> None:
        with pytest.raises(ms.SessionError, match="ios-simulator"):
            ms.acquire(REPO_ROOT, env, name="badplat", platform_name="iphone", listeners=_no_listeners)

    def test_cli_platform_aliases_round_trip(self) -> None:
        doctor = ms.build_parser().parse_args(["doctor", "--platform", "ios-simulator"])
        assert doctor.platform == ["ios"]
        acquire = ms.build_parser().parse_args(["acquire", "--platform", "ios"])
        assert acquire.platform == "ios-simulator"

    def test_main_doctor_exit_codes_follow_the_report(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class Blocked:
            overall = "blocked"
            checks = ()

            def as_dict(self) -> dict:
                return {"overall": "blocked", "checks": []}

        monkeypatch.setattr("dev_harness.mobile_doctor.run_doctor", lambda *a, **k: Blocked())
        assert ms.main(["doctor", "--json"]) == 2


def test_default_device_runner_missing_binary_is_127_not_a_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    """adb/xcrun absent must become exit 127 + message so `device doctor` and
    `device run` classify it as a remediable failure instead of crashing."""

    def missing(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError(2, "No such file or directory", "adb")

    monkeypatch.setattr(ms.subprocess, "run", missing)
    code, out = ms._default_device_runner(["adb", "devices"])
    assert code == 127
    assert "adb" in out


def test_device_controller_default_runner_missing_binary_is_127(monkeypatch: pytest.MonkeyPatch) -> None:
    """xcrun absent (host without Xcode) must not escape detach(): stop/release
    stay idempotent and attach fails closed as a SessionError."""

    def missing(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError(2, "No such file or directory", "xcrun")

    monkeypatch.setattr(ms.subprocess, "run", missing)
    code, out = ms.DeviceController._default_runner(["xcrun", "simctl", "list"])
    assert code == 127
    assert "xcrun" in out


def test_device_heartbeat_cli_is_wired(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """PHYSICAL_DEVICES.md documents `device heartbeat`; the CLI must accept it."""

    monkeypatch.setattr("dev_harness.device_lease.heartbeat", lambda *a, **k: {"ok": True})
    code = ms.main(["device", "heartbeat", "--platform", "ios", "--device-id", "00008101-TEST"])
    assert code == 0
