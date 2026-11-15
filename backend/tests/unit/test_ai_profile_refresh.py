"""Backend-owned AI user profile: cadence, admission, source selection and the write."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from utils import ai_profile_refresh as refresh
from utils.llm.ai_user_profile import ProfileSynthesis

UID = 'uid-ai-profile-refresh'
NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


class FakeStore:
    def __init__(self, profile=None):
        self.profile = profile
        self.writes: list[dict] = []

    def get(self, uid):
        return self.profile

    def write_if_unchanged(self, uid, expected_text, profile):
        if str((self.profile or {}).get('profile_text') or '').strip() != expected_text:
            return False
        self.writes.append(profile)
        self.profile = profile
        return True


class FakeLock:
    def __init__(self, acquired=True, raises=False, cooldown_free=True):
        self.acquired = acquired
        self.raises = raises
        self.cooldown_free = cooldown_free
        self.ttls: list[int] = []
        self.cooldown_ttls: list[int] = []
        self.released = 0

    def acquire(self, uid, ttl=600):
        if self.raises:
            raise ConnectionError('redis down')
        self.ttls.append(ttl)
        return self.acquired

    def cooldown(self, uid, ttl=3600):
        if self.raises:
            raise ConnectionError('redis down')
        self.cooldown_ttls.append(ttl)
        return self.cooldown_free

    def release(self, uid):
        self.released += 1


@pytest.fixture
def wired(monkeypatch):
    store = FakeStore()
    lock = FakeLock()
    calls: dict = {}

    def fake_synthesize(uid, sources, **kwargs):
        calls['sources'] = sources
        calls['kwargs'] = kwargs
        return ProfileSynthesis(profile_text='- User is an engineer', data_sources_used=['memories'], item_count=3)

    monkeypatch.setattr(refresh.users_db, 'get_ai_user_profile', store.get)
    monkeypatch.setattr(refresh.users_db, 'get_ai_user_profile_fresh', store.get)
    monkeypatch.setattr(refresh.users_db, 'write_ai_user_profile_if_unchanged', store.write_if_unchanged)
    monkeypatch.setattr(refresh.redis_db, 'try_acquire_ai_profile_refresh_lock', lock.acquire)
    monkeypatch.setattr(refresh.redis_db, 'release_ai_profile_refresh_lock', lock.release)
    monkeypatch.setattr(refresh.redis_db, 'try_acquire_ai_profile_auto_cooldown', lock.cooldown)
    monkeypatch.setattr(refresh, 'generated_compute_allowed', lambda uid, feature: True)
    monkeypatch.setattr(
        refresh,
        'collect_sources',
        lambda uid, now=None: refresh.profile_llm.ProfileSources(memories=['[work] engineer'], goals=['ship', 'run']),
    )
    monkeypatch.setattr(refresh.profile_llm, 'synthesize_ai_user_profile', fake_synthesize)
    monkeypatch.delenv(refresh.KILL_SWITCH_ENV, raising=False)
    return store, lock, calls


def test_is_stale_uses_backend_refresh_stamp_only():
    assert refresh.is_stale(None, NOW)
    # A client-generated or user-edited profile has no backend stamp: due for a refresh.
    assert refresh.is_stale({'profile_text': 'x', 'generated_at': NOW.isoformat()}, NOW)
    assert not refresh.is_stale({'refreshed_at': (NOW - timedelta(hours=2)).isoformat()}, NOW)
    assert refresh.is_stale({'refreshed_at': (NOW - timedelta(hours=21)).isoformat()}, NOW)
    assert refresh.is_stale({'refreshed_at': 'not-a-time'}, NOW)


def test_stale_profile_is_regenerated_and_written(wired):
    store, lock, calls = wired
    store.profile = {'profile_text': '- old fact', 'source': 'client'}

    assert refresh.refresh_if_stale(UID) == 'written'

    written = store.writes[-1]
    assert written['profile_text'] == '- User is an engineer'
    assert written['source'] == 'backend'
    assert written['data_sources_used'] == 3
    assert written['refreshed_at'] == written['generated_at']
    assert calls['kwargs'] == {'past_profiles': ['- old fact'], 'latest_past_user_edited': False}
    # The hourly cooldown stays (no retry loop); the in-progress lock is released so an
    # explicit Generate Now is not blocked by a finished automatic run.
    assert lock.cooldown_ttls == [3600] and lock.ttls == [600] and lock.released == 1


def test_user_edit_is_merged_as_correction(wired):
    store, _, calls = wired
    store.profile = {'profile_text': '- User lives in Hanoi', 'source': 'user_edit'}

    assert refresh.refresh_if_stale(UID) == 'written'
    assert calls['kwargs']['latest_past_user_edited'] is True
    assert calls['kwargs']['past_profiles'] == ['- User lives in Hanoi']


def test_fresh_profile_skips_without_lock_or_spend(wired):
    store, lock, calls = wired
    store.profile = {'profile_text': 'x', 'refreshed_at': datetime.now(timezone.utc).isoformat()}

    assert refresh.refresh_if_stale(UID) == 'fresh'
    assert lock.ttls == [] and 'kwargs' not in calls and store.writes == []


@pytest.mark.parametrize(
    'setup, outcome',
    [
        (lambda m, lock: setattr(lock, 'cooldown_free', False), 'cooldown'),
        (lambda m, lock: setattr(lock, 'acquired', False), 'locked'),
        (lambda m, lock: setattr(lock, 'raises', True), 'lock_unavailable'),
        (lambda m, lock: m.setattr(refresh, 'generated_compute_allowed', lambda uid, feature: False), 'compute_denied'),
        (lambda m, lock: m.setenv(refresh.KILL_SWITCH_ENV, 'false'), 'disabled'),
    ],
)
def test_automatic_refresh_spends_nothing_when_not_admitted(wired, monkeypatch, setup, outcome):
    store, lock, calls = wired
    setup(monkeypatch, lock)

    assert refresh.refresh_if_stale(UID) == outcome
    assert store.writes == [] and 'kwargs' not in calls


def test_edit_during_synthesis_wins(wired, monkeypatch):
    store, _, _ = wired
    store.profile = {'profile_text': '- old', 'source': 'backend'}
    original = refresh.profile_llm.synthesize_ai_user_profile

    def edit_then_synthesize(uid, sources, **kwargs):
        store.profile = {'profile_text': '- user fixed this', 'source': 'user_edit'}
        return original(uid, sources, **kwargs)

    monkeypatch.setattr(refresh.profile_llm, 'synthesize_ai_user_profile', edit_then_synthesize)

    assert refresh.refresh_if_stale(UID) == 'superseded'
    assert store.writes == []
    assert store.profile['profile_text'] == '- user fixed this'


def test_failures_never_write_or_raise(wired, monkeypatch):
    store, _, _ = wired
    monkeypatch.setattr(refresh.profile_llm, 'synthesize_ai_user_profile', lambda *a, **k: None)
    assert refresh.refresh_if_stale(UID) == 'ai_profile_synthesis_failed'

    monkeypatch.setattr(refresh, 'collect_sources', lambda uid, now=None: refresh.profile_llm.ProfileSources())
    assert refresh.refresh_if_stale(UID) == 'ai_profile_insufficient_data'

    monkeypatch.setattr(refresh, 'collect_sources', lambda uid, now=None: 1 / 0)
    assert refresh.refresh_if_stale(UID) == 'error'
    assert store.writes == []


def test_refresh_now_ignores_cadence_and_cooldown_and_releases_lock(wired):
    store, lock, _ = wired
    lock.cooldown_free = False
    store.profile = {'profile_text': 'x', 'refreshed_at': datetime.now(timezone.utc).isoformat()}

    assert refresh.refresh_now(UID)['source'] == 'backend'
    assert lock.ttls == [600] and lock.released == 1 and lock.cooldown_ttls == []


def test_refresh_now_fails_closed_without_redis(wired):
    store, lock, calls = wired
    lock.raises = True
    with pytest.raises(refresh.RefreshError) as exc:
        refresh.refresh_now(UID)
    assert exc.value.code == 'ai_profile_refresh_unavailable'
    assert 'kwargs' not in calls and store.writes == []


def test_failed_automatic_refresh_releases_in_progress_lock(wired, monkeypatch):
    _, lock, _ = wired
    monkeypatch.setattr(refresh.profile_llm, 'synthesize_ai_user_profile', lambda *a, **k: None)
    assert refresh.refresh_if_stale(UID) == 'ai_profile_synthesis_failed'
    assert lock.released == 1


def test_schedule_refresh_is_bounded_per_process(monkeypatch):
    monkeypatch.delenv(refresh.KILL_SWITCH_ENV, raising=False)
    queued: list = []
    monkeypatch.setattr(refresh, 'submit_with_context', lambda executor, fn, uid: queued.append((fn, uid)))
    monkeypatch.setattr(refresh, '_automatic_slots', refresh.threading.BoundedSemaphore(2))

    stale = {'profile_text': 'x'}
    assert refresh.schedule_refresh('a', stale, known=True)
    assert refresh.schedule_refresh('b', None, known=True)
    assert not refresh.schedule_refresh('c', stale, known=True)  # both slots busy
    fresh = {'refreshed_at': datetime.now(timezone.utc).isoformat()}
    assert not refresh.schedule_refresh('d', fresh, known=True)
    assert [uid for _, uid in queued] == ['a', 'b']

    # A finished run frees its slot.
    monkeypatch.setattr(refresh, 'refresh_if_stale', lambda uid: 'written')
    queued[0][0]('a')
    assert refresh.schedule_refresh('c', stale, known=True)

    monkeypatch.setenv(refresh.KILL_SWITCH_ENV, 'off')
    assert not refresh.schedule_refresh('e', stale, known=True)


def test_schedule_refresh_releases_slot_when_submit_fails(monkeypatch):
    monkeypatch.delenv(refresh.KILL_SWITCH_ENV, raising=False)
    slots = refresh.threading.BoundedSemaphore(1)
    monkeypatch.setattr(refresh, '_automatic_slots', slots)

    def saturated(*args):
        raise RuntimeError('executor saturated')

    monkeypatch.setattr(refresh, 'submit_with_context', saturated)
    assert not refresh.schedule_refresh('a', None, known=True)
    assert slots.acquire(blocking=False)


def test_refresh_now_reports_in_progress(wired):
    _, lock, _ = wired
    lock.acquired = False
    with pytest.raises(refresh.RefreshError) as exc:
        refresh.refresh_now(UID)
    assert exc.value.code == 'ai_profile_refresh_in_progress'


def test_collect_sources_formats_lines_and_survives_a_failed_source(monkeypatch):
    from types import SimpleNamespace

    class FakeMemories:
        def __init__(self, db_client=None):
            pass

        def read(self, uid, limit):
            assert limit == 100
            return [
                SimpleNamespace(category=SimpleNamespace(value='interesting'), content='likes tea'),
                SimpleNamespace(category='system', content='works on Omi'),
                SimpleNamespace(category='system', content='hidden'),
                SimpleNamespace(category='system', content=''),
            ]

    monkeypatch.setattr(refresh, 'MemoryService', FakeMemories)
    monkeypatch.setattr(refresh, 'get_firestore_client', lambda: object())
    monkeypatch.setattr(refresh, 'is_prompt_memory_visible', lambda memory: memory.content != 'hidden')
    monkeypatch.setattr(
        refresh.action_items_db,
        'get_action_items',
        lambda uid, limit: [
            {'description': 'ship profile', 'completed': False, 'priority': 'high'},
            {'description': 'old', 'completed': True},
            {'description': ''},
        ],
    )
    monkeypatch.setattr(
        refresh.goals_db,
        'get_all_goals',
        lambda uid: [{'title': 'Run 100km', 'current_value': 25, 'target_value': 100}, {'title': 'Read'}],
    )

    def conversations(uid, **kwargs):
        assert kwargs['start_date'] == NOW - timedelta(days=7)
        assert kwargs['end_date'] == NOW
        assert kwargs['limit'] == 20
        return [{'structured': {'title': 'Standup', 'overview': 'Planned the week'}}, {'structured': {}}]

    monkeypatch.setattr(refresh.conversations_db, 'get_conversations_without_photos', conversations)
    monkeypatch.setattr(refresh.chat_db, 'get_messages', lambda uid, limit: 1 / 0)

    sources = refresh.collect_sources(UID, NOW)

    assert sources.memories == ['[interesting] likes tea', '[system] works on Omi']
    assert sources.tasks == ['[todo/high] ship profile', '[done/medium] old']
    assert sources.goals == ['Run 100km (25% complete)', 'Read (0% complete)']
    assert sources.conversations == ['Standup: Planned the week']
    assert sources.messages == []


@pytest.mark.parametrize(
    'stored, expected, written',
    [
        ({'profile_text': '- old'}, '- old', True),
        ({'profile_text': '- user fixed this', 'source': 'user_edit'}, '- old', False),
        (None, '', False),
    ],
)
def test_compare_and_write_is_transactional(monkeypatch, stored, expected, written):
    import database.users as users_db
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    rows = {} if stored is None else {('users', UID): {'name': 'x', 'ai_user_profile': stored}}
    client = StrictFirestore(rows)
    monkeypatch.setattr(users_db, 'get_firestore_client', lambda: client)
    profile = {'profile_text': '- new', 'source': 'backend'}

    assert users_db.write_ai_user_profile_if_unchanged(UID, expected, profile) is written
    after = client.rows.get(('users', UID))
    if written:
        assert after['ai_user_profile'] == profile and after['name'] == 'x'
    else:
        assert after == (None if stored is None else {'name': 'x', 'ai_user_profile': stored})
