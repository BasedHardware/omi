"""Real FS conditional cold writes/purge and PG source/checkpoint custody."""

from types import SimpleNamespace

import pytest
from google.cloud.firestore_v1.types import CommitRequest

from database.jobstore.authority import AuthorityRefused, replay_page, transition
from database.jobstore.cold_purge import erase_recording
from database.jobstore.cold_sink import ColdSink
from database.jobstore.retained_copies import RetainedCopies
from database.privacy_fence.protocol import conversation_key, lock, owner_key
from tests.integration.test_jobstore_handoff import context  # noqa: F401
from tests.integration.test_jobstore_provider_projection import lane  # noqa: F401

pytestmark = pytest.mark.integration


@pytest.fixture
def cold(lane):
    handoff = lane.view.handoff
    sink = ColdSink(handoff)
    with handoff.pool.connection() as conn, conn.transaction():
        conn.execute('UPDATE queue_authority SET copier_stopped=false WHERE namespace=%s', (handoff.ticket.namespace,))
        rows = conn.execute(
            'SELECT seq,epoch,family,identity,operation,owner_key,body FROM queue_journal '
            'WHERE namespace=%s ORDER BY seq',
            (handoff.ticket.namespace,),
        ).fetchall()
    return SimpleNamespace(handoff=handoff, sink=sink, rows=rows, view=lane.view, uid=lane.view.binding.owner_id)


def terminal(c):
    h = c.handoff
    with h.pool.connection() as conn:
        cid = h._required_row(conn, c.view.identity)['intent']['conversation_ids'][0]
    h.client.document(f'users/{c.uid}/deleted_conversations/{cid}').set({'id': cid})
    h.fence.close(owner_key(c.uid), conversation=conversation_key(owner_key(c.uid), cid), state='deleted', local=True)
    retained = RetainedCopies(h)
    identity, manifest = retained.inventory(c.uid, cid)[0]
    return retained, cid, identity, manifest


def unit(c):
    from database import legal_holds
    from database.conversation_batch_purge_jobs import GATE_KIND

    return legal_holds.bounded_destructive_unit(c.uid, kind=GATE_KIND, firestore_client=c.handoff.client)


def test_actual_cold_copier_checkpoints_exact_bodies_without_queue_rows_or_wakes(cold):
    c = cold
    assert c.sink.page(limit=100) == len(c.rows)
    latest = {}
    for row in c.rows:
        latest[c.sink.ref(row[2], row[3]).path] = row
    for path, row in latest.items():
        value = c.handoff.client.document(path).get().to_dict()
        assert value['cold_only'] and value['body'] == row[6]
        assert value['seq'] == row[0] and value['epoch'] == row[1]
        assert value['original_deadlines'] == {'one': 20000, 'two': 20000}
    with c.handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT applied_seq,committed_seq FROM queue_authority WHERE namespace=%s',
            (c.handoff.ticket.namespace,),
        ).fetchone() == (c.rows[-1][0], c.rows[-1][0])
        census = conn.execute(
            'SELECT manifest FROM queue_cold_copy_custody WHERE namespace=%s',
            (c.handoff.ticket.namespace,),
        ).fetchone()[0]
    assert set(latest) <= set(census['cold_paths'])
    assert not list(c.handoff.client.collection(c.handoff.ticket.namespace + '_jobs').limit(1).stream())


def test_outbox_cold_key_uses_original_admission_not_pg_id(cold):
    c = cold
    row = next(r for r in c.rows if r[2] == 'outbox')
    assert set(row[3]) == {'kind', 'dedupe_key', 'generation'}
    assert str(row[6]['id']) not in row[3].values()
    with c.handoff.pool.connection() as conn:
        original = c.handoff._required_row(conn, c.view.identity)
    assert row[3]['generation'] == original['admission']['admission_id']
    c.sink.apply(row, timeout=1.5)
    with pytest.raises(AuthorityRefused, match='version/payload'):
        c.sink.apply((row[0], row[1], row[2], {'id': row[6]['id']}, *row[4:]), timeout=1.5)


def test_stale_and_duplicate_pages_cannot_overwrite_newer_cold_version(cold):
    c = cold
    same = [r for r in c.rows if r[2] == 'units' and r[3]['unit_id'] == 'one']
    older, newer = same[0], same[-1]
    c.sink.apply(newer, timeout=1.5)
    c.sink.apply(older, timeout=1.5)
    c.sink.apply(newer, timeout=1.5)
    value = c.sink.ref(newer[2], newer[3]).get().to_dict()
    assert value['seq'] == newer[0]
    bad = list(newer)
    bad[6] = {**newer[6], 'due_at': 999999}
    with pytest.raises(AuthorityRefused, match='version/payload'):
        c.sink.apply(tuple(bad), timeout=1.5)


