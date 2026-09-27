"""Structured doctor for the isolated mobile-session lane.

Every readiness failure is classified exactly one of:

- ``ready`` — check passed.
- ``agent-remediable`` — an agent can fix it with a user-space command; the
  remedy string is the exact resumption command.
- ``operator-action-needed`` — needs the host operator (privileged install,
  license acceptance, host capacity). The remedy names the smallest action.

Checks are pure with respect to an injected runner/env so the classifications
are unit-testable without a provisioned host. The live CLI wrapper
(``mobile-session doctor``) feeds real probes in.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlparse

READY = "ready"
AGENT_REMEDIABLE = "agent-remediable"
OPERATOR = "operator-action-needed"

LANE_BACKEND = "backend"
LANE_ANDROID = "android"
LANE_IOS = "ios"

# mobile-session start + pre-push typecheck. yaml/dotenv alone is the cheap gate.
BACKEND_RUNTIME_PROBE = "import dotenv, google.auth, pyright, uvicorn, yaml"

# Emulator/app-build lanes need real headroom on the shared Data/scratch
# container; below this the capacity check is an operator gate (freeing space
# or approving an install is David's call, never an agent's — see SCA-486
# capacity rules: never delete unrelated assets).
MIN_FREE_GB_EMULATOR_LANES = 12.0
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
HERMETIC_PROFILE = "local_dev"
HERMETIC_FLAVOR = "dev"

_FLUTTER_VERSION_RE = re.compile(r"Flutter\s+(\d+\.\d+\.\d+)", re.MULTILINE)
_FLUTTER_PIN_RE = re.compile(r"flutter-version:\s*(\d+\.\d+\.\d+)")
_ANDROID_IMAGE_PREFIX = "system-images;android-"
# cmdline-tools 23 prints `system-images/android-36/...` instead of the
# historical semicolon package id, and deprecation warnings on stderr, while
# still exiting 0. Disk is an oracle either way; a failed inventory is not
# "engine absent" and a slash-path listing is not "image missing".
PREFERRED_ANDROID_IMAGE = "system-images;android-36;google_apis;arm64-v8a"
PREFERRED_ANDROID_IMAGE_DIR = ("system-images", "android-36", "google_apis", "arm64-v8a")


class DoctorError(RuntimeError):
    """Raised when doctor itself cannot run (not a readiness failure)."""


@dataclass(frozen=True)
class CheckResult:
    check: str
    status: str
    detail: str
    remedy: str
    lanes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "check": self.check,
            "status": self.status,
            "detail": self.detail,
            "remedy": self.remedy,
            "lanes": list(self.lanes),
        }


@dataclass(frozen=True)
class DoctorReport:
    overall: str  # ready | degraded | blocked
    checks: tuple[CheckResult, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"overall": self.overall, "checks": [check.as_dict() for check in self.checks]}

    def by_status(self, status: str) -> tuple[CheckResult, ...]:
        return tuple(check for check in self.checks if check.status == status)


class Runner:
    """Probe executor; injectable for tests."""

    def run(self, command: Sequence[str], timeout: float = 15.0) -> tuple[int, str]:
        try:
            completed = subprocess.run(list(command), capture_output=True, text=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return 127, str(exc)
        return completed.returncode, (completed.stdout or "") + (completed.stderr or "")

    def which(self, name: str) -> str | None:
        return shutil.which(name)

    def exists(self, path: Path) -> bool:
        return Path(path).exists()

    def free_bytes(self, path: Path) -> int:
        return shutil.disk_usage(str(path)).free


def _ok(check: str, detail: str, lanes: Sequence[str]) -> CheckResult:
    return CheckResult(str(check), READY, detail, "", tuple(lanes))


def _agent(check: str, detail: str, remedy: str, lanes: Sequence[str]) -> CheckResult:
    return CheckResult(str(check), AGENT_REMEDIABLE, detail, remedy, tuple(lanes))


def _operator(check: str, detail: str, remedy: str, lanes: Sequence[str]) -> CheckResult:
    return CheckResult(str(check), OPERATOR, detail, remedy, tuple(lanes))


def flutter_pin(repo_root: Path) -> str | None:
    """The Flutter version pinned by mobile CI (not 'latest')."""

    workflow = Path(repo_root) / ".github" / "workflows" / "mobile-app-checks.yml"
    try:
        pins = set(_FLUTTER_PIN_RE.findall(workflow.read_text(encoding="utf-8")))
    except OSError:
        return None
    if len(pins) != 1:
        return None
    return pins.pop()


def _check_git(repo_root: Path, runner: Runner) -> CheckResult:
    code, out = runner.run(["git", "-C", str(repo_root), "rev-parse", "--is-inside-work-tree"])
    if code == 0 and out.strip() == "true":
        return _ok("git", "repository checkout detected", (LANE_BACKEND,))
    return _agent(
        "git", f"{repo_root} is not a usable git worktree", "Re-clone or repair the task worktree", (LANE_BACKEND,)
    )


def _check_python311(repo_root: Path, runner: Runner, env: Mapping[str, str]) -> CheckResult:
    candidate = env.get("OMI_DEV_PYTHON311", "python3.11")
    code, out = runner.run([candidate, "--version"])
    if code == 0 and "3.11." in out:
        return _ok("python3.11", f"{out.strip()} — backend venv interpreter", (LANE_BACKEND,))
    return _agent(
        "python3.11",
        "python3.11 not found; ambient python3 must not select the backend runtime",
        "Install Python 3.11 (brew install python@3.11), then: python3.11 -m venv backend/.venv && make setup",
        (LANE_BACKEND,),
    )


def _check_backend_venv(repo_root: Path, runner: Runner) -> CheckResult:
    venv_python = Path(repo_root) / "backend" / ".venv" / "bin" / "python"
    if not runner.exists(venv_python):
        return _agent(
            "backend-venv",
            "backend/.venv missing; the backend must run on the repo-pinned 3.11 runtime",
            "make lane-bootstrap  # Python 3.11 venv + cheap-gate packages, not the full pylock",
            (LANE_BACKEND,),
        )
    code, out = runner.run([str(venv_python), "--version"])
    if code != 0 or "3.11." not in out:
        return _agent(
            "backend-venv",
            f"backend/.venv is not Python 3.11 ({out.strip() or 'unusable'})",
            "Recreate with: make lane-bootstrap",
            (LANE_BACKEND,),
        )
    probe_code, probe_out = runner.run([str(venv_python), "-c", "import dotenv, yaml"])
    if probe_code != 0:
        hint = (probe_out or "").strip().splitlines()[-1] if (probe_out or "").strip() else "import failed"
        return _agent(
            "backend-venv",
            f"backend/.venv exists but cannot import yaml and dotenv (incomplete; cheap pre-push gates will fail): {hint}",
            "make lane-bootstrap  # installs the cheap-gate extras without the full backend lock",
            (LANE_BACKEND,),
        )
    return _ok("backend-venv", f"backend/.venv ({out.strip()}); yaml+dotenv import", (LANE_BACKEND,))


def _check_backend_runtime(repo_root: Path, runner: Runner) -> CheckResult:
    venv_python = Path(repo_root) / "backend" / ".venv" / "bin" / "python"
    if not runner.exists(venv_python):
        return _agent(
            "backend-runtime",
            "backend/.venv missing; mobile-session start and the pre-push typecheck need uvicorn/pyright",
            "make lane-backend",
            (LANE_BACKEND,),
        )
    probe_code, probe_out = runner.run([str(venv_python), "-c", BACKEND_RUNTIME_PROBE])
    if probe_code != 0:
        hint = (probe_out or "").strip().splitlines()[-1] if (probe_out or "").strip() else "import failed"
        return _agent(
            "backend-runtime",
            f"backend/.venv cannot import uvicorn/pyright/google.auth (mobile-session start / typecheck): {hint}",
            "make lane-backend",
            (LANE_BACKEND,),
        )
    return _ok(
        "backend-runtime",
        "backend/.venv imports uvicorn, pyright, yaml, dotenv, google.auth",
        (LANE_BACKEND,),
    )


def _check_flutter(repo_root: Path, runner: Runner) -> CheckResult:
    pin = flutter_pin(repo_root)
    binary = runner.which("flutter")
    if binary is None:
        return _agent(
            "flutter",
            "flutter not on PATH",
            f"Install Flutter {pin or 'pinned by mobile CI'} and put it first on PATH (repo pin, not latest)",
            (LANE_ANDROID, LANE_IOS),
        )
    code, out = runner.run([binary, "--version"])
    match = _FLUTTER_VERSION_RE.search(out)
    version = match.group(1) if match else None
    if pin is None:
        return _agent(
            "flutter",
            f"flutter {version or 'unknown'} present but the mobile-CI pin could not be read from "
            ".github/workflows/mobile-app-checks.yml",
            "Read the flutter-version pin in .github/workflows/mobile-app-checks.yml and align the SDK",
            (LANE_ANDROID, LANE_IOS),
        )
    if version == pin:
        return _ok("flutter", f"flutter {version} matches the mobile-CI pin", (LANE_ANDROID, LANE_IOS))
    return _agent(
        "flutter",
        f"flutter {version or 'unknown'} != pinned {pin}",
        f"Switch the SDK on PATH to Flutter {pin} (repo pin, not an arbitrary upgrade)",
        (LANE_ANDROID, LANE_IOS),
    )


def _check_java(runner: Runner, env: Mapping[str, str]) -> CheckResult:
    java = env.get("JAVA_HOME", "")
    command = [f"{java}/bin/java", "-version"] if java else ["java", "-version"]
    code, out = runner.run(command)
    match = re.search(r'version "(\d+)', out)
    major = int(match.group(1)) if match and match.group(1).isdigit() else None
    if code == 0 and major is not None and major >= 21:
        return _ok("java", f"JDK {major} (firebase emulators need >= 21)", (LANE_BACKEND,))
    return _agent(
        "java",
        f"JDK 21+ required for firebase emulators, detected major={major}",
        "brew install --cask temurin@21 (or set JAVA_HOME to an existing JDK 21) and export JAVA_HOME",
        (LANE_BACKEND,),
    )


def _check_firebase_cli(runner: Runner) -> CheckResult:
    binary = runner.which("firebase")
    if binary is None:
        return _agent(
            "firebase-cli",
            "firebase CLI missing (emulators for Auth/Firestore)",
            "npm install -g firebase-tools",
            (LANE_BACKEND,),
        )
    code, out = runner.run([binary, "--version"])
    version = out.strip().splitlines()[0] if out.strip() else "unknown"
    return _ok("firebase-cli", f"firebase-tools {version}", (LANE_BACKEND,))


def _check_datastore(repo_root: Path, runner: Runner, env: Mapping[str, str]) -> list[CheckResult]:
    """Redis + Typesense readiness (native binary or docker per harness runtime)."""

    results: list[CheckResult] = []
    redis = runner.which("redis-server")
    if redis:
        results.append(_ok("redis", f"redis-server at {redis}", (LANE_BACKEND,)))
    else:
        results.append(_agent("redis", "redis-server not found", "brew install redis (user-space)", (LANE_BACKEND,)))
    typesense = env.get("OMI_TYPESENSE_SERVER_BIN", "").strip() or runner.which("typesense-server")
    docker = runner.which("docker")
    if typesense:
        results.append(_ok("typesense", f"native typesense-server at {typesense}", (LANE_BACKEND,)))
    elif docker:
        code, out = runner.run([docker, "info", "--format", "{{.ServerVersion}}"])
        if code == 0 and out.strip():
            results.append(_ok("typesense", f"via docker daemon {out.strip()}", (LANE_BACKEND,)))
        else:
            results.append(
                _operator(
                    "typesense",
                    "docker CLI present but daemon not responding; no native typesense-server either",
                    "Start Docker Desktop/colima, or brew install typesense (native) — host-level service",
                    (LANE_BACKEND,),
                )
            )
    else:
        results.append(
            _agent(
                "typesense",
                "neither typesense-server nor docker found",
                "brew install typesense, or install docker for the cached 27.1 image route",
                (LANE_BACKEND,),
            )
        )
    return results


def _android_home(env: Mapping[str, str]) -> str:
    for key in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        value = env.get(key, "").strip()
        if value:
            return value
    return ""


def installed_android_system_image(
    home: Path,
    *,
    exists: Callable[[Path], bool] | None = None,
    list_output: str = "",
) -> str:
    """Return a semicolon package id if an emulator system image is present.

    Prefer the on-disk tree. ``sdkmanager --list_installed`` on cmdline-tools
    23 prints slash paths (``system-images/android-36/google_apis/arm64-v8a``)
    and can miss a fully unpacked image; treating that output as the only
    oracle reported ``android-image: no system-images package installed``.
    Parse stdout even when the process is noisy: a slash or semicolon token
    still proves presence. Callers that got a nonzero exit and an empty
    result must report *undetermined*, not absence.
    """

    probe = exists or (lambda path: Path(path).exists())
    disk = Path(home).joinpath(*PREFERRED_ANDROID_IMAGE_DIR)
    if probe(disk):
        return PREFERRED_ANDROID_IMAGE
    for line in list_output.splitlines():
        token = line.strip().split()[0] if line.strip() else ""
        normalized = token.replace("/", ";")
        if normalized.startswith(_ANDROID_IMAGE_PREFIX):
            return normalized
    return ""


def _check_android(repo_root: Path, runner: Runner, env: Mapping[str, str]) -> list[CheckResult]:
    results: list[CheckResult] = []
    home = _android_home(env)
    if not home or not runner.exists(Path(home)):
        results.append(
            _agent(
                "android-sdk",
                "ANDROID_HOME/ANDROID_SDK_ROOT not set to an existing SDK",
                "export ANDROID_HOME=<sdk> ANDROID_SDK_ROOT=$ANDROID_HOME (scripts/dev-harness doctor "
                "does not guess a location)",
                (LANE_ANDROID,),
            )
        )
        return results
    results.append(_ok("android-sdk", f"ANDROID_HOME={home}", (LANE_ANDROID,)))

    adb = Path(home) / "platform-tools" / "adb"
    if runner.exists(adb):
        results.append(_ok("android-adb", f"adb at {adb}", (LANE_ANDROID,)))
    else:
        results.append(
            _agent(
                "android-adb",
                "platform-tools/adb missing",
                f"sdkmanager --sdk_root={home} 'platform-tools' 'platforms;android-36'",
                (LANE_ANDROID,),
            )
        )

    emulator = Path(home) / "emulator" / "emulator"
    if runner.exists(emulator):
        results.append(_ok("android-emulator", f"emulator binary at {emulator}", (LANE_ANDROID,)))
    else:
        results.append(
            _agent(
                "android-emulator",
                "emulator engine missing (requires cmdline-tools)",
                f"sdkmanager --sdk_root={home} 'cmdline-tools;latest' 'emulator' — capacity-gated: "
                f"needs multiple GiB free before downloading",
                (LANE_ANDROID,),
            )
        )

    sdkmanager = Path(home) / "cmdline-tools" / "latest" / "bin" / "sdkmanager"
    list_code: int | None = None
    list_output = ""
    if runner.exists(sdkmanager):
        list_code, list_output = runner.run([str(sdkmanager), "--list_installed"], timeout=60.0)
    image = installed_android_system_image(Path(home), exists=runner.exists, list_output=list_output)
    if image:
        results.append(_ok("android-image", f"system image installed: {image}", (LANE_ANDROID,)))
    elif list_code is None:
        results.append(
            _agent(
                "android-image",
                "cannot determine Android system image: cmdline-tools missing, so no sdkmanager "
                "(not a finding that the image is absent)",
                f"Install cmdline-tools under {home} first (see android-emulator remedy)",
                (LANE_ANDROID,),
            )
        )
    elif list_code != 0:
        snippet = " ".join(list_output.split())[:180]
        results.append(
            _operator(
                "android-image",
                "cannot determine Android system image: "
                f"sdkmanager --list_installed exited {list_code}"
                + (f" ({snippet})" if snippet else "")
                + " (not a finding that the image is absent)",
                "Inspect sdkmanager / JAVA_HOME; a noisy or failed inventory is not a missing engine. "
                f"On-disk oracle is {Path(home).joinpath(*PREFERRED_ANDROID_IMAGE_DIR)}",
                (LANE_ANDROID,),
            )
        )
    else:
        results.append(
            _agent(
                "android-image",
                "no system-images package installed",
                f"{sdkmanager} '{PREFERRED_ANDROID_IMAGE}' — ARM64 image on Apple "
                f"Silicon; capacity-gated download (~5-8GiB with caches)",
                (LANE_ANDROID,),
            )
        )
    return results


def _check_ios(repo_root: Path, runner: Runner) -> list[CheckResult]:
    results: list[CheckResult] = []
    xcodebuild = runner.which("xcodebuild")
    if xcodebuild is None:
        results.append(
            _operator(
                "xcode",
                "xcodebuild not found",
                "Install Xcode (Mac App Store / developer downloads) — host operator install",
                (LANE_IOS,),
            )
        )
        return results
    code, out = runner.run([xcodebuild, "-version"])
    version = out.strip().splitlines()[0] if out.strip() else "unknown"
    if code != 0:
        results.append(
            _operator(
                "xcode",
                "xcodebuild -version failed (first-launch/license?)",
                "Accept the Xcode license / complete first launch",
                (LANE_IOS,),
            )
        )
    else:
        results.append(_ok("xcode", version, (LANE_IOS,)))

    simctl = runner.which("simctl") or "/usr/bin/xcrun"
    code, out = runner.run(["xcrun", "simctl", "list", "runtimes"])
    runtimes = [line.strip() for line in out.splitlines() if line.strip().startswith("iOS ")]
    if code == 0 and runtimes:
        results.append(_ok("ios-runtime", runtimes[0], (LANE_IOS,)))
    else:
        results.append(
            _operator(
                "ios-runtime",
                "no iOS simulator runtime installed",
                "xcodebuild -downloadPlatform iOS (multi-GiB download — coordinate host capacity first)",
                (LANE_IOS,),
            )
        )
    _ = simctl
    return results


def _check_capacity(repo_root: Path, runner: Runner, env: Mapping[str, str], min_free_gb: float) -> CheckResult:
    from . import safety

    base = safety.default_state_base(Path(repo_root), env)
    base.mkdir(parents=True, exist_ok=True)
    free_gb = runner.free_bytes(base) / (1000**3)
    if free_gb >= min_free_gb:
        return _ok(
            "disk-capacity",
            f"{free_gb:.1f}GiB free on the shared Data/scratch container (>= {min_free_gb:.0f}GiB required)",
            (LANE_ANDROID, LANE_IOS),
        )
    return _operator(
        "disk-capacity",
        f"{free_gb:.1f}GiB free < {min_free_gb:.0f}GiB required for emulator/build lanes",
        "Host capacity action: free space or approve the install size; agents must not delete unrelated assets. "
        "Contract/unit lanes continue without it.",
        (LANE_ANDROID, LANE_IOS),
    )


def parse_dotenv_assignments(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines; last assignment wins. Quotes are stripped."""

    values: dict[str, str] = {}
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def is_loopback_api_base(raw: str | None) -> bool:
    """Empty (unset) or loopback host. LAN and public hosts fail closed."""

    text = (raw or "").strip().strip("\"'")
    if not text:
        return True
    parsed = urlparse(text if "://" in text else f"http://{text}")
    host = (parsed.hostname or "").lower()
    return host in LOOPBACK_HOSTS


