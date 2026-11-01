"""Tests for ``omi conversation`` commands."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from omi_cli.main import app, main
from omi_cli.models import CONVERSATION_TEXT_MAX_LENGTH, CONVERSATION_TITLE_MAX_LENGTH


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


def test_conversation_create_rejects_oversize_text_without_sending(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.post("/v1/dev/user/conversations").respond(
        json={"id": "c1", "status": "completed", "discarded": False}
    )
    oversize = "x" * (CONVERSATION_TEXT_MAX_LENGTH + 1)
    result = cli_runner.invoke(app, ["conversation", "create", "--text", oversize])
    assert result.exit_code == 1  # EXIT_USAGE
    assert "too long" in result.stderr.lower()
    # The point of the check: the write budget is not spent on a doomed request.
    assert not route.called


def test_conversation_create_accepts_text_at_the_limit(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.post("/v1/dev/user/conversations").respond(
        json={"id": "c1", "status": "completed", "discarded": False}
    )
    at_limit = "x" * CONVERSATION_TEXT_MAX_LENGTH
    result = cli_runner.invoke(app, ["conversation", "create", "--text", at_limit])
    assert result.exit_code == 0, result.stderr
    assert len(json.loads(route.calls.last.request.content)["text"]) == CONVERSATION_TEXT_MAX_LENGTH


def test_conversation_update_rejects_oversize_title_without_sending(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.patch("/v1/dev/user/conversations/c1").respond(json={"id": "c1"})
    result = cli_runner.invoke(
        app, ["conversation", "update", "c1", "--title", "t" * (CONVERSATION_TITLE_MAX_LENGTH + 1)]
    )
    assert result.exit_code == 1  # EXIT_USAGE
    assert "too long" in result.stderr.lower()
    assert not route.called


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


def test_conversation_delete_missing_empty_404_exits_not_found(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.delete("/v1/dev/user/conversations/missing").respond(404)
    result = cli_runner.invoke(app, ["conversation", "delete", "missing", "--yes"])
    assert result.exit_code == 5  # EXIT_NOT_FOUND


def test_conversation_get_missing_empty_404_json_exits_not_found(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.get("/v1/dev/user/conversations/missing").respond(404)
    result = cli_runner.invoke(app, ["--json", "conversation", "get", "missing"])
    assert result.exit_code == 5  # EXIT_NOT_FOUND


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


def test_conversation_from_segments_rejects_directory(config_path, respx_mock, monkeypatch, capsys, tmp_path) -> None:
    test_dir = tmp_path / "somedir"
    test_dir.mkdir()
    monkeypatch.setattr(sys, "argv", ["omi", "--json", "conversation", "from-segments", str(test_dir)])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    output = capsys.readouterr()
    err = json.loads(output.err)
    assert "Expected a file, but found a directory" in err["error"]
    assert not respx_mock.calls


def test_conversation_from_segments_missing_file_is_not_found(
    config_path, respx_mock, monkeypatch, capsys, tmp_path
) -> None:
    missing = tmp_path / "missing.json"
    monkeypatch.setattr(sys, "argv", ["omi", "--json", "conversation", "from-segments", str(missing)])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    err = json.loads(capsys.readouterr().err)
    assert err["error"] == f"File not found: {missing}"
    assert not respx_mock.calls


def test_conversation_from_segments_file_parent_is_not_a_directory(
    config_path, respx_mock, monkeypatch, capsys, tmp_path
) -> None:
    """``Path.exists()`` swallows ``ENOTDIR`` and returns False, so a pre-check
    reported ``regular_file/segments.json`` as a missing file. Opening the path
    keeps the real ``NotADirectoryError``."""
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("file", encoding="utf-8")
    segments = blocker / "segments.json"
    monkeypatch.setattr(sys, "argv", ["omi", "--json", "conversation", "from-segments", str(segments)])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    err = json.loads(capsys.readouterr().err)
    assert err["error"] == f"Cannot read file {segments}"
    assert "Not a directory" in err["detail"]
    assert "File not found" not in err["error"]
    assert not respx_mock.calls


def test_conversation_from_segments_windows_directory_error_is_still_a_directory(
    config_path, respx_mock, monkeypatch, capsys, tmp_path
) -> None:
    """Windows opens a directory as ``PermissionError``, not ``IsADirectoryError``."""
    test_dir = tmp_path / "somedir"
    test_dir.mkdir()

    def windows_read_bytes(self):
        raise PermissionError(13, "Permission denied", str(self))

    monkeypatch.setattr(type(test_dir), "read_bytes", windows_read_bytes)
    monkeypatch.setattr(sys, "argv", ["omi", "--json", "conversation", "from-segments", str(test_dir)])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert "Expected a file, but found a directory" in json.loads(capsys.readouterr().err)["error"]
    assert not respx_mock.calls


def test_conversation_from_segments_windows_file_parent_is_still_not_a_directory(
    config_path, respx_mock, monkeypatch, capsys, tmp_path
) -> None:
    """Windows reports a path under a regular file as not found rather than ENOTDIR."""
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("file", encoding="utf-8")
    segments = blocker / "segments.json"

    def windows_read_bytes(self):
        raise FileNotFoundError(2, "The system cannot find the path specified", str(self))

    monkeypatch.setattr(type(segments), "read_bytes", windows_read_bytes)
    monkeypatch.setattr(sys, "argv", ["omi", "--json", "conversation", "from-segments", str(segments)])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    err = json.loads(capsys.readouterr().err)
    assert err["error"] == f"Cannot read file {segments}"
    assert "Not a directory" in err["detail"]
    assert not respx_mock.calls


def test_conversation_from_segments_dotdot_past_a_file_is_still_not_found(
    config_path, respx_mock, monkeypatch, capsys, tmp_path
) -> None:
    """Win32 collapses ``notes.txt\\..`` before lookup, so the file is not the blocker."""
    (tmp_path / "notes.txt").write_text("file", encoding="utf-8")
    segments = tmp_path / "notes.txt" / ".." / "missing.json"

    def windows_read_bytes(self):
        raise FileNotFoundError(2, "The system cannot find the file specified", str(self))

    monkeypatch.setattr(type(segments), "read_bytes", windows_read_bytes)
    monkeypatch.setattr(sys, "argv", ["omi", "--json", "conversation", "from-segments", str(segments)])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert json.loads(capsys.readouterr().err)["error"] == f"File not found: {segments}"
    assert not respx_mock.calls


@pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="POSIX non-root directory traversal permissions only",
)
def test_conversation_from_segments_unsearchable_parent_is_a_read_error(
    config_path, respx_mock, monkeypatch, capsys, tmp_path
) -> None:
    """A mode ``0o000`` parent makes ``Path.exists()`` raise ``PermissionError``
    before ``read_bytes()``. That used to escape as ``unexpected error`` instead
    of the read failure this command already reports for an unreadable file."""
    locked = tmp_path / "locked"
    locked.mkdir()
    segments = locked / "segments.json"
    segments.write_text("[]", encoding="utf-8")
    locked.chmod(0o000)
    try:
        monkeypatch.setattr(sys, "argv", ["omi", "--json", "conversation", "from-segments", str(segments)])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1
        err = json.loads(capsys.readouterr().err)
        assert err["error"] == f"Cannot read file {segments}"
        assert "Permission denied" in err["detail"]
        assert "unexpected error" not in err["error"]
        assert not respx_mock.calls
    finally:
        locked.chmod(0o700)


def test_conversation_from_segments_rejects_unreadable_file(
    config_path, respx_mock, monkeypatch, capsys, tmp_path
) -> None:
    f = tmp_path / "unreadable.json"
    f.write_text("{}")

    def fail_read(*args, **kwargs):
        raise PermissionError("Access denied")

    monkeypatch.setattr(Path, "read_bytes", fail_read)
    monkeypatch.setattr(sys, "argv", ["omi", "--json", "conversation", "from-segments", str(f)])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    output = capsys.readouterr()
    err = json.loads(output.err)
    assert "Cannot read file" in err["error"]
    assert not respx_mock.calls


@pytest.mark.parametrize("bad_text", ["", "   ", " \n \t "])
def test_conversation_create_rejects_empty_text(authed_profile, respx_mock, cli_runner, bad_text) -> None:
    result = cli_runner.invoke(app, ["conversation", "create", "--text", bad_text])
    assert result.exit_code == 1
    assert "Empty text" in result.stderr


@pytest.mark.parametrize("bad_lang", ["", "   "])
def test_conversation_create_rejects_empty_language(authed_profile, respx_mock, cli_runner, bad_lang) -> None:
    result = cli_runner.invoke(app, ["conversation", "create", "--text", "hello", "--language", bad_lang])
    assert result.exit_code == 1
    assert "Invalid language" in result.stderr


def test_conversation_create_escapes_markup_in_id_and_status(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.post("/v1/dev/user/conversations").respond(
        json={"id": "convo[bold]special[/bold]", "status": "pending[cyan]review[/cyan]", "discarded": False}
    )
    result = cli_runner.invoke(app, ["conversation", "create", "--text", "hello world"])
    assert result.exit_code == 0
    assert "convo[bold]special[/bold]" in result.stdout
    assert "pending[cyan]review[/cyan]" in result.stdout


def test_conversation_from_segments_escapes_markup_in_id(authed_profile, respx_mock, cli_runner, tmp_path) -> None:
    f = tmp_path / "segments.json"
    f.write_text(json.dumps([{"text": "hi", "start": 0.0, "end": 1.0}]))
    respx_mock.post("/v1/dev/user/conversations/from-segments").respond(
        json={"id": "seg[bold]special[/bold]", "status": "completed", "discarded": False}
    )
    result = cli_runner.invoke(app, ["conversation", "from-segments", str(f)])
    assert result.exit_code == 0
    assert "seg[bold]special[/bold]" in result.stdout


@pytest.mark.parametrize("bad_title", ["", "   "])
def test_conversation_update_rejects_empty_title(authed_profile, respx_mock, cli_runner, bad_title) -> None:
    result = cli_runner.invoke(app, ["conversation", "update", "c1", "--title", bad_title])
    assert result.exit_code == 1
    assert "Invalid title" in result.stderr
