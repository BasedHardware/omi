import json
import os
import tempfile
import pathlib
import subprocess
import sys

import pytest

# Import the conversion function directly for unit testing
from sdks.python_cli.examples.action_items_to_todoist import (
    convert_action_items_to_todoist,
)

def test_convert_action_items_basic():
    raw_items = [
        {"title": "Task 1", "description": "Desc 1", "due": "2024-10-01", "priority": 3},
        {"title": "Task 2", "due": "2024-10-02"},
        {"title": "Task 3", "priority": 5},  # out of range, should clamp to 4
    ]
    tasks = convert_action_items_to_todoist(raw_items)
    assert len(tasks) == 3
    assert tasks[0]["content"] == "Task 1"
    assert tasks[0]["description"] == "Desc 1"
    assert tasks[0]["due_string"] == "2024-10-01"
    assert tasks[0]["priority"] == 3

    assert tasks[1]["content"] == "Task 2"
    assert "description" not in tasks[1]
    assert tasks[1]["due_string"] == "2024-10-02"
    assert tasks[1]["priority"] == 1  # default

    assert tasks[2]["content"] == "Task 3"
    assert tasks[2]["priority"] == 4  # clamped

def test_convert_action_items_invalid():
    # Missing title
    raw_items = [{"description": "No title"}]
    with pytest.raises(ValueError):
        convert_action_items_to_todoist(raw_items)

def test_script_atomic_write(tmp_path):
    # Create a temporary input file
    input_file = tmp_path / "input.json"
    input_file.write_text(
        json.dumps(
            [
                {"title": "Script test", "priority": 2},
            ]
        )
    )

    # Run the script
    output_file = tmp_path / "output.json"
    result = subprocess.run(
        [sys.executable, "-m", "sdks.python_cli.examples.action_items_to_todoist", str(input_file), str(output_file)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert output_file.exists()
    tasks = json.loads(output_file.read_text())
    assert len(tasks) == 1
    assert tasks[0]["content"] == "Script test"
    assert tasks[0]["priority"] == 2
