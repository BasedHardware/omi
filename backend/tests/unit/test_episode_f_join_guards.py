"""Flag-off parity, read-time processing visibility and bounded F predecessor reads."""

import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.unit.test_episode_f_join import (
    UID,
    T0,
    FIRST,
    SECOND,
    _env,
    store,
    _c,
    _moment,
    _store_row,
    _first_episode,
    _attach,
)
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument
from config import episodes as config
from database import episodes as episodes_db, episode_timeline
from utils import omi_flags
from utils.episodes import f_join, metrics, policy, service


@pytest.mark.parametrize('hidden_field', ['discarded_conversation_ids', 'duplicate_conversation_ids'])
def test_predecessor_selection_excludes_episode_hidden_members(hidden_field):
    episode = {
        'conversation_ids': ['visible', 'hidden', 'candidate'],
        'member_activity': {'visible': T0, 'hidden': T0 + timedelta(minutes=2)},
        hidden_field: ['hidden'],
    }
    assert f_join.latest_member(episode, 'candidate') == 'visible'


def test_explicitly_pinned_absence_never_selects_a_later_attached_earlier_recording(store, monkeypatch):
    marked = []
    monkeypatch.setattr(episodes_db, 'commit_moment', lambda *a, **kw: marked.append(kw['updates']))
    owner = {
        'id': 'e1',
        'status': 'live',
        'state_version': 1,
        'conversation_ids': ['c1'],
        'discarded_conversation_ids': ['c1'],
        'member_activity': {'c1': T0},
    }
    placed = {**owner, 'conversation_ids': ['c1', 'c2']}
    f_join.mark_pending(UID, owner, placed, 'c2', policy.Boundary(policy.ASK, gap_seconds=720), {}, store)
    marker = marked[0]['pending_boundary']['c2']
    assert marker['previous'] is None
    _store_row(store, 'c3', FIRST, minutes=5)
    current = {
        **placed,
        'conversation_ids': ['c1', 'c2', 'c3'],
        'member_activity': {'c1': T0, 'c2': T0 + timedelta(minutes=12), 'c3': T0 + timedelta(minutes=5)},
    }
    asked = []
    result = f_join.settle(
        UID,
        current,
        'c2',
        marker,
        [],
        _c(store, minutes=13, ask=lambda *a, **kw: asked.append(a)),
        started_at=T0 + timedelta(minutes=12),
    )
    assert result.action == policy.CONTINUE and asked == []


def test_legacy_marker_without_predecessor_key_can_use_a_retained_member(store):
    _store_row(store, 'c1', FIRST, minutes=0)
    assert 'okay lunch' in f_join.previous_transcript(
        UID, {'conversation_ids': ['c1', 'c2']}, 'c2', {}, _c(store, minutes=13)
    )


@pytest.mark.parametrize(
    'patch',
    [
        {'discarded': True},
        {'deleted': True},
        {'sync_merged_into': 'survivor'},
        {'dream_duplicate_of': 'survivor'},
        {'is_locked': True},
        {'data_protection_level': 'private'},
        {'data_protection_level': None},
        {'is_locked': None},
        {'discarded': None},
        {'deleted': None},
        {'status': None},
        {'status': 'failed'},
        {'deferred': True},
        {'processing_deferred': True, 'deferred': False, 'status': 'completed'},
        {'processing_deferred': None},
        {'processing_deferred': 'false'},
        {'processing_deferred': 0},
        {'processing_deferred': ''},
        {'processing_deferred': []},
        {'processing_deferred': {}},
        {'processing_state': 'local_pending'},
        {'terminal_no_derived_effects': True},
        {'client_processing': {'state': 'pending'}},
        {'summary_blocked_reason': 'local_only'},
        {'sync_processing_hold': {'held': True}},
        {'sync_processing_hold': None},
        {'sync_processing_hold': {'held': None}},
        {'owner_uid': 'another-owner'},
        {'uid': 'another-owner'},
    ],
)
def test_visibility_is_rechecked_at_settle_and_unknown_keeps_join_without_jev(store, patch):
    _first_episode(store)
    _attach(store, 'c2', minutes=12)
    # Visibility changes after the predecessor was pinned at mark time.
    store.rows[('users', UID, 'conversations', 'c1')].update(patch)
    asked = []
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert (
        f_join.previous_transcript(UID, episode, 'c2', episode['pending_boundary']['c2'], _c(store, minutes=13)) == ''
    )
    result = f_join.settle(
        UID,
        episode,
        'c2',
        episode['pending_boundary']['c2'],
        [],
        _c(store, minutes=13, ask=lambda *a, **kw: asked.append(a)),
        started_at=T0 + timedelta(minutes=12),
    )
    assert result.action == policy.CONTINUE
    assert asked == []