def _check_app_pairing(env: Mapping[str, str]) -> CheckResult:
    profile = env.get("OMI_APP_PROFILE", "").strip()
    flavor = env.get("OMI_APP_FLAVOR", "").strip()
    if profile and profile != HERMETIC_PROFILE:
        return _operator(
            "app-pairing",
            f"OMI_APP_PROFILE={profile!r} is not {HERMETIC_PROFILE}; session/test lanes only allow "
            f"flavor {HERMETIC_FLAVOR} + profile {HERMETIC_PROFILE}",
            f"Unset OMI_APP_PROFILE (or set it to {HERMETIC_PROFILE}); the doctor will not rewrite app/.dev.env",
            (LANE_BACKEND, LANE_ANDROID, LANE_IOS),
        )
    if flavor and flavor != HERMETIC_FLAVOR:
        return _operator(
            "app-pairing",
            f"OMI_APP_FLAVOR={flavor!r} is not {HERMETIC_FLAVOR}; session/test lanes only allow "
            f"flavor {HERMETIC_FLAVOR} + profile {HERMETIC_PROFILE}",
            f"Unset OMI_APP_FLAVOR (or set it to {HERMETIC_FLAVOR}); the doctor will not rewrite app/.dev.env",
            (LANE_BACKEND, LANE_ANDROID, LANE_IOS),
        )
    return _ok(
        "app-pairing",
        f"flavor {HERMETIC_FLAVOR} + profile {HERMETIC_PROFILE} "
        f"(OMI_APP_FLAVOR={flavor or 'unset'}, OMI_APP_PROFILE={profile or 'unset'})",
        (LANE_BACKEND, LANE_ANDROID, LANE_IOS),
    )


