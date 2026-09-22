import csv
import json
import pytest
from pathlib import Path
from examples.goals_to_csv import convert, FIELDS

def test_goals_to_csv(tmp_path):
    source = tmp_path / "goals.json"
    dest = tmp_path / "goals.csv"
    payload = [
        {"id": "g1", "title": "Run marathon", "description": "Finish under 4 hours", "category": "fitness", "target_value": 42.2, "current_value": 15.0, "metric": "km", "horizon_at": "2026-12-31T00:00:00Z", "created_at": "2026-09-20T10:00:00Z"}
    ]
    source.write_text(json.dumps(payload), encoding="utf-8")
    convert(str(source), str(dest))
    assert dest.exists()
    with open(dest, "r", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
        assert rows[0] == FIELDS
        assert rows[1][1] == "Run marathon"
        assert rows[1][7] == "2026-12-31T00:00:00Z"
