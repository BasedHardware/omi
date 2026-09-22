import json
import pytest
from pathlib import Path
from examples.conversations_to_html import convert

def test_conversations_to_html(tmp_path):
    source = tmp_path / "convs.json"
    dest = tmp_path / "report.html"
    payload = [
        {"id": "c1", "started_at": "2026-09-20T10:00:00Z", "structured": {"title": "<script>alert(1)</script>", "overview": "Test & demo"}, "transcript_segments": [{"speaker": "Alice", "text": "Hi"}]},
        {"id": "c2", "started_at": "2026-09-21T10:00:00Z", "structured": None, "transcript_segments": []}
    ]
    source.write_text(json.dumps(payload), encoding="utf-8")
    convert(str(source), str(dest))
    assert dest.exists()
    content = dest.read_text(encoding="utf-8")
    assert "&lt;script&gt;" in content
    assert "<script>" not in content
    assert "Test &amp; demo" in content
