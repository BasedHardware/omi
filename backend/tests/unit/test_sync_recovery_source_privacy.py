"""Original same-owner deletion authority survives receipt-clock isolation."""

from copy import deepcopy
from pathlib import Path

import pytest

from database import _client
from utils.sync.recovery_source import recovery_source_conversation
from database.batch_pipeline_privacy import assert_batch_write_allowed, BatchPrivacyBlocked
from tests.unit.test_batch_pipeline_scheduler import MemoryTransaction
from utils.sync.content_id import compute_sync_content_id
from utils.batch_pipeline.retention import batch_artifact_authorize
from database.batch_pipeline_projection_session import ProjectionSession
from types import SimpleNamespace
from routers import sync as router
from database.batch_pipeline_privacy import privacy_owner_key
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument
from tests.unit.test_sync_future_recovery_admission import admission, client, anchors, _default_skew, FUTURE
from tests.unit.test_batch_pipeline_audio import pcm
from utils.sync.deleted_conversation import deleted_conversation_result


@pytest.fixture
def source_privacy(admission, monkeypatch):
    http, jobs, database, staged = admission
    database.rows['users', 'synthetic-uid'] = {'data_protection_level': 'standard'}
    monkeypatch.setattr(_client, 'get_firestore_client', lambda: database)
    monkeypatch.setattr(router, 'recovery_source_conversation', recovery_source_conversation)
    reads = []
    original = StrictFirestoreDocument.get

    def owned_read(ref, *args, **kwargs):
        reads.append(ref.path)
        if ref.path[0] == 'users':
            assert ref.path[1] == 'synthetic-uid', 'cross-account source lookup'
        return original(ref, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', owned_read)
    return http, jobs, database, staged, reads


def send(http, tmp_path, target):
    path = Path(pcm(tmp_path, int(FUTURE), 16000))
    return http.post(
        '/v2/sync-local-files',
        params={'conversation_id': target} if target is not None else {},
        files=[('files', (path.name, path.read_bytes(), 'application/octet-stream'))],
    )


@pytest.mark.parametrize('deletion', ['soft', 'tombstone'])
def test_recovered_deleted_source_returns_existing_terminal_ack_without_admission(source_privacy, tmp_path, deletion):
    http, jobs, database, staged, reads = source_privacy
    if deletion == 'soft':
        database.rows['users', 'synthetic-uid', 'conversations', 'source'] = {'id': 'source', 'deleted': True}
    else:
        database.rows['users', 'synthetic-uid', 'deleted_conversations', 'source'] = {}
    before = deepcopy(database.rows)
    response = send(http, tmp_path, 'source')
    assert response.status_code == 200, response.text
    assert response.json() == deleted_conversation_result(0)
    assert not jobs.rows and not staged
    assert database.rows == before
    assert ('users', 'synthetic-uid', 'deleted_conversations', 'source') in reads


def test_recovery_privacy_delete_lock_keeps_existing_privacy_refusal(source_privacy, tmp_path):
    http, jobs, database, staged, reads = source_privacy
    database.rows['users', 'synthetic-uid', 'conversations', 'source'] = {'id': 'source'}
    database.rows['batch_pipeline_privacy', privacy_owner_key('synthetic-uid')] = {'purging': True}
    response = send(http, tmp_path, 'source')
    assert response.status_code == 409 and response.json()['code'] == 'sync_batch_privacy_blocked'
    assert not jobs.rows and not staged


@pytest.mark.parametrize('target', ['live', 'unknown', 'foreign'])
def test_recovery_live_unknown_and_foreign_targets_stay_isolated_and_owner_scoped(source_privacy, tmp_path, target):
    http, jobs, database, staged, reads = source_privacy
    database.rows['users', 'synthetic-uid', 'conversations', 'live'] = {'id': 'live', 'title': 'Keep me'}
    database.rows['users', 'another-account', 'conversations', 'foreign'] = {'id': 'foreign', 'deleted': True}
    original = deepcopy(database.rows)
    response = send(http, tmp_path, target)
    assert response.status_code == 202, response.text
    assert staged[0][0].conversation_id.startswith('receipt-')
    assert staged[0][0].capture_source_conversation_id == ('live' if target == 'live' else None)
    for key, row in original.items():
        assert database.rows[key] == row
    assert ('users', 'synthetic-uid', 'deleted_conversations', target) in reads
    assert ('users', 'synthetic-uid', 'conversations', target) in reads


def test_no_target_exact_content_receipt_for_deleted_audio_returns_terminal_ack(source_privacy, tmp_path, monkeypatch):
    http, jobs, database, staged, reads = source_privacy
    path = Path(pcm(tmp_path, int(FUTURE), 16000))
    content = compute_sync_content_id('synthetic-uid', [str(path)])
    database.rows['users', 'synthetic-uid', 'deleted_conversations', 'original'] = {}
    result = {
        'new_memories': ['original'],
        'updated_memories': [],
        'failed_segments': 0,
        'total_segments': 1,
        'errors': [],
    }
    jobs.rows['content', f'synthetic-uid/{content}'] = {'status': 'completed', 'job_id': 'prior', 'result': result}

    def check(tx, uid, conversation_ids=(), expected_generation=None):
        return assert_batch_write_allowed(database, database.transaction(), uid, conversation_ids=conversation_ids)

    monkeypatch.setattr(MemoryTransaction, 'check_privacy', check)
    response = send(http, tmp_path, None)
    assert response.status_code == 200, response.text
    assert response.json() == deleted_conversation_result(1)
    assert not staged
    assert set(table for table, key in jobs.rows) == {'content'}
    assert ('users', 'synthetic-uid', 'deleted_conversations', 'original') in reads


def test_live_source_deleted_after_admission_remains_an_artifact_and_projection_fence(source_privacy, tmp_path):
    http, jobs, database, staged, reads = source_privacy
    database.rows['users', 'synthetic-uid', 'conversations', 'live'] = {'id': 'live'}
    assert send(http, tmp_path, 'live').status_code == 202
    item = staged[0][0]
    database.rows['users', 'synthetic-uid', 'deleted_conversations', 'live'] = {}
    with pytest.raises(BatchPrivacyBlocked, match='conversation_deleted'):
        batch_artifact_authorize(SimpleNamespace(client=database), item)
    session = object.__new__(ProjectionSession)
    session.client = database
    session.binding = SimpleNamespace(owner_id='synthetic-uid', privacy_generation=0)
    session.job = {'capture_source_conversation_id': 'live'}
    session._privacy_fence_ids = None
    with pytest.raises(BatchPrivacyBlocked, match='conversation_deleted'):
        session.guard(database.transaction(), ['isolated-part'])


def test_source_deleted_during_staging_cannot_commit_recovery_jobs(source_privacy, tmp_path, monkeypatch):
    from utils.batch_pipeline import intake

    http, jobs, database, staged, reads = source_privacy
    database.rows['users', 'synthetic-uid', 'conversations', 'live'] = {'id': 'live'}
    original = intake.artifacts_for(jobs).stage_audio

    def stage(item, wav, *, record_origin):
        uri = original(item, wav, record_origin=record_origin)
        database.rows['users', 'synthetic-uid', 'deleted_conversations', 'live'] = {}
        return uri

    monkeypatch.setattr(intake, 'artifacts_for', lambda *a: SimpleNamespace(stage_audio=stage))

    def check(tx, uid, conversation_ids=(), expected_generation=None):
        return assert_batch_write_allowed(database, database.transaction(), uid, conversation_ids=conversation_ids)

    monkeypatch.setattr(MemoryTransaction, 'check_privacy', check)
    response = send(http, tmp_path, 'live')
    assert response.status_code == 409, response.text
    assert not any(table in {'jobs', 'intakes', 'content'} for table, key in jobs.rows)


def test_unchanged_gpu_lease_checks_retained_source_on_cpu_compute_admission(monkeypatch):
    from tests.unit.test_batch_pipeline_admission import setup, tokens, authorize

    jobs, queue, lease, reserve = setup(monkeypatch)
    jobs.rows['jobs', 'segment']['capture_source_conversation_id'] = 'deleted-original'
    observed = []

    def check(tx, uid, conversation_ids=(), expected_generation=None):
        observed.extend(conversation_ids)
        if 'deleted-original' in conversation_ids:
            raise BatchPrivacyBlocked('conversation_deleted')
        return 0

    monkeypatch.setattr(MemoryTransaction, 'check_privacy', check)
    answer = authorize(jobs, tokens(lease), now=1)
    assert 'deleted-original' in observed
    assert answer['allowed'] == []
    assert answer['held_reason']['segment'] == 'privacy_blocked'
    reserve.assert_not_called()


def test_privacy_source_round_trips_without_changing_ordinary_worker_envelopes():
    from dataclasses import replace
    from utils.batch_pipeline.contracts import WorkItem, Priority

    ordinary = WorkItem('segment', 'owner', 1, 'gs://test/audio', 1, Priority(0))
    assert 'capture_source_conversation_id' not in ordinary.to_dict(include_nulls=True)
    isolated = replace(ordinary, capture_source_conversation_id='original')
    assert WorkItem(**isolated.to_dict()).capture_source_conversation_id == 'original'
    assert isolated.conversation_id is None
