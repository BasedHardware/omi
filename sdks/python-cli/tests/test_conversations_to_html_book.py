import unittest
import sys
from pathlib import Path

# Add examples dir to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from conversations_to_html_book import render_html_book, extract_conversations


class TestConversationsToHtmlBook(unittest.TestCase):
    def test_extract_conversations(self):
        raw = '{"conversations": [{"id": "c1", "title": "Test Chat"}]}'
        items = extract_conversations(raw)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "c1")

    def test_render_html_book(self):
        convs = [
            {
                "id": "c-001",
                "started_at": "2026-09-24T09:00:00Z",
                "structured": {
                    "title": "Quarterly Planning",
                    "overview": "Reviewed roadmap goals.",
                    "category": "work"
                },
                "transcript_segments": [
                    {"speaker": "Bob", "text": "Let us finalize the target deliverables."}
                ]
            }
        ]
        html_doc = render_html_book(convs, book_title="Engineering Notes")
        self.assertIn("<title>Engineering Notes</title>", html_doc)
        self.assertIn("Quarterly Planning", html_doc)
        self.assertIn("Reviewed roadmap goals.", html_doc)
        self.assertIn('<span class="badge">Bob</span>', html_doc)
        self.assertIn("Let us finalize the target deliverables.", html_doc)
        self.assertIn("@media print", html_doc)
        self.assertIn("filterNav()", html_doc)

    def test_anchor_sanitization_xss_prevention(self):
        malicious_id = 'c"><img src=x onerror=alert(3)>'
        convs = [
            {
                "id": malicious_id,
                "started_at": "2026-09-24T09:00:00Z",
                "structured": {
                    "title": "Security Review",
                }
            }
        ]
        html_doc = render_html_book(convs)
        # Ensure anchor is sanitized and does not contain raw quotes, angles, or script tags
        self.assertNotIn(malicious_id, html_doc)
        self.assertIn('href="#chapter_c_img_src_x_onerror_alert_3"', html_doc)
        self.assertIn('id="chapter_c_img_src_x_onerror_alert_3"', html_doc)

    def test_extract_conversations_invalid_json(self):
        with self.assertRaises(ValueError):
            extract_conversations("")
        with self.assertRaises(ValueError):
            extract_conversations("{invalid json")


if __name__ == "__main__":
    unittest.main()
