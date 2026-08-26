from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_harness import config, safety
from dev_harness import cli

REPO_ROOT = Path(__file__).resolve().parents[3]
DEV_HARNESS_ROOT = REPO_ROOT / "scripts" / "dev-harness"


def _prepend_dev_harness_pythonpath(env: dict[str, str]) -> None:
    entries = [str(DEV_HARNESS_ROOT)]
    if existing := env.get("PYTHONPATH"):
        entries.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(entries)


def test_child_pythonpath_uses_the_selected_host_separator(tmp_path: Path) -> None:
    env = {"PYTHONPATH": str(tmp_path / "existing")}
    first = tmp_path / "scripts" / "dev-harness"
    second = tmp_path / "backend"

    cli._prepend_pythonpath(env, first, second)

    assert env["PYTHONPATH"].split(os.pathsep) == [str(first), str(second), str(tmp_path / "existing")]


def test_offline_check_skips_provider_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    monkeypatch.setenv("PROVIDER_MODE", "offline")
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))
    cfg = config.load_config(REPO_ROOT)

    missing, warnings = cli.prerequisite_report(cfg)

    assert not any("OPENAI_API_KEY" in item or "DEEPGRAM_API_KEY" in item for item in missing)
    assert any("offline" in item for item in warnings)


def test_real_check_lists_provider_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("agents", encoding="utf-8")
    (repo / ".git").mkdir()
    (repo / "backend").mkdir()
    for key in ("OPENAI_API_KEY", "DEEPGRAM_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PROVIDER_MODE", "real")
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))
    cfg = config.load_config(repo)

    missing, _warnings = cli.prerequisite_report(cfg)

    assert any("OPENAI_API_KEY" in item for item in missing)
    assert any("DEEPGRAM_API_KEY" in item for item in missing)


def test_java_stub_that_exits_nonzero_is_not_a_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """macOS ships /usr/bin/java as a stub that is always on PATH but has no JVM behind it.

    A PATH lookup therefore passes on every Mac, and the missing runtime only surfaces
    ~135s later as an unexplained firestore/auth health-check timeout.
    """
    monkeypatch.setattr(cli, "_which", lambda _name: "/usr/bin/java")
    monkeypatch.setattr(cli.subprocess, "run", lambda *_args, **_kwargs: subprocess.CompletedProcess([], 1))

    assert cli._java_runtime_present() is False


def test_java_present_when_the_binary_reports_a_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "_which", lambda _name: "/usr/bin/java")
    monkeypatch.setattr(cli.subprocess, "run", lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0))

    assert cli._java_runtime_present() is True


