"""The reference adapter must hold a lost side effect under its original operation."""

import os
from datetime import datetime, timezone
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from routers import sync_finalization_reference as reference

pytestmark = pytest.mark.integration


@pytest.fixture
def claim():
    endpoint = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not endpoint.startswith('127.0.0.1:'):
        pytest.skip('requires a loopback Firestore emulator')
    client = firestore.Client(project=f'demo-sync-reference-{uuid4().hex[:12]}', credentials=AnonymousCredentials())
    row = client.collection('users').document('fixture').collection('conversations').document('capture')
    job = client.collection('conversation_finalization_jobs').document('job')
    owner = {'finalization_engine': 'go', 'finalization_owner_epoch': 2, 'finalization_revision': 1}
    row.set(owner | {'finalization_job_id': 'job', 'sync_content_revision': 3, 'status': 'completed'})
    job.set(
        owner
        | {
            'status': 'leased',
            'processing_trigger': 'sync_update',
            'uid': 'fixture',
            'conversation_id': 'capture',
            'go_queue_epoch': 5,
            'go_lease_epoch': 3,
            'lease_epoch': 3,
            'fanout_status': 'leased',
            'fanout_lease_epoch': 3,
            'go_fanout_sync_revision': 3,
        }
    )
    req = reference.ReferenceRequest(
        owner='fixture',
        conversation='capture',
        job='job',
        revision=1,
        sync_revision=3,
        queue_epoch=5,
        step='effects',
        operation='op_' + '0' * 40,
    )
    req.operation = req.expected_operation()
    try:
        yield client, row, job, req
    finally:
        row.delete()
        job.delete()
        client.close()


def test_lost_response_blocks_reexecution_across_takeover_and_append(claim):
    client, row, job, req = claim
    assert reference._read_or_reserve(client, req, reserve=True)[0] == 'owned'
    job.update({'go_queue_epoch': 6})
    req.queue_epoch = 6
    assert reference._read_or_reserve(client, req, reserve=True) == ('operation_unsettled', None)
    row.update({'sync_content_revision': 4})
    assert reference._read_or_reserve(client, req, reserve=True) == ('source_changed', None)
    job.update({'go_fanout_sync_revision': 4})
    appended = req.model_copy(update={'sync_revision': 4})
    appended.operation = appended.expected_operation()
    assert reference._read_or_reserve(client, appended, reserve=True) == ('operation_unsettled', None)
    assert reference._settle(client, req)
    assert reference._read_or_reserve(client, appended, reserve=True)[0] == 'owned'


def test_handback_denies_previous_worker_even_if_its_job_tag_is_unchanged(claim):
    client, row, job, req = claim
    row.update({'finalization_engine': 'python', 'finalization_owner_epoch': 3})
    assert reference._read_or_reserve(client, req, reserve=True) == ('ownership_changed', None)
    assert reference.RECEIPTS not in job.get().to_dict()


def test_effects_refuse_before_the_fanout_claim(claim):
    client, _, job, req = claim
    job.update({'fanout_status': 'pending'})
    assert reference._read_or_reserve(client, req, reserve=True) == ('ownership_changed', None)
    assert reference.RECEIPTS not in job.get().to_dict()


def test_targets_respect_ordinary_sync_creation_policy(claim):
    client, row, job, req = claim
    req.step = 'targets'
    req.operation = req.expected_operation()

    assert reference._adapt(client, req) == {'targets': []}
    assert reference.RECEIPTS not in job.get().to_dict()

    row.update({'sync_content_revision': req.sync_revision + 1})
    assert reference._adapt(client, req).status_code == 409


