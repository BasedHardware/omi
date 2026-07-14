import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    repo = Path(__file__).resolve().parents[3]
    script_path = repo / "scripts" / "voice-provider-probe.sh"
    loader = importlib.machinery.SourceFileLoader("voice_provider_probe", str(script_path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


class _Response:
    status = 200

    def __init__(self, body):
        self.body = body

    def read(self, _size=-1):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_openai_probe_mints_then_connects_commits_and_waits_for_a_terminal_response(monkeypatch, capsys):
    module = _load_module()
    sent = []

    class FakeWebSocket:
        def __init__(self):
            self.events = iter(
                [
                    {"type": "session.updated"},
                    {"type": "response.done", "response": {"status": "completed"}},
                ]
            )
            self._socket = None
            self.closed = False

        def send_json(self, payload):
            sent.append(payload)

        def receive_json(self):
            return next(self.events)

        def close(self):
            self.closed = True

    websocket = FakeWebSocket()
    monkeypatch.setattr(module, "_mint_provider_token", lambda _config: "ek_probe-token-must-not-leak")
    monkeypatch.setattr(module, "_openai_websocket", lambda _token, _timeout: websocket)

    result = module.run_probe(
        module.ProbeConfig(
            provider="openai",
            base_url="https://candidate.invalid",
            bearer_token="firebase-token-must-not-leak",
            timeout_seconds=5,
        )
    )

    output = capsys.readouterr().out
    assert result == 0
    assert websocket.closed is True
    assert [event["type"] for event in sent] == [
        "conversation.item.create",
        "response.create",
    ]
    assert sent[0]["item"]["content"][0]["text"] == module.PROBE_INPUT
    assert "step=mint status=PASS class=none" in output
    assert "step=connect status=PASS class=none" in output
    assert "step=commit status=PASS class=none" in output
    assert "step=response status=PASS class=none" in output
    assert "step=close status=PASS class=expected_idle_teardown" in output
    assert "firebase-token-must-not-leak" not in output
    assert "ek_probe-token-must-not-leak" not in output
    assert module.PROBE_INPUT not in output


def test_mint_rejects_a_2xx_response_with_the_wrong_typed_provider_token(monkeypatch):
    module = _load_module()
    calls = []

    def fake_urlopen(request, *, timeout):
        calls.append((request, timeout))
        return _Response(json.dumps({"provider": "gemini", "token": "auth_tokens/not-openai"}).encode())

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    config = module.ProbeConfig(
        provider="openai",
        base_url="https://candidate.invalid",
        bearer_token="firebase-token-must-not-leak",
        timeout_seconds=5,
    )

    try:
        module._mint_provider_token(config)
    except module.ProbeFailure as error:
        assert error.failure_class == "mint_schema"
    else:
        raise AssertionError("expected typed mint schema rejection")

    request, _ = calls[0]
    assert request.full_url == "https://candidate.invalid/v2/realtime/session"
    assert json.loads(request.data) == {"provider": "openai"}


def test_timeout_returns_retryable_exit_code_without_exposing_the_token(monkeypatch, capsys):
    module = _load_module()
    monkeypatch.setattr(
        module,
        "_mint_provider_token",
        lambda _config: (_ for _ in ()).throw(module.ProbeFailure("timeout", retryable=True)),
    )

    result = module.run_probe(
        module.ProbeConfig(
            provider="gemini",
            base_url="https://candidate.invalid",
            bearer_token="firebase-token-must-not-leak",
            timeout_seconds=5,
        )
    )

    output = capsys.readouterr().out
    assert result == 75
    assert "provider=gemini step=mint status=FAIL class=timeout" in output
    assert "firebase-token-must-not-leak" not in output
