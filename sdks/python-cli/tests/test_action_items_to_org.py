import json
import tempfile
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
from action_items_to_org import export, convert_to_org, items_from


class TestActionItemsToOrg(unittest.TestCase):
    def test_action_items_to_org_export(self):
        sample_data = [
            {
                "id": "task_1",
                "description": "Complete PR #17539",
                "completed": False,
                "due_at": "2026-09-25T14:30:00Z",
                "created_at": "2026-09-24T05:00:00Z",
                "conversation_id": "conv_99",
            },
            {
                "id": "task_2",
                "description": "Verify zero-defect quality gate",
                "completed": True,
                "due_at": None,
                "created_at": "2026-09-24T01:00:00Z",
                "completed_at": "2026-09-24T05:10:00Z",
                "conversation_id": None,
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            input_json = Path(tmpdir) / "items.json"
            output_org = Path(tmpdir) / "tasks.org"
            input_json.write_text(json.dumps(sample_data), encoding="utf-8")

            count = export(output_org, [input_json])
            self.assertEqual(count, 2)
            content = output_org.read_text(encoding="utf-8")

            self.assertIn("#+TITLE: Omi Action Items", content)
            self.assertIn("* TODO Complete PR #17539", content)
            self.assertIn("DEADLINE: <2026-09-25 Fri 14:30>", content)
            self.assertIn(":ID: task_1", content)
            self.assertIn(":CONVERSATION_ID: conv_99", content)

            self.assertIn("* DONE Verify zero-defect quality gate", content)
            self.assertIn("CLOSED: [2026-09-24 Thu 05:10]", content)
            self.assertIn(":ID: task_2", content)


if __name__ == "__main__":
    unittest.main()
