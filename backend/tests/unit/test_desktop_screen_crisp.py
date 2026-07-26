from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import desktop_screen_crisp
from utils.other.endpoints import get_current_user_uid


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(desktop_screen_crisp.router)
    app.dependency_overrides[get_current_user_uid] = lambda: "user-1"
    return TestClient(app)


def test_screen_activity_sync_writes_rows_and_embeddings(monkeypatch):
    writes = []
    monkeypatch.setattr(
        desktop_screen_crisp, "upsert_screen_activity", lambda uid, rows: writes.append((uid, rows)) or 2
    )
    monkeypatch.setattr(
        desktop_screen_crisp, "upsert_screen_activity_vectors", lambda uid, rows: writes.append(("vectors", uid, rows))
    )

    response = make_client().post(
        "/v1/screen-activity/sync",
        json={
            "rows": [
                {"id": 4, "timestamp": "2026-07-26T00:00:00Z", "appName": "Safari", "embedding": [0.1]},
                {"id": 7, "timestamp": "2026-07-26T00:01:00Z", "ocrText": "hello"},
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == {"synced": 2, "last_id": 7}
    assert writes == [
        (
            "user-1",
            [
                {
                    "id": 4,
                    "timestamp": "2026-07-26T00:00:00Z",
                    "appName": "Safari",
                    "windowTitle": "",
                    "ocrText": "",
                    "embedding": [0.1],
                },
                {
                    "id": 7,
                    "timestamp": "2026-07-26T00:01:00Z",
                    "appName": "",
                    "windowTitle": "",
                    "ocrText": "hello",
                    "embedding": None,
                },
            ],
        ),
        (
            "vectors",
            "user-1",
            [
                {
                    "id": 4,
                    "timestamp": "2026-07-26T00:00:00Z",
                    "appName": "Safari",
                    "windowTitle": "",
                    "ocrText": "",
                    "embedding": [0.1],
                }
            ],
        ),
    ]


def test_screen_activity_sync_rejects_batches_larger_than_rust_contract():
    response = make_client().post(
        "/v1/screen-activity/sync",
        json={"rows": [{"id": index, "timestamp": "2026-07-26T00:00:00Z"} for index in range(101)]},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Maximum 100 rows per batch"}


def test_crisp_unread_preserves_operator_text_shape(monkeypatch):
    monkeypatch.setenv("CRISP_PLUGIN_IDENTIFIER", "identifier")
    monkeypatch.setenv("CRISP_PLUGIN_KEY", "key")
    monkeypatch.setenv("CRISP_WEBSITE_ID", "website")
    desktop_screen_crisp._session_cache.clear()
    monkeypatch.setattr(desktop_screen_crisp, "get_user", lambda uid: SimpleNamespace(email="User@Example.com"))
    responses = iter(
        [
            SimpleNamespace(
                is_success=True,
                json=lambda: {"data": [{"session_id": "session", "meta": {"email": "user@example.com"}}]},
            ),
            SimpleNamespace(
                is_success=True,
                json=lambda: {
                    "data": [
                        {"from": "operator", "type": "text", "timestamp": 11, "content": "hello"},
                        {"from": "user", "type": "text", "timestamp": 12, "content": "ignore"},
                        {"from": "operator", "type": "file", "timestamp": 13, "content": "ignore"},
                    ]
                },
            ),
        ]
    )

    async def crisp_get(url, headers):
        return next(responses)

    monkeypatch.setattr(desktop_screen_crisp, "_crisp_get", crisp_get)

    response = make_client().get("/v1/crisp/unread?since=10")

    assert response.status_code == 200
    assert response.json() == {"unread_count": 1, "messages": [{"text": "hello", "timestamp": 11, "from": "operator"}]}


def test_crisp_unread_is_empty_when_unconfigured(monkeypatch):
    monkeypatch.delenv("CRISP_PLUGIN_IDENTIFIER", raising=False)
    monkeypatch.delenv("CRISP_PLUGIN_KEY", raising=False)
    monkeypatch.delenv("CRISP_WEBSITE_ID", raising=False)

    assert make_client().get("/v1/crisp/unread").json() == {"unread_count": 0, "messages": []}
