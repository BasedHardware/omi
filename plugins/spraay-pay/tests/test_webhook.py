import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from config import Settings
from main import create_app
from payment.executor import PaymentResult
from payment.ledger import FAILED, SETTLED

SAMPLES = json.loads((Path(__file__).parent.parent / "examples" / "sample_payloads.json").read_text(encoding="utf-8"))
TOKEN = "test-token"
UID = "user-123"


class FakeExecutor:
    def __init__(self):
        self.calls = []
        self.result = PaymentResult(SETTLED, "Paid. Transaction: 0xabc", "0xabc")

    async def pay(self, target_url, amount_micro):
        self.calls.append((target_url, amount_micro))
        return self.result


@pytest.fixture
def executor():
    return FakeExecutor()


def build(tmp_path, executor, **overrides):
    values = {
        "webhook_secret": TOKEN,
        "allowed_uids": UID,
        "database_path": str(tmp_path / "test.db"),
        "public_base_url": "https://pay.example.com",
        "_env_file": None,
    }
    return TestClient(create_app(Settings(**{**values, **overrides}), executor))


@pytest.fixture
def client(tmp_path, executor):
    return build(tmp_path, executor)


def post_transcript(client, payload, uid=UID, token=TOKEN):
    return client.post(f"/webhook/transcript?token={token}&uid={uid}", json=payload)


def code_from(text):
    return re.search(r"/confirm (\d{6})", text).group(1)


def chat(client, path, **body):
    return client.post(f"/chat/{path}?token={TOKEN}", json={"uid": UID, "app_id": "spraay-pay", **body})


def segment(text, start, is_user=True):
    return {"id": f"s{start}", "text": text, "speaker": "SPEAKER_00", "speaker_id": 0, "is_user": is_user, "start": start, "end": start + 1}


# --- Authentication ------------------------------------------------------------------


def test_rejects_wrong_token(client):
    assert post_transcript(client, SAMPLES["transcript_payment"], token="nope").status_code == 401


def test_fails_closed_without_configured_secret(tmp_path, executor):
    open_client = build(tmp_path, executor, webhook_secret=None)
    assert post_transcript(open_client, SAMPLES["transcript_payment"], token="").status_code == 503


def test_requires_uid_query_parameter(client):
    assert client.post(f"/webhook/transcript?token={TOKEN}", json=SAMPLES["transcript_payment"]).status_code == 422


def test_unlisted_uid_gets_no_prompt(client):
    body = post_transcript(client, SAMPLES["transcript_payment"], uid="stranger").json()
    assert "message" not in body


def test_unlisted_uid_cannot_use_chat(client, executor):
    response = client.post(f"/chat/pay?token={TOKEN}", json=SAMPLES["chat_pay"] | {"uid": "stranger"})
    assert response.status_code == 403
    assert executor.calls == []


def test_empty_allowlist_denies_everyone(tmp_path, executor):
    closed = build(tmp_path, executor, allowed_uids="")
    assert chat(closed, "pay", command="/pay $1 to api.example.com").status_code == 403


# --- Transcript webhook --------------------------------------------------------------


def test_voice_intent_prompts_and_does_not_pay(client, executor):
    response = post_transcript(client, SAMPLES["transcript_payment"])
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "user-123"
    assert "$5.00" in body["message"] and "https://api.example.com" in body["message"]
    assert "notification" not in body
    assert executor.calls == []


def test_other_speakers_are_ignored(client):
    assert "message" not in post_transcript(client, SAMPLES["transcript_other_speaker"]).json()


def test_accepts_documented_array_payload(client):
    assert "$2.50" in post_transcript(client, SAMPLES["transcript_documented_array"]).json()["message"]


def test_intent_spanning_two_calls(client):
    first = post_transcript(client, {"session_id": UID, "segments": [segment("Pay $5", 1.0)]}).json()
    second = post_transcript(client, {"session_id": UID, "segments": [segment("to api.example.com", 2.0)]}).json()
    assert "no service address" in first["message"]
    assert "/confirm" in second["message"]


def test_redelivered_segment_does_not_prompt_twice(client):
    assert "message" in post_transcript(client, SAMPLES["transcript_payment"]).json()
    assert "message" not in post_transcript(client, SAMPLES["transcript_payment"]).json()


def test_over_limit_voice_request_explains_denial(client):
    payload = {"session_id": UID, "segments": [segment("pay $50 to api.example.com", 1.0)]}
    message = post_transcript(client, payload).json()["message"]
    assert "per-payment limit" in message and "/confirm" not in message


def test_everyday_speech_is_silent(client):
    payload = {"session_id": UID, "segments": [segment("I need to buy milk", 1.0)]}
    assert "message" not in post_transcript(client, payload).json()


# --- Confirmation --------------------------------------------------------------------


def test_voice_then_confirm_pays_exactly_once(client, executor):
    code = code_from(post_transcript(client, SAMPLES["transcript_payment"]).json()["message"])
    first = chat(client, "confirm", code=code)
    assert first.status_code == 200 and "0xabc" in first.json()["result"]
    assert chat(client, "confirm", code=code).status_code == 400
    assert executor.calls == [("https://api.example.com", 5_000_000)]


