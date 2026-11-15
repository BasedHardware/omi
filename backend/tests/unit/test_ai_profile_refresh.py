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

    def write(self, uid, profile):
        self.writes.append(profile)
        self.profile = profile
        return profile


class FakeLock:
    def __init__(self, acquired=True, raises=False):
        self.acquired = acquired
        self.raises = raises
        self.ttls: list[int] = []
        self.released = 0

    def acquire(self, uid, ttl=3600):
        if self.raises:
            raise ConnectionError('redis down')
        self.ttls.append(ttl)
        return self.acquired

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
    monkeypatch.setattr(refresh.users_db, 'write_ai_user_profile', store.write)
    monkeypatch.setattr(refresh.redis_db, 'try_acquire_ai_profile_refresh_lock', lock.acquire)
    monkeypatch.setattr(refresh.redis_db, 'release_ai_profile_refresh_lock', lock.release)
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
    # The lock is kept for its TTL, so a failure or a burst of conversations cannot loop.
    assert lock.released == 0


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


def test_refresh_now_ignores_cadence_and_releases_lock(wired):
    store, lock, _ = wired
    store.profile = {'profile_text': 'x', 'refreshed_at': datetime.now(timezone.utc).isoformat()}

    assert refresh.refresh_now(UID)['source'] == 'backend'
    assert lock.ttls == [600] and lock.released == 1


def test_refresh_now_reports_in_progress(wired):
    _, lock, _ = wired
    lock.acquired = False
    with pytest.raises(refresh.RefreshError) as exc:
        refresh.refresh_now(UID)
    assert exc.value.code == 'ai_profile_refresh_in_progress'


def test_collect_sources_formats_lines_and_survives_a_failed_source(monkeypatch):
    monkeypatch.setattr(refresh, 'get_prompt_memories', lambda uid: ('David', '\n- likes tea\n\n- works on Omi\n'))
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

    assert sources.memories == ['- likes tea', '- works on Omi']
    assert sources.tasks == ['[todo/high] ship profile', '[done/medium] old']
    assert sources.goals == ['Run 100km (25% complete)', 'Read (0% complete)']
    assert sources.conversations == ['Standup: Planned the week']
    assert sources.messages == []
