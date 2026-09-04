"""The daily summary's "memories learned today" review contract.

`knowledge_nuggets` is LLM prose with no memory identity, so a client cannot let
the owner accept, reject, or correct what Omi stored. `memories_learned` carries
real canonical memory ids selected deterministically — no model call — and the
`day_summary` push carries a `memoryReviewCard` block only when the selection is
non-empty, so older clients see exactly the message they saw before.
"""

from datetime import datetime, timedelta, timezone

from models.daily_summary_payload import DailySummaryDayStatsPayload, LearnedMemoryRef
from models.memories import MemoryCategory, MemoryDB
from models.notification_message import NotificationMessage
from routers.users import DailySummaryResponse
from routers import users as users_router
from utils.memory.learned_today import (
    MEMORIES_LEARNED_LIMIT,
    memories_learned_for_summary,
    memory_review_card_block,
    select_memories_learned,
)

DAY_START = datetime(2026, 9, 1, 7, 0, tzinfo=timezone.utc)
DAY_END = DAY_START + timedelta(hours=24)


def _memory(memory_id: str, **overrides) -> MemoryDB:
    payload = {
        'id': memory_id,
        'uid': 'u1',
        'content': f'fact {memory_id}',
        'category': MemoryCategory.interesting,
        'created_at': DAY_START + timedelta(hours=1),
        'updated_at': DAY_START + timedelta(hours=1),
        'conversation_id': 'c1',
        'capture_confidence': 0.5,
    }
    payload.update(overrides)
    return MemoryDB(**payload)


def _select(memories, **kwargs):
    params = {
        'conversation_ids': ['c1', 'c2'],
        'window_start': DAY_START,
        'window_end': DAY_END,
    }
    params.update(kwargs)
    return select_memories_learned(memories, **params)


# --- selection rules -------------------------------------------------------


def test_rejected_memory_is_never_offered_again():
    """A memory the owner already rejected must not come back on tomorrow's card."""
    picked = _select([_memory('keep'), _memory('rejected', user_review=False)])
    assert [ref.memory_id for ref in picked] == ['keep']


def test_reviewed_true_memory_still_qualifies():
    """Accepting a memory is not a reason to hide it; only rejection is."""
    picked = _select([_memory('accepted', user_review=True)])
    assert [ref.memory_id for ref in picked] == ['accepted']


def test_locked_memory_is_excluded():
    picked = _select([_memory('keep'), _memory('locked', is_locked=True)])
    assert [ref.memory_id for ref in picked] == ['keep']


def test_invalidated_memory_is_excluded():
    picked = _select([_memory('keep'), _memory('stale', invalid_at=DAY_START + timedelta(hours=2))])
    assert [ref.memory_id for ref in picked] == ['keep']


def test_superseded_memory_is_excluded():
    picked = _select([_memory('keep'), _memory('old', superseded_by='newer')])
    assert [ref.memory_id for ref in picked] == ['keep']


def test_empty_content_is_excluded():
    picked = _select([_memory('keep'), _memory('blank', content='   ')])
    assert [ref.memory_id for ref in picked] == ['keep']


def test_selection_is_capped_at_three():
    picked = _select([_memory(f'm{i}', capture_confidence=0.9) for i in range(10)])
    assert len(picked) == MEMORIES_LEARNED_LIMIT == 3


def test_ordering_prefers_confidence_then_veracity_then_newest():
    memories = [
        _memory('low', capture_confidence=0.1, created_at=DAY_START + timedelta(hours=9)),
        _memory('high', capture_confidence=0.9, created_at=DAY_START + timedelta(hours=1)),
        _memory('mid_old', capture_confidence=0.5, veracity=0.9, created_at=DAY_START + timedelta(hours=2)),
        _memory('mid_new', capture_confidence=0.5, veracity=0.9, created_at=DAY_START + timedelta(hours=8)),
    ]
    assert [ref.memory_id for ref in _select(memories, limit=4)] == ['high', 'mid_new', 'mid_old', 'low']


def test_memory_from_another_days_conversation_is_excluded():
    picked = _select([_memory('today'), _memory('other', conversation_id='c-not-summarised')])
    assert [ref.memory_id for ref in picked] == ['today']


def test_memory_without_a_conversation_falls_back_to_the_local_day_window():
    inside = _memory('manual', conversation_id=None, created_at=DAY_START + timedelta(hours=3))
    outside = _memory('yesterday', conversation_id=None, created_at=DAY_START - timedelta(hours=3))
    picked = _select([inside, outside])
    assert [ref.memory_id for ref in picked] == ['manual']


def test_window_fallback_is_inert_without_a_window():
    picked = _select(
        [_memory('manual', conversation_id=None)],
        window_start=None,
        window_end=None,
    )
    assert picked == []


def test_naive_timestamps_are_treated_as_utc():
    naive = _memory('naive', conversation_id=None, created_at=DAY_START.replace(tzinfo=None) + timedelta(hours=2))
    picked = _select([naive])
    assert [ref.memory_id for ref in picked] == ['naive']
    assert picked[0].captured_at.tzinfo is not None


