import unittest
import sys
from pathlib import Path

# Add examples dir to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from memories_to_chroma import transform_to_chroma, extract_memories


class TestMemoriesToChroma(unittest.TestCase):
    def test_extract_memories(self):
        raw = '{"memories": [{"id": "m1", "content": "Likes matcha"}, {"id": "m2", "content": "Works remotely"}]}'
        mems = extract_memories(raw)
        self.assertEqual(len(mems), 2)
        self.assertEqual(mems[0]["id"], "m1")

    def test_transform_to_chroma(self):
        mems = [
            {
                "id": "mem-101",
                "content": "User prefers dark mode in code editors",
                "category": "preferences",
                "created_at": "2026-09-24T10:00:00Z",
                "manually_added": True
            }
        ]
        payload = transform_to_chroma(mems, collection_name="user_memory")
        self.assertEqual(payload["collection"], "user_memory")
        self.assertEqual(payload["ids"], ["mem-101"])
        self.assertEqual(payload["documents"], ["User prefers dark mode in code editors"])
        self.assertEqual(payload["metadatas"][0]["category"], "preferences")
        self.assertTrue(payload["metadatas"][0]["manually_added"])

    def test_empty_or_malformed_ignored(self):
        mems = [
            {"id": "m-empty", "content": ""},
            {"id": "", "content": "No ID"},
            {"id": "valid", "content": "Valid note"}
        ]
        raw = '{"data": [{"id": "m-empty", "content": ""}, {"id": "", "content": "No ID"}, {"id": "valid", "content": "Valid note"}]}'
        extracted = extract_memories(raw)
        payload = transform_to_chroma(extracted)
        self.assertEqual(len(payload["ids"]), 1)
        self.assertEqual(payload["ids"][0], "valid")


if __name__ == "__main__":
    unittest.main()
