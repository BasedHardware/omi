"""The processes of a prod-parity stack and the environment each one gets.

``prod_parity`` decides *which settings* each production service takes. This
module turns that into a running stack: one local process per production
service, the stand-ins for Cloud Tasks, Cloud Scheduler and the load balancer,
the batch speech worker, and the bindings (ports, emulators, storage folder,
local secrets) that the harness supplies in place of production's
infrastructure. ``dev_harness.cli`` starts what :func:`processes` returns.

See ``scripts/dev-harness/PROD_PARITY.md``.
"""

from __future__ import annotations

import json
import os
import secrets as _secrets
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values

from . import (
    batch_worker,
    config,
    edge_router,
    local_scheduler,
    local_task_queue,
    local_tls,
    log_timestamps,
    prod_parity,
    prod_snapshot,
    safety,
    voice_embedding,
)

# Production service -> harness process name. "backend" stays the name of whatever
# listens on the public port, which in this profile is the edge router.
SERVICE_PROCESSES = {
    "backend": "svc-backend",
    "backend-listen": "svc-listen",
    "backend-sync": "svc-sync",
    "backend-sync-backfill": "svc-sync-backfill",
    "backend-integration": "svc-integration",
}
# Loopback port of each service, as an offset from the public backend port.
SERVICE_PORT_OFFSETS = {
    "backend": 10,
    "backend-listen": 11,
    "backend-sync": 12,
    "backend-sync-backfill": 13,
    "backend-integration": 14,
}
BATCH_WORKER_PORT_OFFSET = 15
VOICE_EMBEDDING_PORT_OFFSET = 9
LOCAL_MEMORY_CURSOR_SECRET = "omi-local-dev-harness-memory-cursor-secret"
LOCAL_METRICS_SECRET = "omi-local-dev-harness-metrics-secret"
LOCAL_ENCRYPTION_SECRET = "omi_local_dev_harness_32_byte_test_secret_not_prod"
BATCH_WORKER_PYTHON = Path("backend") / ".venv-eval" / "bin" / "python"
ROLLOUT_RAMP_WAIT_SECONDS = 45.0

# The rollout document (Firestore ``rollout_cohorts/_ramp``) decides per account
# which pipeline serves it. Production's current values are operated outside git;
# a production snapshot carries them. Without a snapshot these are what the
# tracked files say production runs: batch at 100% with live speech-to-text not
# retired (charts/batch-pipeline-worker prod values), and the legacy sync lane
# dark (deploy/ops/prod.yaml, backend-sync). Edit the document in the emulator to
# study another rollout state; the harness only rewrites a document it wrote.
PRODUCTION_RAMP = {
    "percents": {"batch-pipeline": 100, "legacy-sync": 100, "batch-live-stt-retire": 0, "batch-vendor-routing": 0},
    "legacy_sync": "dark",
}


@dataclass(frozen=True)
class Process:
    """One supervised process of the stack."""

    name: str
    command: list[str]
    cwd: Path
    port: int  # 0: the process listens nowhere
    env: dict[str, str] | None = None  # None: the harness's default child environment
    backend_import: bool = False  # the backend package must be importable


def enabled(env: Mapping[str, str] | None = None) -> bool:
    return prod_parity.enabled(env)


def production_snapshot() -> prod_snapshot.Snapshot | None:
    return prod_snapshot.load_active()


def ports(cfg: config.HarnessConfig) -> dict[str, int]:
    """Loopback port of every production service; the public port stays ``backend_port`` (the edge router)."""
    result = {service: cfg.backend_port + offset for service, offset in SERVICE_PORT_OFFSETS.items()}
    result["pusher"] = cfg.pusher_port
    return result


def topology(cfg: config.HarnessConfig) -> prod_parity.Topology:
    return prod_parity.Topology(
        project_id=cfg.project_id,
        database_id=cfg.database_id,
        ports=ports(cfg),
        llm_gateway_url=cfg.llm_gateway_url,
        redis_host=cfg.redis_host,
        redis_port=cfg.redis_port,
        voice_embedding_url=voice_embedding_url(cfg) if voice_embedding_unavailable(cfg) is None else "",
    )


