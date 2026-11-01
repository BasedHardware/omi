from contextlib import nullcontext
from datetime import datetime, timezone
import logging
from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from database import vector_db
from routers import desktop_screen_crisp
from utils.other.endpoints import get_current_user_uid
from utils.retrieval.frame_request_authority import FrameRequestAuthorityDecision


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(desktop_screen_crisp.router)
    app.dependency_overrides[get_current_user_uid] = lambda: "user-1"
    return TestClient(app)


@pytest.fixture(autouse=True)
def _disable_frame_request_authority(monkeypatch):
    async def disabled(*_args, **_kwargs):
        return FrameRequestAuthorityDecision(enabled=False)

    monkeypatch.setattr(desktop_screen_crisp, "resolve_frame_request_authority", disabled)


def test_crisp_unread_route_is_removed():
    assert make_client().get("/v1/crisp/unread").status_code == 404


def _entitle(monkeypatch, entitled: bool = True) -> None:
    """Pin the screen-vector entitlement.

    Keep unrelated sync fixtures hermetic. Authority behavior has explicit router
    tests below with fake database and provider seams.
    """
    monkeypatch.setattr(desktop_screen_crisp, "grants_cloud_screen_vectors", AsyncMock(return_value=entitled))


def _enable_frame_requests(monkeypatch, generation: int = 7) -> None:
    async def enabled(*_args, **_kwargs):
        return FrameRequestAuthorityDecision(enabled=True, account_generation=generation)

    monkeypatch.setattr(desktop_screen_crisp, "resolve_frame_request_authority", enabled)


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
                    "accountGeneration": 0,
                    "deviceRetentionSeconds": None,
                    "captureEligible": False,
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
                    "accountGeneration": 0,
                    "deviceRetentionSeconds": None,
                    "captureEligible": False,
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
                    "accountGeneration": 0,
                    "deviceRetentionSeconds": None,
                    "captureEligible": False,
                }
            ],
        ),
    ]


def test_slow_sync_logs_phase_durations_without_uid(monkeypatch, caplog):
    ticks = iter(range(12))
    monkeypatch.setattr(desktop_screen_crisp, "time", SimpleNamespace(perf_counter=lambda: next(ticks)))
    monkeypatch.setattr(desktop_screen_crisp, "is_desktop_trial_paywalled", lambda *_: False)
    _entitle(monkeypatch)
    _enable_frame_requests(monkeypatch)
    monkeypatch.setattr(desktop_screen_crisp, "upsert_screen_activity", lambda uid, rows: len(rows))
    monkeypatch.setattr(desktop_screen_crisp, "upsert_screen_activity_vectors", lambda uid, rows: None)
    monkeypatch.setattr(desktop_screen_crisp, "reconcile_conversation_keyframe_jobs", lambda *args, **kwargs: None)
    monkeypatch.setattr(desktop_screen_crisp, "list_pending_frame_requests", lambda *args, **kwargs: [])

    with caplog.at_level(logging.INFO):
        response = make_client().post(
            "/v1/screen-activity/sync",
            json={
                "account_generation": 7,
                "rows": [
                    {
                        "id": 1,
                        "timestamp": "2026-07-26T00:00:00Z",
                        "clientDeviceId": "mac-a",
                        "embedding": [0.1],
                    }
                ],
            },
        )

    assert response.status_code == 200
    lines = [record.message for record in caplog.records if "screen_activity_sync_slow" in record.message]
    assert len(lines) == 1
    assert (
        "total_ms=11000 row_count=1 upsert_ms=1000 entitlement_ms=1000 vector_ms=1000 frame_requests_ms=2000"
        in lines[0]
    )
    assert "user-1" not in lines[0]


