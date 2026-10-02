from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_harness import device_lease as dl
from dev_harness import mobile_session as ms

REPO_ROOT = Path(__file__).resolve().parents[3]


def _env(tmp_path: Path) -> dict[str, str]:
    return {"OMI_LOCAL_STATE_ROOT": str(tmp_path / "state")}


@pytest.fixture()
def env(tmp_path: Path) -> dict[str, str]:
    return _env(tmp_path)


def _register(env: dict, device_id: str = "TESTDEVICE0123", platform: str = "android") -> dict:
    return dl.register_device(
        REPO_ROOT,
        platform,
        device_id,
        label="Pixel test",
        os_version="15",
        confirm=True,
        env=env,
    )


def _dead(pid: int) -> bool:
    return False


def _live(pid: int) -> bool:
    return True


class TestRegistrationGate:
    def test_register_refuses_without_explicit_confirmation(self, tmp_path: Path, env: dict) -> None:
        with pytest.raises(dl.DeviceLeaseError, match="confirm-test-device"):
            dl.register_device(
                REPO_ROOT,
                "android",
                "TESTDEVICE0123",
                label="my personal phone",
                os_version="15",
                confirm=False,
                env=env,
            )
        # The personal device is not silently registered either.
        assert not (dl.registry_root(REPO_ROOT, env) / "android").exists()

    def test_acquire_refuses_unregistered_device(self, tmp_path: Path, env: dict) -> None:
        with pytest.raises(dl.DeviceLeaseError, match="no device qualification record"):
            dl.acquire(REPO_ROOT, "android", "UNKNOWNDEV01", purpose="test", env=env, process_exists=_dead)
        assert not (dl.devices_root(REPO_ROOT, env) / "android").exists()

    def test_registration_is_idempotent_and_deregister_refuses_while_leased(self, tmp_path: Path, env: dict) -> None:
        first = _register(env)
        again = _register(env)
        assert again["device_id"] == first["device_id"]
        dl.acquire(REPO_ROOT, "android", "TESTDEVICE0123", purpose="test", env=env, process_exists=_dead)
        with pytest.raises(dl.DeviceLeaseError, match="active lease"):
            dl.deregister_device(REPO_ROOT, "android", "TESTDEVICE0123", env=env)
        dl.release(REPO_ROOT, "android", "TESTDEVICE0123", env=env)
        removed = dl.deregister_device(REPO_ROOT, "android", "TESTDEVICE0123", env=env)
        assert removed["device_id"] == "TESTDEVICE0123"
        with pytest.raises(dl.DeviceLeaseError, match="no device qualification record"):
            dl.acquire(REPO_ROOT, "android", "TESTDEVICE0123", purpose="test", env=env, process_exists=_dead)


