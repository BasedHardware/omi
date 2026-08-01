import json
import os
import re
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

from routers import desktop_proxy


def test_sanitize_caps_generation_and_normalizes_system_content():
    body = desktop_proxy._sanitize(
        json.dumps(
            {
                "safetySettings": [{"category": "x"}],
                "contents": [{"role": "system", "parts": [{"text": "system"}]}, {"parts": [{"text": "user"}]}],
                "generation_config": {"maxOutputTokens": "9000"},
            }
        ).encode(),
        "generateContent",
    )
    payload = json.loads(body)
    assert "safetySettings" not in payload
    assert payload["contents"] == [{"role": "user", "parts": [{"text": "user"}]}]
    assert payload["systemInstruction"] == {"parts": [{"text": "system"}]}
    assert payload["generation_config"] == {"maxOutputTokens": 8192, "thinkingConfig": {"thinkingBudget": 1024}}


def test_sanitize_rejects_multiple_candidates_and_path_is_allowlisted():
    with pytest.raises(HTTPException, match="candidate_count"):
        desktop_proxy._sanitize(b'{"candidateCount": 2}', "generateContent")
    assert desktop_proxy._path_parts("models/gemini-3-flash-preview:generateContent") == (
        "models/gemini-2.5-flash:generateContent",
        "gemini-2.5-flash",
        "generateContent",
    )
    with pytest.raises(HTTPException):
        desktop_proxy._path_parts("models/gemini-2.5-pro:deleteModel")


def test_desktop_live_suggestions_model_is_allowed_and_vertex_routed(monkeypatch):
    """Desktop live suggestions run on Flash-Lite (ModelQoS.suggestions), so the proxy must forward it."""
    assert desktop_proxy._path_parts("models/gemini-2.5-flash-lite:generateContent") == (
        "models/gemini-2.5-flash-lite:generateContent",
        "gemini-2.5-flash-lite",
        "generateContent",
    )
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "omi-test")
    monkeypatch.setenv("GCP_LOCATION", "us-central1")
    assert desktop_proxy._vertex_url("gemini-2.5-flash-lite", "generateContent") == (
        "https://us-central1-aiplatform.googleapis.com/v1/projects/omi-test/locations/us-central1"
        "/publishers/google/models/gemini-2.5-flash-lite:generateContent"
    )


def test_every_model_the_desktop_client_ships_is_proxy_allowlisted():
    """Static checker: ModelQoS.swift picks the models the desktop sends to this proxy.

    Not behavioral coverage — it reads the client's model table so a tier change there
    cannot ship a model the proxy answers with 403.
    """
    qos = BACKEND_DIR.parent / "desktop/macos/Desktop/Sources/ModelQoS.swift"
    if not qos.exists():  # partial checkouts (backend-only forks) have no desktop tree
        pytest.skip("desktop sources are not present in this checkout")
    client_models = set(re.findall(r'"(gemini-[^"]+)"', qos.read_text()))
    assert client_models
    assert client_models <= desktop_proxy._ALLOWED_MODELS


def test_shared_desktop_policy_admits_every_model_the_client_ships():
    """The same static checker over the shared Rust policy's copy of the proxy allowlist.

    desktop/shared-rust carries the pre-cutover Rust gate's allowlist. Pinning only this
    module let that copy keep the Flash-Lite gap that #10848 closed here, so the client's
    model table is checked against every in-repo copy of the gate, not just the live one.
    """
    qos = BACKEND_DIR.parent / "desktop/macos/Desktop/Sources/ModelQoS.swift"
    policy = BACKEND_DIR.parent / "desktop/shared-rust/src/model_qos.rs"
    if not qos.exists() or not policy.exists():  # partial checkouts have no desktop tree
        pytest.skip("desktop sources are not present in this checkout")
    client_models = set(re.findall(r'"(gemini-[^"]+)"', qos.read_text()))
    allowed_body = re.search(r"fn gemini_proxy_allowed\(\).*?\n\}", policy.read_text(), re.DOTALL)
    assert allowed_body, "gemini_proxy_allowed() is no longer readable in the shared policy"
    assert client_models
    assert client_models <= set(re.findall(r'"(gemini-[^"]+)"', allowed_body.group()))


