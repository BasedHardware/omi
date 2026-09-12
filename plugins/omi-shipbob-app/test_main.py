"""Regression tests for cancel_wro error classification (#13183)."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


class FakeResp:
    def __init__(self, status_code=200, text="", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data if json_data is not None else {}

    def json(self):
        return self._json


def _headers_ok():
    return {"Authorization": "Bearer t", "Content-Type": "application/json"}


@patch("main.get_shipbob_headers", return_value=_headers_ok())
@patch("main.refresh_token_if_needed")
@patch("main.requests.post")
def test_cancel_empty_body_500_is_error(mock_post, _refresh, _headers):
    mock_post.return_value = FakeResp(status_code=500, text="")
    resp = client.post("/tools/cancel_wro", json={"uid": "u1", "wro_id": "123"})
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("error")
    assert "123" not in str(body.get("result") or "")


@patch("main.get_shipbob_headers", return_value=_headers_ok())
@patch("main.refresh_token_if_needed")
@patch("main.make_shipbob_request", return_value=None)
def test_cancel_none_result_is_error(mock_req, _refresh, _headers):
    resp = client.post("/tools/cancel_wro", json={"uid": "u1", "wro_id": "123"})
    body = resp.json()
    assert body.get("error")


@patch("main.get_shipbob_headers", return_value=_headers_ok())
@patch("main.refresh_token_if_needed")
@patch("main.make_shipbob_request", return_value={"error": "forbidden", "status_code": 403})
def test_cancel_nonempty_error_is_surfaced(mock_req, _refresh, _headers):
    resp = client.post("/tools/cancel_wro", json={"uid": "u1", "wro_id": "123"})
    body = resp.json()
    assert "forbidden" in body.get("error", "")


@patch("main.get_shipbob_headers", return_value=_headers_ok())
@patch("main.refresh_token_if_needed")
@patch("main.make_shipbob_request", return_value={"id": 123, "status": "cancelled"})
def test_cancel_success_200_object(mock_req, _refresh, _headers):
    resp = client.post("/tools/cancel_wro", json={"uid": "u1", "wro_id": "123"})
    body = resp.json()
    assert body.get("error") in (None, "")
    assert "cancelled" in (body.get("result") or "").lower()
