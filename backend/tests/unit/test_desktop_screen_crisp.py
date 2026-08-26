from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from database import vector_db
from routers import desktop_screen_crisp
from utils.other.endpoints import get_current_user_uid


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(desktop_screen_crisp.router)
    app.dependency_overrides[get_current_user_uid] = lambda: "user-1"
    return TestClient(app)


def test_crisp_unread_route_is_removed():
    assert make_client().get("/v1/crisp/unread").status_code == 404


def _entitle(monkeypatch, entitled: bool = True) -> None:
    """Pin the screen-vector entitlement.

    Without this the gate performs a real subscription lookup: it fails open, so assertions
    still hold, but each test pays a live Firestore timeout.
    """
    monkeypatch.setattr(desktop_screen_crisp, "grants_cloud_screen_vectors", lambda uid: entitled)


def test_screen_activity_sync_writes_rows_and_embeddings(monkeypatch):
    _entitle(monkeypatch)
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
                {
                    "id": 4,
                    "timestamp": "2026-07-26T00:00:00.123Z",
                    "appName": "Safari",
                    "clientDeviceId": "mac-a",
                    "embedding": [0.1],
                },
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
                    "timestamp": "2026-07-26 00:00:00.123",
                    "appName": "Safari",
                    "windowTitle": "",
                    "ocrText": "",
                    "deviceName": None,
                    "clientDeviceId": "mac-a",
                    "embedding": [0.1],
                    "storageId": "mac-a-4",
                },
                {
                    "id": 7,
                    "timestamp": "2026-07-26 00:01:00.000",
                    "appName": "",
                    "windowTitle": "",
                    "ocrText": "hello",
                    "deviceName": None,
                    "clientDeviceId": None,
                    "embedding": None,
                    "storageId": "7",
                },
            ],
        ),
        (
            "vectors",
            "user-1",
            [
                {
                    "id": 4,
                    "timestamp": "2026-07-26 00:00:00.123",
                    "appName": "Safari",
                    "windowTitle": "",
                    "ocrText": "",
                    "deviceName": None,
                    "clientDeviceId": "mac-a",
                    "embedding": [0.1],
                    "storageId": "mac-a-4",
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


def test_screen_activity_sync_normalizes_iso_timestamp_before_firestore_write(monkeypatch):
    _entitle(monkeypatch)
    writes = []
    monkeypatch.setattr(
        desktop_screen_crisp, "upsert_screen_activity", lambda uid, rows: writes.extend(rows) or len(rows)
    )

    response = make_client().post(
        "/v1/screen-activity/sync",
        json={"rows": [{"id": 9, "timestamp": "2026-07-26T02:03:04.567891+02:00", "ocrText": "text"}]},
    )

    assert response.status_code == 200
    assert writes[0]["timestamp"] == "2026-07-26 00:03:04.567"


def test_screen_activity_storage_ids_are_device_scoped():
    first = desktop_screen_crisp.ScreenActivityRow(id=1, timestamp="2026-07-26T00:00:00Z", clientDeviceId="mac-a")
    second = desktop_screen_crisp.ScreenActivityRow(id=1, timestamp="2026-07-26T00:00:00Z", clientDeviceId="mac-b")

    assert first.storage_id() == "mac-a-1"
    assert second.storage_id() == "mac-b-1"


def test_screen_activity_vector_treats_canonical_naive_timestamp_as_utc(monkeypatch):
    upserts = []
    monkeypatch.setattr(
        vector_db,
        "index",
        SimpleNamespace(upsert=lambda **kwargs: upserts.append(kwargs)),
    )

    written = vector_db.upsert_screen_activity_vectors(
        "user-1",
        [
            {
                "id": 11,
                "timestamp": "2026-07-26 00:00:00.123",
                "appName": "SyntheticApp",
                "embedding": [0.1],
            }
        ],
    )

    assert written == 1
    assert upserts[0]["vectors"][0]["metadata"]["timestamp"] == 1785024000


@pytest.mark.asyncio
async def test_screen_activity_rejects_paywalled_desktop_user(monkeypatch):
    async def run_blocking(_, function, *args):
        return function(*args)

    monkeypatch.setattr(desktop_screen_crisp, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_screen_crisp, "is_desktop_trial_paywalled", lambda uid, platform: True)

    with pytest.raises(HTTPException) as error:
        await desktop_screen_crisp._authorized_desktop_user("user")

    assert error.value.status_code == 402
    assert error.value.detail == "trial_expired"


def test_a_free_desktop_user_syncs_rows_but_no_vectors(monkeypatch):
    """The row is the cheap half and stays; the vector is the expensive half and is withheld."""
    writes: list = []
    vectors: list = []
    monkeypatch.setattr(
        desktop_screen_crisp, "upsert_screen_activity", lambda uid, rows: writes.extend(rows) or len(rows)
    )
    monkeypatch.setattr(
        desktop_screen_crisp, "upsert_screen_activity_vectors", lambda uid, rows: vectors.extend(rows) or len(rows)
    )
    _entitle(monkeypatch, entitled=False)

    response = make_client().post(
        "/v1/screen-activity/sync",
        json={"rows": [{"id": 1, "timestamp": "2026-07-26T00:00:00.000Z", "ocrText": "text", "embedding": [0.1]}]},
    )

    assert response.status_code == 200
    assert [row["id"] for row in writes] == [1], "the row must still be stored"
    assert writes[0]["ocrText"] == "text", "the text is retained so vectors can be backfilled on upgrade"
    assert vectors == [], "no vector is written for an unentitled user"


def test_an_entitled_user_still_gets_vectors(monkeypatch):
    vectors: list = []
    monkeypatch.setattr(desktop_screen_crisp, "upsert_screen_activity", lambda uid, rows: len(rows))
    monkeypatch.setattr(
        desktop_screen_crisp, "upsert_screen_activity_vectors", lambda uid, rows: vectors.extend(rows) or len(rows)
    )
    _entitle(monkeypatch, entitled=True)

    response = make_client().post(
        "/v1/screen-activity/sync",
        json={"rows": [{"id": 1, "timestamp": "2026-07-26T00:00:00.000Z", "ocrText": "text", "embedding": [0.1]}]},
    )

    assert response.status_code == 200
    assert [row["id"] for row in vectors] == [1]


def test_the_entitlement_gate_fails_open(monkeypatch):
    """A subscription-lookup blip must overspend slightly, never silently strip paid search."""
    import utils.subscription as subscription

    subscription.clear_cloud_screen_vector_entitlement_cache("uid-under-test")
    monkeypatch.setattr(
        subscription.users_db,
        "get_user_valid_subscription",
        lambda uid: (_ for _ in ()).throw(RuntimeError("firestore unavailable")),
    )

    assert subscription.grants_cloud_screen_vectors("uid-under-test") is True
