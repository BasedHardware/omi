"""V2 iOS-simulator full-app smoke. Not the V1 live broker, not CI.

Boots one session simulator, launches the real debug/dev/local_dev app with
OMI_DEV_CONTROLS=1, reads ext.omi.controls, screenshots, writes a
session-evidence-v1 receipt, and releases everything this run acquired.

Sign-in is out of this package. The app is signed out; smoke asserts
signedIn=false rather than injecting a token.
"""

from __future__ import annotations

import json
import os
import re
import selectors
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from . import mobile_doctor, mobile_session as ms, session_evidence as se
from .mobile_session import SessionError

FORBIDDEN = ("api.omi.me", "api.omiapi.com", "mobile_beta")
# Measured on this host: 412 s cold Xcode, 212 s spike to app.started.
# Never impose a hidden deadline below that.
DEFAULT_STARTUP_TIMEOUT_S = 900
MIN_STARTUP_TIMEOUT_S = 412
LANE_BACKEND_ISSUE = "https://github.com/BasedHardware/omi/pull/14349"
# TODO(https://github.com/BasedHardware/omi/pull/14319): architect sign-in
# design is pending (seed writes a credential-free uid the app does not consume;
# default local-dev principal is local-dev-user, not the fixture). Smoke must
# assert signedIn=false until that design lands. Do not mint a workaround token.


