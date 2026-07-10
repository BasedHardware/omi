"""CLI implementation for top-level local dev harness make commands."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable

from . import config, providers, safety, memory_scenarios

OWNERSHIP_PREFIX = "omi-dev-harness"
SERVICE_PORTS = {
    "firestore": config.FIRESTORE_PORT,
    "auth": config.AUTH_PORT,
    "redis": config.REDIS_PORT,
    "typesense": config.TYPESENSE_PORT,
    "backend": config.BACKEND_PORT,
    "desktop-backend": config.DESKTOP_BACKEND_PORT,
}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _repo_root() -> Path:
    return config.repo_root_from(Path.cwd())


def _marker(cfg: config.HarnessConfig, service: str) -> str:
    return f"{OWNERSHIP_PREFIX}:{cfg.instance}:{service}"


def _load_json(path: Path, default: dict[str, object]) -> dict[str, object]:
    if not path.is_file():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default
    return data if isinstance(data, dict) else default


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _json_digest(data: object) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _process_records(cfg: config.HarnessConfig) -> list[dict[str, object]]:
    records = _load_json(cfg.layout.process_manifest, {"processes": []}).get("processes", [])
    return records if isinstance(records, list) else []


def _port_records(cfg: config.HarnessConfig) -> list[dict[str, object]]:
    records = _load_json(cfg.layout.port_manifest, {"ports": []}).get("ports", [])
    return records if isinstance(records, list) else []


def _save_manifests(cfg: config.HarnessConfig, records: list[dict[str, object]]) -> None:
    live = [record for record in records if safety.process_exists(int(record.get("pid", -1)))]
    _write_json(cfg.layout.process_manifest, {"schema_version": 1, "updated_at": _now(), "processes": live})
    ports = [
        {"service": record["service"], "port": record["port"], "pid": record["pid"], "endpoint": record.get("endpoint")}
        for record in live
        if "port" in record
    ]
    _write_json(cfg.layout.port_manifest, {"schema_version": 1, "updated_at": _now(), "ports": ports})


def _port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _service_record(cfg: config.HarnessConfig, service: str) -> dict[str, object] | None:
    for record in _process_records(cfg):
        if record.get("service") == service and safety.process_exists(int(record.get("pid", -1))):
            return record
    return None


def _typesense_container_running(cfg: config.HarnessConfig) -> bool:
    result = subprocess.run(
        [
            "docker",
            "ps",
            "--filter",
            f"name={_typesense_container_name(cfg)}",
            "--filter",
            "status=running",
            "-q",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return bool(result.stdout.strip())


def _service_health(cfg: config.HarnessConfig, service: str) -> tuple[bool, str]:
    if service == "redis":
        if _port_open("127.0.0.1", cfg.redis_port):
            return True, "port-open"
        return False, "port-closed"
    if service == "firestore":
        return _http_ok(f"http://{cfg.firestore_host}/")
    if service == "auth":
        return _http_ok(f"http://{cfg.auth_host}/")
    if service == "typesense":
        url = f"http://127.0.0.1:{config.TYPESENSE_PORT}/collections"
        headers = {"X-TYPESENSE-API-KEY": config.LOCAL_TYPESENSE_API_KEY}
        ok, detail = _http_ok(url, headers=headers)
        if ok:
            return True, detail
        if not _typesense_container_running(cfg):
            return False, "container-not-running"
        return False, detail
    if service == "backend":
        return _http_ok(f"{cfg.backend_url}/docs")
    if service == "desktop-backend":
        return _http_ok(f"{cfg.desktop_backend_url}/health")
    return False, f"unknown service {service!r}"


def _stop_single_service(cfg: config.HarnessConfig, record: dict[str, object]) -> None:
    pid = int(record.get("pid", -1))
    service = str(record.get("service"))
    if not safety.process_exists(pid):
        return
    try:
        safety.validate_owned_pid(pid, process_manifest=cfg.layout.process_manifest, service=service)
        _signal_owned_process_group(pid, service)
    except safety.SafetyError as exc:
        print(f"{service}: not stopped before restart: {exc}")
        return
    if service == "typesense":
        _remove_stale_typesense_container(cfg)
    deadline = time.time() + 8
    while time.time() < deadline and safety.process_exists(pid):
        time.sleep(0.25)
    if safety.process_exists(pid):
        try:
            os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    remaining = [entry for entry in _process_records(cfg) if entry.get("service") != service]
    _save_manifests(cfg, remaining)


def _require_port_available_or_owned(cfg: config.HarnessConfig, service: str, port: int) -> None:
    if not _port_open("127.0.0.1", port):
        return
    record = _service_record(cfg, service)
    if record is None:
        raise RuntimeError(
            f"Port {port} for {service} is already in use by a foreign process. Stop it or set a separate local harness state/port before retrying."
        )
    safety.validate_port_owner(
        port,
        pid=int(record["pid"]),
        port_manifest=cfg.layout.port_manifest,
        process_manifest=cfg.layout.process_manifest,
        service=service,
    )


def _http_ok(url: str, timeout: float = 1.0, headers: dict[str, str] | None = None) -> tuple[bool, str]:
    try:
        request = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status < 500, f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        return exc.code < 500, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - health output should be actionable, not typed
        return False, str(exc)


def _which(name: str) -> bool:
    return shutil.which(name) is not None


def _python_importable(module: str) -> bool:
    return (
        subprocess.run(
            [sys.executable, "-c", f"import {module}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ).returncode
        == 0
    )


def prerequisite_report(cfg: config.HarnessConfig) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    warnings: list[str] = []
    if not _which("node"):
        missing.append("node (required by Firebase emulator CLI)")
    if not (_which("firebase") or _which("npx")):
        missing.append(
            "firebase-tools CLI or npx (install with npm install, npm install -g firebase-tools, or use npx)"
        )
    if not _which("java"):
        missing.append("java runtime (required by Firestore emulator)")
    if not _which("redis-server"):
        missing.append("redis-server (required for local Redis on loopback)")
    if not _which("docker"):
        missing.append("docker (required for local Typesense on loopback)")
    if not (cfg.repo_root / "firebase.json").is_file():
        missing.append("firebase.json at repo root")
    if not (cfg.repo_root / "firestore.rules").is_file():
        missing.append("firestore.rules at repo root")
    if not (cfg.repo_root / "firestore.indexes.json").is_file():
        missing.append("firestore.indexes.json at repo root")
    if not (cfg.repo_root / "backend" / "main.py").is_file():
        missing.append("backend/main.py")
    if not _python_importable("uvicorn"):
        missing.append("Python package uvicorn (install backend requirements before starting backend)")
    if not _which("cargo"):
        missing.append("cargo (required to build the Rust desktop backend)")
    provider_report = providers.provider_preflight(cfg.repo_root, env=config.preflight_env(cfg))
    missing.extend(provider_report.missing)
    warnings.extend(provider_report.warnings)
    if cfg.provider_mode == "offline":
        warnings.append(
            "PROVIDER_MODE=offline: external-provider credentials are stripped from child processes; local stack shape is preserved."
        )
    return missing, warnings


def print_config(cfg: config.HarnessConfig) -> None:
    print(f"instance: {cfg.instance}")
    print(f"provider_mode: {cfg.provider_mode}")
    print(f"state_root: {cfg.layout.state_root}")
    print(f"firebase_project: {cfg.project_id}")
    print(f"firestore_database: {cfg.database_id}")
    print(f"firestore_emulator: {cfg.firestore_host}")
    print(f"firebase_auth_emulator: {cfg.auth_host}")
    print(f"redis: {cfg.redis_host}:{cfg.redis_port}")
    print(f"typesense: 127.0.0.1:{config.TYPESENSE_PORT}")
    print(f"backend: {cfg.backend_url}")
    print(f"desktop_backend: {cfg.desktop_backend_url}")


def print_provider_status(cfg: config.HarnessConfig) -> providers.ProviderPreflight:
    parsed = config.parse_secrets_file(cfg)
    report = providers.provider_preflight(cfg.repo_root, env=config.preflight_env(cfg))
    print("provider_status:")
    for line in providers.status_lines(report):
        print(f"  {line}")
    if parsed.ignored_keys:
        print("secrets_file_ignored_keys:")
        for key in parsed.ignored_keys:
            print(f"  - {key} (harness injects this; remove from backend/.env.local-dev)")
    if parsed.sources:
        print("provider_credential_sources:")
        for key in sorted(parsed.sources):
            if key == "PROVIDER_MODE":
                print(f"  {key}: {parsed.sources[key]}")
            elif key in config.CORE_PROVIDER_ENV:
                print(f"  {key}: {parsed.sources[key]}")
    return report


def _git_metadata(repo_root: Path) -> dict[str, object]:
    def run_git(args: list[str]) -> str:
        result = subprocess.run(
            ["git", *args], cwd=repo_root, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"

    return {"commit": run_git(["rev-parse", "HEAD"]), "dirty": bool(run_git(["status", "--porcelain"]))}


def _current_scenario_manifest(cfg: config.HarnessConfig) -> dict[str, object] | None:
    current = cfg.layout.state_root / "manifests" / "memory-scenario-current.json"
    if current.is_file():
        data = _load_json(current, {})
        if data:
            return data
    manifests = sorted((cfg.layout.state_root / "manifests").glob("memory-scenario-*-seed.json"))
    if not manifests:
        return None
    latest = max(manifests, key=lambda path: path.stat().st_mtime)
    return _load_json(latest, {})


def _scenario_users_from_seed_manifest(cfg: config.HarnessConfig) -> list[str]:
    manifests = sorted((cfg.layout.state_root / "manifests").glob("memory-scenario-*-seed.json"))
    if not manifests:
        return []
    latest = max(manifests, key=lambda path: path.stat().st_mtime)
    data = _load_json(latest, {})
    operations = data.get("operations", [])
    if not isinstance(operations, list):
        return []
    users = [
        str(op.get("target"))
        for op in operations
        if isinstance(op, dict) and op.get("kind") == "auth" and op.get("action") == "upsert"
    ]
    return sorted(set(users))


def _summary_path(cfg: config.HarnessConfig) -> Path:
    return cfg.layout.reports_dir / "local-emulator-memory-session-summary.json"


def build_session_summary(cfg: config.HarnessConfig, provider_report: providers.ProviderPreflight) -> dict[str, object]:
    scenario = _current_scenario_manifest(cfg) or {}
    config_digest = _load_json(cfg.layout.config_digest_path, {})
    endpoints = {
        "firestore": cfg.firestore_host,
        "firebase_auth": cfg.auth_host,
        "redis": f"{cfg.redis_host}:{cfg.redis_port}",
        "typesense": f"127.0.0.1:{config.TYPESENSE_PORT}",
        "backend": cfg.backend_url,
        "desktop_backend": cfg.desktop_backend_url,
    }
    return {
        "schema_version": 1,
        "evidence_class": "LOCAL_EMULATOR_DEV",
        "activation_eligible": False,
        "watermark": "NOT_ACTIVATION_EVIDENCE",
        "generated_at": _now(),
        "instance": cfg.instance,
        "state_root": str(cfg.layout.state_root),
        "firebase_project_id": cfg.project_id,
        "firestore_database_id": cfg.database_id,
        "provider_mode": cfg.provider_mode,
        "enabled_external_providers": list(provider_report.enabled_external_providers),
        "credential_fingerprints": dict(provider_report.fingerprints),
        "offline_fake_sources": dict(provider_report.offline_fake_sources),
        "local_endpoints": endpoints,
        "scenario_id": scenario.get("scenario_id"),
        "scenario_digest": scenario.get("scenario_digest"),
        "selected_user": scenario.get("selected_user"),
        "seeded_users": _scenario_users_from_seed_manifest(cfg),
        "git": _git_metadata(cfg.repo_root),
        "config_digest": _json_digest(config_digest) if config_digest else None,
        "session_budget": {
            "session_usd": providers.DEFAULT_SESSION_BUDGET_USD,
            "day_usd": providers.DEFAULT_DAILY_BUDGET_USD,
            "concurrency": providers.DEFAULT_MAX_CONCURRENCY,
        },
        "external_provider_call_summary": {
            "instrumented": False,
            "placeholder": "Provider broker policy is present; live per-call accounting is not wired in this manual-QA slice.",
        },
        "memory_write_attempt_instrumentation": {
            "instrumented": False,
            "placeholder": "Firestore adapter/client-boundary write-attempt counters are reserved for the live desktop/backend instrumentation slice.",
            "attempted_write_count": None,
            "blocked_write_count": None,
        },
        "protected_state_digest": {
            "computed": False,
            "before_digest": None,
            "after_digest": None,
            "placeholder": "Protected-collection before/after digests are not computed unless a live emulator readback instrumenter is added.",
        },
        "manual_qa": {
            "framing": "Exploratory product-use workflow; not a deterministic long-lived pass/fail product test suite.",
            "status": "not_asserted_by_harness",
            "notes": [],
        },
        "non_claims": [
            "Not DEV_CLOUD_PROOF.",
            "Not production, dev-cloud, IAM, deployed index, telemetry sink, rollback, or activation proof.",
            "Does not imply prod/dev-cloud memory activation eligibility.",
        ],
    }


def write_session_summary(cfg: config.HarnessConfig, provider_report: providers.ProviderPreflight) -> Path:
    path = _summary_path(cfg)
    _write_json(path, build_session_summary(cfg, provider_report))
    return path


def cmd_check(args: argparse.Namespace) -> int:
    cfg = config.load_config(_repo_root(), create_layout=False)
    missing, warnings = prerequisite_report(cfg)
    print("Omi local dev harness prerequisite check")
    print_config(cfg)
    print_provider_status(cfg)
    if warnings:
        print("\nWarnings:")
        for item in warnings:
            print(f"  - {item}")
    if missing:
        print("\nMissing prerequisites:")
        for item in missing:
            print(f"  - {item}")
        return 1
    print("\nAll required prerequisites for this mode are present.")
    return 0


def _start_process(
    cfg: config.HarnessConfig,
    service: str,
    command: list[str],
    *,
    cwd: Path,
    log_name: str,
    port: int,
    env: dict[str, str] | None = None,
) -> None:
    existing = _service_record(cfg, service)
    if existing is not None:
        healthy, detail = _service_health(cfg, service)
        if healthy:
            print(f"{service}: already recorded as running")
            return
        print(f"{service}: recorded process unhealthy ({detail}); restarting")
        _stop_single_service(cfg, existing)
    _require_port_available_or_owned(cfg, service, port)
    marker = _marker(cfg, service)
    log_path = cfg.layout.logs_dir / log_name
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("ab")
    child_env = config.child_env_for(cfg) if env is None else env
    child_env["PYTHONPATH"] = f"{cfg.repo_root / 'scripts' / 'dev-harness'}:{child_env.get('PYTHONPATH', '')}"
    if service == "backend":
        child_env["PYTHONPATH"] = (
            f"{cfg.repo_root / 'scripts' / 'dev-harness'}:{cfg.repo_root / 'backend'}:{child_env.get('PYTHONPATH', '')}"
        )
    supervised = [
        sys.executable,
        "-m",
        "dev_harness.supervise",
        "--marker",
        marker,
        "--service",
        service,
        "--",
        *command,
    ]
    proc = subprocess.Popen(
        supervised, cwd=str(cwd), env=child_env, stdout=log_file, stderr=subprocess.STDOUT, start_new_session=True
    )
    records = [record for record in _process_records(cfg) if record.get("service") != service]
    records.append(
        {
            "service": service,
            "pid": proc.pid,
            "port": port,
            "endpoint": f"127.0.0.1:{port}",
            "log": str(log_path),
            "ownership_marker": marker,
            "started_at": _now(),
            "command": command,
        }
    )
    _save_manifests(cfg, records)
    print(f"{service}: started pid={proc.pid} log={log_path}")


def _desktop_backend_dir(cfg: config.HarnessConfig) -> Path:
    return cfg.repo_root / "desktop" / "macos" / "Backend-Rust"


def _ensure_desktop_backend_binary(cfg: config.HarnessConfig) -> Path:
    backend_dir = _desktop_backend_dir(cfg)
    release = os.environ.get("OMI_DESKTOP_BACKEND_RELEASE", "").strip() in {"1", "true", "yes"}
    profile = "release" if release else "debug"
    binary = backend_dir / "target" / profile / "omi-desktop-backend"
    stale_markers = ("src", "Cargo.toml", "Cargo.lock")

    def _is_stale(marker: str) -> bool:
        path = backend_dir / marker
        if not path.exists():
            return False
        if path.is_file():
            return path.stat().st_mtime > binary.stat().st_mtime
        newer = subprocess.run(
            ["find", str(path), "-newer", str(binary)],
            cwd=backend_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        return bool(newer.stdout.strip())

    if binary.is_file() and not any(_is_stale(marker) for marker in stale_markers):
        return binary
    build_cmd = ["cargo", "build"]
    if release:
        build_cmd.append("--release")
    print(f"desktop-backend: building ({' '.join(build_cmd)})...")
    subprocess.run(build_cmd, cwd=backend_dir, check=True)
    return binary


def _firebase_command(cfg: config.HarnessConfig) -> list[str]:
    base = ["firebase"] if _which("firebase") else ["npx", "firebase-tools"]
    return [
        *base,
        "emulators:start",
        "--only",
        "firestore,auth",
        "--project",
        cfg.project_id,
        "--import",
        str(cfg.layout.services_dir / "firebase-export"),
        "--export-on-exit",
        str(cfg.layout.services_dir / "firebase-export"),
    ]


def _typesense_container_name(cfg: config.HarnessConfig) -> str:
    return f"{OWNERSHIP_PREFIX}-{cfg.instance}-typesense"


def _remove_stale_typesense_container(cfg: config.HarnessConfig) -> None:
    container = _typesense_container_name(cfg)
    subprocess.run(
        ["docker", "rm", "-f", container],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def _typesense_command(cfg: config.HarnessConfig) -> list[str]:
    typesense_dir = cfg.layout.services_dir / "typesense"
    typesense_dir.mkdir(parents=True, exist_ok=True)
    return [
        "docker",
        "run",
        "--rm",
        "--name",
        _typesense_container_name(cfg),
        "-p",
        f"127.0.0.1:{config.TYPESENSE_PORT}:{config.TYPESENSE_PORT}",
        "-v",
        f"{typesense_dir}:/data",
        "typesense/typesense:27.1",
        "--data-dir",
        "/data",
        "--api-key",
        config.LOCAL_TYPESENSE_API_KEY,
        "--enable-cors",
    ]


def _start_services(cfg: config.HarnessConfig) -> None:
    cfg.layout.logs_dir.mkdir(parents=True, exist_ok=True)
    _start_process(
        cfg,
        "firestore",
        _firebase_command(cfg),
        cwd=cfg.repo_root,
        log_name="firebase-emulators.log",
        port=config.FIRESTORE_PORT,
    )
    redis_dir = cfg.layout.services_dir / "redis"
    redis_dir.mkdir(parents=True, exist_ok=True)
    _start_process(
        cfg,
        "redis",
        [
            "redis-server",
            "--bind",
            "127.0.0.1",
            "--port",
            str(cfg.redis_port),
            "--dir",
            str(redis_dir),
            "--save",
            "",
            "--appendonly",
            "no",
        ],
        cwd=cfg.repo_root,
        log_name="redis.log",
        port=cfg.redis_port,
    )
    _remove_stale_typesense_container(cfg)
    _start_process(
        cfg,
        "typesense",
        _typesense_command(cfg),
        cwd=cfg.repo_root,
        log_name="typesense.log",
        port=config.TYPESENSE_PORT,
    )
    _start_process(
        cfg,
        "backend",
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(config.BACKEND_PORT)],
        cwd=cfg.repo_root / "backend",
        log_name="backend.log",
        port=config.BACKEND_PORT,
    )
    desktop_binary = _ensure_desktop_backend_binary(cfg)
    _start_process(
        cfg,
        "desktop-backend",
        [str(desktop_binary)],
        cwd=_desktop_backend_dir(cfg),
        log_name="desktop-backend.log",
        port=config.DESKTOP_BACKEND_PORT,
        env=config.desktop_backend_child_env_for(cfg),
    )


def _wait_health(cfg: config.HarnessConfig, *, timeout: float = 45.0) -> list[str]:
    typesense_headers = {"X-TYPESENSE-API-KEY": config.LOCAL_TYPESENSE_API_KEY}
    checks = {
        "firestore": (f"http://{cfg.firestore_host}/", None),
        "auth": (f"http://{cfg.auth_host}/", None),
        "typesense": (f"http://127.0.0.1:{config.TYPESENSE_PORT}/collections", typesense_headers),
        "backend": (f"{cfg.backend_url}/docs", None),
        "desktop-backend": (f"{cfg.desktop_backend_url}/health", None),
    }
    pending = dict(checks)
    deadline = time.time() + timeout
    failures: dict[str, str] = {}
    while pending and time.time() < deadline:
        for service, (url, headers) in list(pending.items()):
            ok, detail = _http_ok(url, headers=headers)
            if ok:
                print(f"{service}: healthy ({detail})")
                pending.pop(service)
            else:
                failures[service] = detail
        if pending:
            time.sleep(0.75)
    for service, (url, _) in pending.items():
        failures.setdefault(service, f"not healthy at {url}")
    return [f"{service}: {failures.get(service, 'unknown failure')}" for service in pending]


def cmd_up(args: argparse.Namespace) -> int:
    cfg = config.load_config(_repo_root(), create_layout=True)
    missing, warnings = prerequisite_report(cfg)
    print("Omi local dev harness startup")
    print_config(cfg)
    provider_report = print_provider_status(cfg)
    for item in warnings:
        print(f"warning: {item}")
    if missing:
        print("\nCannot start; missing prerequisites:")
        for item in missing:
            print(f"  - {item}")
        return 1
    _write_json(
        cfg.layout.config_digest_path,
        {
            "schema_version": 1,
            "updated_at": _now(),
            "project_id": cfg.project_id,
            "database_id": cfg.database_id,
            "provider_mode": cfg.provider_mode,
            "enabled_external_providers": list(provider_report.enabled_external_providers),
            "credential_fingerprints": dict(provider_report.fingerprints),
            "offline_fake_sources": dict(provider_report.offline_fake_sources),
            "provider_budgets": {
                "session_usd": providers.DEFAULT_SESSION_BUDGET_USD,
                "day_usd": providers.DEFAULT_DAILY_BUDGET_USD,
                "concurrency": providers.DEFAULT_MAX_CONCURRENCY,
                "idempotent_retries": providers.DEFAULT_IDEMPOTENT_RETRIES,
                "non_idempotent_retries": providers.DEFAULT_NON_IDEMPOTENT_RETRIES,
                "automatic_replay_after_restart": False,
            },
            "instance": cfg.instance,
            "state_root": str(cfg.layout.state_root),
            "endpoints": {
                "firestore": cfg.firestore_host,
                "auth": cfg.auth_host,
                "redis": f"{cfg.redis_host}:{cfg.redis_port}",
                "typesense": f"127.0.0.1:{config.TYPESENSE_PORT}",
                "backend": cfg.backend_url,
                "desktop_backend": cfg.desktop_backend_url,
            },
        },
    )
    try:
        _start_services(cfg)
        failures = _wait_health(cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"dev-up failed: {exc}")
        return 1
    if failures:
        print("\nHealth checks failed:")
        for failure in failures:
            print(f"  - {failure}")
        print(f"Inspect logs with: make dev-logs OMI_LOCAL_STATE_ROOT={cfg.layout.state_root.parent}")
        return 1
    if _current_scenario_manifest(cfg) is None:
        try:
            memory_scenarios.seed_scenario("happy_path", cfg)
            print("auto-seeded scenario=happy_path (first run)")
        except Exception as exc:  # noqa: BLE001
            print(f"warning: auto-seed happy_path failed: {exc}")
    print("\nLocal dev harness is up.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    cfg = config.load_config(_repo_root(), create_layout=False)
    print("Omi local dev harness status")
    print_config(cfg)
    provider_report = print_provider_status(cfg)
    if cfg.provider_mode == "offline":
        print(
            "offline_hint: PROVIDER_MODE=offline active; external provider credentials are stripped from child processes"
        )
    else:
        print(
            "offline_hint: run with PROVIDER_MODE=offline for hermetic fake providers and no external provider credentials"
        )
    if not cfg.layout.sentinel_path.is_file():
        print("sentinel: missing (run make dev-up or make dev-reset to initialize harness-owned state)")
    else:
        safety.read_and_validate_sentinel(cfg.layout.state_root, repo_root=cfg.repo_root, instance=cfg.instance)
        print("sentinel: ok")
    scenario = _current_scenario_manifest(cfg)
    print("\nMemory manual-QA state:")
    if scenario:
        print(f"  scenario_id: {scenario.get('scenario_id')}")
        print(f"  scenario_digest: {scenario.get('scenario_digest')}")
        print(f"  selected_user: {scenario.get('selected_user')}")
        users = _scenario_users_from_seed_manifest(cfg)
        print(f"  seeded_users: {', '.join(users) if users else 'unknown'}")
    else:
        print(
            "  scenario_id: none (run make dev-up to auto-seed happy_path, or make seed-memory-scenario SCENARIO=happy_path)"
        )
        print("  seeded_users: none")
    print(f"  session_summary_path: {_summary_path(cfg)}")
    if getattr(args, "write_summary", False):
        path = write_session_summary(cfg, provider_report)
        print(f"  session_summary_written: {path}")
    print("\nProcesses:")
    records = _process_records(cfg)
    if not records:
        print("  - none recorded")
    for record in records:
        pid = int(record.get("pid", -1))
        alive = safety.process_exists(pid)
        health = "not checked"
        service = str(record.get("service"))
        port = int(record.get("port", 0) or 0)
        if port:
            health = "port-open" if _port_open("127.0.0.1", port) else "port-closed"
        print(f"  - {service}: pid={pid} alive={alive} {health} log={record.get('log')}")
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    cfg = config.load_config(_repo_root(), create_layout=False)
    provider_report = providers.provider_preflight(cfg.repo_root, env=config.preflight_env(cfg))
    if not cfg.layout.sentinel_path.is_file():
        print("Cannot write session summary: harness sentinel is missing (run make dev-up or make dev-reset first)")
        return 1
    safety.read_and_validate_sentinel(cfg.layout.state_root, repo_root=cfg.repo_root, instance=cfg.instance)
    path = write_session_summary(cfg, provider_report)
    print(path)
    return 0


def _signal_owned_process_group(pid: int, service: str) -> None:
    try:
        os.killpg(pid, signal.SIGINT)
        print(f"{service}: sent SIGINT to process group {pid}")
    except ProcessLookupError:
        return
    except PermissionError as exc:
        raise safety.SafetyError(f"Cannot signal process group {pid}: {exc}") from exc


def _stop_owned(cfg: config.HarnessConfig) -> None:
    records = _process_records(cfg)
    for record in records:
        pid = int(record.get("pid", -1))
        service = str(record.get("service"))
        if not safety.process_exists(pid):
            continue
        try:
            safety.validate_owned_pid(pid, process_manifest=cfg.layout.process_manifest, service=service)
            _signal_owned_process_group(pid, service)
        except safety.SafetyError as exc:
            print(f"{service}: not stopped: {exc}")
    deadline = time.time() + 8
    while time.time() < deadline and any(safety.process_exists(int(r.get("pid", -1))) for r in records):
        time.sleep(0.25)
    for record in records:
        pid = int(record.get("pid", -1))
        service = str(record.get("service"))
        if safety.process_exists(pid):
            try:
                safety.validate_owned_pid(pid, process_manifest=cfg.layout.process_manifest, service=service)
                os.killpg(pid, signal.SIGTERM)
                print(f"{service}: sent SIGTERM to process group {pid}")
            except (ProcessLookupError, safety.SafetyError) as exc:
                print(f"{service}: still running pid={pid}; leaving it for safety inspection: {exc}")
    deadline = time.time() + 5
    while time.time() < deadline and any(safety.process_exists(int(r.get("pid", -1))) for r in records):
        time.sleep(0.25)
    for record in records:
        pid = int(record.get("pid", -1))
        if safety.process_exists(pid):
            print(f"{record.get('service')}: still running pid={pid}; leaving it for safety inspection")
    _save_manifests(cfg, records)


def cmd_down(args: argparse.Namespace) -> int:
    cfg = config.load_config(_repo_root(), create_layout=False)
    if not cfg.layout.sentinel_path.is_file():
        print("No harness-owned state exists; nothing to stop.")
        return 0
    safety.read_and_validate_sentinel(cfg.layout.state_root, repo_root=cfg.repo_root, instance=cfg.instance)
    _stop_owned(cfg)
    return 0


def _clear_state(cfg: config.HarnessConfig) -> None:
    safety.read_and_validate_sentinel(cfg.layout.state_root, repo_root=cfg.repo_root, instance=cfg.instance)
    for child in ("manifests", "logs", "reports", "services", "files"):
        target = cfg.layout.state_root / child
        if target.exists():
            safety.validate_destructive_target(target, state_root=cfg.layout.state_root, repo_root=cfg.repo_root)
            shutil.rmtree(target)
    safety.create_state_layout(cfg.repo_root, cfg.instance, {"OMI_LOCAL_STATE_ROOT": str(cfg.layout.state_root.parent)})


def cmd_reset(args: argparse.Namespace) -> int:
    cfg = config.load_config(_repo_root(), create_layout=True)
    print(f"Resetting harness-owned state only: {cfg.layout.state_root}")
    safety.read_and_validate_sentinel(cfg.layout.state_root, repo_root=cfg.repo_root, instance=cfg.instance)
    _stop_owned(cfg)
    _clear_state(cfg)
    print("Reset complete.")
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    cfg = config.load_config(_repo_root(), create_layout=False)
    print(f"logs_dir: {cfg.layout.logs_dir}")
    for path in sorted(cfg.layout.logs_dir.glob("*.log")) if cfg.layout.logs_dir.is_dir() else []:
        print(f"\n==> {path} <==")
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]
        for line in lines:
            print(line)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dev-harness")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func in {
        "check": cmd_check,
        "up": cmd_up,
        "status": cmd_status,
        "summary": cmd_summary,
        "down": cmd_down,
        "reset": cmd_reset,
        "logs": cmd_logs,
    }.items():
        command = sub.add_parser(name)
        if name == "status":
            command.add_argument("--write-summary", action="store_true", default=False)
        command.set_defaults(func=func)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        return int(args.func(args))
    except safety.SafetyError as exc:
        print(f"Safety check failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
