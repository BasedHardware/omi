"""Tests for conversations to Apache Parquet exporter recipe (#19056).

Verifies Parquet schema generation, fallback handling, timestamp normalization,
action items extraction from both dicts and strings, duration computation,
and real list-endpoint output handling (missing duration/transcripts).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import pytest

script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_parquet.py"
spec = importlib.util.spec_from_file_location("conversations_to_parquet", script_path)
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)

normalize_iso_timestamp = _mod.normalize_iso_timestamp
calculate_duration_seconds = _mod.calculate_duration_seconds
extract_segments_data = _mod.extract_segments_data
extract_action_items = _mod.extract_action_items
normalize_conversation_record = _mod.normalize_conversation_record
parse_omi_conversations = _mod.parse_omi_conversations
records_to_columnar_dict = _mod.records_to_columnar_dict
build_pyarrow_table = _mod.build_pyarrow_table
write_parquet_file = _mod.write_parquet_file
inspect_parquet_file = _mod.inspect_parquet_file
main = _mod.main


def test_normalize_iso_timestamp():
    assert normalize_iso_timestamp(None) is None
    assert normalize_iso_timestamp("") is None

    # Epoch timestamp
    ts = normalize_iso_timestamp(1704067200)
    assert ts == "2024-01-01T00:00:00Z"

    # ISO string
    iso = normalize_iso_timestamp("2026-09-25T14:30:00Z")
    assert iso == "2026-09-25T14:30:00Z"

    # ISO with offset
    iso_offset = normalize_iso_timestamp("2026-09-25T16:30:00+02:00")
    assert iso_offset == "2026-09-25T14:30:00Z"


def test_calculate_duration_seconds():
    # From finished_at - started_at
    dur = calculate_duration_seconds("2026-09-25T10:00:00Z", "2026-09-25T10:30:00Z")
    assert dur == 1800.0

    # With missing timestamps
    assert calculate_duration_seconds(None, None) == 0.0
    assert calculate_duration_seconds("2026-09-25T10:00:00Z", None) == 0.0

    # Fallback to duration field if present
    assert calculate_duration_seconds(None, None, fallback_duration=120.5) == 120.5


def test_extract_action_items_from_objects_and_strings():
    # API emits objects with description / completed
    api_items = [
        {"description": "Benchmark latency", "completed": False},
        {"description": "Write Parquet exporter", "completed": True},
    ]
    extracted = extract_action_items(api_items)
    assert extracted == ["Benchmark latency", "Write Parquet exporter"]

    # Also supports plain strings
    plain_items = ["Item 1", "Item 2"]
    assert extract_action_items(plain_items) == ["Item 1", "Item 2"]

    assert extract_action_items([]) == []
    assert extract_action_items(None) == []


def test_extract_segments_data():
    segments = [
        {"text": "Good morning everyone.", "speaker": "Alice", "start": 0.0, "end": 2.5},
        {"text": "Morning Alice, let's start the demo.", "speaker": "Bob", "start": 3.0, "end": 6.0},
        {"text": "Agreed.", "speaker": "Alice", "start": 6.5, "end": 7.5},
    ]
    transcript, count, num_speakers = extract_segments_data(segments)
    assert count == 3
    assert num_speakers == 2
    assert "Alice: Good morning everyone." in transcript
    assert "Bob: Morning Alice" in transcript

    assert extract_segments_data([]) == ("", 0, 0)
    assert extract_segments_data(None) == ("", 0, 0)


def test_real_list_endpoint_output_without_transcript_or_duration():
    """Validates realistic payload from `GET /v1/dev/user/conversations` default list."""
    real_api_payload = {
        "id": "conv_real_123",
        "created_at": "2026-09-25T10:00:00Z",
        "started_at": "2026-09-25T10:00:00Z",
        "finished_at": "2026-09-25T10:15:00Z",
        "source": "omi",
        "structured": {
            "title": "Quick Standup",
            "overview": "Team sync on release status",
            "category": "work",
            "action_items": [
                {"description": "Review PR 19056", "completed": False}
            ]
        }
        # Notice: no duration, no user_id, no transcript_segments
    }
    rec = normalize_conversation_record(real_api_payload)
    assert rec["id"] == "conv_real_123"
    assert rec["title"] == "Quick Standup"
    assert rec["duration_seconds"] == 900.0  # Derived from finished_at - started_at
    assert rec["action_items"] == '["Review PR 19056"]'
    assert rec["num_action_items"] == 1
    assert rec["full_transcript"] == ""
    assert rec["num_segments"] == 0
    assert rec["num_speakers"] == 0


def test_parse_omi_conversations():
    sample_list = [
        {"id": "c1", "title": "Conv 1"},
        {"id": "c2", "title": "Conv 2"},
    ]
    parsed = parse_omi_conversations(sample_list)
    assert len(parsed) == 2

    # Wrapped in dictionary with 'conversations'
    sample_dict = {"conversations": [{"id": "c1", "title": "Sample"}]}
    assert len(parse_omi_conversations(sample_dict)) == 1

    # Empty payload
    assert parse_omi_conversations("[]") == []
    assert parse_omi_conversations("") == []


def test_records_to_columnar_dict():
    records = [
        normalize_conversation_record({"id": "c1", "title": "First"}),
        normalize_conversation_record({"id": "c2", "title": "Second"}),
    ]
    cols = records_to_columnar_dict(records)
    assert len(cols["id"]) == 2
    assert cols["id"] == ["c1", "c2"]
    assert cols["title"] == ["First", "Second"]
    assert len(cols["duration_seconds"]) == 2


def test_pyarrow_table_and_parquet_roundtrip(tmp_path):
    pytest.importorskip("pyarrow")
    records = [
        normalize_conversation_record(
            {
                "id": f"conv_{i}",
                "started_at": f"2026-09-25T10:0{i}:00Z",
                "finished_at": f"2026-09-25T10:1{i}:00Z",
                "structured": {
                    "title": f"Meeting {i}",
                    "category": "work",
                    "action_items": [{"description": f"Task {i}"}],
                },
                "transcript_segments": [{"text": f"Line {i} content", "speaker": f"Speaker_{i}"}],
            }
        )
        for i in range(5)
    ]

    table = build_pyarrow_table(records)
    assert table.num_rows == 5
    assert len(table.schema.names) == 20

    out_file = tmp_path / "conversations.parquet"
    count, size, is_fallback = write_parquet_file(records, out_file, compression="snappy")
    assert count == 5
    assert size > 0
    assert is_fallback is False
    assert out_file.exists()

    # Inspect file
    info = inspect_parquet_file(out_file)
    assert info["num_rows"] == 5
    assert info["num_columns"] == 20
    assert "title" in info["columns"]
    assert "full_transcript" in info["columns"]
    assert "duration_seconds" in info["columns"]


def test_fallback_columnar_export(tmp_path, monkeypatch):
    records = [
        normalize_conversation_record({"id": "fb_conv_1", "title": "Fallback Test"}),
    ]

    def fake_build(recs):
        raise ImportError("pyarrow missing")

    monkeypatch.setattr(_mod, "build_pyarrow_table", fake_build)

    out = tmp_path / "fallback_conv.parquet"
    count, size, is_fallback = write_parquet_file(records, out)
    assert count == 1
    assert size > 0
    assert is_fallback is True

    fb_file = tmp_path / "fallback_conv.parquet.json"
    assert fb_file.exists()
    payload = json.loads(fb_file.read_text(encoding="utf-8"))
    assert payload["format"] == "columnar_parquet_fallback"
    assert payload["num_rows"] == 1
    assert payload["columns"]["id"] == ["fb_conv_1"]


def test_cli_execution_with_file(tmp_path, capsys):
    input_file = tmp_path / "convs.json"
    output_file = tmp_path / "result.parquet"

    input_data = [
        {"id": "cli_c1", "structured": {"title": "CLI Sync 1", "category": "work"}},
        {"id": "cli_c2", "structured": {"title": "CLI Sync 2", "category": "personal"}},
    ]
    input_file.write_text(json.dumps(input_data), encoding="utf-8")

    # Run with limit 1
    ret = main(["-i", str(input_file), "-o", str(output_file), "-n", "1"])
    assert ret == 0
    assert output_file.exists() or Path(f"{output_file}.json").exists()


def test_cli_schema_flag(tmp_path, capsys):
    input_file = tmp_path / "convs.json"
    input_data = [{"id": "schema_conv", "title": "Schema test"}]
    input_file.write_text(json.dumps(input_data), encoding="utf-8")

    ret = main(["-i", str(input_file), "--schema"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Apache Parquet Inferred Schema for Conversations:" in captured.out
    assert "full_transcript" in captured.out
    assert "duration_seconds" in captured.out
