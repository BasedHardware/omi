import csv
import json
import pytest
from pathlib import Path
from examples.tasks_to_csv import convert, FIELDS

def test_tasks_to_csv(tmp_path):
    source = tmp_path / "tasks.json"
    dest = tmp_path / "tasks.csv"
    payload = [
        {"id": "t1", "description": "Submit report", "completed": False, "created_at": "2026-09-20T10:00:00Z", "updated_at": "2026-09-20T10:05:00Z", "due_at": "2026-09-25T18:00:00Z", "completed_at": None, "conversation_id": "c99"}
    ]
    source.write_text(json.dumps(payload), encoding="utf-8")
    convert(str(source), str(dest))
    assert dest.exists()
    with open(dest, "r", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
        assert rows[0] == FIELDS
        assert rows[1][1] == "Submit report"
        assert rows[1][2] == "false"
        assert rows[1][5] == "2026-09-25T18:00:00Z"
