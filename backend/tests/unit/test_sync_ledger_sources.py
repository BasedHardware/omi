"""Conversation deletion finds sync uploads through the owner's sync content ledger."""

from types import SimpleNamespace

import pytest

from database import batch_pipeline_purge as purge
from database import sync_ledger_sources as sources

UID = 'owner'
LEDGER = f'users/{UID}/sync_content_ledger_dev'
TOMBSTONES = f'users/{UID}/deleted_conversations'


class _Doc:
    def __init__(self, client, path):
        self.client, self.path = client, path
        self.id = path.rsplit('/', 1)[-1]

    def get(self, **kwargs):
        row = self.client.docs.get(self.path)
        return SimpleNamespace(exists=row is not None, to_dict=lambda: dict(row or {}))

    def collection(self, name):
        return _Collection(self.client, f'{self.path}/{name}')


class _Query:
    def __init__(self, collection, field, op, values):
        self.collection, self.field, self.op, self.values = collection, field, op, values

    def stream(self):
        if self.collection.client.fail_reads:
            raise RuntimeError('ledger unavailable')
        if self.op == '==':
            self.collection.client.job_queries.append(self.values)
        else:
            self.collection.client.queries.append((self.field, list(self.values)))
        prefix = self.collection.path + '/'
        for path, row in sorted(self.collection.client.docs.items()):
            if not path.startswith(prefix) or '/' in path[len(prefix) :]:
                continue
            value = row
            for part in self.field.split('.'):
                value = (value or {}).get(part) if isinstance(value, dict) else None
            if self.op == '==':
                matched = value == self.values
            else:
                matched = isinstance(value, list) and bool(set(value) & set(self.values))
            if matched:
                yield SimpleNamespace(id=path[len(prefix) :], to_dict=lambda row=row: dict(row))


class _Collection:
    def __init__(self, client, path):
        self.client, self.path = client, path

    def document(self, doc_id):
        return _Doc(self.client, f'{self.path}/{doc_id}')

    def where(self, *, filter):
        if filter.op_string == '==':
            # Every ledger row of one upload job: its staging directory is shared by all of them.
            assert filter.field_path == 'job_id'
            return _Query(self, filter.field_path, '==', filter.value)
        assert filter.op_string == 'array_contains_any'
        assert len(filter.value) <= 30
        return _Query(self, filter.field_path, 'array_contains_any', filter.value)


class _Client:
    def __init__(self, docs):
        self.docs, self.queries, self.job_queries, self.fail_reads = dict(docs), [], [], False

    def collection(self, name):
        return _Collection(self, name)


