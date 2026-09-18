from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_harness import mobile_doctor as md
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

    def test_port_number_claims_are_exclusive_across_the_offset_space(self, tmp_path: Path, env: dict) -> None:
        from itertools import combinations

        from dev_harness import config

        root = ms.sessions_root(REPO_ROOT, env)
        offsets = list(range(ms.PORT_OFFSET_MIN, ms.PORT_OFFSET_MAX + 1, ms.PORT_OFFSET_STEP))
        port_sets = {
            offset: set(config.harness_ports_from_env({config.PORT_OFFSET_ENV: str(offset)}).values())
            for offset in offsets
        }
        intersecting = [(left, right) for left, right in combinations(offsets, 2) if port_sets[left] & port_sets[right]]
        assert intersecting, "the configured offset space must include cross-role port collisions"
        for left, right in intersecting:
            first_ports = ms._claim_port_offset(
                root, f"oms-left-{left}", requested_offset=left, listeners=_no_listeners
            )[1]
            assert set(first_ports.values()) == port_sets[left]
            for port in port_sets[left]:
                assert (root / "ports" / f"port-{port}.json").is_file()
            with pytest.raises(ms.SessionError, match="already claimed"):
                ms._claim_port_offset(root, f"oms-right-{right}", requested_offset=right, listeners=_no_listeners)
            ms._release_port_offset(root, left, f"oms-left-{left}")
            for port in port_sets[left]:
                assert not (root / "ports" / f"port-{port}.json").exists()
            ms._claim_port_offset(root, f"oms-right-{right}", requested_offset=right, listeners=_no_listeners)
            ms._release_port_offset(root, right, f"oms-right-{right}")

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


def _android_sdk(tmp_path: Path, *, emulator: bool = True, sdkmanager: bool = True, image: bool = False) -> Path:
    home = tmp_path / "android-sdk"
    if emulator:
        (home / "emulator").mkdir(parents=True)
        (home / "emulator" / "emulator").write_text("x\n", encoding="utf-8")
    if sdkmanager:
        bin_dir = home / "cmdline-tools" / "latest" / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "sdkmanager").write_text("x\n", encoding="utf-8")
    if image:
        image_dir = home.joinpath(*md.PREFERRED_ANDROID_IMAGE_DIR)
        image_dir.mkdir(parents=True)
        (image_dir / "kernel-ranchu").write_text("k\n", encoding="utf-8")
    return home