def test_enabled_screen_sync_returns_only_device_routed_frame_metadata(monkeypatch):
    _entitle(monkeypatch)
    _enable_frame_requests(monkeypatch)
    monkeypatch.setattr(desktop_screen_crisp, "upsert_screen_activity", lambda uid, rows: len(rows))
    monkeypatch.setattr(desktop_screen_crisp, "upsert_screen_activity_vectors", lambda uid, rows: None)
    monkeypatch.setattr(desktop_screen_crisp, "reconcile_conversation_keyframe_jobs", lambda *args, **kwargs: 0)
    monkeypatch.setattr(
        desktop_screen_crisp,
        "list_pending_frame_requests",
        lambda uid, **kwargs: [
            SimpleNamespace(
                request_id="frame-1",
                device_id=kwargs["device_id"],
                account_generation=kwargs["account_generation"],
                conversation_id="conversation-1",
                screenshot_id="42",
                state=SimpleNamespace(value="requested"),
                expires_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
            )
        ],
    )

    response = make_client().post(
        "/v1/screen-activity/sync",
        json={
            "account_generation": 7,
            "rows": [{"id": 1, "timestamp": "2026-07-26T00:00:00Z", "clientDeviceId": "mac-a"}],
        },
    )

    assert response.status_code == 200
    assert response.json()["frame_requests"] == [
        {
            "request_id": "frame-1",
            "device_id": "mac-a",
            "account_generation": 7,
            "conversation_id": "conversation-1",
            "screenshot_id": "42",
            "state": "requested",
            "expires_at": "2026-08-25T00:00:00+00:00",
        }
    ]
    assert "image_base64" not in response.text


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
    monkeypatch.setattr(vector_db, "external_write_fence", lambda *_args, **_kwargs: nullcontext())
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


@pytest.mark.asyncio
async def test_unavailable_authority_retains_rows_without_vector_spend(monkeypatch):
    """Unknown authority never becomes a cloud grant; retained rows allow later backfill."""
    import utils.subscription as subscription

    subscription.clear_cloud_screen_vector_entitlement_cache("uid-under-test")
    monkeypatch.setattr(subscription.screen_vector_entitlements, "get_customer_firestore_client", lambda: object())
    monkeypatch.setattr(
        subscription.users_db,
        "get_user_valid_subscription",
        lambda uid, **_kwargs: (_ for _ in ()).throw(RuntimeError("firestore unavailable")),
    )

    with pytest.raises(subscription.screen_vector_entitlements.ScreenVectorAuthorityUnavailable):
        await subscription.grants_cloud_screen_vectors("uid-under-test")


