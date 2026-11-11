from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import desktop_deprecated


def test_deprecated_route_surface_is_registered() -> None:
    actual = {
        (method, route.path)
        for route in desktop_deprecated.router.routes
        for method in route.methods
        if method != "HEAD"
    }
    expected = {(method, path) for path, methods in desktop_deprecated._ROUTES.items() for method in methods}
    assert actual == expected
    assert len(actual) == 130


def test_deprecated_routes_preserve_gone_response() -> None:
    app = FastAPI()
    app.include_router(desktop_deprecated.router)
    response = TestClient(app).patch("/v1/conversations/conversation-1")

    assert response.status_code == 410
    assert response.json() == {
        "error": "gone",
        "message": (
            "This endpoint (PATCH /v1/conversations/conversation-1) is deprecated and no longer served by the "
            "desktop backend. See https://api.omi.me for supported endpoints."
        ),
        "migration": "https://api.omi.me",
    }
