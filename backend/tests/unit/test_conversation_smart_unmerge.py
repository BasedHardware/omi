"""Synthetic undo through real codecs and strict read-before-write transactions."""

from copy import deepcopy
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from database import smart_merge_unmerge as unmerge_db
from scripts import smart_merge_unmerge as cli
from tests.unit.test_conversation_smart_merge import T0, UID, World, _path
from utils import app_integrations, metrics
from utils.conversations import merge_conversations, smart_merge
from utils.conversations import smart_merge_unmerge_audio as unmerge_audio
from utils.conversations.processing_trigger import PROCESSING_MODES, ProcessingTrigger
from utils.conversations.smart_merge_policy import new_conversation_skip, predecessor_status_skip
from utils.other import storage
from utils.sync.assignment import assign_in_transaction, auto_mergeable


@pytest.fixture
def world(monkeypatch):
    world = World(monkeypatch)
    monkeypatch.setattr(unmerge_db, 'get_firestore_client', lambda: world.store)
    monkeypatch.setattr(
        smart_merge.conversations_db, 'update_conversation', lambda uid, cid, payload: world.raw(cid).update(payload)
    )
    world.removed_audio = []
    world.rebuilt_audio = []
    world.restored = []
    world.cached = []
    world.integrations = []

    async def fanout(uid, conversation, **kwargs):
        world.integrations.append((conversation.id, kwargs))
        return []

    monkeypatch.setattr(app_integrations, 'trigger_external_integrations', fanout)
    monkeypatch.setattr(
        smart_merge,
        'delete_copied_smart_merge_audio',
        lambda uid, donor, survivor, **kwargs: world.removed_audio.append((donor, survivor)),
    )
    monkeypatch.setattr(unmerge_audio, 'delete_cached_merged_audio', lambda uid, cid: world.cached.append(cid))
    monkeypatch.setattr(unmerge_audio, 'list_audio_chunks', lambda uid, cid: [])
    monkeypatch.setattr(unmerge_audio, 'is_audio_merge_dispatch_enabled', lambda: False)
    monkeypatch.setattr(
        smart_merge.conversations_db,
        'create_audio_files_from_chunks',
        lambda uid, cid: world.rebuilt_audio.append(cid) or [],
    )

    def process(uid, language, conversation, *, trigger, persistence_observer, smart_merge_refresh=None):
        if trigger is ProcessingTrigger.SMART_MERGE:
            return world.process(
                uid,
                language,
                conversation,
                trigger=trigger,
                persistence_observer=persistence_observer,
                smart_merge_refresh=smart_merge_refresh,
            )
        assert trigger is ProcessingTrigger.SMART_UNMERGE
        if world.process_error:
            raise world.process_error
        world.restored.append(conversation.id)
        persistence_observer(world.process_persisted)
        return conversation

    monkeypatch.setattr(smart_merge, 'process_conversation', process)
    world.add('p', 0, 5, private_cloud_sync_enabled=True)
    world.add('n', 10, 5, private_cloud_sync_enabled=True)
    assert world.finish('n')
    world.removed_audio.clear()
    world.rebuilt_audio.clear()
    return world


def audit(world, cid='n'):
    return world.store.rows[('users', UID, 'smart_merge_audit', cid)]


def test_dry_run_is_read_only_and_default(world):
    before = deepcopy(world.store.rows)
    result = smart_merge.unmerge_conversation(UID, 'n')
    assert result.outcome == 'dry_run'
    assert result.donor_ids == ('n',)
    assert result.removed_segments == 2
    assert world.store.rows == before
    assert not world.removed_audio and not world.restored


@pytest.mark.parametrize(
    'target,patch,reason',
    [
        ('n', {'smart_merge': {}}, 'not_a_donor'),
        ('n', {'sync_bridge_cleaned_revision': -1}, 'donor_cleanup_pending'),
        ('n', {'sync_merged_into': 'elsewhere'}, 'donor_not_owned'),
        ('p', {'deleted': True}, 'survivor_missing_or_deleted'),
        ('p', {'status': 'processing'}, 'survivor_not_completed'),
        ('p', {'user_title': 'synthetic title'}, 'survivor_user_modified'),
        ('p', {'user_title': ''}, 'survivor_user_modified'),
        ('p', {'manual_speaker_assignments': {'generation': 1}}, 'survivor_user_modified'),
    ],
)
def test_eligibility_matrix(world, target, patch, reason):
    world.raw(target).update(patch)
    before = deepcopy(world.store.rows)
    result = smart_merge.unmerge_conversation(UID, 'n')
    assert result.outcome == 'ineligible' and result.reason == reason
    assert world.store.rows == before


