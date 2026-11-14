"""Actual erasure entrypoints, private FS deletes and durable PG custody.

This qualifies redundant private-copy retirement only. Objects, original/cold
metadata, journal finalization and the remote destructive-unit adapter remain
unqualified; neither a callback nor a manifest is an erasure certificate.
"""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from database import legal_holds
from database.jobstore.authority import AuthorityRefused
from database.jobstore.retained_copies import RetainedCopies, RetainedCopiesPending
from database.privacy_fence.protocol import conversation_key, lock, owner_key
from tests.integration.test_jobstore_handoff import context  # noqa: F401
from tests.integration.test_jobstore_provider_projection import lane  # noqa: F401

pytestmark = pytest.mark.integration


@pytest.fixture
def retained(lane):
    view = lane.view
    view.prepare()
    handoff = view.handoff
    uid = view.binding.owner_id
    with handoff.pool.connection() as conn:
        conversation = handoff._required_row(conn, view.identity)['intent']['conversation_ids'][0]
    handoff.client.document(f'users/{uid}/deleted_conversations/{conversation}').set({'id': conversation})
    handoff.fence.close(
        owner_key(uid), conversation=conversation_key(owner_key(uid), conversation), state='deleted', local=True
    )
    from database.batch_pipeline_purge import retained_provider_copies

    return SimpleNamespace(
        view=view, handoff=handoff, uid=uid, conversation=conversation, purge=retained_provider_copies(handoff)
    )


def unit(retained):
    return legal_holds.bounded_destructive_unit(
        retained.uid, kind='conversation_batch_purge', firestore_client=retained.handoff.client
    )


def private_left(retained):
    manifest = retained.purge.inventory(retained.uid, retained.conversation)[0][1]
    return sum(retained.handoff.client.document(path).get().exists for path in manifest['private_paths'])


def test_actual_conversation_purge_retires_private_views_and_keeps_originals(retained):
    from database.batch_pipeline_conversation_purge import purge_conversation

    r = retained
    assert private_left(r) == 5
    progress = SimpleNamespace(position={}, expired=lambda: False, unit=lambda: unit(r))
    with pytest.raises(RetainedCopiesPending, match='certification remains'):
        purge_conversation(r.uid, r.conversation, progress, firestore_client=r.handoff.client, retained_copies=r.purge)
    assert private_left(r) == 0
    # No legacy pass/ledger removal or completion marker is allowed yet.
    assert r.handoff.ref('intent', r.view.identity).get().exists
    assert r.handoff.ref('completion', r.view.identity).get().exists
    assert r.view.ref('intakes', r.view.identity).get().exists
    with r.handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT phase FROM queue_retained_copy_custody WHERE namespace=%s', (r.handoff.ticket.namespace,)
        ).fetchone() == ('private_erased',)
        assert conn.execute(
            'SELECT count(*) FROM units WHERE namespace=%s', (r.handoff.ticket.namespace,)
        ).fetchone() == (2,)
    # Published views cannot be reconstructed after partial or complete deletion.
    with pytest.raises(Exception):
        r.view.prepare()


def test_actual_account_purge_keeps_purging_until_all_original_copies_resolve(retained):
    from database.batch_pipeline_purge import purge_batch_owner

    r = retained
    r.handoff.fence.close(owner_key(r.uid), reason='deleted', local=True)
    with r.handoff.pool.connection() as conn, conn.transaction():
        lock(conn, owner_key(r.uid), exclusive=True)
        conn.execute(
            "UPDATE privacy_owner_fence SET state='purging',close_reason='deleted',purge_generation=generation WHERE owner_key=%s",
            (owner_key(r.uid),),
        )
    with unit(r) as authority:
        with pytest.raises(RetainedCopiesPending):
            purge_batch_owner(
                r.uid,
                firestore_client=r.handoff.client,
                namespaces=(r.handoff.ticket.namespace,),
                retained_copies=r.purge,
                destructive_authority=authority,
            )
    value = r.handoff.client.collection('batch_pipeline_privacy').document(owner_key(r.uid)).get().to_dict()
    assert value['purging'] and value['blocked']
    assert private_left(r) == 0


