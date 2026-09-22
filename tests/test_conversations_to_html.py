import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path("sdks/python-cli/examples/conversations_to_html.py")
INPUT_JSON = Path("tests/_fixtures/convo.json")
OUTPUT_HTML = Path("tests/_fixtures/report.html")


@pytest.fixture(autouse=True)
def clean_output():
    if OUTPUT_HTML.exists():
        OUTPUT_HTML.unlink()
    yield
    if OUTPUT_HTML.exists():
        OUTPUT_HTML.unlink()


def test_render_conversation(tmp_path: Path):
    # Prepare a simple conversation JSON
    convo = [
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi! How can I help?"},
    ]
    INPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    INPUT_JSON.write_text(json.dumps(convo), encoding="utf-8")

    # Run the script
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--input",
        str(INPUT_JSON),
        "--output",
        str(OUTPUT_HTML),
        "--title",
        "Test Report",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)

    # Verify output file exists
    assert OUTPUT_HTML.exists(), "Output HTML file was not created"

    # Basic sanity check on content
    html = OUTPUT_HTML.read_text(encoding="utf-8")
    assert "<title>Test Report</title>" in html
    assert "Hello!" in html
    assert "Hi! How can I help?" in html
    assert "User:" in html or "User:" in html  # role rendering