def test_vector_batch_unknown_authority_is_not_acknowledged_and_recovers_on_retry(monkeypatch):
    from collections import OrderedDict
    from unittest.mock import Mock
    from utils import screen_vector_entitlements as authority
    from config.plan_catalog import RECOGNIZED_STRIPE_PRICE_PLAN_TYPES

    price = next(iter(RECOGNIZED_STRIPE_PRICE_PLAN_TYPES))
    monkeypatch.setenv('LADDER_V1_PLUS_MONTH_PRICE_ID', 'price_router_ladder_plus')
    clock = [100.0]
    monkeypatch.setattr(authority, '_identity_cache', OrderedDict())
    monkeypatch.setattr(authority, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(authority, 'get_customer_firestore_client', lambda: object())
    period_end = datetime.now(timezone.utc).timestamp() + 3600
    monkeypatch.setattr(
        authority.users_db,
        'get_user_valid_subscription',
        lambda *a, **kw: {
            'plan': RECOGNIZED_STRIPE_PRICE_PLAN_TYPES[price].value,
            'current_price_id': price,
            'stripe_subscription_id': 'sub_retry',
            'current_period_end': period_end,
        },
    )
    provider = Mock(side_effect=RuntimeError('temporary authority outage'))
    monkeypatch.setattr(authority, 'read_stripe_subscription', provider)
    stored = {}

    def upsert(_uid, rows):
        for row in rows:
            stored[row['id']] = row
        return len(rows)

    vectors = Mock(return_value=1)
    monkeypatch.setattr(desktop_screen_crisp, 'upsert_screen_activity', upsert)
    monkeypatch.setattr(desktop_screen_crisp, 'upsert_screen_activity_vectors', vectors)
    payload = {'rows': [{'id': 1, 'timestamp': '2026-07-26T00:00:00.000Z', 'ocrText': 'text', 'embedding': [0.1]}]}
    with make_client() as client:
        response = client.post('/v1/screen-activity/sync', json=payload)
        assert response.status_code == 503
        assert response.headers['Retry-After'] == '5'
        assert 'synced' not in response.json() and 'last_id' not in response.json()
        assert 'plan_gated' not in response.text
        assert len(stored) == 1, 'raw write is retained and idempotent'
        vectors.assert_not_called()
        provider.side_effect = None
        provider.return_value = {'id': 'sub_retry', 'items': {'data': [{'price': {'id': price}}]}}
        # A negative hit still cannot acknowledge or spend. Recover at bounded expiry.
        assert client.post('/v1/screen-activity/sync', json=payload).status_code == 503
        assert provider.call_count == 1
        clock[0] += 6
        response = client.post('/v1/screen-activity/sync', json=payload)
    assert response.status_code == 200
    assert response.json()['synced'] == 1 and response.json()['last_id'] == 1
    assert len(stored) == 1
    vectors.assert_called_once()
    assert vectors.call_args.args[1][0]['embedding'] == [0.1]


def test_ocr_only_sync_needs_no_vector_authority(monkeypatch):
    authority = AsyncMock(side_effect=AssertionError('OCR-only batch requested vector authority'))
    vectors = AsyncMock(side_effect=AssertionError('OCR-only batch wrote vector'))
    monkeypatch.setattr(desktop_screen_crisp, 'grants_cloud_screen_vectors', authority)
    monkeypatch.setattr(desktop_screen_crisp, 'upsert_screen_activity', lambda uid, rows: len(rows))
    monkeypatch.setattr(desktop_screen_crisp, 'upsert_screen_activity_vectors', vectors)
    response = make_client().post(
        '/v1/screen-activity/sync',
        json={
            'rows': [{'id': 2, 'timestamp': '2026-07-26T00:00:00.000Z', 'ocrText': 'text'}],
        },
    )
    assert response.status_code == 200 and response.json()['last_id'] == 2
    authority.assert_not_called()
    vectors.assert_not_called()


@pytest.mark.parametrize(
    'plan,stored_price,billed_price,entitled',
    [
        ('basic', None, None, False),
        ('plus', 'legacy', 'price_router_ladder_plus', False),
        ('plus', None, 'legacy', True),
    ],
)
def test_known_vector_authority_controls_real_batch_without_false_retry(
    monkeypatch, plan, stored_price, billed_price, entitled
):
    from collections import OrderedDict
    from unittest.mock import Mock
    from utils import screen_vector_entitlements as authority
    from config.plan_catalog import RECOGNIZED_STRIPE_PRICE_PLAN_TYPES

    legacy = next(price for price, tier in RECOGNIZED_STRIPE_PRICE_PLAN_TYPES.items() if tier.value == 'plus')
    monkeypatch.setattr(authority, '_identity_cache', OrderedDict())
    monkeypatch.setenv('LADDER_V1_PLUS_MONTH_PRICE_ID', 'price_router_ladder_plus')
    monkeypatch.setattr(authority, 'get_customer_firestore_client', lambda: object())
    record = {
        'plan': plan,
        'current_price_id': legacy if stored_price == 'legacy' else stored_price,
        'current_period_end': datetime.now(timezone.utc).timestamp() + 3600,
        'stripe_subscription_id': 'sub_router' if billed_price else None,
    }
    monkeypatch.setattr(authority.users_db, 'get_user_valid_subscription', lambda *a, **kw: record)
    provider = Mock(
        return_value={
            'id': 'sub_router',
            'items': {'data': [{'price': {'id': legacy if billed_price == 'legacy' else billed_price}}]},
        }
    )
    monkeypatch.setattr(authority, 'read_stripe_subscription', provider)
    monkeypatch.setattr(desktop_screen_crisp, 'upsert_screen_activity', lambda uid, rows: len(rows))
    vectors = Mock(return_value=1)
    monkeypatch.setattr(desktop_screen_crisp, 'upsert_screen_activity_vectors', vectors)
    response = make_client().post(
        '/v1/screen-activity/sync',
        json={
            'rows': [{'id': 3, 'timestamp': '2026-07-26T00:00:00.000Z', 'ocrText': 'text', 'embedding': [0.1]}],
        },
    )
    assert response.status_code == 200 and response.json()['last_id'] == 3
    assert vectors.call_count == int(entitled)
    assert provider.call_count == int(billed_price is not None)