def test_legal_hold_and_changed_unit_token_cannot_erase_or_close_p(retained):
    r = retained
    manifest = r.purge.inventory(r.uid, r.conversation)[0][1]
    with unit(r) as authority:
        gate = r.handoff.client.collection(legal_holds.LEGAL_HOLD_DELETION_GATES_COLLECTION).document(r.uid)
        gate.update({'token': 'successor'})
        with pytest.raises(legal_holds.LegalHoldAuthorityUnavailable):
            r.purge.retire_private(r.uid, r.view.identity, manifest, authority, conversation=r.conversation)
    assert private_left(r) == 5
    # A valid hold blocks the actual erasing transaction even if an old unit
    # object survives takeover. It does not manufacture a PG close.
    with r.handoff.pool.connection() as conn:
        before = conn.execute(
            'SELECT generation,change_seq,state FROM privacy_owner_fence WHERE owner_key=%s', (owner_key(r.uid),)
        ).fetchone()
    r.handoff.client.collection(legal_holds.LEGAL_HOLDS_COLLECTION).document(r.uid).set(
        {
            'schema_version': legal_holds.LEGAL_HOLD_SCHEMA_VERSION,
            'issuer': 'admin',
            'active': True,
        }
    )
    with pytest.raises(legal_holds.LegalHoldActive):
        with unit(r):
            pytest.fail('held account acquired erasure authority')
    with r.handoff.pool.connection() as conn:
        assert (
            conn.execute(
                'SELECT generation,change_seq,state FROM privacy_owner_fence WHERE owner_key=%s', (owner_key(r.uid),)
            ).fetchone()
            == before
        )


def test_mode_selector_is_not_consulted_and_original_deadlines_are_exact(retained, monkeypatch):
    r = retained
    monkeypatch.setenv('BATCH_PIPELINE_JOBSTORE_SHADOW_MODE', 'off')
    records = r.purge.inventory(r.uid, r.conversation)
    assert records[0][1]['original_deadlines'] == {'one': 20000, 'two': 20000}
    assert 'expires_at' not in records[0][1]
    with r.handoff.pool.connection() as conn, conn.transaction():
        lock(conn, owner_key(r.uid), exclusive=True)
        # No PG_OPEN-only mutation path: a closing namespace still has copies.
        from database.jobstore.authority import transition

        newer = transition(conn, r.handoff.ticket.namespace, 'PG_OPEN', 3, 'PG_CLOSING')
    r.handoff.ticket = newer
    from database.jobstore.fs_fence import FirestoreAuthority

    r.handoff.authority = FirestoreAuthority(r.handoff.client, newer)
    r.handoff.authority.ref.set(
        {'namespace': newer.namespace, 'epoch': newer.value, 'state': 'PG_CLOSING', 'protocol': 1}
    )
    with unit(r) as authority:
        r.purge.retire_private(r.uid, r.view.identity, records[0][1], authority, conversation=r.conversation)
    assert private_left(r) == 0


@pytest.mark.parametrize('table', ['queue_handoffs', 'units', 'recordings', 'queue_custody', 'queue_journal', 'outbox'])
def test_sql_cannot_drop_original_custodian_before_remote_outcomes_resolve(retained, table):
    r = retained
    r.purge.inventory(r.uid, r.conversation)
    with r.handoff.pool.connection() as conn:
        with pytest.raises(Exception, match='original PG custody'):
            with conn.transaction():
                lock(conn, owner_key(r.uid), exclusive=True)
                conn.execute("SELECT set_config('omi.queue_epoch','3',true)")
                conn.execute(f'DELETE FROM {table} WHERE namespace=%s', (r.handoff.ticket.namespace,))