def test_missing_donor_and_survivor(world):
    assert smart_merge.unmerge_conversation(UID, 'missing').reason == 'not_a_donor'
    world.store.rows.pop(_path('p'))
    assert smart_merge.unmerge_conversation(UID, 'n').reason == 'survivor_missing_or_deleted'


def test_refresh_owed_and_active_lease(world):
    state = world.raw('p')['smart_merge']
    state['refreshed_revision'] = 0
    assert smart_merge.unmerge_conversation(UID, 'n').reason == 'survivor_refresh_owed'
    state['refreshed_revision'] = state['revision']
    state['refresh_lease'] = {'owner': 'other', 'until': datetime.now(timezone.utc) + timedelta(hours=1)}
    assert smart_merge.unmerge_conversation(UID, 'n', force=True).reason == 'survivor_lease_busy'


def test_force_only_overrides_curation(world):
    world.raw('p')['user_title'] = 'synthetic'
    assert smart_merge.unmerge_conversation(UID, 'n', force=True).outcome == 'dry_run'
    world.raw('n')['sync_bridge_cleaned_revision'] = -1
    assert smart_merge.unmerge_conversation(UID, 'n', force=True).reason == 'donor_cleanup_pending'


def test_last_fragment_restored_and_idempotent(world):
    original = deepcopy(world.transcript('n'))
    old_revision = world.raw('p')['smart_merge']['revision']
    result = smart_merge.unmerge_conversation(UID, 'n', dry_run=False)
    assert result.outcome == 'ok'
    survivor, donor = world.get(UID, 'p'), world.get(UID, 'n')
    assert len(survivor['transcript_segments']) == 2
    assert survivor['finished_at'] == T0 + timedelta(minutes=5)
    assert survivor['sync_merged_from'] == []
    assert survivor['smart_merge']['revision'] == old_revision + 1
    assert survivor['smart_merge']['refreshed_revision'] == old_revision + 1
    assert 'unmerge_pending' not in survivor['smart_merge']
    assert not donor['deleted'] and not donor['discarded']
    assert donor['smart_merge']['role'] == 'unmerged'
    # StrictFirestore retains DELETE_FIELD literally; the production transaction deletes it.
    assert world.transcript('n') == original
    assert new_conversation_skip(donor, original, capture_end=True) == 'conversation_not_eligible'
    assert world.removed_audio == [('n', 'p')]
    assert world.restored == ['n']
    assert world.rebuilt_audio == ['p', 'n']
    assert audit(world)['unmerge_actor'] == 'admin'
    effects = (len(world.restored), len(world.removed_audio), len(world.vectors))
    assert smart_merge.unmerge_conversation(UID, 'n', dry_run=False).reason == 'already_unmerged'
    assert effects == (len(world.restored), len(world.removed_audio), len(world.vectors))


def test_middle_donor_restores_suffix(world):
    world.add('later', 20, 5)
    assert world.finish('later')
    result = smart_merge.unmerge_conversation(UID, 'n', dry_run=False)
    assert result.donor_ids == ('n', 'later')
    assert world.restored == ['n', 'later']
    assert [entry['id'] for entry in world.raw('p')['smart_merge']['fragments']] == ['p']
    assert len(world.transcript('p')) == 2
    assert world.raw('later')['smart_merge']['role'] == 'unmerged'
    assert audit(world, 'later')['unmerge_actor'] == 'admin'


