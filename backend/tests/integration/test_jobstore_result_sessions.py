"""Actual ArtifactStore/FS/PG with disk-backed resumable transport, not remote C4."""

import pytest

from database import legal_holds
from database.batch_pipeline_purge import provider_result_artifacts
from database.conversation_batch_purge_jobs import GATE_KIND
from database.jobstore.authority import AuthorityRefused, journal
from database.jobstore.gcs_sink import GCSSink
from database.privacy_fence.protocol import lock
from tests.integration.test_jobstore_handoff import context  # noqa: F401
from tests.integration.test_jobstore_provider_effect import paid  # noqa: F401
from utils.batch_pipeline.contracts import WorkResult
from utils.batch_pipeline.upload_policy import UPLOAD_TIMEOUT
from utils.other.local_storage import LocalStorageClient

pytestmark = pytest.mark.integration


@pytest.fixture
def result(paid, tmp_path, monkeypatch):
    adapter, unit, ticket, item = paid
    ticket.start(item, 'modulate')
    storage = LocalStorageClient(tmp_path)
    monkeypatch.setenv('BUCKET_BATCH_PIPELINE', 'synthetic')
    artifacts = provider_result_artifacts(ticket, storage, 'synthetic', b'x' * 32, lease_seconds=60)
    return adapter, unit, ticket, item, storage, artifacts


def row(result):
    adapter = result[0]
    with adapter.units.pool.connection() as conn:
        from database.privacy_fence.protocol import row_dict

        return row_dict(conn, 'SELECT * FROM queue_provider_uploads WHERE namespace=%s', (adapter.units.namespace,))


def effect(result):
    adapter = result[0]
    with adapter.units.pool.connection() as conn:
        from database.privacy_fence.protocol import row_dict

        return row_dict(
            conn, "SELECT * FROM privacy_effect_inflight WHERE owner_key=%s AND kind='gcs_put'", (result[2].owner,)
        )


def drain(result):
    adapter, _, ticket, item, storage, _ = result
    sink = GCSSink(adapter.handoff, storage, timeout=UPLOAD_TIMEOUT)
    with legal_holds.bounded_destructive_unit(
        item.owner_id, kind=GATE_KIND, firestore_client=adapter.handoff.client
    ) as authority:
        sink.authority = authority
        sink.finish(effect(result)['sink'])


def test_actual_result_publication_and_paid_terminal_join(result):
    adapter, _, ticket, item, storage, artifacts = result
    sends = []

    def before(method, session, body, headers):
        assert method == 'PUT' and body
        assert effect(result)['state'] == 'started'
        with adapter.units.pool.connection() as one, adapter.units.pool.connection() as two:
            with one.transaction():
                one.execute("SET LOCAL lock_timeout='2s'")
                lock(one, ticket.owner, exclusive=True)
            assert two.execute('SELECT 1').fetchone() == (1,)
        sends.append(session)

    storage._http.before_request = before
    payload = {'words': [{'text': 'hello'}], 'duration': 1}
    uri = artifacts.persist_result(item, payload)
    assert len(sends) == 1
    assert artifacts.load_result(item, uri) == payload
    assert artifacts.persist_result(item, payload) == uri
    assert len(sends) == 1
    assert row(result)['phase'] == 'published' and effect(result) is None
    assert row(result)['original_deadline'] == result[1]['custody_deadline']
    with pytest.raises(Exception, match='original published object'):
        ticket.complete(WorkResult(item.segment_id, 'encrypted://wrong').to_dict(), now=202, partial_wait=30)
    assert ticket.complete(WorkResult(item.segment_id, uri).to_dict(), now=202, partial_wait=30)
    assert not list(adapter.handoff.client.collection(adapter.units.namespace + '_jobs').stream())


def test_changed_payload_and_recovery_cohort_refuse(result):
    _, _, _, item, _, artifacts = result
    artifacts.persist_result(item, {'words': []})
    with pytest.raises(AuthorityRefused, match='payload'):
        artifacts.persist_result(item, {'words': ['changed']})
    with pytest.raises(AuthorityRefused, match='cohort'):
        artifacts.persist_recovery_result(item, {}, 'a' * 32)


