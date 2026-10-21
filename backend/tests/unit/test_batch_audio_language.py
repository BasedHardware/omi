"""Independent audio classification drives routing; no text-derived language proof."""

from io import BytesIO
import wave
from unittest.mock import Mock

import pytest

from utils.stt import batch_language as lid
from utils.stt import pre_recorded as stt


def wav(seconds=6):
    output = BytesIO()
    with wave.open(output, 'wb') as writer:
        writer.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        writer.writeframes(b'\x01\x00' * int(seconds * 16000))
    return output.getvalue()


@pytest.fixture(autouse=True)
def defaults(monkeypatch):
    monkeypatch.delenv('STT_PRERECORDED_LANGUAGE_GUARD_ENABLED', raising=False)
    monkeypatch.setenv('STT_PRERECORDED_MODEL', 'parakeet,modulate-velma-2')
    monkeypatch.setenv('MODULATE_API_KEY', 'synthetic-not-a-key')


def detector(monkeypatch, code='en', confidence=0.99):
    client = Mock()
    client.post.return_value.json.return_value = {
        'predicted_language_code': code,
        'confidence': confidence,
        'duration_ms': 6000,
    }
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(lid.httpx, 'Client', Mock(return_value=client))
    return client


@pytest.mark.parametrize('code', ['en', 'es', 'fr', 'de', 'pt', 'ru', 'uk'])
def test_confident_supported_audio_keeps_parakeet_despite_unknown_setting(monkeypatch, code):
    client = detector(monkeypatch, code)
    parakeet = Mock()
    monkeypatch.setattr(stt, 'ParakeetPrerecordedProvider', lambda: parakeet)
    multilingual = Mock()
    monkeypatch.setattr(stt, 'ModulatePrerecordedProvider', multilingual)
    assert stt.prerecorded_from_bytes(wav(), language='multi') is parakeet.transcribe_bytes.return_value
    client.post.assert_called_once()
    multilingual.assert_not_called()


@pytest.mark.parametrize(
    'code,confidence',
    [('th', 0.99), ('ar', 0.99), ('hi', 0.99), ('ja', 0.99), ('ko', 0.99), ('zh', 0.99), ('vi', 0.99), ('en', 0.79)],
)
def test_soak_audio_detections_and_low_confidence_use_multilingual(monkeypatch, code, confidence):
    detector(monkeypatch, code, confidence)
    parakeet = Mock()
    monkeypatch.setattr(stt, 'ParakeetPrerecordedProvider', parakeet)
    multilingual = Mock()
    monkeypatch.setattr(stt, 'ModulatePrerecordedProvider', lambda: multilingual)
    assert stt.prerecorded_from_bytes(wav(), language='und') is multilingual.transcribe_bytes.return_value
    parakeet.assert_not_called()


def test_probe_payload_is_bounded_to_30_seconds(monkeypatch):
    client = detector(monkeypatch)
    decision = lid.resolve_language('multi', wav(65))
    assert decision.parakeet_safe
    body = client.post.call_args.kwargs['files']['upload_file'][1]
    with wave.open(BytesIO(body), 'rb') as source:
        assert source.getnframes() == 30 * 16000
    assert client.post.call_args.args == (lid.LID_URL,)
    assert client.post.call_args.kwargs['headers'] == {'X-API-Key': 'synthetic-not-a-key'}


@pytest.mark.parametrize(
    'code,confidence', [('en', float('nan')), ('en', True), ('en', 1.01), ('private-text', 0.99), ('', 0.99)]
)
def test_malformed_detector_response_is_never_language_proof(monkeypatch, code, confidence):
    detector(monkeypatch, code, confidence)
    result = lid.resolve_language('multi', wav())
    assert result.language == 'und' and not result.parakeet_safe


def test_detector_timeout_is_one_attempt_and_multilingual(monkeypatch, caplog):
    client = detector(monkeypatch)
    client.post.side_effect = TimeoutError('PRIVATE_PROVIDER_SENTINEL')
    result = lid.resolve_language('multi', wav())
    assert not result.parakeet_safe
    client.post.assert_called_once()
    assert 'PRIVATE_PROVIDER_SENTINEL' not in caplog.text


def test_no_probe_spend_after_cap_refusal(monkeypatch):
    client = detector(monkeypatch)
    before = lid.PROBE_SECONDS.labels('accepted')._value.get()
    assert not lid.resolve_language('multi', wav(), before_probe=lambda: False).parakeet_safe
    client.post.assert_not_called()
    assert lid.PROBE_SECONDS.labels('accepted')._value.get() == before


def test_named_language_and_kill_switch_do_not_probe(monkeypatch):
    client = detector(monkeypatch)
    assert lid.resolve_language('en', wav()).parakeet_safe
    monkeypatch.setenv('STT_PRERECORDED_LANGUAGE_GUARD_ENABLED', 'false')
    lid.resolve_language('multi', wav())
    client.post.assert_not_called()


