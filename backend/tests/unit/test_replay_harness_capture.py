"""Hermetic capture privacy, owner scoping, immutable blobs and read capabilities."""

import hashlib
import hmac
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from testing.replay_harness import capture_prod as capture
from testing.replay_harness.capture_schema import manifest_stub
from testing.replay_harness.guard import (
    CaptureRefused,
    consenting_uid,
    conversations,
    private_directory,
    private_text,
)

UID = 'synthetic-consenting-owner-28'
CID = 'synthetic-conversation'
SALT = b'a-per-corpus-synthetic-salt'


def digest(value):
    return hmac.new(SALT, str(value).encode(), hashlib.sha256).hexdigest() if value else None


def private_input(tmp_path, name, body):
    path = tmp_path / name
    path.write_text(body)
    path.chmod(0o600)
    return path


@pytest.fixture(autouse=True)
def no_credentials_or_network(monkeypatch):
    # Also run this suite with these unset in the launching process. conftest
    # installs invalid ADC for legacy suites; this capture suite needs none.
    for key in list(os.environ):
        if key == 'GOOGLE_APPLICATION_CREDENTIALS' or key.startswith('CLOUDSDK_'):
            monkeypatch.delenv(key)
    from testing.hermetic_network import block_outbound_network

    with block_outbound_network():
        yield


@pytest.mark.parametrize('mode', [0o644, 0o640, 0o400, 0o666, 0o700])
@pytest.mark.parametrize('which', ['uid', 'consent', 'conversations'])
def test_guard_refuses_non_0600_inputs(tmp_path, mode, which):
    paths = {
        'uid': private_input(tmp_path, 'uid', UID),
        'consent': private_input(tmp_path, 'consent', hashlib.sha256(UID.encode()).hexdigest() + '\n'),
        'conversations': private_input(tmp_path, 'conversations', CID + '\n'),
    }
    paths[which].chmod(mode)
    with pytest.raises(CaptureRefused) as error:
        if which == 'conversations':
            conversations(paths[which])
        else:
            consenting_uid(paths['uid'], paths['consent'])
    assert UID not in str(error.value)


def test_guard_pins_owner_and_never_edits_consent(tmp_path):
    uid_file = private_input(tmp_path, 'uid', UID)
    pin = hashlib.sha256(UID.encode()).hexdigest() + '\n'
    consent = private_input(tmp_path, 'consent', pin)
    assert consenting_uid(uid_file, consent) == UID
    uid_file.write_text('another-owner')
    with pytest.raises(CaptureRefused, match='not pinned'):
        consenting_uid(uid_file, consent)
    assert consent.read_text() == pin


@pytest.mark.parametrize('body', ['', 'x' * 64, ' ' + 'a' * 64, 'a' * 64 + '\n\n'])
def test_guard_refuses_malformed_pin_files(tmp_path, body):
    with pytest.raises(CaptureRefused):
        consenting_uid(private_input(tmp_path, 'uid', UID), private_input(tmp_path, 'consent', body))


def test_guard_refuses_symlinks_directories_and_unsafe_conversation_ids(tmp_path):
    original = private_input(tmp_path, 'uid', UID)
    link = tmp_path / 'link'
    link.symlink_to(original)
    for path in (link, tmp_path):
        with pytest.raises(CaptureRefused):
            private_text(path)
    for value in ('../other', 'nested/doc', '.', '', CID + '\n' + CID):
        with pytest.raises(CaptureRefused):
            conversations(private_input(tmp_path, 'selected', value))


