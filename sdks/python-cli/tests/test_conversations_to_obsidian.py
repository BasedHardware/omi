import unittest
import sys
import tempfile
from pathlib import Path

# Add examples dir to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from conversations_to_obsidian import render_obsidian_note, export_obsidian_vault, slugify


class TestConversationsToObsidian(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(slugify("Weekly Sync & Architecture!"), "weekly-sync-architecture")

    def test_render_obsidian_note(self):
        conv = {
            "id": "c1",
            "started_at": "2026-09-24T10:00:00Z",
            "structured": {
                "title": "Design Discussion",
                "overview": "Reviewed responsive UI components.",
                "category": "work"
            },
            "transcript_segments": [
                {"speaker": "Alice", "text": "Let us check the colors."},
                {"speaker": "Bob", "text": "Looks great."}
            ]
        }
        fname, content, meta = render_obsidian_note(conv)
        self.assertTrue(fname.startswith("2026-09-24"))
        self.assertIn("---", content)
        self.assertIn('title: "Design Discussion"', content)
        self.assertIn("> [!summary] Overview", content)
        self.assertIn("**Alice**: Let us check the colors.", content)
        self.assertEqual(meta["month_folder"], "2026-09")

    def test_export_obsidian_vault(self):
        convs = [
            {
                "id": "c100",
                "started_at": "2026-09-24T10:00:00Z",
                "title": "Meeting A",
                "overview": "Some notes"
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "Vault"
            export_obsidian_vault(convs, out_dir)
            self.assertTrue((out_dir / "Conversations_Index.md").exists())
            self.assertTrue((out_dir / "Conversations" / "2026-09").exists())


if __name__ == "__main__":
    unittest.main()