def test_missing_java_runtime_is_reported_as_a_prerequisite(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PROVIDER_MODE", "offline")
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setattr(cli, "_java_runtime_present", lambda: False)
    cfg = config.load_config(REPO_ROOT)

    missing, _warnings = cli.prerequisite_report(cfg)

    assert any("java runtime" in item for item in missing)


def test_npx_firebase_tools_does_not_wait_on_an_install_prompt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Without --yes, npx asks "Ok to proceed? (y)" on a pipe nothing can answer.

    The emulator runs detached with stdout redirected to a log file, so the prompt
    blocks forever and the failure presents as a health-check timeout instead.
    """
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setattr(cli, "_which", lambda name: None if name == "firebase" else f"/usr/bin/{name}")
    cfg = config.load_config(REPO_ROOT, create_layout=True)

    command = cli._firebase_command(cfg)

    assert command[:3] == ["npx", "--yes", "firebase-tools"]


def test_firebase_command_writes_the_configured_emulator_ports(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("OMI_HARNESS_PORT_OFFSET", "321")
    cfg = config.load_config(REPO_ROOT, create_layout=True)
    command = cli._firebase_command(cfg)
    config_path = Path(command[command.index("--config") + 1])
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["emulators"]["firestore"]["port"] == 8406
    assert payload["emulators"]["auth"]["port"] == 9420


def test_dev_bind_host_defaults_to_loopback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OMI_DEV_BIND_HOST", raising=False)
    monkeypatch.delenv("OMI_DEV_HOST", raising=False)
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))

    cfg = config.load_config(REPO_ROOT)

    assert cfg.dev_bind_host == "127.0.0.1"


def test_dev_bind_host_falls_back_to_app_dev_host(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # #11774: a contributor who follows the documented physical-device setup sets
    # only OMI_DEV_HOST (the build-side var, app/setup.sh:53). The harness must
    # pick that up too, or the app is built to expect a reachable harness that
    # never actually listens anywhere but loopback.
    monkeypatch.delenv("OMI_DEV_BIND_HOST", raising=False)
    monkeypatch.setenv("OMI_DEV_HOST", "192.168.1.50")
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))

    cfg = config.load_config(REPO_ROOT)

    # Binds all interfaces rather than the literal LAN address, so loopback
    # callers (health checks, a booted simulator) keep working alongside it.
    assert cfg.dev_bind_host == "0.0.0.0"


def test_dev_bind_host_prefers_explicit_bind_host_over_app_dev_host(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OMI_DEV_BIND_HOST", "100.64.1.2")
    monkeypatch.setenv("OMI_DEV_HOST", "192.168.1.50")
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))

    cfg = config.load_config(REPO_ROOT)

    assert cfg.dev_bind_host == "0.0.0.0"


def test_dev_bind_host_rejects_a_public_address(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMI_DEV_HOST", "203.0.113.5")
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))

    with pytest.raises(safety.SafetyError, match="private"):
        config.load_config(REPO_ROOT)


def test_firebase_command_binds_emulators_to_the_resolved_dev_bind_host(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The Auth emulator is what a physical device's Firebase SDK connects to
    # directly, so it must follow the same bind host as the backend (#11774).
    monkeypatch.setenv("OMI_DEV_HOST", "192.168.1.50")
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))
    cfg = config.load_config(REPO_ROOT, create_layout=True)

    command = cli._firebase_command(cfg)

    config_path = Path(command[command.index("--config") + 1])
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["emulators"]["firestore"]["host"] == "0.0.0.0"
    assert payload["emulators"]["auth"]["host"] == "0.0.0.0"


def test_app_services_bind_to_the_resolved_dev_bind_host(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMI_DEV_HOST", "192.168.1.50")
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))
    cfg = config.load_config(REPO_ROOT, create_layout=True)

    started: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        cli,
        "_start_process",
        lambda cfg, service, command, **kwargs: started.append((service, command)),
    )

    cli._start_app_services(cfg)

    assert {service for service, _ in started} == {"llm-gateway", "backend", "desktop-backend"}
    for service, command in started:
        host_index = command.index("--host") + 1
        assert command[host_index] == "0.0.0.0", f"{service} did not bind to the resolved dev_bind_host"


def test_wait_health_returns_services_that_exhaust_their_deadlines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PROVIDER_MODE", "offline")
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))
    cfg = config.load_config(REPO_ROOT)
    ticks = iter((0.0, 181.0))
    monkeypatch.setattr(cli.time, "time", lambda: next(ticks))
    monkeypatch.setattr(cli, "_process_records", lambda _cfg: [])

    failures = cli._wait_health(cfg)

    assert failures == [
        "firestore: not healthy after 45s at http://127.0.0.1:8085/",
        "auth: not healthy after 90s at http://127.0.0.1:9099/",
        "typesense: not healthy after 45s at http://127.0.0.1:8108/collections",
        "backend: not healthy after 180s at http://127.0.0.1:8000/docs",
        "llm-gateway: not healthy after 60s at http://127.0.0.1:9080/health",
        "desktop-backend: not healthy after 60s at http://127.0.0.1:10201/health",
        "redis: not healthy after 30s at 127.0.0.1:6380",
    ]


def test_wait_health_discards_transient_failure_after_recovery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PROVIDER_MODE", "offline")
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))
    cfg = config.load_config(REPO_ROOT)
    ticks = iter((0.0, 1.0, 2.0))
    monkeypatch.setattr(cli.time, "time", lambda: next(ticks))
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(cli, "_process_records", lambda _cfg: [])
    monkeypatch.setattr(cli, "_port_open", lambda _host, _port: True)
    outcomes = iter([(False, "connection refused")] * 6 + [(True, "ok")] * 6)
    monkeypatch.setattr(cli, "_http_ok", lambda _url, headers=None: next(outcomes))

    assert cli._wait_health(cfg) == []


def test_status_health_label_uses_http_probe_and_preserves_degraded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PROVIDER_MODE", "offline")
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))
    cfg = config.load_config(REPO_ROOT)

    monkeypatch.setattr(cli, "_port_open", lambda _host, _port: True)
    monkeypatch.setattr(cli, "_http_ok", lambda _url, headers=None: (True, "HTTP 200"))
    assert cli._status_health_label(cfg, "backend", alive=True, port=cfg.backend_port) == "HTTP 200"

    monkeypatch.setattr(cli, "_http_ok", lambda _url, headers=None: (False, "connection refused"))
    assert (
        cli._status_health_label(cfg, "backend", alive=True, port=cfg.backend_port)
        == "degraded (connection refused)"
    )

    monkeypatch.setattr(cli, "_port_open", lambda _host, _port: False)
    assert cli._status_health_label(cfg, "backend", alive=False, port=cfg.backend_port) == "port-closed"


def test_reset_command_is_idempotent_with_temp_state(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PROVIDER_MODE"] = "offline"
    env["OMI_LOCAL_STATE_ROOT"] = str(tmp_path / "state")
    _prepend_dev_harness_pythonpath(env)

    for _ in range(2):
        result = subprocess.run(
            [sys.executable, "-m", "dev_harness.cli", "reset"],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout
        assert "Reset complete" in result.stdout

    layout = safety.layout_for_instance(REPO_ROOT, "default", env)
    assert layout.sentinel_path.is_file()
    safety.read_and_validate_sentinel(layout.state_root, repo_root=REPO_ROOT, instance="default")


def test_status_reports_seeded_scenario_and_summary_path(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PROVIDER_MODE"] = "offline"
    env["OMI_LOCAL_STATE_ROOT"] = str(tmp_path / "state")
    _prepend_dev_harness_pythonpath(env)

    seed = subprocess.run(
        [sys.executable, "scripts/dev-harness/seed-memory-scenario.py", "happy_path", "--dry-run"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    assert seed.returncode == 0, seed.stdout

    result = subprocess.run(
        [sys.executable, "-m", "dev_harness.cli", "status"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout
    assert "scenario_id: happy_path" in result.stdout
    assert "seeded_users: alice, bob, local_default_user" in result.stdout
    assert "session_summary_path:" in result.stdout
    assert "PROVIDER_MODE=offline active" in result.stdout


def test_session_summary_is_local_emulator_non_activation(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PROVIDER_MODE"] = "offline"
    env["OMI_LOCAL_STATE_ROOT"] = str(tmp_path / "state")
    _prepend_dev_harness_pythonpath(env)

    seed = subprocess.run(
        [sys.executable, "scripts/dev-harness/seed-memory-scenario.py", "happy_path", "--dry-run"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    assert seed.returncode == 0, seed.stdout
    summary = subprocess.run(
        [sys.executable, "-m", "dev_harness.cli", "summary"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    assert summary.returncode == 0, summary.stdout
    path = Path(summary.stdout.strip())
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["evidence_class"] == "LOCAL_EMULATOR_DEV"
    assert payload["activation_eligible"] is False
    assert payload["provider_mode"] == "offline"
    assert payload["memory_write_attempt_instrumentation"]["instrumented"] is False
    assert "before_digest" in payload["protected_state_digest"]
    assert any("Not DEV_CLOUD_PROOF" in item for item in payload["non_claims"])


_DETACHED_PORT_HOLDER = """
import socket, sys, time

sock = socket.socket()
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("127.0.0.1", {port}))
sock.listen(8)
sys.stdout.write("ready\\n")
sys.stdout.flush()
time.sleep(300)
"""

_SUPERVISED_PARENT = """
import subprocess, sys, time

