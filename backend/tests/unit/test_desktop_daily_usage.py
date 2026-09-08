from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import database.daily_summaries as daily_summaries_db
import database.memories as memories_db
import database.notifications as notifications_db
import routers.users as users_router


def _usage_db(existing=None):
    fake_db = MagicMock()
    user_ref = fake_db.collection.return_value.document.return_value
    collection_ref = user_ref.collection.return_value
    usage_ref = collection_ref.document.return_value
    snapshot = MagicMock()
    snapshot.exists = existing is not None
    snapshot.to_dict.return_value = existing
    usage_ref.get.return_value = snapshot
    return fake_db, collection_ref, usage_ref


def test_desktop_daily_usage_upsert_max_merges_running_totals():
    fake_db, collection_ref, usage_ref = _usage_db(
        {
            'watching_seconds': 300,
            'listening_seconds': 20,
            'proactive_cards_shown': 4,
            'proactive_cards_acted': 2,
            'ptt_turns': 8,
        }
    )
    transaction = fake_db.transaction.return_value

    with patch.object(daily_summaries_db, 'db', fake_db), patch.object(
        daily_summaries_db.firestore, 'transactional', side_effect=lambda fn: fn
    ):
        daily_summaries_db.upsert_desktop_daily_usage(
            'uid1',
            '2026-09-01',
            'America/Los_Angeles',
            'macos_abc123',
            {
                'watching_seconds': 200,
                'listening_seconds': 40,
                'proactive_cards_shown': 6,
                'proactive_cards_acted': 1,
                'ptt_turns': 10,
            },
        )

    collection_ref.document.assert_called_once_with('2026-09-01__macos_abc123')
    payload = transaction.set.call_args.args[1]
    assert payload['watching_seconds'] == 300
    assert payload['listening_seconds'] == 40
    assert payload['proactive_cards_shown'] == 6
    assert payload['proactive_cards_acted'] == 2
    assert payload['ptt_turns'] == 10
    assert payload['date'] == '2026-09-01'
    assert payload['timezone'] == 'America/Los_Angeles'
    assert payload['client_device_id'] == 'macos_abc123'
    assert payload['updated_at'].tzinfo is not None
    usage_ref.get.assert_called_once_with(transaction=transaction)


def test_get_desktop_daily_usage_sums_devices_and_returns_zero_for_missing_fields():
    fake_db, collection_ref, _usage_ref = _usage_db()
    query = collection_ref.where.return_value
    query.stream.return_value = [
        SimpleNamespace(
            to_dict=lambda: {
                'watching_seconds': 60,
                'listening_seconds': 10,
                'proactive_cards_shown': 2,
                'proactive_cards_acted': 1,
                'ptt_turns': 3,
            }
        ),
        SimpleNamespace(
            to_dict=lambda: {
                'watching_seconds': 90,
                'listening_seconds': 20,
                'proactive_cards_shown': 4,
                'proactive_cards_acted': 2,
            }
        ),
    ]

    with patch.object(daily_summaries_db, 'db', fake_db):
        result = daily_summaries_db.get_desktop_daily_usage('uid1', '2026-09-01')

    assert result == {
        'watching_seconds': 150,
        'listening_seconds': 30,
        'proactive_cards_shown': 6,
        'proactive_cards_acted': 3,
        'ptt_turns': 3,
    }


def test_memories_created_counts_canonical_and_legacy_shapes_without_duplicates():
    fake_db = MagicMock()
    canonical_query = MagicMock()
    legacy_query = MagicMock()
    canonical_query.stream.return_value = [SimpleNamespace(id='canonical-only'), SimpleNamespace(id='shared')]
    legacy_query.stream.return_value = [SimpleNamespace(id='legacy-only'), SimpleNamespace(id='shared')]
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    end = datetime(2026, 9, 2, tzinfo=timezone.utc)

    with patch.object(
        memories_db,
        'CANONICAL_MEMORIES_CAPTURED_RANGE_QUERY',
        SimpleNamespace(build=MagicMock(return_value=canonical_query)),
    ), patch.object(
        memories_db,
        'MEMORIES_CREATED_RANGE_QUERY',
        SimpleNamespace(build=MagicMock(return_value=legacy_query)),
    ):
        result = memories_db.count_memories_created('uid1', start, end, firestore_client=fake_db)

    assert result == 3


# ---------------------------------------------------------------------------
# The heartbeat is the desktop's only route to the user document's time_zone
# ---------------------------------------------------------------------------


def _user_doc_db(existing_user: dict | None):
    fake_db = MagicMock()
    user_ref = fake_db.collection.return_value.document.return_value
    snapshot = MagicMock()
    snapshot.exists = existing_user is not None
    snapshot.to_dict.return_value = existing_user
    user_ref.get.return_value = snapshot
    return fake_db, user_ref


def test_set_user_time_zone_if_missing_writes_for_a_document_without_one():
    fake_db, user_ref = _user_doc_db({'email': 'desktop-only@example.com'})
    with patch.object(notifications_db, 'db', fake_db):
        assert notifications_db.set_user_time_zone_if_missing('uid1', 'America/New_York') is True
    user_ref.set.assert_called_once_with({'time_zone': 'America/New_York'}, merge=True)


def test_set_user_time_zone_if_missing_leaves_a_mobile_written_zone_alone():
    fake_db, user_ref = _user_doc_db({'time_zone': 'Asia/Tokyo'})
    with patch.object(notifications_db, 'db', fake_db):
        assert notifications_db.set_user_time_zone_if_missing('uid1', 'America/New_York') is False
    user_ref.set.assert_not_called()


def _heartbeat_request(users_router):
    return users_router.DesktopDailyUsageRequest(
        date=datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        timezone='UTC',
        client_device_id='macos_abc123',
        watching_seconds=10,
        listening_seconds=0,
        proactive_cards_shown=0,
        proactive_cards_acted=0,
        ptt_turns=0,
    )


def test_heartbeat_fills_a_missing_time_zone_once_and_then_trusts_the_flag():
    patches = {
        'daily_summaries_db': MagicMock(),
        'notification_db': MagicMock(),
        'get_generic_cache': MagicMock(side_effect=[None, {'time_zone': 'UTC'}]),
        'set_generic_cache': MagicMock(),
    }
    with patch.multiple(users_router, **patches):
        users_router.record_desktop_daily_usage(_heartbeat_request(users_router), uid='u1')
        users_router.record_desktop_daily_usage(_heartbeat_request(users_router), uid='u1')

    patches['daily_summaries_db'].upsert_desktop_daily_usage.assert_called()
    assert patches['daily_summaries_db'].upsert_desktop_daily_usage.call_count == 2
    # One document read across two heartbeats: the flag carries the answer for the second.
    patches['notification_db'].set_user_time_zone_if_missing.assert_called_once_with('u1', 'UTC')
    patches['set_generic_cache'].assert_called_once()
    key, value = patches['set_generic_cache'].call_args.args[:2]
    assert key == 'desktop_usage_time_zone_known:u1'
    assert value == {'time_zone': 'UTC'}
