"""Tests for ``omi conversation`` commands."""

from __future__ import annotations

import json

from omi_cli.main import app


def test_conversation_list_renders(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.get("/v1/dev/user/conversations").respond(
        json=[
            {
                "id": "c1",
                "structured": {"title": "hello", "category": "personal"},
                "started_at": "2026-04-01T00:00:00Z",
                "source": "phone",
            }
        ]
    )
    result = cli_runner.invoke(app, ["--json", "conversation", "list"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload[0]["id"] == "c1"


def test_conversation_create_posts_text(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.post("/v1/dev/user/conversations").respond(
        json={"id": "c1", "status": "completed", "discarded": False}
    )
    result = cli_runner.invoke(
        app, ["--json", "conversation", "create", "--text", "the weather today is fine", "--language", "en"]
    )
    assert result.exit_code == 0
    body = json.loads(route.calls.last.request.content)
    assert body["text"].startswith("the weather")
    assert body["language"] == "en"


def test_conversation_get_includes_transcript_param(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.get("/v1/dev/user/conversations/c1").respond(
        json={"id": "c1", "structured": {"title": "x"}, "transcript_segments": []}
    )
    result = cli_runner.invoke(app, ["--json", "conversation", "get", "c1", "--include-transcript"])
    assert result.exit_code == 0
    request = route.calls.last.request
    assert request.url.params["include_transcript"] == "true"


def test_conversation_update_requires_field(authed_profile, cli_runner) -> None:
    result = cli_runner.invoke(app, ["conversation", "update", "c1"])
    assert result.exit_code == 1
    assert "no fields to update" in result.stderr.lower()


def test_conversation_delete_with_yes(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.delete("/v1/dev/user/conversations/c1").respond(json={"success": True})
    result = cli_runner.invoke(app, ["conversation", "delete", "c1", "--yes"])
    assert result.exit_code == 0


def test_conversation_from_segments_reads_file(authed_profile, respx_mock, cli_runner, tmp_path) -> None:
    f = tmp_path / "segments.json"
    segments = {
        "transcript_segments": [
            {"text": "hi", "start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"},
            {"text": "hello", "start": 1.5, "end": 2.5, "speaker": "SPEAKER_01"},
        ]
    }
    f.write_text(json.dumps(segments))
    route = respx_mock.post("/v1/dev/user/conversations/from-segments").respond(
        json={"id": "c1", "status": "completed", "discarded": False}
    )
    result = cli_runner.invoke(app, ["--json", "conversation", "from-segments", str(f), "--source", "phone"])
    assert result.exit_code == 0
    body = json.loads(route.calls.last.request.content)
    assert len(body["transcript_segments"]) == 2
    assert body["source"] == "phone"