@pytest.mark.parametrize('change', ['discarded_conversation_ids', 'duplicate_conversation_ids', 'removed', 'missing'])
def test_pinned_predecessor_must_still_be_retained_and_exist(store, change):
    _store_row(store, 'c1', FIRST, minutes=0)
    episode = {'conversation_ids': ['c1', 'c2']}
    if change == 'removed':
        episode['conversation_ids'] = ['c2']
    elif change == 'missing':
        store.rows.pop(('users', UID, 'conversations', 'c1'))
    else:
        episode[change] = ['c1']
    assert f_join.previous_transcript(UID, episode, 'c2', {'previous': 'c1'}, _c(store, minutes=13)) == ''


def test_owner_private_visibility_can_feed_f(store):
    _store_row(store, 'c1', FIRST, minutes=0)
    text = f_join.previous_transcript(
        UID, {'conversation_ids': ['c1', 'c2']}, 'c2', {'previous': 'c1'}, _c(store, minutes=13)
    )
    assert 'okay lunch' in text


@pytest.mark.parametrize('failure', ['read', 'predicate', 'decode'])
def test_unknown_predecessor_checks_skip_jev(store, monkeypatch, failure):
    _first_episode(store)
    _attach(store, 'c2', minutes=12)

    def broken(*a, **kw):
        raise RuntimeError('unknown')

    target = {
        'read': 'get_conversation_raw_snapshot',
        'predicate': 'is_visible_conversation',
        'decode': 'decode_transcript_segments_blob',
    }[failure]
    monkeypatch.setattr(f_join.conversations_db, target, broken)
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    asked = []
    result = f_join.settle(
        UID,
        episode,
        'c2',
        episode['pending_boundary']['c2'],
        [],
        _c(store, minutes=13, ask=lambda *a, **kw: asked.append(a)),
        started_at=T0 + timedelta(minutes=12),
    )
    assert result.action == policy.CONTINUE and asked == []


@pytest.mark.parametrize('blob', [None, 'not-encrypted-transcript', b'not-compressed-transcript'])
def test_undecodable_predecessor_keeps_join_without_jev(store, blob):
    _first_episode(store)
    _attach(store, 'c2', minutes=12)
    store.rows[('users', UID, 'conversations', 'c1')].update(
        transcript_segments=blob, transcript_segments_compressed=True
    )
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    asked = []
    result = f_join.settle(
        UID,
        episode,
        'c2',
        episode['pending_boundary']['c2'],
        [],
        _c(store, minutes=13, ask=lambda *a, **kw: asked.append(a)),
        started_at=T0 + timedelta(minutes=12),
    )
    assert result.action == policy.CONTINUE and asked == []


def test_people_document_reads_are_capped_after_tail_truncation(store, monkeypatch):
    _store_row(store, 'c1', FIRST, minutes=0)
    row = store.rows[('users', UID, 'conversations', 'c1')]
    row['transcript_segments'] = [
        {'text': 'outside the tail', 'start': 0, 'person_id': 'outside'},
        *[{'text': 'x' * 1000, 'start': i + 1, 'person_id': f'p{i}'} for i in range(30)],
    ]
    reads = []
    original_get = StrictFirestoreDocument.get

    def get(ref, *a, **kw):
        reads.append(ref.path)
        if ref.path[-2] == 'people':
            assert kw == {'field_paths': ['name']}
            return SimpleNamespace(to_dict=lambda: {'name': 'A person'})
        return original_get(ref, *a, **kw)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    c = _c(store, minutes=13)
    c.people_names = None  # Exercise the production leaf read, not a counting callback.
    text = f_join.previous_transcript(UID, {'conversation_ids': ['c1', 'c2']}, 'c2', {'previous': 'c1'}, c)
    people = [path[-1] for path in reads if path[-2] == 'people']
    assert len(people) == len(set(people)) == config.F_JOIN_PEOPLE_READ_LIMIT
    assert set(people) <= {f'p{i}' for i in range(18, 30)}
    assert [path for path in reads if path[-2] == 'conversations'] == [('users', UID, 'conversations', 'c1')]
    assert text


