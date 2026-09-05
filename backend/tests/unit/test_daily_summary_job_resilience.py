"""Survivability contract for the daily-summary notifications job (#12530).

The job is a Cloud Run Job with a 600s task timeout serving tens of thousands
of users. Before this contract, an execution that ran out of wall clock was
killed mid-batch and the next execution restarted at the head, so the users
after the kill point were never reached on any run and produced no error of
their own. These tests execute the real job functions through the module's own
seams (fake Redis, injected clock, injected per-user worker).
"""

import asyncio
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Dict, Iterator, List, Tuple

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

# Imported for its side effect on import cost, not for its API: the job imports
# learned_today lazily, so without this the pydantic model build inside
# models.daily_summary_payload lands in the call phase of the test below and
# trips the fast-unit CPU duration guard. Paying it at collection keeps the
# guard measuring the test rather than a one-time import.
import utils.memory.learned_today  # noqa: F401

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _module(name: str, **attributes: Any) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


class FakeRedis:
    """Minimal Redis surface used by the job cursor."""

    def __init__(self) -> None:
        self.store: Dict[str, Any] = {}
        self.fail = False

    def get(self, key: str) -> Any:
        if self.fail:
            raise RuntimeError('redis down')
        return self.store.get(key)

    def set(self, key: str, value: Any, ex: Any = None) -> None:
        if self.fail:
            raise RuntimeError('redis down')
        self.store[key] = value

    def delete(self, key: str) -> None:
        if self.fail:
            raise RuntimeError('redis down')
        self.store.pop(key, None)