def test_lost_finalize_reply_retains_original_session_and_drains(result):
    _, _, _, item, storage, artifacts = result

    def lost(*args):
        raise ConnectionError('lost original reply')

    storage._http.after_request = lost
    with pytest.raises(ConnectionError):
        artifacts.persist_result(item, {'words': []})
    assert row(result)['phase'] == 'registered' and effect(result)['state'] == 'started'
    storage._http.after_request = None
    result[0].units.fence.close(result[2].owner, local=True)
    drain(result)
    assert row(result)['phase'] == 'fenced' and effect(result) is None
    assert not list(storage.bucket('synthetic').list_blobs())


def test_close_after_put_retains_custody_until_real_unit_drains(result):
    adapter, _, ticket, item, storage, artifacts = result
    storage._http.after_request = lambda *a: adapter.units.fence.close(ticket.owner, local=True)
    with pytest.raises(Exception):
        artifacts.persist_result(item, {'words': []})
    storage._http.after_request = None
    assert effect(result) is not None
    drain(result)
    assert row(result)['phase'] == 'fenced' and effect(result) is None


def test_generic_callback_cannot_retire_original_result_registry(result):
    adapter, _, ticket, item, storage, artifacts = result
    storage._http.after_request = lambda *a: (_ for _ in ()).throw(ConnectionError('lost'))
    with pytest.raises(ConnectionError):
        artifacts.persist_result(item, {})
    adapter.units.fence.close(ticket.owner, local=True)
    with pytest.raises(Exception, match='share COMMIT'):
        adapter.units.fence.drain_pass(ticket.owner, fence_gcs=lambda _: True)
    assert effect(result) is not None


def test_original_result_identity_and_last_custodian_cannot_be_scrubbed(result):
    adapter, _, ticket, item, _, artifacts = result
    artifacts.persist_result(item, {})
    for statement in [
        'DELETE FROM queue_provider_uploads WHERE namespace=%s',
        "UPDATE queue_provider_uploads SET content_hash='changed' WHERE namespace=%s",
        'UPDATE queue_provider_uploads SET generation=generation+1 WHERE namespace=%s',
    ]:
        with pytest.raises(Exception):
            with adapter.units.pool.connection() as conn, conn.transaction():
                adapter.units._guarded_unit(conn, item.segment_id)
                conn.execute(statement, (adapter.units.namespace,))
    assert row(result)['phase'] == 'published'


def test_expired_open_owner_drain_claim_blocks_late_complete(result):
    adapter, _, ticket, item, storage, artifacts = result

    def after(*args):
        with adapter.units.pool.connection() as conn, conn.transaction():
            lock(conn, ticket.owner, exclusive=True)
            conn.execute(
                "UPDATE privacy_effect_inflight SET lease_until=now()-interval '1 second' WHERE kind='gcs_put' AND owner_key=%s",
                (ticket.owner,),
            )
        storage._http.after_request = None
        drain(result)

    storage._http.after_request = after
    with pytest.raises(AuthorityRefused, match='drain claim'):
        artifacts.persist_result(item, {})
    assert row(result)['phase'] == 'fenced' and effect(result) is None


def test_published_completion_wins_before_janitor_and_is_not_deleted(result):
    adapter, _, _, item, storage, artifacts = result
    observed = []
    storage._http.before_request = lambda *args: observed.append(effect(result)['sink'])
    uri = artifacts.persist_result(item, {})
    storage._http.before_request = lambda *args: pytest.fail('published object was touched by drain')
    assert GCSSink(adapter.handoff, storage, timeout=UPLOAD_TIMEOUT)(observed[0]) is None
    assert artifacts.load_result(item, uri) == {}