def test_zero_rollout_and_threshold_are_strict_with_stable_uid_hash(monkeypatch):
    rule = omi_flags.FlagRule(key=config.F_JOIN_FLAG_KEY, active=True, rollout_percentage=0)
    monkeypatch.setattr(omi_flags, 'rollout_hash', lambda *a: 0.0)
    assert not omi_flags.evaluate(rule, UID).enabled
    rule = omi_flags.FlagRule(key=config.F_JOIN_FLAG_KEY, active=True, rollout_percentage=25)
    monkeypatch.setattr(omi_flags, 'rollout_hash', lambda *a: 0.25)
    assert not omi_flags.evaluate(rule, UID).enabled
    monkeypatch.undo()
    uids = [f'cohort-{i}' for i in range(1000)]
    at25 = {uid for uid in uids if omi_flags.evaluate(rule, uid).enabled}
    assert at25 == {uid for uid in uids if omi_flags.evaluate(rule, uid).enabled}
    at50 = {
        uid
        for uid in uids
        if omi_flags.evaluate(omi_flags.FlagRule(key=rule.key, active=True, rollout_percentage=50), uid).enabled
    }
    assert at25 < at50


def test_full_rollout_includes_hash_one_and_keeps_explicit_allow_and_deny(monkeypatch):
    monkeypatch.setattr(omi_flags, 'rollout_hash', lambda *a: 1.0)
    assert omi_flags.evaluate(omi_flags.FlagRule(key='k', active=True, rollout_percentage=100), UID).enabled
    assert omi_flags.evaluate(omi_flags.FlagRule(key='k', active=True, allow_uids=frozenset({UID})), UID).enabled
    assert not omi_flags.evaluate(
        omi_flags.FlagRule(
            key='k', active=True, rollout_percentage=100, allow_uids=frozenset({UID}), deny_uids=frozenset({UID})
        ),
        UID,
    ).enabled


@pytest.mark.parametrize('mode', ['kill', 'inactive', 'zero', 'no_rule'])
def test_off_does_not_stamp_an_episode_or_evaluate_admission(monkeypatch, mode):
    monkeypatch.setenv(config.EPISODE_F_JOIN_PERCENT_ENV, '0')
    if mode == 'kill':
        monkeypatch.setenv(config.EPISODE_F_JOIN_ENABLED_ENV, 'off')
        monkeypatch.setattr(omi_flags, 'snapshot', lambda: pytest.fail('kill must not read the flag store'))
    elif mode in {'inactive', 'zero'}:
        rule = omi_flags.FlagRule(
            key=config.F_JOIN_FLAG_KEY, active=mode == 'zero', rollout_percentage=0 if mode == 'zero' else 100
        )
        monkeypatch.setattr(omi_flags, 'snapshot', lambda: omi_flags.Snapshot(1, {rule.key: rule}))
    monkeypatch.setattr(omi_flags, 'resolve', lambda *a: pytest.fail('off stamping must not resolve admission'))
    monkeypatch.setattr(omi_flags, 'evaluate', lambda *a: pytest.fail('off stamping must not evaluate admission'))
    assert f_join.arm_fields(UID) == {}


def test_positive_rollout_stamps_controls_for_non_admitted_users(monkeypatch):
    rule = omi_flags.FlagRule(key=config.F_JOIN_FLAG_KEY, active=True, rollout_percentage=5)
    monkeypatch.setattr(omi_flags, 'snapshot', lambda: omi_flags.Snapshot(1, {rule.key: rule}))
    monkeypatch.setattr(omi_flags, 'rollout_hash', lambda *a: 0.5)
    assert f_join.arm_fields(UID) == {'f_join_arm': 'control'}


class Captured(BaseException):
    pass


def opening_payload(kind, store, monkeypatch, mode='kill'):
    """Capture the pre-persistence write bytes, with deterministic id/time/model output."""
    monkeypatch.setenv('EPISODE_RECORDED_TIME_ENABLED', 'false')
    monkeypatch.setenv(config.EPISODE_F_JOIN_ENABLED_ENV, 'off' if mode == 'kill' else 'on')
    monkeypatch.setenv(config.EPISODE_F_JOIN_PERCENT_ENV, '0')
    if mode in {'inactive', 'zero'}:
        rule = omi_flags.FlagRule(
            key=config.F_JOIN_FLAG_KEY, active=mode == 'zero', rollout_percentage=0 if mode == 'zero' else 100
        )
        monkeypatch.setattr(omi_flags, 'snapshot', lambda: omi_flags.Snapshot(1, {rule.key: rule}))
    monkeypatch.setattr(episodes_db, 'new_episode_id', lambda: 'fixed-episode')
    monkeypatch.setattr(service, 'uuid4', lambda: SimpleNamespace(hex='0123456789abcdef'))
    monkeypatch.setattr(service.episode_language, 'detected_state_language', lambda *a, **kw: 'en')
    payloads = []

    def capture(*a, **kw):
        payloads.append(kw['new_episode'])
        raise Captured

    monkeypatch.setattr(episodes_db, 'commit_moment', capture)
    monkeypatch.setattr(episode_timeline, 'attach_recorded', capture)
    c = _c(store, minutes=1)
    with pytest.raises(Captured):
        if kind == 'attach':
            service._attach_once(UID, 'c1', 'omi', T0, c)
        elif kind == 'record':
            service._record_moment_once(UID, _moment('c1', minutes=0, text=FIRST), c)
        else:
            service.attach_recorded(UID, 'c1', {'source': 'omi'}, T0, T0 + timedelta(minutes=1), c)
    return json.dumps(payloads[0], sort_keys=True, separators=(',', ':'), default=lambda value: value.isoformat())