def test_unknown_fs_commit_then_takeover_replays_without_losing_pg_custody(retained, monkeypatch):
    r = retained
    manifest = r.purge.inventory(r.uid, r.conversation)[0][1]
    api = r.handoff.client._firestore_api
    real = api.commit
    lost = [False]

    def commit(*a, **k):
        result = real(*a, **k)
        from google.cloud.firestore_v1.types import CommitRequest

        request = CommitRequest(k.get('request') or (a[0] if a else None))
        if not lost[0] and any(w.delete and 'jobstore_handoffs' in w.delete for w in request.writes):
            lost[0] = True
            raise ConnectionError('private delete committed, response lost')
        return result

    with unit(r) as authority:
        monkeypatch.setattr(api, 'commit', commit)
        with pytest.raises(ConnectionError):
            r.purge.retire_private(r.uid, r.view.identity, manifest, authority, conversation=r.conversation)
    monkeypatch.setattr(api, 'commit', real)
    with r.handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT phase FROM queue_retained_copy_custody WHERE namespace=%s', (r.handoff.ticket.namespace,)
        ).fetchone() == ('inventoried',)
    with unit(r) as successor:
        r.purge.retire_private(r.uid, r.view.identity, manifest, successor, conversation=r.conversation)
    assert private_left(r) == 0
    assert r.handoff.ref('intent', r.view.identity).get().exists


def test_missing_terminal_pc_refuses_before_any_private_delete(lane):
    lane.view.prepare()
    with pytest.raises(AuthorityRefused, match='terminal deleted PC'):
        RetainedCopies(lane.view.handoff).inventory(lane.view.binding.owner_id, 'unclosed')


@pytest.mark.parametrize('gap', ['before_private', 'after_private', 'before_ack', 'after_ack'])
def test_abrupt_process_exit_uses_original_census_after_real_gate_takeover(retained, gap):
    import os
    import subprocess
    import sys
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4

    r = retained
    manifest = r.purge.inventory(r.uid, r.conversation)[0][1]
    token = uuid4().hex
    # Age only the synthetic gate. Real takeover uses the existing production
    # expiry rule; expiry itself never grants the old worker a new token.
    now = datetime.now(timezone.utc)
    legal_holds.acquire_destructive_operation(
        r.uid,
        kind='conversation_batch_purge',
        token=token,
        firestore_client=r.handoff.client,
        now=now - timedelta(seconds=2 * legal_holds.UNIT_EXPIRY_SECONDS),
        expires_at=now - timedelta(seconds=legal_holds.UNIT_EXPIRY_SECONDS),
    )
    with r.handoff.pool.connection() as conn:
        dsn = conn.info.dsn
    command = '''
import os
import testing.pipeline_sim._env
from google.cloud.firestore_v1.types import CommitRequest
from database import legal_holds
from database.jobstore.connection import Pool
from database.jobstore.handoff import Handoff
from database.jobstore.authority import Epoch
from database.jobstore.retained_copies import RetainedCopies
from database.privacy_fence import Fence
from testing.store_fixtures import _emulator_client
pool=Pool(os.environ['OMI_PURGE_CHILD_DSN'],size=2)
if os.environ['OMI_PURGE_CHILD_GAP']=='before_ack':
    original=pool._connect
    class ExitBeforeCommit:
        def __init__(self,conn):self.conn=conn
        def __getattr__(self,name):return getattr(self.conn,name)
        def execute(self,query,*a,**k):
            result=self.conn.execute(query,*a,**k)
            if 'UPDATE queue_retained_copy_custody SET phase=' in query:os._exit(86)
            return result
    pool._connect=lambda:ExitBeforeCommit(original())
client=_emulator_client()
handoff=Handoff(pool,Fence(pool),client,Epoch(os.environ['OMI_PURGE_CHILD_NS'],3))
purge=__import__('database.batch_pipeline_purge', fromlist=['retained_provider_copies']).retained_provider_copies(handoff)
uid,cid=os.environ['OMI_PURGE_CHILD_UID'],os.environ['OMI_PURGE_CHILD_CID']
identity,manifest=purge.inventory(uid,cid)[0]
authority=legal_holds.UnitAuthority(uid,'conversation_batch_purge',os.environ['OMI_PURGE_CHILD_TOKEN'],client,None)
api=client._firestore_api
real=api.commit
def commit(*a,**k):
    request=CommitRequest(k.get('request') or a[0])
    deleting=any(w.delete and 'jobstore_handoffs' in w.delete for w in request.writes)
    if deleting and os.environ['OMI_PURGE_CHILD_GAP']=='before_private':os._exit(86)
    result=real(*a,**k)
    if deleting and os.environ['OMI_PURGE_CHILD_GAP']=='after_private':os._exit(86)
    return result
api.commit=commit
purge.retire_private(uid,identity,manifest,authority,conversation=cid)
os._exit(86)
'''
    result = subprocess.run(
        [sys.executable, '-c', command],
        capture_output=True,
        text=True,
        timeout=30,
        env={
            **os.environ,
            'OMI_PURGE_CHILD_DSN': dsn,
            'OMI_PURGE_CHILD_NS': r.handoff.ticket.namespace,
            'OMI_PURGE_CHILD_UID': r.uid,
            'OMI_PURGE_CHILD_CID': r.conversation,
            'OMI_PURGE_CHILD_TOKEN': token,
            'OMI_PURGE_CHILD_GAP': gap,
        },
    )
    assert result.returncode == 86, result.stderr
    with r.handoff.pool.connection() as conn:
        phase = conn.execute(
            'SELECT phase FROM queue_retained_copy_custody WHERE namespace=%s', (r.handoff.ticket.namespace,)
        ).fetchone()[0]
    assert phase == ('private_erased' if gap == 'after_ack' else 'inventoried')
    assert private_left(r) == (5 if gap == 'before_private' else 0)
    # Abrupt death can leave server-side read locks until the FS transaction
    # lease expires. Redeliver at most twelve times under the unchanged unit and
    # SDK policies; do not turn a timer into deletion authority.
    from google.api_core.exceptions import Aborted

    for delivery in range(12):
        try:
            with unit(r) as successor:
                assert successor.token != token
                r.purge.retire_private(r.uid, r.view.identity, manifest, successor, conversation=r.conversation)
            break
        except ValueError as error:
            assert gap == 'before_private' and isinstance(error.__cause__, Aborted)
            assert r.handoff.ref('intent', r.view.identity).get().exists
    else:
        pytest.fail('abandoned FS read lease outlived twelve bounded erasure deliveries')
    assert private_left(r) == 0
    assert r.handoff.ref('intent', r.view.identity).get().exists
    assert r.handoff.ref('completion', r.view.identity).get().exists