def test_legal_hold_preserves_result_custody_without_closing_p(result):
    adapter, _, ticket, item, storage, artifacts = result
    storage._http.after_request = lambda *a: (_ for _ in ()).throw(ConnectionError('lost'))
    with pytest.raises(ConnectionError):
        artifacts.persist_result(item, {})
    storage._http.after_request = None
    with adapter.units.pool.connection() as conn:
        before = conn.execute(
            'SELECT generation,change_seq,state FROM privacy_owner_fence WHERE owner_key=%s', (ticket.owner,)
        ).fetchone()
    adapter.handoff.client.collection(legal_holds.LEGAL_HOLDS_COLLECTION).document(item.owner_id).set(
        {'schema_version': legal_holds.LEGAL_HOLD_SCHEMA_VERSION, 'issuer': 'admin', 'active': True}
    )
    with pytest.raises(legal_holds.LegalHoldActive):
        drain(result)
    assert effect(result) is not None and row(result)['phase'] == 'registered'
    with adapter.units.pool.connection() as conn:
        assert (
            conn.execute(
                'SELECT generation,change_seq,state FROM privacy_owner_fence WHERE owner_key=%s', (ticket.owner,)
            ).fetchone()
            == before
        )


def test_unknown_terminal_status_pins_gate_and_actual_recovery_finishes(result):
    adapter, _, ticket, item, storage, artifacts = result
    storage._http.after_request = lambda *a: (_ for _ in ()).throw(ConnectionError('lost'))
    with pytest.raises(ConnectionError):
        artifacts.persist_result(item, {})
    storage._http.after_request = None
    adapter.units.fence.close(ticket.owner, local=True)
    from database.jobstore.gcs_sink import PREFIX

    target = PREFIX + adapter.units.namespace + ':' + str(effect(result)['effect_id'])
    sink = GCSSink(adapter.handoff, storage, timeout=UPLOAD_TIMEOUT)
    original = sink.transport.fence
    sink.transport.fence = lambda *a, **k: (_ for _ in ()).throw(ConnectionError('terminal unknown'))
    with pytest.raises(ConnectionError):
        with legal_holds.bounded_destructive_unit(
            item.owner_id, kind=GATE_KIND, firestore_client=adapter.handoff.client
        ) as authority:
            sink.authority = authority
            sink.finish(effect(result)['sink'])
    gate = adapter.handoff.client.collection(legal_holds.LEGAL_HOLD_DELETION_GATES_COLLECTION).document(item.owner_id)
    assert gate.get().to_dict()['remote_target'] == target
    assert gate.get().to_dict()['remote_inflight']
    sink.transport.fence = original
    assert sink.recover(item.owner_id, target)
    assert row(result)['phase'] == 'fenced' and effect(result) is None
    # Recovery proves the outcome; only the existing observed-target CAS may clear the gate.
    assert gate.get().to_dict()['remote_inflight']
    with pytest.raises(ConnectionError, match='foreign'):
        sink.recover(item.owner_id, 'jobstore-gcs-v1:foreign:missing')


@pytest.mark.parametrize('status', [200, 400, 401, 403, 404, 410, 500])
def test_missing_generation_or_nonterminal_status_never_retires_registry(result, status):
    import json

    adapter, _, ticket, item, storage, artifacts = result
    storage._http.after_request = lambda *a: (_ for _ in ()).throw(ConnectionError('lost'))
    with pytest.raises(ConnectionError):
        artifacts.persist_result(item, {})
    storage._http.after_request = None
    source = effect(result)['sink']
    session = storage.root / '.sessions' / source['session'].removeprefix('local-session://')
    # A sticky remote error, or finalize without original version metadata,
    # cannot be promoted to an absence certificate by the real adapter.
    session.write_text(json.dumps({'http_status': status}))
    adapter.units.fence.close(ticket.owner, local=True)
    with pytest.raises(ConnectionError):
        drain(result)
    assert effect(result) is not None and row(result)['phase'] == 'draining'


def test_cancelled_empty_session_refuses_a_paused_late_put(result):
    adapter, _, ticket, item, storage, artifacts = result
    saved = []

    def pause(*args):
        saved.append(args)
        raise ConnectionError('dispatch reply unknown')

    storage._http.before_request = pause
    with pytest.raises(ConnectionError):
        artifacts.persist_result(item, {})
    storage._http.before_request = None
    adapter.units.fence.close(ticket.owner, local=True)
    drain(result)
    method, session, body, headers = saved[0]
    assert storage._http.request(method, session, data=body, headers=headers).status_code == 499
    assert not list(storage.bucket('synthetic').list_blobs())