def test_lost_real_fs_commit_reply_replays_without_checkpoint_loss(cold, monkeypatch):
    c = cold
    api = c.handoff.client._firestore_api
    real = api.commit
    lost = []

    def commit(*a, **k):
        request = CommitRequest(k.get('request') or a[0])
        result = real(*a, **k)
        if any(w.update and 'cold_only' in w.update.fields for w in request.writes) and not lost:
            lost.append(True)
            raise ConnectionError('lost cold COMMIT reply')
        return result

    monkeypatch.setattr(api, 'commit', commit)
    with pytest.raises(ConnectionError):
        c.sink.page(limit=100)
    with c.handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT applied_seq FROM queue_authority WHERE namespace=%s', (c.handoff.ticket.namespace,)
        ).fetchone() == (0,)
    assert c.sink.page(limit=100) == len(c.rows)


def test_real_mode_independent_purge_blocks_delayed_put_and_preserves_journal(cold, monkeypatch):
    c = cold
    c.sink.page(limit=100)
    retained, cid, identity, manifest = terminal(c)
    monkeypatch.setenv('BATCH_PIPELINE_JOBSTORE_SHADOW_MODE', 'off')
    with unit(c) as authority:
        receipt = erase_recording(retained, c.uid, identity, manifest, authority, conversation=cid)
    assert receipt['through'] == c.rows[-1][0]
    assert all(not c.handoff.client.document(path).get().exists for path in receipt['keys'])
    for row in c.rows:
        c.sink.apply(row, timeout=1.5)
    assert all(not c.handoff.client.document(path).get().exists for path in receipt['keys'])
    assert c.sink.barrier(identity).get().to_dict()['original_deadlines'] == manifest['original_deadlines']
    with c.handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT count(*) FROM queue_journal WHERE namespace=%s', (c.handoff.ticket.namespace,)
        ).fetchone()[0] == len(c.rows)
    assert c.handoff.ref('intent', identity).get().exists


@pytest.mark.parametrize('table', ['units', 'queue_handoffs', 'queue_journal', 'queue_cold_copy_custody'])
def test_first_cold_copy_keeps_pg_custodian_before_privacy_purge_census(cold, table):
    c = cold
    c.sink.apply(c.rows[0], timeout=1.5)
    with c.handoff.pool.connection() as conn, pytest.raises(Exception, match='custody|original PG'):
        with conn.transaction():
            lock(conn, owner_key(c.uid), exclusive=True)
            conn.execute("SELECT set_config('omi.queue_epoch','3',true)")
            conn.execute(f'DELETE FROM {table} WHERE namespace=%s', (c.handoff.ticket.namespace,))


def test_epoch_change_during_actual_sink_commit_cannot_advance_old_checkpoint(cold, monkeypatch):
    c = cold
    api = c.handoff.client._firestore_api
    real = api.commit
    changed = []

    def commit(*a, **k):
        result = real(*a, **k)
        request = CommitRequest(k.get('request') or a[0])
        if any(w.update and 'cold_only' in w.update.fields for w in request.writes) and not changed:
            changed.append(True)
            with c.handoff.pool.connection() as conn, conn.transaction():
                transition(conn, c.handoff.ticket.namespace, 'PG_OPEN', 3, 'PG_CLOSING')
        return result

    monkeypatch.setattr(api, 'commit', commit)
    replay_page(c.handoff.pool, c.handoff.ticket.namespace, c.sink.apply, limit=1)
    with c.handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT applied_seq FROM queue_authority WHERE namespace=%s', (c.handoff.ticket.namespace,)
        ).fetchone() == (0,)


def test_token_rotation_between_real_admission_and_cold_commit_refuses(cold, monkeypatch):
    from uuid import uuid4

    c = cold
    real = c.handoff.fence.admit_from_authority

    def admit(*a, **k):
        value = real(*a, **k)
        c.handoff.client.collection('batch_pipeline_privacy').document(owner_key(c.uid)).update(
            {'memo_token': uuid4().hex}
        )
        return value

    monkeypatch.setattr(c.handoff.fence, 'admit_from_authority', admit)
    with pytest.raises(AuthorityRefused, match='token changed'):
        c.sink.page(limit=1)
    assert not c.sink.ref(c.rows[0][2], c.rows[0][3]).get().exists


def test_restored_owner_cannot_export_old_original_paid_admission(cold):
    from database.privacy_fence import FenceRefused

    c = cold
    c.handoff.fence.close(owner_key(c.uid), local=True)
    c.handoff.fence.admit_from_authority(
        c.handoff.client, c.uid, c.view.packet['intent']['conversation_ids'], lambda *_: None
    )
    with pytest.raises(FenceRefused):
        c.sink.page(limit=1)
    assert not c.sink.ref(c.rows[0][2], c.rows[0][3]).get().exists


