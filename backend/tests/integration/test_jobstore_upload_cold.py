"""Actual result reservation/publication -> conditional cold copy and erasure.

SDK Firestore/private PG are real; resumable storage is local, never remote C4.
Original source and unique repair context remain after every phase receipt.
"""

from types import SimpleNamespace

import pytest
from google.cloud.firestore_v1.types import CommitRequest

from database import legal_holds
from database.batch_pipeline_conversation_purge import purge_conversation
from database.batch_pipeline_purge import provider_result_artifacts, purge_batch_owner
from database.conversation_batch_purge_jobs import GATE_KIND
from database.jobstore.authority import AuthorityRefused, journal
from database.jobstore.cold_sink import ColdSink
from database.jobstore.cold_purge import erase_recording
from database.jobstore.retained_copies import RetainedCopies, RetainedCopiesPending
from database.jobstore.upload_cold_custody import FAMILY, descriptor
from database.privacy_fence.protocol import conversation_key, lock
from database.privacy_fence import FenceRefused
from tests.integration.test_jobstore_handoff import context  # noqa: F401
from tests.integration.test_jobstore_provider_effect import paid  # noqa: F401
from tests.integration.test_jobstore_provider_handoff import upload
from tests.integration.test_jobstore_result_sessions import result, row  # noqa: F401
from utils.batch_pipeline.contracts import WorkItem, WorkResult
from utils.other import local_storage

pytestmark = pytest.mark.integration


@pytest.fixture
def upload_cold(result):
    adapter, _, ticket, item, storage, artifacts = result
    uri = artifacts.persist_result(item, {'words': ['original']})
    h = adapter.handoff
    with h.pool.connection() as conn, conn.transaction():
        conn.execute('UPDATE queue_authority SET copier_stopped=false WHERE namespace=%s', (h.ticket.namespace,))
        rows = conn.execute(
            'SELECT seq,epoch,family,identity,operation,owner_key,body FROM queue_journal '
            'WHERE namespace=%s ORDER BY seq',
            (h.ticket.namespace,),
        ).fetchall()
    return SimpleNamespace(
        result=result,
        handoff=h,
        uid=item.owner_id,
        ticket=ticket,
        item=item,
        uri=uri,
        rows=rows,
        sink=ColdSink(h),
        identity=row(result)['recording_id'],
    )


def close(c):
    assert c.ticket.complete(WorkResult(c.item.segment_id, c.uri).to_dict(), now=202, partial_wait=30)
    cid = c.ticket.conversation_ids[0]
    c.handoff.client.document(f'users/{c.uid}/deleted_conversations/{cid}').set({'id': cid})
    c.handoff.fence.close(
        c.ticket.owner, conversation=conversation_key(c.ticket.owner, cid), state='deleted', local=True
    )
    retained = RetainedCopies(c.handoff)
    identity, manifest = retained.inventory(c.uid, cid)[0]
    return retained, cid, identity, manifest


def unit(c):
    return legal_holds.bounded_destructive_unit(c.uid, kind=GATE_KIND, firestore_client=c.handoff.client)


def upload_rows(c):
    return [r for r in c.rows if r[2] == FAMILY]


def test_actual_published_result_cold_replay_keeps_original_attempt_and_exact_deadline(upload_cold):
    c = upload_cold
    assert c.sink.page(limit=100) == len(c.rows)
    versions = upload_rows(c)
    assert {r[6]['phase'] for r in versions} == {'prepared', 'registered', 'published'}
    packet = c.sink.ref(FAMILY, versions[-1][3]).get().to_dict()
    assert packet['body'] == versions[-1][6] and packet['cold_only']
    assert packet['original_deadlines'] == {c.item.segment_id: row(c.result)['original_deadline']}
    assert 'session' not in str(packet)  # capabilities never leave the registry
    with c.handoff.pool.connection() as conn:
        source, path = conn.execute(
            'SELECT original_upload,cold_path FROM queue_upload_cold_custody WHERE namespace=%s',
            (c.handoff.ticket.namespace,),
        ).fetchone()
        original = c.handoff._required_row(conn, c.identity)
        census = conn.execute(
            'SELECT manifest FROM queue_cold_copy_custody WHERE namespace=%s', (c.handoff.ticket.namespace,)
        ).fetchone()[0]
        assert census == RetainedCopies(c.handoff)._manifest(original)
        assert path not in census['cold_paths']  # immutable extension, no rewrite
    assert source == descriptor(row(c.result))
    assert not list(c.handoff.client.collection(c.handoff.ticket.namespace + '_jobs').stream())


