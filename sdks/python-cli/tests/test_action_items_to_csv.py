import csv
import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from action_items_to_csv import convert, spreadsheet_text, boolean_text, FIELDS


class TestActionItemsToCsv(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_spreadsheet_text_escaping(self):
        # Formula injection characters
        self.assertEqual(spreadsheet_text("=1+1"), "'=1+1")
        self.assertEqual(spreadsheet_text("+cmd"), "'+cmd")
        self.assertEqual(spreadsheet_text("-2+3"), "'-2+3")
        self.assertEqual(spreadsheet_text("@SUM(A1)"), "'@SUM(A1)")
        self.assertEqual(spreadsheet_text("  =secret"), "'  =secret")
        # Safe strings
        self.assertEqual(spreadsheet_text("Review PR #18479"), "Review PR #18479")
        self.assertEqual(spreadsheet_text(None), "")
        self.assertEqual(spreadsheet_text(123), "123")

    def test_boolean_text(self):
        self.assertEqual(boolean_text(True), "true")
        self.assertEqual(boolean_text(False), "false")
        self.assertEqual(boolean_text("true"), "true")
        self.assertEqual(boolean_text("1"), "true")
        self.assertEqual(boolean_text("false"), "false")
        self.assertEqual(boolean_text(None), "false")

    def test_convert_valid_json(self):
        sample_tasks = [
            {
                "id": "task_1",
                "description": "Send invoice to client",
                "completed": False,
                "due_at": "2026-09-25T12:00:00Z",
                "created_at": "2026-09-24T08:00:00Z",
                "updated_at": "2026-09-24T08:30:00Z",
                "conversation_id": "conv_100",
            },
            {
                "id": "task_2",
                "description": "=SUM(A1:B2) malicious formula task",
                "completed": True,
                "due_at": None,
                "created_at": "2026-09-24T09:00:00Z",
                "updated_at": "2026-09-24T09:00:00Z",
                "conversation_id": "conv_101",
            }
        ]
        source_json = self.dir_path / "tasks.json"
        dest_csv = self.dir_path / "tasks.csv"
        source_json.write_text(json.dumps(sample_tasks), encoding="utf-8")

        convert(str(source_json), str(dest_csv))
        self.assertTrue(dest_csv.exists())

        # Check UTF-8-sig BOM
        content_bytes = dest_csv.read_bytes()
        self.assertTrue(content_bytes.startswith(b"\xef\xbb\xbf"))

        # Parse CSV
        text_content = content_bytes.decode("utf-8-sig")
        reader = list(csv.reader(text_content.splitlines()))
        self.assertEqual(len(reader), 3)  # header + 2 rows
        self.assertEqual(reader[0], list(FIELDS))

        # Check row 1
        self.assertEqual(reader[1][0], "task_1")
        self.assertEqual(reader[1][1], "Send invoice to client")
        self.assertEqual(reader[1][2], "false")

        # Check row 2 formula escaped
        self.assertEqual(reader[2][0], "task_2")
        self.assertEqual(reader[2][1], "'=SUM(A1:B2) malicious formula task")
        self.assertEqual(reader[2][2], "true")

    def test_wrapped_dict_payload(self):
        wrapped = {
            "action_items": [
                {"id": "task_wrapped", "description": "Wrapped task", "completed": False}
            ]
        }
        source_json = self.dir_path / "wrapped.json"
        dest_csv = self.dir_path / "wrapped.csv"
        source_json.write_text(json.dumps(wrapped), encoding="utf-8")

        convert(str(source_json), str(dest_csv))
        text_content = dest_csv.read_bytes().decode("utf-8-sig")
        reader = list(csv.reader(text_content.splitlines()))
        self.assertEqual(len(reader), 2)
        self.assertEqual(reader[1][0], "task_wrapped")

    def test_refuse_overwrite(self):
        source_json = self.dir_path / "tasks.json"
        dest_csv = self.dir_path / "tasks.csv"
        source_json.write_text(json.dumps([{"id": "t1", "description": "d1"}]), encoding="utf-8")
        dest_csv.write_text("existing", encoding="utf-8")

        with self.assertRaises(FileExistsError):
            convert(str(source_json), str(dest_csv))

    def test_missing_id_raises(self):
        source_json = self.dir_path / "bad.json"
        dest_csv = self.dir_path / "bad.csv"
        source_json.write_text(json.dumps([{"description": "No ID"}]), encoding="utf-8")

        with self.assertRaises(ValueError):
            convert(str(source_json), str(dest_csv))


if __name__ == "__main__":
    unittest.main()