@pytest.mark.parametrize('kind', ['attach', 'record', 'recorded'])
@pytest.mark.parametrize('mode', ['kill', 'inactive', 'zero', 'no_rule'])
def test_flag_off_opening_payload_is_byte_identical_to_main(store, monkeypatch, kind, mode):
    expected = json.loads((Path(__file__).parent / 'fixtures' / 'episode_f_flag_off_payloads.json').read_text())
    assert opening_payload(kind, store, monkeypatch, mode) == expected[kind]


@pytest.mark.parametrize('with_spans', [True, False])
def test_flag_off_legacy_detach_keeps_main_reads_and_recorded_end(store, monkeypatch, with_spans):
    monkeypatch.setenv(config.EPISODE_F_JOIN_ENABLED_ENV, 'off')
    first = _first_episode(store)
    _store_row(store, 'c2', SECOND, minutes=12)
    _attach(store, 'c2', minutes=12)
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    if not with_spans:
        for cid in ('c1', 'c2'):
            store.rows[('users', UID, 'conversations', cid)] = {}
    reads = []
    original_get = StrictFirestoreDocument.get

    def get(ref, *a, **kw):
        if ref.path[-2] == 'conversations':
            reads.append(ref.path[-1])
        return original_get(ref, *a, **kw)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    closed = episodes_db.close_episode(
        UID,
        first['id'],
        'moved_on',
        closed_at=T0 + timedelta(minutes=12),
        extra={
            'conversation_ids': ['c1'],
            'member_activity': {'c1': T0 + timedelta(minutes=1)},
            'last_activity_at': T0 + timedelta(minutes=1),
        },
        firestore_client=store,
    )
    assert reads == ['c1', 'c2']
    # SECOND has two five-second speech segments; finished_at is not its recorded end.
    assert closed['recorded_end'] == T0 + timedelta(minutes=12, seconds=10 if with_spans else 0)


@pytest.mark.parametrize('recover_on_retry', [False, True])
def test_actual_f_detach_is_observed_after_retries_and_orphan_is_counted_and_logged(
    store, monkeypatch, caplog, recover_on_retry
):
    _first_episode(store)
    _store_row(store, 'c2', SECOND, minutes=12)
    _attach(store, 'c2', minutes=12)
    original = episodes_db.commit_moment
    failed = []

    def commit(*a, **kw):
        if kw.get('expected_episode_id') is None and (not recover_on_retry or not failed):
            failed.append(True)
            if recover_on_retry:
                # A competing writer wins the successor before our attempt observes its conflict.
                original(*a, **kw)
            raise episodes_db.EpisodeConflict('successor write conflict')
        return original(*a, **kw)

    monkeypatch.setattr(episodes_db, 'commit_moment', commit)
    counter = metrics.EPISODE_BOUNDARY_TOTAL.labels(outcome='f_orphan')
    before = counter._value.get()
    result = service.record_moment(
        UID,
        _moment('c2', minutes=12, text=SECOND),
        _c(store, minutes=13, ask=lambda *a, **kw: SimpleNamespace(noul=lambda name: 0.0)),
    )
    assert failed
    if recover_on_retry:
        assert result in {'applied', 'skipped_applied'}
        assert counter._value.get() == before
        assert 'event=episode_f_join_orphan outcome=no_live_successor' not in caplog.text
    else:
        assert counter._value.get() == before + 1
        assert caplog.text.count('event=episode_f_join_orphan outcome=no_live_successor') == 1


