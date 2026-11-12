"""Completed memos and rollback paths preserve episode placement and recovery."""

from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config import episode_attach as flags
from database import episode_attach_memo, episode_timeline, episodes
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreTransaction, StrictFirestoreDocument
from tests.unit.test_episode_live_integrity import lane, row, T0, assert_timeline  # noqa: F401
from utils.conversations.episode_attach_key import content_key, process_snapshot, should_schedule
from utils.episodes import service, capture_groups


def seed(store, cid='same', **changes):
    member = row(cid, recorded_start=T0, recorded_end=T0 + timedelta(seconds=30), **changes)
    member['transcript_segments'] = []
    store.rows[('users', 'u', 'conversations', cid)] = member
    return member


def unexpected(*a, **kw):
    pytest.fail('unchanged attach accessed episode state or wrote data')


@pytest.mark.parametrize('entry', ['finalize', 'intake'])
def test_completed_identical_sync_has_no_episode_reads_or_writes(lane, monkeypatch, entry):
    store, c, _ = lane
    monkeypatch.setattr(service.client_gate, 'client_seen_cached', lambda *_: True)
    member = seed(store)
    assert service._attach_synced('u', 'same', member, c) == 'recorded'
    link = store.rows[('users', 'u', 'episode_links', 'same')]
    assert link['attach_revision'] == link['attach_completed'] == content_key(member)
    before = deepcopy(store.rows)
    monkeypatch.setattr(episode_timeline, 'recorded_candidates', unexpected)
    monkeypatch.setattr(episodes, 'get_episode', unexpected)
    monkeypatch.setattr(episodes, 'get_episode_for_conversation', unexpected)
    monkeypatch.setattr(StrictFirestoreTransaction, 'set', unexpected)
    monkeypatch.setattr(StrictFirestoreTransaction, 'update', unexpected)
    read = StrictFirestoreDocument.get
    reads = []

    def counted(ref, *a, **kw):
        reads.append(ref.path)
        assert ref.path[2] != 'episodes'
        return read(ref, *a, **kw)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', counted)
    outcome = (
        service.attach_synced_intake('u', 'same', member, collaborators=c)
        if entry == 'intake'
        else service._attach_synced('u', 'same', member, c)
    )
    assert outcome == 'attached_unchanged'
    assert [p[2:] for p in reads] == [('episode_links', 'same'), ('conversations', 'same')]
    assert before == store.rows


def test_wal_revision_change_conservatively_falls_through(lane):
    store, c, _ = lane
    member = seed(store, sync_content_revision=1)
    service._attach_synced('u', 'same', member, c)
    member = deepcopy(member)
    stored = store.rows[('users', 'u', 'conversations', 'same')]
    stored['sync_content_revision'] = 19
    updated = {**member, 'sync_content_revision': 19}
    assert content_key(updated) != content_key(member)
    assert service._attach_synced('u', 'same', updated, c) == 'recorded'


@pytest.mark.parametrize('change', ['span', 'text', 'new_member', 'discard', 'delete', 'donor'])
def test_real_changes_bypass_the_memo(lane, monkeypatch, change):
    store, c, _ = lane
    member = seed(store)
    service._attach_synced('u', 'same', member, c)
    incoming = deepcopy(store.rows[('users', 'u', 'conversations', 'same')])
    if change == 'span':
        incoming['recorded_end'] += timedelta(minutes=2)
    elif change == 'text':
        incoming['transcript_segments'] = [{'id': 's', 'start': 0, 'end': 30, 'text': 'new retained speech'}]
    elif change == 'new_member':
        incoming['id'] = 'new'
    elif change in {'discard', 'delete'}:
        incoming['discarded' if change == 'discard' else 'deleted'] = True
    else:
        incoming['sync_merged_from'] = ['old']
    store.rows[('users', 'u', 'conversations', incoming['id'])] = incoming
    repartition = Mock(wraps=episode_timeline.recorded_candidates)
    monkeypatch.setattr(episode_timeline, 'recorded_candidates', repartition)
    outcome = service._attach_synced('u', incoming['id'], incoming, c)
    assert outcome != 'attached_unchanged'
    if change in {'discard', 'delete'}:
        assert outcome == 'skipped_discarded'
    elif change == 'span':
        assert repartition.called
        assert (
            episodes.get_episode_for_conversation('u', 'same', firestore_client=store)['last_activity_at']
            == incoming['recorded_end']
        )
    elif change == 'new_member':
        assert repartition.called
        assert set(episodes.get_episode_for_conversation('u', 'new', firestore_client=store)['conversation_ids']) == {
            'same',
            'new',
        }
    assert_timeline(store)