def test_guard_rejects_unpinned_owner_before_client_creation(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('GCP_AGENT_TIER', 'ro-prod')
    monkeypatch.setattr(capture, 'bucket_config', lambda: pytest.fail('no config/client reads before consent'))
    args = [
        '--tier',
        'C',
        '--uid-file',
        str(private_input(tmp_path, 'uid', UID)),
        '--consent-file',
        str(private_input(tmp_path, 'consent', 'a' * 64)),
        '--conversations-file',
        str(private_input(tmp_path, 'selected', CID)),
        '--output',
        str(tmp_path / 'output'),
    ]
    assert capture.main(args) == 1
    assert not (tmp_path / 'output').exists()
    output = capsys.readouterr()
    assert UID not in output.out + output.err
    assert json.loads(output.out) == {'capture': 'failed', 'exception_type': 'CaptureRefused'}


def test_output_refuses_git_and_symlink_or_open_directories(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir(mode=0o700)
    (repo / '.git').write_text('gitdir: elsewhere')
    with pytest.raises(CaptureRefused, match='outside Git'):
        private_directory(repo / 'output', create=True)
    opened = tmp_path / 'opened'
    opened.mkdir(mode=0o755)
    opened.chmod(0o755)
    with pytest.raises(CaptureRefused, match='0700'):
        private_directory(opened)
    link = tmp_path / 'link'
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(CaptureRefused, match='symlinks'):
        private_directory(link / 'output', create=True)


class Session:
    def __init__(self, responses=()):
        self.calls = []
        self.responses = iter(responses)

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return next(self.responses)


def response(body=None, *, status=200, content=b''):
    return SimpleNamespace(status_code=status, json=lambda: body, content=content)


@pytest.mark.parametrize('method', ['PUT', 'PATCH', 'DELETE', 'POST'])
def test_transport_refuses_storage_writes_before_network(method):
    session = Session()
    transport = capture.ReadOnlyTransport(session)
    with pytest.raises(capture.ReadOnlyViolation):
        transport.request(method, capture.STORAGE_ROOT + '/b/bucket/o/object')
    assert session.calls == []


@pytest.mark.parametrize('operation', ['commit', 'batchWrite', 'beginTransaction', 'rollback', 'delete', 'update'])
def test_transport_refuses_firestore_mutations_before_network(operation):
    session = Session()
    with pytest.raises(capture.ReadOnlyViolation):
        capture.ReadOnlyTransport(session).request('POST', capture.FIRESTORE_ROOT + ':' + operation, json={})
    assert not session.calls


@pytest.mark.parametrize(
    'name', ['set', 'create', 'update', 'delete', 'write', 'upload_from_string', 'batch', 'transaction']
)
def test_wrapped_clients_cannot_delegate_sdk_write_calls(name):
    session = Session()
    transport = capture.ReadOnlyTransport(session)
    for client in (transport, capture.ReadOnlyFirestore(transport), capture.ReadOnlyStorage(transport)):
        with pytest.raises(capture.ReadOnlyViolation):
            getattr(client, name)('anything')
    assert not session.calls


def test_transport_refuses_redirects_and_never_exposes_error_urls():
    session = Session([response(status=302)])
    with pytest.raises(capture.CaptureReadError) as error:
        capture.ReadOnlyTransport(session).request('GET', capture.STORAGE_ROOT + '/b/bucket/o/' + UID)
    assert UID not in str(error.value)
    assert session.calls[0][2]['allow_redirects'] is False


def test_tier_s_rpc_uses_only_the_projected_admission_allowlist():
    session = Session([response([])])
    db = capture.ReadOnlyFirestore(capture.ReadOnlyTransport(session))
    db.query(
        capture.PREFIX + 'jobs',
        filters=[capture.eq('state', 'record_pending')],
        fields=capture.ADMISSION_FIELDS,
        order='available_at',
        limit=500,
        require_complete=False,
    )
    query = session.calls[0][2]['json']['structuredQuery']
    assert query['select'] == {'fields': [{'fieldPath': field} for field in capture.ADMISSION_FIELDS]}
    assert set(capture.ADMISSION_FIELDS) == {
        'owner_id',
        'conversation_id',
        'state',
        'attempt',
        'available_at',
        'duration_seconds',
        'worker_vad_receipt.captured_samples',
        'worker_vad_receipt.speech_samples',
    }
    assert query['where'] == capture.eq('state', 'record_pending')
    assert query['orderBy'][0]['field']['fieldPath'] == 'available_at'
    assert query['limit'] == 500


@pytest.mark.parametrize(
    ('delta', 'bucket'),
    [
        (None, 'unknown'),
        (1, 'future'),
        (0, 'due-under-1m'),
        (-60, 'due-under-1h'),
        (-3600, 'due-under-1d'),
        (-86400, 'due-over-1d'),
    ],
)
def test_tier_s_constructs_only_safe_fields_and_buckets_time(delta, bucket):
    row = {
        'owner_id': UID,
        'conversation_id': CID,
        'state': 'private-error',
        'attempt': 3,
        'available_at': 1234567890 + delta if delta is not None else None,
        'duration_seconds': float('nan'),
        'worker_vad_receipt': {'captured_samples': 20, 'speech_samples': 10, 'text': 'private text'},
        'text': 'private text',
        'uri': 'gs://private',
        'error': 'raw exception',
    }
    captured = capture.admission_shape('private-unit', row, digest, 1234567890)
    assert captured == {
        'unit': digest('private-unit'),
        'owner': digest(UID),
        'conversation': digest(CID),
        'state': 'other',
        'attempt': 3,
        'available_at_bucket': bucket,
        'duration_seconds': None,
        'captured_samples': 20,
        'speech_samples': 10,
    }
    assert all(
        private not in json.dumps(captured)
        for private in (UID, CID, 'private text', 'gs://', 'raw exception', '1234567890')
    )


def test_structure_case_counts_are_explicitly_bounded_to_window(tmp_path):
    class DB:
        def query(self, collection, **kwargs):
            assert kwargs['fields'] == capture.ADMISSION_FIELDS
            assert kwargs['require_complete'] is False
            return {'job': {'owner_id': UID, 'conversation_id': CID, 'state': 'record_pending', 'available_at': 0}}

    summary = capture.capture_structure(DB(), tmp_path, digest, limit=1, now=1)
    case = tmp_path / 'admission-window'
    corpus = json.loads((case / 'corpus.json').read_text())
    manifest = json.loads((case / 'manifest.json').read_text())
    assert summary == {'cases': 1, 'rows': 1}
    assert corpus['window_full'] is True and corpus['window_limit'] == 1
    assert manifest['prod_evidence'] == {'rows': 1, 'owners': 1, 'conversations': 1, 'due_rows': 1}
    assert UID not in (case / 'corpus.json').read_text()
    assert manifest['stages'] == {}


def test_check_access_only_tests_permissions_never_lists_objects(monkeypatch):
    session = Session([response({'permissions': ['storage.objects.list']}), response(status=403)])
    storage = capture.ReadOnlyStorage(capture.ReadOnlyTransport(session))
    facts = capture.check_access(storage, {'batch': 'bucket-a', 'chunks': 'bucket-b', 'derived': ''})
    assert facts == [
        {'bucket': 'bucket-a', 'status': 'checked', 'storage.objects.get': False, 'storage.objects.list': True},
        {'bucket': 'bucket-b', 'status': 'unavailable', 'storage.objects.get': False, 'storage.objects.list': False},
    ]
    assert all(method == 'GET' and url.endswith('/iam/testPermissions') for method, url, _ in session.calls)
    assert all(
        kwargs['params'] == [('permissions', permission) for permission in capture.READ_PERMISSIONS]
        for _, _, kwargs in session.calls
    )


def test_bucket_names_come_from_backend_config_and_runtime_overrides(monkeypatch):
    for key in ('BUCKET_BATCH_PIPELINE', 'BUCKET_PRIVATE_CLOUD_SYNC', 'BUCKET_AUDIO_DERIVED'):
        monkeypatch.delenv(key, raising=False)
    assert capture.bucket_config() == {
        'BUCKET_BATCH_PIPELINE': 'based-hardware-batch-pipeline-staging',
        'BUCKET_PRIVATE_CLOUD_SYNC': 'omi-private-cloud-sync',
        'BUCKET_AUDIO_DERIVED': 'omi-audio-derived-uc1',
    }
    monkeypatch.setenv('BUCKET_AUDIO_DERIVED', 'synthetic-derived-bucket')
    assert capture.bucket_config()['BUCKET_AUDIO_DERIVED'] == 'synthetic-derived-bucket'


def test_storage_inventory_handles_pagination_and_projects_metadata_only():
    session = Session(
        [
            response(
                {'items': [{'name': 'chunks/owner/cid/a', 'generation': '10', 'size': '12'}], 'nextPageToken': 'next'}
            ),
            response({'items': [{'name': 'chunks/owner/cid/b', 'generation': '11', 'size': '13'}]}),
        ]
    )
    rows = capture.ReadOnlyStorage(capture.ReadOnlyTransport(session)).inventory('bucket', 'chunks/owner/cid/')
    assert len(rows) == 2 and rows[1]['size'] == 13
    assert session.calls[1][2]['params']['pageToken'] == 'next'
    assert all(
        kwargs['params']['fields'] == 'items(name,generation,size),nextPageToken' for _, _, kwargs in session.calls
    )


def test_ciphertext_uses_exact_generation_without_decryption():
    ciphertext = b'OMIBP1\x00\xff\x81opaque-encrypted-bytes'
    session = Session([response({'generation': '123'}), response(content=ciphertext)])
    result = capture.ReadOnlyStorage(capture.ReadOnlyTransport(session)).ciphertext('bucket', 'owner/object.enc')
    assert result == (ciphertext, '123')
    assert session.calls[1][2]['params'] == {'alt': 'media', 'generation': '123'}
    assert session.calls[1][1].endswith('owner%2Fobject.enc')


def test_plaintext_is_never_persisted_as_an_artifact():
    storage = capture.ReadOnlyStorage(capture.ReadOnlyTransport(Session([response(content=b'plaintext')])))
    with pytest.raises(CaptureRefused, match='ciphertext envelope'):
        storage.ciphertext('bucket', 'object.enc', '123')


class OwnerDB:
    def __init__(self):
        self.calls = []
        self.owner_hash = hashlib.sha256(UID.encode()).hexdigest()
        self.uri = f'gs://batch/batch-pipeline/batch_pipeline_prod/owners/{self.owner_hash}/audio/unit/key.enc'
        self.job = {'owner_id': UID, 'segment_id': 'unit', 'conversation_id': CID, 'audio_uri': self.uri + '#123'}
        self.result = {'owner_key': self.owner_hash, 'result': {'result_uri': self.uri + '#123'}}
        self.artifact = {'owner_id': UID, 'segment_id': 'unit', 'uri': self.uri, 'kind': 'audio'}
        self.conversation = {
            'id': CID,
            'finalization_job_id': 'final-job',
            'status': 'processing',
            'record_audio_closed': True,
            'structured': {'title': ''},
            'transcript_segments': [{'speaker_id_scope': 'final:batch:unit', 'text': 'owner=' + UID}],
            'audio_files': [{'path': f'chunks/{UID}/{CID}/chunk'}],
            UID: UID,
        }

    def query(self, collection, **kwargs):
        self.calls.append((collection, kwargs))
        if collection.endswith('_jobs') and collection.startswith('batch_pipeline'):
            return {'unit': self.job}
        if collection.endswith('_artifacts'):
            return {'artifact': self.artifact}
        if collection == 'conversation_finalization_jobs':
            return {'final-job': {'uid': UID, 'conversation_id': CID, 'status': 'queued'}}
        raise AssertionError('unexpected query')

    def read(self, paths):
        docs = {
            f'users/{UID}/conversations/{CID}': self.conversation,
            capture.PREFIX + 'jobs/unit': self.job,
            capture.PREFIX + 'results/unit': self.result,
            'sync_reprocess_outbox/'
            + hashlib.sha256(f'{UID}\0{CID}'.encode()).hexdigest(): {'uid': UID, 'conversation_id': CID},
        }
        return {path: docs[path] for path in paths if path in docs}


class OwnerStorage:
    ciphertext_bytes = b'OMIBP1\x00\x80\xffopaque ciphertext'

    def __init__(self):
        self.calls = []

    def inventory(self, bucket, prefix):
        self.calls.append(('inventory', bucket, prefix))
        return [{'bucket': bucket, 'name': prefix + 'chunk', 'size': 12, 'generation': '4'}]

    def ciphertext(self, bucket, name, generation):
        self.calls.append(('ciphertext', bucket, name, generation))
        return self.ciphertext_bytes, generation


BUCKETS = {'BUCKET_BATCH_PIPELINE': 'batch', 'BUCKET_PRIVATE_CLOUD_SYNC': 'chunks', 'BUCKET_AUDIO_DERIVED': 'derived'}


def test_owner_case_is_replayable_private_tokenized_and_byte_exact(tmp_path, capsys, caplog):
    db, storage = OwnerDB(), OwnerStorage()
    assert capture.capture_owner(db, storage, tmp_path, digest, UID, [CID], BUCKETS) == {
        'cases': 1,
        'items': [{'item': 'owner-' + digest(CID), 'status': 'complete', 'exception_type': None}],
    }
    case = tmp_path / ('owner-' + digest(CID))
    manifest = json.loads((case / 'manifest.json').read_text())
    corpus = json.loads((case / 'corpus.json').read_text())
    assert manifest['schema_version'] == 1 and manifest['tier'] == 'C' and manifest['stages'] == {}
    assert manifest['prod_evidence']['audio_closed'] == 1
    assert manifest['prod_evidence']['outbox_rows'] == 1
    assert manifest['prod_evidence']['finalization_status'] == 'queued'
    assert manifest['prod_evidence']['has_title'] == 0
    assert all(
        type(value) is int or value in {'processing', 'queued', 'missing', 'complete'}
        for key, value in manifest['prod_evidence'].items()
        if key != 'missing_input'
    )
    assert manifest['prod_evidence']['missing_input'] == []
    assert set(corpus['jobs']) == set(corpus['results']) == {'unit'}
    assert corpus['jobs']['unit']['owner_id'] == corpus['owner_token']
    assert corpus['conversation'][corpus['owner_token']] == corpus['owner_token']
    assert len(corpus['chunk_inventory']) == 2
    encrypted = list((case / 'blobs').iterdir())
    assert len(encrypted) == 1 and encrypted[0].read_bytes() == storage.ciphertext_bytes
    for blob in corpus['seed_blobs']:
        assert hashlib.sha256((case / blob['path']).read_bytes()).hexdigest() == blob['sha256']
        assert blob['sha256'] in manifest['seed_blob_sha256']
    assert hashlib.sha256((case / 'corpus.json').read_bytes()).hexdigest() in manifest['seed_blob_sha256']
    for path in [case, *case.rglob('*')]:
        assert stat.S_IMODE(path.stat().st_mode) == (0o700 if path.is_dir() else 0o600)
        if path.is_file():
            assert UID.encode() not in path.read_bytes()
    output = capsys.readouterr()
    assert UID not in output.out + output.err + caplog.text
    assert ('ciphertext', 'batch', db.uri.split('/', 3)[3], '123') in storage.calls
    for collection, kwargs in db.calls:
        assert (
            capture.eq('uid' if collection == 'conversation_finalization_jobs' else 'owner_id', UID)
            in kwargs['filters']
        )


@pytest.mark.parametrize('kind', ['job', 'result', 'artifact', 'foreign-uri', 'foreign-unit'])
def test_owner_capture_refuses_cross_user_links_before_download(tmp_path, kind):
    db, storage = OwnerDB(), OwnerStorage()
    if kind == 'job':
        db.job['owner_id'] = 'someone-else'
    elif kind == 'result':
        db.result['owner_key'] = 'someone-else'
    elif kind == 'artifact':
        db.artifact['owner_id'] = 'someone-else'
    elif kind == 'foreign-uri':
        db.artifact['uri'] = db.uri.replace(db.owner_hash, 'another-owner')
    else:
        db.artifact['uri'] = db.uri.replace('/unit/', '/other-unit/')
    summary = capture.capture_owner(db, storage, tmp_path, digest, UID, [CID], BUCKETS)
    assert summary['items'] == [
        {'item': 'owner-' + digest(CID), 'status': 'refused', 'exception_type': 'CaptureRefused'}
    ]
    assert not (tmp_path / ('owner-' + digest(CID))).exists()
    assert not any(call[0] == 'ciphertext' for call in storage.calls)


def test_missing_ciphertext_is_explicit_evidence_not_synthetic_success(tmp_path):
    storage = OwnerStorage()
    storage.ciphertext = lambda *_args: None
    capture.capture_owner(OwnerDB(), storage, tmp_path, digest, UID, [CID], BUCKETS)
    case = tmp_path / ('owner-' + digest(CID))
    manifest = json.loads((case / 'manifest.json').read_text())
    corpus = json.loads((case / 'corpus.json').read_text())
    assert manifest['prod_evidence']['missing_blobs'] == 1
    assert manifest['prod_evidence']['ciphertext_blobs'] == 0
    assert manifest['prod_evidence']['capture_status'] == 'partial'
    assert manifest['prod_evidence']['missing_input'] == ['BUCKET_BATCH_PIPELINE']
    assert corpus['blob_refs'][0]['status'] == 'missing'
    assert not list((case / 'blobs').iterdir())


def test_manifest_rejects_text_ids_errors_and_unapproved_states():
    for evidence in ({'uid': UID}, {'error': 'raw error'}, {'conversation_status': UID}, {'rows': True}, {'rows': -1}):
        with pytest.raises(ValueError):
            manifest_stub('case', 'C', evidence, [])


@pytest.mark.parametrize('opaque', ['opaque encrypted transcript', {'_firestore_bytes_base64': 'AA=='}])
def test_encrypted_conversation_is_preserved_without_decoding(tmp_path, opaque):
    db = OwnerDB()
    db.conversation['transcript_segments'] = opaque
    capture.capture_owner(db, OwnerStorage(), tmp_path, digest, UID, [CID], BUCKETS)
    corpus = json.loads((tmp_path / ('owner-' + digest(CID)) / 'corpus.json').read_text())
    assert corpus['conversation']['transcript_segments'] == opaque
    assert corpus['referenced_units'] == ['unit']


def test_missing_artifact_receipt_keeps_owner_bound_referenced_ciphertext(tmp_path):
    db = OwnerDB()
    original = db.query
    db.query = lambda collection, **kwargs: {} if collection.endswith('_artifacts') else original(collection, **kwargs)
    capture.capture_owner(db, OwnerStorage(), tmp_path, digest, UID, [CID], BUCKETS)
    case = tmp_path / ('owner-' + digest(CID))
    corpus = json.loads((case / 'corpus.json').read_text())
    assert corpus['artifacts'] == {}
    assert corpus['blob_refs'][0]['artifact_id'] is None
    assert corpus['blob_refs'][0]['status'] == 'captured'
    assert len(list((case / 'blobs').iterdir())) == 1


def test_orphan_receipt_discovers_unit_when_jobs_and_transcript_scopes_are_unavailable(tmp_path):
    db = OwnerDB()
    db.conversation['transcript_segments'] = 'encrypted blob'
    original_query, original_read = db.query, db.read
    db.query = lambda collection, **kwargs: (
        {} if collection == capture.PREFIX + 'jobs' else original_query(collection, **kwargs)
    )
    db.read = lambda paths: {
        path: row for path, row in original_read(paths).items() if path != capture.PREFIX + 'jobs/unit'
    }
    capture.capture_owner(db, OwnerStorage(), tmp_path, digest, UID, [CID], BUCKETS)
    corpus = json.loads((tmp_path / ('owner-' + digest(CID)) / 'corpus.json').read_text())
    assert corpus['jobs'] == {}
    assert corpus['referenced_units'] == ['unit']
    assert corpus['artifacts']['artifact']['segment_id'] == 'unit'
    assert corpus['results']['unit']['owner_key'] == db.owner_hash


def test_firestore_wire_bytes_preserve_type_without_decrypting():
    assert capture.decode_fields(
        {
            'segments': {'bytesValue': 'AP8='},
            'nested': {'mapValue': {'fields': {'words': {'arrayValue': {'values': [{'stringValue': 'opaque'}]}}}}},
        }
    ) == {'segments': {'_firestore_bytes_base64': 'AP8='}, 'nested': {'words': ['opaque']}}


@pytest.mark.parametrize('identity', ['ro-prod', 'prod-operator'])
@pytest.mark.parametrize('fail', [False, True])
def test_cli_owner_success_and_failure_never_log_uid(tmp_path, monkeypatch, capsys, fail, identity):
    import google.auth
    from google.auth.transport import requests
    from contextlib import nullcontext

    monkeypatch.setenv('GCP_AGENT_TIER', identity)
    monkeypatch.setattr(google.auth, 'default', lambda **kwargs: (object(), 'synthetic-project'))
    monkeypatch.setattr(requests, 'AuthorizedSession', lambda credentials: nullcontext(object()))
    monkeypatch.setattr(capture, 'bucket_config', lambda: BUCKETS)
    db = OwnerDB()
    if fail:

        def failed_read(_paths):
            raise RuntimeError('private provider URL includes ' + UID)

        db.read = failed_read
    monkeypatch.setattr(capture, 'ReadOnlyFirestore', lambda _: db)
    monkeypatch.setattr(capture, 'ReadOnlyStorage', lambda _: OwnerStorage())
    output = tmp_path / 'output'
    args = [
        '--tier',
        'C',
        '--output',
        str(output),
        '--uid-file',
        str(private_input(tmp_path, 'uid', UID)),
        '--consent-file',
        str(private_input(tmp_path, 'consent', hashlib.sha256(UID.encode()).hexdigest())),
        '--conversations-file',
        str(private_input(tmp_path, 'selected', CID)),
    ]
    assert capture.main(args) == int(fail)
    logs = capsys.readouterr()
    assert UID not in logs.out + logs.err
    summary = json.loads(logs.out)
    assert summary['capture'] == ('partial' if fail else 'complete')
    assert summary['items'][0]['status'] == ('partial' if fail else 'complete')
    assert summary['items'][0]['exception_type'] == ('RuntimeError' if fail else None)
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert stat.S_IMODE((output / 'salt').stat().st_mode) == 0o600


@pytest.mark.parametrize(
    ('method', 'url', 'allowed'),
    [
        ('POST', capture.FIRESTORE_ROOT + ':runQuery', True),
        ('POST', capture.FIRESTORE_ROOT + ':batchGet', True),
        ('GET', capture.STORAGE_ROOT + '/b/bucket/o', True),
        ('GET', capture.FIRESTORE_ROOT + '/collection/doc', False),
        ('POST', capture.FIRESTORE_ROOT + ':commit', False),
        ('POST', capture.FIRESTORE_ROOT + ':batchWrite', False),
        ('POST', capture.STORAGE_ROOT + '/b/bucket/o', False),
        ('PUT', capture.STORAGE_ROOT + '/b/bucket/o/name', False),
        ('PATCH', capture.STORAGE_ROOT + '/b/bucket/o/name', False),
        ('DELETE', capture.STORAGE_ROOT + '/b/bucket/o/name', False),
        ('GET', 'https://unapproved.invalid/', False),
    ],
)
def test_prod_operator_keeps_the_exact_read_only_transport(monkeypatch, method, url, allowed):
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    session = Session([response([])])
    transport = capture.ReadOnlyTransport(session)
    if allowed:
        transport.request(method, url)
        assert len(session.calls) == 1
    else:
        with pytest.raises(capture.ReadOnlyViolation):
            transport.request(method, url)
        assert session.calls == []


def test_derived_inventory_works_with_list_only_without_get_or_permission_probe(tmp_path):
    class ListOnlyDerived(OwnerStorage):
        def permissions(self, bucket):
            pytest.fail('capture must not require a permissions probe before listing')

        def inventory(self, bucket, prefix):
            # A real transport with only a listing response: any extra metadata
            # or object GET would exhaust the fake session and fail this item.
            session = Session([response({'items': [{'name': prefix + 'chunk', 'generation': '4', 'size': '12'}]})])
            rows = capture.ReadOnlyStorage(capture.ReadOnlyTransport(session)).inventory(bucket, prefix)
            assert session.calls[0][1].endswith('/b/' + bucket + '/o')
            assert len(session.calls) == 1
            return rows

        def ciphertext(self, bucket, name, generation):
            assert bucket == BUCKETS['BUCKET_BATCH_PIPELINE']
            return super().ciphertext(bucket, name, generation)

    summary = capture.capture_owner(OwnerDB(), ListOnlyDerived(), tmp_path, digest, UID, [CID], BUCKETS)
    assert summary['items'][0]['status'] == 'complete'
    corpus = json.loads((tmp_path / ('owner-' + digest(CID)) / 'corpus.json').read_text())
    assert {row['bucket'] for row in corpus['chunk_inventory']} == {'chunks', 'derived'}


def test_needed_derived_blob_is_missing_input_without_any_object_get(tmp_path):
    db, storage = OwnerDB(), OwnerStorage()
    db.artifact['uri'] = db.uri.replace('gs://batch/', 'gs://derived/')
    summary = capture.capture_owner(db, storage, tmp_path, digest, UID, [CID], BUCKETS)
    assert summary['items'][0]['status'] == 'partial'
    assert summary['items'][0]['exception_type'] == 'StorageReadDenied'
    assert all(call[1] != 'derived' for call in storage.calls if call[0] == 'ciphertext')
    case = tmp_path / ('owner-' + digest(CID))
    manifest = json.loads((case / 'manifest.json').read_text())
    assert manifest['prod_evidence']['missing_input'] == ['BUCKET_AUDIO_DERIVED']
    assert manifest['prod_evidence']['ciphertext_blobs'] == 1
    assert manifest['prod_evidence']['missing_blobs'] == 1


def test_denied_blob_records_bucket_only_and_keeps_other_blobs_and_items(tmp_path, capsys, caplog):
    class TwoArtifacts(OwnerDB):
        def query(self, collection, **kwargs):
            if collection.endswith('_artifacts'):
                return {
                    'denied': self.artifact,
                    'readable': {**self.artifact, 'uri': self.uri.replace('key.enc', 'other.enc')},
                }
            return super().query(collection, **kwargs)

    class DeniedOnce(OwnerStorage):
        def ciphertext(self, bucket, name, generation):
            if name.endswith('/key.enc'):
                # Exercise the real 403 classification, with an exception
                # message containing private data that must never be printed.
                transport = capture.ReadOnlyTransport(Session([response(status=403)]))
                transport.request('GET', capture.STORAGE_ROOT + '/b/' + bucket + '/o/' + name)
                pytest.fail('403 must raise')
            return self.ciphertext_bytes, generation or '124'

    selected = [CID, 'second-conversation']
    summary = capture.capture_owner(TwoArtifacts(), DeniedOnce(), tmp_path, digest, UID, selected, BUCKETS)
    assert [item['status'] for item in summary['items']] == ['partial', 'partial']
    assert [item['exception_type'] for item in summary['items']] == ['StorageReadDenied', 'StorageReadDenied']
    for cid in selected:
        case = tmp_path / ('owner-' + digest(cid))
        manifest = json.loads((case / 'manifest.json').read_text())
        evidence = manifest['prod_evidence']
        assert evidence['missing_input'] == ['BUCKET_BATCH_PIPELINE']
        assert evidence['capture_status'] == 'partial'
        assert evidence['ciphertext_blobs'] == evidence['missing_blobs'] == 1
        assert 'key.enc' not in json.dumps(manifest) and UID not in json.dumps(manifest)
        blobs = list((case / 'blobs').iterdir())
        assert len(blobs) == 1 and blobs[0].read_bytes() == OwnerStorage.ciphertext_bytes
    assert UID not in json.dumps(summary) + capsys.readouterr().out + caplog.text


@pytest.mark.parametrize(
    ('error_class', 'status'),
    [(RuntimeError, 'partial'), (CaptureRefused, 'refused'), (capture.ReadOnlyViolation, 'refused')],
)
def test_failed_item_does_not_abort_later_complete_item(tmp_path, error_class, status):
    class FailingFirst(OwnerDB):
        def read(self, paths):
            if any(path.endswith('/failed-conversation') for path in paths):
                raise error_class('private error ' + UID + ' gs://private/object')
            return super().read(paths)

    summary = capture.capture_owner(
        FailingFirst(), OwnerStorage(), tmp_path, digest, UID, ['failed-conversation', CID], BUCKETS
    )
    assert summary['items'] == [
        {'item': 'owner-' + digest('failed-conversation'), 'status': status, 'exception_type': error_class.__name__},
        {'item': 'owner-' + digest(CID), 'status': 'complete', 'exception_type': None},
    ]
    assert UID not in json.dumps(summary) and 'gs://' not in json.dumps(summary)
    if status == 'partial':
        case = tmp_path / ('owner-' + digest('failed-conversation'))
        manifest = json.loads((case / 'manifest.json').read_text())
        assert manifest['prod_evidence']['capture_status'] == 'partial'
        assert 'private error' not in (case / 'corpus.json').read_text()
    assert (tmp_path / ('owner-' + digest(CID)) / 'manifest.json').exists()


def test_missing_input_manifest_accepts_only_bucket_keys():
    for value in (
        ['gs://bucket/private-object'],
        [UID],
        ['BUCKET_AUDIO_DERIVED', 'BUCKET_AUDIO_DERIVED'],
        [{'bucket': 'BUCKET_AUDIO_DERIVED', 'object': 'secret'}],
    ):
        with pytest.raises(ValueError):
            manifest_stub('case', 'C', {'missing_input': value}, [])


@pytest.mark.parametrize('identity', ['ro-prod', 'prod-operator'])
@pytest.mark.parametrize('mode', ['S', 'check-access'])
def test_structure_and_access_admit_both_read_guarded_identities(tmp_path, monkeypatch, capsys, identity, mode):
    import google.auth
    from google.auth.transport import requests
    from contextlib import nullcontext

    monkeypatch.setenv('GCP_AGENT_TIER', identity)
    monkeypatch.setattr(google.auth, 'default', lambda **kwargs: (object(), 'synthetic-project'))
    monkeypatch.setattr(requests, 'AuthorizedSession', lambda credentials: nullcontext(object()))
    monkeypatch.setattr(capture, 'bucket_config', lambda: BUCKETS)
    if mode == 'check-access':
        monkeypatch.setattr(capture.ReadOnlyStorage, 'permissions', lambda self, bucket: set())
        args = ['--check-access']
    else:
        monkeypatch.setattr(capture.ReadOnlyFirestore, 'query', lambda self, *args, **kwargs: {})
        args = ['--tier', 'S', '--output', str(tmp_path / 'output')]
    assert capture.main(args) == 0
    assert 'capture requires explicit' not in capsys.readouterr().out


class NullOutboxOwnerDB(OwnerDB):
    def __init__(self, outbox):
        super().__init__()
        self.outbox = outbox

    def read(self, paths):
        docs = super().read(paths)
        path = 'sync_reprocess_outbox/' + hashlib.sha256(f'{UID}\0{CID}'.encode()).hexdigest()
        if path in docs:
            docs[path] = self.outbox
        return docs


def test_outbox_with_null_uid_is_owned_by_its_derived_document_id(tmp_path):
    db = NullOutboxOwnerDB({'uid': None, 'conversation_id': CID})
    result = capture.capture_owner(db, OwnerStorage(), tmp_path, digest, UID, [CID], BUCKETS)
    assert result['items'][0]['status'] == 'complete'


@pytest.mark.parametrize(
    'outbox', [{'uid': 'someone-else', 'conversation_id': CID}, {'uid': None, 'conversation_id': 'other'}]
)
def test_outbox_with_conflicting_identity_is_refused(tmp_path, outbox):
    result = capture.capture_owner(NullOutboxOwnerDB(outbox), OwnerStorage(), tmp_path, digest, UID, [CID], BUCKETS)
    assert result['items'][0] == {
        'item': 'owner-' + digest(CID),
        'status': 'refused',
        'exception_type': 'CaptureRefused',
    }


@pytest.mark.parametrize('nested_owner, status', [('someone-else', 'refused'), (UID, 'complete'), (None, 'complete')])
def test_job_projection_binding_owner_must_match_pinned_uid(tmp_path, nested_owner, status):
    db = OwnerDB()
    db.job = dict(db.job, projection_binding={'owner_id': nested_owner, 'conversation_id': CID})
    result = capture.capture_owner(db, OwnerStorage(), tmp_path, digest, UID, [CID], BUCKETS)
    assert result['items'][0]['status'] == status
    if status == 'refused':
        assert not (tmp_path / ('owner-' + digest(CID))).exists()
