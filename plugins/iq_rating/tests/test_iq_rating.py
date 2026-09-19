import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Ensure plugins/iq_rating is in Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from test_main import load_app

main = load_app()
filter_names_with_openai = main.filter_names_with_openai
calculate_iq_with_ai = main.calculate_iq_with_ai

class TestIqRatingExceptionGuards(unittest.TestCase):

    @patch.object(main.requests, "post")
    def test_filter_names_null_message_content(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [
                {"message": {"content": None}}
            ]
        }
        mock_post.return_value = mock_resp

        with patch.object(main, "OPENAI_API_KEY", "test-key"):
            result = filter_names_with_openai(["Alice", "Bob"])
            self.assertEqual(result, ["Alice", "Bob"])

    @patch.object(main.requests, "post")
    def test_filter_names_empty_choices(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": []}
        mock_post.return_value = mock_resp

        with patch.object(main, "OPENAI_API_KEY", "test-key"):
            result = filter_names_with_openai(["Alice", "Bob"])
            self.assertEqual(result, ["Alice", "Bob"])

    @patch.object(main.requests, "post")
    def test_calculate_iq_invalid_iq_type_fallback(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '[{"name": "Alice", "iq": "invalid_number", "is_name": true}]'
                    }
                }
            ]
        }
        mock_post.return_value = mock_resp

        people = {
            "alice": {"name": "Alice", "context_snippets": ["Alice is very smart"]}
        }

        with patch.object(main, "OPENAI_API_KEY", "test-key"):
            result = calculate_iq_with_ai(people)
            self.assertIn("alice", result)
            self.assertEqual(result["alice"]["iq"], 100)

    @patch.object(main.requests, "post")
    def test_calculate_iq_null_name_field(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '[{"name": null, "iq": 130, "is_name": true}]'
                    }
                }
            ]
        }
        mock_post.return_value = mock_resp

        people = {
            "alice": {"name": "Alice", "context_snippets": ["Alice is smart"]}
        }

        with patch.object(main, "OPENAI_API_KEY", "test-key"):
            result = calculate_iq_with_ai(people)
            self.assertIn("alice", result)

    @patch.object(main.requests, "post")
    def test_filter_names_network_exception_recovery(self, mock_post):
        mock_post.side_effect = Exception("Connection timeout")

        with patch.object(main, "OPENAI_API_KEY", "test-key"):
            result = filter_names_with_openai(["Alice", "Bob"])
            self.assertEqual(result, ["Alice", "Bob"])

if __name__ == "__main__":
    unittest.main()