def test_file_selector_accounts_for_the_provider_that_will_actually_run(monkeypatch, tmp_path):
    detector(monkeypatch, 'en')
    path = tmp_path / 'synthetic.wav'
    path.write_bytes(wav())
    assert lid.resolve_file('multi', path, selector=stt.get_prerecorded_service) == ('parakeet', 'en', 'parakeet')
    assert lid.resolve_file('multi', tmp_path / 'missing', selector=stt.get_prerecorded_service)[0] == 'modulate'


def test_route_metric_records_provider_ordering_after_supported_detection(monkeypatch, tmp_path):
    from utils.batch_pipeline.language_metrics import ROUTES

    detector(monkeypatch, 'en')
    monkeypatch.setenv('STT_PRERECORDED_MODEL', 'modulate-velma-2,parakeet')
    path = tmp_path / 'synthetic.wav'
    path.write_bytes(wav())
    actual = ROUTES.labels('prerecorded', 'supported', 'multilingual')._value
    cheap = ROUTES.labels('prerecorded', 'supported', 'parakeet')._value
    before, cheap_before = actual.get(), cheap.get()
    assert lid.resolve_file('multi', path, selector=stt.get_prerecorded_service)[0] == 'modulate'
    assert actual.get() == before + 1
    assert cheap.get() == cheap_before


def test_worker_language_proof_stays_required_after_rollback(monkeypatch):
    from diarizer.batch_pipeline_models import stt_language

    monkeypatch.setenv('STT_PRERECORDED_LANGUAGE_GUARD_ENABLED', 'false')
    assert stt_language({'stt_language': 'en'}) is None
    assert (
        stt_language({'stt_language': 'en', 'stt_language_evidence': 'audio_lid', 'stt_language_confidence': 0.5})
        is None
    )
    assert (
        stt_language({'stt_language': 'en', 'stt_language_evidence': 'audio_lid', 'stt_language_confidence': 0.99})
        == 'en'
    )


def test_old_primary_language_hint_cannot_impersonate_audio_detection():
    from diarizer.batch_pipeline_models import stt_language

    assert stt_language({'stt_language': 'en'}) is None
    assert (
        stt_language({'stt_language': 'en', 'stt_language_evidence': 'audio_lid', 'stt_language_confidence': 0.79})
        is None
    )
    assert (
        stt_language({'stt_language': 'en', 'stt_language_evidence': 'audio_lid', 'stt_language_confidence': 0.99})
        == 'en'
    )


def test_language_metrics_survive_the_actual_sync_export_allowlist():
    import re
    from pathlib import Path
    import yaml
    from utils.batch_pipeline.language_metrics import ROUTES

    source = Path(__file__).parents[3] / 'backend/deploy/cloud_run_gmp_sync.yaml'
    relabeling = yaml.safe_load(source.read_text())['spec']['endpoints'][0]['metricRelabeling']
    keep = next(rule['regex'] for rule in relabeling if rule['action'] == 'keep')
    for collector in (ROUTES, lid.DETECTIONS, lid.PROBE_SECONDS):
        assert re.fullmatch(keep, collector._name + '_total')


@pytest.mark.asyncio
@pytest.mark.parametrize('code,confidence,frozen', [('en', 0.99, 'en'), ('vi', 0.99, 'vi'), ('en', 0.5, 'und')])
async def test_cpu_intake_freezes_detection_proof_instead_of_primary_setting(monkeypatch, code, confidence, frozen):
    from types import SimpleNamespace
    from utils.batch_pipeline import intake
    from utils.batch_pipeline.audio import audio_unit, read_context
    from utils.batch_pipeline.artifacts import ProtectionContext
    from tests.unit.test_batch_pipeline_scheduler import MemoryStore

    detector(monkeypatch, code, confidence)
    captured = []

    def authorize(store, seed, snapshots):
        snapshots['user'] = {'language': 'en', 'transcription_preferences': {'single_language_mode': False}}
        return ProtectionContext('standard', 0)

    def stage(work, body):
        captured.append(read_context(body))
        raise RuntimeError('stop after synthetic staging')

    def units(*args, **kwargs):
        yield audio_unit(100, b'\x01\x00' * 16000)

    monkeypatch.setattr(intake, 'FirestoreStore', lambda _: MemoryStore())
    monkeypatch.setattr(intake, 'current_stage', lambda: 'dev')
    monkeypatch.setattr(intake, 'batch_artifact_authorize', authorize)
    monkeypatch.setattr(intake, 'decode_units', units)
    monkeypatch.setattr(intake, 'artifacts_for', lambda _: SimpleNamespace(stage_audio=stage))
    response = await intake.accept_upload(
        uid='synthetic-owner',
        job_id='new',
        content_id='new',
        paths=[],
        lane='fresh',
        recording_age_seconds=0,
        source='omi',
        should_lock=False,
        conversation_id=None,
        client_device_id=None,
        client_platform='ios',
        policy=SimpleNamespace(batch_enabled=True, live_record_enabled=False),
    )
    assert response.status_code == 503
    assert captured[0]['stt_language'] == frozen
    assert captured[0]['stt_language_evidence'] == 'audio_lid'
    assert captured[0]['stt_language_confidence'] == confidence