def test_create_only_collision_is_not_adopted_or_deleted(result):
    adapter, _, ticket, item, storage, artifacts = result

    def collide(method, session, body, headers):
        source = effect(result)['sink']
        storage.bucket(source['bucket']).blob(source['key']).upload_from_string(b'foreign', if_generation_match=0)
        storage._http.before_request = None

    storage._http.before_request = collide
    with pytest.raises(ConnectionError, match='finalize'):
        artifacts.persist_result(item, {})
    source = effect(result)['sink']
    foreign = storage.bucket(source['bucket']).blob(source['key'])
    assert foreign.download_as_bytes() == b'foreign'
    adapter.units.fence.close(ticket.owner, local=True)
    drain(result)
    assert foreign.download_as_bytes() == b'foreign'
    assert row(result)['generation'] is None and row(result)['phase'] == 'fenced'


@pytest.mark.parametrize(
    'gap',
    [
        'before_register',
        'after_register',
        'before_start',
        'after_start',
        'after_put',
        'before_publish',
        'after_publish',
    ],
)
def test_actual_result_session_process_exit(result, gap):
    import os
    import subprocess
    import sys

    adapter, unit, ticket, item, storage, artifacts = result
    with adapter.units.pool.connection() as conn:
        dsn = conn.info.dsn
    code = '''
import os
from pathlib import Path
import testing.pipeline_sim._env
from database.batch_pipeline_purge import provider_result_artifacts
from database.jobstore.authority import Epoch
from database.jobstore.connection import Pool
from database.jobstore.handoff import Handoff
from database.jobstore.provider_handoff import ProviderHandoff
from database.jobstore.provider_effect import FenceTicket
from database.privacy_fence import Fence
from testing.store_fixtures import _emulator_client
from utils.batch_pipeline.contracts import WorkItem
from utils.other.local_storage import LocalStorageClient
pool=Pool(os.environ['SESSION_DSN'],size=2)
h=Handoff(pool,Fence(pool),_emulator_client(),Epoch(os.environ['SESSION_NS'],3))
ticket=FenceTicket(ProviderHandoff(h).units,os.environ['SESSION_UNIT'],os.environ['SESSION_ATTEMPT'],lease_seconds=60)
item=WorkItem(**{k:ticket.source[k] for k in WorkItem.__dataclass_fields__ if k in ticket.source})
storage=LocalStorageClient(Path(os.environ['SESSION_ROOT']))
artifacts=provider_result_artifacts(ticket,storage,'synthetic',b'x'*32,lease_seconds=60)
rows=artifacts.session_upload.rows
gap=os.environ['SESSION_GAP']
method=gap.removeprefix('before_').removeprefix('after_')
if method in ('register','start','publish'):
    original=getattr(rows,method)
    if gap.startswith('before_'):
        # Kill inside the actual SQL transaction after its mutation, before COMMIT.
        if method=='register':
            real=rows.units.fence.register
            def killed(*a,**k):
                real(*a,**k)
                os._exit(86)
            rows.units.fence.register=killed
        elif method=='start':
            real=rows.units.fence.start
            def killed(*a,**k):
                real(*a,**k)
                os._exit(86)
            rows.units.fence.start=killed
        else:
            real=rows.units.fence.complete
            def killed(*a,**k):
                real(*a,**k)
                os._exit(86)
            rows.units.fence.complete=killed
    else:
        def killed(*a,**k):
            original(*a,**k)
            os._exit(86)
        setattr(rows,method,killed)
else:
    storage._http.after_request=lambda *a:os._exit(86)
artifacts.persist_result(item,{'words':[]})
os._exit(87)
'''
    child = subprocess.run(
        [sys.executable, '-c', code],
        env={
            **os.environ,
            'SESSION_DSN': dsn,
            'SESSION_NS': adapter.units.namespace,
            'SESSION_UNIT': unit['unit_id'],
            'SESSION_ATTEMPT': unit['attempt_token'],
            'SESSION_ROOT': str(storage.root),
            'SESSION_GAP': gap,
        },
        capture_output=True,
        timeout=45,
    )
    assert child.returncode == 86, child.stderr.decode()
    original = row(result)
    if gap == 'before_register':
        assert original['phase'] == 'prepared' and effect(result) is None
    elif gap == 'after_publish':
        assert original['phase'] == 'published' and effect(result) is None
        assert artifacts.persist_result(item, {'words': []}).endswith('#' + str(original['generation']))
    else:
        assert original['phase'] == 'registered' and effect(result) is not None
        adapter.units.fence.close(ticket.owner, local=True)
        drain(result)
        assert row(result)['phase'] == 'fenced' and effect(result) is None
    # Prepared/unknown outcomes never mint a replacement session or discard custody.
    if gap != 'after_publish':
        with pytest.raises(Exception):
            artifacts.persist_result(item, {'words': []})
    assert list(adapter.handoff.client.collection(adapter.units.namespace + '_artifacts').stream())