def test_orphan_observation_has_two_read_bound_and_content_free_error_log(store, monkeypatch, caplog):
    first = _first_episode(store)
    reads = []
    original_get = StrictFirestoreDocument.get

    def get(ref, *a, **kw):
        reads.append(ref.path)
        return original_get(ref, *a, **kw)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    before = metrics.EPISODE_BOUNDARY_TOTAL.labels(outcome='f_orphan')._value.get()
    f_join.record_orphans(UID, {'c1'}, _c(store, minutes=1))
    assert len(reads) == 2
    assert metrics.EPISODE_BOUNDARY_TOTAL.labels(outcome='f_orphan')._value.get() == before
    store.rows[('users', UID, 'episodes', first['id'])]['status'] = 'closed'
    reads.clear()
    caplog.clear()
    f_join.record_orphans(UID, {'c1'}, _c(store, minutes=1))
    assert len(reads) == 2
    assert metrics.EPISODE_BOUNDARY_TOTAL.labels(outcome='f_orphan')._value.get() == before + 1
    assert 'event=episode_f_join_orphan outcome=no_live_successor' in caplog.text
    assert UID not in caplog.text


def test_post_close_exception_still_counts_a_detached_candidate_without_successor(store, monkeypatch, caplog):
    _first_episode(store)
    _store_row(store, 'c2', SECOND, minutes=12)
    _attach(store, 'c2', minutes=12)

    def fail(*a, **kw):
        raise RuntimeError('post-close work failed')

    monkeypatch.setattr(service.composer, 'schedule', fail)
    before = metrics.EPISODE_BOUNDARY_TOTAL.labels(outcome='f_orphan')._value.get()
    assert (
        service.record_moment(
            UID,
            _moment('c2', minutes=12, text=SECOND),
            _c(store, minutes=13, ask=lambda *a, **kw: SimpleNamespace(noul=lambda name: 0.0)),
        )
        == 'error'
    )
    assert metrics.EPISODE_BOUNDARY_TOTAL.labels(outcome='f_orphan')._value.get() == before + 1
    assert 'event=episode_f_join_orphan outcome=no_live_successor' in caplog.text


def test_unknown_orphan_check_is_reported_separately_and_empty_checks_do_no_reads(store, monkeypatch, caplog):
    def broken(*a, **kw):
        raise RuntimeError('unknown')

    monkeypatch.setattr(episodes_db, 'get_episode_owner_snapshot', broken)
    before = metrics.EPISODE_BOUNDARY_TOTAL.labels(outcome='f_orphan_check_error')._value.get()
    f_join.record_orphans(UID, set(), _c(store, minutes=1))
    assert metrics.EPISODE_BOUNDARY_TOTAL.labels(outcome='f_orphan_check_error')._value.get() == before
    f_join.record_orphans(UID, {'c1'}, _c(store, minutes=1))
    assert metrics.EPISODE_BOUNDARY_TOTAL.labels(outcome='f_orphan_check_error')._value.get() == before + 1
    assert 'event=episode_f_join_orphan outcome=check_failed' in caplog.text


def test_safety_reads_never_follow_episode_redirects_or_exceed_their_bound(store, monkeypatch, caplog):
    first = _first_episode(store)
    store.rows[('users', UID, 'episodes', first['id'])]['recorded_merged_into'] = 'another-episode'
    reads = []
    original_get = StrictFirestoreDocument.get

    def get(ref, *a, **kw):
        reads.append(ref.path)
        return original_get(ref, *a, **kw)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    assert not f_join._split_still_clear(UID, first, 'c1', T0 + timedelta(minutes=12), _c(store, minutes=13))
    assert len(reads) == 1
    reads.clear()
    before = metrics.EPISODE_BOUNDARY_TOTAL.labels(outcome='f_orphan')._value.get()
    unknown = metrics.EPISODE_BOUNDARY_TOTAL.labels(outcome='f_orphan_check_error')._value.get()
    f_join.record_orphans(UID, {'c1'}, _c(store, minutes=13))
    assert len(reads) == 2
    assert metrics.EPISODE_BOUNDARY_TOTAL.labels(outcome='f_orphan')._value.get() == before
    assert metrics.EPISODE_BOUNDARY_TOTAL.labels(outcome='f_orphan_check_error')._value.get() == unknown + 1


def test_episode_removed_while_jev_answers_keeps_the_time_join(store):
    episode = _first_episode(store)
    _attach(store, 'c2', minutes=12)
    episode = episodes_db.get_current_episode(UID, firestore_client=store)

    def ask(*a, **kw):
        store.rows.pop(('users', UID, 'episodes', episode['id']))
        return SimpleNamespace(noul=lambda name: 0.0)

    result = f_join.settle(
        UID,
        episode,
        'c2',
        episode['pending_boundary']['c2'],
        [],
        _c(store, minutes=13, ask=ask),
        started_at=T0 + timedelta(minutes=12),
    )
    assert result.action == policy.CONTINUE