class TestAndroidReady:
    def test_missing_emulator_binary_is_engine_absent(self, tmp_path: Path) -> None:
        home = _android_sdk(tmp_path, emulator=False, sdkmanager=True)
        ready, detail = ms.DeviceController(lambda _cmd: (0, "")).android_ready(str(home))
        assert ready is False
        assert "emulator engine missing" in detail

    def test_nonzero_inventory_without_an_image_is_undetermined_not_ready(self, tmp_path: Path) -> None:
        """Fails on origin/main: nonzero sdkmanager was reported as engine present."""
        home = _android_sdk(tmp_path)
        ready, detail = ms.DeviceController(lambda _cmd: (1, "WARNING: deprecated\n")).android_ready(str(home))
        assert ready is False
        assert "cannot determine" in detail
        assert "not a finding that the emulator engine is absent" in detail
        assert "engine present" not in detail
        assert "engine missing" not in detail
        assert "no Android system image installed" not in detail

    def test_exit_zero_slash_path_listing_is_ready(self, tmp_path: Path) -> None:
        """Fails on origin/main: cmdline-tools 23 slash paths missed startswith('system-images;')."""
        home = _android_sdk(tmp_path)
        listing = "  system-images/android-36/google_apis/arm64-v8a         7.0.0             Google APIs ARM 64 v8a System Image\n"

        def runner(command: Sequence[str]) -> tuple[int, str]:
            assert "--list_installed" in command
            return 0, listing

        ready, detail = ms.DeviceController(runner).android_ready(str(home))
        assert ready is True
        assert "system-images;android-36;google_apis;arm64-v8a" in detail

    def test_noisy_nonzero_sdkmanager_with_slash_path_is_ready(self, tmp_path: Path) -> None:
        home = _android_sdk(tmp_path)
        listing = (
            "WARNING: The SDK Manager CLI tool (sdkmanager) is deprecated.\n"
            "  system-images/android-36/google_apis/arm64-v8a\n"
        )
        ready, detail = ms.DeviceController(lambda _cmd: (1, listing)).android_ready(str(home))
        assert ready is True
        assert "system-images;android-36;google_apis;arm64-v8a" in detail

    def test_on_disk_image_is_ready_when_inventory_fails(self, tmp_path: Path) -> None:
        home = _android_sdk(tmp_path, image=True)
        ready, detail = ms.DeviceController(lambda _cmd: (1, "java.lang.RuntimeException\n")).android_ready(str(home))
        assert ready is True
        assert "system-images;android-36;google_apis;arm64-v8a" in detail

    def test_successful_empty_inventory_is_image_absent(self, tmp_path: Path) -> None:
        home = _android_sdk(tmp_path)
        ready, detail = ms.DeviceController(lambda _cmd: (0, "platform-tools\nplatforms;android-36\n")).android_ready(
            str(home)
        )
        assert ready is False
        assert "no Android system image installed" in detail
        assert "cannot determine" not in detail
        assert "engine missing" not in detail


def test_device_controller_default_runner_missing_binary_is_127(monkeypatch: pytest.MonkeyPatch) -> None:
    """xcrun absent (host without Xcode) must not escape detach(): stop/release
    stay idempotent and attach fails closed as a SessionError."""

    def missing(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError(2, "No such file or directory", "xcrun")

    monkeypatch.setattr(ms.subprocess, "run", missing)
    code, out = ms.DeviceController._default_runner(["xcrun", "simctl", "list"])
    assert code == 127
    assert "xcrun" in out


def test_device_doctor_cli_accepts_json_after_the_subcommand() -> None:
    """Siblings take `--json` after the verb (`doctor --json`); device doctor
    used to accept it only as `device --json doctor`."""
    parser = ms.build_parser()
    after = parser.parse_args(["device", "doctor", "--json"])
    before = parser.parse_args(["device", "--json", "doctor"])
    assert after.json is True and before.json is True
    assert after.device_command == "doctor" and before.device_command == "doctor"


def test_device_doctor_stripped_path_is_classified_not_a_traceback() -> None:
    """Acceptance: `mobile-session device doctor` with adb off PATH exits a
    classified result (no traceback) so iOS checks still run."""
    env = {key: value for key, value in os.environ.items() if key not in {"ANDROID_HOME", "ANDROID_SDK_ROOT"}}
    env["PATH"] = "/usr/bin:/bin"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "dev_harness.mobile_session", "device", "--json", "doctor"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    combined = result.stdout + result.stderr
    assert "Traceback" not in combined, combined[-2000:]
    assert result.returncode == 2
    report = json.loads(result.stdout)
    statuses = {check["status"] for check in report["checks"]}
    assert statuses & {"agent-remediable", "operator-action-needed"}
    android = next(c for c in report["checks"] if c["check"].startswith("android."))
    assert android["status"] in {"agent-remediable", "operator-action-needed"}
    assert any(c["check"].startswith("ios.") for c in report["checks"]), "iOS checks must still run after adb fails"


def test_device_heartbeat_cli_is_wired(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """PHYSICAL_DEVICES.md documents `device heartbeat`; the CLI must accept it."""

    monkeypatch.setattr("dev_harness.device_lease.heartbeat", lambda *a, **k: {"ok": True})
    code = ms.main(["device", "heartbeat", "--platform", "ios", "--device-id", "00008101-TEST"])
    assert code == 0
