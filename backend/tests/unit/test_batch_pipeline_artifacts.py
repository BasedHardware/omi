"""Encrypted artifact boundary tests; synthetic identities and fake object IO."""

from dataclasses import replace
from types import SimpleNamespace

from cryptography.exceptions import InvalidTag
from google.api_core.exceptions import NotFound
import pytest

from utils.batch_pipeline.artifacts import (
    ArtifactStore,
    ProtectionContext,
    RESULT_LIMIT,
    UPLOAD_CHUNK_BYTES,
    UPLOAD_TIMEOUT,
    UPLOAD_RETRY,
)
from utils.batch_pipeline.contracts import Priority, WorkItem
from utils.batch_pipeline import upload_policy


class ObjectClient:
    def __init__(self):
        self.objects = {}
        self.uploads = 0
        self.downloads = 0
        self.after_upload = lambda: None
        self.after_download = lambda: None
        self.reported_size = None
        self.soft_delete_policy = SimpleNamespace(retention_duration_seconds=0)
        self.default_event_based_hold = False
        self.retention_period = None

    def reload(self, **kwargs):
        """Synthetic bucket metadata; blob metadata reload is separate below."""
        pass

    def bucket(self, name):
        return self

    def blob(self, name, generation=None):
        client = self

        class Blob:
            def __init__(self):
                self.generation = generation
                self.size = None

            def upload_from_file(self, stream, **kw):
                body = stream.read()
                assert kw['if_generation_match'] == 0
                assert kw['retry'] is UPLOAD_RETRY and kw['timeout'] == UPLOAD_TIMEOUT
                assert 'size' not in kw  # SDK must choose resumable even for small objects
                assert self.chunk_size == UPLOAD_CHUNK_BYTES and self.chunk_size % 262144 == 0
                assert name not in client.objects
                client.uploads += 1
                self.generation = client.uploads
                client.objects[name] = (self.generation, body)
                client.after_upload()

            def reload(self, **kw):
                if name not in client.objects:
                    raise NotFound('synthetic absent object')
                stored_generation, body = client.objects[name]
                self.generation = stored_generation
                if kw.get('if_generation_match', stored_generation) != stored_generation:
                    raise ValueError('generation mismatch')
                self.size = client.reported_size or len(body)

            def download_as_bytes(self, **kw):
                client.downloads += 1
                stored_generation, body = client.objects[name]
                assert stored_generation == kw['if_generation_match']
                client.after_download()
                return body

            def delete(self, **kw):
                assert kw['if_generation_match'] == client.objects[name][0]
                del client.objects[name]

        return Blob()


def item(**kwargs):
    return WorkItem(
        'synthetic-segment', 'synthetic-owner', 100.0, 'pending', 1.0, Priority.FRESH, privacy_generation=0, **kwargs
    )


def setup(level='enhanced'):
    client = ObjectClient()
    state = SimpleNamespace(context=ProtectionContext(level, 0), registered=[])
    store = ArtifactStore(
        client,
        bucket='synthetic-batch-bucket',
        namespace='batch_pipeline_test_artifacts',
        authorize=lambda i: state.context,
        key_for_owner=lambda uid: (b'a' if uid == 'synthetic-owner' else b'b') * 32,
        register_artifact=lambda *args: state.registered.append(args),
    )
    return store, client, state


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_audio_and_results_are_encrypted_generation_pinned_and_round_trip(level):
    store, client, state = setup(level)
    original = item()
    audio_uri = store.stage_audio(original, b'RIFF synthetic cleartext audio')
    staged = replace(original, audio_uri=audio_uri)
    result_uri = store.persist_result(staged, {'words': [{'word': 'synthetic-private-text'}]})
    assert '#1' in audio_uri and '#2' in result_uri and audio_uri != result_uri
    assert store.fetch_audio(staged) == b'RIFF synthetic cleartext audio'
    assert store.load_result(staged, result_uri) == {'words': [{'word': 'synthetic-private-text'}]}
    assert all(
        b'cleartext' not in body and b'synthetic-private-text' not in body for _, body in client.objects.values()
    )
    assert all('synthetic-owner' not in name for name in client.objects)
    assert len(state.registered) == 2
    assert state.registered[0][2] == 'audio' and state.registered[1][2] == 'results'
    assert all('#' not in args[1] for args in state.registered)  # reserved, create-only random names


def test_owner_segment_capture_and_source_are_authenticated():
    store, client, state = setup()
    original = item()
    staged = replace(original, audio_uri=store.stage_audio(original, b'audio'))
    result = store.persist_result(staged, {'words': []})
    with pytest.raises(ValueError):
        store.fetch_audio(replace(staged, owner_id='other-owner'))
    with pytest.raises(ValueError):
        store.load_result(replace(staged, segment_id='other-segment'), result)
    with pytest.raises(InvalidTag):
        store.fetch_audio(replace(staged, capture_at=101.0))
    with pytest.raises(InvalidTag):
        store.load_result(replace(staged, audio_uri=staged.audio_uri + '0'), result)
    name = next(iter(client.objects))
    gen, encrypted = client.objects[name]
    client.objects[name] = (gen, encrypted[:-1] + bytes([encrypted[-1] ^ 1]))
    with pytest.raises(InvalidTag):
        store.fetch_audio(staged)


