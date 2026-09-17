from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from main import (
    REQUEST_TIMEOUT_SECONDS,
    _format_answer,
    _format_date,
    _format_question,
    _request_json,
    app,
)


def _question_item(**overrides):
    item = {
        "title": "How do I parse JSON?",
        "question_id": 1,
        "score": 3,
        "answer_count": 2,
        "view_count": 10,
        "accepted_answer_id": None,
        "tags": ["python", "json"],
        "link": "https://stackoverflow.com/q/1",
    }
    item.update(overrides)
    return item


def _answer_item(**overrides):
    item = {
        "owner": {"display_name": "Alice"},
        "score": 7,
        "is_accepted": True,
        "body": "<p>Use the json module.</p>",
    }
    item.update(overrides)
    return item


def test_search_questions_well_formed_unchanged():
    client = TestClient(app)

    mock_data = {"items": [_question_item()]}

    with patch("main._request_json", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_data

        resp = client.post("/tools/search_questions", json={"query": "json", "limit": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None
        assert "How do I parse JSON?" in data["result"]
        assert "Tags: python, json" in data["result"]

        mock_req.assert_awaited_once()
        called_path = mock_req.await_args[0][0]
        assert called_path == "/search/advanced"


def test_search_questions_rejects_non_dict_payload():
    client = TestClient(app)

    with patch("main._request_json", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = ["unexpected", "list"]

        resp = client.post("/tools/search_questions", json={"query": "json"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"] is None
        assert "malformed response payload" in data["error"]


def test_search_questions_rejects_non_list_items():
    client = TestClient(app)

    with patch("main._request_json", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"items": None}

        resp = client.post("/tools/search_questions", json={"query": "json"})
        data = resp.json()
        assert data["result"] is None
        assert "malformed response payload" in data["error"]


def test_search_questions_skips_none_items():
    client = TestClient(app)

    with patch("main._request_json", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"items": [None, "not-a-dict", _question_item()]}

        resp = client.post("/tools/search_questions", json={"query": "json"})
        data = resp.json()
        assert data["error"] is None
        assert "How do I parse JSON?" in data["result"]
        assert "Untitled question" not in data["result"]


def test_get_question_skips_invalid_items():
    client = TestClient(app)

    with patch("main._request_json", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"items": [None]}

        resp = client.post("/tools/get_question", json={"question_id": 1})
        data = resp.json()
        assert data["result"] is None
        assert "No question found for ID 1" in data["error"]


def test_get_question_rejects_non_list_items():
    client = TestClient(app)

    with patch("main._request_json", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"items": {"unexpected": "dict"}}

        resp = client.post("/tools/get_question", json={"question_id": 1})
        data = resp.json()
        assert data["result"] is None
        assert "malformed response payload" in data["error"]


def test_get_top_answers_well_formed_unchanged():
    client = TestClient(app)

    with patch("main._request_json", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"items": [_answer_item()]}

        resp = client.post("/tools/get_top_answers", json={"question_id": 1})
        data = resp.json()
        assert data["error"] is None
        assert "Alice | 7 score | accepted" in data["result"]
        assert "Use the json module." in data["result"]


def test_get_top_answers_rejects_non_dict_payload():
    client = TestClient(app)

    with patch("main._request_json", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = "not-a-dict"

        resp = client.post("/tools/get_top_answers", json={"question_id": 1})
        data = resp.json()
        assert data["result"] is None
        assert "malformed response payload" in data["error"]


def test_get_top_answers_all_invalid_elements():
    client = TestClient(app)

    with patch("main._request_json", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"items": [None, 42]}

        resp = client.post("/tools/get_top_answers", json={"question_id": 1})
        data = resp.json()
        assert data["error"] is None
        assert "No answers found for question ID 1" in data["result"]


def test_format_question_handles_non_dict_item():
    out = _format_question(None, 1, "stackoverflow")
    assert "1. Untitled question" in out
    assert "no tags" in out


def test_format_question_handles_non_list_tags():
    out = _format_question(_question_item(tags="python"), 1, "stackoverflow")
    assert "Tags: no tags" in out

    out_none = _format_question(_question_item(tags=None), 1, "stackoverflow")
    assert "Tags: no tags" in out_none


def test_format_answer_handles_non_dict_item():
    out = _format_answer("not-a-dict", 2)
    assert "2. unknown | unknown score" in out


def test_format_answer_handles_non_dict_owner():
    out = _format_answer(_answer_item(owner="Alice"), 1)
    assert "1. unknown | 7 score" in out


def test_format_date_handles_malformed_values():
    assert _format_date(None) == "unknown date"
    assert _format_date("not-a-timestamp") == "unknown date"
    assert _format_date(True) == "unknown date"
    assert _format_date(1e18) == "unknown date"


def test_request_json_rejects_non_dict_payload():
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return ["not", "a", "dict"]

    class FakeClient:
        def __init__(self):
            self.kwargs = None

        async def get(self, url, params=None, timeout=None):
            self.kwargs = {"url": url, "params": params, "timeout": timeout}
            return FakeResponse()

    fake_client = FakeClient()

    async def fake_get_client():
        return fake_client

    with patch("main._get_stack_client", fake_get_client):
        try:
            import asyncio

            asyncio.run(_request_json("/search/advanced", {"q": "json"}))
            raised = None
        except ValueError as exc:
            raised = exc

    assert raised is not None
    assert "non-dict payload" in str(raised)
    assert fake_client.kwargs["timeout"] == REQUEST_TIMEOUT_SECONDS


def test_stack_client_sets_explicit_timeout():
    import main

    client = main._new_stack_client()
    assert client.timeout == httpx.Timeout(REQUEST_TIMEOUT_SECONDS)