def test_failed_recovery_does_not_activate_the_memo(lane, monkeypatch):
    store, c, _ = lane
    member = seed(store)
    monkeypatch.setattr(service, '_record_recovered', lambda *a, **kw: 'error')
    service._attach_synced('u', 'same', member, c)
    link = store.rows[('users', 'u', 'episode_links', 'same')]
    assert link['attach_revision'] and not link['attach_completed']
    assert not episode_attach_memo.matches('u', 'same', member, firestore_client=store)
    monkeypatch.setattr(service, '_record_recovered', lambda *a, **kw: 'skipped_applied')
    assert service._attach_synced('u', 'same', member, c) == 'recorded'
    assert episode_attach_memo.matches('u', 'same', member, firestore_client=store)


@pytest.mark.parametrize('mutation', ['deleted', 'discarded', 'repoint', 'text'])
def test_stale_caller_cannot_hit_memo_after_current_row_changes(lane, mutation):
    store, c, _ = lane
    member = seed(store)
    service._attach_synced('u', 'same', member, c)
    current = store.rows[('users', 'u', 'conversations', 'same')]
    if mutation == 'repoint':
        current['episode_id'] = 'other'
    elif mutation == 'text':
        current['transcript_segments'] = [{'id': 'new', 'text': 'later', 'start': 0, 'end': 1}]
    else:
        current[mutation] = True
    assert not episode_attach_memo.matches('u', 'same', member, firestore_client=store)


def test_content_gate_off_restores_full_attach(lane, monkeypatch):
    store, c, _ = lane
    member = seed(store)
    service._attach_synced('u', 'same', member, c)
    monkeypatch.setenv('EPISODE_ATTACH_CONTENT_GATE_ENABLED', 'false')
    assert service._attach_synced('u', 'same', member, c) == 'recorded'


@pytest.mark.parametrize('enabled', [False, True])
def test_membership_writes_only_for_changed_values(lane, monkeypatch, enabled):
    store, _, _ = lane
    monkeypatch.setenv('EPISODE_ATTACH_MEMBERSHIP_DEDUPE_ENABLED', str(enabled))
    store.rows[('users', 'u', 'conversations', 'c')] = {'episode_id': 'e'}
    store.rows[('users', 'u', 'episode_links', 'c')] = {'episode_id': 'e', 'episode_ids': ['e']}
    tx = store.transaction()
    members = episodes.read_memberships(tx, store, 'u', ['c'])
    episodes.write_memberships(tx, store, 'u', 'e', members, T0)
    assert len(tx.sets) == len(tx.updates) == (0 if enabled else 1)
    # A mismatching reverse field still needs repair even when the link is equal.
    store.rows[('users', 'u', 'conversations', 'c')]['episode_id'] = 'old'
    tx = store.transaction()
    members = episodes.read_memberships(tx, store, 'u', ['c'])
    episodes.write_memberships(tx, store, 'u', 'e', members, T0)
    assert len(tx.updates) == 1


@pytest.mark.parametrize('enabled', [False, True])
def test_duplicate_noop_switch(lane, monkeypatch, enabled):
    _, _, _ = lane
    monkeypatch.setenv('EPISODE_ATTACH_DUPLICATES_DEDUPE_ENABLED', str(enabled))
    update = Mock(return_value={})
    monkeypatch.setattr(episodes, 'update_episode', update)
    monkeypatch.setattr(episodes, 'duplicate_memberships_match', lambda *a, **kw: True)
    owner = {'id': 'e', 'conversation_ids': ['c', 'copy'], 'duplicate_conversation_ids': ['copy']}
    capture_groups.join_duplicates('u', owner, 'c', {'capture_group': {'members': [{'id': 'copy'}]}})
    assert update.call_count == (0 if enabled else 1)


