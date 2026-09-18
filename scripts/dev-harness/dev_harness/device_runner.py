"""Device-runner adapter for the C5 physical qualification lane (SCA-491).

Wires leased, registered test devices into the canonical mobile session
surface. It consumes the C1 session manifest (``lease.json``: ports, fixture,
app identity) and drives the device through narrow, injectable tooling
shims (``adb`` / ``xcrun devicectl``) — never through the Flutter debug
session, because a debug Marionette connection does not survive backgrounding
and proves nothing about untethered launch.

Every mutating step requires an active device lease owned by the caller
(``device_lease``). The runner never factory-resets, wipes, or enrolls
anything: permission toggles are the only device-state mutations, and only
for the harness app id. Steps that genuinely need a human (iOS TCC prompts,
hardware switches, wearable buttons) are surfaced as ``operator`` steps in
the plan, not silently automated.

All tooling is injected (``runner: Callable[[Sequence[str]], tuple[int, str]]``)
so every behavior here is unit-proven with fake devices before any hardware
is touched.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import device_lease, session_evidence
from .mobile_session import _load_lease as _load_session_lease
from .mobile_session import session_dir, sessions_root

DEVICE_RUN_EVIDENCE_SCHEMA = "device-run-evidence/v1"
Runner = Callable[[Sequence[str]], tuple[int, str]]

ANDROID_HARNESS_APP_IDS = frozenset(
    {
        "com.friend.ios.dev",  # dev flavor
        "com.friend.ios",  # prod flavor (qualification uses dev; listed for refusal clarity)
    }
)
IOS_HARNESS_BUNDLE_PREFIX = "com.friend-app-with-wearable"

# Permission toggles the runner may flip for the harness app only. iOS TCC
# cannot be granted from the CLI: deny->grant there is an operator step.
ANDROID_TOGGLE_PERMISSIONS = (
    "android.permission.RECORD_AUDIO",
    "android.permission.BLUETOOTH_CONNECT",
    "android.permission.BLUETOOTH_SCAN",
)


class DeviceRunnerError(RuntimeError):
    """Refusal/blocked device-runner operation (exit code 2 at the CLI)."""


@dataclass
class Step:
    name: str
    status: str  # ok | failed | skipped | operator
    detail: str = ""
    at: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "detail": self.detail, "at": self.at}


@dataclass
class RunPlan:
    """A qualification run plan: automatable steps plus operator steps."""

    session_id: str
    platform: str
    device_id: str
    artifact: Path
    steps: list[Step] = field(default_factory=list)
    operator_steps: list[str] = field(default_factory=list)

    def record(self, name: str, status: str, detail: str = "") -> Step:
        step = Step(name=name, status=status, detail=detail, at=session_evidence.utc_now())
        self.steps.append(step)
        return step


class AndroidTooling:
    """``adb`` shim. Injectable; the default shells out to the SDK binary."""

    def __init__(self, runner: Runner, adb: str = "adb") -> None:
        self._runner = runner
        self._adb = adb

    def _run(self, *args: str, ok: tuple[int, ...] = (0,)) -> str:
        try:
            code, out = self._runner([self._adb, *args])
        except OSError as exc:
            raise DeviceRunnerError(f"adb not available: {exc}") from exc
        if code not in ok:
            raise DeviceRunnerError(f"adb {' '.join(args)} failed (exit {code}): {out.strip()[:400]}")
        return out

    def connected(self) -> list[dict[str, str]]:
        out = self._run("devices", "-l")
        devices: list[dict[str, str]] = []
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append({"device_id": parts[0], "transport": "usb", "raw": line})
        return devices

    def shell(self, device_id: str, command: str) -> str:
        return self._run("-s", device_id, "shell", command)

    def install(self, device_id: str, artifact: Path) -> None:
        self._run("-s", device_id, "install", "-r", "-t", str(artifact))

    def reverse(self, device_id: str, device_port: int, host_port: int) -> None:
        self._run("-s", device_id, "reverse", f"tcp:{device_port}", f"tcp:{host_port}")

    def launch(self, device_id: str, app_id: str) -> None:
        self.shell(device_id, f"am start -n {app_id}/.MainActivity")

    def grant(self, device_id: str, app_id: str, permission: str) -> None:
        self._run("-s", device_id, "pm", "grant", app_id, permission, ok=(0, 1))

    def revoke(self, device_id: str, app_id: str, permission: str) -> None:
        self._run("-s", device_id, "pm", "revoke", app_id, permission, ok=(0, 1))

    def logs(self, device_id: str) -> str:
        return self._run("-s", device_id, "logcat", "-d", "-v", "time")

    def device_info(self, device_id: str) -> dict[str, str]:
        def prop(name: str) -> str:
            return self.shell(device_id, f"getprop {name}").strip()

        return {
            "model": prop("ro.product.model"),
            "os_version": prop("ro.build.version.release"),
            "sdk": prop("ro.build.version.sdk"),
        }


class IosTooling:
    """``xcrun devicectl`` shim. Injectable; CLI cannot flip TCC permissions."""

    def __init__(self, runner: Runner) -> None:
        self._runner = runner

    def _run(self, *args: str) -> str:
        try:
            code, out = self._runner(["xcrun", "devicectl", *args])
        except OSError as exc:
            raise DeviceRunnerError(f"xcrun/devicectl not available: {exc}") from exc
        if code != 0:
            raise DeviceRunnerError(f"devicectl {' '.join(args)} failed (exit {code}): {out.strip()[:400]}")
        return out

    def connected(self) -> list[dict[str, str]]:
        out = self._run("list", "devices")
        devices: list[dict[str, str]] = []
        for line in out.splitlines():
            match = re.search(r"([0-9A-Fa-f-]{16,})\s*(.*)$", line)
            # devicectl's dashed table-separator row also matches the UDID/UUID
            # pattern; a real identifier always contains at least one hex digit.
            if match and "Mac" not in line and any(c in "0123456789abcdefABCDEF" for c in match.group(1)):
                devices.append({"device_id": match.group(1), "raw": line.strip()})
        return devices

    def install(self, device_id: str, artifact: Path) -> None:
        self._run("device", "install", "app", "--device", device_id, str(artifact))

    def launch(self, device_id: str, bundle_id: str) -> None:
        self._run("device", "process", "launch", "--device", device_id, bundle_id)

    def terminate(self, device_id: str, bundle_id: str) -> None:
        self._run("device", "process", "terminate", "--device", device_id, bundle_id)


# ---------------------------------------------------------------------------
# Readiness doctor
# ---------------------------------------------------------------------------


def device_doctor(
    repo_root: Path,
    *,
    android: AndroidTooling | None = None,
    ios: IosTooling | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Classify physical-device readiness (same vocabulary as mobile_doctor).

    Every check is one of ``ready`` / ``agent-remediable`` /
    ``operator-action-needed`` with the exact remedy. Read-only.
    """

    checks: list[dict[str, Any]] = []

    def check(name: str, status: str, detail: str, remedy: str | None = None) -> None:
        entry: dict[str, Any] = {"check": name, "status": status, "detail": detail}
        if remedy:
            entry["remedy"] = remedy
        checks.append(entry)

    if android is not None:
        try:
            devices = android.connected()
        except DeviceRunnerError as exc:
            check(
                "android.tooling",
                "agent-remediable",
                str(exc),
                "install Android SDK platform-tools and ensure adb is on PATH",
            )
        else:
            if devices:
                for device in devices:
                    registered = (
                        device_lease.registry_root(repo_root, env) / "android" / f"{device['device_id']}.json"
                    ).exists()
                    check(
                        f"android.device.{device['device_id']}",
                        "ready" if registered else "operator-action-needed",
                        "connected" + ("; registered test device" if registered else "; NOT registered"),
                        (
                            None
                            if registered
                            else "register the dedicated test device: mobile-session device register --platform android "
                            f"--device-id {device['device_id']} --confirm-test-device (personal devices are refused)"
                        ),
                    )
            else:
                check(
                    "android.device.attached",
                    "operator-action-needed",
                    "no Android device visible to adb",
                    "connect + unlock the dedicated test phone, enable Developer options > USB debugging, "
                    "authorize this host, then rerun `mobile-session device doctor`",
                )
    if ios is not None:
        try:
            devices = ios.connected()
        except DeviceRunnerError as exc:
            check(
                "ios.tooling",
                "agent-remediable",
                str(exc),
                "install Xcode and ensure `xcrun devicectl list devices` works",
            )
        else:
            if devices:
                for device in devices:
                    registered = (
                        device_lease.registry_root(repo_root, env) / "ios" / f"{device['device_id']}.json"
                    ).exists()
                    check(
                        f"ios.device.{device['device_id']}",
                        "ready" if registered else "operator-action-needed",
                        "connected" + ("; registered test device" if registered else "; NOT registered"),
                        (
                            None
                            if registered
                            else "register the dedicated test device: mobile-session device register --platform ios "
                            f"--device-id {device['device_id']} --confirm-test-device"
                        ),
                    )
            else:
                check(
                    "ios.device.attached",
                    "operator-action-needed",
                    "no iOS device visible to devicectl",
                    "connect the dedicated test iPhone over USB, unlock it, trust this Mac, and enable "
                    "Developer Mode (Settings > Privacy & Security) — see PHYSICAL_DEVICES.md",
                )
    return {"schema_version": DEVICE_RUN_EVIDENCE_SCHEMA, "checks": checks}