@pytest.mark.parametrize('concurrent_change', [None, 'append', 'app_edit', 'transcript_edit'])
def test_eager_effects_commit_only_current_outputs(claim, monkeypatch, concurrent_change):
    from models.conversation import AppResult
    from utils.conversations import process_conversation as processor
    from utils.conversations.reprocess_contract import (
        DERIVED_EFFECTS_TRANSCRIPT_FIELD,
        derived_effects_transcript_digest,
    )

    client, row, job, req = claim
    captured = datetime(2026, 1, 1, tzinfo=timezone.utc)
    transcript = [
        {
            'id': 'synthetic-segment',
            'text': 'Original text',
            'speaker': 'SPEAKER_00',
            'is_user': True,
            'start': 0,
            'end': 2,
        }
    ]
    row.update(
        {
            'id': req.conversation,
            'created_at': captured,
            'started_at': captured,
            'finished_at': captured,
            'structured': {'title': 'Synthetic notes', 'overview': 'Synthetic preview', 'emoji': '💬'},
            'transcript_segments': transcript,
        }
    )
    calls = []

    def apps(uid, conversation, *, is_reprocess, people):
        assert is_reprocess and people == []
        assert job.get().to_dict()[reference.RECEIPTS] == {req.operation: 'reserved'}
        calls.append(('apps', uid))
        conversation.apps_results = [AppResult(app_id='fixture-app', content='Synthetic result')]
        if concurrent_change == 'append':
            row.update({'sync_content_revision': req.sync_revision + 1})
        elif concurrent_change == 'app_edit':
            row.update({'apps_results': [{'app_id': 'fixture-app', 'content': 'Owner edit'}]})
        elif concurrent_change == 'transcript_edit':
            row.update({'transcript_segments': [{**transcript[0], 'text': 'Updated text'}]})

    monkeypatch.setattr(processor, 'trigger_conversation_apps', apps)
    monkeypatch.setattr(processor, 'extract_memories', lambda uid, conversation: calls.append(('memories', uid)))
    monkeypatch.setattr(processor, '_save_action_items', lambda uid, *_: calls.append(('tasks', uid)))
    monkeypatch.setattr(processor, 'save_structured_vector', lambda *_: calls.append(('vector', req.owner)))

    def goals(uid, conversation):
        assert conversation.id == req.conversation
        assert job.get().to_dict()[reference.RECEIPTS] == {req.operation: 'reserved'}
        calls.append(('goals', uid))
        # Eager goal progress is fail-open in the Python sync callback.
        return False

    monkeypatch.setattr(processor, 'update_goal_progress', goals)

    assert reference._adapt(client, req) == {}
    replayed = reference._adapt(client, req)
    stored = row.get().to_dict()
    if concurrent_change in {'append', 'transcript_edit'}:
        assert 'apps_results' not in stored
        assert DERIVED_EFFECTS_TRANSCRIPT_FIELD not in stored
        if concurrent_change == 'append':
            assert replayed.status_code == 409
        else:
            assert replayed == {}
    else:
        assert replayed == {}
        content = 'Owner edit' if concurrent_change == 'app_edit' else 'Synthetic result'
        assert stored['apps_results'] == [{'app_id': 'fixture-app', 'content': content}]
        assert stored[DERIVED_EFFECTS_TRANSCRIPT_FIELD] == derived_effects_transcript_digest(transcript)
    assert calls == [(step, req.owner) for step in ('apps', 'memories', 'tasks', 'goals')]
    assert job.get().to_dict()[reference.RECEIPTS] == {req.operation: 'settled'}


def test_handback_rejects_stale_replay_and_preserves_the_go_receipt(claim):
    client, row, job, req = claim
    assert reference._read_or_reserve(client, req, reserve=True)[0] == 'owned'
    assert reference._settle(client, req)
    row.update({'finalization_engine': 'python', 'finalization_owner_epoch': 3})
    assert reference._read_or_reserve(client, req, reserve=True) == ('ownership_changed', None)
    assert job.get().to_dict()[reference.RECEIPTS] == {req.operation: 'settled'}


@pytest.mark.parametrize('changed', [False, True])
def test_home_projection_settles_with_episode_receipt_without_stale_write(claim, changed):
    from utils.home_feed.projection import reveal_display

    client, row, job, req = claim
    req.step = 'episode-reconcile'
    req.operation = req.expected_operation()
    row.update(
        {
            'started_at': datetime(2026, 1, 1, tzinfo=timezone.utc),
            'structured': {'title': 'Synthetic notes', 'overview': 'Synthetic preview', 'emoji': '💬'},
        }
    )
    assert reference._read_or_reserve(client, req, reserve=True)[0] == 'owned'
    if changed:
        row.update({'sync_content_revision': 4})
    assert reference._settle(client, req)
    assert job.get().to_dict()[reference.RECEIPTS][req.operation] == 'settled'
    stored = row.get().to_dict()
    if changed:
        assert 'home_display' not in stored
    else:
        assert reveal_display(req.owner, stored['home_display'])['title'] == 'Synthetic notes'
        assert stored['home_has_tasks'] is False


