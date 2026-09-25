import unittest
import sys
from pathlib import Path

# Add examples dir to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from memories_to_graphviz import generate_dot_graph, escape_dot, extract_memories


class TestMemoriesToGraphviz(unittest.TestCase):
    def test_escape_dot(self):
        self.assertEqual(escape_dot('hello "world"\nnext'), 'hello \\"world\\"\\nnext')

    def test_generate_dot_graph(self):
        mems = [
            {
                "id": "m1",
                "content": "Prefers typescript",
                "category": "preferences",
                "created_at": "2026-09-24T12:00:00Z"
            },
            {
                "id": "m2",
                "content": "Works on Omi project",
                "category": "work",
                "created_at": "2026-09-24T13:00:00Z"
            }
        ]
        dot = generate_dot_graph(mems, title="My Brain")
        self.assertIn('digraph "My Brain" {', dot)
        self.assertIn("subgraph cluster_preferences {", dot)
        self.assertIn("subgraph cluster_work {", dot)
        self.assertIn("node_m1 [label=", dot)
        self.assertIn("node_m2 [label=", dot)
        self.assertIn("(2026-09-24)", dot)


if __name__ == "__main__":
    unittest.main()
