import unittest
from unittest.mock import patch, MagicMock
import os
import json

# Ensure dummy credentials so startup/module-level checks pass
os.environ.setdefault("OMI_APP_ID", "test_app_id")
os.environ.setdefault("OMI_APP_SECRET", "test_app_secret")
os.environ.setdefault("OPENAI_API_KEY", "test_openai_key")

from main import filter_names_with_openai, calculate_iq_with_ai


class TestIQRatingRegression(unittest.TestCase):
    """
    Hermetic regression tests for #13980:
    - Unguarded OpenAI choices indexing
    - content: null attribute error defense
    - Malformed 200 payload handling
    - context_snippets list/tuple coercion and None filtering
    """

    @patch("requests.post")
    def test_filter_names_with_openai_null_content(self, mock_post):
        # Case 1: OpenAI returns 200 with content: null
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None
                    }
                }
            ]
        }
        mock_post.return_value = mock_resp

        names = ["Alice", "Bob"]
        # Must not raise AttributeError: 'NoneType' object has no attribute 'strip'
        result = filter_names_with_openai(names)
        self.assertIsInstance(result, list)

    @patch("requests.post")
    def test_filter_names_with_openai_empty_choices(self, mock_post):
        # Case 2: OpenAI returns 200 with empty choices list
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": []}
        mock_post.return_value = mock_resp

        names = ["Alice", "Bob"]
        result = filter_names_with_openai(names)
        self.assertIsInstance(result, list)

    @patch("requests.post")
    def test_filter_names_with_openai_non_dict_payload(self, mock_post):
        # Case 3: Malformed payload (not a dict)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = ["malformed", "list"]
        mock_post.return_value = mock_resp

        names = ["Alice", "Bob"]
        result = filter_names_with_openai(names)
        self.assertIsInstance(result, list)

    @patch("requests.post")
    def test_calculate_iq_with_ai_null_content_and_choices_guard(self, mock_post):
        # Case 4: calculate_iq_with_ai with content: null
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None
                    }
                }
            ]
        }
        mock_post.return_value = mock_resp

        people_dict = {
            "alice": {
                "name": "Alice",
                "context_snippets": ["brilliant engineer", "great problem solver"],
                "mention_count": 12
            }
        }

        # Must not crash, should fall back cleanly
        res = calculate_iq_with_ai(people_dict)
        self.assertIn("alice", res)
        self.assertIn("iq_score", res["alice"])

    def test_calculate_iq_with_ai_context_snippets_coercion(self):
        # Case 5: context_snippets with tuple, non-list, None items, numbers
        people_dict = {
            "bob": {
                "name": "Bob",
                "context_snippets": ("tuple snippet", None, 12345, "good guy"),
                "mention_count": 15
            },
            "charlie": {
                "name": "Charlie",
                "context_snippets": None,
                "mention_count": 10
            }
        }

        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps([
                                {"name": "Bob", "iq": 120, "is_name": True}
                            ])
                        }
                    }
                ]
            }
            mock_post.return_value = mock_resp

            res = calculate_iq_with_ai(people_dict)
            self.assertIn("bob", res)
            self.assertIn("charlie", res)


if __name__ == "__main__":
    unittest.main()
