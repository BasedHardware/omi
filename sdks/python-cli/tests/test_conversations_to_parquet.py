import importlib.util
import json
from pathlib import Path
import pytest

# Robust dynamic loader for recipe module in examples/ or local directory
_recipe_candidates = [
    Path(__file__).resolve().parent.parent / "examples" / "conversations_to_parquet.py",
    Path(__file__).resolve().parent / "conversations_to_parquet.py",
]
_recipe_path = next((p for p in _recipe_candidates if p.exists()), None)
if _recipe_path is None:
    raise FileNotFoundError("Could not locate conversations_to_parquet.py in search paths")

_spec = importlib.util.spec_from_file_location("conversations_to_parquet", _recipe_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

normalize_iso_timestamp = _mod.normalize_iso_timestamp
extract_segments_data = _mod.extract_segments_data
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

    iso_offset = normalize_iso_timestamp("2026-09-25T16:30:00+02:00")
    assert iso_offset == "2026-09-25T14:30:00Z"


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

    # Empty segments
    assert extract_segments_data([]) == ("", 0, 0)
    assert extract_segments_data(None) == ("", 0, 0)


def test_normalize_conversation_record():
    raw = {
        "id": "conv_999",
        "structured": {
            "title": "Architecture Review",
            "overview": "Deep dive into async pipelines and streaming",
            "category": "Engineering",
            "action_items": ["Benchmark latency", "Write Parquet exporter"],
        },
        "source": "desktop",
        "language": "en",
        "user_id": "usr_777",
        "createdAt": "2026-09-25T10:00:00Z",
        "updatedAt": "2026-09-25T10:45:00Z",
        "startedAt": "2026-09-25T10:00:00Z",
        "finishedAt": "2026-09-25T10:40:00Z",
        "duration": 2400.0,
        "discarded": False,
        "transcript_segments": [
            {"text": "Testing transcription pipeline.", "speaker": "Dev", "start": 0.0, "end": 3.0}
        ],
    }
    rec = normalize_conversation_record(raw)
    assert rec["id"] == "conv_999"
    assert rec["title"] == "Architecture Review"
    assert rec["overview"] == "Deep dive into async pipelines and streaming"
    assert rec["category"] == "engineering"
    assert rec["language"] == "en"
    assert rec["source"] == "desktop"
    assert rec["user_id"] == "usr_777"
    assert rec["duration_seconds"] == 2400.0
    assert rec["is_discarded"] is False
    assert rec["num_segments"] == 1
    assert rec["num_speakers"] == 1
    assert "Dev: Testing transcription pipeline." in rec["full_transcript"]
    assert '["Benchmark latency", "Write Parquet exporter"]' == rec["action_items"]
    assert rec["char_len"] == len(rec["full_transcript"])
    assert rec["word_count"] == 4


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
                "structured": {"title": f"Meeting {i}", "category": "work"},
                "duration": 60.0 * i,
                "transcript_segments": [{"text": f"Line {i} content", "speaker": f"Speaker_{i}"}],
            }
        )
        for i in range(5)
    ]

    table = build_pyarrow_table(records)
    assert table.num_rows == 5
    assert len(table.schema.names) == 19

    out_file = tmp_path / "conversations.parquet"
    count, size, is_fallback = write_parquet_file(records, out_file, compression="snappy")
    assert count == 5
    assert size > 0
    assert is_fallback is False
    assert out_file.exists()

    # Inspect file
    info = inspect_parquet_file(out_file)
    assert info["num_rows"] == 5
    assert info["num_columns"] == 19
    assert "title" in info["columns"]
    assert "full_transcript" in info["columns"]


def test_compression_codecs(tmp_path):
    pytest.importorskip("pyarrow")
    records = [
        normalize_conversation_record(
            {
                "id": f"conv_{i}",
                "structured": {"title": f"Meeting {i}"},
                "transcript_segments": [{"text": f"Repetitive text {i} " * 20, "speaker": "A"}],
            }
        )
        for i in range(5)
    ]

    for codec in ["snappy", "gzip", "none"]:
        out = tmp_path / f"conv_{codec}.parquet"
        count, size, is_fallback = write_parquet_file(records, out, compression=codec)
        assert count == 5
        assert size > 0
        assert is_fallback is False
        info = inspect_parquet_file(out)
        assert info["num_rows"] == 5


def test_fallback_columnar_export(tmp_path, monkeypatch):
    records = [
        normalize_conversation_record({"id": "fb_conv_1", "title": "Fallback Test"}),
    ]

    # Simulate pyarrow not installed
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


def test_cli_missing_input_file(tmp_path):
    missing_file = tmp_path / "non_existent.json"
    ret = main(["-i", str(missing_file)])
    assert ret == 1