def test_vertex_embedding_translation_round_trip():
    request = desktop_proxy._vertex_embedding_request(
        b'{"content":{"parts":[{"text":"hello"}]},"taskType":"RETRIEVAL_QUERY","title":"note"}'
    )
    assert json.loads(request) == {"instances": [{"content": "hello", "task_type": "RETRIEVAL_QUERY", "title": "note"}]}
    assert json.loads(
        desktop_proxy._vertex_embedding_response(b'{"predictions":[{"embeddings":{"values":[1,2]}}]}')
    ) == {"embedding": {"values": [1, 2]}}


@pytest.mark.asyncio
async def test_gemini_proxy_rejects_paywalled_desktop_user(monkeypatch):
    async def run_blocking(_, function, *args):
        return function(*args)

    monkeypatch.setattr(desktop_proxy, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_proxy, "is_trial_paywalled", lambda uid, platform: True)

    with pytest.raises(HTTPException) as error:
        await desktop_proxy._authorized_desktop_user("user")

    assert error.value.status_code == 402
    assert error.value.detail == "trial_expired"


def _meter_run_blocking(monkeypatch, *, daily):
    """Install a run_blocking stub returning ``daily`` for the daily-limit check.

    ``check_rate_limit`` returns (allowed, remaining, retry_after) — remaining counts
    DOWN from the limit. Binding it as if it counted up made the daily cap unreachable
    and inverted the pro->flash downgrade, so the stub mirrors the real contract.
    """

    async def run_blocking(_, function, *args, **kwargs):
        if function is desktop_proxy.redis_db.check_rate_limit:
            if args[1] == "desktop_gemini_daily":
                return daily
            return True, 29, 60
        raise AssertionError("unexpected offloaded call")

    monkeypatch.setattr(desktop_proxy, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_proxy, "get_byok_key", lambda _: None)
    monkeypatch.delenv("OMI_MODEL_TIER", raising=False)


@pytest.mark.asyncio
async def test_server_gemini_meter_downgrades_pro_after_the_soft_limit(monkeypatch):
    # 31 of 1500 consumed today -> past the 30-request pro soft limit.
    _meter_run_blocking(monkeypatch, daily=(True, desktop_proxy._DAILY_HARD_LIMIT - 31, 86_400))

    assert (
        await desktop_proxy._meter_server_request(
            "user", "models/gemini-2.5-pro:generateContent", "gemini-2.5-pro", "generateContent"
        )
        == "models/gemini-2.5-flash:generateContent"
    )


@pytest.mark.asyncio
async def test_server_gemini_meter_keeps_pro_below_the_soft_limit(monkeypatch):
    """Only 2 requests consumed today: pro must survive, not be downgraded.

    The inverted binding read ``remaining`` (1498) as the consumed count, so every
    early request looked past the soft limit.
    """
    _meter_run_blocking(monkeypatch, daily=(True, desktop_proxy._DAILY_HARD_LIMIT - 2, 86_400))

    assert (
        await desktop_proxy._meter_server_request(
            "user", "models/gemini-2.5-pro:generateContent", "gemini-2.5-pro", "generateContent"
        )
        == "models/gemini-2.5-pro:generateContent"
    )


@pytest.mark.asyncio
async def test_server_gemini_meter_enforces_the_daily_hard_limit(monkeypatch):
    """Once the daily policy reports not-allowed, the proxy must 429.

    The previous code compared ``remaining`` against the limit, which can never
    exceed it, so the 1500/day ceiling never fired.
    """
    _meter_run_blocking(monkeypatch, daily=(False, 0, 3600))

    with pytest.raises(HTTPException) as error:
        await desktop_proxy._meter_server_request(
            "user", "models/gemini-2.5-flash:generateContent", "gemini-2.5-flash", "generateContent"
        )

    assert error.value.status_code == 429
    assert error.value.detail == "Gemini daily request limit exceeded"
