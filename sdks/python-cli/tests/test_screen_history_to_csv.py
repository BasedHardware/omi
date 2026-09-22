import csv
import json
import pytest
from pathlib import Path
from examples.screen_history_to_csv import convert, FIELDS

def test_screen_history_to_csv(tmp_path):
    source = tmp_path / "screen.json"
    dest = tmp_path / "screen.csv"
    payload = {
        "results": [
            {"screenshot_id": "sc_1", "timestamp": "2026-09-22 10:00:00", "app_name": "Safari", "window_title": "Pricing", "similarity": 0.88, "ocr_preview": "Pro plan $20/mo"}
        ]
    }
    source.write_text(json.dumps(payload), encoding="utf-8")
    convert(str(source), str(dest))
    assert dest.exists()
    with open(dest, "r", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
        assert rows[0] == FIELDS
        assert rows[1][0] == "sc_1"
        assert rows[1][2] == "Safari"
        assert rows[1][5] == "Pro plan $20/mo"
