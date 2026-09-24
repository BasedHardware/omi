import unittest
import sys
from pathlib import Path

# Add examples dir to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from conversations_metrics import analyze_conversation_speakers, to_markdown_report


class TestConversationsMetrics(unittest.TestCase):
    def test_analyze_speakers(self):
        conv = {
            "id": "c1",
            "title": "Sprint Planning",
            "transcript_segments": [
                {"speaker": "Alice", "start": 0.0, "end": 10.0, "text": "Hello team let us begin"},
                {"speaker": "Bob", "start": 10.0, "end": 20.0, "text": "Sounds good I agree completely"},
                {"speaker": "Alice", "start": 20.0, "end": 30.0, "text": "Great moving to ticket two"}
            ]
        }
        res = analyze_conversation_speakers(conv)
        self.assertEqual(res["total_duration_sec"], 30.0)
        self.assertEqual(res["total_words"], 15)
        self.assertEqual(res["total_turns"], 3)
        self.assertIn("Alice", res["speakers"])
        self.assertIn("Bob", res["speakers"])
        # Alice spoke 20s out of 30s -> 66.7%
        self.assertAlmostEqual(res["speakers"]["Alice"]["talk_share_pct"], 66.7, places=1)
        # Bob spoke 10s out of 30s -> 33.3%
        self.assertAlmostEqual(res["speakers"]["Bob"]["talk_share_pct"], 33.3, places=1)

    def test_markdown_report_generation(self):
        data = [{
            "id": "c1",
            "title": "Standup",
            "total_duration_sec": 60.0,
            "total_words": 120,
            "total_turns": 2,
            "speakers": {
                "Alice": {
                    "talk_time_sec": 30.0,
                    "talk_share_pct": 50.0,
                    "words": 60,
                    "speech_rate_wpm": 120.0,
                    "turns": 1
                }
            }
        }]
        md = to_markdown_report(data)
        self.assertIn("# Omi Conversation Speaker & Speech Metrics", md)
        self.assertIn("Standup (`c1`)", md)
        self.assertIn("Alice", md)
        self.assertIn("120.0", md)


if __name__ == "__main__":
    unittest.main()