@pytest.mark.parametrize('fence', [None, 'tombstone', 'owner_deleting', 'revision', 'handback', 'stale_queue_epoch'])
def test_empty_discard_repair_is_fenced_and_idempotent(claim, monkeypatch, fence):
    from config import episodes as episodes_config
    from database import episodes
    from utils.episodes import client_gate, composer

    client, row, job, req = claim
    req.step = 'episode-reconcile'
    req.operation = req.expected_operation()
    row.update(
        {
            'discarded': True,
            'relevance_decision': {'reason': 'empty_transcript', 'verdict': 'discard'},
            'go_sync_minimum_discarded': True,
            'go_sync_minimum_revision': req.sync_revision,
        }
    )
    # Current workers bind empty fanout on the discard row instead of writing
    # a separate fanout claim to the mirror job.
    row.update(
        {'go_empty_discard_fanout_epoch': req.queue_epoch, 'go_sync_empty_discard_home_revision': req.sync_revision}
    )
    job.update({'fanout_status': 'pending'})
    user = row.parent.parent
    link = user.collection('episode_links').document(req.conversation)
    episode = user.collection('episodes').document('fixture-episode')
    link.set({'episode_id': episode.id, 'attach_revision': req.sync_revision})
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # The production seal still runs. The fixture needs a synthetic key only.
    monkeypatch.setenv('ENCRYPTION_SECRET', 'synthetic-replay-key-for-discard-tests-only')
    episode.set(
        {
            'id': episode.id,
            'status': 'closed',
            'state_version': 4,
            'started_at': started,
            'last_activity_at': started,
            'conversation_ids': [req.conversation],
            'member_activity': {req.conversation: started},
        }
    )
    monkeypatch.setattr(episodes_config, 'episodes_enabled_for', lambda _: True)
    monkeypatch.setattr(client_gate, 'client_seen', lambda _: True)
    monkeypatch.setattr(episodes, 'recorded_episodes_enabled', lambda: False)
    scheduled = []
    monkeypatch.setattr(
        composer, 'schedule_for_conversation', lambda *args, **kwargs: scheduled.append(kwargs['episode'])
    )
    marker = client.collection('account_deletions').document(req.owner)
    tombstone = user.collection('deleted_conversations').document(req.conversation)
    if fence == 'tombstone':
        tombstone.set({'deleted': True})
    elif fence == 'owner_deleting':
        marker.set({'wipe_status': 'running'})
    elif fence == 'revision':
        row.update({'sync_content_revision': req.sync_revision + 1})
    elif fence == 'handback':
        row.update({'finalization_engine': 'python', 'finalization_owner_epoch': 3})
    elif fence == 'stale_queue_epoch':
        job.update({'go_queue_epoch': req.queue_epoch + 1})

    assert reference.RECEIPTS not in job.get().to_dict()
    try:
        if fence:
            assert reference._adapt(client, req).status_code == 409
            assert episode.get().to_dict()['state_version'] == 4
            assert link.get().to_dict()['attach_revision'] == req.sync_revision
            assert scheduled == []
        else:
            assert reference._adapt(client, req) == {}
            assert reference._adapt(client, req) == {}
            stored = episode.get().to_dict()
            assert stored['state_version'] == 5
            assert stored['discarded_conversation_ids'] == [req.conversation]
            assert stored['member_activity'] == {}
            assert link.get().to_dict()['attach_revision'] is None
            assert len(scheduled) == 2
        assert reference.RECEIPTS not in job.get().to_dict()
    finally:
        for ref in (marker, tombstone, episode, link):
            ref.delete()


def test_empty_discard_without_episode_does_not_write(claim, monkeypatch):
    from config import episodes as episodes_config
    from utils.episodes import client_gate

    client, row, job, req = claim
    req.step = 'episode-reconcile'
    req.operation = req.expected_operation()
    row.update(
        {
            'discarded': True,
            'relevance_decision': {'reason': 'empty_transcript', 'verdict': 'discard'},
            'go_sync_minimum_discarded': True,
            'go_sync_minimum_revision': req.sync_revision,
            'go_empty_discard_fanout_epoch': req.queue_epoch,
            'go_sync_empty_discard_home_revision': req.sync_revision,
        }
    )
    job.update({'fanout_status': 'pending'})
    monkeypatch.setattr(episodes_config, 'episodes_enabled_for', lambda _: True)
    monkeypatch.setattr(client_gate, 'client_seen', lambda _: True)

    before = row.get().update_time, job.get().update_time
    assert reference._adapt(client, req) == {}
    assert reference._adapt(client, req) == {}
    assert (row.get().update_time, job.get().update_time) == before


