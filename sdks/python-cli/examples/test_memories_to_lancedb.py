import json
import math
from pathlib import Path
import pytest

from memories_to_lancedb import (
    generate_deterministic_vector,
    extract_text_content,
    normalize_iso_timestamp,
    normalize_memory_record,
    parse_omi_memories,
    export_to_lancedb_payload,
    write_lancedb_jsonl,
    write_direct_lancedb,
    main,
)


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

    # ISO string
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
    raw = {
        "id": "mem_456",
        "content": "Existing vector test",
        "vector": [0.1, 0.2, 0.3, 0.4],
    }
    norm = normalize_memory_record(raw)
    assert norm["vector"] == [0.1, 0.2, 0.3, 0.4]


def test_parse_omi_memories():
    # Envelope
    env = {"memories": [{"id": "1", "content": "one"}, {"id": "2", "content": "two"}]}
    assert len(parse_omi_memories(env)) == 2

    # Direct list
    direct = [{"id": "3", "content": "three"}]
    assert len(parse_omi_memories(direct)) == 1


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
    in_json = tmp_path / "input.json"
    in_json.write_text(
        json.dumps(
            [{"id": "cli_1", "content": "Test CLI execution", "category": "ideas"}]
        ),
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
