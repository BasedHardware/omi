"""Hermetic tests for examples/conversations_to_parquet.py (#19056).

Covers: typed schema (string/float/int/timestamp/list-count), duration
computation, transcript/action-item counts, envelope unwrapping,
raw_json preservation, dedupe, atomic write. Requires pyarrow.
"""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

try:
    import pyarrow as pa
    import pyarrow.parquet as pq

    HAVE_PARQUET = True
except ImportError:
    HAVE_PARQUET = False

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "examples"))

if HAVE_PARQUET:
    import conversations_to_parquet as m  # noqa: E402


CONV = {
    "id": "c1",
    "title": "Planning session",
    "structured": {"title": "Planning session", "category": "Work", "overview": "Weekly plan"},
    "started_at": "2026-10-17T10:00:00+02:00",
    "finished_at": "2026-10-17T11:30:00Z",
    "source": "omi",
    "language": "en",
    "action_items": [{"description": "a"}, {"description": "b"}],
    "transcript_segments": [{"speaker": 0, "text": "hi"}, {"speaker": 1, "text": "yo"}],
}


@unittest.skipUnless(HAVE_PARQUET, "pyarrow not installed")
class TestConvert(unittest.TestCase):
    def test_typed_schema(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "c.json"
            src.write_text(json.dumps({"conversations": [CONV]}))
            out = str(Path(td) / "c.parquet")
            n = m.convert([str(src)], out)
            self.assertEqual(n, 1)
            table = pq.read_table(out)
            self.assertTrue(pa.types.is_timestamp(table.schema.field("started_at").type))
            self.assertTrue(pa.types.is_floating(table.schema.field("duration_minutes").type))
            self.assertTrue(pa.types.is_int64(table.schema.field("action_items_count").type))
            row = table.to_pylist()[0]
            self.assertEqual(row["id"], "c1")
            self.assertAlmostEqual(row["duration_minutes"], 210.0)  # 08:00Z→11:30Z = 3.5h
            self.assertEqual(row["action_items_count"], 2)
            self.assertEqual(row["transcript_segment_count"], 2)
            self.assertIn('"id": "c1"', row["raw_json"])

    def test_structured_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "c.json"
            src.write_text(json.dumps([{"id": "c2", "structured": {"title": "T", "category": "C"}}]))
            out = str(Path(td) / "c.parquet")
            m.convert([str(src)], out)
            row = pq.read_table(out).to_pylist()[0]
            self.assertEqual(row["title"], "T")
            self.assertEqual(row["category"], "C")

    def test_incomplete_no_duration(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "c.json"
            src.write_text(json.dumps([{"id": "c", "started_at": "2026-10-17T10:00:00Z"}]))
            out = str(Path(td) / "c.parquet")
            m.convert([str(src)], out)
            row = pq.read_table(out).to_pylist()[0]
            self.assertIsNone(row["duration_minutes"])

    def test_multi_page_dedupe(self):
        with tempfile.TemporaryDirectory() as td:
            p1 = Path(td) / "a.json"
            p1.write_text(json.dumps({"conversations": [CONV, {**CONV, "id": "c2"}]}))
            p2 = Path(td) / "b.json"
            p2.write_text(json.dumps({"conversations": [CONV]}))
            n = m.convert([str(p1), str(p2)], str(Path(td) / "o.parquet"))
            self.assertEqual(n, 2)

    def test_envelope_shapes(self):
        for payload in (
            {"conversations": [CONV]},
            {"items": [CONV]},
            {"data": [CONV]},
            {"results": [CONV]},
            [CONV],
            CONV,
        ):
            self.assertEqual(len(m.extract_conversations(payload)), 1)

    def test_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "c.json"
            src.write_text(json.dumps([CONV]))
            out = Path(td) / "o.parquet"
            out.write_text("keep")
            with self.assertRaises(FileExistsError):
                m.convert([str(src)], str(out))
            self.assertEqual(out.read_text(), "keep")

    def test_dotdot_refused(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "c.json"
            src.write_text(json.dumps([CONV]))
            with self.assertRaises(ValueError):
                m.convert([str(src)], "../escape.parquet")


if __name__ == "__main__":
    unittest.main()
