"""Developer webhook route and delivery coverage."""

import asyncio

import httpx


def test_realtime_webhook_config_roundtrip_and_delivery_capture(client, auth_headers, monkeypatch):
    configured = client.post(
        "/v1/users/developer/webhook/realtime_transcript",
        json={"url": "https://webhook.test/realtime"},
        headers=auth_headers,
    )
    assert configured.status_code == 200, configured.text

    read_back = client.get("/v1/users/developer/webhook/realtime_transcript", headers=auth_headers)
    assert read_back.status_code == 200, read_back.text
    assert read_back.json() == {"url": "https://webhook.test/realtime"}

    enabled = client.post("/v1/users/developer/webhook/realtime_transcript/enable", headers=auth_headers)
    assert enabled.status_code == 200, enabled.text

    status = client.get("/v1/users/developer/webhooks/status", headers=auth_headers)
    assert status.status_code == 200, status.text
    assert "realtime_transcript" in status.json()

    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    import utils.webhooks as webhooks

    async def exercise_webhook():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as fake_client:
            monkeypatch.setattr(webhooks, "get_webhook_client", lambda: fake_client)
            await webhooks.realtime_transcript_webhook(
                "123",
                [{"text": "Hermetic realtime transcript", "speaker": "SPEAKER_00", "start": 0.0, "end": 1.0}],
            )

    asyncio.run(exercise_webhook())

    assert len(requests) == 1
    assert str(requests[0].url) == "https://webhook.test/realtime?uid=123"
    payload = requests[0].read()
    assert b"Hermetic realtime transcript" in payload

    disabled = client.post("/v1/users/developer/webhook/realtime_transcript/disable", headers=auth_headers)
    assert disabled.status_code == 200, disabled.text
