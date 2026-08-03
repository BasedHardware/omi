"""Focused coverage for the dev-only live listen parity-pack seam."""

import json
import logging

from routers.listen.parity_capture import ListenParityCapture
from routers.listen.parity_telemetry import record_parity_capture_event


class _TelemetryCounter:
    def __init__(self):
        self.events = []

    def labels(self, **labels):
        self.events.append(labels)
        return self

    def inc(self):
        return None


def _capture_env(root):
    return {
        'OMI_ENV_STAGE': 'dev',
        'OMI_PARITY_PACK_CAPTURE': '1',
        'OMI_PARITY_PACK_ALLOWED_PRINCIPALS': 'allowed-firebase-uid',
        'OMI_PARITY_PACK_ROOT': str(root),
    }


def _request():
    return {
        'codec': 'pcm8',
        'sample_rate': 8000,
        'channels': 1,
        'language': 'en',
        'provider': 'parakeet',
        'model': 'parakeet_streaming',
    }


def test_listen_capture_persists_client_provider_and_inbound_events_for_allowed_uid(tmp_path):
    capture = ListenParityCapture.from_environ(
        principal_id='allowed-firebase-uid',
        session_id='runtime-session',
        provider='parakeet',
        model='parakeet_streaming',
        request=_request(),
        environ=_capture_env(tmp_path),
    )

    capture.observe_client_audio(b'client-audio')
    capture.observe_outbound_stt(b'provider-request')
    capture.observe_inbound_stt([{'text': 'synthetic transcript'}])
    capture.persist()

    cassette_files = list((tmp_path / 'cassettes').glob('*.json'))
    assert len(cassette_files) == 1
    cassette = json.loads(cassette_files[0].read_text())
    assert [event['direction'] for event in cassette['events']] == ['client', 'outbound', 'inbound']
    assert cassette['identity']['anon_session'] != 'allowed-firebase-uid'
    assert 'allowed-firebase-uid' not in cassette_files[0].read_text()
    assert cassette['request_fingerprint']['algorithm'] == 'sha256-canonical-redacted-v1'


def test_listen_capture_whitelist_miss_writes_no_cassette_bytes(tmp_path):
    capture = ListenParityCapture.from_environ(
        principal_id='not-allowlisted',
        session_id='runtime-session',
        provider='parakeet',
        model='parakeet_streaming',
        request=_request(),
        environ=_capture_env(tmp_path),
    )

    assert not capture.enabled
    capture.observe_client_audio(b'must-not-persist')
    capture.observe_outbound_stt(b'must-not-persist')
    capture.observe_inbound_stt([{'text': 'must-not-persist'}])
    capture.persist()
    assert not (tmp_path / 'cassettes').exists()


def test_listen_capture_emits_bounded_lifecycle_telemetry_without_principal(tmp_path, monkeypatch, caplog):
    from routers.listen import parity_telemetry

    counter = _TelemetryCounter()
    monkeypatch.setattr(parity_telemetry, 'OMI_PARITY_PACK_CAPTURE_EVENTS_TOTAL', counter)
    caplog.set_level(logging.INFO, logger='routers.listen.parity_telemetry')
    env = _capture_env(tmp_path)

    capture = ListenParityCapture.from_environ(
        principal_id='allowed-firebase-uid',
        session_id='runtime-session',
        provider='parakeet',
        model='parakeet_streaming',
        request=_request(),
        environ=env,
    )
    capture.persist()

    assert counter.events == [
        {'stage': 'listen', 'outcome': 'accepted', 'reason_class': 'none'},
        {'stage': 'allowlist', 'outcome': 'accepted', 'reason_class': 'allowed'},
        {'stage': 'initialize', 'outcome': 'succeeded', 'reason_class': 'none'},
        {'stage': 'persist', 'outcome': 'succeeded', 'reason_class': 'none'},
        {'stage': 'export', 'outcome': 'skipped', 'reason_class': 'target_unconfigured'},
    ]
    assert 'allowed-firebase-uid' not in caplog.text
    assert 'runtime-session' not in caplog.text