def test_no_pg_slots_or_owner_guards_span_real_private_fs_commit(retained, monkeypatch):
    from google.cloud.firestore_v1.types import CommitRequest

    r = retained
    manifest = r.purge.inventory(r.uid, r.conversation)[0][1]
    api = r.handoff.client._firestore_api
    real = api.commit
    inspected = []

    def commit(*a, **k):
        request = CommitRequest(k.get('request') or a[0])
        if any(w.delete and 'jobstore_handoffs' in w.delete for w in request.writes):
            with r.handoff.pool.connection(timeout=2) as one, r.handoff.pool.connection(timeout=2) as two:
                with one.transaction():
                    lock(one, owner_key(r.uid), exclusive=True)
                    assert two.execute('SELECT 1').fetchone() == (1,)
            inspected.append(True)
        return real(*a, **k)

    with unit(r) as authority:
        monkeypatch.setattr(api, 'commit', commit)
        r.purge.retire_private(r.uid, r.view.identity, manifest, authority, conversation=r.conversation)
    assert inspected


def test_census_cannot_change_lifetime_or_disappear(retained):
    r = retained
    r.purge.inventory(r.uid, r.conversation)
    with r.handoff.pool.connection() as conn:
        for query in (
            "UPDATE queue_retained_copy_custody SET manifest=manifest || '{\"expires_at\":9999999999}'::jsonb WHERE namespace=%s",
            'DELETE FROM queue_retained_copy_custody WHERE namespace=%s',
        ):
            with pytest.raises(Exception, match='immutable|no final erasure certificate'):
                with conn.transaction():
                    lock(conn, owner_key(r.uid), exclusive=True)
                    conn.execute(query, (r.handoff.ticket.namespace,))


