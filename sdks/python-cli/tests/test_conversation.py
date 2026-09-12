"""Tests for ``omi conversation`` commands."""

from __future__ import annotations

import json

import pytest

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


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16", "utf-32"])
def test_conversation_from_segments_preserves_unicode(
    authed_profile, respx_mock, cli_runner, tmp_path, encoding
) -> None:
    segments = [{"text": "Caf\u00e9, \u65e5\u672c\u8a9e \U0001f642", "start": 0.0, "end": 1.0}]
    source = tmp_path / "segments.json"
    source.write_bytes(json.dumps(segments, ensure_ascii=False).encode(encoding))
    route = respx_mock.post("/v1/dev/user/conversations/from-segments").respond(
        json={"id": "c1", "status": "completed", "discarded": False}
    )

    result = cli_runner.invoke(app, ["--json", "conversation", "from-segments", str(source)])

    assert result.exit_code == 0, result.output
    assert json.loads(route.calls.last.request.content)["transcript_segments"] == segments


def test_conversation_from_segments_rejects_invalid_unicode(config_path, respx_mock, cli_runner, tmp_path) -> None:
    source = tmp_path / "segments.json"
    source.write_bytes(b'[{"text": "\xff", "start": 0, "end": 1}]')

    result = cli_runner.invoke(app, ["--json", "conversation", "from-segments", str(source)])

    assert result.exit_code == 1
    assert "Invalid JSON" in result.stderr
    assert not respx_mock.calls


_TRANSCRIPT_SEGMENTS = [
    {"text": "hi", "start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"},
    {"text": "hello", "start": 1.5, "end": 2.5, "speaker": "SPEAKER_01"},
]


def test_conversation_get_srt_writes_stdout(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.get("/v1/dev/user/conversations/c1").respond(
        json={"id": "c1", "transcript_segments": _TRANSCRIPT_SEGMENTS}
    )

    result = cli_runner.invoke(app, ["conversation", "get", "c1", "--include-transcript", "--format", "srt"])

    assert result.exit_code == 0, result.output
    # Cue numbering starts at 1, timestamps are comma-separated, and cues are blank-line separated.
    assert result.stdout.startswith("1\n00:00:00,000 --> 00:00:01,000\nhi\n")
    assert "2\n00:00:01,500 --> 00:00:02,500\nhello\n" in result.stdout


def test_conversation_get_srt_writes_file(authed_profile, respx_mock, cli_runner, tmp_path) -> None:
    respx_mock.get("/v1/dev/user/conversations/c1").respond(
        json={"id": "c1", "transcript_segments": _TRANSCRIPT_SEGMENTS}
    )
    target = tmp_path / "transcript.srt"

    result = cli_runner.invoke(
        app,
        ["conversation", "get", "c1", "--include-transcript", "--format", "srt", "--output", str(target)],
    )

    assert result.exit_code == 0, result.output
    written = target.read_text(encoding="utf-8")
    assert written.startswith("1\n00:00:00,000 --> 00:00:01,000\nhi\n")
    assert "hello" in written


def test_conversation_get_srt_skips_segments_without_start(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.get("/v1/dev/user/conversations/c1").respond(
        json={
            "id": "c1",
            "transcript_segments": [
                {"text": "no timestamp"},
                {"text": "kept", "start": 3.0, "end": 4.0},
            ],
        }
    )

    result = cli_runner.invoke(app, ["conversation", "get", "c1", "--include-transcript", "--format", "srt"])

    assert result.exit_code == 0, result.output
    # The untimed segment is dropped rather than given a fabricated cue time; the
    # surviving cue keeps index 1 so the track stays contiguous.
    assert "no timestamp" not in result.stdout
    assert result.stdout.startswith("1\n00:00:03,000 --> 00:00:04,000\nkept\n")


def test_conversation_get_srt_clamps_negative_start(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.get("/v1/dev/user/conversations/c1").respond(
        json={"id": "c1", "transcript_segments": [{"text": "early", "start": -0.25, "end": 0.5}]}
    )

    result = cli_runner.invoke(app, ["conversation", "get", "c1", "--include-transcript", "--format", "srt"])

    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("1\n00:00:00,000 --> 00:00:00,500\nearly\n")


def test_conversation_get_srt_requires_transcript_flag(authed_profile, cli_runner) -> None:
    result = cli_runner.invoke(app, ["conversation", "get", "c1", "--format", "srt"])

    assert result.exit_code == 1
    assert "--include-transcript" in result.stderr


def test_conversation_get_rejects_unknown_format(authed_profile, cli_runner) -> None:
    result = cli_runner.invoke(app, ["conversation", "get", "c1", "--format", "vtt"])

    assert result.exit_code == 1
    assert "Unsupported --format" in result.stderr