class SmokeBlocked(SessionError):
    def __init__(self, message: str, *, remedy: str, payload: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.remedy = remedy
        self.payload = dict(payload or {})


class MachineProcess(Protocol):
    def send(self, line: str) -> None: ...
    def receive(self, timeout_s: float) -> str | None: ...
    def close(self) -> None: ...
    @property
    def pid(self) -> int: ...


@dataclass(frozen=True)
class LaunchSpec:
    argv: tuple[str, ...]
    cwd: Path
    env: Mapping[str, str]
    device_id: str
    stderr_path: Path | None = None


class FlutterChild:
    """Binary machine-protocol child. Never mix OS select() with text readline()."""

    def __init__(self, spec: LaunchSpec) -> None:
        for bad in FORBIDDEN:
            if bad in " ".join(spec.argv):
                raise SmokeBlocked(
                    f"refusing flutter argv that mentions {bad}",
                    remedy="use loopback session ports",
                    payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
                )
        self._stderr_handle = None
        if spec.stderr_path is not None:
            spec.stderr_path.parent.mkdir(parents=True, exist_ok=True)
            self._stderr_handle = spec.stderr_path.open("wb")
        self.process = subprocess.Popen(
            list(spec.argv),
            cwd=str(spec.cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr_handle or subprocess.DEVNULL,
            bufsize=0,
            env={**os.environ, **dict(spec.env), "PROVIDER_MODE": "offline"},
        )
        assert self.process.stdout is not None
        self._buf = b""
        self.readable = selectors.DefaultSelector()
        self.readable.register(self.process.stdout, selectors.EVENT_READ)

    @property
    def pid(self) -> int:
        return int(self.process.pid)

    def send(self, line: str) -> None:
        assert self.process.stdin is not None
        payload = line if line.endswith("\n") else line + "\n"
        self.process.stdin.write(payload.encode("utf-8"))
        self.process.stdin.flush()

    def receive(self, timeout_s: float) -> str | None:
        if b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            return line.decode("utf-8", "replace") + "\n"
        deadline = time.monotonic() + max(0.0, timeout_s)
        while True:
            if b"\n" in self._buf:
                line, self._buf = self._buf.split(b"\n", 1)
                return line.decode("utf-8", "replace") + "\n"
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("machine deadline")
            if self.process.poll() is not None:
                chunk = self._read_chunk()
                if chunk:
                    self._buf += chunk
                    continue
                if self._buf:
                    line = self._buf
                    self._buf = b""
                    return line.decode("utf-8", "replace")
                return None
            if not self.readable.select(remaining):
                raise TimeoutError("machine deadline")
            chunk = self._read_chunk()
            if not chunk:
                if self._buf:
                    line = self._buf
                    self._buf = b""
                    return line.decode("utf-8", "replace")
                return None
            self._buf += chunk

    def _read_chunk(self) -> bytes:
        if self.process.stdout is None:
            return b""
        try:
            return os.read(self.process.stdout.fileno(), 65536)
        except OSError:
            return b""

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=10)
        try:
            self.readable.close()
        except Exception:
            pass
        for stream in (self.process.stdin, self.process.stdout):
            if stream:
                try:
                    stream.close()
                except OSError:
                    pass
        if self._stderr_handle is not None:
            try:
                self._stderr_handle.close()
            except OSError:
                pass


def lane_backend_target_present(repo_root: Path) -> bool:
    makefile = Path(repo_root) / "Makefile"
    if not makefile.is_file():
        return False
    return bool(re.search(r"^lane-backend:", makefile.read_text(encoding="utf-8"), flags=re.M))


def session_backend_remedy(repo_root: Path) -> str:
    if lane_backend_target_present(repo_root):
        return "make lane-backend"
    return (
        "this tree has no `make lane-backend` (session uvicorn wheels; "
        f"{LANE_BACKEND_ISSUE} stacked on #14321). Do not vendor that target here. "
        "`make setup-backend` on this base only syncs the pylock. Stack onto a tree "
        "that has `make lane-backend`, then rerun."
    )


def uvicorn_importable(repo_root: Path) -> bool:
    """cmd_up starts uvicorn with this process's interpreter."""
    try:
        import uvicorn  # noqa: F401

        return True
    except ImportError:
        pass
    python = Path(repo_root) / "backend" / ".venv" / "bin" / "python"
    if not python.is_file():
        return False
    completed = subprocess.run(
        [str(python), "-c", "import uvicorn"],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0


# flutter run rewrites these tracked files. Smoke restores the bytes it
# observed at start so a passing lane cannot leave lockfile dirt for pre-push.
_FLUTTER_TREE_PATHS = (
    "app/ios/Podfile.lock",
    "app/android/gradle.properties",
)


def snapshot_flutter_tree_files(repo_root: Path) -> dict[str, bytes | None]:
    snapshot: dict[str, bytes | None] = {}
    for relative in _FLUTTER_TREE_PATHS:
        path = Path(repo_root) / relative
        try:
            snapshot[relative] = path.read_bytes()
        except OSError:
            snapshot[relative] = None
    return snapshot


def restore_flutter_tree_files(repo_root: Path, snapshot: Mapping[str, bytes | None]) -> None:
    for relative, before in snapshot.items():
        path = Path(repo_root) / relative
        try:
            after = path.read_bytes()
        except OSError:
            after = None
        if after == before:
            continue
        if before is None:
            try:
                path.unlink()
            except OSError:
                pass
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(before)


def ensure_generated_env(
    app_dir: Path, repo_root: Path, *, runner: Callable[..., subprocess.CompletedProcess[str]]
) -> None:
    """Generate envied files without deleting tracked sources.

    A `build_runner --build-filter=… --delete-conflicting-outputs` run on the
    V2 spike deleted tracked `lib/utils/manifest/manifest.g.dart`. Never pass
    `--delete-conflicting-outputs` here; restore any tracked deletions if they
    still happen.
    """

    envied = (app_dir / "lib" / "env" / "dev_env.g.dart", app_dir / "lib" / "env" / "prod_env.g.dart")
    if all(path.is_file() for path in envied):
        return
    runner(["flutter", "pub", "get"], cwd=app_dir, timeout=180)
    completed = runner(
        [
            "flutter",
            "pub",
            "run",
            "build_runner",
            "build",
            "--build-filter=lib/env/*",
        ],
        cwd=app_dir,
        timeout=300,
    )
    argv = " ".join(completed.args if isinstance(completed.args, (list, tuple)) else [str(completed.args)])
    if "--delete-conflicting-outputs" in argv:
        raise SmokeBlocked(
            "codegen invoked --delete-conflicting-outputs",
            remedy="rerun build_runner without that flag; restore tracked *.g.dart",
            payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
        )
    output = f"{completed.stdout or ''}{completed.stderr or ''}"
    if completed.returncode not in (0, None) or "wrote 0 outputs" in (completed.stdout or ""):
        raise SmokeBlocked(
            "envied codegen wrote no files",
            remedy="flutter pub run build_runner build --build-filter=lib/env/*  (no --delete-conflicting-outputs)",
            payload={"classification": mobile_doctor.AGENT_REMEDIABLE, "codegen_tail": output[-2000:]},
        )
    deleted = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "-d"],
        capture_output=True,
        text=True,
        check=False,
    )
    missing_tracked = [line for line in (deleted.stdout or "").splitlines() if line]
    if missing_tracked:
        subprocess.run(["git", "-C", str(repo_root), "checkout", "--", *missing_tracked], check=False)
    if not all(path.is_file() for path in envied):
        raise SmokeBlocked(
            "envied generated files are still missing after build_runner",
            remedy="flutter pub run build_runner build --build-filter=lib/env/*  (no --delete-conflicting-outputs)",
            payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
        )


