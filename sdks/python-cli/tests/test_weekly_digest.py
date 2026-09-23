import json
import pytest
from pathlib import Path
from examples.conversations_to_weekly_digest import convert

def test_weekly_digest(tmp_path):
    source = tmp_path / "convs.json"
    dest = tmp_path / "digest.md"
    payload = [
        {"id": "c1", "started_at": "2026-09-21T10:00:00Z", "structured": {"title": "Strategy Sync", "overview": "Q4 plan", "action_items": [{"description": "Send deck", "completed": True}]}}
    ]
    source.write_text(json.dumps(payload), encoding="utf-8")
    convert(str(source), str(dest))
    assert dest.exists()
    content = dest.read_text(encoding="utf-8")
    assert "## 2026-09-21" in content
    assert "- [x] Send deck" in content
