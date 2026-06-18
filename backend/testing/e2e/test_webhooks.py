"""Developer webhook route and delivery coverage."""

import asyncio

import httpx
import pytest


def _configure_realtime_webhook(client, auth_headers, url="https://webhook.test/realtime"):
    configured = client.post(
        "/v1/users/developer/webhook/realtime_transcript",
        json={"url": url},
        headers=auth_headers,
    )
    assert configured.status_code == 200, configured.text


def _enable_realtime_webhook(client, auth_headers):
    enabled = client.post("/v1/users/developer/webhook/realtime_transcript/enable", headers=auth_headers)
    assert enabled.status_code == 200, enabled.text


def _health(fake_redis, uid="123", wtype="realtime_transcript"):
    return {k.decode(): v.decode() for k, v in fake_redis.hgetall(f"dev_webhook_health:{uid}:{wtype}").items()}


def _run_realtime_delivery(monkeypatch, handler):
    import utils.webhooks as webhooks

    async def exercise_webhook():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as fake_client:
            monkeypatch.setattr(webhooks, "get_webhook_client", lambda: fake_client)
            await webhooks.realtime_transcript_webhook(
                "123",
                [{"text": "Hermetic realtime transcript", "speaker": "SPEAKER_00", "start": 0.0, "end": 1.0}],
            )

    asyncio.run(exercise_webhook())


def test_realtime_webhook_config_roundtrip_and_delivery_capture(client, auth_headers, monkeypatch, fake_redis):
    _configure_realtime_webhook(client, auth_headers)

    read_back = client.get("/v1/users/developer/webhook/realtime_transcript", headers=auth_headers)
    assert read_back.status_code == 200, read_back.text
    assert read_back.json() == {"url": "https://webhook.test/realtime"}

    _enable_realtime_webhook(client, auth_headers)

    status = client.get("/v1/users/developer/webhooks/status", headers=auth_headers)
    assert status.status_code == 200, status.text
    assert "realtime_transcript" in status.json()

    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    _run_realtime_delivery(monkeypatch, handler)

    assert len(requests) == 1
    assert str(requests[0].url) == "https://webhook.test/realtime?uid=123"
    payload = requests[0].read()
    assert b"Hermetic realtime transcript" in payload
    assert _health(fake_redis)["failure_count"] == "0"
    assert _health(fake_redis)["last_status"] == "200"

    disabled = client.post("/v1/users/developer/webhook/realtime_transcript/disable", headers=auth_headers)
    assert disabled.status_code == 200, disabled.text


def test_realtime_webhook_does_not_call_provider_when_disabled(client, auth_headers, monkeypatch, fake_redis):
    _configure_realtime_webhook(client, auth_headers)
    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    _run_realtime_delivery(monkeypatch, handler)

    assert requests == []
    assert _health(fake_redis) == {}


@pytest.mark.parametrize(
    ("status_code", "last_error"),
    [(500, "HTTP 500"), (429, "HTTP 429")],
)
def test_realtime_webhook_records_non_2xx_failures(
    client, auth_headers, monkeypatch, fake_redis, status_code, last_error
):
    _configure_realtime_webhook(client, auth_headers)
    _enable_realtime_webhook(client, auth_headers)

    async def handler(request):
        return httpx.Response(status_code, json={"ok": False})

    _run_realtime_delivery(monkeypatch, handler)

    health = _health(fake_redis)
    assert health["failure_count"] == "1"
    assert health["last_status"] == str(status_code)
    assert health["last_error"] == last_error
    assert health["disabled"] == "0"


def test_realtime_webhook_records_timeout_exception_without_real_network(client, auth_headers, monkeypatch, fake_redis):
    _configure_realtime_webhook(client, auth_headers)
    _enable_realtime_webhook(client, auth_headers)

    async def handler(request):
        raise httpx.ConnectTimeout("deterministic timeout")

    _run_realtime_delivery(monkeypatch, handler)

    health = _health(fake_redis)
    assert health["failure_count"] == "1"
    assert health["last_status"] == "0"
    assert health["last_error"] == "ConnectTimeout"
    assert health["disabled"] == "0"


def test_realtime_webhook_auto_disables_after_failure_threshold(client, auth_headers, monkeypatch, fake_redis):
    _configure_realtime_webhook(client, auth_headers)
    _enable_realtime_webhook(client, auth_headers)

    async def handler(request):
        return httpx.Response(500, json={"ok": False})

    import database.webhook_health as webhook_health

    monkeypatch.setattr(webhook_health, "_DEV_FAILURE_THRESHOLD", 2)

    _run_realtime_delivery(monkeypatch, handler)
    _run_realtime_delivery(monkeypatch, handler)

    health = _health(fake_redis)
    assert health["failure_count"] == "2"
    assert health["disabled"] == "1"

    status = client.get("/v1/users/developer/webhooks/status", headers=auth_headers)
    assert status.status_code == 200, status.text
    assert status.json()["realtime_transcript"] is False
