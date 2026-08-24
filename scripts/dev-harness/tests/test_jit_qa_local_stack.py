from __future__ import annotations

import asyncio
import importlib.util
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
import google.auth

MODULE_PATH = Path(__file__).resolve().parents[1] / "jit_qa_local_stack.py"
VERTEX_GATEWAY_PATH = MODULE_PATH.parent / "dev_harness" / "jit_vertex_gateway.py"
SPEC = importlib.util.spec_from_file_location("jit_qa_local_stack", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
jit_stack = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(jit_stack)


def _load_vertex_gateway(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(MODULE_PATH.parents[2] / "backend"))
    monkeypatch.setenv("OMI_LLM_GATEWAY_SERVICE_TOKEN", "s" * 32)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware-dev")
    spec = importlib.util.spec_from_file_location(
        f"jit_vertex_gateway_contract_{time.monotonic_ns()}", VERTEX_GATEWAY_PATH
    )
    assert spec is not None and spec.loader is not None
    gateway = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gateway)
    return gateway


def _vertex_headers(**extra: str) -> dict[str, str]:
    return {
        "authorization": f"Bearer {'s' * 32}",
        "x-omi-service-caller": "backend",
        **extra,
    }


def test_backend_children_cannot_discover_adc_and_only_vertex_broker_gets_host_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "jit-qa-local-dev-gcp"
    state.mkdir()
    host_home = tmp_path / "host-home"
    host_config = tmp_path / "host-config"
    host_home.mkdir()
    host_config.mkdir()
    monkeypatch.setenv("HOME", str(host_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(host_config))
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "forbidden.json"))
    monkeypatch.setenv("POSTHOG_PROJECT_API_KEY", "must-not-leak")
    identity = {"auth_project": "based-hardware", "gcp_project": "based-hardware-dev"}

    main_env = jit_stack._child_env(state, identity, "main")
    vertex_env = jit_stack._child_env(state, identity, "vertex-gateway")

    assert main_env["HOME"] == str(state / "main-home")
    assert main_env["XDG_CONFIG_HOME"] == str(state / "main-home" / ".config")
    assert main_env["GOOGLE_CLOUD_PROJECT"] == jit_stack.LOCAL_FIREBASE_PROJECT
    assert main_env["OMI_LLM_GATEWAY_URL"] == "http://127.0.0.1:18084"
    assert main_env["OMI_LLM_GATEWAY_FEATURE_MODE"] == "gateway"
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in main_env
    assert "POSTHOG_PROJECT_API_KEY" not in main_env

    assert vertex_env["HOME"] == str(host_home)
    assert vertex_env["XDG_CONFIG_HOME"] == str(host_config)
    assert vertex_env["GOOGLE_CLOUD_PROJECT"] == jit_stack.DEV_GCP_PROJECT
    assert vertex_env["OMI_JIT_QA_VERTEX_GATEWAY"] == "1"
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in vertex_env
    assert "POSTHOG_PROJECT_API_KEY" not in vertex_env
    assert vertex_env["OMI_LLM_GATEWAY_SERVICE_TOKEN"] == main_env["OMI_LLM_GATEWAY_SERVICE_TOKEN"]


def test_vertex_broker_has_one_cloud_provider_and_no_shared_mutation_imports() -> None:
    source = VERTEX_GATEWAY_PATH.read_text(encoding="utf-8")
    assert "VertexGeminiProvider" in source
    assert "aiplatform.googleapis.com" in source
    for forbidden in (
        "google.cloud.storage",
        "google.cloud.tasks",
        "google.cloud.compute",
        "firebase_admin.messaging",
        "database.",
    ):
        assert forbidden not in source