class TestExclusiveLease:
    def test_acquire_creates_exclusive_generation_1_lease(self, tmp_path: Path, env: dict) -> None:
        _register(env)
        lease = dl.acquire(REPO_ROOT, "android", "TESTDEVICE0123", purpose="sca-491", env=env, process_exists=_dead)
        assert lease["generation"] == 1
        assert lease["status"] == "leased"
        path = dl.devices_root(REPO_ROOT, env) / "android" / "TESTDEVICE0123.json"
        assert json.loads(path.read_text("utf-8"))["owner"]["pid"] == lease["owner"]["pid"]

    def test_live_foreign_lease_is_never_stolen_and_bounded_wait_times_out(self, tmp_path: Path, env: dict) -> None:
        _register(env)
        dl.acquire(REPO_ROOT, "android", "TESTDEVICE0123", purpose="other", env=env, process_exists=_dead)
        ticks = {"n": 0, "now": [0.0]}

        def clock() -> float:
            return ticks["now"][-1]

        def sleep(_: float) -> None:
            ticks["n"] += 1
            ticks["now"].append(ticks["now"][-1] + 0.05)

        with pytest.raises(dl.DeviceLeaseError, match="refusing to steal a live lease.*gave up after 0.2") as excinfo:
            dl.acquire(
                REPO_ROOT,
                "android",
                "TESTDEVICE0123",
                purpose="mine",
                wait_timeout_s=0.2,
                env=env,
                process_exists=_live,
                clock=clock,
                sleep=sleep,
            )
        assert ticks["n"] >= 2, "bounded acquisition must poll before refusing"
        assert "live" in str(excinfo.value)

    def test_release_then_reacquire_succeeds(self, tmp_path: Path, env: dict) -> None:
        _register(env)
        dl.acquire(REPO_ROOT, "android", "TESTDEVICE0123", purpose="a", env=env, process_exists=_dead)
        released = dl.release(REPO_ROOT, "android", "TESTDEVICE0123", env=env)
        assert released["status"] == "released"
        # Idempotent release.
        again = dl.release(REPO_ROOT, "android", "TESTDEVICE0123", env=env)
        assert again["status"] == "released"
        lease = dl.acquire(REPO_ROOT, "android", "TESTDEVICE0123", purpose="b", env=env, process_exists=_dead)
        assert lease["generation"] == 1, "fresh lease after clean release restarts at generation 1"

    def test_release_by_live_foreign_owner_is_refused(self, tmp_path: Path, env: dict) -> None:
        _register(env)
        lease = dl.acquire(REPO_ROOT, "android", "TESTDEVICE0123", purpose="owner", env=env, process_exists=_dead)
        assert lease["owner"]["pid"] != -1
        # Reforge the recorded owner as a live foreign pid: release must refuse.
        path = dl.devices_root(REPO_ROOT, env) / "android" / "TESTDEVICE0123.json"
        lease = json.loads(path.read_text("utf-8"))
        lease["owner"]["pid"] = 999997
        path.write_text(json.dumps(lease), "utf-8")
        with pytest.raises(dl.DeviceLeaseError, match="live pid"):
            dl.release(REPO_ROOT, "android", "TESTDEVICE0123", env=env, process_exists=_live)
        assert path.exists()

    def test_session_binding_requires_a_real_session_lease(self, tmp_path: Path, env: dict) -> None:
        _register(env)
        with pytest.raises(dl.DeviceLeaseError, match="no session lease"):
            dl.acquire(
                REPO_ROOT,
                "android",
                "TESTDEVICE0123",
                purpose="t",
                session_id="oms-nonexistent",
                env=env,
                process_exists=_dead,
            )
        session = ms.acquire(REPO_ROOT, env, name="bound", listeners=lambda port: ())
        lease = dl.acquire(
            REPO_ROOT,
            "android",
            "TESTDEVICE0123",
            purpose="t",
            session_id=session["session_id"],
            env=env,
            process_exists=_dead,
        )
        assert lease["session_id"] == session["session_id"]


