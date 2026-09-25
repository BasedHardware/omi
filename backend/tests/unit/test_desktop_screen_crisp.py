from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import desktop_screen_crisp
from utils.other.endpoints import get_current_user_uid


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(desktop_screen_crisp.router)
    app.dependency_overrides[get_current_user_uid] = lambda: "user-1"
    return TestClient(app)


def test_screen_activity_sync_is_a_drain_that_stores_nothing():
    """Path 2 egress: the route accepts but persists nothing, anywhere.

    The shipped client only treats 200 as success and never gives up, so a 404
    would make it re-POST the same OCR batch every five minutes forever. This
    tombstone lets it drain and go quiet while writing no Firestore document
    and no vector. It is temporary; the real fix is the client change that
    stops uploading.
    """
    response = make_client().post(
        "/v1/screen-activity/sync",
        json={
            "rows": [
                {
                    "id": 1,
                    "timestamp": "2026-07-26T00:00:00Z",
                    "appName": "Safari",
                    "ocrText": "secret on-screen text",
                    "embedding": [0.1, 0.2],
                }
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == {"synced": 0, "last_id": 0}

    # Static tripwire (not behavioral coverage): the router must not import the
    # screen-activity persistence layers, which is the only way it could write
    # anything through them.
    import inspect

    router_source = inspect.getsource(desktop_screen_crisp)
    assert "database.screen_activity" not in router_source
    assert "database.vector_db" not in router_source
    assert "upsert_screen_activity" not in router_source


def test_crisp_unread_route_is_removed():
    assert make_client().get("/v1/crisp/unread").status_code == 404
