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
compute_duration_seconds = _mod.compute_duration_seconds
extract_segments_data = _mod.extract_segments_data
extract_action_item_text = _mod.extract_action_item_text
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

    # ISO strings
    iso = normalize_iso_timestamp("2026-09-25T14:30:00Z")
    assert iso == "2026-09-25T14:30:00Z"


def test_compute_duration_seconds():
    # Explicit duration
    assert compute_duration_seconds(None, None, explicit_duration=120) == 120.0
    # Derived from timestamps
    start = "2026-09-25T10:00:00Z"
    finish = "2026-09-25T10:15:30Z"
    assert compute_duration_seconds(start, finish) == 930.0
    # Missing timestamps
    assert compute_duration_seconds(start, None) == 0.0
    assert compute_duration_seconds(None, finish) == 0.0


def test_extract_segments_data():
    segments = [
        {"speaker": "Alice", "text": "Hello, how are you?"},
        {"speaker": "Bob", "text": "I am doing well, thanks!"},
        {"speaker": "Alice", "text": "Great to hear."},
    ]
    transcript, count, num_spk = extract_segments_data(segments)
    assert count == 3
    assert num_spk == 2
    assert "Alice: Hello, how are you?" in transcript
    assert "Bob: I am doing well, thanks!" in transcript

    # Empty
    t_empty, c_empty, s_empty = extract_segments_data([])
    assert t_empty == ""
    assert c_empty == 0
    assert s_empty == 0


def test_extract_action_item_text():
    assert extract_action_item_text({"description": "Test task"}) == "Test task"
    assert extract_action_item_text({"title": "Another task"}) == "Another task"
    assert extract_action_item_text("Plain string task") == "Plain string task"


def test_normalize_conversation_record():
    raw = {
        "id": "conv_101",
        "createdAt": "2026-09-25T10:00:00Z",
        "startedAt": "2026-09-25T10:00:00Z",
        "finishedAt": "2026-09-25T10:10:00Z",
        "source": "omi",
        "language": "en",
        "structured": {
            "title": "Roadmap Sync",
            "overview": "Quarterly planning discussion",
            "category": "work",
            "action_items": [
                {"description": "Draft engineering spec", "completed": False},
                {"description": "Schedule design review", "completed": True},
            ],
        },
        "transcript_segments": [
            {"speaker": "Lead", "text": "Let's review the milestones."},
            {"speaker": "Eng", "text": "Milestone one is complete."},
        ],
    }
    rec = normalize_conversation_record(raw)
    assert rec["id"] == "conv_101"
    assert rec["title"] == "Roadmap Sync"
    assert rec["overview"] == "Quarterly planning discussion"
    assert rec["category"] == "work"
    assert rec["duration_seconds"] == 600.0
    assert rec["num_segments"] == 2
    assert rec["num_speakers"] == 2
    assert "Lead: Let's review the milestones." in rec["full_transcript"]
    assert json.loads(rec["action_items"]) == ["Draft engineering spec", "Schedule design review"]
    assert rec["char_len"] == len(rec["full_transcript"])
    assert rec["word_count"] == 10


def test_real_cli_conversation_shape():
    """Verify that a real list-endpoint response without transcripts and with dict action items maps cleanly."""
    real_cli_record = {
        "id": "f81d4fae-7dec-11d0-a765-00a0c91e6bf6",
        "created_at": "2026-09-25T12:00:00.000000Z",
        "started_at": "2026-09-25T12:00:00.000000Z",
        "finished_at": "2026-09-25T12:20:00.000000Z",
        "source": "omi",
        "language": "en",
        "structured": {
            "title": "Edge AI Benchmark",
            "overview": "Benchmarking low-power NPU inference",
            "category": "interesting",
            "action_items": [
                {"description": "Benchmark latency", "completed": False},
            ],
        },
    }
    rec = normalize_conversation_record(real_cli_record)
    assert rec["id"] == "f81d4fae-7dec-11d0-a765-00a0c91e6bf6"
    assert rec["title"] == "Edge AI Benchmark"
    assert rec["duration_seconds"] == 1200.0
    assert rec["num_segments"] == 0
    assert rec["num_speakers"] == 0
    assert rec["full_transcript"] == ""
    assert json.loads(rec["action_items"]) == ["Benchmark latency"]


def test_parse_omi_conversations():
    sample_list = [
        {"id": "c1", "structured": {"title": "Conv 1"}},
        {"id": "c2", "structured": {"title": "Conv 2"}},
    ]
    parsed = parse_omi_conversations(sample_list)
    assert len(parsed) == 2

    sample_dict = {"conversations": [{"id": "c1", "title": "Direct title"}]}
    assert len(parse_omi_conversations(sample_dict)) == 1

    assert parse_omi_conversations("[]") == []
    assert parse_omi_conversations("") == []