def test_restored_live_donor_repair_with_clock_offset_deduplicates(world):
    assert not world.raw('n').get('sync_live_target')
    smart_merge.unmerge_conversation(UID, 'n', dry_run=False)
    # Model the actual DELETE_FIELD operation without extending the strict fake.
    world.raw('n').pop('sync_merged_into')
    incoming = deepcopy(world.get(UID, 'n'))
    incoming.update(id='repair', started_at=incoming['started_at'] + timedelta(seconds=10))
    incoming['finished_at'] += timedelta(seconds=10)
    incoming.pop('smart_merge')
    for segment in incoming['transcript_segments']:
        segment.pop('id', None)
    for _ in range(2):
        result, _, added = assign_in_transaction(
            world.store.transaction(),
            world.store.collection('users').document(UID),
            incoming,
            target_id='n',
            decode=lambda raw: world.get(UID, raw['id']),
            encode=lambda row: smart_merge.conversations_db.encode_conversation_for_write(UID, row, 'enhanced'),
            invalidate=lambda row: None,
        )
        assert len(result['transcript_segments']) == 2
        assert added == []
        assert result['sync_live_target']


def test_restored_donor_cannot_be_automatically_absorbed_by_sync(world):
    smart_merge.unmerge_conversation(UID, 'n', dry_run=False)
    assert world.raw('n')['sync_live_target']
    assert not auto_mergeable(world.get(UID, 'n'))
    # The role also protects previously restored rows without the new marker.
    world.raw('n').pop('sync_live_target')
    assert not auto_mergeable(world.get(UID, 'n'))


def test_restored_donor_external_integrations_precede_checkpoint_and_retry_with_same_key(world, monkeypatch):
    calls = []

    async def fanout(uid, conversation, **kwargs):
        pending = world.raw('p')['smart_merge']['unmerge_pending']
        assert conversation.id not in pending.get('processed_ids', [])
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError('synthetic transient integration failure')
        return []

    monkeypatch.setattr(app_integrations, 'trigger_external_integrations', fanout)
    with pytest.raises(smart_merge.SmartMergeIncomplete):
        smart_merge.unmerge_conversation(UID, 'n', dry_run=False)
    assert not world.raw('p')['smart_merge']['unmerge_pending'].get('processed_ids')
    assert smart_merge.unmerge_conversation(UID, 'n', dry_run=False).outcome == 'ok'
    assert len(calls) == 2
    assert calls[0]['idempotency_key'] == calls[1]['idempotency_key']
    assert calls[0]['require_delivery'] is True
    assert smart_merge.unmerge_conversation(UID, 'n', dry_run=False).reason == 'already_unmerged'
    assert len(calls) == 2


@pytest.mark.parametrize('hard_delete', [False, True])
def test_deleted_restored_donor_is_terminal_and_does_not_block_survivor(world, hard_delete):
    world.process_error = RuntimeError('synthetic follow-up failure')
    with pytest.raises(smart_merge.SmartMergeIncomplete):
        smart_merge.unmerge_conversation(UID, 'n', dry_run=False)
    if hard_delete:
        world.store.rows.pop(_path('n'))
    else:
        world.raw('n')['deleted'] = True
    world.process_error = None
    smart_merge.finish_unmerge(UID, 'p')
    assert 'unmerge_pending' not in world.raw('p')['smart_merge']
    assert predecessor_status_skip(world.raw('p')) is None
    assert not world.restored and not world.integrations
    assert (_path('n') not in world.store.rows) if hard_delete else world.raw('n')['deleted']


