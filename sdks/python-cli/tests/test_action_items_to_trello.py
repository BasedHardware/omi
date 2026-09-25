import unittest
import sys
from pathlib import Path

# Add examples dir to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from action_items_to_trello import transform_to_trello_board, extract_action_items


class TestActionItemsToTrello(unittest.TestCase):
    def test_extract_items(self):
        raw = '{"action_items": [{"id": "a1", "description": "Review PR"}, {"id": "a2", "description": "Deploy to prod"}]}'
        items = extract_action_items(raw)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["id"], "a1")

    def test_transform_to_trello_board(self):
        items = [
            {
                "id": "act-1",
                "description": "Buy groceries",
                "completed": False,
                "due_at": "2026-09-25T18:00:00Z",
                "conversation_id": "conv-99"
            },
            {
                "id": "act-2",
                "description": "Send invoice",
                "status": "completed",
                "notes": "Paid via Stripe"
            }
        ]
        board = transform_to_trello_board(items, board_name="My Tasks")
        self.assertEqual(board["name"], "My Tasks")
        self.assertEqual(len(board["lists"]), 2)
        self.assertEqual(len(board["cards"]), 2)

        card1 = board["cards"][0]
        self.assertEqual(card1["name"], "Buy groceries")
        self.assertEqual(card1["idList"], "list_todo_001")
        self.assertFalse(card1["dueComplete"])
        self.assertEqual(card1["due"], "2026-09-25T18:00:00Z")
        self.assertIn("conv-99", card1["desc"])

        card2 = board["cards"][1]
        self.assertEqual(card2["name"], "Send invoice")
        self.assertEqual(card2["idList"], "list_done_002")
        self.assertTrue(card2["dueComplete"])


if __name__ == "__main__":
    unittest.main()
