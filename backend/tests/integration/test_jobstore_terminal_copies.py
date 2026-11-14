"""Actual result-session drain -> retained-copy purge. Local transport, not remote C4."""

from types import SimpleNamespace

import pytest
from psycopg import OperationalError  # pyright: ignore[reportMissingImports]

from database import legal_holds
from database.batch_pipeline_conversation_purge import purge_conversation
from database.batch_pipeline_purge import purge_batch_owner
from database.conversation_batch_purge_jobs import GATE_KIND
from database.jobstore.authority import AuthorityRefused
from database.jobstore.gcs_sink import GCSSink, PREFIX
from database.jobstore.published_copies import PublishedCopies, payload
from database.jobstore.retained_copies import RetainedCopies, RetainedCopiesPending
from database.jobstore.terminal_uploads import require_terminal
from database.privacy_fence.protocol import conversation_key, lock
from tests.integration.test_jobstore_handoff import context  # noqa: F401
from tests.integration.test_jobstore_provider_effect import paid  # noqa: F401
from tests.integration.test_jobstore_result_sessions import result, row, effect  # noqa: F401
from tests.integration.test_jobstore_result_sessions import (
    test_real_terminal_proof_and_pg_retirement_process_exit as crash_retirement,
)
from utils.batch_pipeline.contracts import WorkResult
from utils.batch_pipeline.upload_policy import UPLOAD_TIMEOUT
from utils.other import local_storage

pytestmark = pytest.mark.integration


@pytest.fixture(params=['finalized', 'cancelled', 'collision'])
def terminal(result, request, monkeypatch):
    adapter, _, ticket, item, storage, artifacts = result
    mode = request.param

    def fail(*args):
        raise ConnectionError('original request reply unknown')

    def collide(*args):
        sink = effect(result)['sink']
        storage.bucket(sink['bucket']).blob(sink['key']).upload_from_string(b'foreign', if_generation_match=0)
        storage._http.before_request = None

    if mode == 'finalized':
        storage._http.after_request = fail
    else:
        storage._http.before_request = fail if mode == 'cancelled' else collide
    with pytest.raises(ConnectionError):
        artifacts.persist_result(item, {'words': ['original']})
    storage._http.before_request = storage._http.after_request = None
    handoff = adapter.handoff
    conversation = ticket.conversation_ids[0]
    handoff.client.document(f'users/{item.owner_id}/deleted_conversations/{conversation}').set({'id': conversation})
    handoff.fence.close(
        ticket.owner, conversation=conversation_key(ticket.owner, conversation), state='deleted', local=True
    )
    assert not ticket.complete(WorkResult(item.segment_id, 'unused-after-close').to_dict(), now=202, partial_wait=30)
    original_sink = effect(result)['sink']
    unit = lambda: legal_holds.bounded_destructive_unit(item.owner_id, kind=GATE_KIND, firestore_client=handoff.client)
    sink = GCSSink(handoff, storage, timeout=UPLOAD_TIMEOUT)
    with unit() as authority:
        sink.authority = authority
        sink.finish(original_sink)
    retained = RetainedCopies(handoff)
    monkeypatch.setattr(local_storage, 'create_storage_client', lambda: storage)
    return SimpleNamespace(
        result=result,
        mode=mode,
        handoff=handoff,
        retained=retained,
        copies=PublishedCopies(retained, storage_client=storage),
        sink=sink,
        original_sink=original_sink,
        uid=item.owner_id,
        identity=result[1]['recording_id'],
        conversation=conversation,
        unit=unit,
    )


def receipt(r):
    with r.handoff.pool.connection() as conn:
        return require_terminal(conn, row(r.result))


def prepare(r, authority):
    identity, manifest = r.retained.inventory(r.uid, r.conversation)[0]
    r.retained.retire_private(r.uid, identity, manifest, authority, conversation=r.conversation)


