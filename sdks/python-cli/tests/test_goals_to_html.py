"""Offline checks for the standalone goal dashboard recipe."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).parents[1] / "examples" / "goals_to_html.py"
spec = importlib.util.spec_from_file_location("goals_to_html", SCRIPT)
assert spec and spec.loader
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


SAMPLE = {
    "id": "goal_sample", "title": "Read 10 books", "desired_outcome": "Read 10 books",
    "status": "background", "is_active": True,
    "metric": {"type": "scale", "current": 3.0, "target": 10.0, "unit": "books"},
    "goal_type": "scale", "current_value": 3.0, "target_value": 10.0,
}


def test_empty_and_sample() -> None:
    empty = exporter.render([], "file", datetime(2026, 9, 26, tzinfo=timezone.utc))
    assert "No exported goals" in empty
    assert "0%</strong>" in empty
    rendered = exporter.render([SAMPLE], "file")
    assert "3 / 10 books" in rendered
    assert "30% progress" in rendered
    assert 'style="width:30.0%"' in rendered
    assert "Offline snapshot" in rendered


def test_states_kpis_and_qualitative() -> None:
    goals = [SAMPLE, {"title": "Done", "status": "achieved", "is_active": False},
             {"title": "Stopped", "status": "abandoned", "is_active": False},
             {"title": "Pause", "status": "paused", "is_active": True}]
    rendered = exporter.render(goals, "file")
    assert "4</strong><span>Exported goals" in rendered
    assert "2</strong><span>Active goals" in rendered
    assert "1</strong><span>Completed goals" in rendered
    assert "25%</strong><span>Completion rate" in rendered
    assert "Qualitative goal" in rendered
    assert rendered.count('role="progressbar"') == 1


@pytest.mark.parametrize(("metric", "expected", "meter"), [
    ({"type": "boolean", "current": 1, "target": 1}, "100% progress", True),
    ({"type": "boolean", "current": 2, "target": 1}, "Boolean values must be 0 or 1", False),
    ({"type": "numeric", "current": 15, "target": 10}, "150% progress", True),
    ({"type": "scale", "current": -2, "target": 10}, "-20% progress", True),
    ({"type": "numeric", "current": 1, "target": 0}, "Target must be positive", False),
    ({"type": "scale", "current": 2, "target": None}, "Progress unavailable", False),
    ({"type": "scale", "current": float("inf"), "target": 10}, "Progress unavailable", False),
    ({"type": "scale", "current": 1e308, "target": 1e-308}, "Percentage exceeds supported range", False),
    ({"type": "numeric", "current": 10**400, "target": 10}, "Progress unavailable", False),
])
def test_metric_cases(metric, expected, meter) -> None:
    rendered = exporter.render([{"title": "Measure", "metric": metric}], "file")
    assert expected in rendered
    assert ('role="progressbar"' in rendered) is meter
    if "150%" in expected:
        assert 'style="width:100.0%"' in rendered


def test_untrusted_unicode_and_markup() -> None:
    goal = {"title": 'هدف & "books" </script><script>alert(1)</script>', "status": "background",
            "desired_outcome": "قراءة <img src=x onerror=alert(1)>"}
    rendered = exporter.render([goal], "file")
    assert 'dir="auto"' in rendered
    assert "هدف" in rendered
    assert "&amp; &quot;books&quot;" in rendered
    assert "&lt;/script&gt;" in rendered
    assert "<img src=x" not in rendered
    assert rendered.count("<script>") == 1


def test_expandable_card_only_shows_present_details() -> None:
    goal = {"title": "Learn Arabic", "status": "focused", "is_active": True,
            "desired_outcome": "Read a story", "success_criteria": ["Finish chapter <one>", ""],
            "horizon_at": "2026-12-01T00:00:00Z"}
    rendered = exporter.render([goal], "file")
    assert '<details class="goal-disclosure"><summary>' in rendered
    assert '<span class="goal-title" dir="auto">Learn Arabic</span>' in rendered
    assert "<a href=" not in rendered
    assert "Finish chapter &lt;one&gt;" in rendered
    assert "2026-12-01T00:00:00Z" in rendered
    assert "Why it matters:" not in rendered
    assert "Source:" not in rendered
    assert "Finish chapter &lt;one&gt;" in rendered.split('data-search="', 1)[1]
    assert "beforeprint" in rendered and "afterprint" in rendered
    assert ".goal-disclosure:not([open])>.goal-details{display:block!important}" in rendered


@pytest.mark.parametrize("payload", [{}, [None], [{"title": ""}], [{"title": "x", "metric": []}],
                                     [{"title": "x", "status": []}], [{"title": "x", "is_active": "yes"}]])
def test_bad_structure(payload) -> None:
    with pytest.raises(exporter.ExportError):
        exporter.parse_goals(payload)


def test_file_bom_stdin_and_atomic_output(tmp_path, monkeypatch, capsys) -> None:
    source = tmp_path / "goals.json"
    output = tmp_path / "dashboard.html"
    source.write_text(json.dumps([SAMPLE]), encoding="utf-8-sig")
    assert exporter.main(["--input", str(source), "--output", str(output)]) == 0
    assert "30% progress" in output.read_text(encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(read=lambda: "\ufeff" + json.dumps([SAMPLE])))
    assert exporter.main(["--input", "-", "--output", str(output)]) == 0
    previous = output.read_bytes()
    source.write_text("not json", encoding="utf-8")
    assert exporter.main(["--input", str(source), "--output", str(output)]) == 1
    assert output.read_bytes() == previous
    assert "not valid JSON" in capsys.readouterr().err


def test_cli_success_failure_missing_timeout(monkeypatch) -> None:
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps([SAMPLE]), stderr="")

    monkeypatch.setattr(exporter.subprocess, "run", run)
    assert exporter.retrieve_goals("omi-test", "work") == [SAMPLE]
    assert calls[0] == ["omi-test", "--json", "--profile", "work", "goal", "list", "--include-inactive", "--limit", "100"]
    monkeypatch.setattr(exporter.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=2, stdout="", stderr="secret"))
    with pytest.raises(exporter.ExportError, match="exit 2") as failure:
        exporter.retrieve_goals("omi", None)
    assert "secret" not in str(failure.value)
    monkeypatch.setattr(exporter.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    with pytest.raises(exporter.ExportError, match="not found"):
        exporter.retrieve_goals("omi", None)
    monkeypatch.setattr(exporter.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("omi", 45)))
    with pytest.raises(exporter.ExportError, match="timed out"):
        exporter.retrieve_goals("omi", None)


def test_write_failure_and_demo(tmp_path) -> None:
    assert exporter.main(["--demo", "--output", str(tmp_path / "demo.html")]) == 0
    assert "Read 10 books" in (tmp_path / "demo.html").read_text(encoding="utf-8")
    assert exporter.main(["--demo", "--output", str(tmp_path / "missing" / "x.html")]) == 1
