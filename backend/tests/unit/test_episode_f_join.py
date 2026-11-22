"""Episode-join variant F: recorded-time uncertain joins settle with full-transcript Jev behind a flag."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from config import episodes as config
from database.episode_timeline import recorded_candidates
from database import episode_timeline
from database import episodes as episodes_db
from database.episodes import EpisodeConflict
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils import omi_flags
from utils.conversations.recorded_time import conversation_span
from utils.episodes import f_join, incremental, metrics, policy, service
from utils.episodes.service import Collaborators, MomentInput

UID = 'uid-f-join'
T0 = datetime(2026, 11, 5, 10, 0, tzinfo=timezone.utc)
FIRST = (
    'okay lunch at the noodle place works for both of us today. the table is booked for two people at noon. '
    'we can walk over now and grab a coffee on the way back to the office after we are done eating'
)
SECOND = (
    'hi this is the dentist office calling about your cleaning appointment tomorrow morning. '
    'please call us back to confirm the time or we will need to give the slot to another patient soon'
)


class FakeModel:
    def __init__(self):
        self.calls = []

    def __call__(self, uid, messages):
        import json

        self.calls.append(messages)
        return SimpleNamespace(
            content=json.dumps({'title': 'T', 'bullets': ['x']}),
            usage_metadata={'input_tokens': 10, 'output_tokens': 5},
        )


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv('EPISODE_RECORDED_TIME_ENABLED', 'true')
    for name in (
        config.EPISODES_ENABLED_ENV,
        config.EPISODE_F_JOIN_ENABLED_ENV,
        config.EPISODE_HARD_CAP_ACROSS_CONVERSATIONS_ENV,
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(config.EPISODE_F_JOIN_PERCENT_ENV, '100')
    # No flag-store rule: the env bucket decides (the store path has its own test).
    monkeypatch.setattr(omi_flags, 'resolve', lambda key, uid: None)
    monkeypatch.setattr(omi_flags, 'snapshot', lambda: omi_flags.EMPTY)
    monkeypatch.setenv('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')
    monkeypatch.setattr(service.client_gate, 'client_seen', lambda uid: True)
    monkeypatch.setattr(service, 'get_user_name', lambda *_a, **_kw: None)
    monkeypatch.setattr(service.incremental, 'get_user_name', lambda *_a, **_kw: None)
    monkeypatch.setattr(service.episode_language, 'language_preference', lambda uid: 'en')
    service.client_gate.reset_for_tests()
    service.reset_for_tests()


@pytest.fixture
def store(monkeypatch):
    store = StrictFirestore()
    # The user's current private cloud sync consent (checked before any Jev question) is on by default here.
    store.rows[('users', UID)] = {'private_cloud_sync_enabled': True}
    # Policy/storage seam as in test_episode_live_integrity; query ordering runs on the emulator.
    monkeypatch.setattr(
        episode_timeline,
        'recorded_candidates',
        lambda uid, *a, **kw: [
            dict(v, id=k[-1]) for k, v in store.rows.items() if len(k) == 4 and k[:3] == ('users', uid, 'episodes')
        ],
    )
    # The photo-join read path is not part of this unit; serve the stored row as get_conversation would.
    monkeypatch.setattr(
        service.conversations_db,
        'get_conversation',
        lambda uid, cid, **kw: store.rows.get(('users', uid, 'conversations', cid)),
    )
    return store


def _segments(text, *, start=0.0):
    return [
        {'text': w, 'start': start + i * 5.0, 'end': start + (i + 1) * 5.0, 'is_user': i % 2 == 0}
        for i, w in enumerate(text.split('. '))
    ]


def _c(store, *, minutes, ask=None, model=None):
    return Collaborators(
        invoke=model or FakeModel(),
        ask=ask or (lambda *a, **k: None),
        tz_name='UTC',
        firestore_client=store,
        saved_tasks=lambda uid, cid: [],
        people_names=lambda uid, ids: {},
        now=lambda: T0 + timedelta(minutes=minutes),
    )


def _moment(cid, *, minutes, text, source='omi'):
    return MomentInput(
        conversation_id=cid,
        source=source,
        segments=_segments(text),
        started_at=T0 + timedelta(minutes=minutes),
        ended_at=T0 + timedelta(minutes=minutes + 1),
        trigger='pause',
    )


def _store_row(store, cid, text, *, minutes):
    store.rows[('users', UID, 'conversations', cid)] = {
        'id': cid,
        'source': 'omi',
        'status': 'in_progress',
        'discarded': False,
        'is_locked': False,
        'data_protection_level': 'standard',
        'private_cloud_sync_enabled': True,
        'visibility': 'private',
        'started_at': T0 + timedelta(minutes=minutes),
        'finished_at': T0 + timedelta(minutes=minutes + 1),
        'transcript_segments': _segments(text),
    }


def _attach(store, cid, *, minutes, source='omi'):
    return service.attach_conversation(
        UID, cid, source, started_at=T0 + timedelta(minutes=minutes), collaborators=_c(store, minutes=minutes)
    )


def _first_episode(store):
    _store_row(store, 'c1', FIRST, minutes=0)
    assert _attach(store, 'c1', minutes=0) == 'opened'
    assert service.record_moment(UID, _moment('c1', minutes=0, text=FIRST), _c(store, minutes=1)) == 'applied'
    return episodes_db.get_current_episode(UID, firestore_client=store)


def test_uncertain_recorded_join_is_marked_for_f_and_moved_on_splits_it_off(store):
    first = _first_episode(store)
    _store_row(store, 'c2', SECOND, minutes=12)
    assert _attach(store, 'c2', minutes=12) == 'joined'
    joined = episodes_db.get_current_episode(UID, firestore_client=store)
    assert joined['id'] == first['id'] and joined['conversation_ids'] == ['c1', 'c2']
    assert joined['pending_boundary']['c2']['variant'] == 'f'

    asked = []

    def ask(state, questions, **kwargs):
        asked.append((state, kwargs))
        return SimpleNamespace(noul=lambda name: 0.05)

    assert service.record_moment(UID, _moment('c2', minutes=12, text=SECOND), _c(store, minutes=13, ask=ask)) == (
        'applied'
    )
    state, kwargs = asked[0]
    assert kwargs['lane'] == 'episode_boundary_f' and kwargs['max_attempts'] == 1
    assert state.startswith('EPISODE so far (full transcript of its last conversation):\nYou: okay lunch')
    assert '\n\nNEW speech (full transcript):\nYou: hi this is the dentist' in state
    assert 'minutes_since_last_speech' not in state and 'voices_changed' not in state
    closed = episodes_db.get_episode(UID, first['id'], firestore_client=store)
    assert closed['status'] == 'closed' and closed['close_reason'] == 'moved_on'
    assert closed['conversation_ids'] == ['c1']
    current = episodes_db.get_current_episode(UID, firestore_client=store)
    assert current['id'] != first['id'] and current['conversation_ids'] == ['c2']


def test_same_occasion_keeps_the_join_and_clears_the_marker(store):
    first = _first_episode(store)
    _attach(store, 'c2', minutes=12)
    keep = lambda *a, **k: SimpleNamespace(noul=lambda name: 0.9)  # noqa: E731
    service.record_moment(UID, _moment('c2', minutes=12, text=SECOND), _c(store, minutes=13, ask=keep))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2']
    assert episode['pending_boundary'] == {}


@pytest.mark.parametrize('answer', [None, TimeoutError('slow'), 1.7])
def test_no_answer_error_or_timeout_falls_back_to_todays_join(store, answer):
    first = _first_episode(store)
    _attach(store, 'c2', minutes=25, source='phone')  # past the 15 min fallback gap and a device change

    def ask(*_a, **_k):
        if isinstance(answer, Exception):
            raise answer
        return None if answer is None else SimpleNamespace(noul=lambda name: answer)

    service.record_moment(UID, _moment('c2', minutes=25, text=SECOND, source='phone'), _c(store, minutes=26, ask=ask))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2']


def test_short_gaps_keep_todays_rules_without_a_model_call(store):
    _first_episode(store)
    _attach(store, 'c2', minutes=2.5)  # under two minutes after c1's last speech at minute one
    assert episodes_db.get_current_episode(UID, firestore_client=store)['pending_boundary'] == {}


@pytest.mark.parametrize('env', [{'EPISODE_F_JOIN_PERCENT': '0'}, {'EPISODE_F_JOIN_ENABLED': 'off'}])
def test_outside_the_cohort_or_killed_nothing_is_marked(store, monkeypatch, env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    _first_episode(store)
    assert _attach(store, 'c2', minutes=12) == 'joined'
    assert episodes_db.get_current_episode(UID, firestore_client=store)['pending_boundary'] == {}


def test_kill_switch_after_marking_settles_as_todays_join_without_calling_jev(store, monkeypatch):
    first = _first_episode(store)
    _attach(store, 'c2', minutes=12)
    monkeypatch.setenv(config.EPISODE_F_JOIN_ENABLED_ENV, 'off')

    def ask(*_a, **_k):
        raise AssertionError('killed F must not call Jev')

    service.record_moment(UID, _moment('c2', minutes=12, text=SECOND), _c(store, minutes=13, ask=ask))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2']
    assert episode['pending_boundary'] == {}


def test_cohort_is_a_stable_bucket_and_invalid_percent_admits_nobody(monkeypatch):
    monkeypatch.setenv(config.EPISODE_F_JOIN_PERCENT_ENV, '25')
    admitted = [f'u{i}' for i in range(2000) if f_join.admitted(f'u{i}')]
    assert 400 < len(admitted) < 600
    assert admitted == [f'u{i}' for i in range(2000) if f_join.admitted(f'u{i}')]
    monkeypatch.setenv(config.EPISODE_F_JOIN_PERCENT_ENV, 'lots')
    assert not any(f_join.admitted(f'u{i}') for i in range(200))
    monkeypatch.delenv(config.EPISODE_F_JOIN_PERCENT_ENV)
    assert not f_join.admitted('u1')


def test_flag_store_rule_is_the_ramp_and_the_env_kill_switch_overrides_it(monkeypatch):
    rule = omi_flags.FlagRule(key=config.F_JOIN_FLAG_KEY, active=True, rollout_percentage=5.0)
    monkeypatch.setattr(omi_flags, 'resolve', lambda key, uid: omi_flags.evaluate(rule, uid))
    monkeypatch.setenv(config.EPISODE_F_JOIN_PERCENT_ENV, '100')
    share = sum(f_join.admitted(f'u{i}') for i in range(4000)) / 4000
    assert 0.03 < share < 0.07
    rule = omi_flags.FlagRule(key=config.F_JOIN_FLAG_KEY, active=False, rollout_percentage=100.0)
    assert not any(f_join.admitted(f'u{i}') for i in range(200))
    rule = omi_flags.FlagRule(key=config.F_JOIN_FLAG_KEY, active=True, rollout_percentage=100.0)
    assert f_join.admitted('u1')
    monkeypatch.setenv(config.EPISODE_F_JOIN_ENABLED_ENV, 'off')
    assert not f_join.admitted('u1')

    def broken(key, uid):
        raise RuntimeError('store')

    monkeypatch.delenv(config.EPISODE_F_JOIN_ENABLED_ENV)
    monkeypatch.setattr(omi_flags, 'resolve', broken)
    assert not f_join.admitted('u1')


def test_f_state_caps_each_side_and_marks_empty_speech():
    state = incremental.f_boundary_state('a' * 13_000 + 'END', 'START' + 'b' * 9_000)
    previous, new = state.split('\n\nNEW speech (full transcript):\n')
    assert previous.endswith('END') and len(previous.split(':\n', 1)[1]) == config.F_JOIN_PREVIOUS_CHARS
    assert new.startswith('START') and len(new) == config.F_JOIN_NEW_CHARS
    assert incremental.f_boundary_state('', '').count('(no speech captured)') == 2
    rendered = incremental.render_f_transcript(
        [
            {'text': 'later', 'start': 9, 'is_user': False, 'speaker': 'SPEAKER_01'},
            {'text': 'hi', 'start': 0, 'is_user': True},
            {'text': 'there', 'start': 1, 'is_user': True},
            {'text': ' ', 'start': 2, 'is_user': False},
        ]
    )
    assert rendered == 'You: hi there\nSPEAKER_01: later'


def test_closed_episode_size_is_recorded_by_arm(store):
    before = metrics.EPISODE_CLOSED_MEMBERS.labels(arm='f')._sum.get()
    _first_episode(store)
    _store_row(store, 'c2', SECOND, minutes=12)
    _attach(store, 'c2', minutes=12)
    move = lambda *a, **k: SimpleNamespace(noul=lambda name: 0.0)  # noqa: E731
    service.record_moment(UID, _moment('c2', minutes=12, text=SECOND), _c(store, minutes=13, ask=move))
    assert metrics.EPISODE_CLOSED_MEMBERS.labels(arm='f')._sum.get() == before + 1


def test_a_typo_in_the_kill_switch_turns_f_off(monkeypatch):
    monkeypatch.setenv(config.EPISODE_F_JOIN_ENABLED_ENV, 'disabled')
    assert not config.f_join_enabled()
    monkeypatch.setenv(config.EPISODE_F_JOIN_ENABLED_ENV, 'true')
    assert config.f_join_enabled()
    monkeypatch.delenv(config.EPISODE_F_JOIN_ENABLED_ENV)
    assert config.f_join_enabled()


def test_a_moment_too_short_to_commit_never_calls_jev_or_splits(store):
    _first_episode(store)
    _attach(store, 'c2', minutes=12)

    def ask(*_a, **_k):
        raise AssertionError('a short moment must not ask Jev')

    short = 'yes sure'
    assert service.record_moment(UID, _moment('c2', minutes=12, text=short), _c(store, minutes=13, ask=ask)) == (
        'skipped_short'
    )
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['conversation_ids'] == ['c1', 'c2']
    assert episode['pending_boundary']['c2']['variant'] == 'f'


def test_the_predecessor_is_the_one_recorded_at_the_join_not_a_later_member(store):
    _first_episode(store)
    _attach(store, 'c2', minutes=12)
    marker = episodes_db.get_current_episode(UID, firestore_client=store)['pending_boundary']['c2']
    assert marker['previous'] == 'c1'
    # A later member attaching before c2's first moment must not become c2's predecessor.
    episode = {'conversation_ids': ['c1', 'c2', 'c3'], 'member_activity': {'c1': T0, 'c3': T0 + timedelta(minutes=14)}}
    _store_row(store, 'c3', SECOND, minutes=14)
    rendered = f_join.previous_transcript(UID, episode, 'c2', marker, _c(store, minutes=13))
    assert 'okay lunch' in rendered and 'dentist' not in rendered


def test_the_arm_is_the_one_live_when_the_episode_opened(store, monkeypatch):
    _first_episode(store)
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['f_join_arm'] == 'f'
    monkeypatch.setenv(config.EPISODE_F_JOIN_ENABLED_ENV, 'off')
    before = metrics.EPISODE_CLOSED_MEMBERS.labels(arm='f')._sum.get()
    f_join.record_closed_size({**episode, 'closed_at': T0 + timedelta(minutes=5), 'conversation_ids': ['c1']})
    assert metrics.EPISODE_CLOSED_MEMBERS.labels(arm='f')._sum.get() == before + 1
    f_join.record_closed_size({'conversation_ids': ['c1']})


def test_a_later_member_keeps_the_candidate_without_a_question_so_no_overlapping_split(store):
    first = _first_episode(store)
    assert _attach(store, 'c2', minutes=12) == 'joined'
    assert _attach(store, 'c3', minutes=14) == 'joined'
    asked = []
    service.record_moment(
        UID, _moment('c2', minutes=12, text=SECOND), _c(store, minutes=15, ask=lambda *a, **k: asked.append(a))
    )
    assert asked == []
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2', 'c3']
    assert 'c2' not in episode['pending_boundary']


def test_a_member_that_attaches_while_jev_answers_keeps_the_join(store):
    first = _first_episode(store)
    _store_row(store, 'c2', SECOND, minutes=12)
    assert _attach(store, 'c2', minutes=12) == 'joined'
    attached = []

    def ask(*_a, **_k):
        # c3 attaches after the candidate's own check but before the model answers: the split must not go.
        attached.append(_attach(store, 'c3', minutes=14))
        return SimpleNamespace(noul=lambda name: 0.05)

    service.record_moment(UID, _moment('c2', minutes=12, text=SECOND), _c(store, minutes=15, ask=ask))
    assert attached == ['joined']
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2', 'c3']
    assert 'c2' not in episode['pending_boundary']


def test_a_member_attaching_between_the_split_plan_and_its_close_is_kept_not_erased(store, monkeypatch):
    first = _first_episode(store)
    _store_row(store, 'c2', SECOND, minutes=12)
    assert _attach(store, 'c2', minutes=12) == 'joined'
    real_close = service.episodes_db.close_episode
    raced = []

    def racing_close(*args, **kwargs):
        if not raced:
            raced.append(True)
            # c3 attaches after the split was planned from c1 and c2, before the close transaction runs.
            assert _attach(store, 'c3', minutes=14) == 'joined'
        return real_close(*args, **kwargs)

    monkeypatch.setattr(service.episodes_db, 'close_episode', racing_close)
    ask = lambda *a, **k: SimpleNamespace(noul=lambda name: 0.05)  # noqa: E731
    service.record_moment(UID, _moment('c2', minutes=12, text=SECOND), _c(store, minutes=13, ask=ask))
    assert raced == [True]
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2', 'c3']
    assert 'c2' not in episode['pending_boundary']
    assert episodes_db.get_episode(UID, first['id'], firestore_client=store)['status'] == 'live'


@pytest.mark.parametrize('error', [EpisodeConflict('lost the compare-and-swap'), RuntimeError('storage down')])
def test_a_failed_f_marker_records_the_shared_fallback_and_keeps_todays_join(monkeypatch, error):
    fallbacks = []
    monkeypatch.setattr(f_join, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))

    def fail(*_a, **_k):
        raise error

    monkeypatch.setattr(f_join.episodes_db, 'commit_moment', fail)
    live = {'id': 'e1', 'status': 'live', 'state_version': 1, 'conversation_ids': ['c1']}
    decision = policy.Boundary(policy.ASK, gap_seconds=720.0, source_changed=False)
    f_join.mark_pending(UID, live, live, 'c2', decision, {}, firestore_client=None)
    assert [item['component'] for item in fallbacks] == ['episode_f_join']


def _sync_attach(store, cid, text, *, minutes, ask=None):
    _store_row(store, cid, text, minutes=minutes)
    row = store.rows[('users', UID, 'conversations', cid)]
    return service.attach_synced_intake(UID, cid, row, collaborators=_c(store, minutes=minutes + 1, ask=ask))


def test_a_synced_join_the_model_calls_moved_on_opens_its_own_occasion(store):
    first = _first_episode(store)
    asked = []

    def ask(state, questions, **kwargs):
        asked.append(state)
        return SimpleNamespace(noul=lambda name: 0.05)

    _sync_attach(store, 'c2', SECOND, minutes=12, ask=ask)
    assert asked and '\n\nNEW speech (full transcript):\nYou: hi this is the dentist' in asked[0]
    closed = episodes_db.get_episode(UID, first['id'], firestore_client=store)
    assert closed['status'] == 'closed' and closed['close_reason'] == 'moved_on'
    assert closed['conversation_ids'] == ['c1']
    # A sync conversation with no live owner forms its own closed occasion, as it does without F.
    own = episodes_db.get_episode_for_conversation(UID, 'c2', firestore_client=store)
    assert own['id'] != first['id'] and own['conversation_ids'] == ['c2']
    assert own['status'] == 'closed'


def test_a_synced_join_the_model_calls_same_occasion_stays_one_episode(store):
    first = _first_episode(store)
    keep = lambda *a, **k: SimpleNamespace(noul=lambda name: 0.9)  # noqa: E731
    _sync_attach(store, 'c2', SECOND, minutes=12, ask=keep)
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2']


@pytest.mark.parametrize('answer,opens_own', [(0.05, True), (0.9, False)], ids=['moved_on', 'same_occasion'])
def test_a_sync_attach_retried_after_lost_cas_asks_jev_once(store, monkeypatch, answer, opens_own):
    # sync_attach re-runs the whole attach after a lost CAS; each run used to ask Jev again (up to three times).
    # Every attempt also keeps the first answer's placement: a moved-on candidate opens its own occasion each time.
    _first_episode(store)
    real_attach_recorded = service.attach_recorded
    attempts = []

    def lose_two_cas(uid, conversation_id, row, started, finished, c, **kwargs):
        attempts.append(kwargs.get('new_occasion', False))
        if len(attempts) <= 2:
            raise EpisodeConflict('lost cas')
        return real_attach_recorded(uid, conversation_id, row, started, finished, c, **kwargs)

    monkeypatch.setattr(service, 'attach_recorded', lose_two_cas)
    asked = []

    def ask(state, questions, **kwargs):
        asked.append(state)
        return SimpleNamespace(noul=lambda name: answer)

    _sync_attach(store, 'c2', SECOND, minutes=12, ask=ask)
    assert attempts == [opens_own] * 3, 'the lost CAS must be retried twice, each with the first answer'
    assert len(asked) == 1, 'a retry must reuse the first answer, never ask Jev again'


def test_a_synced_candidate_locked_after_intake_never_reaches_jev(store, monkeypatch):
    # The intake snapshot was taken before the conversation was locked; the worker must ask the stored document.
    first = _first_episode(store)
    _store_row(store, 'c2', SECOND, minutes=12)
    row = store.rows[('users', UID, 'conversations', 'c2')]
    snapshot = dict(row)
    monkeypatch.setattr(service, '_named_segments', lambda *a, **kw: pytest.fail('locked candidate was named'))
    row['is_locked'] = True
    span = conversation_span(snapshot)
    asked = []
    ask = lambda state, *a, **k: asked.append(state) or SimpleNamespace(noul=lambda n: 0.05)  # noqa: E731
    service._attach_recorded_synced(
        UID, 'c2', snapshot, span.recorded_start, span.recorded_end, _c(store, minutes=13, ask=ask)
    )
    assert asked == [], 'a conversation locked after intake must never be sent to Jev'
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2']


@pytest.mark.parametrize('consent', ['missing', False], ids=['missing', 'off'])
def test_a_synced_candidate_without_a_private_cloud_sync_opt_in_is_never_named_or_asked(store, monkeypatch, consent):
    # Retention consent is an explicit opt-in on the row. An absent or false value keeps today's join, unasked.
    first = _first_episode(store)
    _store_row(store, 'c2', SECOND, minutes=12)
    row = store.rows[('users', UID, 'conversations', 'c2')]
    if consent == 'missing':
        del row['private_cloud_sync_enabled']
    else:
        row['private_cloud_sync_enabled'] = consent
    span = conversation_span(row)
    monkeypatch.setattr(service, '_named_segments', lambda *a, **kw: pytest.fail('unconsented candidate was named'))
    asked = []
    ask = lambda *a, **k: asked.append(a) or SimpleNamespace(noul=lambda n: 0.05)  # noqa: E731
    service._attach_recorded_synced(
        UID, 'c2', row, span.recorded_start, span.recorded_end, _c(store, minutes=13, ask=ask)
    )
    assert asked == []
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2']


def test_a_predecessor_without_private_cloud_sync_consent_is_never_sent_to_jev(store):
    first = _first_episode(store)
    store.rows[('users', UID, 'conversations', 'c1')]['private_cloud_sync_enabled'] = False
    _store_row(store, 'c2', SECOND, minutes=12)
    row = store.rows[('users', UID, 'conversations', 'c2')]
    span = conversation_span(row)
    asked = []
    ask = lambda state, *a, **k: asked.append(state) or SimpleNamespace(noul=lambda n: 0.05)  # noqa: E731
    service._attach_recorded_synced(
        UID, 'c2', row, span.recorded_start, span.recorded_end, _c(store, minutes=13, ask=ask)
    )
    assert asked == [], 'the previous transcript is consent-gated too'
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2']


@pytest.mark.parametrize(
    'change',
    [{'is_locked': True}, {'deleted': True}, {'private_cloud_sync_enabled': False}],
    ids=['locked', 'deleted', 'consent_off'],
)
def test_a_candidate_changed_while_the_predecessor_is_read_never_reaches_jev(store, monkeypatch, change):
    # The intake gate passed, then the candidate changed during the predecessor and name reads.
    # The stored-privacy re-read just before Jev prevents the question.
    first = _first_episode(store)
    _store_row(store, 'c2', SECOND, minutes=12)
    row = store.rows[('users', UID, 'conversations', 'c2')]
    span = conversation_span(row)
    real_previous = f_join.previous_transcript

    def changing_previous(*a, **kw):
        out = real_previous(*a, **kw)
        row.update(change)
        return out

    monkeypatch.setattr(f_join, 'previous_transcript', changing_previous)
    asked = []
    ask = lambda state, *a, **k: asked.append(state) or SimpleNamespace(noul=lambda n: 0.05)  # noqa: E731
    try:
        service._attach_recorded_synced(
            UID, 'c2', row, span.recorded_start, span.recorded_end, _c(store, minutes=13, ask=ask)
        )
    except EpisodeConflict as error:
        # Placement itself refuses a deleted conversation, after F has already declined to ask.
        assert str(error) == 'conversation_hidden' and 'deleted' in change
        assert asked == []
        return
    assert asked == [], 'a candidate that changed during the reads must not reach Jev'
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2']


@pytest.mark.parametrize('user_state', ['doc_missing', 'field_missing', 'off'])
def test_a_synced_candidate_without_current_user_consent_is_never_sent_to_jev(store, user_state):
    # The user-level toggle is re-read before Jev. A missing user document or field is not permission (fail closed).
    first = _first_episode(store)
    _store_row(store, 'c2', SECOND, minutes=12)
    if user_state == 'doc_missing':
        store.rows.pop(('users', UID))
    elif user_state == 'field_missing':
        store.rows[('users', UID)] = {}
    else:
        store.rows[('users', UID)]['private_cloud_sync_enabled'] = False
    row = store.rows[('users', UID, 'conversations', 'c2')]
    span = conversation_span(row)
    asked = []
    ask = lambda state, *a, **k: asked.append(state) or SimpleNamespace(noul=lambda n: 0.05)  # noqa: E731
    service._attach_recorded_synced(
        UID, 'c2', row, span.recorded_start, span.recorded_end, _c(store, minutes=13, ask=ask)
    )
    assert asked == [], 'a user without current consent must never reach Jev'
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2']


def test_a_user_who_turns_private_cloud_sync_off_while_the_predecessor_is_read_is_never_asked_about(store, monkeypatch):
    # The row-level snapshot still says on; the user's current toggle, checked before Jev, says off.
    first = _first_episode(store)
    _store_row(store, 'c2', SECOND, minutes=12)
    row = store.rows[('users', UID, 'conversations', 'c2')]
    span = conversation_span(row)
    real_previous = f_join.previous_transcript

    def toggling_previous(*a, **kw):
        out = real_previous(*a, **kw)
        store.rows[('users', UID)]['private_cloud_sync_enabled'] = False
        return out

    monkeypatch.setattr(f_join, 'previous_transcript', toggling_previous)
    asked = []
    ask = lambda state, *a, **k: asked.append(state) or SimpleNamespace(noul=lambda n: 0.05)  # noqa: E731
    service._attach_recorded_synced(
        UID, 'c2', row, span.recorded_start, span.recorded_end, _c(store, minutes=13, ask=ask)
    )
    assert asked == [], 'a toggle turned off during the reads must keep today\'s join'
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2']


def test_an_unexpected_failure_closing_the_owner_keeps_todays_join(store, monkeypatch):
    first = _first_episode(store)
    _store_row(store, 'c2', SECOND, minutes=12)
    row = store.rows[('users', UID, 'conversations', 'c2')]
    span = conversation_span(row)

    def close_fails(*args, **kwargs):
        raise RuntimeError('close failed')

    monkeypatch.setattr(service, '_close', close_fails)
    asked = []
    ask = lambda state, *a, **k: asked.append(state) or SimpleNamespace(noul=lambda n: 0.05)  # noqa: E731
    service._attach_recorded_synced(
        UID, 'c2', row, span.recorded_start, span.recorded_end, _c(store, minutes=13, ask=ask)
    )
    assert asked, 'F decided moved-on, so the close is the step that failed'
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2']


@pytest.mark.parametrize('case', ['killed', 'outside_cohort', 'short_speech', 'short_gap', 'member_later'])
def test_a_synced_join_that_f_does_not_decide_keeps_todays_join_without_a_question(store, monkeypatch, case):
    first = _first_episode(store)
    text, minutes = SECOND, 12
    if case == 'killed':
        monkeypatch.setenv(config.EPISODE_F_JOIN_ENABLED_ENV, 'off')
    elif case == 'outside_cohort':
        monkeypatch.setenv(config.EPISODE_F_JOIN_PERCENT_ENV, '0')
    elif case == 'short_speech':
        text = 'please call us back to confirm'
    elif case == 'short_gap':
        minutes = 2.5
    elif case == 'member_later':
        _attach(store, 'c3', minutes=12.5)
    asked = []
    _sync_attach(
        store,
        'c2',
        text,
        minutes=minutes,
        ask=lambda *a, **k: asked.append(a) or SimpleNamespace(noul=lambda name: 0.05),
    )
    assert asked == []
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and 'c2' in episode['conversation_ids']


def test_a_failing_synced_f_decision_keeps_todays_join_and_reports_the_fallback(store, monkeypatch):
    first = _first_episode(store)
    fallbacks = []
    monkeypatch.setattr(f_join, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))

    def boom(*_a, **_k):
        raise RuntimeError('storage down')

    monkeypatch.setattr(f_join, 'settle', boom)
    _sync_attach(store, 'c2', SECOND, minutes=12, ask=lambda *a, **k: SimpleNamespace(noul=lambda name: 0.05))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2']
    assert [item['component'] for item in fallbacks] == ['episode_f_join']


def test_a_split_refused_by_the_member_guard_keeps_the_join(store, monkeypatch):
    first = _first_episode(store)

    def refuse(*_a, **_k):
        raise EpisodeConflict('split_member_recorded_later')

    monkeypatch.setattr(service, '_close', refuse)
    _sync_attach(store, 'c2', SECOND, minutes=12, ask=lambda *a, **k: SimpleNamespace(noul=lambda name: 0.05))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2']


def test_a_conversation_already_placed_is_never_asked_about_again(store, monkeypatch):
    first = _first_episode(store)
    _sync_attach(store, 'c2', SECOND, minutes=12, ask=lambda *a, **k: SimpleNamespace(noul=lambda name: 0.9))
    assert episodes_db.get_episode_for_conversation(UID, 'c2', firestore_client=store)['id'] == first['id']
    ambiguous = policy.Boundary(policy.ASK, gap_seconds=720.0, source_changed=False)
    monkeypatch.setattr(f_join, 'uncertain', lambda *a, **k: ambiguous)
    monkeypatch.setattr(f_join, 'settle', lambda *a, **k: pytest.fail('a placed conversation was asked about again'))
    row = store.rows[('users', UID, 'conversations', 'c2')]
    span = conversation_span(row)
    with monkeypatch.context() as retry:
        retry.setattr(
            episode_timeline,
            'recorded_candidates',
            lambda *a, **k: pytest.fail('a placed conversation queried recorded candidates again'),
        )
        retry.setattr(
            episodes_db,
            'get_episode',
            lambda *a, **k: pytest.fail('a placed conversation read the recorded episode again'),
        )
        retry.setattr(
            f_join,
            'uncertain',
            lambda *a, **k: pytest.fail('a placed conversation evaluated the boundary again'),
        )
        assert (
            service._synced_f_verdict(UID, 'c2', row, span.recorded_start, span.recorded_end, _c(store, minutes=13))
            is None
        )
    service._attach_recorded_synced(UID, 'c2', row, span.recorded_start, span.recorded_end, _c(store, minutes=13))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and episode['conversation_ids'] == ['c1', 'c2']


def test_synced_candidate_placed_after_owner_snapshot_declines_before_settlement(store, monkeypatch):
    first = _first_episode(store)
    assert first is not None
    _store_row(store, 'c2', SECOND, minutes=12)
    row = store.rows[('users', UID, 'conversations', 'c2')]
    uncertain = f_join.uncertain
    checked = []

    def attach_before_uncertain(uid, owner, *a, **kw):
        assert owner['id'] == first['id'] and 'c2' not in owner['conversation_ids']
        assert episodes_db.get_episode_owner_snapshot(UID, 'c2', firestore_client=store) is None
        with monkeypatch.context() as control:
            control.setenv(config.EPISODE_F_JOIN_ENABLED_ENV, 'off')
            _sync_attach(store, 'c2', SECOND, minutes=12)
        placed = episodes_db.get_episode_owner_snapshot(UID, 'c2', firestore_client=store)
        assert placed is not None and placed['id'] == first['id']
        marker = uncertain(uid, owner, *a, **kw)
        assert marker is not None and marker.action == policy.ASK
        checked.append(True)
        return marker

    def forbidden(*a, **kw):
        pytest.fail('a concurrently placed candidate reached settlement or Jev')

    monkeypatch.setattr(f_join, 'uncertain', attach_before_uncertain)
    monkeypatch.setattr(f_join, 'settle', forbidden)
    monkeypatch.setattr(incremental, 'ask_same_occasion_f', forbidden)
    assert (
        service.attach_synced_intake(UID, 'c2', row, collaborators=_c(store, minutes=13, ask=forbidden)) == 'recorded'
    )
    assert checked == [True]


@pytest.mark.parametrize('during', ['previous_transcript', '_user_consent_allows'])
def test_synced_candidate_placed_during_settlement_never_reaches_jev(store, monkeypatch, during):
    first = _first_episode(store)
    assert first is not None
    _store_row(store, 'c2', SECOND, minutes=12)
    row = store.rows[('users', UID, 'conversations', 'c2')]
    original = getattr(f_join, during)
    attached = []

    def attach_during_reads(*a, **kw):
        result = original(*a, **kw)
        with monkeypatch.context() as control:
            control.setenv(config.EPISODE_F_JOIN_ENABLED_ENV, 'off')
            _sync_attach(store, 'c2', SECOND, minutes=12)
        attached.append(True)
        return result

    def forbidden(*a, **kw):
        pytest.fail('a candidate placed during settlement reached Jev')

    monkeypatch.setattr(f_join, during, attach_during_reads)
    monkeypatch.setattr(incremental, 'ask_same_occasion_f', forbidden)
    assert (
        service.attach_synced_intake(UID, 'c2', row, collaborators=_c(store, minutes=13, ask=forbidden)) == 'recorded'
    )
    assert attached == [True]
    placed = episodes_db.get_episode_owner_snapshot(UID, 'c2', firestore_client=store)
    assert placed is not None and placed['id'] == first['id']


EXCLUDED_CLASSES = [
    ('locked', {'is_locked': True}),
    ('discarded', {'discarded': True}),
    ('deleted', {'deleted': True}),
    ('deferred', {'deferred': True}),
    ('processing_deferred', {'processing_deferred': True}),
    ('local_pending', {'processing_state': 'local_pending'}),
    ('client_processing', {'client_processing': True}),
    ('local_only', {'summary_blocked_reason': 'local_only'}),
    ('held', {f_join.HOLD_FIELD: {'held': True}}),
    ('another_owner', {'owner_uid': 'someone-else'}),
    ('failed_status', {'status': 'failed'}),
    ('unknown_protection', {'data_protection_level': 'none'}),
    ('private_cloud_sync_off', {'private_cloud_sync_enabled': False}),
]


@pytest.mark.parametrize('name, change', EXCLUDED_CLASSES, ids=[n for n, _ in EXCLUDED_CLASSES])
def test_a_synced_candidate_that_may_not_feed_the_llm_is_never_sent_to_jev(store, name, change):
    first = _first_episode(store)
    _store_row(store, 'c2', SECOND, minutes=12)
    row = store.rows[('users', UID, 'conversations', 'c2')]
    row.update(change)
    span = conversation_span(row)
    asked = []
    c = _c(store, minutes=13, ask=lambda *a, **k: asked.append(a) or SimpleNamespace(noul=lambda n: 0.05))
    try:
        service._attach_recorded_synced(UID, 'c2', row, span.recorded_start, span.recorded_end, c)
    except EpisodeConflict as error:
        # Placement itself refuses a hidden conversation, after F has already declined to ask.
        assert str(error) == 'conversation_hidden' and name in {'discarded', 'deleted'}
        assert asked == []
        return
    assert asked == []
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and 'c2' in episode['conversation_ids']


@pytest.mark.parametrize('name, change', EXCLUDED_CLASSES, ids=[n for n, _ in EXCLUDED_CLASSES])
def test_settle_reads_the_candidate_and_never_asks_about_an_excluded_one(store, name, change):
    first = _first_episode(store)
    _store_row(store, 'c2', SECOND, minutes=12)
    store.rows[('users', UID, 'conversations', 'c2')].update(change)
    asked = []
    c = _c(store, minutes=13, ask=lambda *a, **k: asked.append(a) or SimpleNamespace(noul=lambda n: 0.05))
    pending = {'gap_seconds': 720.0, 'source_changed': False, 'previous': 'c1'}
    decision = f_join.settle(UID, first, 'c2', pending, [], c, started_at=T0 + timedelta(minutes=12))
    assert decision.action == policy.CONTINUE and asked == []


def test_settle_without_the_candidate_document_fails_closed_and_never_asks(store):
    first = _first_episode(store)
    asked = []
    c = _c(store, minutes=13, ask=lambda *a, **k: asked.append(a) or SimpleNamespace(noul=lambda n: 0.05))
    pending = {'gap_seconds': 720.0, 'source_changed': False, 'previous': 'c1'}
    decision = f_join.settle(UID, first, 'c2', pending, [], c, started_at=T0 + timedelta(minutes=12))
    assert decision.action == policy.CONTINUE and asked == []


def test_candidate_head_keeps_the_spec_head_and_names_only_its_first_voices():
    segments = [
        {'text': 'x' * 5000, 'start': 0.0, 'person_id': 'a'},
        {'text': 'y' * 5000, 'start': 10.0, 'person_id': 'b'},
        {'text': 'z', 'start': 20.0, 'person_id': 'c'},
    ]
    head = f_join.candidate_head(segments)
    assert [len(s['text']) for s in head] == [5000, config.F_JOIN_NEW_CHARS - 5001]
    voices = [{'text': 'hi', 'start': float(i), 'person_id': f'p{i}'} for i in range(20)]
    named = f_join.candidate_head(voices)
    assert sum(1 for s in named if s.get('person_id')) == config.F_JOIN_PEOPLE_READ_LIMIT
    assert [s.get('person_id') for s in named[: config.F_JOIN_PEOPLE_READ_LIMIT]] == [
        f'p{i}' for i in range(config.F_JOIN_PEOPLE_READ_LIMIT)
    ]


def test_a_long_synced_candidate_names_at_most_the_people_read_limit(store):
    first = _first_episode(store)
    _store_row(store, 'c2', SECOND, minutes=12)
    row = store.rows[('users', UID, 'conversations', 'c2')]
    row['transcript_segments'] = [
        {'text': 'word ' * 60, 'start': 720.0 + i * 60.0, 'end': 750.0 + i * 60.0, 'person_id': f'p{i}'}
        for i in range(40)
    ]
    span = conversation_span(row)
    lookups, asked = [], []
    c = _c(store, minutes=13, ask=lambda state, *a, **k: asked.append(state) or SimpleNamespace(noul=lambda n: 0.9))
    c.people_names = lambda uid, ids: lookups.append(list(ids)) or {}
    service._attach_recorded_synced(UID, 'c2', row, span.recorded_start, span.recorded_end, c)
    assert asked, 'the candidate must reach Jev for the cap to matter'
    assert lookups and all(len(ids) <= config.F_JOIN_PEOPLE_READ_LIMIT for ids in lookups)
    # The complete synced/late decision reserves two name reads per side within its 26-read budget.
    assert sorted(lookups[-1]) == ['p0', 'p1']
    new_speech = asked[0].split('NEW speech (full transcript):\n', 1)[1]
    assert len(new_speech) <= config.F_JOIN_NEW_CHARS
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['id'] == first['id'] and 'c2' in episode['conversation_ids']


@pytest.mark.parametrize(
    'changes,missing',
    [
        ({'is_locked': True}, None),
        ({'deferred': True}, None),
        ({'processing_deferred': True}, None),
        ({'discarded': True}, None),
        ({'deleted': True}, None),
        ({'owner_uid': 'someone-else'}, None),
        ({'uid': 'someone-else'}, None),
        ({'data_protection_level': 'local'}, None),
        ({'processing_state': 'local_pending'}, None),
        ({'summary_blocked_reason': 'local_only'}, None),
        ({'client_processing': True}, None),
        ({'terminal_no_derived_effects': True}, None),
        ({'sync_processing_hold': {'held': True}}, None),
        ({}, 'is_locked'),
        ({}, 'discarded'),
        ({}, 'data_protection_level'),
        ({}, 'status'),
    ],
)
def test_synced_candidate_processing_exclusions_keep_control_before_naming(store, monkeypatch, changes, missing):
    _store_row(store, 'candidate', SECOND, minutes=12)
    row = dict(store.rows[('users', UID, 'conversations', 'candidate')], **changes)
    if missing:
        row.pop(missing)
    control = []
    monkeypatch.setattr(service, 'attach_recorded', lambda *a, **kw: control.append(kw) or {'id': 'control'})

    def forbidden(*a, **kw):
        pytest.fail('excluded candidate reached F lookup, naming or Jev')

    monkeypatch.setattr(episode_timeline, 'recorded_candidates', forbidden)
    monkeypatch.setattr(service, '_named_segments', forbidden)
    monkeypatch.setattr(f_join, 'settle', forbidden)
    result = service._attach_recorded_synced(UID, 'candidate', row, T0, T0, _c(store, minutes=13, ask=forbidden))
    assert result == {'id': 'control'} and control == [{}]


def _bounded_query_fake(store, monkeypatch, reads):
    """Model only this single-field ordered range; count every returned document, including overflow."""
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreCollection

    class Query:
        def __init__(self, path):
            self.path, self.filters, self.fields = path, [], ()
            self.count, self.direction = None, None

        def where(self, *, filter):
            assert filter.field_path == 'started_at' and filter.op_string in {'>=', '<='}
            self.filters.append(filter)
            return self

        def order_by(self, field, *, direction):
            assert field == 'started_at'
            self.direction = direction
            return self

        def select(self, fields):
            assert fields == episode_timeline.FIELDS
            self.fields = fields
            return self

        def limit(self, count):
            assert count == episode_timeline.F_JOIN_CANDIDATE_LIMIT == 2
            self.count = count
            return self

        def stream(self, transaction=None):
            assert self.count is not None and self.direction == 'DESCENDING'
            if transaction:
                transaction._assert_read_allowed()
            rows = [
                (path, row)
                for path, row in store.rows.items()
                if path[:-1] == self.path
                and all(
                    row['started_at'] >= f.value if f.op_string == '>=' else row['started_at'] <= f.value
                    for f in self.filters
                )
            ]
            rows.sort(key=lambda item: item[1]['started_at'], reverse=True)
            result = []
            for path, row in rows[: self.count]:
                reads.append(path)
                data = {k: v for k, v in row.items() if k in self.fields}
                result.append(SimpleNamespace(id=path[-1], to_dict=lambda data=data: dict(data)))
            return iter(result)

    monkeypatch.setattr(StrictFirestoreCollection, 'where', lambda ref, **kw: Query(ref._path).where(**kw))
    # The store fixture replaces the ordinary query seam. Rebind the actual function under test.
    original = episode_timeline.recorded_candidates
    monkeypatch.setattr(episode_timeline, 'recorded_candidates', recorded_candidates)
    return original


@pytest.mark.parametrize(
    'owner_reuse,optimizations', [('true', 'true'), ('false', 'true'), ('true', 'false'), ('false', 'false')]
)
@pytest.mark.parametrize('answer', [0.05, 0.9, None, TimeoutError('slow Jev')])
def test_synced_f_read_and_jev_budget_includes_close_and_all_attach_retries(
    store, monkeypatch, owner_reuse, optimizations, answer, record_property
):
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument

    first = _first_episode(store)
    assert first is not None
    # Seed retained live members directly: recorded attachment marks members recovered,
    # which intentionally takes the reconciliation/control branch instead of this F close.
    owner = store.rows[('users', UID, 'episodes', first['id'])]
    for cid, minute in [('c3', 2), ('c4', 3)]:
        _store_row(store, cid, FIRST, minutes=minute)
        owner['conversation_ids'].append(cid)
        owner['member_activity'][cid] = T0 + timedelta(minutes=minute + 1)
    owner['last_activity_at'] = T0 + timedelta(minutes=4)
    assert not owner.get('recovered_conversation_ids')
    _store_row(store, 'c2', SECOND, minutes=12)
    row = store.rows[('users', UID, 'conversations', 'c2')]
    for cid in ('c2', 'c4'):
        store.rows[('users', UID, 'conversations', cid)]['transcript_segments'] = [
            {'text': SECOND, 'start': i, 'end': i + 1, 'person_id': f'{cid}-p{i}', 'is_user': False} for i in range(12)
        ]
    reads, asked, name_reads, placements = [], [], [], []
    read = StrictFirestoreDocument.get

    def counted(ref, *a, **kw):
        reads.append(ref.path)
        if len(ref.path) > 2 and ref.path[2] == 'people':
            assert kw.pop('field_paths') == ['name']
            name_reads.append(ref.path[-1])
        return read(ref, *a, **kw)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', counted)
    _bounded_query_fake(store, monkeypatch, reads)
    monkeypatch.setenv('EPISODE_ATTACH_OWNER_REUSE_ENABLED', owner_reuse)
    monkeypatch.setenv('EPISODE_ATTACH_OPTIMIZATIONS_ENABLED', optimizations)
    monkeypatch.setattr(service.sync_attach, 'hidden_conversation', lambda *a, **kw: False)
    monkeypatch.setenv('EPISODE_BOUNDARIES_MODE', 'serve')  # Include a cold authority read, not a cached shadow.
    monkeypatch.setattr(service.composer, 'schedule', lambda *a, **kw: False)
    monkeypatch.setattr(service.episode_groups, 'canonical_row', lambda *a, **kw: None)
    monkeypatch.setattr(service.episode_groups, 'join_duplicates', lambda *a, **kw: None)
    monkeypatch.setattr(service.episode_attach_memo, 'matches', lambda *a, **kw: False)
    monkeypatch.setattr(service, '_repoint_sync_donors', lambda *a, **kw: None)
    monkeypatch.setattr(service, '_record_recovered', lambda *a, **kw: 'skipped')

    # Only control placement/recovery is stubbed: F's queries, naming, predecessor, recheck,
    # service close and the transaction (including member docs and its query) are real.
    def place(*a, **kw):
        placements.append(kw)
        if len(placements) < 3:
            raise EpisodeConflict('placement_lost_cas')
        return {**first, 'recovered_conversation_ids': ['c2']}

    monkeypatch.setattr(service, 'attach_recorded', place)

    def ask(*a, **kw):
        asked.append(kw)
        if isinstance(answer, Exception):
            raise answer
        return None if answer is None else SimpleNamespace(noul=lambda name: answer)

    c = _c(store, minutes=13, ask=ask)
    c.people_names = None
    monkeypatch.setattr(
        service.users_db, 'get_people_by_ids', lambda *a, **kw: pytest.fail('F used unbounded People projections')
    )
    assert service._attach_synced(UID, 'c2', row, c) == 'recorded'
    assert len(placements) == 3 and len(asked) == 1, reads
    assert asked[0]['max_attempts'] == 1
    assert len(name_reads) == 4
    assert sum(pid.startswith('c2-') for pid in name_reads) == 2
    assert sum(pid.startswith('c4-') for pid in name_reads) == 2
    record_property('document_reads', len(reads))
    assert len(reads) <= 26, reads
    if answer != 0.05:
        # Non-close outcomes include both new unplaced-link rechecks; optimization-off/owner-reuse-off
        # configurations retain their existing rereads.
        assert len(reads) <= 15, reads
    if answer == 0.05:
        assert store.rows[('users', UID, 'episodes', first['id'])]['status'] == 'closed'
        assert store.transactions[-1]._max_attempts == 1
        assert placements == [{'new_occasion': True}] * 3
    # A separate decision with the same collaborators is not suppressed by the prior decision's cache.
    assert c.extras == {}


@pytest.mark.parametrize('case', ['crowded_timeline', 'many_members', 'recovered_owner', 'redirected_owner'])
def test_synced_f_unbounded_owners_keep_control_without_jev(store, monkeypatch, case):
    first = _first_episode(store)
    owner = store.rows[('users', UID, 'episodes', first['id'])]
    _store_row(store, 'c2', SECOND, minutes=12)
    if case == 'crowded_timeline':
        store.rows[('users', UID, 'episodes', 'other')] = {**owner, 'started_at': T0 + timedelta(minutes=1)}
    elif case == 'many_members':
        owner['conversation_ids'] = ['c1', 'a', 'b', 'c']
    elif case == 'recovered_owner':
        owner['recovered_conversation_ids'] = ['c1']
    else:
        owner['recorded_merged_into'] = 'redirect'
    reads, control = [], []
    _bounded_query_fake(store, monkeypatch, reads)
    monkeypatch.setattr(service, 'attach_recorded', lambda *a, **kw: control.append(kw) or first)
    row = store.rows[('users', UID, 'conversations', 'c2')]
    c = _c(store, minutes=13, ask=lambda *a, **kw: pytest.fail('unbounded decision asked Jev'))
    service._attach_recorded_synced(UID, 'c2', row, row['started_at'], row['finished_at'], c)
    assert control == [{}] and len(reads) <= 2


@pytest.mark.parametrize('race', ['members', 'recovered'])
def test_synced_f_close_rechecks_read_budget_inside_the_transaction(store, monkeypatch, race):
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument

    first = _first_episode(store)
    owner = store.rows[('users', UID, 'episodes', first['id'])]
    if race == 'members':
        owner['conversation_ids'] = ['c1', 'a', 'b', 'c']
    else:
        owner['recovered_conversation_ids'] = ['c1']
    reads = []
    read = StrictFirestoreDocument.get

    def counted(ref, *a, **kw):
        reads.append(ref.path)
        return read(ref, *a, **kw)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', counted)
    with pytest.raises(EpisodeConflict, match='f_close_read_budget'):
        episodes_db.close_episode(
            UID, first['id'], 'moved_on', closed_at=T0 + timedelta(minutes=12), firestore_client=store, synced_f=True
        )
    assert len(reads) == 3
    assert not store.transactions[-1].has_written
    assert store.transactions[-1]._max_attempts == 1


def test_synced_f_owner_read_does_not_follow_a_racing_redirect(store, monkeypatch):
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument

    first = _first_episode(store)
    store.rows[('users', UID, 'episodes', first['id'])]['recorded_merged_into'] = 'other'
    reads = []
    read = StrictFirestoreDocument.get

    def counted(ref, *a, **kw):
        reads.append(ref.path)
        return read(ref, *a, **kw)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', counted)
    assert episodes_db.get_episode(UID, first['id'], firestore_client=store, follow_redirects=False) is None
    assert len(reads) == 1


def test_a_marker_that_loses_the_cas_rereads_and_merges_into_the_fresh_live_episode(monkeypatch):
    """A live episode is written on every moment, so the attach-time version is often stale by the marker write."""
    fallbacks, commits = [], []
    monkeypatch.setattr(f_join, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))
    fresh = {
        'id': 'e1',
        'status': 'live',
        'state_version': 4,
        'conversation_ids': ['c1', 'c2'],
        'pending_boundary': {'c0': {'gap_seconds': 300.0}},
    }

    def commit(uid, **kwargs):
        commits.append(kwargs)
        if kwargs['expected_version'] != fresh['state_version']:
            raise EpisodeConflict('state_version_changed')
        return {}

    monkeypatch.setattr(f_join.episodes_db, 'commit_moment', commit)
    monkeypatch.setattr(f_join.episodes_db, 'get_episode', lambda *a, **k: dict(fresh))
    placed = {'id': 'e1', 'status': 'live', 'state_version': 2, 'conversation_ids': ['c1', 'c2']}
    decision = policy.Boundary(policy.ASK, gap_seconds=720.0, source_changed=False)
    f_join.mark_pending(UID, placed, placed, 'c2', decision, {}, firestore_client=None)
    assert [c['expected_version'] for c in commits] == [2, 4]
    pending = commits[-1]['updates']['pending_boundary']
    # The retry keeps a concurrent writer's marker instead of overwriting it from the stale copy.
    assert set(pending) == {'c0', 'c2'} and pending['c2']['variant'] == config.F_JOIN_VARIANT
    assert fallbacks == []


@pytest.mark.parametrize(
    'fresh',
    [
        None,
        {'id': 'e1', 'status': 'closed', 'state_version': 3, 'conversation_ids': ['c1', 'c2']},
        {'id': 'e1', 'status': 'live', 'state_version': 3, 'conversation_ids': ['c1']},
        {
            'id': 'e1',
            'status': 'live',
            'state_version': 3,
            'conversation_ids': ['c1', 'c2'],
            'pending_boundary': {'c2': {}},
        },
    ],
)
def test_a_marker_stops_retrying_once_the_join_no_longer_stands(monkeypatch, fresh):
    fallbacks, commits = [], []
    monkeypatch.setattr(f_join, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))

    def commit(uid, **kwargs):
        commits.append(kwargs)
        raise EpisodeConflict('current_episode_changed')

    monkeypatch.setattr(f_join.episodes_db, 'commit_moment', commit)
    monkeypatch.setattr(f_join.episodes_db, 'get_episode', lambda *a, **k: fresh)
    placed = {'id': 'e1', 'status': 'live', 'state_version': 2, 'conversation_ids': ['c1', 'c2']}
    decision = policy.Boundary(policy.ASK, gap_seconds=720.0, source_changed=False)
    f_join.mark_pending(UID, placed, placed, 'c2', decision, {}, firestore_client=None)
    assert len(commits) == 1
    assert [item['reason'] for item in fallbacks] == ['other']


def test_a_marker_gives_up_after_bounded_retries(monkeypatch):
    fallbacks, commits = [], []
    monkeypatch.setattr(f_join, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))
    versions = iter(range(10, 20))

    def commit(uid, **kwargs):
        commits.append(kwargs)
        raise EpisodeConflict('state_version_changed')

    monkeypatch.setattr(f_join.episodes_db, 'commit_moment', commit)
    monkeypatch.setattr(
        f_join.episodes_db,
        'get_episode',
        lambda *a, **k: {'id': 'e1', 'status': 'live', 'state_version': next(versions), 'conversation_ids': ['c2']},
    )
    placed = {'id': 'e1', 'status': 'live', 'state_version': 2, 'conversation_ids': ['c2']}
    decision = policy.Boundary(policy.ASK, gap_seconds=720.0, source_changed=False)
    f_join.mark_pending(UID, placed, placed, 'c2', decision, {}, firestore_client=None)
    assert len(commits) == f_join.MARK_PENDING_ATTEMPTS
    assert len(fallbacks) == 1