def tls(cfg: config.HarnessConfig) -> local_tls.LocalTls:
    """Certificate and trust file for the stack's HTTPS service stand-ins."""
    return local_tls.ensure(cfg.layout.services_dir / "tls")


def _trust_env(cfg: config.HarnessConfig) -> dict[str, str]:
    bundle = str(tls(cfg).bundle)
    return {
        "SSL_CERT_FILE": bundle,  # stdlib ssl, httpx, aiohttp
        "REQUESTS_CA_BUNDLE": bundle,  # requests
        local_task_queue.CA_BUNDLE_ENV: bundle,  # harness transports that ignore the ambient environment
    }


# Homebrew keeps libopus outside dyld's default search path, and the allowlisted
# child environment drops any path the developer's shell exported. Without it
# opuslib cannot load, and every Opus listen session (the pendant's codec) ends
# at "Codec decoder initialization failed".
_HOMEBREW_LIBRARY_DIRS = (Path("/opt/homebrew/lib"), Path("/usr/local/lib"))


def _native_library_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    source = os.environ if env is None else env
    if sys.platform != "darwin":
        return {}
    inherited = source.get("DYLD_FALLBACK_LIBRARY_PATH", "").strip()
    if inherited:
        return {"DYLD_FALLBACK_LIBRARY_PATH": inherited}
    for directory in _HOMEBREW_LIBRARY_DIRS:
        if any(directory.glob("libopus.*")):
            return {"DYLD_FALLBACK_LIBRARY_PATH": str(directory)}
    return {}


def task_queue_secret(cfg: config.HarnessConfig) -> str:
    """The stack's token secret for local task and scheduler deliveries (created once per state root)."""
    path = cfg.layout.services_dir / "tasks" / "secret"
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_secrets.token_urlsafe(32))
        path.chmod(0o600)
    return path.read_text().strip()


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        return max(1, int(raw)) if raw else default
    except ValueError as exc:
        raise safety.SafetyError(f"{name} must be an integer, got {raw!r}") from exc


def task_queue_env(cfg: config.HarnessConfig) -> dict[str, str]:
    """The one queue every service of the stack shares."""
    snapshot = production_snapshot()
    queues = local_task_queue.production_queue_settings(
        cfg.repo_root,
        _int_env(local_task_queue.CONCURRENCY_ENV, local_task_queue.DEFAULT_CONCURRENCY),
        live=snapshot.queues if snapshot else None,
    )
    return {
        local_task_queue.DB_ENV: str(cfg.layout.services_dir / "tasks" / "tasks.sqlite"),
        local_task_queue.SECRET_ENV: task_queue_secret(cfg),
        local_task_queue.SETTINGS_ENV: local_task_queue.encode_settings(queues),
    }


def _store_bindings(cfg: config.HarnessConfig) -> dict[str, str]:
    """Emulators, Redis and the storage folder: the same for every process that touches data."""
    return {
        **_native_library_env(),
        "PYTHONUNBUFFERED": "1",
        "ENVIRONMENT": "local-dev-harness",
        "OMI_HARNESS_INSTANCE": cfg.instance,
        "OMI_HARNESS_STATE_ROOT": str(cfg.layout.state_root),
        "OMI_LOCAL_STORAGE_ROOT": str(cfg.layout.services_dir / "storage"),
        "OMI_LOCAL_STORAGE_BASE_URL": f"{cfg.backend_public_url}/_local/storage",
        "FIRESTORE_EMULATOR_HOST": cfg.firestore_host,
        "FIREBASE_PROJECT_ID": cfg.project_id,
        "FIRESTORE_DATABASE_ID": cfg.database_id,
        "REDIS_DB_HOST": cfg.redis_host,
        "REDIS_DB_PORT": str(cfg.redis_port),
        "REDIS_DB_PASSWORD": "",
        "ENCRYPTION_SECRET": LOCAL_ENCRYPTION_SECRET,
    }