# ---------------------------------------------------------------------------
# Qualification run
# ---------------------------------------------------------------------------


def run(
    repo_root: Path,
    session_id: str,
    platform: str,
    device_id: str,
    *,
    artifact: Path,
    env: Mapping[str, str] | None = None,
    android: AndroidTooling | None = None,
    ios: IosTooling | None = None,
    lease_generation: int | None = None,
) -> dict[str, Any]:
    """Execute the automatable part of a device qualification run.

    Requires: a C1 session manifest (loopback endpoints, synthetic fixture),
    an active device lease owned by this caller, and the built artifact.
    Produces a ``device-run-evidence/v1`` receipt next to the session lease;
    steps that need a human are recorded as ``operator`` steps, never faked.
    """

    manifest = _load_session_lease(session_dir(repo_root, session_id, env) / "lease.json")
    if manifest.get("status") != "running":
        raise DeviceRunnerError(
            f"session {session_id} is {manifest.get('status')!r}, not running; start it first "
            "(the device run routes the app at the session's loopback endpoints)"
        )
    try:
        lease = device_lease._load_lease(repo_root, platform, device_id, env)
    except device_lease.DeviceLeaseError as exc:
        raise DeviceRunnerError(f"device lease required before a run: {exc}") from exc
    device_lease.check_ownership(lease)
    if lease.get("session_id") not in (None, session_id):
        raise DeviceRunnerError(
            f"device {platform}/{device_id} lease is bound to session {lease.get('session_id')!r}, not {session_id!r}"
        )
    if not artifact.is_file():
        raise DeviceRunnerError(f"artifact {artifact} does not exist; build it first (see PHYSICAL_DEVICES.md)")

    plan = RunPlan(session_id=session_id, platform=platform, device_id=device_id, artifact=artifact)
    app_id = manifest.get("app_id", "com.friend.ios.dev")
    ports = manifest.get("ports", {})

    started = session_evidence.utc_now()
    try:
        if platform == "android":
            if android is None:
                raise DeviceRunnerError("android tooling unavailable")
            _run_android(plan, android, device_id, app_id, artifact, ports)
        elif platform == "ios":
            if ios is None:
                raise DeviceRunnerError("ios tooling unavailable")
            _run_ios(plan, ios, device_id, app_id, artifact)
        else:
            raise DeviceRunnerError(
                f"platform {platform!r} has no automatable device run yet (wearable is operator-assisted)"
            )
    except DeviceRunnerError as exc:
        plan.record("run", "failed", str(exc))
        raise
    finally:
        receipt = _build_receipt(repo_root, plan, manifest, lease, started)
        _write_device_run_evidence(repo_root, session_id, env, receipt)
    return receipt