class TestStaleOwnerSafety:
    def _write_lease(self, env: dict, owner: dict, generation: int = 1) -> Path:
        path = dl.devices_root(REPO_ROOT, env) / "android" / "TESTDEVICE0123.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        lease = {
            "schema_version": dl.DEVICE_LEASE_SCHEMA_VERSION,
            "platform": "android",
            "device_id": "TESTDEVICE0123",
            "status": "leased",
            "generation": generation,
            "recovered_count": 0,
            "owner": owner,
            "purpose": "crashed run",
            "session_id": None,
            "created_at": "2026-09-16T00:00:00Z",
            "heartbeat_at": "2026-09-16T00:00:00Z",
        }
        path.write_text(json.dumps(lease), "utf-8")
        return path

    def test_crashed_owner_is_recovered_with_generation_bump(self, tmp_path: Path, env: dict) -> None:
        _register(env)
        crashed = {"host": dl.owner_identity()["host"], "user": dl.owner_identity()["user"], "pid": 424242}
        self._write_lease(env, crashed)
        lease = dl.acquire(REPO_ROOT, "android", "TESTDEVICE0123", purpose="recovery", env=env, process_exists=_dead)
        assert lease["generation"] == 2, "stale takeover must bump the generation"
        assert lease["recovered_count"] == 1
        assert lease["owner"]["pid"] == dl.owner_identity()["pid"]

    def test_cross_host_lease_is_never_recovered_automatically(self, tmp_path: Path, env: dict) -> None:
        _register(env)
        self._write_lease(env, {"host": "other-mac", "user": dl.owner_identity()["user"], "pid": 424242})
        with pytest.raises(dl.DeviceLeaseError, match="cross-host takeover"):
            dl.acquire(REPO_ROOT, "android", "TESTDEVICE0123", purpose="t", env=env, process_exists=_dead)
        with pytest.raises(dl.DeviceLeaseError, match="not recoverable here"):
            dl.recover(REPO_ROOT, "android", "TESTDEVICE0123", env=env)

    def test_cross_user_lease_is_refused(self, tmp_path: Path, env: dict) -> None:
        _register(env)
        self._write_lease(env, {"host": dl.owner_identity()["host"], "user": "someone-else", "pid": 424242})
        with pytest.raises(dl.DeviceLeaseError, match="another user's"):
            dl.acquire(REPO_ROOT, "android", "TESTDEVICE0123", purpose="t", env=env, process_exists=_dead)

    def test_explicit_recover_refuses_live_owner_and_bumps_stale(self, tmp_path: Path, env: dict) -> None:
        _register(env)
        live = {"host": dl.owner_identity()["host"], "user": dl.owner_identity()["user"], "pid": 999999}
        self._write_lease(env, live, generation=7)
        with pytest.raises(dl.DeviceLeaseError, match="not recoverable here"):
            dl.recover(REPO_ROOT, "android", "TESTDEVICE0123", env=env, process_exists=_live)
        dead = {"host": dl.owner_identity()["host"], "user": dl.owner_identity()["user"], "pid": 424243}
        self._write_lease(env, dead, generation=7)
        recovered = dl.recover(REPO_ROOT, "android", "TESTDEVICE0123", env=env)
        assert recovered["generation"] == 8

    def test_concurrent_recovery_guard_admits_exactly_one(self, tmp_path: Path, env: dict) -> None:
        _register(env)
        crashed = {"host": dl.owner_identity()["host"], "user": dl.owner_identity()["user"], "pid": 424244}
        self._write_lease(env, crashed)
        guard = dl.devices_root(REPO_ROOT, env) / "android" / ("TESTDEVICE0123" + dl._RECOVERY_GUARD_SUFFIX)
        guard.mkdir(parents=True)
        try:
            with pytest.raises(dl.DeviceLeaseError, match="already in progress"):
                dl.acquire(REPO_ROOT, "android", "TESTDEVICE0123", purpose="t", env=env, process_exists=_dead)
        finally:
            guard.rmdir()
        lease = dl.acquire(REPO_ROOT, "android", "TESTDEVICE0123", purpose="t", env=env, process_exists=_dead)
        assert lease["generation"] == 2


class TestStatusAndHeartbeat:
    def test_status_reports_registry_and_lease_state(self, tmp_path: Path, env: dict) -> None:
        _register(env)
        report = dl.status(REPO_ROOT, env=env)
        entry = next(d for d in report["devices"] if d["device_id"] == "TESTDEVICE0123")
        assert entry["qualified"] is True and entry["leased"] is False
        dl.acquire(REPO_ROOT, "android", "TESTDEVICE0123", purpose="t", env=env, process_exists=_dead)
        report = dl.status(REPO_ROOT, platform="android", device_id="TESTDEVICE0123", env=env)
        entry = report["devices"][0]
        assert entry["leased"] is True
        assert entry["lease"]["generation"] == 1

    def test_heartbeat_refreshes_stamp_and_foreign_is_refused(self, tmp_path: Path, env: dict) -> None:
        _register(env)
        dl.acquire(REPO_ROOT, "android", "TESTDEVICE0123", purpose="t", env=env, process_exists=_dead)
        beat = dl.heartbeat(REPO_ROOT, "android", "TESTDEVICE0123", env=env)
        assert beat["heartbeat_at"]
        # Reforge the owner as live-foreign: heartbeat must refuse.
        path = dl.devices_root(REPO_ROOT, env) / "android" / "TESTDEVICE0123.json"
        lease = json.loads(path.read_text("utf-8"))
        lease["owner"]["pid"] = 999998
        path.write_text(json.dumps(lease), "utf-8")
        with pytest.raises(dl.DeviceLeaseError, match="live pid"):
            dl.heartbeat(REPO_ROOT, "android", "TESTDEVICE0123", env=env, process_exists=_live)
