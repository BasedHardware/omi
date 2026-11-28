"""The prod-parity profile may differ from production in infrastructure only.

These run against this checkout's own deploy files, so they follow production's
settings as the files change: they assert relations (a setting equals what the
files declare, services agree with each other), not today's values.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "dev-harness"))

pytest.importorskip("yaml")

pytest.importorskip("croniter")
pytest.importorskip("cryptography")

from dev_harness import cli, config, edge_router, local_scheduler, local_task_queue, parity_report  # noqa: E402
from dev_harness import parity_stack, prod_snapshot, voice_embedding  # noqa: E402
from dev_harness import prod_parity as profile  # noqa: E402


@pytest.fixture(autouse=True)
def _files_are_the_source(monkeypatch):
    # A developer's own snapshot or profile must not leak into these tests.
    monkeypatch.delenv(prod_snapshot.SNAPSHOT_ENV, raising=False)
    monkeypatch.delenv(profile.PROFILE_ENV, raising=False)


@pytest.fixture(scope="module")
def topology() -> profile.Topology:
    return profile.Topology(
        project_id="demo-omi-local",
        database_id="(default)",
        ports={
            "backend": 8010,
            "backend-listen": 8011,
            "backend-sync": 8012,
            "backend-sync-backfill": 8013,
            "backend-integration": 8014,
            "pusher": 8090,
        },
        llm_gateway_url="http://127.0.0.1:9080",
        redis_host="127.0.0.1",
        redis_port=6380,
    )


@pytest.fixture()
def composed(topology) -> dict[str, dict[str, str]]:
    return profile.compose(REPO_ROOT, topology)


def test_every_logic_setting_is_productions(composed):
    # The whole point of the profile: a setting that changes behaviour takes
    # production's declared value on every service, or this fails naming it.
    assert profile.logic_differences(REPO_ROOT, composed) == []


def test_no_service_can_dial_a_host_off_this_machine(composed):
    assert profile.remote_addresses(composed) == []
    for service, env in composed.items():
        for name, value in env.items():
            if name.endswith(("_PROJECT", "_PROJECT_ID", "_URL", "_AUDIENCE")):
                assert "based-hardware" not in value, (service, name)
        assert not env.get("POSTHOG_PRODUCT_CAPTURE_TOKEN"), service  # no telemetry to production's project
        assert env.get("OMI_TELEGRAM_ENABLED", "off") == "off", service


def test_services_keep_productions_per_service_differences(composed):
    # One process per service exists because production gives them different settings.
    declared = profile.declared_production(REPO_ROOT)
    differing = {
        name
        for name in declared["backend"].values
        if not profile.is_infrastructure(name)
        and any(declared[other].values.get(name) != declared["backend"].values[name] for other in profile.SERVICES)
    }
    assert differing, "every production service declares the same settings; one process would do"
    for name in differing:
        for service in profile.SERVICES:
            assert composed[service].get(name) == declared[service].values.get(name), (service, name)
    for service in profile.SERVICES:
        assert composed[service]["OMI_ENV_STAGE"] == "prod", service


def test_services_agree_on_shared_infrastructure(composed, topology):
    # The enqueuer and the verifier must name the same account, and services that
    # pass data through a bucket must name the same bucket.
    invokers = {env[name] for env in composed.values() for name in env if name.endswith("_INVOKER_SA") and env[name]}
    invokers = {value for value in invokers if "developer.gserviceaccount.com" not in value}
    assert invokers == {"local-tasks-invoker@demo-omi-local.iam.gserviceaccount.com"}
    for bucket in ("BUCKET_PRIVATE_CLOUD_SYNC", "BUCKET_BATCH_PIPELINE", "BUCKET_TEMPORAL_SYNC_LOCAL"):
        names = {env[bucket] for env in composed.values() if env.get(bucket)}
        assert len(names) == 1, (bucket, names)
    sync = composed["backend-sync"]
    assert sync["SYNC_TASKS_HANDLER_URL"] == f"{topology.url('backend-sync')}/v2/sync-jobs/run"
    assert sync["SYNC_BACKFILL_TASKS_HANDLER_URL"] == f"{topology.url('backend-sync-backfill')}/v2/sync-jobs/run"
    assert composed["backend-listen"]["HOSTED_PUSHER_API_URL"] == topology.url("pusher")
    # Production checks these schemes; the stand-ins must satisfy them unchanged.
    assert sync["BATCH_PIPELINE_API_URL"].startswith("https://127.0.0.1:")
    assert sync["ENRICHMENT_TASKS_HANDLER_URL"].startswith("https://127.0.0.1:")


def test_infrastructure_classification_is_narrow():
    for logic in (
        "SYNC_FRESH_MAX_AGE_SECONDS",
        "BATCH_PIPELINE_ENABLED",
        "STT_SERVICE_MODELS",
        "STT_ROUTING_REDIS_TIMEOUT_SECONDS",
        "FAIR_USE_REDIS_RETENTION_SECONDS",
        "SYNC_DISPATCH_MODE",
        "HTTP_POST_TIMEOUT",
        "OMI_ENV_STAGE",
    ):
        assert not profile.is_infrastructure(logic), logic
    for infra in ("SYNC_TASKS_HANDLER_URL", "BUCKET_BATCH_PIPELINE", "REDIS_DB_HOST", "SYNC_TASKS_QUEUE"):
        assert profile.is_infrastructure(infra), infra


def test_batch_worker_takes_the_chart_settings_and_local_addresses(topology):
    declared = profile.declared_batch_worker(REPO_ROOT)
    worker = profile.compose_batch_worker(REPO_ROOT, topology)
    assert declared["BATCH_PIPELINE_WORDS_PROVIDER"] == "parakeet" and declared["BATCH_PIPELINE_DIARIZER"] == "pyannote"
    assert worker["BATCH_PIPELINE_API_URL"] == topology.url("backend-sync")
    for name, value in declared.items():
        if not profile.is_infrastructure(name):
            assert worker[name] == value, name


def test_queues_and_scheduler_follow_productions_definitions(topology, composed):
    queues = local_task_queue.production_queue_settings(REPO_ROOT, 4)
    for env in composed.values():
        for name, value in env.items():
            if name.endswith("_QUEUE") and value:
                assert value in queues, (name, value)
    assert all(settings.max_concurrent <= 4 for settings in queues.values())
    jobs = local_scheduler.plan(
        REPO_ROOT,
        localize=lambda value: profile.local_address(value, topology),
        identity_for=lambda url: "local-tasks-invoker@demo-omi-local.iam.gserviceaccount.com",
    )
    assert {job.name for job in jobs} == set(local_scheduler.RECORDING_JOBS)
    assert all(job.url.startswith("https://127.0.0.1:") for job in jobs)


def test_edge_routes_by_production_service():
    assert edge_router.upstream_for("websocket", "/v4/listen") == "listen"
    assert edge_router.upstream_for("http", "/v2/sync-local-files") == "sync"
    assert edge_router.upstream_for("http", "/v2/sync-local-files/abc/release-hold") == "sync"
    assert edge_router.upstream_for("http", "/v1/conversations") == "backend"
    assert edge_router.upstream_for("http", "/v2/sync-jobs/run") == "backend"  # task routes are never public


def _cfg(monkeypatch, tmp_path) -> config.HarnessConfig:
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("PROVIDER_MODE", "real")
    monkeypatch.delenv(config.MODEL_ACCESS_TOKEN_ENV, raising=False)
    # A developer's own keys file must not decide what these tests see.
    monkeypatch.setattr(config, "secrets_file_path", lambda _cfg: tmp_path / "no-secrets-file")
    return config.load_config(REPO_ROOT, create_layout=True)


def test_bindings_carry_no_logic(monkeypatch, tmp_path):
    cfg = _cfg(monkeypatch, tmp_path)
    harmless = {"PORT", "PYTHONUNBUFFERED", "ENVIRONMENT", "DYLD_FALLBACK_LIBRARY_PATH", "SSL_CERT_FILE"}
    for name in parity_stack.bindings(cfg, "backend-sync"):
        assert (
            profile.is_infrastructure(name)
            or name in harmless
            or name.startswith(("OMI_HARNESS_", "OMI_LOCAL_STORAGE_", "OMI_LLM_GATEWAY_"))
            or name.endswith(("_SECRET", "_KEY", "_CA_BUNDLE", "_EMULATOR_HOST"))
            or name == "PROVIDER_MODE"
        ), name


def test_stack_runs_one_process_per_production_service_behind_the_edge_router(monkeypatch, tmp_path):
    cfg = _cfg(monkeypatch, tmp_path)
    processes = {process.name: process for process in parity_stack.processes(cfg)}

    for service, name in parity_stack.SERVICE_PROCESSES.items():
        process = processes[name]
        assert process.env is not None and process.env["PORT"] == str(process.port)
        assert process.command[process.command.index("--host") + 1] == "127.0.0.1", name  # never on the LAN
        # Cloud Run stand-ins serve TLS, as the code that calls them requires.
        assert ("--ssl-certfile" in process.command) == (service in profile.CLOUD_RUN_SERVICES), name
        assert process.env["FIRESTORE_EMULATOR_HOST"] == cfg.firestore_host
    assert len({process.port for process in processes.values() if process.port}) == len(
        [process for process in processes.values() if process.port]
    )
    # The public port is the router, and it is the last thing to start.
    router = list(processes.values())[-1]
    assert router.name == "backend" and router.port == cfg.backend_port
    assert "dev_harness.edge_router:app" in router.command
    assert {"llm-gateway", "pusher", "task-queue", "scheduler"} <= set(processes)
    # No model runtime or access token in this checkout: the worker is left out and the developer is told.
    assert not any(name.startswith("batch-worker") for name in processes)
    assert any("batch-worker: not started" in note for note in parity_stack.start_notes(cfg))
    # The speaker-embedding service needs the same runtime: left out, announced, and its address stays unreachable.
    assert "voice-embedding" not in processes
    assert any("voice-embedding: not started" in note for note in parity_stack.start_notes(cfg))
    assert processes["svc-backend"].env[profile.VOICE_EMBEDDING_ENV] == profile.BLACKHOLE
    assert "record-seal-worker" not in processes  # described only by a production snapshot


def test_speaker_embedding_is_served_locally_when_the_model_runtime_is_installed(monkeypatch, tmp_path):
    cfg = _cfg(monkeypatch, tmp_path)
    monkeypatch.setattr(parity_stack, "batch_worker_python", lambda _cfg: Path("/model-runtime/bin/python"))
    monkeypatch.setattr(parity_stack, "model_access_token", lambda _cfg: "model-token")
    processes = {process.name: process for process in parity_stack.processes(cfg)}

    service = processes["voice-embedding"]
    assert service.command == ["/model-runtime/bin/python", "-m", "dev_harness.voice_embedding"]
    assert service.env is not None and service.env[voice_embedding.PORT_ENV] == str(service.port)
    assert parity_stack.is_process("voice-embedding")
    # Every production service that declares the route is pointed at the local one, and at nothing else.
    callers = [
        name
        for name in parity_stack.SERVICE_PROCESSES.values()
        if profile.VOICE_EMBEDDING_ENV in (processes[name].env or {})
    ]
    assert "svc-backend" in callers and "svc-sync" in callers
    for name in callers:
        assert processes[name].env[profile.VOICE_EMBEDDING_ENV] == f"http://127.0.0.1:{service.port}", name
        # The other hosted model services stay unreachable.
        assert processes[name].env.get("HOSTED_DIARIZATION_API_URL", profile.BLACKHOLE) == profile.BLACKHOLE, name
    assert not any("voice-embedding" in note for note in parity_stack.start_notes(cfg))


def test_speaker_embedding_route_answers_like_the_diarizer(tmp_path):
    import json
    import threading
    import urllib.error
    import urllib.request

    class TooShort(Exception):
        status_code = 422
        detail = {"error": "audio_too_short"}

    def embed(filename, data):
        if len(data) < 4:
            raise TooShort()
        return [[float(len(filename)), float(len(data))]]

    ready = threading.Event()
    server = voice_embedding.build_server(0, embed, ready)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"

    def post(data: bytes, path: str = voice_embedding.ROUTE):
        boundary = "harness-boundary"
        body = (
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="clip.wav"\r\n'
                "Content-Type: audio/wav\r\n\r\n"
            ).encode()
            + data
            + f"\r\n--{boundary}--\r\n".encode()
        )
        request = urllib.request.Request(
            url + path, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    try:
        assert post(b"RIFF....")[0] == 503  # the model is still loading: the caller takes its unavailable path
        ready.set()
        # Binary audio survives the form parsing byte for byte.
        audio = bytes(range(256)) * 4 + b"\r\n--not-the-boundary\r\n"
        assert post(audio) == (200, [[8.0, float(len(audio))]])
        assert post(b"abc") == (422, {"detail": {"error": "audio_too_short"}})
        assert post(audio, "/v1/diarization")[0] == 404
        with urllib.request.urlopen(url + "/health", timeout=5) as response:
            assert json.loads(response.read()) == {"status": "healthy"}
    finally:
        server.shutdown()
        server.server_close()


def test_no_process_receives_cloud_credentials_or_a_production_project(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/secrets/prod.json")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware")
    cfg = _cfg(monkeypatch, tmp_path)
    for process in parity_stack.processes(cfg):
        env = process.env or {}
        assert "GOOGLE_APPLICATION_CREDENTIALS" not in env, process.name
        assert env.get("GOOGLE_CLOUD_PROJECT", cfg.project_id) == cfg.project_id, process.name


def test_profile_is_opt_in_and_names_its_own_required_credentials(monkeypatch, tmp_path):
    cfg = _cfg(monkeypatch, tmp_path)
    assert not parity_stack.enabled()
    assert cli._required_credentials() is None  # the default stack keeps its own rules

    monkeypatch.setenv(profile.PROFILE_ENV, profile.PROD_PARITY)
    assert cli._required_credentials() == profile.REQUIRED_CREDENTIALS
    for name in profile.REQUIRED_CREDENTIALS:
        monkeypatch.delenv(name, raising=False)
    missing, _warnings = cli.prerequisite_report(cfg)
    for name in profile.REQUIRED_CREDENTIALS:
        assert any(name in item for item in missing), name
    assert not any("DEEPGRAM_API_KEY" in item or "GEMINI_API_KEY" in item for item in missing)

    monkeypatch.setenv("PROVIDER_MODE", "offline")
    offline = config.load_config(REPO_ROOT, create_layout=True)
    assert any("PROVIDER_MODE=real" in item for item in cli.prerequisite_report(offline)[0])


def test_report_without_a_snapshot_says_what_the_source_is(monkeypatch, tmp_path):
    cfg = _cfg(monkeypatch, tmp_path)
    assert parity_report.build(cfg)[1] == 1  # not the prod-parity profile

    monkeypatch.setenv(profile.PROFILE_ENV, profile.PROD_PARITY)
    report, findings = parity_report.build(cfg)
    assert "this checkout's deploy files" in report
    assert "settings that differ from the source: 0" in report
    assert "batch speech worker: NOT RUNNING" in report
    assert "speaker embedding: NOT RUNNING" in report
    assert findings == 3  # no snapshot, no batch worker, no speaker embedding; nothing else


def test_a_worker_that_exited_is_reported_not_counted_as_running(monkeypatch, tmp_path):
    cfg = _cfg(monkeypatch, tmp_path)
    # The manifest holds live processes only: the seal worker's record is already gone.
    records = [{"service": "scheduler", "pid": os.getpid()}, {"service": "task-queue", "pid": 2_000_000_000}]
    planned = [
        parity_stack.Process(name, ["python"], tmp_path, 0)
        for name in ("svc-sync", "task-queue", "scheduler", "record-seal-worker")
    ]
    monkeypatch.setattr(cli, "_process_records", lambda _cfg: records)
    monkeypatch.setattr(
        cli, "_service_record", lambda _cfg, name: next((r for r in records if r["service"] == name), None)
    )
    monkeypatch.setattr(parity_stack, "processes", lambda _cfg: planned)

    exited = cli._exited_prod_parity_processes(cfg)
    assert [item.split(":")[0] for item in exited] == ["task-queue", "record-seal-worker"]
    assert "record-seal-worker.log" in exited[1]
    assert cli._service_health(cfg, "record-seal-worker") == (False, "not running")
    assert cli._service_health(cfg, "task-queue") == (False, "not running")
    assert cli._service_health(cfg, "scheduler") == (True, "running")


def test_a_finished_child_counts_as_gone_before_anyone_reaps_it():
    if os.name == "nt":
        pytest.skip("POSIX process table semantics")
    import subprocess
    import time

    child = subprocess.Popen([sys.executable, "-c", "pass"])
    deadline = time.time() + 10
    while time.time() < deadline and not cli._process_gone(child.pid):
        time.sleep(0.05)
    assert cli._process_gone(child.pid)
    assert not cli._process_gone(os.getpid())