def test_delete_cleans_copies_before_originals_and_replay_uses_retained_manifest(world, monkeypatch):
    names = ['100.000.opus.enc', '101.000-110.000.batch.bin']
    originals, copies = set(names), {*names, 'survivor-original.opus.enc'}
    monkeypatch.setattr(
        unmerge_audio,
        'list_audio_chunks',
        lambda uid, cid: [{'path': f'chunks/{uid}/{cid}/{name}'} for name in originals],
    )

    def remove(uid, donor, survivor, *, filenames=None):
        assert filenames == names
        copies.difference_update(filenames)

    def fail_audio(*args, **kwargs):
        raise RuntimeError('synthetic storage outage')

    monkeypatch.setattr(smart_merge, 'delete_copied_smart_merge_audio', fail_audio)
    monkeypatch.setattr(unmerge_audio, 'delete_copied_smart_merge_audio', fail_audio)
    with pytest.raises(smart_merge.SmartMergeIncomplete):
        smart_merge.unmerge_conversation(UID, 'n', dry_run=False)
    pending = world.raw('p')['smart_merge']['unmerge_pending']
    assert pending['audio_filenames'] == {'n': names}
    assert world.raw('n')['smart_merge']['unmerge_audio_filenames'] == names

    def delete(uid, cid):
        assert copies == {'survivor-original.opus.enc'}
        assert world.rebuilt_audio == ['p'] and world.cached == ['p']
        originals.clear()
        world.store.rows.pop(_path(cid))

    monkeypatch.setattr(merge_conversations.conversations_db, 'delete_conversation', delete)
    with pytest.raises(RuntimeError):
        merge_conversations.delete_conversation_with_sync_sources(UID, 'n')
    assert originals == set(names) and _path('n') in world.store.rows
    monkeypatch.setattr(unmerge_audio, 'delete_copied_smart_merge_audio', remove)
    merge_conversations.delete_conversation_with_sync_sources(UID, 'n')
    assert not originals
    monkeypatch.setattr(smart_merge, 'delete_copied_smart_merge_audio', remove)
    # The sibling audit lets the original admin invocation resume after hard deletion.
    assert smart_merge.unmerge_conversation(UID, 'n', dry_run=False).reason == 'followup_pending'
    assert 'unmerge_pending' not in world.raw('p')['smart_merge']
    assert copies == {'survivor-original.opus.enc'}
    assert _path('n') not in world.store.rows
    assert not world.restored and not world.integrations


@pytest.mark.parametrize('hard_delete', [False, True])
def test_deletion_during_restored_processing_is_terminal(world, monkeypatch, hard_delete):
    process = smart_merge.process_conversation

    def delete_during_processing(uid, language, conversation, **kwargs):
        if kwargs['trigger'] is ProcessingTrigger.SMART_UNMERGE:
            if hard_delete:
                world.store.rows.pop(_path(conversation.id))
            else:
                world.raw(conversation.id)['deleted'] = True
            kwargs['persistence_observer'](False)
            return conversation
        return process(uid, language, conversation, **kwargs)

    monkeypatch.setattr(smart_merge, 'process_conversation', delete_during_processing)
    assert smart_merge.unmerge_conversation(UID, 'n', dry_run=False).outcome == 'ok'
    assert 'unmerge_pending' not in world.raw('p')['smart_merge']
    assert 'n' not in world.rebuilt_audio
    assert not world.integrations


def test_audio_manifest_is_fenced_by_donor_content_revision(world, monkeypatch):
    undo = unmerge_db.unmerge_transaction

    def race(*args, **kwargs):
        world.raw('n')['sync_content_revision'] += 1
        world.raw('n')['sync_bridge_cleaned_revision'] = world.raw('n')['sync_content_revision']
        return undo(*args, **kwargs)

    monkeypatch.setattr(unmerge_db, 'unmerge_transaction', race)
    assert smart_merge.unmerge_conversation(UID, 'n', dry_run=False).reason == 'revision_conflict'
    assert world.raw('n')['deleted']
    assert 'unmerge_pending' not in world.raw('p')['smart_merge']


def test_select_last_keeps_middle(world):
    world.add('later', 20, 5)
    assert world.finish('later')
    result = smart_merge.unmerge_conversation(UID, 'later', dry_run=False)
    assert result.donor_ids == ('later',)
    assert world.raw('n')['smart_merge']['role'] == 'donor'
    assert len(world.transcript('p')) == 4
    assert world.raw('p')['finished_at'] == T0 + timedelta(minutes=15)


def test_suffix_requires_every_cleanup(world):
    world.add('later', 20, 5)
    assert world.finish('later')
    world.raw('later')['sync_bridge_cleaned_revision'] = -1
    assert smart_merge.unmerge_conversation(UID, 'n').reason == 'donor_cleanup_pending'


@pytest.mark.parametrize('missing', ['donor', 'survivor', 'both', 'partial'])
def test_segment_time_fallback(world, missing):
    for cid in ('p', 'n'):
        segments = world.transcript(cid)
        if cid == 'n' and missing in ('donor', 'both', 'partial'):
            for index, segment in enumerate(segments):
                if missing != 'partial' or index == 0:
                    segment['id'] = ''
        if cid == 'p' and missing in ('survivor', 'both'):
            for segment in segments[2:]:
                segment['id'] = ''
        world.raw(cid).update(
            smart_merge.conversations_db.encode_conversation_for_write(
                UID, {'transcript_segments': segments}, 'enhanced'
            )
        )
    assert smart_merge.unmerge_conversation(UID, 'n', dry_run=False).removed_segments == 2
    assert len(world.transcript('p')) == 2


