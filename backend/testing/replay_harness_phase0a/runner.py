"""Generic topology launcher for the Replay Harness.

Reads a declarative capability/topology contract (topology.json), allocates
isolated ports, resolves placeholders, starts each declared role via its
declared command, probes declared health endpoints, and builds a
machine-verifiable attestation. Contains NO sync-specific branching logic;
the sync test fixture env is a labeled constant, not runtime branching.

Usage:
    PYTHONPATH=backend python -m testing.replay_harness_phase0a.runner [options]
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
PYTHON = str(BACKEND / ".venv" / "bin" / "python")
PROJECT = "demo-omi-replay-harness"
ADMIN_KEY = "omi-replay-harness-admin-"
ENCRYPTION_SECRET = "omi_replay_harness_test_secret_32_bytes"
TRANSCRIPT_TOKEN = "Replay harness transcript verified."
DEVICE_HASH = "01234567"
DEVICE_ID = f"ios_{DEVICE_HASH}"
LOCAL_OIDC_AUDIENCE = "https://replay-harness.local/v2/sync-jobs/run"
LOCAL_INVOKER_SA = f"replay-invoker@{PROJECT}.iam.gserviceaccount.com"
LOCAL_OIDC_TOKEN = f"local-replay-oidc:{LOCAL_INVOKER_SA}"
SYNC_QUEUE = "sync-jobs"


class HarnessFailure(AssertionError):
    pass


@dataclass
class Child:
    name: str
    process: subprocess.Popen[bytes]
    log_path: Path
    pid: int


@dataclass
class RoleHealth:
    name: str
    pid: int
    port: int | None
    ready: bool
    ready_probe: dict[str, Any] = field(default_factory=dict)


class Harness:
    """Generic topology launcher driven by a declarative contract."""

    def __init__(self, topology_path: Path, state_dir: Path, *, fault_controls: dict[str, str] | None = None):
        self.topology = json.loads(topology_path.read_text())
        self.topology_path = topology_path
        self.state_dir = state_dir
        self.fault_controls = fault_controls or {}
        self.logs_dir = state_dir / "logs"
        self.evidence_dir = state_dir / "evidence"
        self.storage_dir = state_dir / "local-storage"
        for d in (self.logs_dir, self.evidence_dir, self.storage_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.ports: dict[str, int] = {}
        self.children: dict[str, Child] = {}
        self.health_records: list[RoleHealth] = []
        self.control_token = f"replay-{int(time.time())}-{os.getpid()}"
        self.http = httpx.Client(timeout=15.0, trust_env=False)
        self._resolved_topology: dict[str, Any] = {}

    def _free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            return int(probe.getsockname()[1])

    def _resolve_placeholders(self, text: str) -> str:
        result = text
        for role_name, port in self.ports.items():
            result = result.replace(f"${{port:{role_name}}}", str(port))
        result = result.replace("${python}", PYTHON)
        return result

    def _build_egress_allow(self, role: str) -> list[dict[str, Any]]:
        entries = []
        for item in self.topology.get("egress_allow_list", []):
            if item["role"] != role:
                continue
            target = item["to"]
            if target == "firestore":
                firestore_host = os.getenv("FIRESTORE_EMULATOR_HOST", "")
                host = firestore_host.rsplit(":", 1)[0] if ":" in firestore_host else "127.0.0.1"
                port_str = firestore_host.rsplit(":", 1)[1] if ":" in firestore_host else "0"
                entries.append({"host": host, "port": int(port_str)})
            elif target in self.ports:
                entries.append({"host": "127.0.0.1", "port": self.ports[target]})
        return entries

    def _build_env(self, role: str) -> dict[str, str]:
        # Generic: allowlisted inheritance.
        env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TZ", "TMPDIR") if os.getenv(key)}
        firestore_host = os.getenv("FIRESTORE_EMULATOR_HOST", "").strip()
        isolated_home = self.state_dir / "home"
        isolated_config = self.state_dir / "config"
        env.update(
            {
                "HOME": str(isolated_home),
                "XDG_CONFIG_HOME": str(isolated_config),
                "CLOUDSDK_CONFIG": str(isolated_config / "gcloud"),
                "NO_PROXY": "127.0.0.1,localhost",
                "no_proxy": "127.0.0.1,localhost",
                "FIRESTORE_EMULATOR_HOST": firestore_host,
                "FIREBASE_AUTH_EMULATOR_HOST": "127.0.0.1:9099",
                "FIREBASE_PROJECT_ID": PROJECT,
                "GOOGLE_CLOUD_PROJECT": PROJECT,
                "GCLOUD_PROJECT": PROJECT,
                "FIRESTORE_DATABASE_ID": "(default)",
                "ENCRYPTION_SECRET": ENCRYPTION_SECRET,
                "ADMIN_KEY": ADMIN_KEY,
                "REDIS_DB_HOST": "127.0.0.1",
                "REDIS_DB_PORT": str(self.ports["redis"]),
                "REDIS_DB_PASSWORD": "",
                "OMI_ENV_STAGE": "offline",
                "PROVIDER_MODE": "offline",
                "LOCAL_DEVELOPMENT": "true",
                "PYTHONPATH": str(BACKEND),
                "OMI_REPLAY_ROLE": role,
                "OMI_REPLAY_STATE_DIR": str(self.state_dir),
                "OMI_REPLAY_STORAGE_DIR": str(self.storage_dir),
                "OMI_REPLAY_CONTROL_TOKEN": self.control_token,
                "OMI_REPLAY_TRANSCRIPT_TOKEN": TRANSCRIPT_TOKEN,
                "OMI_REPLAY_EGRESS_ALLOW": json.dumps(self._build_egress_allow(role)),
            }
        )
        # Generic: topology-derived URLs.
        env["OMI_REPLAY_OIDC_TOKEN"] = LOCAL_OIDC_TOKEN
        env["OMI_REPLAY_OIDC_SA"] = LOCAL_INVOKER_SA
        env["OMI_REPLAY_OIDC_AUDIENCE"] = LOCAL_OIDC_AUDIENCE
        env["OMI_REPLAY_QUEUE_PATH"] = f"projects/{PROJECT}/locations/local/queues/{SYNC_QUEUE}"

        # SYNC TEST FIXTURE (constant, not branching): sync pipeline configuration.
        env.update(
            {
                "SYNC_DISPATCH_MODE": "cloud_tasks",
                "SYNC_LEDGER_FENCE_MODE": "active",
                "SYNC_TASKS_PROJECT": PROJECT,
                "SYNC_TASKS_LOCATION": "local",
                "SYNC_TASKS_QUEUE": SYNC_QUEUE,
                "SYNC_TASKS_HANDLER_URL": f"http://127.0.0.1:{self.ports['worker']}/v2/sync-jobs/run",
                "SYNC_TASKS_OIDC_AUDIENCE": LOCAL_OIDC_AUDIENCE,
                "SYNC_TASKS_INVOKER_SA": LOCAL_INVOKER_SA,
                "SYNC_TASKS_MAX_ATTEMPTS": "2",
                "HTTP_SYNC_JOBS_RUN_TIMEOUT": "30",
                "FAIR_USE_ENABLED": "true",
                "MAX_DAILY_AUDIO_HOURS": "30",
                "TRIAL_PAYWALL_ENABLED": "false",
                "STT_PRERECORDED_MODEL": "parakeet",
                "STT_SERVICE_MODELS": "parakeet",
                "HOSTED_PARAKEET_API_URL": "http://127.0.0.1:1",
                "BUCKET_TEMPORAL_SYNC_LOCAL": "sync-temporal",
                "BUCKET_SPEECH_PROFILES": "speech-profiles",
                "BUCKET_POSTPROCESSING": "postprocessing",
                "BUCKET_PRIVATE_CLOUD_SYNC": "omi-private-cloud-sync",
                "BUCKET_MEMORIES_RECORDINGS": "memories-recordings",
                "BUCKET_APP_THUMBNAILS": "app-thumbnails",
                "BUCKET_CHAT_FILES": "chat-files",
                "BUCKET_DESKTOP_UPDATES": "desktop-updates",
                "STRIPE_SECRET_KEY": "",
            }
        )

        # Role-specific URLs.
        if role == "admission":
            env["OMI_REPLAY_LOOPBACK_URL"] = f"http://127.0.0.1:{self.ports['cloud-tasks-loopback']}"
        elif role == "cloud-tasks-loopback":
            env["OMI_REPLAY_PORT"] = str(self.ports["cloud-tasks-loopback"])
            env["OMI_REPLAY_WORKER_URL"] = f"http://127.0.0.1:{self.ports['worker']}"
            env["OMI_REPLAY_DISPATCH_DEADLINE"] = "1500"

        # Fault controls (from scenario, not launcher).
        for key, value in self.fault_controls.items():
            env[key] = value

        return env

    def _start_role(self, name: str) -> Child:
        role_def = self.topology["roles"][name]
        command = [self._resolve_placeholders(c) for c in role_def["command"]]
        log_path = self.logs_dir / f"{name}.log"
        env = self._build_env(name)
        output = log_path.open("wb")
        process = subprocess.Popen(
            command,
            cwd=str(BACKEND),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        child = Child(name=name, process=process, log_path=log_path, pid=process.pid)
        self.children[name] = child
        return child

    def _wait_health(self, name: str) -> RoleHealth:
        role_def = self.topology["roles"][name]
        health = role_def["health"]
        timeout = float(role_def.get("startup_timeout_seconds", 30))
        port = self.ports.get(name)
        pid = self.children[name].pid

        if health["type"] == "tcp":
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                        rh = RoleHealth(name=name, pid=pid, port=port, ready=True, ready_probe={"type": "tcp"})
                        self.health_records.append(rh)
                        return rh
                except OSError:
                    time.sleep(0.2)
            raise HarnessFailure(f"{name} did not listen on 127.0.0.1:{port}")

        # HTTP health probe.
        expect_role = health.get("expect_role", name)
        url = f"http://127.0.0.1:{port}{health['path']}"
        deadline = time.monotonic() + timeout

        def check() -> bool:
            try:
                response = self.http.get(url, timeout=2.0)
                body = response.json()
                return response.status_code == 200 and body.get("status") == "ok" and body.get("role") == expect_role
            except Exception:
                return False

        while time.monotonic() < deadline:
            if self.children[name].process.poll() is not None:
                raise HarnessFailure(f"{name} exited early; see {self.logs_dir / f'{name}.log'}")
            if check():
                probe = {"type": "http", "path": health["path"], "status": 200, "role": expect_role}
                rh = RoleHealth(name=name, pid=pid, port=port, ready=True, ready_probe=probe)
                self.health_records.append(rh)
                return rh
            time.sleep(0.3)
        raise HarnessFailure(f"{name} health check failed within {timeout:.0f}s")

    def start(self) -> None:
        roles = self.topology["roles"]
        for name in roles:
            self.ports[name] = self._free_port()
        # Start in dependency order (topology.json key order is significant).
        for name in roles:
            child = self._start_role(name)
            print(f"  started {name} (pid {child.pid})", file=sys.stderr)
            self._wait_health(name)
            print(f"  {name} ready", file=sys.stderr)

    def teardown(self) -> None:
        for name in list(self.children):
            self._stop(name)
        self.http.close()

    def _stop(self, name: str) -> None:
        child = self.children.pop(name, None)
        if child is None or child.process.poll() is not None:
            return
        import contextlib

        with contextlib.suppress(ProcessLookupError):
            os.killpg(child.process.pid, signal.SIGTERM)
        try:
            child.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(child.process.pid, signal.SIGKILL)
            child.process.wait(timeout=5)

    @property
    def admission_url(self) -> str:
        return f"http://127.0.0.1:{self.ports['admission']}"

    @property
    def control_headers(self) -> dict[str, str]:
        return {"X-Omi-Replay-Control": self.control_token}

    def read_events(self) -> list[dict[str, Any]]:
        path = self.evidence_dir / "egress.jsonl"
        if not path.exists():
            return []
        result = []
        for line in path.read_text().strip().split("\n"):
            if line:
                result.append(json.loads(line))
        return result

    def stt_invocation_count(self) -> int:
        return sum(1 for e in self.read_events() if e.get("event") == "stt_completed")

    def build_attestation(self, *, outcome: str) -> dict[str, Any]:
        from testing.replay_harness_phase0a.attestation import build_attestation

        firestore_host = os.getenv("FIRESTORE_EMULATOR_HOST", "")
        return build_attestation(
            topology=self._resolved_topology or self.topology,
            health_records=self.health_records,
            events=self.read_events(),
            ports=self.ports,
            firestore_emulator_host=firestore_host,
            outcome=outcome,
            fault_controls=self.fault_controls,
        )


def main() -> int:
    from testing.replay_harness_phase0a.scenario import run_phase0a

    topology_path = Path(__file__).parent / "topology.json"
    state_root = Path(os.environ.get("OMI_REPLAY_STATE_ROOT", f"/tmp/omi-replay-harness-{os.getpid()}"))

    return run_phase0a(topology_path, state_root)


if __name__ == "__main__":
    sys.exit(main())