@pytest.mark.parametrize('gap', ['before_retirement', 'after_retirement'])
def test_real_terminal_proof_and_pg_retirement_process_exit(result, gap):
    import os
    import subprocess
    import sys

    adapter, _, ticket, item, storage, artifacts = result
    storage._http.after_request = lambda *a: (_ for _ in ()).throw(ConnectionError('lost'))
    with pytest.raises(ConnectionError):
        artifacts.persist_result(item, {})
    storage._http.after_request = None
    adapter.units.fence.close(ticket.owner, local=True)
    original_sink = effect(result)['sink']
    with adapter.units.pool.connection() as conn:
        dsn = conn.info.dsn
    code = '''
import os,json
from pathlib import Path
import testing.pipeline_sim._env
from database import legal_holds
from database.jobstore.authority import Epoch
from database.jobstore.connection import Pool
from database.jobstore.handoff import Handoff
from database.jobstore.gcs_sink import GCSSink
from database.privacy_fence import Fence
from testing.store_fixtures import _emulator_client
from utils.batch_pipeline.upload_policy import UPLOAD_TIMEOUT
from utils.other.local_storage import LocalStorageClient
pool=Pool(os.environ['SESSION_DSN'],size=2)
h=Handoff(pool,Fence(pool),_emulator_client(),Epoch(os.environ['SESSION_NS'],3))
authority=legal_holds.UnitAuthority(os.environ['SESSION_UID'],os.environ['SESSION_KIND'],os.environ['SESSION_TOKEN'],h.client,None)
sink=GCSSink(h,LocalStorageClient(Path(os.environ['SESSION_ROOT'])),timeout=UPLOAD_TIMEOUT,authority=authority)
if os.environ['SESSION_GAP']=='before_retirement':
    real=h.fence._retire
    def killed(*a,**k):
        real(*a,**k)
        os._exit(86)
    h.fence._retire=killed
sink.finish(json.loads(os.environ['SESSION_SINK']))
os._exit(86)
'''
    import json

    with legal_holds.bounded_destructive_unit(
        item.owner_id, kind=GATE_KIND, firestore_client=adapter.handoff.client
    ) as authority:
        child = subprocess.run(
            [sys.executable, '-c', code],
            env={
                **os.environ,
                'SESSION_DSN': dsn,
                'SESSION_NS': adapter.units.namespace,
                'SESSION_ROOT': str(storage.root),
                'SESSION_GAP': gap,
                'SESSION_UID': item.owner_id,
                'SESSION_KIND': authority.kind,
                'SESSION_TOKEN': authority.token,
                'SESSION_SINK': json.dumps(original_sink),
            },
            capture_output=True,
            timeout=45,
        )
        assert child.returncode == 86, child.stderr.decode()
        if gap == 'before_retirement':
            assert row(result)['phase'] == 'draining' and effect(result) is not None
            GCSSink(adapter.handoff, storage, timeout=UPLOAD_TIMEOUT, authority=authority).finish(original_sink)
        assert row(result)['phase'] == 'fenced' and effect(result) is None
        assert not list(storage.bucket('synthetic').list_blobs())


