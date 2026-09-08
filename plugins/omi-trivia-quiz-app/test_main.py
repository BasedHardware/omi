"""Hermetic unit tests for Omi Open Trivia & Voice Quiz App."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from main import (
    SimpleTTLCache,
    _format_trivia_question,
    _resolve_category_id,
    app,
    get_trivia_question,
    get_true_false_quiz,
    health,
    list_trivia_categories,
    omi_tools,
    question_pool,
    trivia_cache,
)
from models import (
    ChatToolResponse,
    GetTriviaQuestionRequest,
    ListCategoriesRequest,
    QuickTrueFalseQuizRequest,
)

SAMPLE_MULTIPLE = {
    "type": "multiple",
    "difficulty": "medium",
    "category": "Science &amp; Nature",
    "question": "What is the chemical symbol for Gold?",
    "correct_answer": "Au",
    "incorrect_answers": ["Ag", "Fe", "Cu"],
}

SAMPLE_BOOLEAN = {
    "type": "boolean",
    "difficulty": "easy",
    "category": "Geography",
    "question": "The Great Wall of China is visible from space with the naked eye.",
    "correct_answer": "False",
    "incorrect_answers": ["True"],
}


class TestModels(unittest.TestCase):
    """Test Pydantic schemas and validation contracts."""

    def test_chat_tool_response_valid_result(self):
        resp = ChatToolResponse(result="Question here")
        self.assertEqual(resp.result, "Question here")
        self.assertIsNone(resp.error)

    def test_chat_tool_response_valid_error(self):
        resp = ChatToolResponse(error="Failed to fetch")
        self.assertEqual(resp.error, "Failed to fetch")
        self.assertIsNone(resp.result)

    def test_chat_tool_response_invalid_both(self):
        with self.assertRaises(ValueError):
            ChatToolResponse(result="Q", error="Err")

    def test_chat_tool_response_invalid_neither(self):
        with self.assertRaises(ValueError):
            ChatToolResponse()

    def test_get_trivia_question_request(self):
        req = GetTriviaQuestionRequest(category="Science", difficulty="hard", question_type="multiple")
        self.assertEqual(req.category, "Science")
        self.assertEqual(req.difficulty, "hard")
        self.assertEqual(req.question_type, "multiple")

    def test_quick_true_false_request(self):
        req = QuickTrueFalseQuizRequest(category="History", difficulty="easy")
        self.assertEqual(req.category, "History")
        self.assertEqual(req.difficulty, "easy")


class TestHelpers(unittest.TestCase):
    """Test caching, category resolution, and question formatting."""

    def test_ttl_cache_eviction(self):
        cache = SimpleTTLCache(maxsize=2, ttl_seconds=100)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        self.assertIsNone(cache.get("a"))
        self.assertEqual(cache.get("b"), 2)
        self.assertEqual(cache.get("c"), 3)

    def test_ttl_cache_expiration(self):
        cache = SimpleTTLCache(maxsize=2, ttl_seconds=1)
        cache.set("a", 100)
        self.assertEqual(cache.get("a"), 100)
        cache._cache["a"] = (cache._cache["a"][0] - 2, 100)
        self.assertIsNone(cache.get("a"))

    def test_resolve_category_id_keywords(self):
        self.assertEqual(_resolve_category_id("science"), 17)
        self.assertEqual(_resolve_category_id("computers"), 18)
        self.assertEqual(_resolve_category_id("tech"), 18)
        self.assertEqual(_resolve_category_id("history"), 23)
        self.assertEqual(_resolve_category_id("geography"), 22)
        self.assertEqual(_resolve_category_id("movies"), 11)
        self.assertEqual(_resolve_category_id("music"), 12)
        self.assertIsNone(_resolve_category_id("UnknownCategory123"))

    def test_resolve_category_id_compound_preference(self):
        # "computer science" should match computers (18) rather than science (17)
        self.assertEqual(_resolve_category_id("computer science"), 18)
        self.assertEqual(_resolve_category_id("science"), 17)

    def test_format_multiple_choice_question(self):
        formatted = _format_trivia_question(SAMPLE_MULTIPLE)
        self.assertIn("What is the chemical symbol for Gold?", formatted)
        self.assertIn("Science & Nature", formatted)
        self.assertIn("Options:", formatted)
        self.assertIn("Au", formatted)
        self.assertIn("Correct Answer:", formatted)

    def test_format_boolean_question(self):
        formatted = _format_trivia_question(SAMPLE_BOOLEAN)
        self.assertIn("Quick True/False Challenge", formatted)
        self.assertIn("The Great Wall of China", formatted)
        self.assertIn("Correct Answer: False", formatted)


class TestEndpointsHermetic(unittest.IsolatedAsyncioTestCase):
    """Hermetic route handler tests with mocked HTTP client."""

    async def asyncSetUp(self):
        trivia_cache.clear()
        question_pool.clear()
        self.mock_client = AsyncMock()
        app.state.http_client = self.mock_client

    async def test_health_endpoint(self):
        res = await health()
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(res.get("service"), "omi-trivia-quiz-app")

    async def test_manifest_endpoint(self):
        manifest = await omi_tools()
        self.assertEqual(manifest.get("schema_version"), "1.0")
        self.assertEqual(manifest.get("auth", {}).get("type"), "none")
        tools = manifest.get("tools", [])
        self.assertEqual(len(tools), 3)

        tool_names = [t["name"] for t in tools]
        self.assertIn("get_trivia_question", tool_names)
        self.assertIn("get_true_false_quiz", tool_names)
        self.assertIn("list_trivia_categories", tool_names)

        for t in tools:
            self.assertIn("endpoint", t)
            self.assertEqual(t["method"], "POST")
            self.assertFalse(t["auth_required"])

    async def test_get_trivia_question_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response_code": 0, "results": [SAMPLE_MULTIPLE]}
        self.mock_client.get.return_value = mock_resp

        req = GetTriviaQuestionRequest(category="Science", difficulty="medium")
        resp = await get_trivia_question(req)
        self.assertIsNone(resp.error)
        self.assertIsNotNone(resp.result)
        self.assertIn("Gold", resp.result)
        self.assertIn("Au", resp.result)

    async def test_get_true_false_quiz_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response_code": 0, "results": [SAMPLE_BOOLEAN]}
        self.mock_client.get.return_value = mock_resp

        req = QuickTrueFalseQuizRequest(category="Geography")
        resp = await get_true_false_quiz(req)
        self.assertIsNone(resp.error)
        self.assertIsNotNone(resp.result)
        self.assertIn("Quick True/False Challenge", resp.result)
        self.assertIn("Great Wall of China", resp.result)

    async def test_list_trivia_categories_success(self):
        req = ListCategoriesRequest()
        resp = await list_trivia_categories(req)
        self.assertIsNone(resp.error)
        self.assertIsNotNone(resp.result)
        self.assertIn("Science & Nature", resp.result)
        self.assertIn("History", resp.result)
        self.assertIn("Geography", resp.result)

    async def test_get_trivia_question_empty_fallback(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response_code": 1, "results": []}
        self.mock_client.get.return_value = mock_resp

        req = GetTriviaQuestionRequest()
        resp = await get_trivia_question(req)
        self.assertIsNotNone(resp.error)
        self.assertIn("Could not retrieve", resp.error)

    async def test_opentdb_code_5_rate_limit_handled(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response_code": 5, "results": []}
        self.mock_client.get.return_value = mock_resp

        req = GetTriviaQuestionRequest(category="Science")
        resp = await get_trivia_question(req)
        self.assertIsNotNone(resp.error)
        self.assertIn("rate limit", resp.error)
        # Verify fallback was NOT executed
        self.assertEqual(self.mock_client.get.call_count, 1)

    async def test_fallback_preserves_question_type(self):
        mock_resp_empty = MagicMock()
        mock_resp_empty.status_code = 200
        mock_resp_empty.json.return_value = {"response_code": 1, "results": []}

        mock_resp_success = MagicMock()
        mock_resp_success.status_code = 200
        mock_resp_success.json.return_value = {"response_code": 0, "results": [SAMPLE_MULTIPLE]}

        self.mock_client.get.side_effect = [mock_resp_empty, mock_resp_success]

        req = GetTriviaQuestionRequest(category="Mythology", question_type="multiple")
        resp = await get_trivia_question(req)
        self.assertIsNone(resp.error)
        self.assertEqual(self.mock_client.get.call_count, 2)
        fallback_call_params = self.mock_client.get.call_args_list[1][1]["params"]
        self.assertEqual(fallback_call_params.get("type"), "multiple")

    async def test_question_pool_buffering(self):
        # Return 2 questions in the initial batch
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "response_code": 0,
            "results": [SAMPLE_MULTIPLE, SAMPLE_BOOLEAN],
        }
        self.mock_client.get.return_value = mock_resp

        req = GetTriviaQuestionRequest(category="Science")
        # First call fetches and returns question 1, pools question 2
        resp1 = await get_trivia_question(req)
        self.assertIsNone(resp1.error)
        self.assertEqual(self.mock_client.get.call_count, 1)

        # Second call immediately consumes question 2 from pool without calling HTTP client
        resp2 = await get_trivia_question(req)
        self.assertIsNone(resp2.error)
        self.assertEqual(self.mock_client.get.call_count, 1)


class TestFastAPIHttp(unittest.TestCase):
    """Test HTTP routing and exception handling."""

    def setUp(self):
        self.client = TestClient(app)

    def test_root_html(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])
        self.assertIn("Open Trivia", resp.text)

    def test_health_http(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    def test_manifest_http(self):
        resp = self.client.get("/.well-known/omi-tools.json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["schema_version"], "1.0")
        self.assertEqual(len(data["tools"]), 3)
        for t in data["tools"]:
            self.assertIn("endpoint", t)
            self.assertEqual(t["method"], "POST")
            self.assertFalse(t["auth_required"])

    def test_validation_exception_handler_returns_200_with_error(self):
        resp = self.client.post("/tools/get_trivia_question", json={"difficulty": "impossible_level"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("error", data)
        self.assertNotIn("result", data)
        self.assertIn("Invalid tool request", data["error"])


if __name__ == "__main__":
    unittest.main()