def test_listen_capture_telemetry_distinguishes_allowlist_reject_and_invalid_root(tmp_path, monkeypatch):
    from routers.listen import parity_telemetry

    counter = _TelemetryCounter()
    monkeypatch.setattr(parity_telemetry, 'OMI_PARITY_PACK_CAPTURE_EVENTS_TOTAL', counter)
    env = _capture_env(tmp_path)
    ListenParityCapture.from_environ(
        principal_id='not-allowlisted',
        session_id='runtime-session',
        provider='parakeet',
        model='parakeet_streaming',
        request=_request(),
        environ=env,
    )
    invalid_root = dict(env, OMI_PARITY_PACK_ROOT='relative')
    ListenParityCapture.from_environ(
        principal_id='allowed-firebase-uid',
        session_id='runtime-session',
        provider='parakeet',
        model='parakeet_streaming',
        request=_request(),
        environ=invalid_root,
    )

    assert {'stage': 'allowlist', 'outcome': 'rejected', 'reason_class': 'allowlist_miss'} in counter.events
    assert {'stage': 'initialize', 'outcome': 'failed', 'reason_class': 'root_invalid'} in counter.events


def test_parity_capture_telemetry_is_dev_only_and_normalizes_unknown_labels(monkeypatch):
    from routers.listen import parity_telemetry

    counter = _TelemetryCounter()
    monkeypatch.setattr(parity_telemetry, 'OMI_PARITY_PACK_CAPTURE_EVENTS_TOTAL', counter)
    record_parity_capture_event('user-stage', 'user-outcome', 'user-reason', environ={'OMI_ENV_STAGE': 'prod'})
    record_parity_capture_event('user-stage', 'user-outcome', 'user-reason', environ={'OMI_ENV_STAGE': 'dev'})

    assert counter.events == [{'stage': 'other', 'outcome': 'other', 'reason_class': 'other'}]


def test_listen_capture_requires_a_restricted_absolute_root(tmp_path):
    relative_env = _capture_env(tmp_path)
    relative_env['OMI_PARITY_PACK_ROOT'] = 'parity-pack'
    relative = ListenParityCapture.from_environ(
        principal_id='allowed-firebase-uid',
        session_id='runtime-session',
        provider='parakeet',
        model='parakeet_streaming',
        request=_request(),
        environ=relative_env,
    )
    assert not relative.enabled

    not_dev_env = _capture_env(tmp_path)
    not_dev_env['OMI_ENV_STAGE'] = 'prod'
    not_dev = ListenParityCapture.from_environ(
        principal_id='allowed-firebase-uid',
        session_id='runtime-session',
        provider='parakeet',
        model='parakeet_streaming',
        request=_request(),
        environ=not_dev_env,
    )
    assert not not_dev.enabled


def test_listen_capture_bounds_audio_and_snapshots_transcript_segments(tmp_path):
    capture = ListenParityCapture.from_environ(
        principal_id='allowed-firebase-uid',
        session_id='runtime-session',
        provider='parakeet',
        model='parakeet_streaming',
        request=_request(),
        environ=_capture_env(tmp_path),
    )
    segments = [{'text': 'provider callback', 'speaker': 'unknown'}]
    capture.observe_inbound_stt(segments)
    segments[0]['speaker'] = 'backend-enriched'
    capture.observe_client_audio(b'x' * (8 * 1024 * 1024 + 1))
    capture.observe_outbound_stt(b'must-be-dropped-after-limit')
    capture.persist()

    cassette = json.loads(next((tmp_path / 'cassettes').glob('*.json')).read_text())
    assert len(cassette['events']) == 1
    assert cassette['events'][0]['direction'] == 'inbound'
    assert cassette['events'][0]['payload']['segments'][0]['speaker'] == 'unknown'


def test_listen_capture_export_fail_open_when_gcs_upload_raises(tmp_path, monkeypatch):
    env = _capture_env(tmp_path)
    env['OMI_PARITY_PACK_GCS_URI'] = 'gs://based-hardware-dev-omi-parity-pack-v0/parity-pack/v0'

    def boom(*_args, **_kwargs):
        raise RuntimeError('gcs unavailable')

    monkeypatch.setattr(
        'routers.listen.parity_pack_export.export_cassette_file',
        boom,
    )

    capture = ListenParityCapture.from_environ(
        principal_id='allowed-firebase-uid',
        session_id='runtime-session',
        provider='parakeet',
        model='parakeet_streaming',
        request=_request(),
        environ=env,
    )
    capture.observe_client_audio(b'client-audio')
    # Must not raise even when export path fails hard.
    capture.persist()
    assert list((tmp_path / 'cassettes').glob('*.json'))


