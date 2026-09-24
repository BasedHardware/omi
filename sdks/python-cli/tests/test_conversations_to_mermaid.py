import unittest
import sys
from pathlib import Path

# Add examples dir to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from conversations_to_mermaid import generate_timeline, generate_sequence, clean_mermaid_text


class TestConversationsToMermaid(unittest.TestCase):
    def test_clean_mermaid_text(self):
        self.assertEqual(clean_mermaid_text('Hello: "World"\nTest'), "Hello -  'World' Test")

    def test_generate_timeline(self):
        convs = [
            {"id": "c1", "started_at": "2026-09-24T10:00:00Z", "structured": {"title": "Architecture Review"}},
            {"id": "c2", "started_at": "2026-09-24T14:00:00Z", "structured": {"title": "Team Sync"}},
            {"id": "c3", "started_at": "2026-09-25T09:00:00Z", "structured": {"title": "Client Onboarding"}}
        ]
        md = generate_timeline(convs, title="Weekly Timeline")
        self.assertIn("```mermaid", md)
        self.assertIn("timeline", md)
        self.assertIn("title Weekly Timeline", md)
        self.assertIn("2026-09-24 : Architecture Review : Team Sync", md)
        self.assertIn("2026-09-25 : Client Onboarding", md)

    def test_generate_sequence(self):
        conv = {
            "id": "c1",
            "structured": {"title": "Interview"},
            "transcript_segments": [
                {"speaker": "Interviewer", "text": "Tell me about your background."},
                {"speaker": "Candidate", "text": "I have worked in backend systems for 5 years."}
            ]
        }
        md = generate_sequence(conv)
        self.assertIn("```mermaid", md)
        self.assertIn("sequenceDiagram", md)
        self.assertIn("Interviewer->>Candidate: Tell me about your background.", md)
        self.assertIn("Candidate->>Interviewer: I have worked in backend systems for 5 years.", md)


if __name__ == "__main__":
    unittest.main()
