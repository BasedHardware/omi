import importlib.util
import json
from pathlib import Path
import pytest

# Robust dynamic loader for recipe module in examples/ or local directory
_recipe_candidates = [
    Path(__file__).resolve().parent.parent / "examples" / "action_items_to_parquet.py",
    Path(__file__).resolve().parent / "action_items_to_parquet.py",
]
_recipe_path = next((p for p in _recipe_candidates if p.exists()), None)
if _recipe_path is None:
    raise FileNotFoundError("Could not locate action_items_to_parquet.py in search paths")

_spec = importlib.util.spec_from_file_location("action_items_to_parquet", _recipe_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

normalize_iso_timestamp = _mod.normalize_iso_timestamp
generate_task_hash_id = _mod.generate_task_hash_id
normalize_action_item_record = _mod.normalize_action_item_record
parse_omi_action_items = _mod.parse_omi_action_items
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


def test_generate_task_hash_id():
    id1 = generate_task_hash_id("Review code", "2026-09-25T10:00:00Z")
    assert id1.startswith("task_")
    id2 = generate_task_hash_id("Review code", "2026-09-25T10:00:00Z")
    assert id1 == id2


def test_normalize_action_item_record():
    raw = {
        "id": "act_101",
        "description": "Follow up with client regarding API migration",
        "completed": True,
        "category": "Work",
        "priority": "High",
        "createdAt": "2026-09-25T09:00:00Z",
        "updatedAt": "2026-09-25T11:00:00Z",
        "dueAt": "2026-09-26T18:00:00Z",
        "completedAt": "2026-09-25T11:00:00Z",
        "conversation_id": "conv_555",
        "user_id": "usr_888",
        "deleted": False,
    }
    rec = normalize_action_item_record(raw)
    assert rec["id"] == "act_101"
    assert rec["description"] == "Follow up with client regarding API migration"
    assert rec["completed"] is True
    assert rec["category"] == "work"
    assert rec["priority"] == "high"
    assert rec["created_at"] == "2026-09-25T09:00:00Z"
    assert rec["updated_at"] == "2026-09-25T11:00:00Z"
    assert rec["due_at"] == "2026-09-26T18:00:00Z"
    assert rec["completed_at"] == "2026-09-25T11:00:00Z"
    assert rec["conversation_id"] == "conv_555"
    assert rec["user_id"] == "usr_888"
    assert rec["is_deleted"] is False
    assert rec["char_len"] == len("Follow up with client regarding API migration")
    assert rec["word_count"] == 7


def test_parse_omi_action_items():
    sample_list = [
        {"id": "t1", "description": "Task 1"},
        {"id": "t2", "description": "Task 2"},
    ]
    parsed = parse_omi_action_items(sample_list)
    assert len(parsed) == 2

    # Wrapped in dictionary with 'action_items'
    sample_dict = {"action_items": [{"id": "t1", "description": "Sample task"}]}
    assert len(parse_omi_action_items(sample_dict)) == 1

    # Empty payload
    assert parse_omi_action_items("[]") == []
    assert parse_omi_action_items("") == []


def test_records_to_columnar_dict():
    records = [
        normalize_action_item_record({"id": "t1", "description": "Task 1", "completed": False}),
        normalize_action_item_record({"id": "t2", "description": "Task 2", "completed": True}),
    ]
    cols = records_to_columnar_dict(records)
    assert len(cols["id"]) == 2
    assert cols["id"] == ["t1", "t2"]
    assert cols["completed"] == [False, True]
    assert len(cols["char_len"]) == 2


def test_pyarrow_table_and_parquet_roundtrip(tmp_path):
    pytest.importorskip("pyarrow")
    records = [
        normalize_action_item_record(
            {
                "id": f"task_{i}",
                "description": f"Productivity checklist item {i}",
                "completed": (i % 2 == 0),
                "priority": "normal",
                "created_at": "2026-09-25T10:00:00Z",
            }
        )
        for i in range(6)
    ]

    table = build_pyarrow_table(records)
    assert table.num_rows == 6
    assert len(table.schema.names) == 14

    out_file = tmp_path / "action_items.parquet"
    count, size, is_fallback = write_parquet_file(records, out_file, compression="snappy")
    assert count == 6
    assert size > 0
    assert is_fallback is False
    assert out_file.exists()

    info = inspect_parquet_file(out_file)
    assert info["num_rows"] == 6
    assert info["num_columns"] == 14
    assert "description" in info["columns"]
    assert "completed" in info["columns"]


def test_compression_codecs(tmp_path):
    pytest.importorskip("pyarrow")
    records = [
        normalize_action_item_record(
            {
                "id": f"task_{i}",
                "description": f"Repetitive task description text {i} " * 15,
                "category": "work",
            }
        )
        for i in range(6)
    ]

    for codec in ["snappy", "gzip", "none"]:
        out = tmp_path / f"tasks_{codec}.parquet"
        count, size, is_fallback = write_parquet_file(records, out, compression=codec)
        assert count == 6
        assert size > 0
        assert is_fallback is False
        info = inspect_parquet_file(out)
        assert info["num_rows"] == 6


def test_fallback_columnar_export(tmp_path, monkeypatch):
    records = [
        normalize_action_item_record({"id": "fb_task_1", "description": "Fallback task"}),
    ]

    # Simulate pyarrow not installed
    def fake_build(recs):
        raise ImportError("pyarrow missing")

    monkeypatch.setattr(_mod, "build_pyarrow_table", fake_build)

    out = tmp_path / "fallback_tasks.parquet"
    count, size, is_fallback = write_parquet_file(records, out)
    assert count == 1
    assert size > 0
    assert is_fallback is True

    fb_file = tmp_path / "fallback_tasks.parquet.json"
    assert fb_file.exists()
    payload = json.loads(fb_file.read_text(encoding="utf-8"))
    assert payload["format"] == "columnar_parquet_fallback"
    assert payload["num_rows"] == 1
    assert payload["columns"]["id"] == ["fb_task_1"]


def test_cli_execution_with_file(tmp_path, capsys):
    input_file = tmp_path / "tasks.json"
    output_file = tmp_path / "result.parquet"

    input_data = [
        {"id": "cli_t1", "description": "CLI action item 1", "category": "work"},
        {"id": "cli_t2", "description": "CLI action item 2", "category": "life"},
    ]
    input_file.write_text(json.dumps(input_data), encoding="utf-8")

    # Run with limit 1
    ret = main(["-i", str(input_file), "-o", str(output_file), "-n", "1"])
    assert ret == 0
    assert output_file.exists() or Path(f"{output_file}.json").exists()


def test_cli_schema_flag(tmp_path, capsys):
    input_file = tmp_path / "tasks.json"
    input_data = [{"id": "schema_t1", "description": "Schema verification task"}]
    input_file.write_text(json.dumps(input_data), encoding="utf-8")

    ret = main(["-i", str(input_file), "--schema"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Apache Parquet Inferred Schema for Action Items:" in captured.out
    assert "description" in captured.out


def test_cli_missing_input_file(tmp_path):
    missing_file = tmp_path / "non_existent.json"
    ret = main(["-i", str(missing_file)])
    assert ret == 1
