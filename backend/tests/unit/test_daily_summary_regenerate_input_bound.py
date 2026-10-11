import os
from datetime import datetime, timedelta, timezone
from types import ModuleType
from unittest.mock import patch

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-fake-for-unit-tests')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from testing.import_isolation import AutoMockModule, stub_modules


def _make_fakes() -> dict:
    names = [
        "database._client",
        "database.redis_db",
        "database.conversations",
        "database.memories",
        "database.chat",
        "database.users",
        "database.user_usage",
        "database.llm_usage",
        "database.announcements",
        "database.notifications",
        "database.daily_summaries",
        "database.app_review_config",
        "database.webhook_health",
        "database.action_items",
        "database.goals",
        "database.workstreams",
        "database.apps",
        "utils.other.storage",
        "utils.apps",
        "utils.stripe",
        "utils.twilio_service",
        "utils.notifications",
        "utils.llm.external_integrations",
        "utils.llm.persona",
        "utils.llm.usage_tracker",
        "utils.llm.clients",
        "utils.llm.gateway_client",
    ]
    fakes: dict = {name: AutoMockModule(name) for name in names}
    streaming = ModuleType("utils.stt.streaming")
    streaming.deepgram_nova3_multi_languages = ['en']
    fakes["utils.stt.streaming"] = streaming
    return fakes


@pytest.fixture(scope="module", autouse=True)
def _isolation():
    with stub_modules(_make_fakes()):
        import routers.users as users_router

        yield users_router


def _conversation(index: int, overview_chars: int):
    from models.conversation import Conversation
    from models.structured import Structured

    started = datetime(2026, 9, 1, 8, tzinfo=timezone.utc) + timedelta(hours=index)
    return Conversation(
        id=f'c{index}',
        created_at=started,
        started_at=started,
        finished_at=started + timedelta(minutes=30),
        structured=Structured(title=f'Meeting {index}', overview='x' * overview_chars),
    )


def _regenerate(users_router, day):
    seen = {}

    def generate(uid, conversations, date_str, *args, **kwargs):
        seen['ids'] = [c.id for c in conversations]
        return {'id': 'fresh', 'date': date_str, 'headline': 'h', 'overview': 'o'}

    with patch.object(users_router, 'enforce_chat_quota'), patch.object(
        users_router, 'daily_summaries_db'
    ) as summaries_db, patch.object(users_router, 'notification_db') as notif_db, patch.object(
        users_router, 'conversations_db'
    ) as convs_db, patch.object(
        users_router, 'deserialize_conversations', return_value=day
    ), patch.object(
        users_router, 'generate_comprehensive_daily_summary', side_effect=generate
    ), patch.object(
        users_router, '_memories_learned_payload', return_value=[]
    ), patch.object(
        users_router, 'get_generic_cache', return_value=None
    ), patch.object(
        users_router, 'set_generic_cache'
    ):
        summaries_db.get_daily_summary.return_value = {'id': 's1', 'date': '2026-09-01'}
        notif_db.get_user_time_zone.return_value = 'UTC'
        convs_db.get_conversations.return_value = [{'id': c.id} for c in day]
        users_router.regenerate_daily_summary('s1', uid='u1', x_app_platform='ios')
    return seen['ids']


def test_regenerate_bounds_a_heavy_day_like_the_scheduled_job():
    import routers.users as users_router

    day = [_conversation(i, 150_000) for i in range(4)]

    assert _regenerate(users_router, day) == ['c2', 'c3']


def test_regenerate_keeps_a_normal_day_whole():
    import routers.users as users_router

    day = [_conversation(i, 2_000) for i in range(4)]

    assert _regenerate(users_router, day) == ['c0', 'c1', 'c2', 'c3']


class _Stop(Exception):
    pass


def test_web_generate_recap_bounds_a_heavy_day():
    import routers.users as users_router

    day = [_conversation(i, 150_000) for i in range(4)]
    seen = {}

    def generate(uid, conversations, *args, **kwargs):
        seen['ids'] = [c.id for c in conversations]
        raise _Stop()

    with patch.object(users_router, 'enforce_chat_quota'), patch.object(
        users_router, 'notification_db'
    ) as notif_db, patch.object(users_router, 'conversations_db') as convs_db, patch.object(
        users_router, 'deserialize_conversations', return_value=day
    ), patch.object(
        users_router, 'generate_comprehensive_daily_summary', side_effect=generate
    ), patch.object(
        users_router, '_memories_learned_payload', return_value=[]
    ):
        notif_db.get_user_time_zone.return_value = 'UTC'
        notif_db.get_all_tokens.return_value = ['token']
        convs_db.get_conversations.return_value = [{'id': c.id} for c in day]
        with pytest.raises(_Stop):
            users_router.test_daily_summary(
                users_router.TestDailySummaryRequest(date='2026-09-01'), uid='u1', x_app_platform='web'
            )

    assert seen['ids'] == ['c2', 'c3']


def test_regenerate_records_a_truncated_day_like_the_scheduled_job():
    import routers.users as users_router
    import utils.other.notifications as daily_summary_job

    with patch.object(daily_summary_job, '_record_daily_summary_fallback') as recorded:
        _regenerate(users_router, [_conversation(i, 150_000) for i in range(4)])

    recorded.assert_called_once_with(from_mode='full_day', to_mode='truncated_day', reason='quota', outcome='degraded')


def test_regenerate_records_nothing_for_a_normal_day():
    import routers.users as users_router
    import utils.other.notifications as daily_summary_job

    with patch.object(daily_summary_job, '_record_daily_summary_fallback') as recorded:
        _regenerate(users_router, [_conversation(i, 2_000) for i in range(4)])

    recorded.assert_not_called()