subprocess.Popen([sys.executable, "-c", {holder!r}], start_new_session=True)
time.sleep(300)
"""

# dev-up exits and leaves the supervisors running, so the process under test is an
# orphan reaped by init — not a child of the caller that would linger as a zombie.
_ORPHANING_LAUNCHER = """
import subprocess, sys

proc = subprocess.Popen(sys.argv[1:], start_new_session=True,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(proc.pid)
"""


def _wait_for_listener(port: int, *, timeout: float = 20.0) -> tuple[int, ...]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        pids = safety.listening_pids(port)
        if pids:
            return pids
        time.sleep(0.1)
    return ()


def test_down_reaps_a_detached_child_still_holding_the_service_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The Firestore emulator JVM is spawned detached (its own session), so signalling
    the supervisor's process group never reaches it and it keeps port 8085."""

    monkeypatch.setenv("PROVIDER_MODE", "offline")
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))
    cfg = config.load_config(REPO_ROOT, create_layout=True)
    port = cfg.firestore_port
    if safety.listening_pids(port):
        pytest.skip(f"port {port} is already in use on this machine")

    env = os.environ.copy()
    _prepend_dev_harness_pythonpath(env)
    marker = cli._marker(cfg, "firestore")
    holder = _DETACHED_PORT_HOLDER.format(port=port)
    launched = subprocess.run(
        [
            sys.executable,
            "-c",
            _ORPHANING_LAUNCHER,
            sys.executable,
            "-m",
            "dev_harness.supervise",
            "--marker",
            marker,
            "--service",
            "firestore",
            "--",
            sys.executable,
            "-c",
            _SUPERVISED_PARENT.format(holder=holder),
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        timeout=30,
    )
    supervisor_pid = int(launched.stdout.strip())
    try:
        cli._save_manifests(
            cfg,
            [
                {
                    "service": "firestore",
                    "pid": supervisor_pid,
                    "process_group": supervisor_pid,
                    "port": port,
                    "endpoint": f"127.0.0.1:{port}",
                    "ownership_marker": marker,
                }
            ],
        )
        assert _wait_for_listener(port), "detached port holder never came up"

        cli._stop_owned(cfg)

        assert safety.listening_pids(port) == (), f"port {port} still held after dev-down"
        assert not safety.process_exists(supervisor_pid), "supervisor survived dev-down"
    finally:
        for pid in safety.listening_pids(port) + (supervisor_pid,):
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