def test_id_removal_does_not_remove_unrelated_ids(world):
    segments = world.transcript('p')
    segments.append(dict(segments[0], id='independent', start=605, end=610))
    world.raw('p').update(
        smart_merge.conversations_db.encode_conversation_for_write(UID, {'transcript_segments': segments}, 'enhanced')
    )
    assert smart_merge.unmerge_conversation(UID, 'n').removed_segments == 2


@pytest.mark.parametrize('field', ['revision', 'sync_content_revision'])
def test_revision_conflict(world, monkeypatch, field):
    original = unmerge_db.unmerge_transaction

    def mutate(*args, **kwargs):
        target = world.raw('p')['smart_merge'] if field == 'revision' else world.raw('p')
        target[field] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(unmerge_db, 'unmerge_transaction', mutate)
    result = smart_merge.unmerge_conversation(UID, 'n', dry_run=False)
    assert result.reason == 'revision_conflict'
    assert world.raw('n')['deleted']
    assert 'unmerged_at' not in audit(world)


def test_failed_followup_replays_without_second_surgery(world):
    world.process_error = RuntimeError('synthetic provider failure')
    with pytest.raises(smart_merge.SmartMergeIncomplete):
        smart_merge.unmerge_conversation(UID, 'n', dry_run=False)
    assert world.raw('n')['smart_merge']['role'] == 'unmerged'
    assert predecessor_status_skip(world.raw('p')) == 'predecessor_refresh_pending'
    assert 'unmerge_pending' in world.raw('p')['smart_merge']
    revision = world.raw('p')['smart_merge']['revision']
    world.process_error = None
    assert smart_merge.unmerge_conversation(UID, 'n').reason == 'followup_pending'
    assert smart_merge.unmerge_conversation(UID, 'n', dry_run=False).outcome == 'ok'
    assert world.raw('p')['smart_merge']['revision'] == revision
    assert world.restored == ['n']


def test_leased_followup_does_not_run_concurrently(world, monkeypatch):
    monkeypatch.setattr(smart_merge, 'finish_unmerge', lambda uid, survivor: None)
    assert smart_merge.unmerge_conversation(UID, 'n', dry_run=False).outcome == 'ok'
    now = datetime.now(timezone.utc)
    assert unmerge_db.checkpoint_unmerge(UID, 'p', owner='one', now=now, lease_seconds=600)
    assert unmerge_db.checkpoint_unmerge(UID, 'p', owner='two', now=now, lease_seconds=600) is None
    unmerge_db.release_unmerge(UID, 'p', owner='two')
    assert unmerge_db.checkpoint_unmerge(UID, 'p', owner='two', now=now, lease_seconds=600) is None
    unmerge_db.release_unmerge(UID, 'p', owner='one')
    assert unmerge_db.checkpoint_unmerge(UID, 'p', owner='two', now=now, lease_seconds=600)


def test_suffix_followup_checkpoints_each_donor_and_resumes(world, monkeypatch):
    world.add('later', 20, 5)
    assert world.finish('later')
    original = smart_merge.process_conversation

    def fail_later(uid, language, conversation, **kwargs):
        if conversation.id == 'later':
            raise RuntimeError('synthetic transient failure')
        return original(uid, language, conversation, **kwargs)

    monkeypatch.setattr(smart_merge, 'process_conversation', fail_later)
    with pytest.raises(smart_merge.SmartMergeIncomplete):
        smart_merge.unmerge_conversation(UID, 'n', dry_run=False)
    assert world.raw('p')['smart_merge']['unmerge_pending']['processed_ids'] == ['n']
    assert world.restored == ['n']
    monkeypatch.setattr(smart_merge, 'process_conversation', original)
    assert smart_merge.unmerge_conversation(UID, 'later', dry_run=False).outcome == 'ok'
    assert world.restored == ['n', 'later']
    assert [cid for cid, _ in world.integrations] == ['n', 'later']
    assert smart_merge.unmerge_conversation(UID, 'n', dry_run=False).reason == 'already_unmerged'


