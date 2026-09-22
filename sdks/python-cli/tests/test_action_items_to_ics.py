import json
import pytest
from pathlib import Path
from examples.action_items_to_ics import convert

def test_action_items_to_ics(tmp_path):
    source = tmp_path / "tasks.json"
    dest = tmp_path / "tasks.ics"
    payload = [
        {"id": "t1", "description": "Call Alice; plan, review", "completed": False, "due_at": "2026-09-25T18:00:00Z"}
    ]
    source.write_text(json.dumps(payload), encoding="utf-8")
    convert(str(source), str(dest))
    assert dest.exists()
    content = dest.read_text(encoding="utf-8")
    assert "BEGIN:VCALENDAR" in content
    assert "BEGIN:VTODO" in content
    assert "SUMMARY:Call Alice\\; plan\\, review" in content
    assert "DUE:20260925T180000Z" in content
