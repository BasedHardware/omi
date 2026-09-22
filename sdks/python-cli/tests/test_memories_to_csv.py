import csv
import json
import pytest
from pathlib import Path
from examples.memories_to_csv import convert, FIELDS

def test_memories_to_csv(tmp_path):
    source = tmp_path / "memories.json"
    dest = tmp_path / "memories.csv"
    payload = [
        {"id": "m1", "content": "Test note", "category": "work", "visibility": "private", "tags": ["q4", "plan"], "created_at": "2026-09-20T10:00:00Z"},
        {"id": "m2", "content": "=1+2", "category": "finance", "visibility": "private", "tags": [], "created_at": "2026-09-21T10:00:00Z"}
    ]
    source.write_text(json.dumps(payload), encoding="utf-8")
    convert(str(source), str(dest))
    assert dest.exists()
    with open(dest, "r", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
        assert rows[0] == FIELDS
        assert rows[1][1] == "Test note"
        assert rows[2][1] == "'=1+2"
