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
        "createdAt": "2026-09-25T09:00:00Z",
        "updatedAt": "2026-09-25T11:00:00Z",
        "dueAt": "2026-09-26T18:00:00Z",
        "completedAt": "2026-09-25T11:00:00Z",
        "conversation_id": "conv_555",
    }
    rec = normalize_action_item_record(raw)
    assert rec["id"] == "act_101"
    assert rec["description"] == "Follow up with client regarding API migration"
    assert rec["completed"] is True
    assert rec["created_at"] == "2026-09-25T09:00:00Z"
    assert rec["updated_at"] == "2026-09-25T11:00:00Z"
    assert rec["due_at"] == "2026-09-26T18:00:00Z"
    assert rec["completed_at"] == "2026-09-25T11:00:00Z"
    assert rec["conversation_id"] == "conv_555"
    assert rec["char_len"] == len("Follow up with client regarding API migration")
    assert rec["word_count"] == 7


def test_real_cli_action_item_shape():
    """Verify that a real-shaped payload directly emitted by `omi --json action-item list` maps cleanly."""
    real_cli_record = {
        "id": "c1f2b456-9a01-4de2-bc34-56789abcdef0",
        "description": "Prepare latency benchmarking suite for edge inference",
        "completed": False,
        "created_at": "2026-09-25T14:22:10.123456Z",
        "updated_at": "2026-09-25T14:22:10.123456Z",
        "due_at": "2026-09-28T12:00:00Z",
        "completed_at": None,
        "conversation_id": "8f3e2b10-6745-4abc-9012-3456789abcde",
    }
    rec = normalize_action_item_record(real_cli_record)
    assert rec["id"] == "c1f2b456-9a01-4de2-bc34-56789abcdef0"
    assert rec["description"] == "Prepare latency benchmarking suite for edge inference"
    assert rec["completed"] is False
    assert rec["created_at"] == "2026-09-25T14:22:10Z"
    assert rec["updated_at"] == "2026-09-25T14:22:10Z"
    assert rec["due_at"] == "2026-09-28T12:00:00Z"
    assert rec["completed_at"] is None
    assert rec["conversation_id"] == "8f3e2b10-6745-4abc-9012-3456789abcde"
    assert rec["char_len"] == len(real_cli_record["description"])
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
        {
            "id": "1",
            "description": "Desc 1",
            "completed": False,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": None,
            "due_at": None,
            "completed_at": None,
            "conversation_id": None,
            "char_len": 6,
            "word_count": 2,
        },
        {
            "id": "2",
            "description": "Desc 2",
            "completed": True,
            "created_at": "2026-01-02T00:00:00Z",
            "updated_at": "2026-01-02T05:00:00Z",
            "due_at": "2026-01-03T00:00:00Z",
            "completed_at": "2026-01-02T05:00:00Z",
            "conversation_id": "conv_99",
            "char_len": 6,
            "word_count": 2,
        },
    ]
    cols = records_to_columnar_dict(records)
    assert cols["id"] == ["1", "2"]
    assert cols["completed"] == [False, True]
    assert cols["conversation_id"] == [None, "conv_99"]


def test_pyarrow_table_and_parquet_roundtrip(tmp_path):
    pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq

    records = [
        normalize_action_item_record(
            {
                "id": f"task_{i}",
                "description": f"Test task item {i}",
                "completed": (i % 2 == 0),
                "created_at": "2026-09-25T12:00:00Z",
                "due_at": "2026-09-30T12:00:00Z",
                "conversation_id": f"conv_{i}",
            }
        )
        for i in range(10)
    ]

    table = build_pyarrow_table(records)
    assert table.num_rows == 10
    assert table.num_columns == 10

    out_file = tmp_path / "test_tasks.parquet"
    num_rec, size, is_fallback = write_parquet_file(records, out_file, compression="snappy")
    assert num_rec == 10
    assert size > 0
    assert is_fallback is False
    assert out_file.exists()

    # Read back and inspect
    info = inspect_parquet_file(out_file)
    assert info["num_rows"] == 10
    assert info["num_columns"] == 10
    assert "description" in info["columns"]
    assert "due_at" in info["columns"]

    # Read through pyarrow
    read_table = pq.read_table(str(out_file))
    assert read_table.num_rows == 10


def test_compression_codecs(tmp_path):
    pytest.importorskip("pyarrow")
    records = [normalize_action_item_record({"id": f"t_{i}", "description": f"Payload {i}" * 20}) for i in range(25)]

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

    records = [normalize_action_item_record({"id": "t1", "description": "Fallback task"})]
    out_file = tmp_path / "fallback.parquet"
    num, size, is_fallback = write_parquet_file(records, out_file)
    assert num == 1
    assert is_fallback is True

    json_fallback = tmp_path / "fallback.parquet.json"
    assert json_fallback.exists()
    payload = json.loads(json_fallback.read_text(encoding="utf-8"))
    assert payload["format"] == "columnar_parquet_fallback"
    assert payload["num_rows"] == 1
    assert payload["columns"]["id"] == ["t1"]


def test_cli_execution_with_file(tmp_path):
    sample_file = tmp_path / "tasks.json"
    data = [
        {"id": "a1", "description": "Do A", "completed": True},
        {"id": "a2", "description": "Do B", "completed": False},
    ]
    sample_file.write_text(json.dumps(data), encoding="utf-8")
    out_parquet = tmp_path / "out.parquet"

    exit_code = main(["-i", str(sample_file), "-o", str(out_parquet), "--limit", "1"])
    assert exit_code == 0
    assert out_parquet.exists() or (tmp_path / "out.parquet.json").exists()


def test_cli_schema_flag(capsys):
    raw_json = '[{"id": "task_99", "description": "Schema check", "completed": false}]'
    exit_code = main(["--json", raw_json, "--schema"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Apache Parquet Inferred Schema" in captured.out
    assert "description" in captured.out
    assert "(string)" in captured.out
    assert "(bool)" in captured.out
    assert "Total records: 1" in captured.out


def test_cli_missing_input_file(tmp_path, capsys):
    exit_code = main(["-i", str(tmp_path / "non_existent.json")])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Error: input file" in captured.err