def test_relevance_replays_settled_provider_answer_and_refuses_new_revision(claim):
    client, row, job, effects = claim
    notes = effects.model_copy(update={'step': 'notes'})
    operation = reference._RelevanceOperation(client, notes)
    calls = []

    def discard():
        calls.append('discard')
        return True

    assert operation('nano', discard) is True
    assert operation('nano', discard) is True
    assert calls == ['discard']
    settled = dict(job.get().to_dict()[reference.RECEIPTS])
    assert list(settled.values()) == ['settled']
    row.update({'sync_content_revision': notes.sync_revision + 1})
    assert operation('nano', discard) is None
    assert operation.refusal == 'source_changed'
    assert calls == ['discard']
    assert job.get().to_dict()[reference.RECEIPTS] == settled


def test_notes_actions_bind_provider_evidence_to_the_stored_revision(claim, monkeypatch):
    from database import notifications

    client, row, job, effects = claim
    occurred = datetime(2026, 1, 1, tzinfo=timezone.utc)
    row.update(
        {
            'id': effects.conversation,
            'created_at': occurred,
            'started_at': occurred,
            'finished_at': occurred,
            'transcript_segments': [{'id': 'real', 'text': 'Send the test notes', 'start': 0, 'end': 1}],
        }
    )
    monkeypatch.setattr(notifications, 'get_user_time_zone', lambda _: 'UTC')

    def unexpected(*args):
        pytest.fail('action normalization must not read deletion markers')

    monkeypatch.setattr(reference, '_deletion_blocks', unexpected)
    req = effects.model_copy(update={'step': 'notes-actions'})
    req.operation = req.expected_operation()
    req.action_items = [
        {'description': 'Send the test notes', 'source_segment_ids': ['invented', 'real', 'real'], 'completed': True},
        {'description': None},
    ]
    actions = reference._adapt(client, req)['action_items']
    assert len(actions) == 1
    assert actions[0]['source_segment_ids'] == ['real']
    assert actions[0]['completed'] is False
    assert reference.RECEIPTS not in job.get().to_dict()
    row.update({'sync_content_revision': req.sync_revision + 1})
    assert reference._adapt(client, req).status_code == 409


def test_episode_wait_refuses_deletion_before_idle_close(claim, monkeypatch):
    from utils.episodes import member_notes

    client, _, _, req = claim
    req = req.model_copy(update={'step': 'episode-start'})
    req.operation = req.expected_operation()
    marker = client.collection('account_deletions').document(req.owner)
    marker.set({'wipe_status': 'running'})

    def unexpected(*args):
        pytest.fail('the episode check can close an episode during deletion')

    monkeypatch.setattr(member_notes, 'waits', unexpected)
    try:
        assert reference._adapt(client, req).status_code == 409
    finally:
        marker.delete()


def test_relevance_replay_uses_the_fenced_notes_snapshot(claim, monkeypatch):
    client, _, _, effects = claim
    notes = effects.model_copy(update={'step': 'notes'})
    initial = reference._RelevanceOperation(client, notes)
    assert initial('nano', lambda: False) is False
    loaded = reference._JobVersion()
    assert reference._read_or_reserve(client, notes, reserve=False, job_version=loaded)[0] == 'owned'

    def unexpected(*args, **kwargs):
        pytest.fail('settled relevance must not read Firestore or call the provider again')

    monkeypatch.setattr(reference, '_read_or_reserve', unexpected)
    assert reference._RelevanceOperation(client, notes, loaded)('nano', unexpected) is False