@pytest.mark.parametrize('copied', [True, False])
def test_mode_independent_purge_censuses_upload_keys_even_when_copier_never_ran(upload_cold, copied, monkeypatch):
    c = upload_cold
    if copied:
        c.sink.page(limit=100)
    retained, cid, identity, manifest = close(c)
    monkeypatch.setenv('BATCH_PIPELINE_JOBSTORE_SHADOW_MODE', 'off')
    with unit(c) as authority:
        receipt = erase_recording(retained, c.uid, identity, manifest, authority, conversation=cid)
    ref = c.sink.ref(FAMILY, upload_rows(c)[0][3])
    assert ref.path in receipt['keys'] and not ref.get().exists
    for r in upload_rows(c):
        c.sink.apply(r, timeout=1.5)
    assert not ref.get().exists
    assert row(c.result)['phase'] == 'published'
    intake = c.handoff.client.collection(c.handoff.ticket.namespace + '_intakes').document(identity).get().to_dict()
    assert intake['repair_lineage'] == 'synthetic-original'
    with c.handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT count(*) FROM queue_upload_cold_custody WHERE namespace=%s', (c.handoff.ticket.namespace,)
        ).fetchone() == (1,)
        assert conn.execute(
            'SELECT count(*) FROM queue_journal WHERE namespace=%s', (c.handoff.ticket.namespace,)
        ).fetchone()[0] > len(c.rows)


@pytest.mark.parametrize('table', ['queue_upload_cold_custody', 'queue_provider_uploads', 'queue_journal'])
def test_sql_cannot_drop_original_or_extension_before_all_copy_proof(upload_cold, table):
    c = upload_cold
    c.sink.apply(upload_rows(c)[0], timeout=1.5)
    with c.handoff.pool.connection() as conn, pytest.raises(Exception, match='custody|retirement|original PG'):
        with conn.transaction():
            lock(conn, c.ticket.owner, exclusive=True)
            conn.execute("SELECT set_config('omi.queue_epoch','3',true)")
            conn.execute(f'DELETE FROM {table} WHERE namespace=%s', (c.handoff.ticket.namespace,))


def test_sql_extension_requires_owner_x_and_immutable_source(upload_cold):
    c = upload_cold
    c.sink.apply(upload_rows(c)[0], timeout=1.5)
    with c.handoff.pool.connection() as conn:
        with pytest.raises(Exception, match='owner'):
            with conn.transaction():
                conn.execute(
                    'UPDATE queue_upload_cold_custody SET cold_path=cold_path WHERE namespace=%s',
                    (c.handoff.ticket.namespace,),
                )
        with pytest.raises(Exception, match='retirement'):
            with conn.transaction():
                lock(conn, c.ticket.owner, exclusive=True)
                conn.execute(
                    "UPDATE queue_upload_cold_custody SET original_upload='{}' WHERE namespace=%s",
                    (c.handoff.ticket.namespace,),
                )


def test_upload_lost_real_fs_reply_does_not_advance_checkpoint(upload_cold, monkeypatch):
    c = upload_cold
    api = c.handoff.client._firestore_api
    real, lost = api.commit, []

    def commit(*a, **k):
        request = CommitRequest(k.get('request') or a[0])
        value = real(*a, **k)
        if (
            any(
                w.update and 'family' in w.update.fields and w.update.fields['family'].string_value == FAMILY
                for w in request.writes
            )
            and not lost
        ):
            lost.append(True)
            raise ConnectionError('lost upload cold COMMIT reply')
        return value

    monkeypatch.setattr(api, 'commit', commit)
    with pytest.raises(ConnectionError):
        c.sink.page(limit=100)
    with c.handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT applied_seq FROM queue_authority WHERE namespace=%s', (c.handoff.ticket.namespace,)
        ).fetchone() == (0,)
    assert c.sink.page(limit=100) == len(c.rows)


