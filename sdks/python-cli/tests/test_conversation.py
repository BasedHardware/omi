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


def test_conversation_export_writes_srt(authed_profile, respx_mock, cli_runner, tmp_path) -> None:
    respx_mock.get("/v1/dev/user/conversations/c1").respond(
        json={
            "id": "c1",
            "structured": {"title": "x"},
            "transcript_segments": [
                {"text": "hi", "start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"},
                {"text": "hello", "start": 1.5, "end": 2.5, "speaker": "SPEAKER_01"},
            ],
        }
    )
    out = tmp_path / "out.srt"
    result = cli_runner.invoke(app, ["--json", "conversation", "export", "c1", "--output", str(out)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["segments"] == 2
    assert payload["skipped"] == 0
    content = out.read_text(encoding="utf-8")
    assert content.splitlines()[0] == "1"
    assert "00:00:00,000 --> 00:00:01,000" in content
    assert "00:00:01,500 --> 00:00:02,500" in content
    assert "hello" in content


def test_conversation_export_skips_invalid_segments(authed_profile, respx_mock, cli_runner, tmp_path) -> None:
    respx_mock.get("/v1/dev/user/conversations/c1").respond(
        json={
            "id": "c1",
            "structured": {"title": "x"},
            "transcript_segments": [
                {"text": "good", "start": 0.0, "end": 1.0},
                {"text": "no end", "start": 2.0},
                {"text": "reversed", "start": 5.0, "end": 4.0},
                {"text": "", "start": 6.0, "end": 7.0},
                "not-a-dict",
            ],
        }
    )
    out = tmp_path / "out.srt"
    result = cli_runner.invoke(app, ["--json", "conversation", "export", "c1", "--output", str(out)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["segments"] == 1
    assert payload["skipped"] == 4
    content = out.read_text(encoding="utf-8")
    assert "good" in content and "no end" not in content


def test_conversation_export_refuses_overwrite_without_force(authed_profile, respx_mock, cli_runner, tmp_path) -> None:
    respx_mock.get("/v1/dev/user/conversations/c1").respond(
        json={"id": "c1", "transcript_segments": [{"text": "hi", "start": 0.0, "end": 1.0}]}
    )
    out = tmp_path / "out.srt"
    out.write_text("existing", encoding="utf-8")
    result = cli_runner.invoke(app, ["conversation", "export", "c1", "--output", str(out)])
    assert result.exit_code == 1
    assert "already exists" in result.stderr.lower()
    assert out.read_text(encoding="utf-8") == "existing"


def test_conversation_export_force_overwrites(authed_profile, respx_mock, cli_runner, tmp_path) -> None:
    respx_mock.get("/v1/dev/user/conversations/c1").respond(
        json={"id": "c1", "transcript_segments": [{"text": "hi", "start": 0.0, "end": 1.0}]}
    )
    out = tmp_path / "out.srt"
    out.write_text("existing", encoding="utf-8")
    result = cli_runner.invoke(app, ["conversation", "export", "c1", "--output", str(out), "--force"])
    assert result.exit_code == 0, result.output
    assert "hi" in out.read_text(encoding="utf-8")


def test_conversation_export_no_valid_segments(authed_profile, respx_mock, cli_runner, tmp_path) -> None:
    respx_mock.get("/v1/dev/user/conversations/c1").respond(
        json={"id": "c1", "structured": {"title": "x"}, "transcript_segments": []}
    )
    out = tmp_path / "out.srt"
    result = cli_runner.invoke(app, ["conversation", "export", "c1", "--output", str(out)])
    assert result.exit_code == 1
    assert "no valid transcript segments" in result.stderr.lower()
    assert not out.exists()


def test_conversation_export_missing_timing_handled(authed_profile, respx_mock, cli_runner, tmp_path) -> None:
    respx_mock.get("/v1/dev/user/conversations/c1").respond(
        json={
            "id": "c1",
            "transcript_segments": [{"text": "bool start", "start": True, "end": 1.0}],
        }
    )
    out = tmp_path / "out.srt"
    result = cli_runner.invoke(app, ["conversation", "export", "c1", "--output", str(out)])
    assert result.exit_code == 1
    assert not out.exists()


def test_conversation_export_rejects_bad_timing_and_blank_lines(authed_profile, respx_mock, cli_runner, tmp_path) -> None:
    body = json.dumps(
        {
            "id": "c1",
            "transcript_segments": [
                {"text": "string start", "start": "0.5", "end": 1.0},
                {"text": "negative", "start": -2.0, "end": 1.0},
                {"text": "nan start", "start": float("nan"), "end": 1.0},
                {"text": "inf end", "start": 0.0, "end": float("inf")},
                {"text": "multi\n\nline\ntext", "start": 0.0, "end": 1.0},
            ],
        }
    )  # allow_nan default keeps NaN/Infinity literals, which standard JSON parsers reject
    respx_mock.get("/v1/dev/user/conversations/c1").respond(content=body.encode("utf-8"))
    out = tmp_path / "out.srt"
    result = cli_runner.invoke(app, ["--json", "conversation", "export", "c1", "--output", str(out)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["segments"] == 1
    assert payload["skipped"] == 4
    content = out.read_text(encoding="utf-8")
    # surviving cue has the blank line collapsed - never an SRT cue separator inside text
    assert "multi\nline\ntext" in content
    assert "\n\n" not in content.rstrip("\n")
