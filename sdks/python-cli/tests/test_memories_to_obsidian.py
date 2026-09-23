import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

# Load memories_to_obsidian dynamically using importlib.util
script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_obsidian.py"
spec = importlib.util.spec_from_file_location("memories_to_obsidian", script_path)
m2o = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2o)


class TestMemoriesToObsidian(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.source_file = Path(self.test_dir) / "memories.json"
        self.sample_data = [
            {
                "id": "mem_01",
                "content": "Line 1 of memory.\nLine 2 continuation.\nLine 3 conclusion.",
                "category": "personal",
                "created_at": "2026-09-22T10:00:00Z"
            }
        ]
        self.source_file.write_text(json.dumps(self.sample_data), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_multiline_blockquotes_preserved(self):
        dest = Path(self.test_dir) / "memories.md"
        m2o.convert(str(self.source_file), str(dest))

        self.assertTrue(dest.exists())
        content = dest.read_text(encoding="utf-8")

        self.assertIn("> Line 1 of memory.", content)
        self.assertIn("> Line 2 continuation.", content)
        self.assertIn("> Line 3 conclusion.", content)
        self.assertIn("> — [[Personal]] · *2026-09-22T10:00:00Z*", content)
        self.assertIn("[[Omi]]", content)


if __name__ == "__main__":
    unittest.main()
