from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from models.product_memory import MemoryItem
from routers import memory_use as memory_use_router
from routers.memory_use import MemoryUseRequest
from utils.memory.memory_use import (
    MemoryUseAction,
    MemoryUseConflict,
    build_memory_use_patch,
    feedback_reason,
    feedback_value,
    normalize_feedback_id,
)


def _item(*, arguments=None, curation_weight=0, item_revision=1):
    now = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    return MemoryItem(
        memory_id="mem_1",
        uid="user_1",
        version=1,
        tier="short_term",
        status="active",
        processing_state="pending",
        content="The user is testing memory use feedback.",
        evidence=[],
        source_state="active",
        sensitivity_labels=[],
        visibility="private",
        user_asserted=True,
        captured_at=now,
        updated_at=now,
        expires_at=datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc),
        item_revision=item_revision,
        arguments=arguments or {},
        curation_weight=curation_weight,
    )


def test_feedback_id_is_trimmed_and_bounded():
    assert normalize_feedback_id("  feedback-1 ") == "feedback-1"
    with pytest.raises(ValueError, match="at most"):
        normalize_feedback_id("x" * 129)
    with pytest.raises(ValueError, match="blank"):
        normalize_feedback_id("  ")


def test_suppress_preserves_arguments_and_does_not_change_truth_or_currency():
    item = _item(arguments={"predicate": "prefers", "memory_use": {"state": "useful"}})
    patch = build_memory_use_patch(item, action="suppress", feedback_id="f-1")
    assert patch.arguments["predicate"] == "prefers"
    assert patch.arguments["memory_use"] == {
        "state": "suppressed",
        "suppressed": True,
        "last_action": "suppress",
        "feedback_id": "f-1",
    }
    assert patch.curation_weight == 0


def test_allow_is_the_explicit_reenable_action():
    item = _item(arguments={"memory_use": {"suppressed": True, "feedback_id": "old", "last_action": "suppress"}})
    patch = build_memory_use_patch(item, action=MemoryUseAction.allow, feedback_id="f-2")
    assert patch.arguments["memory_use"]["suppressed"] is False
    assert patch.arguments["memory_use"]["state"] == "allowed"


def test_useful_keeps_an_existing_suppression_and_raises_curation_floor():
    item = _item(
        arguments={"memory_use": {"suppressed": True, "feedback_id": "old", "last_action": "suppress"}},
        curation_weight=-2,
    )
    patch = build_memory_use_patch(item, action="useful", feedback_id="f-3")
    assert patch.arguments["memory_use"]["suppressed"] is True
    assert patch.curation_weight == 1


def test_feedback_id_reuse_is_durable_conflict():
    item = _item(arguments={"memory_use": {"suppressed": True, "feedback_id": "same", "last_action": "suppress"}})
    patch = build_memory_use_patch(item, action="suppress", feedback_id="same")
    assert patch.arguments["memory_use"]["suppressed"] is True
    with pytest.raises(MemoryUseConflict, match="different action"):
        build_memory_use_patch(item, action="allow", feedback_id="same")


def test_memory_use_request_rejects_extra_fields_and_blank_id():
    with pytest.raises(ValidationError):
        MemoryUseRequest(action="suppress", feedback_id=" ")
    with pytest.raises(ValidationError):
        MemoryUseRequest(action="suppress", feedback_id="ok", unexpected=True)


def test_memory_use_maps_to_unified_feedback_values():
    assert feedback_value("suppress") == -1
    assert feedback_value("allow") == 0
    assert feedback_value("useful") == 1
    assert feedback_reason("suppress") == "not_useful"
    assert feedback_reason("useful") is None


