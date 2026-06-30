from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_harness import safety


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_state_root_layout_and_sentinel(tmp_path: Path) -> None:
    env = {"OMI_LOCAL_STATE_ROOT": str(tmp_path / "state")}

    layout = safety.create_state_layout(REPO_ROOT, "default", env)

    assert layout.state_root == (tmp_path / "state" / "default").resolve()
    assert layout.sentinel_path.is_file()
    assert layout.process_manifest.parent.is_dir()
    assert layout.port_manifest.parent.is_dir()
    assert layout.config_digest_path.parent == layout.state_root
    assert layout.logs_dir.is_dir()
    assert layout.reports_dir.is_dir()
    assert (layout.services_dir / "firestore").is_dir()
    assert (layout.services_dir / "auth").is_dir()
    assert (layout.services_dir / "redis").is_dir()
    assert (layout.services_dir / "typesense").is_dir()

    sentinel = safety.read_and_validate_sentinel(layout.state_root, repo_root=REPO_ROOT, instance="default")
    assert sentinel["project_id"] == safety.DEFAULT_LOCAL_FIREBASE_PROJECT_ID
    assert sentinel["database_id"] == safety.DEFAULT_FIRESTORE_DATABASE_ID

    layout.sentinel_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(safety.SafetyError, match="Invalid harness sentinel"):
        safety.read_and_validate_sentinel(layout.state_root, repo_root=REPO_ROOT, instance="default")


def test_project_database_and_loopback_validation() -> None:
    assert safety.validate_project_id("demo-omi-local", require_canonical=True) == "demo-omi-local"
    assert safety.validate_project_id("demo-other") == "demo-other"
    assert safety.validate_database_id("(default)") == "(default)"

    for host in ("127.0.0.1:8085", "localhost:9099", "http://[::1]:9099", "127.12.0.3:1234"):
        assert safety.validate_loopback_emulator_host(host) == host

    with pytest.raises(safety.SafetyError, match="non-demo"):
        safety.validate_project_id("omi-prod")
    with pytest.raises(safety.SafetyError, match="demo-omi-local"):
        safety.validate_project_id("demo-memory", require_canonical=True)
    with pytest.raises(safety.SafetyError, match="database"):
        safety.validate_database_id("customer-data")
    with pytest.raises(safety.SafetyError, match="loopback"):
        safety.validate_loopback_emulator_host("0.0.0.0:8085")
    with pytest.raises(safety.SafetyError, match="loopback"):
        safety.validate_loopback_emulator_host("firestore.googleapis.com:443")


def test_child_environment_strips_cloud_defaults_and_offline_provider_secrets() -> None:
    parent = {
        "PATH": "/usr/bin",
        "HOME": "/home/dev",
        "GOOGLE_APPLICATION_CREDENTIALS": "/prod/service-account.json",
        "GOOGLE_CLOUD_PROJECT": "prod-project",
        "GCLOUD_PROJECT": "prod-project",
        "FIREBASE_CONFIG": "prod-config",
        "SERVICE_ACCOUNT_JSON": "secret",
        "OPENAI_API_KEY": "secret",
        "OMI_VISIBLE": "1",
    }

    env = safety.build_child_env(parent, provider_mode="offline", extra={"FIRESTORE_EMULATOR_HOST": "127.0.0.1:8085"})

    assert env["PATH"] == "/usr/bin"
    assert env["OMI_VISIBLE"] == "1"
    assert env["FIREBASE_PROJECT_ID"] == "demo-omi-local"
    assert env["FIRESTORE_DATABASE_ID"] == "(default)"
    assert env["FIRESTORE_EMULATOR_HOST"] == "127.0.0.1:8085"
    for stripped in (
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_CLOUD_PROJECT",
        "GCLOUD_PROJECT",
        "FIREBASE_CONFIG",
        "SERVICE_ACCOUNT_JSON",
        "OPENAI_API_KEY",
    ):
        assert stripped not in env

    with pytest.raises(safety.SafetyError, match="unsafe child environment"):
        safety.build_child_env(parent, extra={"GOOGLE_APPLICATION_CREDENTIALS": "/tmp/key.json"})
    env_with_backend_secret = safety.build_child_env(
        parent,
        provider_mode="offline",
        extra={
            "ENCRYPTION_SECRET": "local-only-test-secret",
            "ADMIN_KEY": "local-admin",
            "TYPESENSE_API_KEY": "local-typesense",
        },
    )
    assert env_with_backend_secret["ENCRYPTION_SECRET"] == "local-only-test-secret"
    assert env_with_backend_secret["ADMIN_KEY"] == "local-admin"
    assert env_with_backend_secret["TYPESENSE_API_KEY"] == "local-typesense"

    with pytest.raises(safety.SafetyError, match="provider credential"):
        safety.build_child_env(parent, provider_mode="offline", extra={"DEEPGRAM_API_KEY": "x"})