def _run_android(
    plan: RunPlan,
    android: AndroidTooling,
    device_id: str,
    app_id: str,
    artifact: Path,
    ports: Mapping[str, int],
) -> None:
    if app_id not in ANDROID_HARNESS_APP_IDS:
        raise DeviceRunnerError(f"refusing to operate on foreign app id {app_id!r}")
    connected = {d["device_id"] for d in android.connected()}
    if device_id not in connected:
        raise DeviceRunnerError(f"device {device_id} not visible to adb (connected: {sorted(connected) or 'none'})")
    plan.record("device-info", "ok", json.dumps(android.device_info(device_id), sort_keys=True))
    android.install(device_id, artifact)
    plan.record("install", "ok", f"{artifact.name} sha256={session_evidence.file_sha256(artifact)[:16]}…")
    # Route the app at the session's loopback services via adb reverse: the
    # device dials its own localhost, adb forwards to the host session ports.
    for name, port in sorted(ports.items()):
        android.reverse(device_id, port, port)
    plan.record("reverse-ports", "ok", ",".join(f"{name}={port}" for name, port in sorted(ports.items())))
    # Permission deny -> grant cycle (deny state first so the prompt path is exercised).
    for permission in ANDROID_TOGGLE_PERMISSIONS:
        android.revoke(device_id, app_id, permission)
    plan.record("permission-deny", "ok", "revoked: " + ",".join(ANDROID_TOGGLE_PERMISSIONS))
    android.launch(device_id, app_id)
    plan.record("launch", "ok", f"am start {app_id}/.MainActivity (untethered; no flutter session)")
    for permission in ANDROID_TOGGLE_PERMISSIONS:
        android.grant(device_id, app_id, permission)
    plan.record("permission-grant", "ok", "granted: " + ",".join(ANDROID_TOGGLE_PERMISSIONS))
    plan.operator_steps.extend(
        [
            "Background/foreground the app (swipe home, return) and confirm capture recovery — adb can't drive OS app switching",
            "Bluetooth wearable disconnect/reconnect — physical device action, watch the app reconnect",
            "Airplane-mode on/off for offline persistence -> recovery/upload",
        ]
    )