def test_privacy_generation_or_level_change_cannot_read_old_payload():
    store, client, state = setup()
    original = item()
    staged = replace(original, audio_uri=store.stage_audio(original, b'audio'))
    state.context = ProtectionContext('standard', 0)
    with pytest.raises(InvalidTag):
        store.fetch_audio(staged)
    state.context = ProtectionContext('enhanced', 1)
    with pytest.raises(PermissionError):
        store.fetch_audio(staged)
    with pytest.raises(PermissionError):
        store.stage_audio(replace(original, privacy_generation=None), b'audio')


@pytest.mark.parametrize('level', ['e2ee', 'unknown', '', None])
def test_unsupported_protection_never_silently_downgrades(level):
    with pytest.raises(ValueError):
        ProtectionContext(level, 0)


def test_deletion_during_upload_removes_exact_object_and_returns_no_reference():
    store, client, state = setup()
    client.after_upload = lambda: setattr(state, 'context', ProtectionContext('enhanced', 1))
    with pytest.raises(PermissionError):
        store.stage_audio(item(), b'audio')
    assert client.objects == {} and client.uploads == 1 and len(state.registered) == 1


def test_deletion_during_download_returns_no_plaintext():
    store, client, state = setup()
    original = item()
    staged = replace(original, audio_uri=store.stage_audio(original, b'audio'))
    client.after_download = lambda: setattr(state, 'context', ProtectionContext('enhanced', 1))
    with pytest.raises(PermissionError):
        store.fetch_audio(staged)


def test_registration_precedes_upload_and_revocation_after_registration_prevents_io():
    store, client, state = setup()

    def register(*args):
        assert client.uploads == 0
        state.context = ProtectionContext('enhanced', 1)

    store.register_artifact = register
    with pytest.raises(PermissionError):
        store.stage_audio(item(), b'audio')
    assert client.uploads == 0


def test_no_arbitrary_urls_unversioned_objects_or_unbounded_downloads():
    store, client, state = setup()
    original = item()
    staged = replace(original, audio_uri=store.stage_audio(original, b'audio'))
    for uri in [
        'https://example.com/audio',
        staged.audio_uri.split('#')[0],
        staged.audio_uri + '?x=1',
        staged.audio_uri.replace('synthetic-batch-bucket', 'foreign-bucket'),
    ]:
        with pytest.raises(ValueError):
            store.fetch_audio(replace(staged, audio_uri=uri))
    assert client.downloads == 0
    client.reported_size = RESULT_LIMIT * 100
    with pytest.raises(ValueError, match='bounded'):
        store.fetch_audio(staged)
    assert client.downloads == 0


def test_invalid_result_json_fails_before_storage():
    store, client, state = setup()
    with pytest.raises(ValueError):
        store.persist_result(item(), {'words': float('nan')})
    assert not client.objects and not state.registered


def test_stale_registration_never_starts_upload(monkeypatch):
    import utils.batch_pipeline.artifacts as module

    store, client, state = setup()
    values = iter([0, 31])
    monkeypatch.setattr(module.time, 'monotonic', lambda: next(values))
    with pytest.raises(TimeoutError, match='too old'):
        store.stage_audio(item(), b'audio')
    assert client.uploads == 0 and len(state.registered) == 1


def test_slow_upload_stops_new_chunks_before_deletion_outbox_can_drop_the_name(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(upload_policy.time, 'monotonic', lambda: clock[0])
    stream = upload_policy.UploadStream(b'synthetic audio')
    assert stream.read(4) == b'synt'
    clock[0] = upload_policy.UPLOAD_STREAM_SECONDS
    with pytest.raises(TimeoutError, match='upload deadline'):
        stream.read(4)
    assert upload_policy.UPLOAD_PENDING_SECONDS > (
        upload_policy.UPLOAD_STREAM_SECONDS
        + upload_policy.UPLOAD_RETRY_SECONDS
        + sum(upload_policy.UPLOAD_TIMEOUT)
        + 30
    )


def test_recovery_upload_lost_reply_reconciles_same_encrypted_generation():
    store, client, state = setup()
    original = item()
    staged = replace(original, audio_uri=store.stage_audio(original, b'synthetic audio'))
    token = 'a' * 32
    assert store.find_recovery_result(staged, token) is None
    payload = {'words': [{'word': 'synthetic-private-text'}]}

    def lost_reply():
        raise TimeoutError('synthetic')

    client.after_upload = lost_reply
    with pytest.raises(TimeoutError):
        store.persist_recovery_result(staged, payload, token)
    uri = store.find_recovery_result(staged, token)
    assert uri.endswith(f'/{token}.enc#2')
    assert store.load_result(staged, uri) == payload
    assert client.uploads == 2  # one audio, one result; no reupload or new STT
    assert all(b'synthetic-private-text' not in body for _, body in client.objects.values())
    state.context = ProtectionContext('enhanced', 1)
    with pytest.raises(PermissionError):
        store.find_recovery_result(staged, token)