def test_wrong_code_does_not_pay(client, executor):
    post_transcript(client, SAMPLES["transcript_payment"])
    assert chat(client, "confirm", code="not-a-code").status_code == 400
    assert executor.calls == []


def test_cancel_prevents_confirmation(client, executor):
    code = code_from(post_transcript(client, SAMPLES["transcript_payment"]).json()["message"])
    assert "Cancelled 1" in chat(client, "cancel").json()["result"]
    assert chat(client, "confirm", code=code).status_code == 400
    assert executor.calls == []


def test_daily_limit_rechecked_at_confirmation(tmp_path, executor):
    client = build(tmp_path, executor, daily_limit_usd="6")
    first = code_from(chat(client, "pay", command="/pay $4 to a.example.com").json()["result"])
    second = code_from(chat(client, "pay", command="/pay $4 to b.example.com").json()["result"])
    assert chat(client, "confirm", code=first).status_code == 200
    denied = chat(client, "confirm", code=second)
    assert denied.status_code == 403 and "daily limit" in denied.json()["error"]
    assert len(executor.calls) == 1


# --- /pay chat tool ------------------------------------------------------------------


def test_pay_requires_confirmation_by_default(client, executor):
    body = client.post(f"/chat/pay?token={TOKEN}", json=SAMPLES["chat_pay"]).json()
    assert "/confirm" in body["result"]
    assert executor.calls == []


def test_pay_under_auto_approve_executes(tmp_path, executor):
    client = build(tmp_path, executor, auto_approve_usd="5")
    assert "0xabc" in chat(client, "pay", command="/pay $5 to api.example.com").json()["result"]
    assert executor.calls == [("https://api.example.com", 5_000_000)]


def test_failed_payment_releases_daily_budget(tmp_path, executor):
    client = build(tmp_path, executor, auto_approve_usd="5", daily_limit_usd="5")
    executor.result = PaymentResult(FAILED, "Nothing was paid.")
    chat(client, "pay", command="/pay $5 to api.example.com")
    executor.result = PaymentResult(SETTLED, "Paid. Transaction: 0xabc", "0xabc")
    assert "0xabc" in chat(client, "pay", command="/pay $5 to api.example.com").json()["result"]


def test_pay_with_unusable_command_returns_omi_error_shape(client):
    response = chat(client, "pay", command="/pay something")
    assert response.status_code == 400
    assert "error" in response.json()


def test_pay_over_limit_denied(client, executor):
    response = chat(client, "pay", command="/pay $6 to api.example.com")
    assert response.status_code == 403
    assert executor.calls == []


# --- Memory webhook ------------------------------------------------------------------


def test_memory_logs_user_payment_mentions(client):
    response = client.post(f"/webhook/memory?token={TOKEN}&uid={UID}", json=SAMPLES["memory_with_payment"])
    assert response.status_code == 200
    assert response.json() == {"logged": 1, "patterns": []}


def test_memory_redelivery_does_not_create_pattern(client):
    url = f"/webhook/memory?token={TOKEN}&uid={UID}"
    client.post(url, json=SAMPLES["memory_with_payment"])
    assert client.post(url, json=SAMPLES["memory_with_payment"]).json()["patterns"] == []


def test_recurring_pattern_detected_across_memories(client):
    url = f"/webhook/memory?token={TOKEN}&uid={UID}"
    client.post(url, json=SAMPLES["memory_with_payment"])
    patterns = client.post(url, json=SAMPLES["memory_with_payment"] | {"id": "memory-2"}).json()["patterns"]
    assert patterns == [{"pattern": "pay|https://news.example.com|$3", "occurrences": 2}]


def test_discarded_memory_not_logged(client):
    payload = SAMPLES["memory_with_payment"] | {"discarded": True}
    assert client.post(f"/webhook/memory?token={TOKEN}&uid={UID}", json=payload).json()["logged"] == 0


# --- Chat tools manifest -------------------------------------------------------------


def test_tools_manifest_requires_token(client):
    assert client.get("/.well-known/omi-tools.json").status_code == 401


def test_tools_manifest_shape(client):
    tools = client.get(f"/.well-known/omi-tools.json?token={TOKEN}").json()["tools"]
    assert [tool["name"] for tool in tools] == ["pay", "confirm_payment", "cancel_payment"]
    assert tools[0]["endpoint"] == f"https://pay.example.com/chat/pay?token={TOKEN}"


def test_app_manifests_are_valid():
    root = Path(__file__).parent.parent
    primary = json.loads((root / "omi_app.json").read_text(encoding="utf-8"))
    memory = json.loads((root / "omi_app_memory.json").read_text(encoding="utf-8"))
    assert primary["name"] == "Spraay Pay" and primary["author"] == "Plagtech"
    assert set(primary["capabilities"]) == {"external_integration", "proactive_notification", "chat"}
    assert primary["external_integration"]["triggers_on"] == "transcript_processed"
    assert memory["external_integration"]["triggers_on"] == "memory_creation"
    assert memory["author"] == "Plagtech"