@pytest.mark.parametrize('deletion', [None, 'account', 'tombstone'])
def test_combined_effects_rechecks_deletion_before_episode_admission(claim, monkeypatch, deletion):
    from utils.conversations import process_conversation as processor
    from database import episodes
    from utils.episodes import service

    client, row, job, effects = claim
    req = effects.model_copy(update={'step': 'effects-episode'})
    req.operation = req.expected_operation()
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    row.update(
        {'id': req.conversation, 'created_at': stamp, 'started_at': stamp, 'finished_at': stamp, 'structured': {}}
    )
    row.update({'go_sync_inline_fanout_epoch': req.queue_epoch, 'go_sync_inline_fanout_revision': req.sync_revision})
    job.update({'fanout_status': 'pending'})
    marker = client.collection('account_deletions').document(req.owner)
    tombstone = row.parent.parent.collection('deleted_conversations').document(req.conversation)
    calls = []
    episode = row.parent.parent.collection('episodes').document('fixture-episode')
    episode.set({'id': episode.id, 'status': 'closed', 'state_version': 1, 'conversation_ids': [req.conversation]})

    def apply(*args):
        calls.append('effects')
        if deletion == 'account':
            marker.set({'wipe_status': 'running'})
        if deletion == 'tombstone':
            tombstone.set({'conversation_id': req.conversation})

    def reconcile(*args, **kwargs):
        assert job.get().to_dict()[reference.RECEIPTS] == {key: 'reserved' for key in reference._operation_keys(req)}
        assert reference._adapt(client, req).status_code == 409
        assert reference.DERIVED_EFFECTS_TRANSCRIPT_FIELD not in row.get().to_dict()
        episodes.update_episode(req.owner, episode.id, expected_version=1, updates={}, firestore_client=client)
        calls.append('episode')
        return 'updated'

    monkeypatch.setattr(processor, 'apply_eager_sync_enrichment', apply)
    monkeypatch.setattr(service, 'on_conversation_finalized', reconcile)
    try:
        answer = reference._adapt(client, req)
        effects_key, episode_key = reference._operation_keys(req)
        if deletion:
            assert answer.status_code == 409
            assert calls == ['effects']
            assert episode.get().to_dict()['state_version'] == 1
            assert job.get().to_dict()[reference.RECEIPTS] == {effects_key: 'settled'}
        else:
            assert answer == {'combined': True}
            assert reference._adapt(client, req) == {'combined': True}
            assert calls == ['effects', 'episode']
            assert episode.get().to_dict()['state_version'] == 2
            assert reference.DERIVED_EFFECTS_TRANSCRIPT_FIELD in row.get().to_dict()
            assert job.get().to_dict()[reference.RECEIPTS] == {effects_key: 'settled', episode_key: 'settled'}
    finally:
        marker.delete()
        tombstone.delete()
        episode.delete()


def test_relevance_cas_refuses_a_takeover_before_the_provider_call(claim):
    client, _, job, req = claim
    req = req.model_copy(update={'step': 'notes'})
    version = reference._JobVersion()
    assert reference._read_or_reserve(client, req, reserve=False, job_version=version)[0] == 'owned'
    job.update({'go_queue_epoch': req.queue_epoch + 1})

    def unexpected():
        pytest.fail('stale snapshot paid for relevance')

    operation = reference._RelevanceOperation(client, req, job_version=version)
    assert operation('nano', unexpected) is None
    assert operation.refusal == 'ownership_changed'
    assert reference.RECEIPTS not in job.get().to_dict()


@pytest.mark.parametrize('change', ['transcript', 'tombstone', 'account'])
def test_combined_settlement_rechecks_after_episode_work(claim, monkeypatch, change):
    from utils.conversations import process_conversation as processor
    from database import episodes
    from utils.episodes import service

    client, row, job, req = claim
    req = req.model_copy(update={'step': 'effects-episode'})
    req.operation = req.expected_operation()
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    row.update(
        {
            'id': req.conversation,
            'created_at': stamp,
            'started_at': stamp,
            'finished_at': stamp,
            'structured': {},
        }
    )
    marker = client.collection('account_deletions').document(req.owner)
    tombstone = row.parent.parent.collection('deleted_conversations').document(req.conversation)

    episode_ref = row.parent.parent.collection('episodes').document('fixture-episode')
    episode_ref.set(
        {'id': episode_ref.id, 'status': 'closed', 'state_version': 1, 'conversation_ids': [req.conversation]}
    )

    def episode(*args, **kwargs):
        episodes.update_episode(req.owner, episode_ref.id, expected_version=1, updates={}, firestore_client=client)
        if change == 'transcript':
            row.update({'sync_content_revision': req.sync_revision + 1})
        elif change == 'tombstone':
            tombstone.set({'conversation_id': req.conversation})
        else:
            marker.set({'wipe_status': 'running'})
        return 'updated'

    monkeypatch.setattr(processor, 'apply_eager_sync_enrichment', lambda *_: None)
    monkeypatch.setattr(service, 'on_conversation_finalized', episode)
    try:
        assert reference._adapt(client, req) == {'combined': True}
        stored = row.get().to_dict()
        assert reference.DERIVED_EFFECTS_TRANSCRIPT_FIELD not in stored
        assert 'home_display' not in stored
        assert job.get().to_dict()[reference.RECEIPTS] == {key: 'settled' for key in reference._operation_keys(req)}
    finally:
        marker.delete()
        tombstone.delete()
        episode_ref.delete()