def test_destructive_path_guard_rejects_dangerous_paths(tmp_path: Path) -> None:
    env = {"OMI_LOCAL_STATE_ROOT": str(tmp_path / "state")}
    layout = safety.create_state_layout(REPO_ROOT, "default", env)
    owned_child = layout.state_root / "services" / "firestore"

    assert (
        safety.validate_destructive_target(owned_child, state_root=layout.state_root, repo_root=REPO_ROOT)
        == owned_child.resolve()
    )

    dangerous = [Path("/"), Path.home(), REPO_ROOT, tmp_path / "outside"]
    for target in dangerous:
        with pytest.raises(safety.SafetyError):
            safety.validate_destructive_target(target, state_root=layout.state_root, repo_root=REPO_ROOT)

    (layout.state_root / safety.HARNESS_SENTINEL_FILENAME).unlink()
    with pytest.raises(safety.SafetyError, match="Missing harness ownership sentinel"):
        safety.validate_destructive_target(owned_child, state_root=layout.state_root, repo_root=REPO_ROOT)


def _write_manifests(layout: safety.HarnessLayout, process: dict[str, object], port: dict[str, object]) -> None:
    layout.process_manifest.parent.mkdir(parents=True, exist_ok=True)
    layout.process_manifest.write_text(json.dumps({"processes": [process]}) + "\n", encoding="utf-8")
    layout.port_manifest.write_text(json.dumps({"ports": [port]}) + "\n", encoding="utf-8")


def test_foreign_pid_and_port_are_rejected(tmp_path: Path) -> None:
    env = {"OMI_LOCAL_STATE_ROOT": str(tmp_path / "state")}
    layout = safety.create_state_layout(REPO_ROOT, "default", env)
    marker = "omi-harness-test-owned-marker"
    proc = subprocess.Popen([sys.executable, "-c", f"import time; time.sleep(60)  # {marker}"])
    foreign_proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        time.sleep(0.1)
        _write_manifests(
            layout,
            {"service": "backend", "pid": proc.pid, "ownership_marker": marker},
            {"service": "backend", "port": 49152, "pid": proc.pid},
        )

        assert (
            safety.validate_owned_pid(proc.pid, process_manifest=layout.process_manifest, service="backend")["pid"]
            == proc.pid
        )
        assert (
            safety.validate_port_owner(
                49152,
                pid=proc.pid,
                port_manifest=layout.port_manifest,
                process_manifest=layout.process_manifest,
                service="backend",
            )["port"]
            == 49152
        )

        with pytest.raises(safety.SafetyError, match="foreign PID"):
            safety.validate_owned_pid(foreign_proc.pid, process_manifest=layout.process_manifest)
        with pytest.raises(safety.SafetyError, match="Foreign process owns port"):
            safety.validate_port_owner(49152, pid=foreign_proc.pid, port_manifest=layout.port_manifest)

        _write_manifests(
            layout,
            {"service": "backend", "pid": foreign_proc.pid, "ownership_marker": "not-in-command-line"},
            {"service": "backend", "port": 49153, "pid": foreign_proc.pid},
        )
        with pytest.raises(safety.SafetyError, match="ownership marker"):
            safety.validate_owned_pid(foreign_proc.pid, process_manifest=layout.process_manifest)
    finally:
        for running in (proc, foreign_proc):
            running.terminate()
            try:
                running.wait(timeout=5)
            except subprocess.TimeoutExpired:
                running.kill()
                running.wait(timeout=5)


def test_redis_reset_guard_refuses_shared_redis(tmp_path: Path) -> None:
    layout = safety.create_state_layout(REPO_ROOT, "default", {"OMI_LOCAL_STATE_ROOT": str(tmp_path / "state")})

    assert (
        safety.validate_redis_reset_target(
            "redis://127.0.0.1:6379/0?omi_instance=default", state_root=layout.state_root, expected_instance="default"
        )
        == "redis://127.0.0.1:6379/0?omi_instance=default"
    )
    with pytest.raises(safety.SafetyError, match="shared Redis"):
        safety.validate_redis_reset_target(
            "redis://127.0.0.1:6379/0", state_root=layout.state_root, expected_instance="default"
        )
    with pytest.raises(safety.SafetyError, match="loopback"):
        safety.validate_redis_reset_target(
            "redis://redis.internal:6379/0?omi_instance=default",
            state_root=layout.state_root,
            expected_instance="default",
        )