def test_export_target_resolves_uri_and_bucket_prefix():
    from routers.listen.parity_pack_export import resolve_export_target

    assert resolve_export_target(
        {'OMI_PARITY_PACK_GCS_URI': 'gs://based-hardware-dev-omi-parity-pack-v0/parity-pack/v0'}
    ) == ('based-hardware-dev-omi-parity-pack-v0', 'parity-pack/v0')
    assert resolve_export_target(
        {
            'OMI_PARITY_PACK_GCS_BUCKET': 'based-hardware-dev-omi-parity-pack-v0',
            'OMI_PARITY_PACK_GCS_PREFIX': 'parity-pack/v0',
        }
    ) == ('based-hardware-dev-omi-parity-pack-v0', 'parity-pack/v0')
    assert resolve_export_target({}) is None


def test_export_cassette_file_uploads_under_prefix_without_logging_object_path(tmp_path, monkeypatch, caplog):
    from routers.listen import parity_pack_export as export_mod
    from routers.listen import parity_telemetry

    cassette_dir = tmp_path / 'cassettes'
    cassette_dir.mkdir()
    cassette = cassette_dir / 'abc.json'
    cassette.write_text('{"ok":true}\n', encoding='utf-8')

    uploaded = {}

    class FakeBlob:
        def upload_from_filename(self, filename, content_type=None):
            uploaded['filename'] = filename
            uploaded['content_type'] = content_type

    class FakeBucket:
        def blob(self, name):
            uploaded['object'] = name
            return FakeBlob()

    class FakeClient:
        def bucket(self, name):
            uploaded['bucket'] = name
            return FakeBucket()

    counter = _TelemetryCounter()
    monkeypatch.setattr(parity_telemetry, 'OMI_PARITY_PACK_CAPTURE_EVENTS_TOTAL', counter)
    monkeypatch.setattr(export_mod, '_storage_client', lambda: FakeClient())
    caplog.set_level(logging.INFO)
    env = {
        'OMI_ENV_STAGE': 'dev',
        'OMI_PARITY_PACK_ROOT': str(tmp_path),
        'OMI_PARITY_PACK_GCS_URI': 'gs://based-hardware-dev-omi-parity-pack-v0/parity-pack/v0',
    }
    assert export_mod.export_cassette_file(cassette, environ=env) is True
    assert uploaded['bucket'] == 'based-hardware-dev-omi-parity-pack-v0'
    assert uploaded['object'] == 'parity-pack/v0/cassettes/abc.json'
    assert uploaded['filename'] == str(cassette)
    assert 'abc.json' not in caplog.text
    assert counter.events == [
        {'stage': 'export', 'outcome': 'attempted', 'reason_class': 'configured'},
        {'stage': 'export', 'outcome': 'succeeded', 'reason_class': 'none'},
    ]


def test_export_cassette_file_emits_attempt_and_bounded_failure(tmp_path, monkeypatch, caplog):
    from routers.listen import parity_pack_export as export_mod
    from routers.listen import parity_telemetry

    class FakeBlob:
        def upload_from_filename(self, *_args, **_kwargs):
            raise PermissionError('private detail must not be emitted')

    class FakeBucket:
        def blob(self, _name):
            return FakeBlob()

    class FakeClient:
        def bucket(self, _name):
            return FakeBucket()

    counter = _TelemetryCounter()
    monkeypatch.setattr(parity_telemetry, 'OMI_PARITY_PACK_CAPTURE_EVENTS_TOTAL', counter)
    monkeypatch.setattr(export_mod, '_storage_client', lambda: FakeClient())
    monkeypatch.setattr(export_mod, '_record_export_failure', lambda **_kwargs: None)
    caplog.set_level(logging.INFO)
    cassette_dir = tmp_path / 'cassettes'
    cassette_dir.mkdir()
    cassette = cassette_dir / 'abc.json'
    cassette.write_text('{"ok":true}\n', encoding='utf-8')
    env = dict(
        _capture_env(tmp_path),
        OMI_PARITY_PACK_GCS_URI='gs://based-hardware-dev-omi-parity-pack-v0/parity-pack/v0',
    )

    assert export_mod.export_cassette_file(cassette, environ=env) is False
    assert counter.events == [
        {'stage': 'export', 'outcome': 'attempted', 'reason_class': 'configured'},
        {'stage': 'export', 'outcome': 'failed', 'reason_class': 'upload_error'},
    ]
    assert 'private detail' not in caplog.text