def test_crashed_followup_lease_can_expire(world, monkeypatch):
    monkeypatch.setattr(smart_merge, 'finish_unmerge', lambda uid, survivor: None)
    smart_merge.unmerge_conversation(UID, 'n', dry_run=False)
    now = datetime.now(timezone.utc)
    assert unmerge_db.checkpoint_unmerge(UID, 'p', owner='crashed', now=now, lease_seconds=600)
    assert unmerge_db.checkpoint_unmerge(UID, 'p', owner='retry', now=now + timedelta(seconds=601), lease_seconds=600)


def test_audit_update_keeps_closed_fields_only(world):
    audit(world)['unexpected_summary'] = 'synthetic secret'
    assert smart_merge.unmerge_conversation(UID, 'n', dry_run=False).outcome == 'ok'
    assert 'unexpected_summary' not in audit(world)


def test_audit_closed_projection_and_retention(world):
    record = audit(world)
    assert set(record) == {
        'donor_id',
        'survivor_id',
        'p_same',
        'threshold',
        'question_version',
        'served_model',
        'gap_seconds',
        'merged_at',
        'mode',
        'source',
        'expire_at',
    }
    assert record['donor_id'] == 'n' and record['survivor_id'] == 'p'
    assert record['expire_at'] - record['merged_at'] == timedelta(days=60)
    assert 'synthetic' not in str(record)


def test_legacy_audit_created_on_unmerge(world):
    world.store.rows.pop(('users', UID, 'smart_merge_audit', 'n'))
    assert smart_merge.unmerge_conversation(UID, 'n', dry_run=False).outcome == 'ok'
    assert audit(world)['unmerge_actor'] == 'admin'


def test_served_model_is_preserved_in_audit(world, monkeypatch):
    monkeypatch.setattr(smart_merge, '_ask', lambda state: (0.5, 'served-model-version'))
    world.add('later', 20, 5)
    assert world.finish('later')
    assert audit(world, 'later')['served_model'] == 'served-model-version'


@pytest.mark.parametrize('outcome', ['ok', 'ineligible', 'dry_run', 'error'])
def test_unmerge_outcome_metrics(outcome):
    counter = metrics.SMART_MERGE_UNMERGE_TOTAL.labels(outcome=outcome)
    before = counter._value.get()
    metrics.record_smart_merge_unmerge(outcome)
    assert counter._value.get() == before + 1


def test_audit_survives_survivor_and_donor_cascade(world, monkeypatch):
    deleted = []

    def delete(uid, cid, **kwargs):
        deleted.append(cid)
        # Delete the conversation subtree only, like the storage primitive.
        for path in list(world.store.rows):
            if path[:4] == _path(cid):
                world.store.rows.pop(path)

    monkeypatch.setattr(merge_conversations, '_delete_conversation_and_related_data', delete)
    monkeypatch.setattr(merge_conversations.conversations_db, 'delete_conversation', delete)
    before = deepcopy(audit(world))
    merge_conversations.delete_conversation_with_sync_sources(UID, 'p')
    assert deleted == ['n', 'p']
    assert audit(world) == before


@pytest.mark.parametrize('age,bucket', [(3599, 'lt_1h'), (3600, 'lt_24h'), (86400, 'lt_7d'), (604800, 'gte_7d')])
def test_deletion_age_buckets(age, bucket):
    counter = metrics.SMART_MERGE_SURVIVOR_DELETED_TOTAL.labels(age_bucket=bucket)
    before = counter._value.get()
    metrics.record_smart_merge_survivor_deleted(T0 - timedelta(seconds=age), now=T0)
    assert counter._value.get() == before + 1


