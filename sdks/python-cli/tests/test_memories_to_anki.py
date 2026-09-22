import json
import pytest
from pathlib import Path
from examples.memories_to_anki import convert

def test_memories_to_anki(tmp_path):
    source = tmp_path / "mems.json"
    dest = tmp_path / "cards.tsv"
    payload = [
        {"id": "m1", "content": "Line 1\nLine 2", "category": "reading", "created_at": "2026-09-20"}
    ]
    source.write_text(json.dumps(payload), encoding="utf-8")
    convert(str(source), str(dest))
    assert dest.exists()
    content = dest.read_text(encoding="utf-8")
    assert "#separator:tab" in content
    assert "Line 1<br>Line 2" in content
    assert "reading" in content