def test_upload_stale_version_cannot_replace_published_cold_state(upload_cold):
    c = upload_cold
    first, last = upload_rows(c)[0], upload_rows(c)[-1]
    c.sink.apply(last, timeout=1.5)
    c.sink.apply(first, timeout=1.5)
    assert c.sink.ref(FAMILY, last[3]).get().to_dict()['body']['phase'] == 'published'
    changed = (*last[:6], {**last[6], 'session': 'forbidden-capability'})
    with pytest.raises(AuthorityRefused, match='version/payload'):
        c.sink.apply(changed, timeout=1.5)


@pytest.mark.parametrize(
    'field,value',
    [
        ('attempt_token', 'foreign'),
        ('original_deadline', 99999),
        ('admission_id', 'foreign'),
        ('session', 'not-a-capability'),
        ('phase', 'fenced'),
    ],
)
def test_real_journal_cannot_export_unknown_upload_source_fields(upload_cold, field, value):
    c = upload_cold
    last = upload_rows(c)[-1]
    with c.handoff.pool.connection() as conn, conn.transaction():
        journal(conn, c.handoff.ticket, FAMILY, last[3], c.ticket.owner, {**last[6], field: value})
    with pytest.raises(AuthorityRefused, match='source/admission/lifetime'):
        c.sink.page(limit=100)
    with c.handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT applied_seq FROM queue_authority WHERE namespace=%s', (c.handoff.ticket.namespace,)
        ).fetchone() == (0,)


@pytest.mark.parametrize('changed', ['seq', 'body', 'generation', 'fingerprint', 'unknown_old_seq'])
def test_purge_refuses_unknown_newer_or_changed_upload_destination(upload_cold, changed):
    c = upload_cold
    target = upload_rows(c)[-1]
    c.sink.apply(target, timeout=1.5)
    ref = c.sink.ref(FAMILY, target[3])
    packet = ref.get().to_dict()
    if changed == 'seq':
        packet['seq'] += 1000
    elif changed == 'unknown_old_seq':
        packet['seq'] = 0
    elif changed == 'generation':
        packet['body']['generation'] += 1
    elif changed == 'fingerprint':
        packet['source_fingerprint'] = 'foreign'
    else:
        packet['body']['attempt_token'] = 'unknown'
    ref.set(packet)
    retained, cid, identity, manifest = close(c)
    with unit(c) as authority, pytest.raises(AuthorityRefused, match='destination version/source'):
        erase_recording(retained, c.uid, identity, manifest, authority, conversation=cid)
    assert ref.get().exists and not c.sink.barrier(identity).get().exists


@pytest.mark.parametrize('changed', ['epoch', 'token', 'restore'])
def test_upload_original_paid_admission_and_transaction_authority_are_required(upload_cold, monkeypatch, changed):
    c = upload_cold
    if changed == 'epoch':
        c.handoff.authority.ref.update({'epoch': 4})
    elif changed == 'restore':
        c.handoff.fence.close(c.ticket.owner, local=True)
        c.handoff.fence.admit_from_authority(c.handoff.client, c.uid, c.ticket.conversation_ids, lambda *_: None)
    else:
        real = c.handoff.fence.admit_from_authority

        def admit(*a, **k):
            value = real(*a, **k)
            c.handoff.client.collection('batch_pipeline_privacy').document(c.ticket.owner).update(
                {'memo_token': 'rotated'}
            )
            return value

        monkeypatch.setattr(c.handoff.fence, 'admit_from_authority', admit)
    with pytest.raises((AuthorityRefused, FenceRefused)):
        c.sink.apply(upload_rows(c)[-1], timeout=1.5)
    assert not c.sink.ref(FAMILY, upload_rows(c)[-1][3]).get().exists


def test_upload_copy_and_purge_release_sql_slots_and_guards_before_fs_io(upload_cold, monkeypatch):
    c = upload_cold
    real, checks = c.handoff.authority.check, []

    def check(*a, **k):
        with c.handoff.pool.connection(timeout=2) as one, c.handoff.pool.connection(timeout=2) as two:
            with one.transaction():
                one.execute("SET LOCAL lock_timeout='2s'")
                lock(one, c.ticket.owner, exclusive=True)
                assert two.execute('SELECT 1').fetchone() == (1,)
        checks.append(True)
        return real(*a, **k)

    monkeypatch.setattr(c.handoff.authority, 'check', check)
    c.sink.apply(upload_rows(c)[-1], timeout=1.5)
    retained, cid, identity, manifest = close(c)
    with unit(c) as authority:
        erase_recording(retained, c.uid, identity, manifest, authority, conversation=cid)
    assert len(checks) >= 3