def test_actual_conversation_purge_joins_terminal_original_receipt(terminal):
    r = terminal
    original, proof = row(r.result), receipt(r)
    assert proof['original_deadline'] == original['original_deadline']
    assert proof['status'] == {'finalized': 200, 'cancelled': 499, 'collision': 412}[r.mode]
    assert 'session' not in proof
    assert all(r.original_sink['session'] not in str(value) for value in proof.values())
    assert r.copies._reference(original).get().exists
    progress = SimpleNamespace(position={}, expired=lambda: False, unit=r.unit, settle_stuck=lambda _: None)
    with pytest.raises(RetainedCopiesPending, match='complete ordinary source required'):
        purge_conversation(
            r.uid, r.conversation, progress, firestore_client=r.handoff.client, retained_copies=r.retained
        )
    assert not r.copies._reference(original).get().exists
    assert row(r.result) == original and receipt(r) == proof
    blobs = list(r.result[4].bucket('synthetic').list_blobs())
    assert len(blobs) == (1 if r.mode == 'collision' else 0)
    if blobs:
        assert blobs[0].download_as_bytes() == b'foreign'
    with r.handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT purpose,state FROM queue_original_erasure_operations WHERE namespace=%s ORDER BY purpose',
            (original['namespace'],),
        ).fetchall() == [('fenced_object', 'committed'), ('fenced_reference', 'committed')]
    with r.unit() as authority:
        r.copies.retire(r.uid, r.identity, authority, conversation=r.conversation)


def test_reference_needs_committed_original_terminal_object_phase(terminal):
    r = terminal
    with r.unit() as authority:
        prepare(r, authority)
        with pytest.raises(AuthorityRefused, match='object proof'):
            r.copies.operations.prepare(
                r.uid, r.identity, authority, 'fenced_reference', payload(row(r.result)), conversation=r.conversation
            )


def test_receipt_original_identity_and_absence_are_required(terminal):
    r = terminal
    original = row(r.result)
    with r.handoff.pool.connection() as conn:
        for mutation in ({'attempt_token': 'successor'}, {'generation': 777}, {'original_deadline': 1}):
            with pytest.raises(AuthorityRefused, match='terminal-session receipt'):
                require_terminal(conn, dict(original, **mutation))
        with conn.transaction():
            lock(conn, original['owner_key'], exclusive=True)
            for query in (
                'UPDATE queue_upload_terminal_receipts SET status=499 WHERE namespace=%s',
                'DELETE FROM queue_upload_terminal_receipts WHERE namespace=%s',
            ):
                with pytest.raises(Exception), conn.transaction():
                    conn.execute(query, (original['namespace'],))
    # A missing receipt must never be inferred from fenced phase or missing registry.
    with r.handoff.pool.connection() as conn, conn.transaction():
        lock(conn, original['owner_key'], exclusive=True)
        conn.execute('ALTER TABLE queue_upload_terminal_receipts DISABLE TRIGGER USER')
        conn.execute('DELETE FROM queue_upload_terminal_receipts WHERE namespace=%s', (original['namespace'],))
        conn.execute('ALTER TABLE queue_upload_terminal_receipts ENABLE TRIGGER USER')
    with pytest.raises(AuthorityRefused, match='terminal-session receipt'):
        r.sink.recover(r.uid, PREFIX + original['namespace'] + ':' + str(original['effect_id']))
    with r.unit() as authority:
        prepare(r, authority)
        with pytest.raises(AuthorityRefused, match='terminal-session receipt'):
            r.copies.retire(r.uid, r.identity, authority, conversation=r.conversation)
    assert r.copies._reference(original).get().exists


@pytest.mark.parametrize('gap', ['before_retirement', 'after_retirement'])
def test_terminal_receipt_and_registry_share_actual_process_exit_commit(result, gap):
    # Reuse the actual SQL/SDK subprocess crash harness; now assert the newly
    # durable receipt joins that COMMIT rather than merely a phase marker.
    crash_retirement(result, gap)
    with result[0].units.pool.connection() as conn:
        proof = require_terminal(conn, row(result))
    assert proof['generation'] == row(result)['generation'] and effect(result) is None


def test_actual_account_purge_joins_terminal_original_receipt(terminal):
    r = terminal
    original = row(r.result)
    r.handoff.fence.close(original['owner_key'], reason='deleted', local=True)
    # Account close/drain orchestration is not installed: explicitly seed its
    # terminal prerequisite rather than claiming production qualification.
    with r.handoff.pool.connection() as conn, conn.transaction():
        lock(conn, original['owner_key'], exclusive=True)
        conn.execute(
            "UPDATE privacy_owner_fence SET state='purging',close_reason='deleted',purge_generation=generation WHERE owner_key=%s",
            (original['owner_key'],),
        )
    with r.unit() as authority:
        with pytest.raises(RetainedCopiesPending, match='complete ordinary source required'):
            purge_batch_owner(
                r.uid,
                firestore_client=r.handoff.client,
                namespaces=(original['namespace'],),
                retained_copies=r.retained,
                destructive_authority=authority,
            )
    assert not r.copies._reference(original).get().exists
    assert row(r.result) == original and receipt(r)