def test_selected_ref_carries_identity_content_and_category():
    picked = _select([_memory('m1', category=MemoryCategory.manual, content='  drinks oat milk  ')])
    assert picked[0].memory_id == 'm1'
    assert picked[0].content == 'drinks oat milk'
    assert picked[0].category == 'manual'
    assert picked[0].captured_at == DAY_START + timedelta(hours=1)


def test_no_review_state_is_copied_into_the_summary():
    """Review state is read live from the memory so a vote on one device shows on the other."""
    assert set(LearnedMemoryRef.model_fields) == {'memory_id', 'content', 'category', 'captured_at'}


# --- read boundary ---------------------------------------------------------


def test_read_failure_degrades_to_no_card_not_no_summary():
    def _boom(*args, **kwargs):
        raise RuntimeError('canonical memory unavailable')

    assert (
        memories_learned_for_summary(
            'u1',
            conversation_ids=['c1'],
            window_start=DAY_START,
            window_end=DAY_END,
            read_memories=_boom,
        )
        == []
    )


def test_read_uses_one_bounded_newest_first_page():
    calls = []

    def _reader(uid, *, limit, offset):
        calls.append((uid, limit, offset))
        return [_memory('m1')]

    picked = memories_learned_for_summary(
        'u1',
        conversation_ids=['c1'],
        window_start=DAY_START,
        window_end=DAY_END,
        read_memories=_reader,
        scan_limit=50,
    )
    assert calls == [('u1', 50, 0)]
    assert [ref.memory_id for ref in picked] == ['m1']


# --- chat content block ----------------------------------------------------


def test_no_block_when_nothing_was_learned():
    assert memory_review_card_block('sum-1', date='2026-09-01', memories_learned=[]) is None


def test_block_shape():
    block = memory_review_card_block(
        'sum-1',
        date='2026-09-01',
        memories_learned=[LearnedMemoryRef(memory_id='m1', content='drinks oat milk', category='interesting')],
    )
    assert block == {
        'type': 'memoryReviewCard',
        'id': 'sum-1:memories',
        'summaryId': 'sum-1',
        'date': '2026-09-01',
        'items': [{'memoryId': 'm1', 'content': 'drinks oat milk', 'category': 'interesting'}],
    }


def test_block_accepts_the_stored_dict_projection():
    stored = LearnedMemoryRef(memory_id='m1', content='c', category='manual').model_dump(mode='json')
    block = memory_review_card_block('sum-1', date='2026-09-01', memories_learned=[stored])
    assert block['items'] == [{'memoryId': 'm1', 'content': 'c', 'category': 'manual'}]


def test_notification_payload_omits_content_blocks_when_absent():
    message = NotificationMessage(
        text='body', from_integration='false', type='day_summary', notification_type='daily_summary'
    )
    assert 'content_blocks' not in NotificationMessage.get_message_as_dict(message)


def test_notification_payload_encodes_blocks_as_fcm_safe_text():
    """FCM data is Dict[str, str]; a nested list fails the whole batch send."""
    block = memory_review_card_block(
        'sum-1', date='2026-09-01', memories_learned=[LearnedMemoryRef(memory_id='m1', content='c')]
    )
    message = NotificationMessage(
        text='body',
        from_integration='false',
        type='day_summary',
        notification_type='daily_summary',
        content_blocks=[block],
    )
    payload = NotificationMessage.get_message_as_dict(message)
    assert all(isinstance(value, str) for value in payload.values())
    import json

    assert json.loads(payload['content_blocks'])[0]['type'] == 'memoryReviewCard'


# --- response model round-trip --------------------------------------------


def test_response_model_round_trips_memories_learned():
    stored = {
        'id': 'sum-1',
        'date': '2026-09-01',
        'knowledge_nuggets': [{'insight': 'prose', 'conversation_id': 'c1'}],
        'memories_learned': [
            {
                'memory_id': 'm1',
                'content': 'drinks oat milk',
                'category': 'interesting',
                'captured_at': '2026-09-01T08:00:00+00:00',
            }
        ],
    }
    response = DailySummaryResponse.model_validate(stored)
    assert response.memories_learned[0].memory_id == 'm1'
    assert response.memories_learned[0].captured_at == datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
    dumped = response.model_dump(mode='json')
    assert dumped['memories_learned'][0]['memory_id'] == 'm1'
    # knowledge_nuggets stays untouched for older clients.
    assert dumped['knowledge_nuggets'][0]['insight'] == 'prose'


def test_response_model_defaults_to_empty_for_older_summaries():
    assert DailySummaryResponse.model_validate({'id': 'old', 'date': '2026-01-01'}).memories_learned == []


# --- day_summary message ---------------------------------------------------


