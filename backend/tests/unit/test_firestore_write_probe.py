"""The write probe must count every committed write once, by collection, op and caller, and never break one."""

import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402

firestore = pytest.importorskip('google.cloud.firestore')
from google.auth.credentials import AnonymousCredentials  # noqa: E402
from google.cloud.firestore_v1.services.firestore import FirestoreClient  # noqa: E402
from google.cloud.firestore_v1.types import (  # noqa: E402
    BatchWriteResponse,
    CommitResponse,
    Document,
    DocumentMask,
    Precondition,
    Write,
    WriteResult,
)
from google.rpc import status_pb2  # noqa: E402

import database.firestore_write_probe as probe  # noqa: E402

ROOT = 'projects/p/databases/(default)/documents'


def _billed(collection, op, database='default'):
    value = probe.FIRESTORE_BILLED_WRITES.labels(collection=collection, op=op, database=database)._value.get()
    return float(value or 0)


def _by_caller(collection, op, caller):
    value = probe.FIRESTORE_BILLED_WRITES_BY_CALLER.labels(collection=collection, op=op, caller=caller)._value.get()
    return float(value or 0)


class _Transport:
    """Fake GAPIC Commit/BatchWrite: records requests, optionally fails."""

    def __init__(self):
        self.requests = []
        self.fail = False
        self.batch_status = None

    def commit(self, client, request=None, **kwargs):
        if self.fail:
            raise self.fail if isinstance(self.fail, BaseException) else RuntimeError('commit refused')
        self.requests.append(request)
        writes = request['writes'] if isinstance(request, dict) else request.writes
        return CommitResponse(write_results=[WriteResult() for _ in writes])

    def batch_write(self, client, request=None, **kwargs):
        self.requests.append(request)
        return BatchWriteResponse(status=[status_pb2.Status(code=code) for code in self.batch_status])


@pytest.fixture
def transport(monkeypatch):
    fake = _Transport()
    monkeypatch.setattr(FirestoreClient, 'commit', lambda self, request=None, **kw: fake.commit(self, request, **kw))
    monkeypatch.setattr(
        FirestoreClient, 'batch_write', lambda self, request=None, **kw: fake.batch_write(self, request, **kw)
    )
    monkeypatch.setattr(probe, '_installed', False)
    probe.install_document_write_probe()
    yield fake
    monkeypatch.setattr(probe, '_installed', False)


@pytest.fixture
def client(transport):
    db = firestore.Client(project='p', credentials=AnonymousCredentials())
    db._firestore_api_internal = FirestoreClient(credentials=AnonymousCredentials())
    return db


def test_write_op_classifies_every_write_shape():
    name = f'{ROOT}/users/u1/conversations/c1'
    create = Write(update=Document(name=name), current_document=Precondition(exists=False))
    assert probe.write_op(create) == ('create', 'default', ('users', 'u1', 'conversations', 'c1'))
    assert probe.write_op(Write(update=Document(name=name)))[0] == 'set'
    assert probe.write_op(Write(update=Document(name=name), update_mask=DocumentMask(field_paths=['a'])))[0] == 'merge'
    assert probe.write_op(Write(update=Document(name=name), current_document=Precondition(exists=True)))[0] == 'update'
    # A last-update-time CAS requires the document to exist: not an upsert.
    cas = Write(
        update=Document(name=name),
        update_mask=DocumentMask(field_paths=['a']),
        current_document=Precondition(update_time=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)),
    )
    assert probe.write_op(cas)[0] == 'update'
    assert probe.write_op(Write(delete=name))[0] == 'delete'
    assert probe.write_op({'delete': name})[0] == 'delete'
    named = probe.write_op(Write(delete='projects/p/databases/staging/documents/users/u1'))
    assert named == ('delete', 'named', ('users', 'u1'))
    assert probe.write_op(object()) == ('unknown', 'unknown', ())


def test_document_writes_counted_by_op_and_caller(client, transport):
    caller = f'{__name__}:test_document_writes_counted_by_op_and_caller'
    before = {op: _billed('users/conversations', op) for op in ('set', 'merge', 'update', 'create', 'delete')}
    by_caller = _by_caller('users/conversations', 'set', caller)

    ref = client.collection('users').document('u1').collection('conversations').document('c1')
    ref.set({'status': 'in_progress'})
    ref.set({'status': 'completed'}, merge=True)
    ref.update({'status': 'processing'})
    ref.create({'status': 'new'})
    ref.delete()

    assert _billed('users/conversations', 'set') == before['set'] + 1
    assert _billed('users/conversations', 'merge') == before['merge'] + 1
    assert _billed('users/conversations', 'update') == before['update'] + 1
    assert _billed('users/conversations', 'create') == before['create'] + 1
    assert _billed('users/conversations', 'delete') == before['delete'] + 1
    assert _by_caller('users/conversations', 'set', caller) == by_caller + 1
    # The probe observes and never skips: five Commit RPCs still ran.
    assert len(transport.requests) == 5