def bootstrap_local_placeholders(app_dir: Path) -> None:
    setup = app_dir / "setup" / "prebuilt"
    copies = [
        (app_dir / "lib" / "firebase_options_local.dart", app_dir / "lib" / "firebase_options_dev.dart"),
        (app_dir / "lib" / "firebase_options_local.dart", app_dir / "lib" / "firebase_options_prod.dart"),
        (setup / "google-services-local.json", app_dir / "android" / "app" / "src" / "dev" / "google-services.json"),
        (setup / "google-services-local.json", app_dir / "android" / "app" / "src" / "prod" / "google-services.json"),
        (setup / "GoogleService-Info-Local.plist", app_dir / "ios" / "Config" / "Dev" / "GoogleService-Info.plist"),
        (setup / "GoogleService-Info-Local.plist", app_dir / "ios" / "Config" / "Prod" / "GoogleService-Info.plist"),
        (setup / "GoogleService-Info-Local.plist", app_dir / "ios" / "Runner" / "GoogleService-Info.plist"),
        (setup / "GoogleService-Info-Local.plist", app_dir / "macos" / "GoogleService-Info.plist"),
        (setup / "GoogleService-Info-Local.plist", app_dir / "macos" / "Config" / "Dev" / "GoogleService-Info.plist"),
        (setup / "GoogleService-Info-Local.plist", app_dir / "macos" / "Config" / "Prod" / "GoogleService-Info.plist"),
    ]
    for src, dest in copies:
        if not src.is_file():
            continue
        if dest.is_file():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    env_path = app_dir / ".dev.env"
    if not env_path.is_file():
        env_path.write_text("API_BASE_URL=\nUSE_WEB_AUTH=true\nUSE_AUTH_CUSTOM_TOKEN=true\n", encoding="utf-8")
    else:
        text = env_path.read_text(encoding="utf-8")
        for bad in FORBIDDEN:
            if bad in text:
                raise SmokeBlocked(
                    f"app/.dev.env mentions {bad}",
                    remedy="set API_BASE_URL= (empty) or a loopback session URL",
                    payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
                )


def _parse_machine(line: str) -> dict[str, Any] | None:
    stripped = line.strip()
    if not stripped.startswith("["):
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, list):
        if len(payload) != 1 or not isinstance(payload[0], dict):
            return None
        return payload[0]
    return payload if isinstance(payload, dict) else None


def find_ios_app_bundle(app_dir: Path) -> Path | None:
    root = app_dir / "build" / "ios"
    if not root.is_dir():
        return None
    for candidate in sorted(root.rglob("*.app")):
        if candidate.is_dir():
            return candidate
    return None


