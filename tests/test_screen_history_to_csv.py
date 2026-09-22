import json
import pathlib
import subprocess
import sys
import tempfile
import os

import pytest

SCRIPT_PATH = pathlib.Path(__file__).parent.parent / "sdks" / "python-cli" / "examples" / "screen_history_to_csv.py"


def run_script(input_path: pathlib.Path, output_path: pathlib.Path | None = None) -> str:
    cmd = [sys.executable, str(SCRIPT_PATH), str(input_path)]
    if output_path:
        cmd.extend(["--output", str(output_path)])
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return result


@pytest.fixture
def sample_json(tmp_path: pathlib.Path) -> pathlib.Path:
    data = [
        {"timestamp": "2023-01-01T00:00:00Z", "text": "Hello"},
        {"timestamp": "2023-01-01T00:01:00Z", "text": "World", "extra": "value"},
    ]
    json_path = tmp_path / "screen_history.json"
    json_path.write_text(json.dumps(data), encoding="utf-8")
    return json_path


def test_convert_to_csv(sample_json, tmp_path):
    output_csv = tmp_path / "output.csv"
    result = run_script(sample_json, output_csv)
    assert result.returncode == 0, f"Script failed: {result.stderr}"
    assert output_csv.exists()

    # Verify CSV content
    csv_text = output_csv.read_text(encoding="utf-8")
    expected_lines = [
        "timestamp,text,extra",
        "2023-01-01T00:00:00Z,Hello,",
        "2023-01-01T00:01:00Z,World,value",
    ]
    assert csv_text.strip().splitlines() == expected_lines


def test_atomic_write(sample_json, tmp_path):
    """
    Ensure that the script writes the CSV atomically by checking that the
    temporary file does not persist after a successful run.
    """
    output_csv = tmp_path / "atomic.csv"
    temp_file = output_csv.with_suffix(".tmp")
    # Ensure temp file does not exist before
    if temp_file.exists():
        temp_file.unlink()

    result = run_script(sample_json, output_csv)
    assert result.returncode == 0
    assert not temp_file.exists(), "Temporary file should have been removed after atomic replace"
    assert output_csv.exists()
