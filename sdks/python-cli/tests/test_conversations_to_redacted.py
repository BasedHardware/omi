import unittest
import sys
from pathlib import Path

# Add examples dir to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from conversations_to_redacted import redact_text, sanitize_conversation


class TestConversationsToRedacted(unittest.TestCase):
    def test_redact_email_and_phone(self):
        text = "Contact Alice at alice@example.com or call 415-555-0199 for updates."
        cleaned, stats = redact_text(text)
        self.assertNotIn("alice@example.com", cleaned)
        self.assertIn("[REDACTED_EMAIL]", cleaned)
        self.assertNotIn("415-555-0199", cleaned)
        self.assertIn("[REDACTED_PHONE]", cleaned)
        self.assertEqual(stats["emails"], 1)
        self.assertEqual(stats["phones"], 1)

    def test_redact_api_secrets_and_ips(self):
        text = "Server IP is 192.168.1.50 using token ghp_dummyTestingTokenStringForUnitTests12345."
        cleaned, stats = redact_text(text)
        self.assertNotIn("ghp_dummyTestingTokenStringForUnitTests12345", cleaned)
        self.assertIn("[REDACTED_SECRET]", cleaned)
        self.assertNotIn("192.168.1.50", cleaned)
        self.assertIn("[REDACTED_IP]", cleaned)
        self.assertEqual(stats["secrets"], 1)
        self.assertEqual(stats["ips"], 1)

    def test_sanitize_conversation_structure(self):
        conv = {
            "id": "conv-test",
            "structured": {
                "title": "Discussion with bob@domain.org",
                "overview": "Call Bob at 555-123-4567"
            },
            "transcript_segments": [
                {"text": "My card is 4111-2222-3333-4444 thanks."}
            ]
        }
        sanitized, stats = sanitize_conversation(conv)
        self.assertEqual(sanitized["structured"]["title"], "Discussion with [REDACTED_EMAIL]")
        self.assertEqual(sanitized["structured"]["overview"], "Call Bob at [REDACTED_PHONE]")
        self.assertEqual(sanitized["transcript_segments"][0]["text"], "My card is [REDACTED_CARD] thanks.")
        self.assertEqual(stats["emails"], 1)
        self.assertEqual(stats["phones"], 1)
        self.assertEqual(stats["cards"], 1)


if __name__ == "__main__":
    unittest.main()
