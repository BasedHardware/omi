"""DELETE /v1/personas/{persona_id} must dispatch to delete_persona, not the thumbnail uploader.

The route decorator was stacked on `upload_app_thumbnail_endpoint`:

    @router.delete('/v1/personas/{persona_id}', ..., response_model=AppThumbnailUploadResponse)
    @router.post('/v1/app/thumbnails', ..., response_model=AppThumbnailUploadResponse)
    async def upload_app_thumbnail_endpoint(file: UploadFile = File(...), uid=Depends(...)):

so the persona delete path was served by the thumbnail handler, which requires a multipart file
body and authenticates with a regular Firebase uid. Meanwhile the real `delete_persona` below it
carried no decorator at all and was unreachable, taking its admin `secret_key` gate with it.

These assertions are route-table facts rather than source-text checks: they read the registered
routes off the app and assert which endpoint function each one resolves to, so the test fails if
the decorator ever drifts onto the wrong function again.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from routers import apps as apps_router  # noqa: E402


def _routes_for(path: str, method: str):
    return [
        r
        for r in apps_router.router.routes
        if getattr(r, "path", None) == path and method in getattr(r, "methods", set())
    ]


def test_persona_delete_dispatches_to_delete_persona():
    matches = _routes_for("/v1/personas/{persona_id}", "DELETE")

    assert len(matches) == 1, f"expected exactly one DELETE route, got {len(matches)}"
    assert matches[0].endpoint is apps_router.delete_persona, (
        "DELETE /v1/personas/{persona_id} resolves to " f"{matches[0].endpoint.__name__}, not delete_persona"
    )


def test_persona_delete_keeps_its_admin_secret_key_gate():
    """The intended handler is admin-gated; the thumbnail handler is not.

    Reaching the wrong endpoint silently swapped an ADMIN_KEY header check for a regular
    per-user Firebase dependency, so assert the served handler still takes secret_key.
    """
    endpoint = _routes_for("/v1/personas/{persona_id}", "DELETE")[0].endpoint

    assert "secret_key" in endpoint.__annotations__, f"{endpoint.__name__} has no secret_key parameter"
    assert "file" not in endpoint.__annotations__, f"{endpoint.__name__} unexpectedly requires a file upload"


def test_thumbnail_upload_still_serves_its_own_post_route():
    """Removing the misplaced decorator must not disturb the route it was stacked on."""
    matches = _routes_for("/v1/app/thumbnails", "POST")

    assert len(matches) == 1
    assert matches[0].endpoint is apps_router.upload_app_thumbnail_endpoint


def test_thumbnail_uploader_no_longer_serves_any_delete_route():
    delete_routes = [
        r
        for r in apps_router.router.routes
        if "DELETE" in getattr(r, "methods", set())
        and getattr(r, "endpoint", None) is apps_router.upload_app_thumbnail_endpoint
    ]

    assert delete_routes == [], "the thumbnail uploader is still registered for a DELETE route"