def test_records_to_columnar_dict():
    records = [
        {
            "id": "1",
            "title": "Title 1",
            "overview": "Overview 1",
            "category": "work",
            "language": "en",
            "source": "omi",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": None,
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:10:00Z",
            "duration_seconds": 600.0,
            "num_segments": 0,
            "num_speakers": 0,
            "full_transcript": "",
            "action_items": "[]",
            "char_len": 0,
            "word_count": 0,
        }
    ]
    cols = records_to_columnar_dict(records)
    assert cols["id"] == ["1"]
    assert cols["duration_seconds"] == [600.0]


def test_pyarrow_table_and_parquet_roundtrip(tmp_path):
    pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq

    records = [
        normalize_conversation_record(
            {
                "id": f"conv_{i}",
                "structured": {"title": f"Conv title {i}", "category": "work"},
                "started_at": "2026-09-25T10:00:00Z",
                "finished_at": "2026-09-25T10:15:00Z",
                "transcript_segments": [{"speaker": "A", "text": "Hello"}],
            }
        )
        for i in range(10)
    ]

    table = build_pyarrow_table(records)
    assert table.num_rows == 10
    assert table.num_columns == 17

    out_file = tmp_path / "test_convs.parquet"
    num_rec, size, is_fallback = write_parquet_file(records, out_file, compression="snappy")
    assert num_rec == 10
    assert size > 0
    assert is_fallback is False
    assert out_file.exists()

    info = inspect_parquet_file(out_file)
    assert info["num_rows"] == 10
    assert info["num_columns"] == 17
    assert "duration_seconds" in info["columns"]
    assert "full_transcript" in info["columns"]

    read_table = pq.read_table(str(out_file))
    assert read_table.num_rows == 10


def test_compression_codecs(tmp_path):
    pytest.importorskip("pyarrow")
    records = [
        normalize_conversation_record(
            {
                "id": f"c_{i}",
                "structured": {"title": f"Title {i}" * 10},
                "started_at": "2026-09-25T10:00:00Z",
                "finished_at": "2026-09-25T10:20:00Z",
            }
        )
        for i in range(25)
    ]

    for codec in ["snappy", "gzip", "zstd", "none"]:
        out_file = tmp_path / f"test_{codec}.parquet"
        num, size, fallback = write_parquet_file(records, out_file, compression=codec)
        assert num == 25
        assert size > 0
        assert out_file.exists()


def test_fallback_columnar_export(tmp_path, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name.startswith("pyarrow"):
            raise ImportError("Simulated missing pyarrow")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    records = [normalize_conversation_record({"id": "c1", "structured": {"title": "Fallback Conv"}})]
    out_file = tmp_path / "fallback.parquet"
    num, size, is_fallback = write_parquet_file(records, out_file)
    assert num == 1
    assert is_fallback is True

    json_fallback = tmp_path / "fallback.parquet.json"
    assert json_fallback.exists()
    payload = json.loads(json_fallback.read_text(encoding="utf-8"))
    assert payload["format"] == "columnar_parquet_fallback"
    assert payload["num_rows"] == 1
    assert payload["columns"]["id"] == ["c1"]


def test_cli_execution_with_file(tmp_path):
    sample_file = tmp_path / "conversations.json"
    data = [
        {"id": "c1", "structured": {"title": "Alpha"}},
        {"id": "c2", "structured": {"title": "Beta"}},
    ]
    sample_file.write_text(json.dumps(data), encoding="utf-8")
    out_parquet = tmp_path / "out.parquet"

    exit_code = main(["-i", str(sample_file), "-o", str(out_parquet), "--limit", "1"])
    assert exit_code == 0
    assert out_parquet.exists() or (tmp_path / "out.parquet.json").exists()


def test_cli_schema_flag(capsys):
    raw_json = '[{"id": "conv_99", "structured": {"title": "Schema check"}}]'
    exit_code = main(["--json", raw_json, "--schema"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Apache Parquet Inferred Schema" in captured.out
    assert "duration_seconds" in captured.out
    assert "(float64)" in captured.out
    assert "(string)" in captured.out
    assert "Total records: 1" in captured.out


def test_cli_missing_input_file(tmp_path, capsys):
    exit_code = main(["-i", str(tmp_path / "non_existent.json")])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Error: input file" in captured.err