def test_memory_use_http_contract_runs_authenticated_suppress_allow_and_revision_error(monkeypatch):
    app = FastAPI()
    app.include_router(memory_use_router.router)
    monkeypatch.setattr(memory_use_router, "belief_model_enabled", lambda: True)
    state = {"item": _item()}

    def fake_apply(uid, memory_id, **kwargs):
        assert uid == "user_1"
        assert memory_id == state["item"].memory_id
        previous = state["item"]
        built = kwargs["build_patch"](previous, datetime.now(timezone.utc))
        assert built is not None
        _logical_updates, patch_updates = built
        updated = previous.model_copy(
            update={
                "arguments": patch_updates["arguments"],
                "curation_weight": patch_updates["curation_weight"],
                "item_revision": previous.item_revision + 1,
                "version": previous.version + 1,
            }
        )
        state["item"] = updated
        return previous, updated

    monkeypatch.setattr(memory_use_router, "_apply_canonical_user_mutation", fake_apply)
    monkeypatch.setattr(memory_use_router, "get_data_plane_firestore_client", lambda: object())
    route = next(route for route in app.routes if route.path == "/v3/memories/{memory_id}/use")
    app.dependency_overrides[route.dependant.dependencies[0].call] = lambda: "user_1"

    with TestClient(app) as client:
        suppressed = client.post(
            "/v3/memories/mem_1/use",
            json={"action": "suppress", "feedback_id": "http-suppress"},
        )
        assert suppressed.status_code == 200
        assert suppressed.json()["suppressed"] is True
        assert suppressed.json()["action"] == "suppress"

        allowed = client.post(
            "/v3/memories/mem_1/use",
            json={"action": "allow", "feedback_id": "http-allow"},
        )
        assert allowed.status_code == 200
        assert allowed.json()["suppressed"] is False
        assert allowed.json()["item_revision"] == 3

        stale = client.post(
            "/v3/memories/mem_1/use",
            json={
                "action": "useful",
                "feedback_id": "http-stale",
                "expected_item_revision": 1,
            },
        )
        assert stale.status_code == 409

        invalid = client.post(
            "/v3/memories/mem_1/use",
            json={"action": "suppress", "feedback_id": " "},
        )
        assert invalid.status_code == 422


def test_memory_use_route_uses_the_configured_customer_data_plane_client(monkeypatch):
    """The route is registered on desktop-backend, so its Firestore reads and
    writes must target the configured customer data plane — never the compute
    project's default client (silent cross-plane corruption otherwise)."""
    app = FastAPI()
    app.include_router(memory_use_router.router)
    monkeypatch.setattr(memory_use_router, "belief_model_enabled", lambda: True)

    sentinel = object()
    monkeypatch.setattr(memory_use_router, "get_data_plane_firestore_client", lambda: sentinel)
    seen = {}

    def fake_apply(uid, memory_id, **kwargs):
        seen["db_client"] = kwargs.get("db_client")
        item = _item()
        return item, item

    monkeypatch.setattr(memory_use_router, "_apply_canonical_user_mutation", fake_apply)
    route = next(route for route in app.routes if route.path == "/v3/memories/{memory_id}/use")
    app.dependency_overrides[route.dependant.dependencies[0].call] = lambda: "user_1"

    with TestClient(app) as client:
        response = client.post(
            "/v3/memories/mem_1/use",
            json={"action": "suppress", "feedback_id": "http-data-plane"},
        )
    assert response.status_code == 200
    assert seen["db_client"] is sentinel


@pytest.mark.parametrize(
    ("error_factory", "expected_status", "expected_detail"),
    [
        (
            lambda: _apply_store_error(
                "CanonicalMemoryIntakePausedError", "canonical memory intake is globally paused"
            ),
            503,
            "memory feedback intake is temporarily paused",
        ),
        (
            lambda: _apply_store_error(
                "MemoryFirestoreApplyError", "canonical apply blocked by account deletion fence"
            ),
            409,
            "canonical apply blocked by account deletion fence",
        ),
    ],
)
def test_memory_use_maps_apply_store_pause_and_fence_errors(
    monkeypatch, error_factory, expected_status, expected_detail
):
    """The canonical adapter raises MemoryFirestoreApplyError (not
    RuntimeError) for intake pause and account-deletion fences; these must map
    to retry/authorization responses, not leak unhandled 500s."""
    app = FastAPI()
    app.include_router(memory_use_router.router)
    monkeypatch.setattr(memory_use_router, "belief_model_enabled", lambda: True)

    def raise_apply(*_args, **_kwargs):
        raise error_factory()

    monkeypatch.setattr(memory_use_router, "_apply_canonical_user_mutation", raise_apply)
    monkeypatch.setattr(memory_use_router, "get_data_plane_firestore_client", lambda: object())
    route = next(route for route in app.routes if route.path == "/v3/memories/{memory_id}/use")
    app.dependency_overrides[route.dependant.dependencies[0].call] = lambda: "user_1"

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/v3/memories/mem_1/use",
            json={"action": "suppress", "feedback_id": "http-fence"},
        )
    assert response.status_code == expected_status
    assert response.json()["detail"] == expected_detail


def _apply_store_error(class_name: str, message: str) -> Exception:
    from database import memory_apply_store

    return getattr(memory_apply_store, class_name)(message)