def _check_app_dev_env(repo_root: Path) -> CheckResult:
    env_file = Path(repo_root) / "app" / ".dev.env"
    if not env_file.is_file():
        return _ok(
            "app-dev-env",
            "app/.dev.env absent; hermetic bootstrap will write an empty API_BASE_URL",
            (LANE_BACKEND, LANE_ANDROID, LANE_IOS),
        )
    api = parse_dotenv_assignments(env_file).get("API_BASE_URL", "")
    if is_loopback_api_base(api):
        return _ok(
            "app-dev-env",
            "app/.dev.env API_BASE_URL is empty or loopback",
            (LANE_BACKEND, LANE_ANDROID, LANE_IOS),
        )
    return _operator(
        "app-dev-env",
        f"app/.dev.env API_BASE_URL={api!r} is not loopback; hermetic tests/sessions must not send traffic there",
        "Point API_BASE_URL at empty or http://127.0.0.1:... yourself; the doctor will not rewrite this file",
        (LANE_BACKEND, LANE_ANDROID, LANE_IOS),
    )


def _check_egress_env(repo_root: Path, env: Mapping[str, str]) -> CheckResult:
    api = env.get("OMI_LOCAL_API_BASE_URL", "").strip()
    if api and api.startswith("https://"):
        return _operator(
            "egress-env",
            f"OMI_LOCAL_API_BASE_URL={api!r} points off-loopback; session lane must not send traffic there",
            "Unset the production override for session lanes; the session CLI pins loopback endpoints itself",
            (LANE_BACKEND, LANE_ANDROID, LANE_IOS),
        )
    return _ok(
        "egress-env",
        "no production API override in the environment; session endpoints are loopback-pinned",
        (LANE_BACKEND, LANE_ANDROID, LANE_IOS),
    )