def test_reference_read_budget_and_original_deadline(result, monkeypatch):
    from google.cloud.firestore_v1.document import DocumentReference

    adapter, _, _, item, _, artifacts = result
    actual = DocumentReference.get
    reads = []

    def get(ref, *a, **k):
        if ref.path.startswith(adapter.units.namespace + '_artifacts/'):
            reads.append(k.get('transaction'))
        return actual(ref, *a, **k)

    monkeypatch.setattr(DocumentReference, 'get', get)
    artifacts.persist_result(item, {})
    assert len(reads) == 1 and reads[0] is not None
    (reference,) = list(adapter.handoff.client.collection(adapter.units.namespace + '_artifacts').stream())
    payload = reference.to_dict()
    assert payload['provider_upload']['original_deadline'] == row(result)['original_deadline']
    assert not {'expire_at', 'expires_at', 'write_pending_until'} & set(payload)


def test_result_session_journal_only_copies_through_explicit_cold_custody(result):
    from database.jobstore.cold_sink import ColdSink

    adapter, _, _, item, _, artifacts = result
    artifacts.persist_result(item, {})
    with adapter.units.pool.connection() as conn:
        entry = conn.execute(
            "SELECT seq,epoch,family,identity,operation,owner_key,body FROM queue_journal WHERE namespace=%s AND family='queue_provider_uploads' ORDER BY seq LIMIT 1",
            (adapter.units.namespace,),
        ).fetchone()
    sink = ColdSink(adapter.handoff)
    sink.apply(entry, timeout=1.5)
    copied = sink.ref(entry[2], entry[3]).get().to_dict()
    assert copied['cold_only'] is True and copied['body'] == entry[6]
    assert not list(adapter.handoff.client.collection(adapter.units.namespace + '_jobs').stream())
    # The now-qualified explicit cold adapter cannot export unknown fields or
    # session capabilities, even from a real committed journal row.
    with adapter.units.pool.connection() as conn, conn.transaction():
        journal(
            conn,
            adapter.handoff.ticket,
            entry[2],
            entry[3],
            entry[5],
            {**entry[6], 'session': 'synthetic-unusable-capability'},
        )
        unknown = conn.execute(
            'SELECT seq,epoch,family,identity,operation,owner_key,body FROM queue_journal '
            'WHERE namespace=%s ORDER BY seq DESC LIMIT 1',
            (adapter.units.namespace,),
        ).fetchone()
    with pytest.raises(AuthorityRefused, match='source/admission/lifetime'):
        sink.apply(unknown, timeout=1.5)
    with adapter.units.pool.connection() as conn:
        assert conn.execute(
            'SELECT applied_seq FROM queue_authority WHERE namespace=%s', (adapter.units.namespace,)
        ).fetchone() == (0,)
    assert row(result)['phase'] == 'published'


def test_stale_epoch_cannot_claim_or_erase_original_session(result):
    from database.jobstore.authority import transition

    adapter, _, ticket, item, storage, artifacts = result
    storage._http.after_request = lambda *a: (_ for _ in ()).throw(ConnectionError('lost'))
    with pytest.raises(ConnectionError):
        artifacts.persist_result(item, {})
    storage._http.after_request = None
    adapter.units.fence.close(ticket.owner, local=True)
    with adapter.units.pool.connection() as conn, conn.transaction():
        transition(conn, adapter.units.namespace, 'PG_OPEN', 3, 'PG_CLOSING')
    storage._http.before_request = lambda *a: pytest.fail('stale destructive adapter touched storage')
    with pytest.raises(AuthorityRefused, match='epoch'):
        drain(result)
    assert row(result)['phase'] == 'registered' and effect(result) is not None


def test_restored_owner_cannot_publish_original_paid_result(result):
    from database.privacy_fence import FenceRefused

    adapter, _, ticket, item, storage, artifacts = result
    adapter.units.fence.close(ticket.owner, local=True)
    adapter.units.fence.admit_from_authority(
        adapter.handoff.client, item.owner_id, ticket.conversation_ids, lambda *_: None
    )
    storage._http.before_request = lambda *a: pytest.fail('restored original result sent bytes')
    with pytest.raises((FenceRefused, AuthorityRefused)):
        artifacts.persist_result(item, {})
    assert row(result) is None and effect(result) is None


