import json
import pytest
from pathlib import Path
from examples.action_items_to_todoist import convert

def test_action_items_to_todoist(tmp_path):
    source = tmp_path / "tasks.json"
    dest = tmp_path / "todoist.json"
    payload = [
        {"id": "act_101", "description": "Review quarterly deck", "due_at": "2026-09-25T18:00:00Z"}
    ]
    source.write_text(json.dumps(payload), encoding="utf-8")
    convert(str(source), str(dest))
    assert dest.exists()
    tasks = json.loads(dest.read_text(encoding="utf-8"))
    assert tasks[0]["content"] == "Review quarterly deck"
    assert tasks[0]["due_string"] == "2026-09-25T18:00:00Z"
    assert "act_101" in tasks[0]["description"]
