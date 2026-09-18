"""Tests for the top-level ``omi ask`` command."""

from __future__ import annotations

import json

from omi_cli.main import app


def test_ask_posts_question_and_prints_answer(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.post("/v1/dev/user/ask").respond(
        json={
            "answer": "You decided to raise prices 10%.",
            "sources": [{"id": "c1", "title": "Pricing sync", "created_at": "2026-07-20T00:00:00Z"}],
        }
    )

    result = cli_runner.invoke(app, ["ask", "what did I decide about pricing?"])

    assert result.exit_code == 0
    assert "You decided to raise prices 10%." in result.stdout
    assert "Pricing sync" in result.stdout  # source rendered
    body = json.loads(route.calls[0].request.content)
    assert body["question"] == "what did I decide about pricing?"
    assert body["limit"] == 5  # default grounding size


def test_ask_forwards_timezone_verbatim_and_defaults_to_utc(authed_profile, respx_mock, cli_runner) -> None:
    """The CLI is not the validation boundary — the backend's ``DeveloperAskRequest``
    validator is, so the option is forwarded as typed rather than pre-screened here.
    A CLI-side IANA check would drift from the server's ``ZoneInfo`` database."""
    route = respx_mock.post("/v1/dev/user/ask").respond(json={"answer": "ok", "sources": []})

    assert cli_runner.invoke(app, ["ask", "when?"]).exit_code == 0
    assert json.loads(route.calls[0].request.content)["timezone"] == "UTC"

    assert cli_runner.invoke(app, ["ask", "when?", "--timezone", "Asia/Kolkata"]).exit_code == 0
    assert json.loads(route.calls[1].request.content)["timezone"] == "Asia/Kolkata"


def test_ask_json_mode_emits_raw_payload(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.post("/v1/dev/user/ask").respond(json={"answer": "42", "sources": []})

    result = cli_runner.invoke(app, ["--json", "ask", "meaning of life?", "--limit", "3"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"answer": "42", "sources": []}
