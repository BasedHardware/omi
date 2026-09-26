import importlib.util
import json
import math
from pathlib import Path
import pytest

# Robust dynamic loader for recipe module in examples/ or local directory
_recipe_candidates = [
    Path(__file__).resolve().parent.parent / "examples" / "memories_to_lancedb.py",
    Path(__file__).resolve().parent / "memories_to_lancedb.py",
]
_recipe_path = next((p for p in _recipe_candidates if p.exists()), None)
if _recipe_path is None:
    raise FileNotFoundError("Could not locate memories_to_lancedb.py in search paths")

_spec = importlib.util.spec_from_file_location("memories_to_lancedb", _recipe_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

generate_deterministic_vector = _mod.generate_deterministic_vector
extract_text_content = _mod.extract_text_content
normalize_iso_timestamp = _mod.normalize_iso_timestamp
normalize_memory_record = _mod.normalize_memory_record
parse_omi_memories = _mod.parse_omi_memories
export_to_lancedb_payload = _mod.export_to_lancedb_payload
write_lancedb_jsonl = _mod.write_lancedb_jsonl
write_direct_lancedb = _mod.write_direct_lancedb
main = _mod.main


def test_generate_deterministic_vector():
    vec384 = generate_deterministic_vector("Remember to submit report", dim=384)
    assert len(vec384) == 384
    norm = math.sqrt(sum(x * x for x in vec384))
    assert math.isclose(norm, 1.0, rel_tol=1e-3)

    # Determinism
    vec384_again = generate_deterministic_vector("Remember to submit report", dim=384)
    assert vec384 == vec384_again

    # Different text yields different vector
    vec_other = generate_deterministic_vector("Going to grocery store", dim=384)
    assert vec384 != vec_other


def test_normalize_iso_timestamp():
    # Millisecond epoch
    ts_ms = 1716998400000
    res_ms = normalize_iso_timestamp(ts_ms)
    assert "2024" in res_ms

    # Second epoch
    ts_sec = 1716998400
    res_sec = normalize_iso_timestamp(ts_sec)
    assert "2024" in res_sec

    # ISO string with Z
    iso_str = "2026-03-25T14:30:00Z"
    assert "2026-03-25" in normalize_iso_timestamp(iso_str)


def test_normalize_memory_record():
    raw = {
        "id": "mem_123",
        "content": "Meeting with client at 3 PM",
        "category": "work",
        "created_at": "2026-05-10T10:00:00Z",
        "tags": ["client", "urgent"],
        "user_id": "usr_99",
    }
    norm = normalize_memory_record(raw, vector_dim=128)
    assert norm["id"] == "mem_123"
    assert norm["content"] == "Meeting with client at 3 PM"
    assert norm["category"] == "work"
    assert len(norm["vector"]) == 128
    meta = json.loads(norm["metadata"])
    assert meta["user_id"] == "usr_99"
    assert meta["tags"] == ["client", "urgent"]


def test_normalize_memory_record_preserves_existing_vector():
    raw_vec = {
        "id": "mem_456",
        "content": "Existing vector test",
        "vector": [0.1, 0.2, 0.3, 0.4],
    }
    norm_vec = normalize_memory_record(raw_vec)
    assert norm_vec["vector"] == [0.1, 0.2, 0.3, 0.4]

    raw_emb = {
        "id": "mem_789",
        "content": "Existing embedding test",
        "embedding": [0.5, 0.6, 0.7, 0.8],
    }
    norm_emb = normalize_memory_record(raw_emb)
    assert norm_emb["vector"] == [0.5, 0.6, 0.7, 0.8]


def test_parse_omi_memories():
    # Envelope with memories
    env = {"memories": [{"id": "1", "content": "one"}, {"id": "2", "content": "two"}]}
    assert len(parse_omi_memories(env)) == 2

    # Envelope with items
    items_env = {"items": [{"id": "10", "content": "item"}]}
    assert len(parse_omi_memories(items_env)) == 1

    # Direct list
    direct = [{"id": "3", "content": "three"}]
    assert len(parse_omi_memories(direct)) == 1

    # Single dict
    single = {"id": "4", "content": "four"}
    assert len(parse_omi_memories(single)) == 1


def test_export_to_lancedb_payload_deduplication():
    records = [
        {"id": "dup_1", "content": "first"},
        {"id": "dup_1", "content": "duplicate"},
        {"id": "dup_2", "content": "second"},
    ]
    # With deduplication
    deduped = export_to_lancedb_payload(records, deduplicate=True)
    assert len(deduped) == 2
    assert deduped[0]["id"] == "dup_1"
    assert deduped[1]["id"] == "dup_2"

    # Without deduplication
    all_recs = export_to_lancedb_payload(records, deduplicate=False)
    assert len(all_recs) == 3


def test_write_lancedb_jsonl(tmp_path: Path):
    target = tmp_path / "memories.jsonl"
    recs = [{"id": "1", "content": "test", "vector": [0.5, 0.5]}]
    write_lancedb_jsonl(recs, target)
    assert target.exists()
    lines = target.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    loaded = json.loads(lines[0])
    assert loaded["id"] == "1"

    # Overwrite check
    with pytest.raises(FileExistsError):
        write_lancedb_jsonl(recs, target, overwrite=False)
    write_lancedb_jsonl(recs, target, overwrite=True)


def test_cli_execution_with_json_and_jsonl(tmp_path: Path, capsys):
    # Test JSON input
    in_json = tmp_path / "input.json"
    in_json.write_text(
        json.dumps([{"id": "cli_1", "content": "Test CLI execution", "category": "ideas"}]),
        encoding="utf-8",
    )
    out_jsonl = tmp_path / "out.jsonl"

    ret = main(["-i", str(in_json), "-o", str(out_jsonl), "--dim", "64", "--pretty"])
    assert ret == 0
    assert out_jsonl.exists()
    captured = capsys.readouterr()
    res = json.loads(captured.out)
    assert res["status"] == "success"
    assert res["records_exported"] == 1
    assert res["vector_dim"] == 64
    assert res["fallback"] is False

    # Test JSONL input
    in_jsonl = tmp_path / "input_stream.jsonl"
    in_jsonl.write_text(
        '{"id": "cli_2", "content": "Second memory"}\n{"id": "cli_3", "content": "Third memory"}\n',
        encoding="utf-8",
    )
    out_stream = tmp_path / "out_stream.jsonl"
    ret2 = main(["-i", str(in_jsonl), "-o", str(out_stream), "--dim", "64"])
    assert ret2 == 0
    assert out_stream.exists()
    lines = out_stream.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_direct_mode_fallback_signaled(tmp_path: Path, monkeypatch, capsys):
    in_json = tmp_path / "input_direct.json"
    in_json.write_text(
        json.dumps([{"id": "dir_1", "content": "Direct test"}]),
        encoding="utf-8",
    )
    out_dir = tmp_path / "lancedb_store"

    # In environment without lancedb or mocked failure
    monkeypatch.setattr(_mod, "write_direct_lancedb", lambda *args, **kwargs: False)

    ret = main(["-i", str(in_json), "-o", str(out_dir), "-m", "direct"])
    assert ret == 0
    captured = capsys.readouterr()
    res = json.loads(captured.out)
    assert res["status"] == "success"
    assert res["fallback"] is True
    assert "jsonl" in res["output"]