def test_lost_reference_commit_reply_keeps_original_terminal_evidence(terminal, monkeypatch):
    r = terminal
    original = row(r.result)
    actual, lost = r.copies._check, []

    def check(*args, **kwargs):
        actual(*args, **kwargs)
        if kwargs.get('erase') and not lost:
            lost.append(True)
            raise ConnectionError('reference COMMIT reply lost')

    monkeypatch.setattr(r.copies, '_check', check)
    with r.unit() as authority:
        prepare(r, authority)
        with pytest.raises(ConnectionError, match='reply lost'):
            r.copies.retire(r.uid, r.identity, authority, conversation=r.conversation)
        assert not r.copies._reference(original).get().exists
        assert receipt(r)
        r.copies.retire(r.uid, r.identity, authority, conversation=r.conversation)
    assert row(r.result) == original


def test_cancelled_terminal_progress_fences_a_paused_sql_executor(terminal):
    r = terminal
    with r.unit() as authority:
        prepare(r, authority)
        target = r.copies.operations.prepare(
            r.uid, r.identity, authority, 'fenced_object', payload(row(r.result)), conversation=r.conversation
        )
        assert r.copies.operations.resolve(r.uid, target)
        with pytest.raises(AuthorityRefused, match='cancelled'):
            r.copies.operations.finish(r.uid, target, authority, conversation=r.conversation)
        assert r.copies._reference(row(r.result)).get().exists
        r.copies.retire(r.uid, r.identity, authority, conversation=r.conversation)


def test_raw_sql_fenced_retirement_cannot_skip_terminal_receipt(result):
    adapter, _, ticket, item, storage, artifacts = result
    storage._http.after_request = lambda *args: (_ for _ in ()).throw(ConnectionError('lost finalize'))
    with pytest.raises(ConnectionError):
        artifacts.persist_result(item, {})
    storage._http.after_request = None
    adapter.units.fence.close(ticket.owner, local=True)
    source = effect(result)
    sink = GCSSink(adapter.handoff, storage, timeout=UPLOAD_TIMEOUT)
    with legal_holds.bounded_destructive_unit(
        item.owner_id, kind=GATE_KIND, firestore_client=adapter.handoff.client
    ) as authority:
        sink.authority = authority
        proof = sink(source['sink'])
        # Neither an isolated proof insert/fenced marker nor a registry DELETE
        # can escape the actual joined transaction.
        with pytest.raises(Exception, match='share COMMIT'):
            with adapter.units.pool.connection() as conn, conn.transaction():
                lock(conn, ticket.owner, exclusive=True)
                sink.retire(conn, source, proof)
        with adapter.units.pool.connection() as conn:
            assert not conn.execute(
                'SELECT 1 FROM queue_upload_terminal_receipts WHERE namespace=%s', (adapter.units.namespace,)
            ).fetchone()
        with pytest.raises(Exception, match='terminal proof'):
            with adapter.units.pool.connection() as conn, conn.transaction():
                lock(conn, ticket.owner, exclusive=True)
                sink._epoch(conn)
                conn.execute(
                    "UPDATE queue_provider_uploads SET phase='fenced' WHERE namespace=%s", (adapter.units.namespace,)
                )
                adapter.units.fence._retire(conn, source)
        sink.finish(source['sink'])
        assert effect(result) is None
        with adapter.units.pool.connection() as conn:
            assert require_terminal(conn, row(result))


@pytest.mark.parametrize('terminal', ['cancelled', 'collision'], indirect=True)
def test_receipt_transport_error_pins_actual_destructive_gate(terminal, monkeypatch):
    r = terminal
    original = row(r.result)
    assert original['generation'] is None and receipt(r)

    def disconnected(*args, **kwargs):
        raise OperationalError('synthetic PG transport lost')

    with pytest.raises(ConnectionError, match='lookup unresolved'):
        with r.unit() as authority:
            monkeypatch.setattr(r.handoff.pool, 'connection', disconnected)
            authority.remote(lambda: r.copies._absent(r.uid, original), target=payload(original)['uri'])
    gate = r.handoff.client.collection(legal_holds.LEGAL_HOLD_DELETION_GATES_COLLECTION).document(r.uid).get().to_dict()
    assert gate['remote_inflight'] and gate['remote_target'] == payload(original)['uri']
    assert r.copies._reference(original).get().exists
