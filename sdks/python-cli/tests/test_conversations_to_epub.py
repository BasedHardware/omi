import unittest
import sys
import tempfile
import zipfile
from pathlib import Path

# Add examples dir to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from conversations_to_epub import build_epub, build_chapter_html, extract_conversations


class TestConversationsToEpub(unittest.TestCase):
    def test_build_chapter_html(self):
        conv = {
            "id": "c1",
            "title": "Strategy Session",
            "overview": "Discussed Q4 product launch goals.",
            "transcript_segments": [
                {"speaker": "Alice", "text": "Are we ready for launch?"},
                {"speaker": "Bob", "text": "Yes everything is tested."}
            ]
        }
        html_code = build_chapter_html(conv, 1)
        self.assertIn("Strategy Session", html_code)
        self.assertIn("Discussed Q4 product launch goals.", html_code)
        self.assertIn("Alice:", html_code)
        self.assertIn("Are we ready for launch?", html_code)

    def test_build_epub_archive(self):
        convs = [
            {
                "id": "c1",
                "title": "Meeting 1",
                "overview": "Overview 1",
                "transcript": "Hello world"
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            epub_path = Path(tmpdir) / "test.epub"
            build_epub(convs, epub_path, title="Test Ebook")
            self.assertTrue(epub_path.exists())

            # Verify EPUB internal files
            with zipfile.ZipFile(epub_path, "r") as zf:
                names = zf.namelist()
                self.assertIn("mimetype", names)
                self.assertEqual(zf.read("mimetype"), b"application/epub+zip")
                self.assertIn("META-INF/container.xml", names)
                self.assertIn("OEBPS/content.opf", names)
                self.assertIn("OEBPS/toc.ncx", names)
                self.assertIn("OEBPS/chapter_1.xhtml", names)


if __name__ == "__main__":
    unittest.main()
