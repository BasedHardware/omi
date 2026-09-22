import json
import os
import pathlib
import subprocess
import sys
import tempfile
import csv

import pytest

# Import the function directly for unit testing
from sdks.python_cli.examples.screen_history_to_csv import (
    convert_screen_history_to_csv,
)

@pytest.fixture
def sample_json(tmp_path):
    data = [
        {
            "timestamp": "2024-09-22T12:34:56Z",
            "screen_text": "Hello world",
            "ocr_text": "Hello world",
        },
        {
            "timestamp": "2024-09-22T12:35:10Z",
            "screen_text": "Another line",
            "ocr_text": "Another line",
        },
    ]
    path = tmp_path / "input.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path

def test_convert_screen_history_to_csv(sample_json):
    out_path = pathlib.Path(tempfile.mktemp(suffix=".csv"))
    convert_screen_history_to_csv(sample_json, out_path)

    # Verify CSV content
    with out_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 2
    assert rows[0]["timestamp"] == "2024-09-22T12:34:56Z"
    assert rows[0]["screen_text"] == "Hello world"
    assert rows[0]["ocr_text"] == "Hello world"

    # Clean up
    out_path.unlink()

def test_cli_invocation(sample_json, tmp_path):
    out_path = tmp_path / "output.csv"
    cmd = [
        sys.executable,
        "-m",
        "sdks.python_cli.examples.screen_history_to_csv",
        str(sample_json),
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    assert out_path.is_file()

    with out_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 2
    assert rows[1]["ocr_text"] == "Another line"
