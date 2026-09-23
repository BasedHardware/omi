import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

# Load action_items_to_todoist dynamically using importlib.util
script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_todoist.py"
spec = importlib.util.spec_from_file_location("action_items_to_todoist", script_path)
ai2t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai2t)


class TestActionItemsToTodoist(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.source_file = Path(self.test_dir) / "action_items.json"
        self.sample_data = [
            {
                "id": "act_001",
                "description": "Send quarterly review report",
                "due_at": "2026-09-25T15:00:00Z",
                "completed": False
            },
            {
                "id": "act_002",
                "title": "Review hardware specs",
                "due_date": "tomorrow",
                "completed": False
            },
            {
                "id": "act_003",
                "description": "Team catchup meeting",
                "completed": False
            }
        ]
        self.source_file.write_text(json.dumps(self.sample_data), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_convert_generates_valid_todoist_tasks(self):
        dest = Path(self.test_dir) / "todoist_tasks.json"
        ai2t.convert(str(self.source_file), str(dest))

        self.assertTrue(dest.exists())
        tasks = json.loads(dest.read_text(encoding="utf-8"))

        self.assertEqual(len(tasks), 3)

        # Task 1: due_at check and labels
        self.assertEqual(tasks[0]["content"], "Send quarterly review report")
        self.assertEqual(tasks[0]["due_string"], "2026-09-25T15:00:00Z")
        self.assertIn("omi", tasks[0]["labels"])
        self.assertIn("ai-wearable", tasks[0]["labels"])
        self.assertIn("act_001", tasks[0]["description"])

        # Task 2: due_date fallback
        self.assertEqual(tasks[1]["content"], "Review hardware specs")
        self.assertEqual(tasks[1]["due_string"], "tomorrow")

        # Task 3: no due date
        self.assertNotIn("due_string", tasks[2])

    def test_destination_exists_raises(self):
        dest = Path(self.test_dir) / "existing.json"
        dest.write_text("{}", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            ai2t.convert(str(self.source_file), str(dest))

    def test_invalid_json_format_raises(self):
        invalid_file = Path(self.test_dir) / "invalid.json"
        invalid_file.write_text(json.dumps({"unexpected": "structure"}), encoding="utf-8")
        dest = Path(self.test_dir) / "out.json"
        with self.assertRaises(ValueError):
            ai2t.convert(str(invalid_file), str(dest))


if __name__ == "__main__":
    unittest.main()