def test_vertex_broker_rejects_multimodal_and_tool_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _load_vertex_gateway(monkeypatch)

    with pytest.raises(HTTPException) as image_error:
        gateway._reject_unsupported_surfaces(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": "data:image/png;base64,x"},
                            }
                        ],
                    }
                ]
            }
        )
    assert getattr(image_error.value, "status_code", None) == 422

    with pytest.raises(HTTPException) as tool_error:
        gateway._reject_unsupported_surfaces({"messages": [], "tools": [{"type": "function"}]})
    assert getattr(tool_error.value, "status_code", None) == 422


def test_vertex_broker_behaviorally_enforces_auth_byok_tools_and_body_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _load_vertex_gateway(monkeypatch)
    client = TestClient(gateway.app)
    endpoint = "/v1/chat/completions"
    payload = {"messages": [{"role": "user", "content": "hello"}]}

    assert client.post(endpoint, json=payload).status_code == 401
    assert (
        client.post(
            endpoint,
            json=payload,
            headers={
                "authorization": f"Bearer {'s' * 32}",
                "x-omi-service-caller": "frontend",
            },
        ).status_code
        == 403
    )
    assert (
        client.post(
            endpoint,
            json=payload,
            headers=_vertex_headers(**{"x-omi-byok-openai": "forbidden"}),
        ).status_code
        == 400
    )
    assert (
        client.post(
            endpoint,
            json={**payload, "tools": [{"type": "function"}]},
            headers=_vertex_headers(),
        ).status_code
        == 422
    )
    oversized = b"{" + (b"x" * gateway.MAX_REQUEST_BYTES) + b"}"
    assert (
        client.post(
            endpoint,
            content=oversized,
            headers={**_vertex_headers(), "content-type": "application/json"},
        ).status_code
        == 413
    )


def test_vertex_broker_clamps_output_and_caps_nonstream_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _load_vertex_gateway(monkeypatch)

    class FakeProvider:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        async def create_chat_completion(self, request, **_kwargs):
            self.requests.append(dict(request))
            return SimpleNamespace(
                response={
                    "id": "test",
                    "choices": [{"message": {"role": "assistant", "content": "bounded"}}],
                }
            )

    provider = FakeProvider()
    monkeypatch.setattr(gateway, "_get_provider", lambda: provider)
    client = TestClient(gateway.app)
    response = client.post(
        "/v1/chat/completions",
        json={
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": gateway.MAX_OUTPUT_TOKENS * 100,
        },
        headers=_vertex_headers(),
    )
    assert response.status_code == 200
    assert provider.requests[0]["max_tokens"] == gateway.MAX_OUTPUT_TOKENS
    assert gateway._in_flight == 0

    monkeypatch.setattr(gateway, "MAX_RESPONSE_BYTES", 8)
    response = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hello"}]},
        headers=_vertex_headers(),
    )
    assert response.status_code == 502
    assert gateway._in_flight == 0


def test_vertex_broker_caps_stream_bytes_and_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _load_vertex_gateway(monkeypatch)
    monkeypatch.setattr(gateway, "MAX_RESPONSE_BYTES", 5)

    async def chunks():
        yield b"123"
        yield b"456"

    async def consume() -> None:
        async for _chunk in gateway._bounded_stream(chunks()):
            pass

    with pytest.raises(RuntimeError, match="response budget"):
        asyncio.run(consume())

    gateway._request_starts.clear()
    gateway._in_flight = 0
    gateway._reserve_request_slot()
    gateway._reserve_request_slot()
    with pytest.raises(HTTPException) as saturated:
        gateway._reserve_request_slot()
    assert saturated.value.status_code == 429
    gateway._release_request_slot()
    gateway._release_request_slot()
    assert gateway._in_flight == 0


def test_vertex_broker_readiness_refreshes_development_adc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _load_vertex_gateway(monkeypatch)
    refreshed = 0

    def refresh() -> None:
        nonlocal refreshed
        refreshed += 1

    monkeypatch.setattr(gateway, "_refresh_development_adc", refresh)
    response = TestClient(gateway.app).get("/ready")
    assert response.status_code == 200
    assert refreshed == 1