@pytest.mark.parametrize('legacy', [False, True])
def test_delete_hook_and_metric_failure_do_not_block(world, monkeypatch, legacy):
    if legacy:
        world.raw('p')['smart_merge'].pop('last_merged_at')
    recorded, deleted = [], []
    monkeypatch.setattr(merge_conversations, 'record_smart_merge_survivor_deleted', lambda ts: recorded.append(ts))
    monkeypatch.setattr(
        merge_conversations, '_delete_conversation_and_related_data', lambda uid, cid, **kw: deleted.append(cid)
    )
    monkeypatch.setattr(
        merge_conversations.conversations_db, 'delete_conversation', lambda uid, cid: deleted.append(cid)
    )
    merge_conversations.delete_conversation_with_sync_sources(UID, 'p')
    assert recorded == [world.raw('n')['smart_merge']['merged_at']]
    assert deleted == ['n', 'p']
    monkeypatch.setattr(
        merge_conversations, 'record_smart_merge_survivor_deleted', lambda ts: (_ for _ in ()).throw(RuntimeError())
    )
    merge_conversations.delete_conversation_with_sync_sources(UID, 'p')
    assert deleted == ['n', 'p', 'n', 'p']


def test_cli_dry_run_output_has_no_content(world, capsys):
    assert cli.main(['--uid', UID, '--donor-id', 'n']) == 0
    output = capsys.readouterr()
    assert 'synthetic' not in output.out and 'title' not in output.out and 'overview' not in output.out
    assert '"reason": "eligible"' in output.out
    assert not output.err
    assert world.raw('n')['deleted']


def test_cli_suppresses_downstream_output_and_exception_text(monkeypatch, capsys):
    def noisy(*args, **kwargs):
        print('synthetic confidential transcript')
        raise RuntimeError('synthetic confidential overview')

    monkeypatch.setattr(cli, 'unmerge_conversation', noisy)
    assert cli.main(['--uid', UID, '--donor-id', 'n', '--apply']) == 1
    output = capsys.readouterr()
    assert 'synthetic' not in output.out and '"reason": "error"' in output.out
    assert not output.err


def test_donor_processing_mode_is_eager_initial_keep():
    mode = PROCESSING_MODES[ProcessingTrigger.SMART_UNMERGE]
    assert mode.run_now and not mode.reprocess and mode.bypass_jit_first_open
    assert mode.relevance.value == 'keep'


def test_audio_removal_uses_exact_copied_filenames(monkeypatch):
    deleted = []
    bucket = SimpleNamespace(blob=lambda path: SimpleNamespace(delete=lambda: deleted.append(path)))
    monkeypatch.setattr(storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: bucket))
    monkeypatch.setattr(
        storage,
        'list_audio_chunks',
        lambda uid, cid: [
            {'path': f'chunks/{uid}/{cid}/100.000.opus.enc'},
            {'path': f'chunks/{uid}/{cid}/101.000-110.000.batch.bin'},
        ],
    )
    monkeypatch.setattr(storage, 'owner_storage_write_gate', lambda uid, bucket: nullcontext())
    storage.delete_copied_smart_merge_audio(UID, 'n', 'p')
    assert deleted == [f'chunks/{UID}/p/100.000.opus.enc', f'chunks/{UID}/p/101.000-110.000.batch.bin']
    deleted.clear()
    monkeypatch.setattr(storage, 'list_audio_chunks', lambda uid, cid: [])
    storage.delete_copied_smart_merge_audio(UID, 'n', 'p', filenames=['100.000.opus.enc'])
    assert deleted == [f'chunks/{UID}/p/100.000.opus.enc']


def test_unmerge_fenced_while_account_wipe_runs(world):
    """The audit sibling is user data the account wipe owns: a live wipe gate
    must block the undo transaction instead of recreating audit documents."""
    from database.legal_holds import LEGAL_HOLD_DELETION_GATE_SCHEMA_VERSION

    world.store.rows[('legal_hold_deletion_gates', UID)] = {
        'schema_version': LEGAL_HOLD_DELETION_GATE_SCHEMA_VERSION,
        'uid': UID,
        'kind': 'account_data_wipe',
        'token': 'live-wipe',
        'state': 'running',
        'started_at': datetime.now(timezone.utc),
        'finished_at': None,
    }
    before = deepcopy(world.store.rows)
    with pytest.raises(smart_merge.SmartMergeIncomplete):
        smart_merge.unmerge_conversation(UID, 'n', dry_run=False)
    assert world.store.rows == before  # no partial undo, no audit resurrection
    assert not world.restored and not world.removed_audio