@pytest.fixture(autouse=True)
def dev_stage(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')


def _row(job_id, new=(), updated=(), partial=(), segments=None, namespace='batch_pipeline_dev', status='completed'):
    row = {
        'job_id': job_id,
        'status': status,
        'result': {'new_memories': list(new), 'updated_memories': list(updated)},
        'partial_result': {'new_memories': list(partial), 'updated_memories': []},
    }
    if segments is not None:
        row['batch_pipeline'] = {'namespace': namespace, 'segment_ids': list(segments)}
    return row


def test_uploads_found_from_every_conversation_field_and_unsafe_job_ids_dropped():
    client = _Client(
        {
            f'{LEDGER}/created': _row('job-created', new=['c1']),
            f'{LEDGER}/updated': _row('job-updated', updated=['c1', 'sibling']),
            f'{LEDGER}/partial': _row('job-partial', partial=['c1']),
            f'{LEDGER}/traversal': _row('../other-owner', new=['c1']),
            f'{LEDGER}/unrelated': _row('job-unrelated', new=['c2']),
            'users/someone-else/sync_content_ledger_dev/x': _row('job-foreign', new=['c1']),
        }
    )
    uploads = sources.uploads_for_conversations(UID, ['c1'], firestore_client=client)
    assert sorted(upload.job_id for upload in uploads if upload.job_id) == [
        'job-created',
        'job-partial',
        'job-updated',
    ]
    assert {field for field, _ in client.queries} == set(sources.CONVERSATION_FIELDS)


def test_lookup_chunks_conversation_ids_to_the_firestore_limit():
    client = _Client({f'{LEDGER}/last': _row('job-last', new=['c44'])})
    ids = [f'c{i}' for i in range(45)]
    assert [u.job_id for u in sources.uploads_for_conversations(UID, ids, firestore_client=client)] == ['job-last']
    assert sorted(len(values) for _, values in client.queries) == [15] * 4 + [30] * 4


def test_no_ids_means_no_reads():
    client = _Client({})
    assert sources.uploads_for_conversations(UID, [None, ''], firestore_client=client) == []
    assert client.queries == []


def test_batch_segments_owed_only_when_every_fed_conversation_is_deleted():
    client = _Client(
        {
            f'{LEDGER}/solo': _row('job-solo', new=['c1'], segments=['s1', 's2']),
            f'{LEDGER}/shared-live': _row('job-shared', new=['c1'], updated=['live'], segments=['s3']),
            f'{LEDGER}/shared-deleted': _row('job-both', updated=['c1', 'gone'], segments=['s4']),
            f'{LEDGER}/no-batch': _row('job-legacy', new=['c1']),
            f'{TOMBSTONES}/c1': {},
            f'{TOMBSTONES}/gone': {},
        }
    )
    assert sources.owed_batch_segments(UID, ['c1'], firestore_client=client) == {
        'batch_pipeline_dev': {'s1', 's2', 's4'}
    }


def test_unknown_stage_has_no_ledger_to_read(monkeypatch):
    monkeypatch.delenv('OMI_ENV_STAGE', raising=False)
    client = _Client({f'{LEDGER}/created': _row('job-created', new=['c1'])})
    assert sources.staging_job_ids(UID, ['c1'], firestore_client=client) == []
    assert sources.owed_batch_segments(UID, ['c1'], firestore_client=client) == {}
    assert client.queries == []


def test_inline_conversation_batch_purge_erases_ledger_linked_rows(monkeypatch):
    """Rows keyed by an upload's provisional capture identity are erased with the conversation."""
    ns = 'batch_pipeline_prod'
    client = _Client({f'users/{UID}/deleted_conversations/c1': {}})
    for table, doc_id in (('jobs', 'seg-job'), ('results', 'seg-job'), ('results', 'seg-result'), ('results', 'other')):
        client.docs[f'{ns}_{table}/{doc_id}'] = {'owner_key': 'k', 'conversation_id': 'capture-identity'}
    monkeypatch.setattr(purge, 'privacy_owner_key', lambda uid: 'k')
    monkeypatch.setattr(
        purge,
        'owed_batch_segments',
        lambda uid, cids, **kwargs: {ns: {'seg-job', 'seg-result'}} if cids == ['c1'] else {},
    )

    def owner_documents(_client, namespace, table, key, *, after=None):
        prefix = f'{namespace}_{table}/'
        if after:
            return []
        return [
            SimpleNamespace(id=path[len(prefix) :], to_dict=lambda path=path: dict(client.docs[path]))
            for path in sorted(client.docs)
            if path.startswith(prefix)
        ]

    erased = []
    monkeypatch.setattr(purge.queries, 'owner_documents', owner_documents)
    monkeypatch.setattr(purge.queries, 'artifacts_by_owner_id', lambda *args, **kwargs: [])
    monkeypatch.setattr(purge, '_delete_job', lambda _c, _ns, snapshot, **kwargs: erased.append(('jobs', snapshot.id)))
    monkeypatch.setattr(
        purge, '_erase_result', lambda _c, _ns, snapshot, **kwargs: erased.append(('results', snapshot.id))
    )
    monkeypatch.setattr(purge, 'mirror_refresh', lambda *args: None)
    monkeypatch.setattr(purge, 'purge_jobstore_owner', lambda *args: 0)
    purge.purge_batch_owner(
        UID, conversation_id='c1', namespaces=(ns,), firestore_client=client, delete_uri=lambda *a: None
    )
    assert sorted(erased) == [('jobs', 'seg-job'), ('results', 'seg-job'), ('results', 'seg-result')]


def test_shared_upload_with_a_live_sibling_keeps_its_staging():
    """Deleting A from an A/B upload must not erase the staged bytes B still needs."""
    client = _Client(
        {
            f'{LEDGER}/shared': _row('job-shared', new=['a'], updated=['b']),
            f'{LEDGER}/solo': _row('job-solo', new=['a']),
            f'{TOMBSTONES}/a': {},
        }
    )
    plan = sources.staging_plan(UID, ['a'], firestore_client=client)
    assert plan == sources.StagingPlan(erasable=('job-solo',), shared_live=('job-shared',))
    assert sources.staging_job_ids(UID, ['a'], firestore_client=client) == ['job-solo']


def test_deleting_the_last_sibling_makes_the_shared_staging_erasable():
    client = _Client(
        {
            f'{LEDGER}/shared': _row('job-shared', new=['a'], updated=['b']),
            f'{TOMBSTONES}/a': {},
            f'{TOMBSTONES}/b': {},
        }
    )
    assert sources.staging_plan(UID, ['b'], firestore_client=client).erasable == ('job-shared',)


def test_sibling_fed_by_another_ledger_row_of_the_same_job_keeps_the_staging():
    """The directory is keyed by job: a row that does not name the deleted conversation still counts."""
    client = _Client(
        {
            f'{LEDGER}/first-file': _row('job-shared', new=['a']),
            f'{LEDGER}/second-file': _row('job-shared', new=['b']),
            f'{TOMBSTONES}/a': {},
        }
    )
    assert sources.staging_plan(UID, ['a'], firestore_client=client).shared_live == ('job-shared',)
    assert client.job_queries == ['job-shared']


def test_staging_of_an_unfinished_upload_is_retained_for_retry():
    client = _Client({f'{LEDGER}/running': _row('job-running', new=['a'], status='processing'), f'{TOMBSTONES}/a': {}})
    plan = sources.staging_plan(UID, ['a'], firestore_client=client)
    assert plan == sources.StagingPlan(in_flight=('job-running',))


def test_ledger_read_failure_propagates_instead_of_erasing_nothing_silently():
    client = _Client({f'{LEDGER}/solo': _row('job-solo', new=['a']), f'{TOMBSTONES}/a': {}})
    client.fail_reads = True
    with pytest.raises(RuntimeError, match='ledger unavailable'):
        sources.staging_plan(UID, ['a'], firestore_client=client)
