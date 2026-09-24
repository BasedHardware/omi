import unittest
import sys
from pathlib import Path

# Add examples dir to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from action_items_to_todoist import transform_to_todoist, extract_action_items


class TestActionItemsToTodoist(unittest.TestCase):
    def test_extract_items(self):
        raw = '{"action_items": [{"id": "t1", "description": "Update website"}]}'
        items = extract_action_items(raw)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "t1")

    def test_transform_to_todoist(self):
        items = [
            {
                "id": "act-1",
                "description": "Email accountant",
                "completed": False,
                "due_at": "2026-09-30T17:00:00Z",
                "conversation_id": "conv-101"
            },
            {
                "id": "act-2",
                "description": "Old task",
                "completed": True
            }
        ]
        # Only open tasks by default
        tasks = transform_to_todoist(items, label="omi-tasks", project_id="12345")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["content"], "Email accountant")
        self.assertEqual(tasks[0]["labels"], ["omi-tasks"])
        self.assertEqual(tasks[0]["project_id"], "12345")
        self.assertEqual(tasks[0]["due_date"], "2026-09-30")
        self.assertIn("conv-101", tasks[0]["description"])

        # Include completed
        all_tasks = transform_to_todoist(items, include_completed=True)
        self.assertEqual(len(all_tasks), 2)


if __name__ == "__main__":
    unittest.main()