@pytest.mark.parametrize(
    'name',
    [
        'optimizations',
        'content_gate',
        'noop_schedule',
        'owner_reuse',
        'membership_dedupe',
        'row_visibility',
        'walk_context',
        'duplicates_dedupe',
    ],
)
def test_switches_default_on_and_explicit_off(monkeypatch, name):
    env = 'EPISODE_ATTACH_' + name.upper() + '_ENABLED'
    monkeypatch.delenv(env, raising=False)
    fn = getattr(flags, name + '_enabled')
    assert fn()
    for value in ['false', 'off', '0', 'no']:
        monkeypatch.setenv(env, value)
        assert not fn()


def test_reprocess_snapshot_catches_in_place_changes():
    before = row('c', episode_id='e')
    obj = SimpleNamespace(model_dump=lambda: before)
    snapshot = process_snapshot(before, obj)
    assert not should_schedule(snapshot, before)
    before['transcript_segments'][0]['text'] = 'changed'
    assert should_schedule(snapshot, before)
    assert should_schedule({**snapshot, 'episode_id': None}, snapshot)
    assert should_schedule(snapshot, {**snapshot, 'episode_id': None})
    assert should_schedule(snapshot, {**snapshot, 'discarded': True})
    assert should_schedule(snapshot, {**snapshot, 'recorded_end': T0 + timedelta(hours=1)})
    assert should_schedule(
        snapshot,
        {**snapshot, 'recorded_start': T0, 'recorded_end': T0 + timedelta(seconds=30), 'clock': 'unknown-clock'},
    )


@pytest.mark.parametrize('enabled', [False, True])
def test_owner_and_visibility_switches_restore_their_reads(lane, monkeypatch, enabled):
    store, c, _ = lane
    member = seed(store)
    monkeypatch.setenv('EPISODE_ATTACH_CONTENT_GATE_ENABLED', 'false')
    monkeypatch.setenv('EPISODE_ATTACH_OWNER_REUSE_ENABLED', str(enabled))
    monkeypatch.setenv('EPISODE_ATTACH_ROW_VISIBILITY_ENABLED', str(enabled))
    owner_read = Mock(wraps=episodes.get_episode_for_conversation)
    monkeypatch.setattr(episodes, 'get_episode_for_conversation', owner_read)
    from utils.episodes import sync_attach

    visibility = Mock(return_value=False)
    monkeypatch.setattr(sync_attach, 'hidden_conversation', visibility)
    assert service._attach_synced('u', 'same', member, c) == 'recorded'
    assert owner_read.call_count == (0 if enabled else 1)
    assert visibility.call_count == (0 if enabled else 1)


@pytest.mark.parametrize('enabled', [False, True])
def test_walk_context_reuses_owner_but_guard_still_reads_current_visibility(lane, monkeypatch, enabled):
    from utils.episodes.recorded_recovery import RecoveryReceipts
    from utils.episodes.moment import MomentInput

    store, c, _ = lane
    member = seed(store)
    service._attach_synced('u', 'same', member, c)
    owner = episodes.get_episode_for_conversation('u', 'same', firestore_client=store)
    receipts = RecoveryReceipts('u', 'same', c, owner)
    receipts.row = member
    moment = MomentInput(
        conversation_id='same',
        source='omi',
        segments=[],
        started_at=T0,
        ended_at=T0,
        trigger='sync_recovery',
        recovery_receipts=receipts,
    )
    monkeypatch.setenv('EPISODE_ATTACH_WALK_CONTEXT_ENABLED', str(enabled))
    get_owner = Mock(wraps=episodes.get_episode)
    hidden = Mock(return_value=False)
    monkeypatch.setattr(episodes, 'get_episode', get_owner)
    monkeypatch.setattr(service, 'hidden_conversation', hidden)
    service.record_moment('u', moment, c, member_episode_id=owner['id'])
    assert get_owner.call_count == hidden.call_count == (0 if enabled else 1)
    # A stored deletion still fences a notes CAS that used a cached visible row.
    store.rows[('users', 'u', 'conversations', 'same')]['deleted'] = True
    with pytest.raises(episodes.EpisodeConflict, match='conversation_hidden'):
        episodes.update_episode(
            'u',
            owner['id'],
            expected_version=owner['state_version'],
            updates={'title': 'must not land'},
            recovery_conversation_id='same',
            firestore_client=store,
        )