class FakeClock:
    """Deterministic replacement for ``time.monotonic`` inside the job."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class RecordedFallbacks:
    def __init__(self) -> None:
        self.events: List[Dict[str, str]] = []

    def __call__(self, **kwargs: Any) -> None:
        self.events.append({k: str(v) for k, v in kwargs.items() if k != 'log'})

    def reasons(self) -> List[str]:
        return [event['reason'] for event in self.events]


@contextmanager
def _loaded_job() -> Iterator[Tuple[ModuleType, ModuleType, FakeRedis, RecordedFallbacks]]:
    async def no_async_work(*_args: Any, **_kwargs: Any) -> None:
        return None

    def no_db_work(*_args: Any, **_kwargs: Any) -> List[Any]:
        return []

    fake_redis = FakeRedis()
    fallbacks = RecordedFallbacks()
    notification_db = _module(
        'database.notifications',
        get_users_for_daily_summary=no_db_work,
        get_users_token_in_timezones=no_db_work,
    )
    notification_message = type(
        'NotificationMessage',
        (),
        {
            '__init__': lambda self, **kwargs: self.__dict__.update(kwargs),
            'get_message_as_dict': staticmethod(lambda message: dict(message.__dict__)),
        },
    )
    stubs = {
        # utils.memory.learned_today -> models.memories -> database._client pulls
        # the Firestore SDK into the import graph; the job never touches it here.
        'database._client': AutoMockModule('database._client'),
        'database.conversations': _module('database.conversations', get_conversations=lambda *_a, **_k: []),
        'database.notifications': notification_db,
        'database.redis_db': _module(
            'database.redis_db',
            try_acquire_daily_summary_lock=lambda *_args: True,
            # Declines before the LLM call hand the day back instead of sitting on the 2h key.
            release_daily_summary_lock=lambda *_args: None,
            r=fake_redis,
        ),
        'models.notification_message': _module(
            'models.notification_message',
            NotificationMessage=notification_message,
        ),
        'utils.conversations.factory': _module('utils.conversations.factory', deserialize_conversation=lambda v: v),
        'utils.llm.external_integrations': _module(
            'utils.llm.external_integrations',
            generate_comprehensive_daily_summary=lambda *_a, **_k: {},
        ),
        'utils.notifications': _module(
            'utils.notifications',
            send_bulk_notification=no_async_work,
            send_notification=lambda *_a, **_k: None,
        ),
        'utils.observability.fallback': _module('utils.observability.fallback', record_fallback=fallbacks),
        'utils.webhooks': _module('utils.webhooks', day_summary_webhook=no_async_work),
        'database.daily_summaries': _module(
            'database.daily_summaries',
            get_daily_summary_by_date=lambda *_args: None,
            create_daily_summary=lambda *_args: 'summary-id',
        ),
    }

    with stub_modules(stubs):
        notifications = load_module_fresh(
            'utils.other.notifications',
            str(BACKEND_DIR / 'utils' / 'other' / 'notifications.py'),
        )
        yield notifications, notification_db, fake_redis, fallbacks


def _users(count: int, hour: int = 22) -> List[Tuple[str, List[str], str]]:
    return [(f'uid-{i:02d}', [f'token-{i:02d}'], 'UTC') for i in range(count)]


# --------------------------------------------------------------- per-user isolation


def test_one_failing_user_does_not_abort_the_rest_of_the_group() -> None:
    with _loaded_job() as (notifications, _db, _redis, _fallbacks):
        served: List[str] = []

        def worker(user: Tuple[Any, ...]) -> None:
            served.append(user[0])
            if user[0] == 'uid-02':
                raise RuntimeError('Error code: 400 - context_length_exceeded')

        notifications._send_summary_notification = worker
        stats = notifications.DailySummaryJobStats()

        finished = asyncio.run(notifications._send_bulk_summary_notification(_users(20), stats=stats, target_hour=22))

        assert finished is True
        assert len(served) == 20, 'every user in the group must still be attempted'
        assert stats.attempted == 20
        assert stats.failed == 1
        assert stats.succeeded == 19


def test_per_user_budget_exceeded_is_recorded_and_skipped() -> None:
    with _loaded_job() as (notifications, _db, _redis, fallbacks):
        notifications.DAILY_SUMMARY_USER_BUDGET_SECONDS = 0.05
        release = threading.Event()
        served: List[str] = []

        def worker(user: Tuple[Any, ...]) -> None:
            served.append(user[0])
            if user[0] == 'uid-01':
                assert release.wait(timeout=5)

        notifications._send_summary_notification = worker
        stats = notifications.DailySummaryJobStats()
        try:
            finished = asyncio.run(
                notifications._send_bulk_summary_notification(_users(4), stats=stats, target_hour=22)
            )
        finally:
            release.set()

        assert finished is True
        assert stats.timed_out == 1
        assert stats.succeeded == 3, 'the slow account must not cost its batch-mates their summary'
        assert 'timeout' in fallbacks.reasons()


def test_failing_hour_group_does_not_abort_the_remaining_groups() -> None:
    with _loaded_job() as (notifications, notification_db, _redis, _fallbacks):
        notifications._get_timezones_grouped_by_hour = lambda: {21: ['UTC'], 22: ['Etc/GMT+1']}
        served: List[str] = []

        def read_users(timezones: List[str], target_hour: int) -> List[Any]:
            if target_hour == 21:
                raise RuntimeError('firestore unavailable')
            return _users(3, hour=22)

        notification_db.get_users_for_daily_summary = read_users
        notifications._send_summary_notification = lambda user: served.append(user[0])

        outcome = asyncio.run(notifications.send_daily_summary_notification())
        assert outcome.ok is False
        assert 'firestore unavailable' in (outcome.error_text or '')
        assert served == ['uid-00', 'uid-01', 'uid-02'], 'hour 22 must still be served after hour 21 failed'


# ------------------------------------------------------------------ job budget


def test_job_budget_checkpoints_the_unfinished_tail() -> None:
    with _loaded_job() as (notifications, _db, redis, fallbacks):
        clock = FakeClock()
        notifications.monotonic = clock
        notifications.DAILY_SUMMARY_JOB_BUDGET_SECONDS = 100.0
        served: List[str] = []

        def worker(user: Tuple[Any, ...]) -> None:
            served.append(user[0])
            clock.advance(10.0)

        notifications._send_summary_notification = worker
        stats = notifications.DailySummaryJobStats()

        finished = asyncio.run(
            notifications._send_bulk_summary_notification(
                _users(17),
                deadline=clock() + notifications.DAILY_SUMMARY_JOB_BUDGET_SECONDS,
                stats=stats,
                target_hour=22,
                cursor_key='cursor-key',
            )
        )

        assert finished is False
        assert stats.succeeded == 16 and stats.skipped_for_budget == 1
        assert served[-1] == 'uid-15'
        cursor = notifications.summary_budget.read_job_cursor('cursor-key')
        assert cursor == {'hour': 22, 'uid': 'uid-16'}, 'the unfinished tail must be checkpointed'
        assert 'timeout' in fallbacks.reasons()


def test_next_execution_resumes_at_the_checkpointed_tail() -> None:
    with _loaded_job() as (notifications, notification_db, redis, _fallbacks):
        notifications._get_timezones_grouped_by_hour = lambda: {22: ['UTC']}
        notification_db.get_users_for_daily_summary = lambda _tz, _hour: _users(9)
        notifications.summary_budget.write_job_cursor(
            notifications.summary_budget.job_cursor_key(),
            {'hour': 22, 'uid': 'uid-08'},
        )
        served: List[str] = []
        notifications._send_summary_notification = lambda user: served.append(user[0])

        asyncio.run(notifications.send_daily_summary_notification())

        assert served[0] == 'uid-08', 'the run must start at the tail the previous run could not reach'
        assert sorted(served) == [f'uid-{i:02d}' for i in range(9)], 'rotation still covers the head'
        assert redis.store == {}, 'a complete pass clears the checkpoint'


def test_a_partially_read_hour_group_does_not_clear_the_checkpoint() -> None:
    """A dropped timezone chunk is a partial enumeration. Finishing the run as if
    it were complete retires users the job never even listed."""
    with _loaded_job() as (notifications, notification_db, redis, fallbacks):
        notifications._get_timezones_grouped_by_hour = lambda: {22: [f'tz-{i:02d}' for i in range(40)]}
        served: List[str] = []

        def read_users(timezones: List[str], _target_hour: int) -> List[Any]:
            if 'tz-30' in timezones:
                raise RuntimeError('firestore unavailable')
            return _users(3)

        notification_db.get_users_for_daily_summary = read_users
        notifications._send_summary_notification = lambda user: served.append(user[0])

        asyncio.run(notifications.send_daily_summary_notification())

        assert served == ['uid-00', 'uid-01', 'uid-02'], 'the chunk that did read is still served'
        assert redis.store, 'a partial read must leave the run resumable'


def test_the_checkpoint_key_survives_the_hour_rollover() -> None:
    """The key used to carry the UTC hour, so the execution that wrote the tail
    and the execution that should resume it never shared a key."""
    from utils.other import daily_summary_budget

    assert daily_summary_budget.job_cursor_key() == daily_summary_budget.job_cursor_key()
    assert 'T' not in daily_summary_budget.job_cursor_key()


def test_job_end_summary_line_reports_the_counters() -> None:
    with _loaded_job() as (notifications, _db, _redis, _fallbacks):
        stats = notifications.DailySummaryJobStats(
            groups_attempted=2, groups_failed=1, attempted=10, succeeded=8, failed=1, timed_out=1, skipped_for_budget=5
        )
        line = stats.as_log()
        for fragment in ('attempted=10', 'succeeded=8', 'failed=1', 'timed_out=1', 'skipped_for_budget=5'):
            assert fragment in line


# ---------------------------------------------------------------- input bound


class _Conversation:
    def __init__(self, index: int, size: int) -> None:
        self.index = index
        self.size = size
        self.started_at = datetime(2026, 8, 23, tzinfo=timezone.utc) + timedelta(hours=index)


def _render(conversation: _Conversation) -> str:
    return 'x' * conversation.size


def test_truncation_bound_keeps_the_most_recent_conversations() -> None:
    from utils.other import daily_summary_budget

    conversations = [_Conversation(i, 100) for i in range(10)]
    bounded = daily_summary_budget.select_conversations_within_budget(conversations, 350, render=_render)

    assert bounded.truncated is True
    assert bounded.dropped == 7
    assert [c.index for c in bounded.conversations] == [7, 8, 9], 'most recent first, chronological order preserved'
    assert bounded.rendered_chars <= 350


def test_truncation_bound_is_a_no_op_under_the_cap() -> None:
    from utils.other import daily_summary_budget

    conversations = [_Conversation(i, 10) for i in range(5)]
    bounded = daily_summary_budget.select_conversations_within_budget(conversations, 10_000, render=_render)

    assert bounded.truncated is False
    assert [c.index for c in bounded.conversations] == [0, 1, 2, 3, 4]


def test_truncation_bound_always_keeps_one_conversation() -> None:
    from utils.other import daily_summary_budget

    conversations = [_Conversation(0, 1_000_000), _Conversation(1, 1_000_000)]
    bounded = daily_summary_budget.select_conversations_within_budget(conversations, 100, render=_render)

    assert len(bounded.conversations) == 1
    assert bounded.conversations[0].index == 1, 'the single kept conversation is the most recent one'
    assert bounded.dropped == 1


def test_a_nonpositive_budget_falls_back_to_the_bound_not_past_it() -> None:
    """Returning the whole day for max_chars <= 0 removed the only protection
    against the context overflow this bound exists for."""
    from utils.other import daily_summary_budget

    conversations = [_Conversation(i, 100) for i in range(10)]
    bounded = daily_summary_budget.select_conversations_within_budget(conversations, 0, render=_render)

    assert bounded.rendered_chars <= daily_summary_budget.DEFAULT_MAX_HISTORY_CHARS
    assert len(bounded.conversations) == 10, 'a small day still fits under the fallback bound'

    bounded = daily_summary_budget.select_conversations_within_budget(
        [_Conversation(i, 200_000) for i in range(5)], -1, render=_render
    )
    assert bounded.truncated is True, 'the fallback bound is applied, not skipped'


def test_an_unrenderable_conversation_is_dropped_and_counted() -> None:
    """Keeping it at zero cost only moved the failure into the summary render,
    where it costs the whole recap instead of one conversation."""
    from utils.other import daily_summary_budget

    def render(conversation: _Conversation) -> str:
        if conversation.index == 1:
            raise ValueError('unrenderable segment')
        return 'x' * conversation.size

    conversations = [_Conversation(i, 10) for i in range(3)]
    bounded = daily_summary_budget.select_conversations_within_budget(conversations, 10_000, render=render)

    assert [c.index for c in bounded.conversations] == [0, 2]
    assert bounded.dropped == 1


def test_a_renderer_that_fails_for_everything_still_hands_the_day_over() -> None:
    """If nothing renders the fault is the renderer, not the conversations, and
    dropping the whole day would turn that into a silently missing recap."""
    from utils.other import daily_summary_budget

    def render(_conversation: _Conversation) -> str:
        raise ImportError('renderer unavailable')

    conversations = [_Conversation(i, 10) for i in range(3)]
    bounded = daily_summary_budget.select_conversations_within_budget(conversations, 10_000, render=render)

    assert bounded.conversations == conversations
    assert bounded.truncated is False


def test_truncation_bound_tolerates_naive_and_missing_timestamps() -> None:
    from utils.other import daily_summary_budget

    naive = _Conversation(1, 10)
    naive.started_at = datetime(2026, 8, 23, 5)
    undated = _Conversation(2, 10)
    undated.started_at = None
    bounded = daily_summary_budget.select_conversations_within_budget([naive, undated], 10_000, render=_render)

    assert len(bounded.conversations) == 2


# ------------------------------------------------------------- cursor helpers


def test_rotate_to_starts_at_the_checkpoint_and_wraps() -> None:
    from utils.other import daily_summary_budget

    assert daily_summary_budget.rotate_to([0, 1, 2, 3], 2) == [2, 3, 0, 1]
    assert daily_summary_budget.rotate_to([0, 1, 2, 3], None) == [0, 1, 2, 3]
    assert daily_summary_budget.rotate_to([0, 1, 2, 3], 9) == [0, 1, 2, 3], 'a stale cursor must not strand anyone'


def test_cursor_helpers_are_fail_soft_when_redis_is_down() -> None:
    with _loaded_job() as (notifications, _db, redis, _fallbacks):
        budget = notifications.summary_budget
        redis.fail = True

        assert budget.read_job_cursor('k') is None
        budget.write_job_cursor('k', {'hour': 1, 'uid': 'u'})
        budget.clear_job_cursor('k')


def test_job_survives_a_redis_outage_end_to_end() -> None:
    with _loaded_job() as (notifications, notification_db, redis, _fallbacks):
        redis.fail = True
        notifications._get_timezones_grouped_by_hour = lambda: {22: ['UTC']}
        notification_db.get_users_for_daily_summary = lambda _tz, _hour: _users(3)
        served: List[str] = []
        notifications._send_summary_notification = lambda user: served.append(user[0])

        outcome = asyncio.run(notifications.send_daily_summary_notification())
        assert outcome.ok is True
        assert len(served) == 3, 'losing the checkpoint costs a re-walk, never a summary'


# ------------------------------------------------- memory review card on the real send


class _FakeConversation:
    def __init__(self) -> None:
        self.id = 'convo-1'
        self.discarded = False
        self.transcript_segments = ['segment']
        self.started_at = datetime(2026, 8, 23, 9, tzinfo=timezone.utc)
        # The pre-LLM summary-content gate (flip-review F-12) declines a day
        # whose conversations carry titles only; these tests pin the send path,
        # so the fixture carries body content.
        self.apps_results: list = []
        self.structured = SimpleNamespace(overview='You shipped the thing.')


@contextmanager
def _loaded_send_path(
    memories_learned: List[Dict[str, Any]],
) -> Iterator[Tuple[ModuleType, List[Any], Dict[str, Any]]]:
    """Load the job with the real NotificationMessage so FCM serialization is exercised.

    The generator stub behaves like the real one: ``memories_learned`` is a
    *parameter* it echoes into the summary, never something it reads for itself.
    A stub that returned the refs regardless of what it was passed would pass
    whether or not the scheduled path selects them — which is exactly how the
    card shipped dead.
    """

    async def no_async_work(*_args: Any, **_kwargs: Any) -> None:
        return None

    sends: List[Any] = []
    seen: Dict[str, Any] = {}
    summary_data = {
        'day_emoji': '📅',
        'headline': 'A good day',
        'overview': 'You shipped the thing.',
    }

    def generate(*args: Any, memories_learned: Any = None, **_kwargs: Any) -> Dict[str, Any]:
        seen['generator_args'] = args
        seen['generator_kwarg'] = memories_learned
        return {**summary_data, 'memories_learned': list(memories_learned or [])}

    def select_payload(uid: str, conversations: Any, window_start: Any, window_end: Any) -> List[Dict[str, Any]]:
        seen['selection_args'] = (uid, [c.id for c in conversations], window_start, window_end)
        return memories_learned

    stubs = {
        'database._client': AutoMockModule('database._client'),
        'database.conversations': _module(
            'database.conversations',
            get_conversations=lambda *_a, **_k: [{'is_locked': False}],
        ),
        'database.notifications': _module(
            'database.notifications',
            get_users_for_daily_summary=lambda *_a, **_k: [],
            get_users_token_in_timezones=lambda *_a, **_k: [],
        ),
        'database.redis_db': _module(
            'database.redis_db',
            try_acquire_daily_summary_lock=lambda *_args: True,
            # Declines before the LLM call hand the day back instead of sitting on the 2h key.
            release_daily_summary_lock=lambda *_args: None,
            r=FakeRedis(),
        ),
        'utils.conversations.factory': _module(
            'utils.conversations.factory', deserialize_conversation=lambda _v: _FakeConversation()
        ),
        'utils.conversations.render': _module('utils.conversations.render', conversations_to_string=lambda _c: 'text'),
        'utils.llm.external_integrations': _module(
            'utils.llm.external_integrations',
            generate_comprehensive_daily_summary=generate,
        ),
        'utils.notifications': _module(
            'utils.notifications',
            send_bulk_notification=no_async_work,
            send_notification=lambda *args, **kwargs: sends.append((args, kwargs)),
        ),
        'utils.observability.fallback': _module('utils.observability.fallback', record_fallback=RecordedFallbacks()),
        'utils.webhooks': _module('utils.webhooks', day_summary_webhook=no_async_work),
        'database.daily_summaries': _module(
            'database.daily_summaries',
            get_daily_summary_by_date=lambda *_args: None,
            create_daily_summary=lambda *_args: 'summary-id',
        ),
    }
    with stub_modules(stubs):
        notifications = load_module_fresh(
            'utils.other.notifications',
            str(BACKEND_DIR / 'utils' / 'other' / 'notifications.py'),
        )
        # The selection itself is a Firestore read; the job's obligation under
        # test is that it makes the call and threads the result through.
        notifications.memories_learned_payload = select_payload
        yield notifications, sends, seen


_MEMORY = {'memory_id': 'mem-1', 'content': 'Ships on Tuesdays', 'category': 'work'}


def test_scheduled_send_carries_the_memory_review_card() -> None:
    """Regression (#12635 review): the scheduled job called the generator without
    ``memories_learned``, so the parameter kept its None default, the summary's
    list was always empty, and the block was never attached on the only path real
    users receive. The card was dead in production as shipped."""
    import json

    with _loaded_send_path([_MEMORY]) as (notifications, sends, seen):
        notifications._send_summary_notification(('uid-00', ['token-00']))

        assert seen['generator_kwarg'] == [_MEMORY], 'the scheduled path must select the day\'s memories'
        assert seen['selection_args'][0] == 'uid-00'
        assert seen['selection_args'][1] == ['convo-1'], 'selection is scoped to the bounded conversation set'
        assert len(sends) == 1
        args, _kwargs = sends[0]
        payload = args[3]
        blocks = json.loads(payload['content_blocks'])
        assert blocks[0]['type'] == 'memoryReviewCard'
        assert blocks[0]['summaryId'] == 'summary-id'
        assert blocks[0]['items'] == [{'memoryId': 'mem-1', 'content': 'Ships on Tuesdays', 'category': 'work'}]
        assert payload['text'] == 'You shipped the thing.'
        assert args[2] == 'You shipped the thing.'


def test_scheduled_send_omits_the_card_when_no_memories_were_learned() -> None:
    with _loaded_send_path([]) as (notifications, sends, _seen):
        notifications._send_summary_notification(('uid-00', ['token-00']))

        assert len(sends) == 1
        args, _kwargs = sends[0]
        payload = args[3]
        assert 'content_blocks' not in payload, 'no card is sent when the day produced nothing to review'
        assert payload['text'] == 'You shipped the thing.', 'the message text is identical either way'
        assert args[2] == 'You shipped the thing.'


def test_an_oversized_card_costs_the_card_not_the_notification() -> None:
    """FCM rejects the whole message past 4KB of data, so an unbounded card would
    take the recap down with it rather than degrade."""
    huge = [{'memory_id': f'mem-{i}', 'content': 'x' * 900, 'category': 'work'} for i in range(6)]
    with _loaded_send_path(huge) as (notifications, sends, _seen):
        notifications._send_summary_notification(('uid-00', ['token-00']))

        assert len(sends) == 1, 'the summary must still be sent'
        payload = sends[0][0][3]
        assert 'content_blocks' not in payload
        assert payload['text'] == 'You shipped the thing.'