@pytest.mark.parametrize('scope', ['conversation', 'account'])
def test_actual_artifactstore_to_production_purge_covers_upload_cold(context, tmp_path, monkeypatch, scope):
    h, uid = context
    storage = local_storage.LocalStorageClient(tmp_path)
    audio = storage.bucket('synthetic').blob(f'syncing/{uid}/audio/segment-0')
    audio.upload_from_string(b'original-audio')
    adapter, binding, _, _ = upload(
        context, monkeypatch, count=1, audio_uris={'segment-0': f'gs://synthetic/{audio.name}#{audio.generation}'}
    )
    adapter.deliver(binding.job_id)
    (job,) = adapter.units.claim(1, now=201, lease_seconds=30, backlog_share=0)
    ticket = adapter.fence_ticket(job['unit_id'], job['attempt_token'], lease_seconds=60)
    item = WorkItem(**{k: v for k, v in ticket.source.items() if k in WorkItem.__dataclass_fields__})
    ticket.start(item, 'modulate')
    monkeypatch.setenv('BUCKET_BATCH_PIPELINE', 'synthetic')
    monkeypatch.setattr(local_storage, 'create_storage_client', lambda: storage)
    artifacts = provider_result_artifacts(ticket, storage, 'synthetic', b'x' * 32, lease_seconds=60)
    uri = artifacts.persist_result(item, {'words': ['ordinary']})
    assert ticket.complete(WorkResult(item.segment_id, uri).to_dict(), now=202, partial_wait=30)
    sink = ColdSink(h)
    with h.pool.connection() as conn, conn.transaction():
        conn.execute('UPDATE queue_authority SET copier_stopped=false WHERE namespace=%s', (h.ticket.namespace,))
        original = h._required_row(conn, binding.job_id)
    sink.page(limit=100)
    cid = ticket.conversation_ids[0]
    h.client.document(f'users/{uid}/deleted_conversations/{cid}').set({'id': cid})
    h.fence.close(ticket.owner, conversation=conversation_key(ticket.owner, cid), state='deleted', local=True)
    c = SimpleNamespace(uid=uid, handoff=h)
    progress = SimpleNamespace(position={}, expired=lambda: False, unit=lambda: unit(c), settle_stuck=lambda _: None)
    monkeypatch.setenv('BATCH_PIPELINE_JOBSTORE_SHADOW_MODE', 'off')
    if scope == 'account':
        # Seed the terminal prerequisite, not a claim that production account
        # close/drain orchestration has been implemented or qualified.
        h.fence.close(ticket.owner, reason='deleted', local=True)
        with h.pool.connection() as conn, conn.transaction():
            lock(conn, ticket.owner, exclusive=True)
            conn.execute(
                "UPDATE privacy_owner_fence SET state='purging',close_reason='deleted',purge_generation=generation "
                'WHERE owner_key=%s',
                (ticket.owner,),
            )
        with unit(c) as authority, pytest.raises(RetainedCopiesPending, match='certification remains'):
            purge_batch_owner(
                uid,
                firestore_client=h.client,
                namespaces=(h.ticket.namespace,),
                retained_copies=RetainedCopies(h),
                destructive_authority=authority,
            )
    else:
        with pytest.raises(RetainedCopiesPending, match='certification remains'):
            purge_conversation(uid, cid, progress, firestore_client=h.client, retained_copies=RetainedCopies(h))
    barrier = sink.barrier(binding.job_id).get().to_dict()
    assert any(k['family'] == FAMILY for k in barrier['keys'].values())
    assert all(not h.client.document(path).get().exists for path in barrier['keys'])
    assert not list(storage.bucket('synthetic').list_blobs())
    with h.pool.connection() as conn:
        assert h._required_row(conn, binding.job_id) == original
        assert conn.execute(
            'SELECT phase FROM queue_provider_uploads WHERE namespace=%s', (h.ticket.namespace,)
        ).fetchone() == ('published',)
    assert (
        h.client.collection(h.ticket.namespace + '_intakes').document(binding.job_id).get().to_dict()['repair_lineage']
    )