def test_memo_read_failure_falls_through(lane, monkeypatch):
    store, _, _ = lane
    member = seed(store)
    monkeypatch.setattr(
        episode_attach_memo,
        'run_preloaded_transactional',
        Mock(side_effect=RuntimeError('synthetic outage')),
    )
    fallback = Mock()
    monkeypatch.setattr(episode_attach_memo, 'record_fallback', fallback)
    assert not episode_attach_memo.matches('u', 'same', member, firestore_client=store)
    assert fallback.call_count == 1


def test_scheduling_gate_runs_before_submit_and_preserves_first_finalize(lane, monkeypatch):
    from utils.episodes import finalize

    store, c, _ = lane
    member = seed(store, sync_content_revision=4)
    service._attach_synced('u', 'same', member, c)
    fresh = deepcopy(store.rows[('users', 'u', 'conversations', 'same')])
    monkeypatch.setattr(episode_attach_memo, 'get_firestore_client', lambda: store)
    submit = Mock()
    monkeypatch.setattr(finalize, 'submit_with_context', submit)
    monkeypatch.setattr(finalize, 'lifecycle_executor', lambda *a, **kw: object())
    # Intake may skip now, but finalize must emit its FIRST compose signal.
    finalize.schedule_synced_intake_attach('u', 'same', fresh)
    assert submit.call_count == 0
    finalize.schedule_after_finalization('u', 'same', finalize.ProcessingTrigger.SYNC_UPDATE, row=fresh)
    assert submit.call_count == 1
    episode_attach_memo.complete('u', 'same', fresh, None, finalized=True, firestore_client=store)
    finalize.schedule_after_finalization('u', 'same', finalize.ProcessingTrigger.SYNC_UPDATE, row=fresh)
    assert submit.call_count == 1
    monkeypatch.setenv('EPISODE_ATTACH_CONTENT_GATE_ENABLED', 'false')
    finalize.schedule_after_finalization('u', 'same', finalize.ProcessingTrigger.SYNC_UPDATE, row=fresh)
    assert submit.call_count == 2


def test_discard_after_intake_same_revision_still_schedules_and_ends_member(lane, monkeypatch):
    from utils.episodes import finalize

    store, c, _ = lane
    member = seed(store, sync_content_revision=7)
    service._attach_synced('u', 'same', member, c)
    fresh = deepcopy(store.rows[('users', 'u', 'conversations', 'same')])
    episode_attach_memo.complete('u', 'same', fresh, None, finalized=True, firestore_client=store)
    old_key = content_key(fresh)
    fresh['discarded'] = True  # Discard does not bump the revision.
    store.rows[('users', 'u', 'conversations', 'same')] = fresh
    assert fresh['sync_content_revision'] == member['sync_content_revision'] == 7
    assert content_key(fresh) != old_key
    monkeypatch.setattr(episode_attach_memo, 'matches', unexpected)
    assert not finalize.skip_unchanged_schedule('u', 'same', fresh, finalized=True)
    owner_id = fresh['episode_id']
    assert (
        service.on_conversation_finalized('u', 'same', fresh, trigger='sync_update', collaborators=c)
        == 'skipped_discarded'
    )
    owner = episodes.get_episode('u', owner_id, firestore_client=store)
    assert 'same' in owner['discarded_conversation_ids']


