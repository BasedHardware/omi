"""Focused coverage for the dev-only live listen parity-pack seam."""

import json

from routers.listen.parity_capture import ListenParityCapture


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
