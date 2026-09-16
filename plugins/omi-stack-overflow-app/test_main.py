"""
Hermetic test suite for Stack Overflow Integration App.
Covers formatting, validation handlers, null-safety, and API fallbacks without network access.
"""

import unittest
from unittest.mock import AsyncMock, patch
import httpx
from fastapi.testclient import TestClient

from main import app, _format_question, _format_answer, _safe_limit, _safe_site, _clean_text


class TestStackOverflowApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app, raise_server_exceptions=False)

    def test_root_endpoint(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Stack Overflow x Omi", res.text)

    def test_health_endpoint(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok"})

    def test_tools_manifest(self):
        res = self.client.get("/.well-known/omi-tools.json")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("tools", data)
        self.assertEqual(len(data["tools"]), 3)

    # 1. Null owner and null tag regressions
    def test_format_answer_null_owner_does_not_crash(self):
        # Deleted or anonymized user where owner is explicitly None
        item = {
            "owner": None,
            "score": 10,
            "is_accepted": True,
            "body": "<p>Sample answer body</p>",
        }
        out = _format_answer(item, 1)
        self.assertIn("1. unknown | 10 score | accepted", out)
        self.assertIn("Sample answer body", out)

    def test_format_answer_missing_owner(self):
        item = {
            "score": 5,
            "body": "No owner key",
        }
        out = _format_answer(item, 2)
        self.assertIn("2. unknown | 5 score", out)

    def test_format_question_null_tags(self):
        item = {
            "title": "Question with null tags",
            "question_id": 123,
            "score": 4,
            "answer_count": 1,
            "view_count": 100,
            "accepted_answer_id": None,
            "tags": None,
        }
        out = _format_question(item, 1, "stackoverflow")
        self.assertIn("Tags: no tags", out)

    def test_format_question_empty_tags(self):
        item = {
            "title": "Empty tags",
            "question_id": 124,
            "tags": [],
        }
        out = _format_question(item, 1, "stackoverflow")
        self.assertIn("Tags: no tags", out)

    def test_clean_text_edge_cases(self):
        self.assertEqual(_clean_text(None), "")
        self.assertEqual(_clean_text(""), "")
        self.assertEqual(_clean_text("<p>Hello &amp; world</p>"), "Hello & world")
        self.assertEqual(_clean_text("<code>code_block</code>"), "`code_block`")

    # 2. Endpoint validation error handler returning 200 with error envelope
    def test_search_questions_missing_query_returns_200_error(self):
        res = self.client.post("/tools/search_questions", json={})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsNone(data.get("result"))
        self.assertIn("error", data)
        self.assertIn("query", data["error"])

    def test_search_questions_empty_query_string(self):
        res = self.client.post("/tools/search_questions", json={"query": "   "})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("error", data)
        self.assertIn("Missing required field: query", data["error"])

    def test_get_question_missing_id_returns_200_error(self):
        res = self.client.post("/tools/get_question", json={})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("error", data)
        self.assertIn("question_id", data["error"])

    def test_get_question_invalid_id_type(self):
        res = self.client.post("/tools/get_question", json={"question_id": "not-an-int"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("error", data)
        self.assertIn("integer", data["error"])

    def test_get_top_answers_missing_id(self):
        res = self.client.post("/tools/get_top_answers", json={})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("error", data)

    # 3. Null values from Omi client coercion
    @patch("main._request_json", new_callable=AsyncMock)
    def test_search_questions_null_optional_fields_coerced(self, mock_request):
        mock_request.return_value = {
            "items": [
                {
                    "title": "How to use Python",
                    "question_id": 999,
                    "score": 10,
                    "answer_count": 2,
                    "view_count": 50,
                    "tags": ["python"],
                }
            ]
        }
        res = self.client.post(
            "/tools/search_questions",
            json={"query": "python", "site": None, "limit": None, "tags": None, "accepted": None},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsNone(data.get("error"))
        self.assertIn("Stack Exchange results for 'python' on stackoverflow:", data["result"])

    @patch("main._request_json", new_callable=AsyncMock)
    def test_search_questions_no_results(self, mock_request):
        mock_request.return_value = {"items": []}
        res = self.client.post("/tools/search_questions", json={"query": "unmatchedquery123"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("No Stack Exchange questions found", data["result"])

    @patch("main._request_json", new_callable=AsyncMock)
    def test_get_question_success(self, mock_request):
        mock_request.return_value = {
            "items": [
                {
                    "title": "Valid Question",
                    "question_id": 555,
                    "creation_date": 1609459200,
                    "score": 15,
                    "answer_count": 3,
                    "view_count": 200,
                    "tags": ["python", "asyncio"],
                    "body": "<p>Body text here</p>",
                }
            ]
        }
        res = self.client.post("/tools/get_question", json={"question_id": 555})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("Valid Question", data["result"])
        self.assertIn("Question body:\nBody text here", data["result"])

    @patch("main._request_json", new_callable=AsyncMock)
    def test_get_top_answers_success_with_null_owner(self, mock_request):
        mock_request.return_value = {
            "items": [
                {
                    "owner": None,
                    "score": 25,
                    "is_accepted": True,
                    "body": "<p>Top answer content</p>",
                }
            ]
        }
        res = self.client.post("/tools/get_top_answers", json={"question_id": 555, "limit": 2})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("Top answers for question 555 on stackoverflow:", data["result"])
        self.assertIn("1. unknown | 25 score | accepted", data["result"])

    @patch("main._request_json", new_callable=AsyncMock)
    def test_api_upstream_error_handled_gracefully(self, mock_request):
        mock_request.side_effect = ValueError("API rate limit exceeded")
        res = self.client.post("/tools/search_questions", json={"query": "test"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("Stack Exchange search failed: API rate limit exceeded", data["error"])


if __name__ == "__main__":
    unittest.main()