def bindings(cfg: config.HarnessConfig, service: str) -> dict[str, str]:
    """What the harness supplies to a production service: addresses, stores, secrets. No logic."""
    result = {
        **_store_bindings(cfg),
        "PORT": str(ports(cfg)[service]),
        "FIREBASE_AUTH_EMULATOR_HOST": cfg.auth_host,
        "FIREBASE_AUTH_PROJECT_ID": cfg.project_id,
        "FIREBASE_API_KEY": config.LOCAL_FIREBASE_API_KEY,
        "TYPESENSE_HOST": "127.0.0.1",
        "TYPESENSE_HOST_PORT": str(cfg.typesense_port),
        "TYPESENSE_API_KEY": config.LOCAL_TYPESENSE_API_KEY,
        "TYPESENSE_PROTOCOL": "http",
        "BASE_API_URL": cfg.backend_url,
        "API_BASE_URL": cfg.backend_url,
        "OMI_LLM_GATEWAY_URL": cfg.llm_gateway_url,
        "OMI_LLM_GATEWAY_SERVICE_TOKEN": cfg.llm_gateway_service_token,
        "ADMIN_KEY": "local-dev-admin-key-",
        "SCREEN_FRAME_SIGNING_SECRET": config.LOCAL_SCREEN_FRAME_SIGNING_SECRET,
        "MEMORY_V3_CURSOR_SECRET": LOCAL_MEMORY_CURSOR_SECRET,
        "METRICS_SECRET": LOCAL_METRICS_SECRET,
        **config.provider_secrets_from_file(cfg),
        **task_queue_env(cfg),
        **_trust_env(cfg),
    }
    if service != "pusher":
        result["HOSTED_PUSHER_API_URL"] = cfg.pusher_url
    return result


def _child_env(cfg: config.HarnessConfig, env: Mapping[str, str]) -> dict[str, str]:
    """The harness's allowlisted child environment, with cloud credentials and defaults stripped."""
    kept = {
        name: value
        for name, value in env.items()
        if name not in safety.STRIPPED_EXACT_ENV_KEYS and not name.startswith(safety.STRIPPED_ENV_PREFIXES)
    }
    return safety.build_child_env(provider_mode=cfg.provider_mode, extra=kept)


def service_env(cfg: config.HarnessConfig, service: str) -> dict[str, str]:
    """Environment of one production service on this stack: production's settings plus local bindings."""
    composed = prod_parity.compose(cfg.repo_root, topology(cfg))
    env = dict(composed[service])
    for name, value in config.LOCAL_STORAGE_BUCKET_ENV.items():
        env.setdefault(name, value)  # buckets production binds outside its declared settings
    if "STT_SERVICE_MODELS" not in env:
        # Cloud Run mounts the live chain from a secret; the listen chart declares the same chain.
        env["STT_SERVICE_MODELS"] = composed["backend-listen"]["STT_SERVICE_MODELS"]
    env.update(bindings(cfg, service))
    return _child_env(cfg, env)


def batch_worker_python(cfg: config.HarnessConfig) -> Path | None:
    """The separate model runtime, when the developer has built it."""
    path = cfg.repo_root / BATCH_WORKER_PYTHON
    return path if path.is_file() else None


def model_access_token(cfg: config.HarnessConfig) -> str:
    path = config.secrets_file_path(cfg)
    file_value = (dotenv_values(path).get(config.MODEL_ACCESS_TOKEN_ENV) or "") if path.is_file() else ""
    return file_value.strip() or os.environ.get(config.MODEL_ACCESS_TOKEN_ENV, "").strip()


def batch_worker_count() -> int:
    return _int_env(batch_worker.WORKERS_ENV, batch_worker.DEFAULT_WORKERS)


def batch_worker_unavailable(cfg: config.HarnessConfig) -> str | None:
    """Why the batch speech worker cannot start here, or None when it can."""
    if batch_worker_python(cfg) is None:
        return (
            f"no model runtime at {BATCH_WORKER_PYTHON} "
            "(build it from backend/scripts/diarization_eval/requirements-eval.txt)"
        )
    if not model_access_token(cfg):
        return (
            f"{config.MODEL_ACCESS_TOKEN_ENV} is not set in backend/.env.local-dev "
            "(production's speaker model is access-gated)"
        )
    return None


