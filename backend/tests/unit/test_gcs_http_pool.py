"""The shared GCS client's pool matches executor concurrency; the drain cap is bounded."""

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import storage

from utils.other import local_storage


@pytest.mark.parametrize('raw,expected', [(None, 128), ('64', 64), ('3', 10), ('9999', 512), ('bad', 128)])
def test_pool_size_setting_is_bounded(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv('GCS_HTTP_POOL_MAXSIZE', raising=False)
    else:
        monkeypatch.setenv('GCS_HTTP_POOL_MAXSIZE', raw)
    assert local_storage.gcs_http_pool_maxsize() == expected


def test_client_session_uses_the_sized_https_adapter(monkeypatch):
    monkeypatch.setenv('GCS_HTTP_POOL_MAXSIZE', '96')
    client = local_storage._size_http_pool(storage.Client(project='synthetic', credentials=AnonymousCredentials()))
    adapter = client._http.get_adapter('https://storage.googleapis.com/')
    assert adapter._pool_maxsize == 96


def test_pool_sizing_failure_keeps_the_client(caplog):
    class Broken:
        @property
        def _http(self):
            raise RuntimeError('synthetic')

    client = Broken()
    assert local_storage._size_http_pool(client) is client
    assert 'event=gcs_http_pool outcome=default exception_type=RuntimeError' in caplog.text


def test_a_non_default_adapter_is_kept():
    import requests.adapters

    class MutualTls(requests.adapters.HTTPAdapter):
        pass

    client = storage.Client(project='synthetic', credentials=AnonymousCredentials())
    keep = MutualTls()
    client._http.mount('https://', keep)
    local_storage._size_http_pool(client)
    assert client._http.get_adapter('https://storage.googleapis.com/') is keep


@pytest.fixture
def private_sync_readers():
    from utils.other import storage as storage_helpers
    from utils.other.audio_chunks import AudioChunkReadSession

    return storage_helpers, AudioChunkReadSession('synthetic', 'conversation')


def test_private_sync_gets_count_prepared_sdk_requests_and_restore_reader(monkeypatch, private_sync_readers):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from urllib.parse import parse_qs, urlsplit

    from requests import Response

    from utils.other import private_sync_get_metrics as usage

    storage_helpers, speaker_session = private_sync_readers
    client = storage.Client(project='synthetic', credentials=AnonymousCredentials())
    bucket = client.bucket('private-synthetic')
    counter = Mock()
    monkeypatch.setattr(usage, 'OBJECT_GETS', counter)
    monkeypatch.setenv('BUCKET_PRIVATE_CLOUD_SYNC', bucket.name)

    def respond(request, **kwargs):
        response = Response()
        response.request = request
        response.status_code = 200
        response._content_consumed = True
        if 'alt=media' in request.url:
            query = parse_qs(urlsplit(request.url).query)
            assert query['ifGenerationMatch'] == ['3']
            if 'audio-outbox' in request.url:
                assert query['ifMetagenerationMatch'] == ['2']
            assert 'generation' not in query
            response.raw = SimpleNamespace(headers={})
            response._content = b'payload'
            response.headers['Content-Length'] = '7'
        else:
            response._content = b'{"generation":"3","metageneration":"2","size":"7"}'
        return response

    monkeypatch.setattr(client._http, 'send', Mock(side_effect=respond))
    local_storage._configure_storage_transport(client)
    blob = bucket.blob('audio-outbox/synthetic/frame')
    with usage.object_get_reader(usage.Reader.PLAYBACK_INVENTORY):
        blob.reload(retry=None)
        newest = bucket.blob(blob.name)
        assert newest.download_as_bytes(if_generation_match=3, if_metageneration_match=2, retry=None) == b'payload'
        with pytest.raises(RuntimeError):
            with usage.object_get_reader(usage.Reader.BATCH_SOURCE):
                raise RuntimeError('synthetic')
        blob.reload(retry=None)
    list(bucket.list_blobs(retry=None))
    client.bucket('other-bucket').blob(blob.name).reload(retry=None)
    blob.reload(retry=None)
    playback_blob = bucket.blob('playback/synthetic/conversation/artifact.mp3')
    monkeypatch.setattr(storage_helpers, '_playback_artifact_blob', lambda *_: playback_blob)
    monkeypatch.setattr(storage_helpers, '_get_signed_url', lambda *_: 'https://example.invalid/playback')
    assert storage_helpers.get_playback_artifact_signed_url('synthetic', 'conversation', 'artifact')
    chunk_path = 'audio-chunks/synthetic/capture.pcm'
    speaker_session._chunks = [{'path': chunk_path, 'generation': 3, 'size': 7}]
    monkeypatch.setattr(storage_helpers, 'get_private_cloud_sync_bucket', lambda: bucket)

    def decode_downloaded(selected, path, *_args, **_kwargs):
        return selected.blob(path).download_as_bytes()

    monkeypatch.setattr(storage_helpers, 'download_and_decode_chunk_blob', decode_downloaded)
    assert speaker_session.fetch(chunk_path) == b'payload'
    assert [call.args for call in counter.labels.call_args_list] == [
        ('playback_inventory', 'metadata'),
        ('playback_inventory', 'payload'),
        ('playback_inventory', 'metadata'),
        ('other', 'metadata'),
        ('playback_media', 'metadata'),
        ('speaker_evidence', 'payload'),
    ]


def test_private_sync_counter_failure_does_not_mask_storage_result(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from utils.other import private_sync_get_metrics as usage

    result = object()
    send = Mock(return_value=result)
    session = SimpleNamespace(send=send)
    request = SimpleNamespace(
        method='GET', url='https://storage.googleapis.com/download/storage/v1/b/private-synthetic/o/obj?alt=media'
    )
    monkeypatch.setattr(usage, 'OBJECT_GETS', Mock(labels=Mock(side_effect=RuntimeError('synthetic'))))
    usage.instrument_storage_session(session, 'private-synthetic')
    assert session.send(request, timeout=3) is result
    send.assert_called_once_with(request, timeout=3)