def _drive_day_summary_endpoint(monkeypatch, memories_learned):
    """Run the real /v1/users/daily-summary-settings/test path and capture the push data."""
    sent = {}
    seen = {}
    monkeypatch.setattr(users_router, 'enforce_chat_quota', lambda *a, **k: None)
    monkeypatch.setattr(users_router.notification_db, 'get_user_time_zone', lambda uid: 'UTC')
    monkeypatch.setattr(users_router.notification_db, 'get_all_tokens', lambda uid: ['tok1'])
    monkeypatch.setattr(
        users_router.conversations_db, 'get_conversations', lambda *a, **k: [{'id': 'c1', 'is_locked': False}]
    )
    monkeypatch.setattr(users_router, 'deserialize_conversations', lambda data: [object()])
    # The endpoint owns the memory read and hands it to the generator; stub the
    # read at that seam and let the fake generator echo it back, so the test
    # covers the real read -> generate -> store -> block wiring.
    monkeypatch.setattr(users_router, '_memories_learned_payload', lambda *a, **k: memories_learned)

    def _fake_generate(*args, **kwargs):
        seen['memories_learned'] = kwargs.get('memories_learned')
        return {
            'id': 'sum-1',
            'headline': 'H',
            'day_emoji': 'X',
            'overview': 'You had 1 conversation today.',
            'memories_learned': kwargs.get('memories_learned') or [],
        }

    monkeypatch.setattr(users_router, 'generate_comprehensive_daily_summary', _fake_generate)
    monkeypatch.setattr(users_router.daily_summaries_db, 'create_daily_summary', lambda uid, data: 'sum-1')
    monkeypatch.setattr(
        users_router, 'send_notification', lambda uid, title, body, data, tokens=None: sent.update(data=data, body=body)
    )

    users_router.test_daily_summary(
        request=users_router.TestDailySummaryRequest(date='2026-09-01'),
        uid='u1',
        x_app_platform=None,
    )
    sent['generator_kwarg'] = seen.get('memories_learned')
    return sent


def test_day_summary_push_carries_the_block_when_memories_were_learned(monkeypatch):
    import json

    sent = _drive_day_summary_endpoint(
        monkeypatch,
        [{'memory_id': 'm1', 'content': 'drinks oat milk', 'category': 'interesting', 'captured_at': None}],
    )
    blocks = json.loads(sent['data']['content_blocks'])
    assert blocks == [
        {
            'type': 'memoryReviewCard',
            'id': 'sum-1:memories',
            'summaryId': 'sum-1',
            'date': '2026-09-01',
            'items': [{'memoryId': 'm1', 'content': 'drinks oat milk', 'category': 'interesting'}],
        }
    ]
    # Older clients read `text`; it must be exactly what it was before the block existed.
    assert sent['data']['text'] == 'You had 1 conversation today.'
    assert sent['body'] == 'You had 1 conversation today.'


def test_day_summary_push_omits_the_block_when_nothing_was_learned(monkeypatch):
    sent = _drive_day_summary_endpoint(monkeypatch, [])
    assert 'content_blocks' not in sent['data']
    assert sent['data']['text'] == 'You had 1 conversation today.'


def test_generator_receives_the_selection_from_the_endpoint(monkeypatch):
    """The endpoint owns the read; the generator must not reach into memory itself."""
    refs = [{'memory_id': 'm1', 'content': 'c', 'category': 'interesting', 'captured_at': None}]
    sent = _drive_day_summary_endpoint(monkeypatch, refs)
    assert sent['generator_kwarg'] == refs


def test_generate_comprehensive_daily_summary_does_not_read_memories_itself():
    """Regression: an in-generator memory read put a Firestore call behind every
    caller and every existing test of the daily summary, and cost 0.77s CPU in
    tests/unit/test_daily_summary_zero_coordinate_locations.py. The selection is
    a parameter, so the LLM summary builder stays free of the memory stack."""
    import inspect

    from utils.llm import external_integrations

    source = inspect.getsource(external_integrations)
    assert 'memories_learned_for_summary' not in source
    assert 'memory_service' not in source
    signature = inspect.signature(external_integrations.generate_comprehensive_daily_summary)
    assert signature.parameters['memories_learned'].default is None


def test_generator_defaults_to_no_card_without_a_selection():
    from utils.llm.external_integrations import _basic_daily_summary

    stats = DailySummaryDayStatsPayload()
    assert _basic_daily_summary('2026-09-01', 0, 0.0, [], [], stats)['memories_learned'] == []
    assert _basic_daily_summary('2026-09-01', 0, 0.0, [], [], stats, [{'memory_id': 'm1'}])['memories_learned'] == [
        {'memory_id': 'm1'}
    ]


def test_read_failure_reports_a_fallback_rather_than_swallowing_it(monkeypatch):
    """A missing card is a correctness change; silent ops is not allowed."""
    import utils.memory.learned_today as learned_today

    recorded = []
    monkeypatch.setattr(learned_today, 'record_fallback', lambda **kwargs: recorded.append(kwargs))

    def _boom(*args, **kwargs):
        raise RuntimeError('canonical memory unavailable')

    assert (
        learned_today.memories_learned_for_summary(
            'u1', conversation_ids=['c1'], window_start=DAY_START, window_end=DAY_END, read_memories=_boom
        )
        == []
    )
    assert len(recorded) == 1
    assert recorded[0]['component'] == 'daily_summary'
    assert recorded[0]['outcome'] == 'degraded'