def default_simctl_screenshot(udid: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ["xcrun", "simctl", "io", udid, "screenshot", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SmokeBlocked(
            completed.stderr.strip() or "simctl screenshot failed",
            remedy=f"xcrun simctl io {udid} screenshot {path}",
            payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
        )


class SimulatorSmoke:
    def __init__(
        self,
        repo_root: Path,
        *,
        doctor: Callable[..., mobile_doctor.DoctorReport] | None = None,
        acquire: Callable[..., dict[str, Any]] | None = None,
        start: Callable[..., dict[str, Any]] | None = None,
        seed: Callable[..., dict[str, Any]] | None = None,
        release: Callable[..., dict[str, Any]] | None = None,
        evidence: Callable[..., dict[str, Any]] | None = None,
        factory: Callable[[LaunchSpec], MachineProcess] | None = None,
        screenshot: Callable[[str, Path], None] | None = None,
        codegen: Callable[[Path, Path], None] | None = None,
        uvicorn_ok: Callable[[Path], bool] | None = None,
        startup_timeout_s: float = DEFAULT_STARTUP_TIMEOUT_S,
        env: Mapping[str, str] | None = None,
        keep_dir: Path | None = None,
    ) -> None:
        if startup_timeout_s < MIN_STARTUP_TIMEOUT_S:
            raise SmokeBlocked(
                f"startup timeout {startup_timeout_s}s is below the measured cold start {MIN_STARTUP_TIMEOUT_S}s",
                remedy=f"pass a timeout of at least {MIN_STARTUP_TIMEOUT_S} (default {DEFAULT_STARTUP_TIMEOUT_S})",
                payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
            )
        self.repo_root = Path(repo_root)
        self.env = dict(env or {})
        self._doctor = doctor or (
            lambda **kwargs: mobile_doctor.run_doctor(self.repo_root, env=self.env or None, **kwargs)
        )
        self._acquire = acquire or (lambda **kwargs: ms.acquire(self.repo_root, self.env or None, **kwargs))
        self._start = start or (
            lambda session_id, **kwargs: ms.start(self.repo_root, session_id, self.env or None, **kwargs)
        )
        self._seed = seed or (lambda session_id: ms.seed(self.repo_root, session_id, self.env or None))
        self._release = release or (lambda session_id: ms.release(self.repo_root, session_id, self.env or None))
        self._evidence = evidence or (
            lambda session_id, **kwargs: ms.evidence(self.repo_root, session_id, self.env or None, **kwargs)
        )
        self._factory = factory or FlutterChild
        self._screenshot = screenshot or default_simctl_screenshot
        self._codegen = codegen or (
            lambda app, root: ensure_generated_env(
                app,
                root,
                runner=lambda argv, cwd, timeout: subprocess.run(
                    argv, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, check=False
                ),
            )
        )
        self._uvicorn_ok = uvicorn_ok or uvicorn_importable
        self._startup_timeout_s = float(startup_timeout_s)
        self._keep_dir = Path(keep_dir) if keep_dir else None
        self._child: MachineProcess | None = None
        self._app_id: str | None = None
        self._rpc_id = 0
        self._acquired_id: str | None = None
        self._timings: dict[str, float] = {}
        self._machine_log: Path | None = None

    def run(self, *, session_id: str | None = None, name: str = "v2smoke") -> dict[str, Any]:
        tree_snapshot = snapshot_flutter_tree_files(self.repo_root)
        started = time.monotonic()
        passed = False
        try:
            result = self._run(session_id=session_id, name=name)
            passed = True
            return result
        except (SmokeBlocked, SessionError):
            raise
        except Exception as exc:
            raise SmokeBlocked(
                f"simulator smoke crashed: {type(exc).__name__}: {exc}",
                remedy="inspect flutter.stderr.log and the session machine.jsonl",
                payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
            ) from exc
        finally:
            self._timings["total_s"] = round(time.monotonic() - started, 1)
            self._stop_child()
            restore_flutter_tree_files(self.repo_root, tree_snapshot)
            teardown_error: BaseException | None = None
            if self._acquired_id:
                old_stdout = sys.stdout
                try:
                    sys.stdout = sys.stderr
                    self._release(self._acquired_id)
                except Exception as exc:
                    teardown_error = exc
                finally:
                    sys.stdout = old_stdout
            if passed and teardown_error is not None:
                raise SmokeBlocked(
                    f"app checks passed but session teardown failed: {teardown_error}",
                    remedy=(
                        "inspect harness logs; an unowned port or unprovable pid must not be reported as a passed smoke"
                    ),
                    payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
                ) from teardown_error

    def _run(self, *, session_id: str | None, name: str) -> dict[str, Any]:
        report = self._doctor(platforms=("ios-simulator",), skip_capacity=False)
        if report.overall != "ready":
            first = next(
                (c for c in getattr(report, "checks", ()) if getattr(c, "status", "") != mobile_doctor.READY), None
            )
            raise SmokeBlocked(
                "simulator lane not ready (doctor)",
                remedy=(
                    first.remedy
                    if first
                    else "bash scripts/dev-harness/mobile-session.sh doctor --platform ios-simulator"
                ),
                payload={
                    "doctor": report.as_dict(),
                    "classification": first.status if first else mobile_doctor.AGENT_REMEDIABLE,
                },
            )
        if not self._uvicorn_ok(self.repo_root):
            raise SmokeBlocked(
                "session backend uvicorn is not importable in backend/.venv",
                remedy=session_backend_remedy(self.repo_root),
                payload={
                    "classification": mobile_doctor.AGENT_REMEDIABLE,
                    "lane_backend": lane_backend_target_present(self.repo_root),
                },
            )
        lease: dict[str, Any]
        if session_id:
            lease = ms._load_lease(ms.session_dir(self.repo_root, session_id, self.env or None) / ms.LEASE_FILENAME)
        else:
            lease = dict(self._acquire(name=name, platform_name="ios-simulator"))
            self._acquired_id = str(lease["session_id"])
            session_id = self._acquired_id
            started = self._start(session_id, json_stdout=True)
            if isinstance(started, Mapping):
                lease = dict(started)
            self._seed(session_id)
        device = (lease.get("device") or {}).get("udid") or ""
        if not device:
            raise SmokeBlocked(
                f"session {session_id} has no attached simulator",
                remedy=f'make mobile-session ARGS="start {session_id}"',
                payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
            )
        app_dir = self.repo_root / "app"
        bootstrap_local_placeholders(app_dir)
        self._codegen(app_dir, self.repo_root)
        ports = lease["ports"]
        backend = f"http://127.0.0.1:{ports['backend']}/"
        directory = ms.session_dir(self.repo_root, str(session_id), self.env or None)
        directory.mkdir(parents=True, exist_ok=True)
        self._machine_log = directory / "machine.jsonl"
        spec = LaunchSpec(
            argv=(
                "flutter",
                "run",
                "--machine",
                "--debug",
                "--flavor",
                "dev",
                "--dart-define=OMI_APP_PROFILE=local_dev",
                "--dart-define=OMI_DEV_CONTROLS=1",
                f"--dart-define=OMI_API_BASE_URL={backend}",
                "--dart-define=OMI_FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1",
                f"--dart-define=OMI_FIREBASE_AUTH_EMULATOR_PORT={ports['auth']}",
                f"--device-id={device}",
                "--host-vmservice-port=0",
                "--no-dds",
            ),
            cwd=app_dir,
            env={"PROVIDER_MODE": "offline"},
            device_id=str(device),
            stderr_path=directory / "flutter.stderr.log",
        )
        boot = time.monotonic()
        deadline = boot + self._startup_timeout_s
        self._child = self._factory(spec)
        self._drain_until_started(deadline)
        self._timings["app_started_s"] = round(time.monotonic() - boot, 1)
        capabilities, state = self._wait_signed_out_ready(deadline)
        shot = directory / "screenshots" / "smoke.png"
        self._screenshot(str(device), shot)
        artifact = find_ios_app_bundle(app_dir)
        if artifact is None:
            raise SmokeBlocked(
                "no iOS .app bundle under app/build/ios after app.started",
                remedy="inspect flutter.stderr.log; expected app/build/ios/**/*.app",
                payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
            )
        document = self._evidence(
            str(session_id),
            artifact_path=artifact,
            state="running",
            artifact_files={"screenshots": ["screenshots/smoke.png"]},
        )
        errors = se.validate_evidence(document)
        if errors:
            raise SmokeBlocked(
                "session-evidence-v1 invalid: " + "; ".join(errors),
                remedy="inspect the session evidence.json and screenshot path",
                payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
            )
        kept_shot = shot
        kept_evidence = directory / ms.EVIDENCE_FILENAME
        if self._keep_dir is not None:
            self._keep_dir.mkdir(parents=True, exist_ok=True)
            kept_shot = self._keep_dir / "screenshots" / "smoke.png"
            kept_shot.parent.mkdir(parents=True, exist_ok=True)
            if shot != kept_shot:
                shutil.copy2(shot, kept_shot)
            kept_evidence = self._keep_dir / "evidence.json"
            session_evidence_path = directory / ms.EVIDENCE_FILENAME
            if session_evidence_path.is_file():
                shutil.copy2(session_evidence_path, kept_evidence)
            else:
                kept_evidence.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
            for name in ("machine.jsonl", "flutter.stderr.log"):
                src = directory / name
                if src.is_file():
                    shutil.copy2(src, self._keep_dir / name)
        return {
            "outcome": "passed",
            "session_id": session_id,
            "device": device,
            "timings": dict(self._timings),
            "controls": {"capabilities": capabilities, "state": state},
            "screenshot": str(kept_shot),
            "screenshot_sha256": se.file_sha256(kept_shot),
            "artifact": None if artifact is None else str(artifact),
            "evidence": document,
            "evidence_path": str(kept_evidence),
        }

    def _assert_signed_out_ready(self, state: Mapping[str, Any]) -> None:
        if state.get("profile") != "local_dev":
            raise SmokeBlocked(
                f"controls profile is {state.get('profile')!r}, expected local_dev",
                remedy="launch with --dart-define=OMI_APP_PROFILE=local_dev --flavor dev",
                payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
            )
        readiness = state.get("readiness") or {}
        if readiness.get("routed") is not True or readiness.get("captureIdle") is not True:
            raise SmokeBlocked(
                f"app is not routed/idle: {readiness}",
                remedy="wait for first-frame routing; do not treat app.started as ready",
                payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
            )
        if readiness.get("signedIn") is not False:
            raise SmokeBlocked(
                f"expected signedIn=false (sign-in is not in this package), got {readiness.get('signedIn')!r}",
                remedy="do not inject a token; wait for the architect's pending sign-in design",
                payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
            )

    def _wait_signed_out_ready(self, deadline: float) -> tuple[dict[str, Any], dict[str, Any]]:
        last: SmokeBlocked | None = None
        capabilities: dict[str, Any] | None = None
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise last or SmokeBlocked(
                    "controls deadline before routed/idle signed-out state",
                    remedy="keep reading after app.started; do not treat app.started as ready",
                    payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
                )
            try:
                if capabilities is None:
                    capabilities = self._call_extension("ext.omi.controls.capabilities")
                state = self._call_extension("ext.omi.controls.state")
                self._assert_signed_out_ready(state)
                return capabilities, state
            except SmokeBlocked as exc:
                last = exc
                message = str(exc)
                if "signedIn=false" in message or "expected local_dev" in message or "leaked" in message:
                    raise
                time.sleep(min(1.0, max(0.05, remaining)))

    def _drain_until_started(self, deadline: float) -> None:
        events: list[str] = []
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SmokeBlocked(
                    "flutter machine deadline before app.started",
                    remedy=f"cold start on this host was {MIN_STARTUP_TIMEOUT_S}s; do not lower the timeout below that (default {DEFAULT_STARTUP_TIMEOUT_S})",
                    payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
                )
            try:
                message = self._read(remaining)
            except TimeoutError:
                raise SmokeBlocked(
                    "flutter machine deadline before app.started",
                    remedy=f"cold start on this host was {MIN_STARTUP_TIMEOUT_S}s; do not lower the timeout below that (default {DEFAULT_STARTUP_TIMEOUT_S})",
                    payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
                ) from None
            if message is None:
                raise SmokeBlocked(
                    "flutter daemon exited before app.started",
                    remedy="inspect flutter.stderr.log",
                    payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
                )
            name = message.get("event")
            if name:
                events.append(str(name))
            if name == "app.start":
                self._app_id = str((message.get("params") or {}).get("appId") or "")
            if name == "app.started":
                if "app.start" not in events:
                    raise SmokeBlocked(
                        "app.started without app.start",
                        remedy="keep reading the machine log",
                        payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
                    )
                return

    def _read(self, timeout_s: float) -> dict[str, Any] | None:
        if self._child is None:
            raise SmokeBlocked(
                "no flutter child",
                remedy="start flutter run --machine",
                payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
            )
        deadline = time.monotonic() + timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("machine deadline")
            line = self._child.receive(remaining)
            if line is None:
                return None
            parsed = _parse_machine(line)
            if parsed is None:
                continue
            if self._machine_log is not None:
                with self._machine_log.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(parsed) + "\n")
            return parsed

    def _call_extension(self, method_name: str, params: Mapping[str, str] | None = None) -> dict[str, Any]:
        if self._child is None or not self._app_id:
            raise SmokeBlocked(
                "cannot call controls without a running app",
                remedy="wait for app.start",
                payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
            )
        self._rpc_id += 1
        rpc_id = self._rpc_id
        self._child.send(
            json.dumps(
                [
                    {
                        "id": rpc_id,
                        "method": "app.callServiceExtension",
                        "params": {"appId": self._app_id, "methodName": method_name, "params": dict(params or {})},
                    }
                ]
            )
        )
        deadline = time.monotonic() + 45
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SmokeBlocked(
                    f"{method_name} timed out",
                    remedy="this package requires B0 ext.omi.controls.* registration (PR #14319)",
                    payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
                )
            try:
                message = self._read(remaining)
            except TimeoutError:
                raise SmokeBlocked(
                    f"{method_name} timed out",
                    remedy="this package requires B0 ext.omi.controls.* registration (PR #14319)",
                    payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
                ) from None
            if message is None:
                raise SmokeBlocked(
                    f"{method_name} got EOF",
                    remedy="keep the flutter child alive through controls",
                    payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
                )
            if message.get("id") == rpc_id:
                if "error" in message:
                    raise SmokeBlocked(
                        f"{method_name} error: {message['error']}",
                        remedy="this package requires B0 ext.omi.controls.* registration (PR #14319)",
                        payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
                    )
                result = message.get("result")
                if not isinstance(result, dict):
                    raise SmokeBlocked(
                        f"{method_name} returned a non-object",
                        remedy="decode callServiceExtension result as the extension map",
                        payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
                    )
                blob = json.dumps(result)
                for bad in FORBIDDEN:
                    if bad in blob:
                        raise SmokeBlocked(
                            f"{method_name} leaked {bad}",
                            remedy="session endpoints must stay loopback",
                            payload={"classification": mobile_doctor.AGENT_REMEDIABLE},
                        )
                return result

    def _stop_child(self) -> None:
        child = self._child
        if child is None:
            return
        try:
            if self._app_id:
                try:
                    child.send(json.dumps([{"id": 999001, "method": "app.stop", "params": {"appId": self._app_id}}]))
                    child.receive(5)
                except Exception:
                    pass
            child.close()
        finally:
            self._child = None


def block_android(repo_root: Path, args: Any) -> dict[str, Any]:
    report = mobile_doctor.run_doctor(repo_root, platforms=("android",), skip_capacity=True)
    android = next((c for c in report.checks if c.check == "android-sdk"), None)
    payload = {
        "outcome": "blocked",
        "lane": "android",
        "reason": android.detail if android else "android SDK is not on this host",
        "remedy": (
            android.remedy
            if android
            else "do not install an SDK from this package; use the doctor's android-sdk message"
        ),
        "classification": android.status if android else mobile_doctor.AGENT_REMEDIABLE,
        "doctor": report.as_dict(),
        "ci_policy": "this package does not add the simulator or android lane to CI",
    }
    return payload


def run_smoke(repo_root: Path, args: Any) -> int:
    from . import mobile_verify as verify

    platform_name = getattr(args, "platform", None) or "ios-simulator"
    if platform_name == "android":
        payload = block_android(repo_root, args)
        verify._emit(payload, as_json=getattr(args, "json", False))
        print(f"blocked: {payload['reason']} — {payload['remedy']}", file=sys.stderr)
        return verify.EXIT_BLOCKED
    timeout = float(getattr(args, "journey_timeout", None) or DEFAULT_STARTUP_TIMEOUT_S)
    if timeout < MIN_STARTUP_TIMEOUT_S:
        timeout = DEFAULT_STARTUP_TIMEOUT_S
    evidence_dir = Path(getattr(args, "evidence_dir", None) or (Path(repo_root) / ".local" / "v2-sim-smoke"))
    evidence_dir.mkdir(parents=True, exist_ok=True)
    engine = SimulatorSmoke(repo_root, startup_timeout_s=timeout, keep_dir=evidence_dir)
    try:
        result = engine.run(session_id=getattr(args, "session", None) or None)
    except SmokeBlocked as exc:
        payload = {
            "outcome": "blocked",
            "reason": str(exc),
            "remedy": exc.remedy,
            **exc.payload,
            "timings": engine._timings,
        }
        verify._emit(payload, as_json=getattr(args, "json", False))
        print(f"blocked: {exc} — {exc.remedy}", file=sys.stderr)
        return verify.EXIT_BLOCKED
    except SessionError as exc:
        payload = {
            "outcome": "blocked",
            "reason": str(exc),
            "remedy": str(exc),
            "classification": mobile_doctor.AGENT_REMEDIABLE,
            "timings": engine._timings,
        }
        verify._emit(payload, as_json=getattr(args, "json", False))
        print(f"blocked: {exc}", file=sys.stderr)
        return verify.EXIT_BLOCKED
    receipt = {
        "schema": "mobile-verify/v1",
        "command": "smoke",
        "lane": "simulator",
        "outcome": "passed",
        "session_id": result["session_id"],
        "screenshot": result["screenshot"],
        "screenshot_sha256": result["screenshot_sha256"],
        "artifact": result["artifact"],
        "evidence_path": result["evidence_path"],
        "timings": result["timings"],
        "ci_policy": "ordinary CI never runs this lane",
    }
    (evidence_dir / "verify-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    verify._emit(
        {**receipt, "controls_profile": (result["controls"]["state"] or {}).get("profile")},
        as_json=getattr(args, "json", False),
    )
    return verify.EXIT_OK
