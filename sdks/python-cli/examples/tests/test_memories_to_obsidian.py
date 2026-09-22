import json
import os
import tempfile
import shutil
from pathlib import Path

import pytest

# Import the script functions
from sdks.python_cli.examples.memories_to_obsidian import (
    _load_memories,
    _memory_to_markdown,
    _write_atomic,
    _sanitize_filename,
)


@pytest.fixture
def sample_memories():
    return [
        {
            "title": "Test Memory",
            "content": "This is a test.",
            "tags": ["test", "memory"],
            "date": "2024-01-01T12:00:00",
        },
        {
            "title": "Another Memory",
            "content": "More content.",
            "tags": [],
            "date": None,
        },
    ]


def test_sanitize_filename():
    assert _sanitize_filename("Hello World") == "Hello_World"
    assert _sanitize_filename("Invalid/Name") == "Invalid_Name"


def test_memory_to_markdown(sample_memories):
    md = _memory_to_markdown(sample_memories[0])
    assert "---" in md
    assert "title: Test Memory" in md
    assert "date: 2024-01-01T12:00:00" in md
    assert 'tags: ["test", "memory"]' in md
    assert "This is a test." in md
    assert "[[test]] [[memory]]" in md


def test_write_atomic(tmp_path):
    target = tmp_path / "test.md"
    content = "Hello\n"
    _write_atomic(target, content, dry_run=False)
    assert target.read_text() == content

    # Ensure atomicity: temp file should not exist after write
    assert not (target.with_suffix(".tmp")).exists()


def test_load_memories(tmp_path, sample_memories):
    json_path = tmp_path / "memories.json"
    json_path.write_text(json.dumps(sample_memories))
    loaded = _load_memories(json_path)
    assert loaded == sample_memories
