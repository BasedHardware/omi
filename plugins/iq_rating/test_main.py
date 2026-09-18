import json
import unittest
from unittest.mock import MagicMock, patch

from plugins.iq_rating import main


class IQRatingCalculateAITests(unittest.TestCase):
    def setUp(self):
        self.sample_people = {
            "alice": {
                "name": "Alice",
                "context_snippets": ["Alice is a brilliant engineer and visionary leader."],
            },
            "bob": {
                "name": "Bob",
                "context_snippets": ["Bob helped with some questions."],
            },
        }

    @patch.object(main, "OPENAI_API_KEY", "test-key")
    @patch("requests.post")
    def test_valid_ai_response_assigns_scores(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            [
                                {"name": "Alice", "iq": 145, "is_name": True},
                                {"name": "Bob", "iq": 115, "is_name": True},
                            ]
                        )
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        scores = main.calculate_iq_with_ai(self.sample_people)

        self.assertEqual(scores["alice"]["iq"], 145)
        self.assertTrue(scores["alice"]["is_name"])
        self.assertEqual(scores["bob"]["iq"], 115)
        self.assertTrue(scores["bob"]["is_name"])

    @patch.object(main, "OPENAI_API_KEY", "test-key")
    @patch("requests.post")
    def test_leading_non_object_element_keeps_valid_scores(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            [
                                1,
                                None,
                                "invalid_entry",
                                {"name": "Alice", "iq": 140, "is_name": True},
                                {"name": "Bob", "iq": 110, "is_name": True},
                            ]
                        )
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        scores = main.calculate_iq_with_ai(self.sample_people)

        self.assertEqual(scores["alice"]["iq"], 140)
        self.assertEqual(scores["bob"]["iq"], 110)

    @patch.object(main, "OPENAI_API_KEY", "test-key")
    @patch("requests.post")
    def test_null_and_non_integer_iq_values_fallback_without_dropping_batch(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            [
                                {"name": "Alice", "iq": None, "is_name": True},
                                {"name": "Bob", "iq": "invalid_number", "is_name": "yes"},
                            ]
                        )
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        scores = main.calculate_iq_with_ai(self.sample_people)

        self.assertEqual(scores["alice"]["iq"], 100)
        self.assertTrue(scores["alice"]["is_name"])
        self.assertEqual(scores["bob"]["iq"], 100)
        self.assertTrue(scores["bob"]["is_name"])

    @patch.object(main, "OPENAI_API_KEY", "test-key")
    @patch("requests.post")
    def test_invalid_name_entries_skipped_safely(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            [
                                {"name": None, "iq": 130},
                                {"name": "   ", "iq": 125},
                                {"name": 12345, "iq": 120},
                                {"name": "Alice", "iq": 135, "is_name": True},
                            ]
                        )
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        scores = main.calculate_iq_with_ai(self.sample_people)

        self.assertEqual(scores["alice"]["iq"], 135)
        # Bob was not in AI response, so filled via random fallback
        self.assertIn("bob", scores)
        self.assertIsInstance(scores["bob"]["iq"], int)

    @patch.object(main, "OPENAI_API_KEY", "test-key")
    @patch("requests.post")
    def test_non_list_json_response_handled_gracefully(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": json.dumps({"error": "not a list"})}}]}
        mock_post.return_value = mock_response

        scores = main.calculate_iq_with_ai(self.sample_people)

        self.assertIn("alice", scores)
        self.assertIn("bob", scores)

    @patch.object(main, "OPENAI_API_KEY", "")
    def test_no_api_key_uses_random_fallback(self):
        scores = main.calculate_iq_with_ai(self.sample_people)
        self.assertIn("alice", scores)
        self.assertIn("bob", scores)
        self.assertTrue(
            70 <= scores["alice"] <= 160 or (isinstance(scores["alice"], dict) and 70 <= scores["alice"]["iq"] <= 160)
        )


if __name__ == "__main__":
    unittest.main()