def test_smart_merge_same_revision_cannot_skip_absorbed_donor_repoint(lane, monkeypatch):
    from utils.episodes import finalize

    store, c, _ = lane
    donor = seed(store, 'donor', sync_content_revision=7)
    survivor = seed(store, 'survivor', sync_content_revision=7)
    service._attach_synced('u', 'donor', donor, c)
    service._attach_synced('u', 'survivor', survivor, c)
    fresh = deepcopy(store.rows[('users', 'u', 'conversations', 'survivor')])
    episode_attach_memo.complete('u', 'survivor', fresh, None, finalized=True, firestore_client=store)
    monkeypatch.setattr(episode_attach_memo, 'matches', unexpected)
    assert not finalize.skip_unchanged_schedule('u', 'survivor', fresh, finalized=True, absorbed_from='donor')
    assert service._attach_synced('u', 'survivor', fresh, c, absorbed_from='donor') != 'attached_unchanged'
    owner = episodes.get_episode_for_conversation('u', 'survivor', firestore_client=store)
    assert owner['conversation_ids'] == ['survivor']
    assert_timeline(store)


def test_pending_to_failed_same_revision_changes_key_and_schedules(lane, monkeypatch):
    from utils.episodes import finalize

    store, c, _ = lane
    member = seed(store, sync_content_revision=7, episode_transcription_pending_at=T0)
    service._attach_synced('u', 'same', member, c)
    fresh = deepcopy(store.rows[('users', 'u', 'conversations', 'same')])
    episode_attach_memo.complete('u', 'same', fresh, None, finalized=True, firestore_client=store)
    failed = {**fresh, 'summary_blocked_reason': 'transcription_failed', 'record_upload_failed': True}
    assert content_key(fresh) != content_key(failed)
    monkeypatch.setattr(episode_attach_memo, 'get_firestore_client', lambda: store)
    assert not finalize.skip_unchanged_schedule('u', 'same', failed, finalized=True)


@pytest.mark.parametrize('gate_during_discard', ['true', 'false'])
def test_restore_cannot_reuse_the_pre_discard_completed_memo(lane, monkeypatch, gate_during_discard):
    from utils.episodes import finalize

    store, c, _ = lane
    member = seed(store, sync_content_revision=7, sync_relevance_user_kept=True)
    service._attach_synced('u', 'same', member, c)
    visible = deepcopy(store.rows[('users', 'u', 'conversations', 'same')])
    episode_attach_memo.complete('u', 'same', visible, None, finalized=True, firestore_client=store)
    monkeypatch.setenv('EPISODE_ATTACH_CONTENT_GATE_ENABLED', gate_during_discard)
    hidden = {**visible, 'discarded': True, 'sync_relevance_user_kept': False}
    store.rows[('users', 'u', 'conversations', 'same')] = hidden
    assert service._attach_synced('u', 'same', hidden, c) == 'skipped_discarded'
    # Re-enabling the gate after rollback must also reject the old stamp.
    monkeypatch.setenv('EPISODE_ATTACH_CONTENT_GATE_ENABLED', 'true')
    # A second user restore has exactly the original visible key/revision.
    store.rows[('users', 'u', 'conversations', 'same')] = visible
    monkeypatch.setattr(episode_attach_memo, 'get_firestore_client', lambda: store)
    assert not finalize.skip_unchanged_schedule('u', 'same', visible, finalized=True)
    assert not episode_attach_memo.matches('u', 'same', visible, firestore_client=store)


def test_scheduling_hit_validates_current_conversation_and_never_submits(lane, monkeypatch):
    from utils.episodes import finalize

    store, c, _ = lane
    member = seed(store, sync_content_revision=7)
    service._attach_synced('u', 'same', member, c)
    fresh = deepcopy(store.rows[('users', 'u', 'conversations', 'same')])
    episode_attach_memo.complete('u', 'same', fresh, None, finalized=True, firestore_client=store)
    monkeypatch.setattr(episode_attach_memo, 'get_firestore_client', lambda: store)
    read = StrictFirestoreDocument.get
    reads = []

    def counted(ref, *a, **kw):
        reads.append(ref.path)
        return read(ref, *a, **kw)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', counted)
    monkeypatch.setattr(StrictFirestoreTransaction, 'set', unexpected)
    monkeypatch.setattr(StrictFirestoreTransaction, 'update', unexpected)
    monkeypatch.setattr(finalize, 'submit_with_context', unexpected)
    finalize.schedule_after_finalization('u', 'same', finalize.ProcessingTrigger.SYNC_UPDATE, row=fresh)
    assert [p[2:] for p in reads] == [('episode_links', 'same'), ('conversations', 'same')]
