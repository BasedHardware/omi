import pytest
from unittest.mock import MagicMock, patch
from plugins.iq_rating.main import filter_names_with_openai, calculate_iq_with_ai


def test_filter_names_with_openai_handles_empty_choices():
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": []}
        mock_post.return_value = mock_response

        with patch("plugins.iq_rating.main.OPENAI_API_KEY", "test-key"):
            result = filter_names_with_openai(["Alice", "Bob"])
            assert result == []


def test_filter_names_with_openai_handles_malformed_response():
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_post.return_value = mock_response

        with patch("plugins.iq_rating.main.OPENAI_API_KEY", "test-key"):
            result = filter_names_with_openai(["Alice", "Bob"])
            assert result == []


def test_calculate_iq_with_ai_handles_string_context_snippets():
    people_dict = {
        "alice": {
            "name": "Alice",
            "context_snippets": "Alice is brilliant at solving complex puzzles.",
        }
    }
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '[{"name": "Alice", "iq": 145, "is_name": true}]'
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        with patch("plugins.iq_rating.main.OPENAI_API_KEY", "test-key"):
            result = calculate_iq_with_ai(people_dict)
            assert "alice" in result
            assert result["alice"]["iq"] == 145