def _run_ios(plan: RunPlan, ios: IosTooling, device_id: str, bundle_id: str, artifact: Path) -> None:
    if not str(bundle_id).startswith(IOS_HARNESS_BUNDLE_PREFIX):
        raise DeviceRunnerError(f"refusing to operate on foreign bundle id {bundle_id!r}")
    connected = {d["device_id"] for d in ios.connected()}
    if device_id not in connected:
        raise DeviceRunnerError(
            f"device {device_id} not visible to devicectl (connected: {sorted(connected) or 'none'})"
        )
    ios.install(device_id, artifact)
    plan.record("install", "ok", f"{artifact.name} sha256={session_evidence.file_sha256(artifact)[:16]}…")
    ios.launch(device_id, bundle_id)
    plan.record("launch", "ok", f"devicectl launch {bundle_id} (AOT/profile build; untethered)")
    plan.operator_steps.extend(
        [
            "First launch: tap through the microphone + Bluetooth permission prompts (TCC cannot be granted from the CLI)",
            "Settings > Privacy > Microphone: deny once, relaunch, re-grant to exercise the permission recovery path",
            "Lock/unlock and background/foreground transitions during capture",
            "Bluetooth wearable disconnect/reconnect",
        ]
    )


def _build_receipt(
    repo_root: Path,
    plan: RunPlan,
    manifest: Mapping[str, Any],
    lease: Mapping[str, Any],
    started: str,
) -> dict[str, Any]:
    return {
        "schema_version": DEVICE_RUN_EVIDENCE_SCHEMA,
        "session_id": plan.session_id,
        "platform": plan.platform,
        "device": {
            "device_id": plan.device_id,
            "lease_generation": lease.get("generation"),
        },
        "artifact": {"path": plan.artifact.name, "sha256": session_evidence.file_sha256(plan.artifact)},
        "app_id": manifest.get("app_id"),
        "fixture_version": manifest.get("fixture_version"),
        "source": session_evidence.source_identity(repo_root),
        "started_at": started,
        "finished_at": session_evidence.utc_now(),
        "steps": [step.as_dict() for step in plan.steps],
        "operator_steps": plan.operator_steps,
        "physical_acceptance": "pending-user-run-evidence",
    }


def _write_device_run_evidence(
    repo_root: Path,
    session_id: str,
    env: Mapping[str, str] | None,
    receipt: Mapping[str, Any],
) -> Path:
    offending = session_evidence._walk_credential_keys(receipt)
    if offending:
        raise DeviceRunnerError(f"device-run evidence contains credential-shaped keys: {offending}")
    path = sessions_root(repo_root, env) / session_id / "device-run.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
