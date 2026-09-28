import csv
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent))
import action_items_to_asana as a2a


class TestActionItemsToAsana(unittest.TestCase):

    def setUp(self):
        self.sample_items = [
            {
                "id": "act-001",
                "description": "Prepare quarterly financial slides",
                "completed": False,
                "due_at": "2026-10-01T17:00:00Z",
                "priority": "High",
                "category": "finance",
                "conversation_id": "conv-101",
                "created_at": "2026-09-28T10:00:00Z"
            },
            {
                "id": "act-002",
                "description": "Send follow-up email to partner",
                "completed": True,
                "due_at": "2026-09-28T12:00:00Z",
                "priority": "Low",
                "category": "operations"
            }
        ]

    def test_asana_csv_generation(self):
        with TemporaryDirectory() as tmpdir:
            input_file = Path(tmpdir) / "action_items.json"
            input_file.write_text(json.dumps(self.sample_items), encoding="utf-8")
            output_file = Path(tmpdir) / "asana.csv"

            ret = a2a.main([str(input_file), "-o", str(output_file)])
            self.assertEqual(ret, 0)
            self.assertTrue(output_file.exists())

            # Read back CSV
            content = output_file.read_bytes().decode("utf-8-sig")
            reader = list(csv.DictReader(content.splitlines()))
            self.assertEqual(len(reader), 2)

            # Check Headers
            expected_headers = {"Name", "Description", "Due Date", "Section/Column", "Priority", "Completed", "Tags"}
            self.assertEqual(set(reader[0].keys()), expected_headers)

            # Check task 1 (Open)
            task1 = next(r for r in reader if "slides" in r["Name"])
            self.assertEqual(task1["Completed"], "FALSE")
            self.assertEqual(task1["Section/Column"], "To Do")
            self.assertEqual(task1["Priority"], "High")
            self.assertEqual(task1["Due Date"], "2026-10-01")
            self.assertIn("omi", task1["Tags"])
            self.assertIn("finance", task1["Tags"])

            # Check task 2 (Completed)
            task2 = next(r for r in reader if "partner" in r["Name"])
            self.assertEqual(task2["Completed"], "TRUE")
            self.assertEqual(task2["Section/Column"], "Done")
            self.assertEqual(task2["Priority"], "Low")

    def test_deduplication(self):
        with TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "f1.json"
            f2 = Path(tmpdir) / "f2.json"
            f1.write_text(json.dumps([self.sample_items[0]]), encoding="utf-8")
            f2.write_text(json.dumps(self.sample_items), encoding="utf-8")

            output_file = Path(tmpdir) / "asana.csv"
            ret = a2a.main([str(f1), str(f2), "-o", str(output_file)])
            self.assertEqual(ret, 0)

            content = output_file.read_bytes().decode("utf-8-sig")
            reader = list(csv.DictReader(content.splitlines()))
            self.assertEqual(len(reader), 2)

    def test_status_filter(self):
        with TemporaryDirectory() as tmpdir:
            input_file = Path(tmpdir) / "action_items.json"
            input_file.write_text(json.dumps(self.sample_items), encoding="utf-8")
            output_file = Path(tmpdir) / "asana_open.csv"

            ret = a2a.main([str(input_file), "-o", str(output_file), "--filter-status", "open"])
            self.assertEqual(ret, 0)

            content = output_file.read_bytes().decode("utf-8-sig")
            reader = list(csv.DictReader(content.splitlines()))
            self.assertEqual(len(reader), 1)
            self.assertEqual(reader[0]["Completed"], "FALSE")

    def test_tz_offset(self):
        with TemporaryDirectory() as tmpdir:
            input_file = Path(tmpdir) / "action_items.json"
            input_file.write_text(json.dumps(self.sample_items), encoding="utf-8")
            output_file = Path(tmpdir) / "asana_tz.csv"

            ret = a2a.main([str(input_file), "-o", str(output_file), "--tz-offset", "+09:00"])
            self.assertEqual(ret, 0)
            self.assertTrue(output_file.exists())

    def test_path_traversal(self):
        ret = a2a.main(["dummy.json", "-o", "../malicious.csv"])
        self.assertEqual(ret, 2)


if __name__ == "__main__":
    unittest.main()