@pytest.mark.parametrize('changed', ['token', 'epoch', 'deletion_intent'])
def test_cold_erasure_rechecks_real_authority_in_writing_transaction(cold, changed):
    from database.legal_holds import LegalHoldAuthorityUnavailable

    c = cold
    c.sink.page(limit=100)
    retained, cid, identity, manifest = terminal(c)
    with unit(c) as authority:
        if changed == 'token':
            from database import legal_holds

            c.handoff.client.document(f'{legal_holds.LEGAL_HOLD_DELETION_GATES_COLLECTION}/{c.uid}').update(
                {'token': 'different'}
            )
        elif changed == 'epoch':
            c.handoff.authority.ref.update({'epoch': 4})
        else:
            c.handoff.client.document(f'users/{c.uid}/deleted_conversations/{cid}').delete()
        with pytest.raises((AuthorityRefused, LegalHoldAuthorityUnavailable)):
            erase_recording(retained, c.uid, identity, manifest, authority, conversation=cid)
    assert not c.sink.barrier(identity).get().exists
    assert any(c.handoff.client.document(path).get().exists for path in manifest['cold_paths'])


def test_actual_cold_write_and_erasure_hold_no_pool_slots_or_owner_guards(cold, monkeypatch):
    c = cold
    real = c.handoff.authority.check
    seen = []

    def check(*a, **k):
        with c.handoff.pool.connection(timeout=2) as one, c.handoff.pool.connection(timeout=2) as two:
            with one.transaction():
                lock(one, owner_key(c.uid), exclusive=True)
                assert two.execute('SELECT 1').fetchone() == (1,)
                seen.append(True)
        return real(*a, **k)

    monkeypatch.setattr(c.handoff.authority, 'check', check)
    c.sink.page(limit=1)
    retained, cid, identity, manifest = terminal(c)
    with unit(c) as authority:
        erase_recording(retained, c.uid, identity, manifest, authority, conversation=cid)
    assert len(seen) >= 3


def test_original_outbox_generation_cannot_be_replaced_in_sql(cold):
    c = cold
    with c.handoff.pool.connection() as conn, pytest.raises(Exception, match='logical generation is immutable'):
        with conn.transaction():
            c.handoff._guard(conn, c.handoff._required_row(conn, c.view.identity))
            conn.execute(
                'UPDATE outbox SET logical_generation=%s WHERE namespace=%s',
                ('restored-admission', c.handoff.ticket.namespace),
            )


def test_unsupported_real_journal_cohort_preserves_checkpoint_and_cold_custodian(cold):
    from database.jobstore.authority import journal

    c = cold
    with c.handoff.pool.connection() as conn, conn.transaction():
        journal(
            conn,
            c.handoff.ticket,
            'budgets',
            {'scope': 'shared', 'period': 'day'},
            owner_key(c.uid),
            {'namespace': c.handoff.ticket.namespace},
        )
    with pytest.raises(AuthorityRefused, match='cohort adapter missing'):
        c.sink.page(limit=100)
    with c.handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT applied_seq FROM queue_authority WHERE namespace=%s', (c.handoff.ticket.namespace,)
        ).fetchone() == (0,)
        assert conn.execute(
            'SELECT count(*) FROM queue_cold_copy_custody WHERE namespace=%s', (c.handoff.ticket.namespace,)
        ).fetchone() == (1,)
    retained, cid, identity, manifest = terminal(c)
    with unit(c) as authority, pytest.raises(AuthorityRefused, match='cohort adapter missing'):
        erase_recording(retained, c.uid, identity, manifest, authority, conversation=cid)
    assert not c.sink.barrier(identity).get().exists


def test_actual_cold_direct_read_counts_fit_existing_dark_planning_bound(cold, monkeypatch):
    from google.cloud.firestore_v1.document import DocumentReference

    c = cold
    reads = []
    real = DocumentReference.get

    def get(ref, *a, **k):
        if ref.path.split('/')[0] == 'jobstore_handoffs':
            reads.append(ref.path)
        return real(ref, *a, **k)

    monkeypatch.setattr(DocumentReference, 'get', get)
    c.sink.page(limit=1)
    assert len(reads) == 5  # authority/barrier twice, destination once
    retained, cid, identity, manifest = terminal(c)
    reads.clear()
    with unit(c) as authority:
        erase_recording(retained, c.uid, identity, manifest, authority, conversation=cid)
    assert len(reads) == 2 + len(manifest['cold_paths']) == 9