def batch_worker_env(cfg: config.HarnessConfig, index: int = 0) -> dict[str, str]:
    """One batch worker replica: production's worker settings, CPU sizing, the stack's stores and identity."""
    composed = prod_parity.compose(cfg.repo_root, topology(cfg))
    env = prod_parity.compose_batch_worker(cfg.repo_root, topology(cfg))
    env.update(batch_worker.CPU_SIZING)
    env.update(
        {
            **_store_bindings(cfg),
            "PORT": str(cfg.backend_port + BATCH_WORKER_PORT_OFFSET + index),
            # Each replica is one process; the index keeps its health port on loopback.
            "BATCH_PIPELINE_WORKER_PROCESS_INDEX": str(index),
            batch_worker.THREADS_ENV: str(max(2, (os.cpu_count() or 4) // (batch_worker_count() + 1))),
            config.MODEL_ACCESS_TOKEN_ENV: model_access_token(cfg),
            # Same account and bucket names as the services that admit and verify this worker.
            "BATCH_PIPELINE_WORKER_SERVICE_ACCOUNT": composed["backend-sync"]["BATCH_PIPELINE_WORKER_SERVICE_ACCOUNT"],
            "BUCKET_BATCH_PIPELINE": composed["backend-sync"]["BUCKET_BATCH_PIPELINE"],
            local_task_queue.SECRET_ENV: task_queue_secret(cfg),
            **_trust_env(cfg),
        }
    )
    return _child_env(cfg, env)


def voice_embedding_unavailable(cfg: config.HarnessConfig) -> str | None:
    """Why the speaker-embedding service cannot start here, or None when it can. It shares the batch worker's
    model runtime and model access token."""
    return batch_worker_unavailable(cfg)


def voice_embedding_url(cfg: config.HarnessConfig) -> str:
    return f"http://127.0.0.1:{cfg.backend_port + VOICE_EMBEDDING_PORT_OFFSET}"


def voice_embedding_env(cfg: config.HarnessConfig) -> dict[str, str]:
    return _child_env(
        cfg,
        {
            voice_embedding.PORT_ENV: str(cfg.backend_port + VOICE_EMBEDDING_PORT_OFFSET),
            voice_embedding.WORK_DIR_ENV: str(cfg.layout.services_dir / "voice-embedding"),
            # Clips are a few seconds long; leave the cores to the batch workers.
            voice_embedding.THREADS_ENV: "2",
            config.MODEL_ACCESS_TOKEN_ENV: model_access_token(cfg),
        },
    )


def record_seal_worker_enabled() -> bool:
    """Production runs a CPU worker that seals finished recordings. Its settings are
    in no tracked file the harness can compose from, so it starts only when a
    production snapshot describes it."""
    snapshot = production_snapshot()
    return snapshot is not None and "record-seal-worker" in snapshot.services


def record_seal_worker_env(cfg: config.HarnessConfig) -> dict[str, str]:
    """The seal worker's production settings with the stack's stores."""
    snapshot = production_snapshot()
    if snapshot is None or "record-seal-worker" not in snapshot.services:
        raise safety.SafetyError("the record seal worker needs a production snapshot that describes it")
    local_topology = topology(cfg)
    composed = prod_parity.compose(cfg.repo_root, local_topology)
    env = prod_parity.localized(snapshot.services["record-seal-worker"].values, local_topology)
    env.update(
        {
            **_store_bindings(cfg),
            "POD_NAMESPACE": "local",  # production takes it from the pod
            "HOME": str(cfg.layout.state_root),
            "BUCKET_BATCH_PIPELINE": composed["backend-sync"]["BUCKET_BATCH_PIPELINE"],
            **_trust_env(cfg),
        }
    )
    return _child_env(cfg, env)


def _plain_env(cfg: config.HarnessConfig) -> dict[str, str]:
    env = safety.build_child_env(provider_mode=cfg.provider_mode, extra={"PYTHONUNBUFFERED": "1"})
    env.update(_trust_env(cfg))
    return env


def edge_router_env(cfg: config.HarnessConfig) -> dict[str, str]:
    local_topology = topology(cfg)
    env = _plain_env(cfg)
    env.update(
        {
            edge_router.BACKEND_ENV: local_topology.url("backend"),
            edge_router.LISTEN_ENV: local_topology.url("backend-listen"),
            edge_router.SYNC_ENV: local_topology.url("backend-sync"),
        }
    )
    snapshot = production_snapshot()
    if snapshot is not None and snapshot.routes:
        # The load balancer's own rules, so each request reaches the service production sends it to.
        env[edge_router.INTEGRATION_ENV] = local_topology.url("backend-integration")
        env[edge_router.ROUTES_ENV] = json.dumps({"routes": snapshot.routes, "default": snapshot.default_route})
    return env


def task_dispatcher_env(cfg: config.HarnessConfig) -> dict[str, str]:
    env = _plain_env(cfg)
    env.update(task_queue_env(cfg))
    return env


def scheduler_env(cfg: config.HarnessConfig) -> dict[str, str]:
    local_topology = topology(cfg)
    composed = prod_parity.compose(cfg.repo_root, local_topology)
    by_url = {local_topology.url(service): service for service in prod_parity.SERVICES}

    def identity_for(url: str) -> str:
        service = next((name for base, name in by_url.items() if url.startswith(base)), "backend-sync")
        return composed[service].get("SYNC_TASKS_INVOKER_SA", "")

    def localize(value: str) -> str | None:
        return prod_parity.local_address(value, local_topology)

    selected = os.environ.get(local_scheduler.JOBS_ENV, "").strip().lower()
    names = None if selected == "all" else local_scheduler.RECORDING_JOBS
    snapshot = production_snapshot()
    if snapshot is not None and snapshot.scheduler_jobs:
        # The jobs Cloud Scheduler runs today, not the list in a checkout.
        jobs = local_scheduler.plan_live(
            snapshot.scheduler_jobs, localize=localize, identity_for=identity_for, names=names
        )
    else:
        jobs = local_scheduler.plan(cfg.repo_root, localize=localize, identity_for=identity_for, names=names)
    env = _plain_env(cfg)
    env[local_scheduler.PLAN_ENV] = local_scheduler.encode(jobs)
    env[local_task_queue.SECRET_ENV] = task_queue_secret(cfg)
    return env


def _loop_args() -> list[str]:
    """Event-loop choice for the stack's services.

    The Sync worker route arms ``asyncio.timeout_at`` with deadlines taken from
    ``time.monotonic()``. That is the loop's clock on Linux, where the backend
    is deployed. On macOS uvloop's clock also counts time the machine spent
    asleep, so after any sleep those deadlines are already in the past and every
    queued job is answered 409 ``handler_preamble_expired``. The stdlib loop
    uses ``time.monotonic()`` on every platform.
    """
    return ["--loop", "asyncio"] if sys.platform == "darwin" else []


def gateway_app() -> str:
    """The gateway's ASGI target; the stamped wrapper only when log timestamps are on."""
    return "dev_harness.gateway_app:app" if log_timestamps.enabled() else "llm_gateway.main:app"


def processes(cfg: config.HarnessConfig) -> list[Process]:
    """Every application process of the stack, in start order.

    One process per deployed service, because production gives them different
    settings (the batch serving loop runs on backend-integration only, for
    example). The task queue, the scheduler and the edge router stand in for
    Cloud Tasks, Cloud Scheduler and the load balancer.
    """
    python = sys.executable
    backend_dir = cfg.repo_root / "backend"
    service_ports = ports(cfg)
    certificate = tls(cfg)
    result = [
        Process(
            "llm-gateway",
            [python, "-m", "uvicorn", gateway_app(), "--host", cfg.dev_bind_host]
            + ["--port", str(cfg.llm_gateway_port)],
            backend_dir,
            cfg.llm_gateway_port,
        ),
        Process(
            "pusher",
            # Flags from backend/pusher/Dockerfile, with the macOS loop choice.
            [python, "-m", "uvicorn", "pusher.main:app", "--host", "127.0.0.1", "--port", str(cfg.pusher_port)]
            + ["--ws-ping-interval", "20", "--ws-ping-timeout", "20", "--timeout-graceful-shutdown", "90"]
            + _loop_args(),
            backend_dir,
            cfg.pusher_port,
            service_env(cfg, "pusher"),
            backend_import=True,
        ),
    ]
    for service, name in SERVICE_PROCESSES.items():
        result.append(
            Process(
                name,
                # Flags from backend/Dockerfile, with the macOS loop choice. Cloud Run
                # services are HTTPS-only, and the code checks it.
                [python, "-m", "uvicorn", "dev_harness.parity_service_app:app", "--host", "127.0.0.1"]
                + ["--port", str(service_ports[service]), "--timeout-graceful-shutdown", "60"]
                + (
                    ["--ssl-certfile", str(certificate.certificate), "--ssl-keyfile", str(certificate.key)]
                    if service in prod_parity.CLOUD_RUN_SERVICES
                    else []
                )
                + _loop_args(),
                backend_dir,
                service_ports[service],
                service_env(cfg, service),
                backend_import=True,
            )
        )
    result.append(
        Process("task-queue", [python, "-m", "dev_harness.local_task_queue"], backend_dir, 0, task_dispatcher_env(cfg))
    )
    result.append(
        Process("scheduler", [python, "-m", "dev_harness.local_scheduler"], backend_dir, 0, scheduler_env(cfg))
    )
    if batch_worker_unavailable(cfg) is None:
        for index in range(batch_worker_count()):
            result.append(
                Process(
                    "batch-worker" if index == 0 else f"batch-worker-{index + 1}",
                    [str(batch_worker_python(cfg)), "-m", "dev_harness.batch_worker"],
                    backend_dir,
                    cfg.backend_port + BATCH_WORKER_PORT_OFFSET + index,
                    batch_worker_env(cfg, index),
                    backend_import=True,
                )
            )
    if voice_embedding_unavailable(cfg) is None:
        result.append(
            Process(
                "voice-embedding",
                [str(batch_worker_python(cfg)), "-m", "dev_harness.voice_embedding"],
                backend_dir,
                cfg.backend_port + VOICE_EMBEDDING_PORT_OFFSET,
                voice_embedding_env(cfg),
                backend_import=True,
            )
        )
    if record_seal_worker_enabled():
        result.append(
            Process(
                "record-seal-worker",
                # Production's own command (charts/batch-pipeline-worker/templates/record-seal-worker.yaml).
                [python, "scripts/record_seal_worker.py"],
                backend_dir,
                0,
                record_seal_worker_env(cfg),
                backend_import=True,
            )
        )
    result.append(
        Process(
            "backend",
            [python, "-m", "uvicorn", "dev_harness.edge_router:app", "--host", cfg.dev_bind_host]
            # The upstream's own Server and Date headers are the ones a client should see.
            + ["--port", str(cfg.backend_port), "--no-server-header", "--no-date-header"],
            backend_dir,
            cfg.backend_port,
            edge_router_env(cfg),
        )
    )
    return result


def is_process(name: str) -> bool:
    """A process only this profile starts and that has no HTTP health route of its own."""
    return name in ("task-queue", "scheduler", "record-seal-worker", "voice-embedding") or name.startswith(
        "batch-worker"
    )


def health_checks(cfg: config.HarnessConfig) -> dict[str, tuple[str | None, dict[str, str] | None]]:
    """Health URL of each service process, checked against the stack's own certificate authority."""
    local_topology = topology(cfg)
    # The Cloud Run stand-ins serve TLS from the stack's own authority.
    os.environ["SSL_CERT_FILE"] = str(tls(cfg).bundle)
    checks: dict[str, tuple[str | None, dict[str, str] | None]] = {
        name: (f"{local_topology.url(service)}/v1/health", None) for service, name in SERVICE_PROCESSES.items()
    }
    checks["pusher"] = (f"{cfg.pusher_url}/health", None)
    return checks


def start_notes(cfg: config.HarnessConfig) -> list[str]:
    """What a developer should know before the services start: sources and anything that will not run."""
    notes: list[str] = []
    snapshot = production_snapshot()
    if snapshot is None:
        notes.append(
            "settings: this checkout's deploy files (no production snapshot; see scripts/dev-harness/PROD_PARITY.md)"
        )
    else:
        notes.append(f"settings: production snapshot of {snapshot.captured_at} ({snapshot.directory})")
        for service in (*SERVICE_PROCESSES, "pusher", "batch-worker"):
            live = snapshot.services.get(service)
            commit = live.commit[:10] if live and live.commit else "an unknown commit"
            notes.append(f"  {service}: production runs {commit}")
    reason = batch_worker_unavailable(cfg)
    if reason is not None:
        notes.append(
            f"batch-worker: not started ({reason}). Phone and pendant recordings stay 'Transcribing' until it runs."
        )
        notes.append(
            "voice-embedding: not started (same reason). Speakers are numbered per recorded unit and never "
            "joined across a conversation or matched to a named person."
        )
    return notes


def _firestore_value(value: object) -> dict[str, object]:
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, str):
        return {"stringValue": value}
    if value is None:
        return {"nullValue": None}
    if isinstance(value, dict):
        return {"mapValue": {"fields": {key: _firestore_value(item) for key, item in value.items()}}}
    raise TypeError(f"unsupported rollout value {type(value).__name__}")


def seed_rollout_ramp(cfg: config.HarnessConfig) -> str:
    """Write production's rollout state to the emulator; a document someone else wrote is the developer's.

    Returns one line saying what happened.
    """
    url = (
        f"http://{cfg.firestore_host}/v1/projects/{cfg.project_id}/databases/{cfg.database_id}"
        "/documents/rollout_cohorts/_ramp"
    )
    headers = {"Authorization": "Bearer owner", "Content-Type": "application/json"}
    deadline = time.time() + ROLLOUT_RAMP_WAIT_SECONDS
    snapshot = production_snapshot()
    live = (((snapshot.rollout_ramp or {}).get("envs") or {}).get("prod") or {}) if snapshot else {}
    ramp = {"percents": live["percents"], "legacy_sync": live.get("legacy_sync")} if live.get("percents") else None
    reason = f"prod_snapshot:{snapshot.captured_at}" if ramp and snapshot else "prod_parity_seed"
    while True:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=5) as response:
                current = json.loads(response.read()).get("fields", {})
            prod = current.get("envs", {}).get("mapValue", {}).get("fields", {}).get("prod", {}).get("mapValue", {})
            fields = prod.get("fields", {})
            ours = fields.get("updated_by", {}).get("stringValue") == "dev-harness"
            if ramp is None or not ours or fields.get("reason", {}).get("stringValue") == reason:
                # Ours is refreshed only when a newer production snapshot says something else.
                return "rollout ramp: present, left as is"
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                break
            raise RuntimeError(f"cannot read the rollout ramp from the emulator: HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            # The emulator was started moments ago; services need the document before they boot.
            if time.time() >= deadline:
                raise RuntimeError(f"Firestore emulator not reachable for the rollout ramp: {exc.reason}") from exc
            time.sleep(0.75)
    document = {
        "schema_version": 1,
        "revision": 1,
        "envs": {
            "prod": {
                **(ramp or PRODUCTION_RAMP),
                "locked_by": None,
                "updated_at": None,
                "updated_by": "dev-harness",
                "reason": reason,
            }
        },
    }
    body = json.dumps({"fields": {key: _firestore_value(value) for key, value in document.items()}}).encode()
    request = urllib.request.Request(url, data=body, headers=headers, method="PATCH")
    with urllib.request.urlopen(request, timeout=5):
        return f"rollout ramp: written from {reason}: {ramp or PRODUCTION_RAMP}"
