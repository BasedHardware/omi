"""Hermetic tests for examples/memories_to_parquet.py (#19035).

Covers: typed Parquet schema (string/bool/list/timestamp), timestamp
normalization to UTC, list-of-string tags, envelope unwrapping, dedupe,
atomic write + refusal. Requires pyarrow.
"""

import json
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

if HAVE_PARQUET:
    import importlib.util

    _spec = importlib.util.spec_from_file_location(
        "memories_to_parquet", HERE.parents[1] / "examples" / "memories_to_parquet.py"
    )
    m = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(m)


MEM = {
    "id": "m1",
    "content": "Prefers short standups",
    "category": "Work",
    "tags": ["style", "meetings"],
    "visibility": "public",
    "manually_added": True,
    "reviewed": False,
    "app_id": "chatgpt",
    "created_at": "2026-10-17T12:00:00+02:00",
    "updated_at": "2026-10-17T13:00:00Z",
}


@unittest.skipUnless(HAVE_PARQUET, "pyarrow not installed")
class TestTypes(unittest.TestCase):
    def test_timestamp_to_utc(self):
        dt = m.to_ts("2026-10-17T12:00:00+02:00")
        self.assertEqual(dt, datetime(2026, 10, 17, 10, 0, 0, tzinfo=timezone.utc))
        self.assertIsNone(m.to_ts("bad"))
        self.assertIsNone(m.to_ts(None))

    def test_bool_coercion(self):
        self.assertIs(m.to_bool(True), True)
        self.assertIs(m.to_bool("yes"), True)
        self.assertIsNone(m.to_bool("maybe"))
        self.assertIsNone(m.to_bool(None))

    def test_tags_to_list(self):
        self.assertEqual(m.to_tags(["a", "b"]), ["a", "b"])
        self.assertEqual(m.to_tags("solo"), ["solo"])
        self.assertIsNone(m.to_tags(None))


@unittest.skipUnless(HAVE_PARQUET, "pyarrow not installed")
class TestConvert(unittest.TestCase):
    def test_typed_schema(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "m.json"
            src.write_text(json.dumps({"memories": [MEM]}))
            out = str(Path(td) / "m.parquet")
            n = m.convert([str(src)], out)
            self.assertEqual(n, 1)
            table = pq.read_table(out)
            self.assertEqual(table.num_rows, 1)
            schema_names = [f.name for f in table.schema]
            self.assertIn("tags", schema_names)
            self.assertTrue(pa.types.is_list(table.schema.field("tags").type))
            self.assertTrue(pa.types.is_timestamp(table.schema.field("created_at").type))
            self.assertTrue(pa.types.is_boolean(table.schema.field("manually_added").type))
            row = table.to_pylist()[0]
            self.assertEqual(row["id"], "m1")
            self.assertEqual(row["tags"], ["style", "meetings"])
            self.assertIs(row["manually_added"], True)
            self.assertEqual(row["created_at"].hour, 10)

    def test_multi_page_dedupe(self):
        with tempfile.TemporaryDirectory() as td:
            p1 = Path(td) / "a.json"
            p1.write_text(json.dumps({"memories": [MEM, {**MEM, "id": "m2"}]}))
            p2 = Path(td) / "b.json"
            p2.write_text(json.dumps({"memories": [MEM]}))
            n = m.convert([str(p1), str(p2)], str(Path(td) / "o.parquet"))
            self.assertEqual(n, 2)

    def test_envelope_shapes(self):
        for payload in ({"memories": [MEM]}, {"items": [MEM]}, {"data": [MEM]}, [MEM], MEM):
            self.assertEqual(len(m.extract_memories(payload)), 1)

    def test_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "m.json"
            src.write_text(json.dumps([MEM]))
            out = Path(td) / "o.parquet"
            out.write_text("keep")
            with self.assertRaises(FileExistsError):
                m.convert([str(src)], str(out))
            self.assertEqual(out.read_text(), "keep")

    def test_dotdot_refused(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "m.json"
            src.write_text(json.dumps([MEM]))
            with self.assertRaises(ValueError):
                m.convert([str(src)], "../escape.parquet")


if __name__ == "__main__":
    unittest.main()
