import json
import pytest
from pathlib import Path
from examples.memories_to_obsidian import convert

def test_memories_to_obsidian(tmp_path):
    source = tmp_path / "mems.json"
    dest = tmp_path / "obsidian.md"
    payload = [
        {"id": "m1", "content": "Paragraph 1\nParagraph 2", "category": "project", "created_at": "2026-09-20"}
    ]
    source.write_text(json.dumps(payload), encoding="utf-8")
    convert(str(source), str(dest))
    assert dest.exists()
    content = dest.read_text(encoding="utf-8")
    assert "> Paragraph 1" in content
    assert "> Paragraph 2" in content
    assert "[[Project]]" in content