def test_vertex_broker_adc_requires_dev_detected_and_quota_projects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _load_vertex_gateway(monkeypatch)

    class FakeCredentials:
        def __init__(self, quota_project_id: str | None) -> None:
            self.quota_project_id = quota_project_id
            self.refreshed = False

        def refresh(self, _request) -> None:
            self.refreshed = True

    wrong_quota = FakeCredentials("based-hardware")
    monkeypatch.setattr(
        gateway.google.auth,
        "default",
        lambda **_kwargs: (wrong_quota, "based-hardware-dev"),
    )
    with pytest.raises(RuntimeError, match="quota project"):
        gateway._refresh_development_adc()
    assert not wrong_quota.refreshed

    dev_quota = FakeCredentials("based-hardware-dev")
    monkeypatch.setattr(
        gateway.google.auth,
        "default",
        lambda **_kwargs: (dev_quota, "based-hardware-dev"),
    )
    gateway._refresh_development_adc()
    assert dev_quota.refreshed


def test_local_stack_adc_requires_dev_quota_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCredentials:
        def __init__(self, quota_project_id: str | None) -> None:
            self.quota_project_id = quota_project_id
            self.refreshed = False

        def refresh(self, _request) -> None:
            self.refreshed = True

    monkeypatch.delenv("JIT_QA_TEST_MODE", raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware-dev")
    wrong_quota = FakeCredentials("based-hardware")
    monkeypatch.setattr(
        google.auth,
        "default",
        lambda **_kwargs: (wrong_quota, "based-hardware-dev"),
    )
    errors = jit_stack._validate_gcp_identity("based-hardware")
    assert "ADC quota project must be based-hardware-dev" in errors
    assert wrong_quota.refreshed

    dev_quota = FakeCredentials("based-hardware-dev")
    monkeypatch.setattr(
        google.auth,
        "default",
        lambda **_kwargs: (dev_quota, "based-hardware-dev"),
    )
    assert jit_stack._validate_gcp_identity("based-hardware") == []
    assert dev_quota.refreshed


def test_state_lock_rejects_hardlink_without_chmodding_external_inode(
    tmp_path: Path,
) -> None:
    state = tmp_path / "jit-qa-local-dev-gcp"
    state.mkdir()
    external = tmp_path / "external-lock"
    external.write_text("external\n", encoding="utf-8")
    external.chmod(0o644)
    os.link(external, state / ".operation.lock")

    with pytest.raises(jit_stack.SafetyError, match="hardlinked state lock"):
        with jit_stack._state_lock(state):
            pytest.fail("hardlinked lock must never be acquired")

    assert stat.S_IMODE(external.stat().st_mode) == 0o644
    assert external.read_text(encoding="utf-8") == "external\n"


def test_harden_state_tree_rejects_hardlink_without_chmodding_external_inode(
    tmp_path: Path,
) -> None:
    state = tmp_path / "jit-qa-local-dev-gcp"
    state.mkdir()
    external = tmp_path / "external-state"
    external.write_text("external\n", encoding="utf-8")
    external.chmod(0o644)
    os.link(external, state / "run.json")

    with pytest.raises(jit_stack.SafetyError, match="hardlinked state file"):
        jit_stack._harden_state_tree(state)

    assert stat.S_IMODE(external.stat().st_mode) == 0o644
    assert external.read_text(encoding="utf-8") == "external\n"


@pytest.mark.parametrize(
    "payload",
    [
        "[]\n",
        "null\n",
        '"string"\n',
        "123\n",
        "{}\n",
        '{"schema_version": 2, "services": []}\n',
        '{"schema_version": 1}\n',
        '{"schema_version": 1, "services": {}}\n',
    ],
)
def test_load_metadata_rejects_existing_noncanonical_state(tmp_path: Path, payload: str) -> None:
    state = tmp_path / "jit-qa-local-dev-gcp"
    state.mkdir()
    metadata = state / "run.json"
    metadata.write_text(payload, encoding="utf-8")

    with pytest.raises(jit_stack.SafetyError):
        jit_stack._load_metadata(state)

    assert metadata.read_text(encoding="utf-8") == payload


def test_start_service_rejects_malformed_record_before_spawning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "jit-qa-local-dev-gcp"
    state.mkdir()
    jit_stack._save_metadata(
        state,
        {
            "schema_version": 1,
            "updated_at": jit_stack._now(),
            "services": ["malformed"],
        },
    )
    spawned = False

    def unexpected_spawn(*_args, **_kwargs):
        nonlocal spawned
        spawned = True
        raise AssertionError("malformed metadata must fail before spawn")

    monkeypatch.setattr(jit_stack.subprocess, "Popen", unexpected_spawn)
    with pytest.raises(jit_stack.SafetyError, match="malformed ownership record"):
        jit_stack._start_service(MODULE_PATH.parents[2], state, {}, "main")
    assert not spawned


def test_start_service_terminates_exact_process_when_metadata_save_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "jit-qa-local-dev-gcp"
    (state / "logs").mkdir(parents=True)
    spawned: list[subprocess.Popen[bytes]] = []
    real_popen = subprocess.Popen

    def tracking_popen(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        if kwargs.get("start_new_session") is True:
            spawned.append(process)
        return process

    monkeypatch.setattr(jit_stack, "_load_metadata", lambda _state: {})
    monkeypatch.setattr(jit_stack, "_port_open", lambda _port: False)
    monkeypatch.setattr(
        jit_stack,
        "_command",
        lambda _repo, _state, _identity, _service: (
            [sys.executable, "-c", "import time; time.sleep(60)"],
            tmp_path,
            "test.log",
            18080,
        ),
    )
    child_env = dict(os.environ)
    child_env["PYTHONPATH"] = str(MODULE_PATH.parent)
    monkeypatch.setattr(jit_stack, "_child_env", lambda _state, _identity, _service: dict(child_env))
    monkeypatch.setattr(jit_stack.subprocess, "Popen", tracking_popen)
    monkeypatch.setattr(
        jit_stack,
        "_save_metadata",
        lambda _state, _data: (_ for _ in ()).throw(OSError("disk failure")),
    )

    with pytest.raises(OSError, match="disk failure"):
        jit_stack._start_service(MODULE_PATH.parents[2], state, {}, "main")

    assert len(spawned) == 1
    spawned[0].wait(timeout=5)
    assert spawned[0].poll() is not None


def test_stop_terminates_owned_group_after_supervisor_leader_crash(
    tmp_path: Path,
) -> None:
    state = tmp_path / "jit-qa-local-dev-gcp"
    state.mkdir()
    marker = f"{jit_stack.OWNERSHIP_PREFIX}:main:{'0' * 32}"
    child_env = dict(os.environ)
    child_env["PYTHONPATH"] = str(MODULE_PATH.parent)
    supervisor = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "dev_harness.supervise",
            "--marker",
            marker,
            "--service",
            "main",
            "--",
            "/bin/sleep",
            "60",
        ],
        env=child_env,
        start_new_session=True,
    )
    record = {
        "service": "main",
        "pid": supervisor.pid,
        "process_group": supervisor.pid,
        "marker": marker,
    }
    jit_stack._save_metadata(
        state,
        {"schema_version": 1, "updated_at": jit_stack._now(), "services": [record]},
    )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and jit_stack._owned_marker_process_count(supervisor.pid, marker) < 2:
        time.sleep(0.05)
    assert jit_stack._owned_marker_process_count(supervisor.pid, marker) >= 2

    os.kill(supervisor.pid, signal.SIGKILL)
    supervisor.wait(timeout=5)
    assert jit_stack._owned_process_group(supervisor.pid, marker)

    assert jit_stack._stop(state) == 0
    assert not jit_stack._process_group_exists(supervisor.pid)
    assert jit_stack._load_metadata(state)["services"] == []
