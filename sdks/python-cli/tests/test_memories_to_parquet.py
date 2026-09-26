import importlib.util
import json
from pathlib import Path
import pytest

# Robust dynamic loader for recipe module in examples/ or local directory
_recipe_candidates = [
    Path(__file__).resolve().parent.parent / "examples" / "memories_to_parquet.py",
    Path(__file__).resolve().parent / "memories_to_parquet.py",
]
_recipe_path = next((p for p in _recipe_candidates if p.exists()), None)
if _recipe_path is None:
    raise FileNotFoundError("Could not locate memories_to_parquet.py in search paths")

_spec = importlib.util.spec_from_file_location("memories_to_parquet", _recipe_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

normalize_iso_timestamp = _mod.normalize_iso_timestamp
extract_tags_json = _mod.extract_tags_json
normalize_memory_record = _mod.normalize_memory_record
parse_omi_memories = _mod.parse_omi_memories
records_to_columnar_dict = _mod.records_to_columnar_dict
build_pyarrow_table = _mod.build_pyarrow_table
write_parquet_file = _mod.write_parquet_file
inspect_parquet_file = _mod.inspect_parquet_file
main = _mod.main


def test_normalize_iso_timestamp():
    assert normalize_iso_timestamp(None) is None
    assert normalize_iso_timestamp("") is None

    # Epoch float timestamp (2024-01-01 00:00:00 UTC = 1704067200)
    ts = normalize_iso_timestamp(1704067200)
    assert ts == "2024-01-01T00:00:00Z"

    # ISO strings
    iso = normalize_iso_timestamp("2026-09-25T14:30:00Z")
    assert iso == "2026-09-25T14:30:00Z"

    iso_offset = normalize_iso_timestamp("2026-09-25T16:30:00+02:00")
    assert iso_offset == "2026-09-25T14:30:00Z"


def test_extract_tags_json():
    assert extract_tags_json(None) == "[]"
    assert extract_tags_json([]) == "[]"
    assert extract_tags_json(["python", "ai"]) == '["python", "ai"]'
    assert extract_tags_json('["data", "lake"]') == '["data", "lake"]'
    assert extract_tags_json("single_tag") == '["single_tag"]'


def test_normalize_memory_record():
    raw = {
        "id": "mem_abc_123",
        "content": "User prefers dark mode in VSCode and terminal",
        "category": "Preference",
        "visibility": "Private",
        "user_id": "usr_999",
        "is_starred": True,
        "is_discarded": False,
        "createdAt": "2026-09-25T10:00:00Z",
        "updatedAt": "2026-09-25T10:05:00Z",
        "tags": ["ui", "editor"],
        "conversation_id": "conv_456",
        "source": "desktop_sync",
    }
    rec = normalize_memory_record(raw)
    assert rec["id"] == "mem_abc_123"
    assert rec["content"] == "User prefers dark mode in VSCode and terminal"
    assert rec["category"] == "preference"
    assert rec["visibility"] == "private"
    assert rec["user_id"] == "usr_999"
    assert rec["is_starred"] is True
    assert rec["is_discarded"] is False
    assert rec["created_at"] == "2026-09-25T10:00:00Z"
    assert rec["updated_at"] == "2026-09-25T10:05:00Z"
    assert rec["conversation_id"] == "conv_456"
    assert rec["tags"] == '["ui", "editor"]'
    assert rec["source"] == "desktop_sync"
    assert rec["char_len"] == len("User prefers dark mode in VSCode and terminal")
    assert rec["word_count"] == 8


def test_parse_omi_memories():
    # Direct list
    sample_list = [
        {"id": "1", "content": "Memory 1"},
        {"id": "2", "content": "Memory 2"},
    ]
    parsed = parse_omi_memories(sample_list)
    assert len(parsed) == 2

    # Wrapped in dictionary with 'memories'
    sample_dict = {"memories": [{"id": "m1", "content": "Sample"}]}
    assert len(parse_omi_memories(sample_dict)) == 1

    # Wrapped in dictionary with 'items'
    sample_items = {"items": [{"id": "m2", "content": "Sample 2"}]}
    assert len(parse_omi_memories(sample_items)) == 1

    # JSON string input
    json_str = json.dumps(sample_list)
    assert len(parse_omi_memories(json_str)) == 2

    # Empty payload
    assert parse_omi_memories("[]") == []
    assert parse_omi_memories("") == []


def test_records_to_columnar_dict():
    records = [
        normalize_memory_record({"id": "1", "content": "First"}),
        normalize_memory_record({"id": "2", "content": "Second"}),
    ]
    cols = records_to_columnar_dict(records)
    assert len(cols["id"]) == 2
    assert cols["id"] == ["1", "2"]
    assert cols["content"] == ["First", "Second"]
    assert len(cols["char_len"]) == 2
    assert len(cols["word_count"]) == 2


def test_pyarrow_table_and_parquet_roundtrip(tmp_path):
    pytest.importorskip("pyarrow")
    records = [
        normalize_memory_record(
            {
                "id": f"mem_{i}",
                "content": f"Memory record #{i} for parquet storage test",
                "category": "fact",
                "tags": [f"tag_{i}", "test"],
                "created_at": "2026-09-25T12:00:00Z",
            }
        )
        for i in range(5)
    ]

    table = build_pyarrow_table(records)
    assert table.num_rows == 5
    assert len(table.schema.names) == 14

    out_file = tmp_path / "output.parquet"
    count, size, is_fallback = write_parquet_file(records, out_file, compression="snappy")
    assert count == 5
    assert size > 0
    assert is_fallback is False
    assert out_file.exists()

    # Inspect file
    info = inspect_parquet_file(out_file)
    assert info["num_rows"] == 5
    assert info["num_columns"] == 14
    assert "content" in info["columns"]
    assert "char_len" in info["columns"]


def test_compression_codecs(tmp_path):
    pytest.importorskip("pyarrow")
    records = [
        normalize_memory_record(
            {
                "id": f"mem_{i}",
                "content": f"Compressible content text repetition {i}" * 10,
                "category": "learning",
            }
        )
        for i in range(10)
    ]

    for codec in ["snappy", "gzip", "none"]:
        out = tmp_path / f"test_{codec}.parquet"
        count, size, is_fallback = write_parquet_file(records, out, compression=codec)
        assert count == 10
        assert size > 0
        assert is_fallback is False
        info = inspect_parquet_file(out)
        assert info["num_rows"] == 10


def test_fallback_columnar_export(tmp_path, monkeypatch):
    records = [
        normalize_memory_record({"id": "fb_1", "content": "Fallback testing", "category": "system"}),
    ]

    # Simulate pyarrow not installed
    def fake_build(recs):
        raise ImportError("pyarrow missing")

    monkeypatch.setattr(_mod, "build_pyarrow_table", fake_build)

    out = tmp_path / "fallback_run.parquet"
    count, size, is_fallback = write_parquet_file(records, out)
    assert count == 1
    assert size > 0
    assert is_fallback is True

    fb_file = tmp_path / "fallback_run.parquet.json"
    assert fb_file.exists()
    payload = json.loads(fb_file.read_text(encoding="utf-8"))
    assert payload["format"] == "columnar_parquet_fallback"
    assert payload["num_rows"] == 1
    assert payload["columns"]["id"] == ["fb_1"]


def test_cli_execution_with_file(tmp_path, capsys):
    input_file = tmp_path / "memories.json"
    output_file = tmp_path / "result.parquet"

    input_data = [
        {"id": "cli_1", "content": "CLI test memory item 1", "category": "work"},
        {"id": "cli_2", "content": "CLI test memory item 2", "category": "life"},
    ]
    input_file.write_text(json.dumps(input_data), encoding="utf-8")

    # Run with limit 1
    ret = main(["-i", str(input_file), "-o", str(output_file), "-n", "1"])
    assert ret == 0
    # Either binary parquet or fallback json exists
    assert output_file.exists() or Path(f"{output_file}.json").exists()


def test_cli_schema_flag(tmp_path, capsys):
    input_file = tmp_path / "memories.json"
    input_data = [{"id": "schema_1", "content": "Schema verification text"}]
    input_file.write_text(json.dumps(input_data), encoding="utf-8")

    ret = main(["-i", str(input_file), "--schema"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Apache Parquet Inferred Schema:" in captured.out
    assert "content" in captured.out


def test_cli_missing_input_file(tmp_path):
    missing_file = tmp_path / "non_existent.json"
    ret = main(["-i", str(missing_file)])
    assert ret == 1