def test_batch_counts_each_write_and_failed_commit_counts_nothing(client, transport):
    before = _billed('users/memories', 'set')
    batch = client.batch()
    for i in range(3):
        batch.set(client.collection('users').document('u1').collection('memories').document(f'm{i}'), {'x': i})
    batch.commit()
    assert _billed('users/memories', 'set') == before + 3

    transport.fail = True
    failed = client.batch()
    failed.set(client.collection('users').document('u1').collection('memories').document('m9'), {'x': 9})
    with pytest.raises(RuntimeError):
        failed.commit()
    assert _billed('users/memories', 'set') == before + 3


def test_ambiguous_commit_is_counted_apart(client, transport):
    from google.api_core.exceptions import DeadlineExceeded, InvalidArgument

    billed = _billed('users/memories', 'set')
    ambiguous = probe.FIRESTORE_AMBIGUOUS_COMMIT_WRITES._value.get()
    ref = client.collection('users').document('u1').collection('memories').document('m1')

    transport.fail = DeadlineExceeded('response lost')
    with pytest.raises(DeadlineExceeded):
        ref.set({'x': 1}, retry=None)
    assert probe.FIRESTORE_AMBIGUOUS_COMMIT_WRITES._value.get() == ambiguous + 1

    # A definite rejection applied nothing and is not ambiguous.
    transport.fail = InvalidArgument('rejected')
    with pytest.raises(InvalidArgument):
        ref.set({'x': 1}, retry=None)
    assert probe.FIRESTORE_AMBIGUOUS_COMMIT_WRITES._value.get() == ambiguous + 1
    assert _billed('users/memories', 'set') == billed


def test_batch_write_counts_only_applied_writes(transport):
    before = _billed('users/memories', 'delete')
    transport.batch_status = [0, 10, 0]
    request = {'writes': [Write(delete=f'{ROOT}/users/u1/memories/m{i}') for i in range(3)]}
    FirestoreClient.batch_write(object(), request=request)
    assert _billed('users/memories', 'delete') == before + 2


def test_probe_sees_writes_a_later_commit_patch_appends(transport):
    # database._client installs the probe before memory_change_head, so the head
    # wrapper calls through the probe with its head write already appended.
    from database import memory_change_head

    head_wrapped = memory_change_head._wrap_commit(FirestoreClient.commit)
    source_before = _billed('users/memories', 'merge')
    head_before = _billed('other', 'merge') + _billed('users/memory_state', 'merge')
    write = Write(update=Document(name=f'{ROOT}/users/u1/memories/m1'), update_mask=DocumentMask(field_paths=['a']))
    head_wrapped(object(), request={'database': 'projects/p/databases/(default)', 'writes': [write]})
    assert _billed('users/memories', 'merge') == source_before + 1
    assert _billed('other', 'merge') + _billed('users/memory_state', 'merge') == head_before + 1
    assert len(transport.requests[-1].writes) == 2


def test_recording_failure_never_propagates(client, transport, monkeypatch):
    class _Exploding:
        def labels(self, **kwargs):
            raise RuntimeError('registry unavailable')

    monkeypatch.setattr(probe, 'FIRESTORE_BILLED_WRITES', _Exploding())
    monkeypatch.setattr(probe, 'FIRESTORE_BILLED_WRITES_BY_CALLER', _Exploding())
    monkeypatch.setattr(probe, 'FIRESTORE_BILLED_WRITES_BY_ORIGIN', _Exploding())
    client.collection('users').document('u1').set({'a': 1})
    assert len(transport.requests) == 1


def test_install_is_idempotent(transport):
    wrapped = FirestoreClient.commit
    probe._installed = False
    probe.install_document_write_probe()
    assert FirestoreClient.commit is wrapped


def test_caller_cap_folds_new_labels_to_other(monkeypatch):
    monkeypatch.setattr(probe, '_known_callers', {f'm{i}:f' for i in range(probe.MAX_WRITE_CALLERS)})
    overflow = probe.FIRESTORE_WRITE_CALLER_LABEL_OVERFLOW._value.get()
    assert probe._bound_caller('database.new_module:new_writer') == 'other'
    assert probe.FIRESTORE_WRITE_CALLER_LABEL_OVERFLOW._value.get() == overflow + 1
    assert probe._bound_caller('not a label') == 'other'