def run_doctor(
    repo_root: Path,
    env: Mapping[str, str] | None = None,
    runner: Runner | None = None,
    *,
    platforms: Sequence[str] = (LANE_BACKEND,),
    min_free_gb: float = MIN_FREE_GB_EMULATOR_LANES,
    skip_capacity: bool = False,
) -> DoctorReport:
    source = dict(os.environ if env is None else env)
    probe = runner or Runner()
    wanted_lanes = {LANE_BACKEND, *(p for p in platforms if p in (LANE_ANDROID, LANE_IOS))}
    root = Path(repo_root)

    checks: list[CheckResult] = [
        _check_git(root, probe),
        _check_python311(root, probe, source),
        _check_backend_venv(root, probe),
        _check_backend_runtime(root, probe),
        _check_flutter(root, probe),
        _check_java(probe, source),
        _check_firebase_cli(probe),
        _check_egress_env(root, source),
        _check_app_pairing(source),
        _check_app_dev_env(root),
    ]
    checks.extend(_check_datastore(root, probe, source))
    if LANE_ANDROID in wanted_lanes:
        checks.extend(_check_android(root, probe, source))
    if LANE_IOS in wanted_lanes:
        checks.extend(_check_ios(root, probe))
    if not skip_capacity and wanted_lanes & {LANE_ANDROID, LANE_IOS}:
        checks.append(_check_capacity(root, probe, source, min_free_gb))

    relevant = [check for check in checks if set(check.lanes) & wanted_lanes]
    if any(check.status == OPERATOR for check in relevant):
        overall = "blocked"
    elif any(check.status == AGENT_REMEDIABLE for check in relevant):
        overall = "degraded"
    else:
        overall = "ready"
    return DoctorReport(overall=overall, checks=tuple(checks))


def format_report_text(report: DoctorReport) -> str:
    lines = [f"overall: {report.overall}"]
    for check in report.checks:
        suffix = "" if check.status == READY else f" — {check.remedy}"
        lines.append(f"[{check.status:>22}] {check.check}: {check.detail}{suffix}")
    return "\n".join(lines)
