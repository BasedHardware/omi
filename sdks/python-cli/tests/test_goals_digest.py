"""Hermetic tests for examples/goals_digest.py (#19099).

Covers: multi-page loading, ID deduplication, KPI calculation, type
breakdown, status indicators, and overwrite refusal.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "examples"))

import goals_digest as m  # noqa: E402

ACTIVE = {
    "id": "g1",
    "title": "Drink water",
    "goal_type": "numeric",
    "current_value": 1.0,
    "target_value": 2.0,
    "unit": "liters",
    "is_active": True,
}
DONE = {
    "id": "g2",
    "title": "Read 12 books",
    "goal_type": "numeric",
    "current_value": 12,
    "target_value": 12,
    "is_active": True,
}
QUAL = {"id": "g3", "title": "Be kind", "goal_type": None, "is_active": False}


def _page(td, payload, name):
    p = Path(td) / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


class TestLoadDedupe(unittest.TestCase):
    def test_multi_page_id_dedup(self):
        with tempfile.TemporaryDirectory() as td:
            p1 = _page(td, {"goals": [ACTIVE, DONE]}, "a.json")
            p2 = _page(td, {"goals": [ACTIVE, QUAL]}, "b.json")  # ACTIVE repeats
            goals = m.load([p1, p2])
            self.assertEqual(len(goals), 3)
            self.assertEqual(len({g["id"] for g in goals}), 3)

    def test_envelope_shapes(self):
        for payload in ({"goals": [ACTIVE]}, {"items": [ACTIVE]}, {"data": [ACTIVE]}, [ACTIVE], ACTIVE):
            with tempfile.TemporaryDirectory() as td:
                self.assertEqual(len(m.load([_page(td, payload, "x.json")])), 1)


class TestKpis(unittest.TestCase):
    def test_kpi_calculation(self):
        k = m.kpis([ACTIVE, DONE, QUAL])
        self.assertEqual(k["total"], 3)
        self.assertEqual(k["active"], 2)
        self.assertEqual(k["inactive"], 1)
        self.assertEqual(k["achieved"], 1)  # DONE is 12/12
        self.assertAlmostEqual(k["avg_progress"], 75.0)  # (50% + 100%)/2

    def test_qualitative_excluded_from_avg(self):
        k = m.kpis([QUAL])
        self.assertIsNone(k["avg_progress"])

    def test_zero_target_no_divide(self):
        k = m.kpis([{"id": "g", "current_value": 1, "target_value": 0}])
        self.assertIsNone(k["avg_progress"])


class TestBreakdownStatus(unittest.TestCase):
    def test_type_breakdown(self):
        rows = m.type_breakdown([ACTIVE, DONE, QUAL])
        by = {r[0]: r for r in rows}
        self.assertEqual(by["numeric"][1], 2)
        self.assertEqual(by["qualitative"][1], 1)
        self.assertEqual(by["numeric"][2], "75%")

    def test_status_indicators(self):
        self.assertEqual(m.status(DONE), "✅")
        self.assertEqual(m.status(ACTIVE), "🟢")
        self.assertEqual(m.status(QUAL), "⏸")


class TestConvert(unittest.TestCase):
    def test_writes_digest(self):
        with tempfile.TemporaryDirectory() as td:
            src = _page(td, {"goals": [ACTIVE, DONE, QUAL]}, "g.json")
            dst = str(Path(td) / "d.md")
            m.convert([src], dst)
            text = Path(dst).read_text()
            self.assertIn("# Goals digest", text)
            self.assertIn("**Total goals:** 3", text)
            self.assertIn("| numeric | 2 | 75% |", text)
            self.assertIn("✅ **Read 12 books** — 12/12", text)

    def test_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            src = _page(td, [ACTIVE], "g.json")
            dst = Path(td) / "d.md"
            dst.write_text("keep")
            with self.assertRaises(FileExistsError):
                m.convert([src], str(dst))
            self.assertEqual(dst.read_text(), "keep")

    def test_dotdot_refused(self):
        with tempfile.TemporaryDirectory() as td:
            src = _page(td, [ACTIVE], "g.json")
            with self.assertRaises(ValueError):
                m.convert([src], "../escape.md")


if __name__ == "__main__":
    unittest.main()
