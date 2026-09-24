import csv
import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from goals_to_csv import convert, spreadsheet_text, boolean_text, compute_progress_pct, FIELDS


class TestGoalsToCsv(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_spreadsheet_text_escaping(self):
        self.assertEqual(spreadsheet_text("=cmd|'/C calc'!A0"), "'=cmd|'/C calc'!A0")
        self.assertEqual(spreadsheet_text("+123"), "'+123")
        self.assertEqual(spreadsheet_text("-discount"), "'-discount")
        self.assertEqual(spreadsheet_text("@lookup"), "'@lookup")
        self.assertEqual(spreadsheet_text("Safe Title"), "Safe Title")
        self.assertEqual(spreadsheet_text(None), "")
        self.assertEqual(spreadsheet_text(42), "42")

    def test_compute_progress_pct(self):
        self.assertEqual(compute_progress_pct(5, 10), "50.0")
        self.assertEqual(compute_progress_pct(10, 10), "100.0")
        self.assertEqual(compute_progress_pct(1, 3), "33.33")
        self.assertEqual(compute_progress_pct(0, 10), "0.0")
        self.assertEqual(compute_progress_pct(5, 0), "0.0")
        self.assertEqual(compute_progress_pct(None, 10), "0.0")

    def test_boolean_text(self):
        self.assertEqual(boolean_text(True), "true")
        self.assertEqual(boolean_text(False), "false")
        self.assertEqual(boolean_text("active"), "true")
        self.assertEqual(boolean_text("false"), "false")
        self.assertEqual(boolean_text(None), "true")  # default active

    def test_convert_valid_json(self):
        sample_goals = [
            {
                "id": "g_1",
                "title": "Meditate 10 mins",
                "goal_type": "wellness",
                "current_value": 7,
                "target_value": 10,
                "unit": "mins",
                "is_active": True,
                "created_at": "2026-09-20T08:00:00Z",
                "updated_at": "2026-09-24T08:00:00Z"
            },
            {
                "id": "g_2",
                "title": "+Run 10km",
                "goal_type": "fitness",
                "current_value": 10,
                "target_value": 10,
                "unit": "km",
                "is_active": False,
                "created_at": "2026-09-01T00:00:00Z",
                "updated_at": "2026-09-24T09:00:00Z"
            }
        ]
        source_json = self.dir_path / "goals.json"
        dest_csv = self.dir_path / "goals.csv"
        source_json.write_text(json.dumps(sample_goals), encoding="utf-8")

        convert(str(source_json), str(dest_csv))
        self.assertTrue(dest_csv.exists())

        # Assert BOM
        content_bytes = dest_csv.read_bytes()
        self.assertTrue(content_bytes.startswith(b"\xef\xbb\xbf"))

        # Parse CSV
        reader = list(csv.reader(content_bytes.decode("utf-8-sig").splitlines()))
        self.assertEqual(len(reader), 3)  # header + 2 rows
        self.assertEqual(reader[0], list(FIELDS))

        # Check row 1
        self.assertEqual(reader[1][0], "g_1")
        self.assertEqual(reader[1][1], "Meditate 10 mins")
        self.assertEqual(reader[1][5], "70.0")  # progress_pct
        self.assertEqual(reader[1][7], "true")  # is_active

        # Check row 2 formula escaped
        self.assertEqual(reader[2][0], "g_2")
        self.assertEqual(reader[2][1], "'+Run 10km")
        self.assertEqual(reader[2][5], "100.0")
        self.assertEqual(reader[2][7], "false")

    def test_wrapped_dict_payload(self):
        wrapped = {
            "goals": [
                {"id": "g_wrap", "title": "Wrapped Item", "current_value": 1, "target_value": 1}
            ]
        }
        source_json = self.dir_path / "wrapped.json"
        dest_csv = self.dir_path / "wrapped.csv"
        source_json.write_text(json.dumps(wrapped), encoding="utf-8")

        convert(str(source_json), str(dest_csv))
        reader = list(csv.reader(dest_csv.read_bytes().decode("utf-8-sig").splitlines()))
        self.assertEqual(len(reader), 2)
        self.assertEqual(reader[1][0], "g_wrap")

    def test_refuse_overwrite(self):
        source_json = self.dir_path / "goals.json"
        dest_csv = self.dir_path / "goals.csv"
        source_json.write_text(json.dumps([{"id": "g1", "title": "t1"}]), encoding="utf-8")
        dest_csv.write_text("existing", encoding="utf-8")

        with self.assertRaises(FileExistsError):
            convert(str(source_json), str(dest_csv))

    def test_missing_id_raises(self):
        source_json = self.dir_path / "bad.json"
        dest_csv = self.dir_path / "bad.csv"
        source_json.write_text(json.dumps([{"title": "No ID"}]), encoding="utf-8")

        with self.assertRaises(ValueError):
            convert(str(source_json), str(dest_csv))


if __name__ == "__main__":
    unittest.main()