def test_writing_transaction_rejects_changed_f_token_before_result_bytes(result, monkeypatch):
    from uuid import uuid4

    adapter, _, ticket, item, storage, artifacts = result
    upload = artifacts.session_upload
    real = upload._admission

    def rotate(item):
        admission = real(item)
        adapter.handoff.client.collection('batch_pipeline_privacy').document(ticket.owner).update(
            {'memo_token': uuid4().hex}
        )
        return admission

    monkeypatch.setattr(upload, '_admission', rotate)
    storage._http.before_request = lambda *a: pytest.fail('token-changed result sent bytes')
    with pytest.raises(AuthorityRefused, match='token'):
        artifacts.persist_result(item, {})
    assert row(result) is None and effect(result) is None


def test_budgeted_original_result_read_and_expired_deadline(result):
    import time
    from utils.batch_pipeline.artifact_reads import ArtifactReadBudget, ArtifactReadLimit

    _, _, _, item, _, artifacts = result
    uri = artifacts.persist_result(item, {'words': []})
    budget = ArtifactReadBudget(time.monotonic() + 10, 65536, 1)
    assert artifacts.load_result(item, uri, read_budget=budget) == {'words': []}
    assert budget.objects == 1 and 0 < budget.received_bytes == budget.downloaded_bytes < 65536
    expired = ArtifactReadBudget(time.monotonic() - 1, 65536, 1)
    with pytest.raises(ArtifactReadLimit, match='deadline'):
        artifacts.load_result(item, uri, read_budget=expired)
    assert expired.objects == 0


@pytest.mark.parametrize('change', ['restore', 'epoch'])
def test_budgeted_original_result_read_refuses_changed_authority(result, change):
    import time
    from database.jobstore.authority import transition
    from database.privacy_fence import FenceRefused
    from utils.batch_pipeline.artifact_reads import ArtifactReadBudget

    adapter, _, ticket, item, _, artifacts = result
    uri = artifacts.persist_result(item, {})
    if change == 'restore':
        adapter.units.fence.close(ticket.owner, local=True)
        adapter.units.fence.admit_from_authority(
            adapter.handoff.client, item.owner_id, ticket.conversation_ids, lambda *_: None
        )
    else:
        with adapter.units.pool.connection() as conn, conn.transaction():
            transition(conn, adapter.units.namespace, 'PG_OPEN', 3, 'PG_CLOSING')
    budget = ArtifactReadBudget(time.monotonic() + 10, 65536, 1)
    with pytest.raises((AuthorityRefused, FenceRefused)):
        artifacts.load_result(item, uri, read_budget=budget)
    assert budget.objects == budget.received_bytes == 0


@pytest.mark.parametrize('error_name', ['DeadlineExceeded', 'PreconditionFailed'])
def test_raw_storage_error_cannot_settle_whole_session_erasure(result, monkeypatch, error_name):
    from google.api_core import exceptions
    from utils.other.local_storage import LocalBlob

    adapter, _, ticket, item, storage, artifacts = result
    storage._http.after_request = lambda *a: (_ for _ in ()).throw(ConnectionError('lost'))
    with pytest.raises(ConnectionError):
        artifacts.persist_result(item, {})
    storage._http.after_request = None
    adapter.units.fence.close(ticket.owner, local=True)

    def unknown(*a, **k):
        raise getattr(exceptions, error_name)('earlier generation erase remains unproved')

    monkeypatch.setattr(LocalBlob, 'delete', unknown)
    with pytest.raises(ConnectionError, match='unresolved'):
        drain(result)
    assert effect(result) is not None and row(result)['phase'] == 'draining'
    gate = (
        adapter.handoff.client.collection(legal_holds.LEGAL_HOLD_DELETION_GATES_COLLECTION)
        .document(item.owner_id)
        .get()
        .to_dict()
    )
    assert gate['remote_inflight'] and gate['remote_target'].startswith('jobstore-gcs-v1:')
