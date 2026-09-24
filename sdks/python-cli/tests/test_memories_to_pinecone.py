import unittest
import sys
from pathlib import Path

# Add examples dir to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from memories_to_pinecone import transform_to_pinecone, extract_memories


class TestMemoriesToPinecone(unittest.TestCase):
    def test_extract_memories(self):
        raw = '{"memories": [{"id": "m1", "content": "Knowledge item 1"}]}'
        items = extract_memories(raw)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "m1")

    def test_transform_to_pinecone(self):
        mems = [
            {
                "id": "mem-55",
                "content": "User lives in Seattle and loves hiking",
                "category": "lifestyle",
                "created_at": "2026-09-24T15:00:00Z",
                "manually_added": True
            }
        ]
        payload = transform_to_pinecone(mems, namespace="user-facts")
        self.assertEqual(payload["namespace"], "user-facts")
        self.assertEqual(len(payload["vectors"]), 1)

        vec = payload["vectors"][0]
        self.assertEqual(vec["id"], "mem-55")
        self.assertEqual(vec["metadata"]["text"], "User lives in Seattle and loves hiking")
        self.assertEqual(vec["metadata"]["category"], "lifestyle")
        self.assertTrue(vec["metadata"]["manually_added"])


if __name__ == "__main__":
    unittest.main()