def test_stale_queue_epoch_refuses_before_remote_delete(retained):
    r = retained
    with r.handoff.pool.connection() as conn, conn.transaction():
        from database.jobstore.authority import transition

        transition(conn, r.handoff.ticket.namespace, 'PG_OPEN', 3, 'PG_CLOSING')
    with pytest.raises(AuthorityRefused, match='current PG queue epoch'):
        r.purge.inventory(r.uid, r.conversation)
    assert all(
        r.handoff.client.document(r.view.ref(table, sid).path).get().exists
        for sid in r.view.binding.segment_ids
        for table in ('jobs', 'results')
    )


def test_account_binding_refuses_before_f_advance_without_purging_p(retained, monkeypatch):
    from database.batch_pipeline_purge import purge_batch_owner

    r = retained
    privacy = r.handoff.client.collection('batch_pipeline_privacy').document(owner_key(r.uid))
    before = privacy.get().to_dict()
    from database import batch_pipeline_purge

    advanced = []
    original = batch_pipeline_purge.advance_privacy_generation

    def observe(*a, **k):
        advanced.append(True)
        return original(*a, **k)

    monkeypatch.setattr(batch_pipeline_purge, 'advance_privacy_generation', observe)
    with unit(r) as authority:
        with pytest.raises(AuthorityRefused, match='purging or erased P'):
            purge_batch_owner(
                r.uid,
                firestore_client=r.handoff.client,
                namespaces=(r.handoff.ticket.namespace,),
                retained_copies=r.purge,
                destructive_authority=authority,
            )
    after = privacy.get().to_dict()
    assert not advanced
    # Gate acquisition/release can benignly rotate memo_token. P/F purge state
    # must not change, and the actual generation-advance function never ran.
    assert {key: after.get(key) for key in ('generation', 'blocked', 'purging')} == {
        key: before.get(key) for key in ('generation', 'blocked', 'purging')
    }
    assert private_left(r) == 5


def test_real_redirect_admission_target_is_in_conversation_erasure_census(context, monkeypatch):
    from database.batch_pipeline_conversation_purge import purge_conversation
    from database.batch_pipeline_purge import retained_provider_copies
    from database.jobstore.provider_projection import ProviderProjection
    from testing.store_fixtures import ClientCustomerData
    from tests.integration.test_jobstore_provider_handoff import upload, terminal

    handoff, uid = context
    target = 'redirect-target'
    ClientCustomerData(handoff.client).add_conversation(uid, target)
    handoff.client.document(f'users/{uid}/conversations/c').update({'deleted': True, 'sync_merged_into': target})
    provider, binding, _, _ = upload(context, monkeypatch, count=1)
    admission = provider.deliver(binding.job_id)
    target_key = conversation_key(owner_key(uid), target)
    assert target_key in {t['conversation_key'] for t in admission['privacy_targets']}
    with handoff.pool.connection() as conn:
        assert target not in handoff._required_row(conn, binding.job_id)['intent']['conversation_ids']
    (claimed,) = provider.units.claim(1, now=201, lease_seconds=30, backlog_share=0)
    assert terminal(provider, claimed)
    view = ProviderProjection(handoff, binding.job_id)
    view.prepare()
    handoff.client.document(f'users/{uid}/deleted_conversations/{target}').set({'id': target})
    handoff.fence.close(owner_key(uid), conversation=target_key, state='deleted', local=True)
    copies = retained_provider_copies(handoff)
    manifest = copies.inventory(uid, target)[0][1]
    assert len(manifest['private_paths']) == 3

    @contextmanager
    def destructive_unit():
        with legal_holds.bounded_destructive_unit(
            uid, kind='conversation_batch_purge', firestore_client=handoff.client
        ) as authority:
            yield authority

    progress = SimpleNamespace(position={}, expired=lambda: False, unit=destructive_unit)
    with pytest.raises(RetainedCopiesPending):
        purge_conversation(uid, target, progress, firestore_client=handoff.client, retained_copies=copies)
    assert not any(handoff.client.document(path).get().exists for path in manifest['private_paths'])
    assert handoff.ref('intent', binding.job_id).get().exists
