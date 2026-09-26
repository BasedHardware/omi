"""Hermetic unit tests for examples/memories_to_jsonl.py.

All tests are stdlib-only (except pytest as test runner) and never touch
the network or filesystem except through tmp_path.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make examples/ importable regardless of working directory
sys.path.insert(0, str(Path(__file__).parent.parent / "examples"))
import memories_to_jsonl as m2j  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_MEMORIES = [
    {
        "id": "mem_001",
        "content": "I prefer morning workouts.",
        "category": "health",
        "created_at": "2025-01-10T08:00:00+00:00",
        "source": "voice_capture",
    },
    {
        "id": "mem_002",
        "content": "Favourite editor is Neovim.",
        "category": "skills",
        "created_at": 1736496000.0,
        "source": None,
    },
    {
        "id": "mem_003",
        "content": "Allergic to shellfish.",
        "category": "health",
        "created_at": None,
        "source": None,
    },
]


# 1. chat schema — required keys and roles
def test_chat_record_structure():
    rec = m2j.to_chat_record(SAMPLE_MEMORIES[0])
    assert rec is not None
    assert "messages" in rec
    roles = [msg["role"] for msg in rec["messages"]]
    assert roles == ["system", "user", "assistant"]


# 2. chat schema — assistant content equals memory content
def test_chat_record_assistant_content():
    memory = {"id": "x", "content": "I like jazz."}
    rec = m2j.to_chat_record(memory)
    assert rec is not None
    assistant_msg = rec["messages"][-1]
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["content"] == "I like jazz."


# 3. knowledge schema — all metadata fields present
def test_knowledge_record_fields():
    rec = m2j.to_knowledge_record(SAMPLE_MEMORIES[0])
    assert rec is not None
    for key in ("id", "content", "category", "created_at", "source"):
        assert key in rec, f"Missing key: {key}"
    assert rec["id"] == "mem_001"
    assert rec["category"] == "health"
    assert rec["created_at"] == "2025-01-10T08:00:00+00:00"


# 4. knowledge schema — Unix float timestamp normalised to ISO-8601 string
def test_knowledge_record_timestamp_normalisation():
    rec = m2j.to_knowledge_record(SAMPLE_MEMORIES[1])
    assert rec is not None
    ts = rec["created_at"]
    assert ts is not None
    assert isinstance(ts, str)
    assert "T" in ts


# 5. Empty-content records return None for both formatters
def test_empty_content_returns_none():
    empty = {"id": "bad", "content": "", "category": None}
    assert m2j.to_chat_record(empty) is None
    assert m2j.to_knowledge_record(empty) is None


# 6. Records with no content key return None for both formatters
def test_missing_content_key_returns_none():
    no_content = {"id": "bad2"}
    assert m2j.to_chat_record(no_content) is None
    assert m2j.to_knowledge_record(no_content) is None


# 7. Multi-file deduplication by id
def test_load_inputs_deduplication(tmp_path: Path):
    data = json.dumps(SAMPLE_MEMORIES)
    f1 = tmp_path / "a.json"
    f2 = tmp_path / "b.json"
    f1.write_text(data, encoding="utf-8")
    f2.write_text(data, encoding="utf-8")
    records = m2j.load_inputs([str(f1), str(f2)])
    ids = [r["id"] for r in records]
    assert len(ids) == len(set(ids)), "Duplicate ids found after deduplication"
    assert len(records) == len(SAMPLE_MEMORIES)


# 8. Atomic overwrite — .jsonl.tmp is cleaned up after successful write
def test_atomic_write_no_tmp_file_left(tmp_path: Path):
    output = tmp_path / "out.jsonl"
    m2j.write_jsonl(SAMPLE_MEMORIES, str(output), "knowledge")
    tmp = tmp_path / "out.jsonl.tmp"
    assert not tmp.exists(), ".jsonl.tmp should be cleaned up after write"
    assert output.exists()


# 9. write_jsonl produces valid JSONL — one parseable JSON object per line
def test_write_jsonl_valid_lines(tmp_path: Path):
    output = tmp_path / "test.jsonl"
    written = m2j.write_jsonl(SAMPLE_MEMORIES, str(output), "chat")
    lines = output.read_text(encoding="utf-8").strip().splitlines()
    assert written == len(lines)
    for line in lines:
        obj = json.loads(line)
        assert "messages" in obj


# 10. main() CLI — end-to-end with --output flag
def test_main_cli_end_to_end(tmp_path: Path):
    input_file = tmp_path / "input.json"
    output_file = tmp_path / "out.jsonl"
    input_file.write_text(json.dumps(SAMPLE_MEMORIES), encoding="utf-8")
    m2j.main([str(input_file), "-o", str(output_file), "--format", "knowledge"])
    lines = output_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == len(SAMPLE_MEMORIES)
    for line in lines:
        obj = json.loads(line)
        assert "content" in obj