@pytest.mark.parametrize('change', ['account', 'tombstone', 'handback'])
def test_lost_authority_after_episode_planning_aborts_the_receiver_write(claim, monkeypatch, change):
    from database import episodes
    from utils.conversations import process_conversation as processor
    from utils.episodes import service

    client, row, job, req = claim
    req = req.model_copy(update={'step': 'effects-episode'})
    req.operation = req.expected_operation()
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    row.update(
        {'id': req.conversation, 'created_at': stamp, 'started_at': stamp, 'finished_at': stamp, 'structured': {}}
    )
    target = row.parent.parent.collection('episodes').document('fixture-episode')
    target.set({'id': target.id, 'status': 'closed', 'state_version': 1, 'conversation_ids': [req.conversation]})
    marker = client.collection('account_deletions').document(req.owner)
    tombstone = row.parent.parent.collection('deleted_conversations').document(req.conversation)

    def reconcile(*_args, **_kwargs):
        # The receiver has finished effects and the episode planner has read its
        # candidate. The actual writer must check live deletion inside its CAS.
        version = target.get().to_dict()['state_version']
        if change == 'account':
            marker.set({'wipe_status': 'running'})
        elif change == 'tombstone':
            tombstone.set({'conversation_id': req.conversation})
        else:
            row.update({'finalization_engine': 'python', 'finalization_owner_epoch': 3})
        episodes.update_episode(req.owner, target.id, expected_version=version, updates={}, firestore_client=client)
        pytest.fail('episode write accepted after losing authority')

    monkeypatch.setattr(processor, 'apply_eager_sync_enrichment', lambda *_: None)
    monkeypatch.setattr(service, 'on_conversation_finalized', reconcile)
    try:
        response = reference._adapt(client, req)
        assert response.status_code == 409
        assert target.get().to_dict()['state_version'] == 1
        assert reference.DERIVED_EFFECTS_TRANSCRIPT_FIELD not in row.get().to_dict()
        effects, _ = reference._operation_keys(req)
        assert job.get().to_dict()[reference.RECEIPTS] == {effects: 'settled'}
    finally:
        marker.delete()
        tombstone.delete()
        target.delete()


@pytest.mark.parametrize('change', [None, 'account', 'tombstone'])
def test_scheduled_go_compose_fences_deletion_after_planning(claim, monkeypatch, change):
    from utils.episodes import composer, service

    client, row, job, req = claim
    req = req.model_copy(update={'step': 'episode-reconcile'})
    req.operation = req.expected_operation()
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    row.update({'id': req.conversation, 'created_at': stamp, 'started_at': stamp, 'finished_at': stamp})
    target = row.parent.parent.collection('episodes').document('fixture-episode')
    target.set({'id': target.id, 'status': 'closed', 'state_version': 1, 'conversation_ids': [req.conversation]})
    original = target.get().to_dict()
    marker = client.collection('account_deletions').document(req.owner)
    tombstone = row.parent.parent.collection('deleted_conversations').document(req.conversation)
    queued = []
    planned = []

    def reconcile(uid, *_args, collaborators, **_kwargs):
        assert composer.schedule(uid, target.id, collaborators=collaborators, trigger='member_final')
        assert not queued
        return 'updated'

    def compose(uid, episode_id, collaborators, **_kwargs):
        def finish(current):
            assert current['state_version'] == 1
            planned.append(True)
            if change == 'account':
                marker.set({'wipe_status': 'running'})
            elif change == 'tombstone':
                tombstone.set({'conversation_id': req.conversation})
            return {'title': 'Synthetic composed notes'}

        return composer._write(uid, episode_id, collaborators, finish)

    monkeypatch.setattr(service, 'on_conversation_finalized', reconcile)
    monkeypatch.setattr(composer, 'episode_composer_enabled', lambda: True)
    monkeypatch.setattr(composer, 'episode_compose_settle_enabled', lambda: False)
    monkeypatch.setattr(composer._executor, 'submit', queued.append)
    monkeypatch.setattr(composer, '_compose', compose)
    try:
        assert reference._adapt(client, req) == {}
        assert job.get().to_dict()[reference.RECEIPTS] == {req.operation: 'settled'}
        assert len(queued) == 1
        queued[0]()
        assert planned == [True]
        stored = target.get().to_dict()
        if change is None:
            assert stored['state_version'] == 2
            assert stored['content']
        else:
            assert stored == original
    finally:
        marker.delete()
        tombstone.delete()
        target.delete()
