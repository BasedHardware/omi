"""Slice D vendor clients and LID-under-outage, on mock transports only (no vendor is called)."""

import asyncio
from io import BytesIO
from unittest.mock import Mock
import wave

import httpx
import pytest

from utils.batch_pipeline import provider_stt
from utils.batch_pipeline.contracts import Priority, WorkItem
from utils.observability.reasons import VendorAttemptOutcome
from utils.stt import batch_language as lid
from utils.stt import language_gate, soniox_batch
from utils.stt import modulate_batch, pre_recorded


def wav(seconds=5):
    output = BytesIO()
    with wave.open(output, 'wb') as writer:
        writer.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        writer.writeframes(b'\x01\x00' * int(seconds * 16000))
    return output.getvalue()


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    monkeypatch.setenv('MODULATE_API_KEY', 'synthetic-not-a-key')
    monkeypatch.setenv('SONIOX_API_KEY', 'synthetic-not-a-key')
    monkeypatch.setenv('STT_PRERECORDED_VENDOR_FAIL_FAST', 'false')
    monkeypatch.delenv('BATCH_VENDOR_FAILOVER_ENABLED', raising=False)


def modulate(handler):
    async def call():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await modulate_batch.modulate_batch_async(wav(), language='ja', client=client)

    return asyncio.run(call())


UTTERANCES = {
    'text': 'synthetic fixture',
    'duration_ms': 5000,
    'utterances': [{'text': 'synthetic fixture words', 'start_ms': 500, 'duration_ms': 900, 'language': 'ja-JP'}],
}


def test_velma_batch_async_posts_once_and_parses_like_the_sync_client():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        assert request.headers['x-api-key'] == 'synthetic-not-a-key'
        return httpx.Response(200, json=UTTERANCES)

    words, language = modulate(handler)
    assert calls == ['/api/velma-2-stt-batch'] and language == 'ja'
    assert words == [{'timestamp': [0.5, 1.4], 'speaker': 'SPEAKER_00', 'text': 'synthetic fixture words'}]
    assert (words, language) == pre_recorded.modulate_batch_words(UTTERANCES, True, 'ja')


@pytest.mark.parametrize(
    'status,body,kind',
    [
        (402, 'payment required', 'credit_refusal'),
        (429, 'Insufficient credits', 'credit_refusal'),
        (401, 'unauthorized', 'credit_refusal'),
        (429, 'concurrent request limit reached', 'rate_limited'),
        (500, 'internal', 'error_5xx'),
        (504, 'timeout', 'error_5xx'),
        (413, 'too large', 'error'),
    ],
)
def test_velma_batch_async_types_every_refusal_without_retry(status, body, kind):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status, text=body)

    with pytest.raises(modulate_batch.ModulateBatchError) as raised:
        modulate(handler)
    assert raised.value.kind == kind and raised.value.posted and len(calls) == 1
    assert 'synthetic' not in str(raised.value) and str(raised.value) == 'modulate_batch_failed'


@pytest.mark.parametrize(
    'handler,kind',
    [
        (lambda request: (_ for _ in ()).throw(httpx.ReadTimeout('synthetic')), 'timeout'),
        (lambda request: (_ for _ in ()).throw(httpx.ConnectError('synthetic')), 'error'),
        (lambda request: httpx.Response(200, json={'unexpected': True}), 'invalid_response'),
    ],
)
def test_velma_batch_async_types_transport_and_shape_failures(handler, kind):
    with pytest.raises(modulate_batch.ModulateBatchError) as raised:
        modulate(handler)
    assert raised.value.kind == kind


def soniox(handler, **kwargs):
    async def call():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await soniox_batch.transcribe_async(
                wav(), 5, client=client, semaphore=asyncio.Semaphore(4), failover=True, **kwargs
            )

    return asyncio.run(call())


FILE = '00000000-0000-4000-8000-000000000001'
TRANSCRIPTION = '00000000-0000-4000-8000-000000000002'


def soniox_handler(*, create_status=201, poll_status='completed', transcript=None):
    def handler(request):
        if request.method == 'DELETE':
            return httpx.Response(204)
        if request.url.path == '/v1/files':
            return httpx.Response(201, json={'id': FILE})
        if request.method == 'POST':
            if create_status != 201:
                return httpx.Response(create_status, text='organization_balance_exhausted')
            return httpx.Response(201, json={'id': TRANSCRIPTION, 'status': 'queued'})
        if request.url.path.endswith('/transcript'):
            return httpx.Response(
                200,
                json=transcript
                or {
                    'text': 'hi',
                    'tokens': [{'text': 'hi', 'start_ms': 500, 'end_ms': 900, 'is_final': True, 'language': 'ja'}],
                },
            )
        return httpx.Response(200, json={'status': poll_status})

    return handler


def test_soniox_failover_is_admitted_by_the_prerecorded_surface_not_the_recovery_budget(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED', 'false')
    words, language = soniox(soniox_handler(), sleep=lambda _: asyncio.sleep(0))
    assert words[0]['text'] == 'hi' and language == 'ja'
    with pytest.raises(soniox_batch.SonioxBatchError):
        soniox_batch.authorization(5)  # held recovery keeps its own opt-in budget
    with pytest.raises(soniox_batch.SonioxBatchError) as raised:
        soniox_batch.authorization(7201, failover=True)
    assert raised.value.kind == 'refused'


@pytest.mark.parametrize('status,kind', [(402, 'credit_refusal'), (429, 'rate_limited'), (503, 'error_5xx')])
def test_soniox_refusal_at_submission_is_typed_and_not_submitted(status, kind):
    with pytest.raises(soniox_batch.SonioxBatchError) as raised:
        soniox(soniox_handler(create_status=status))
    assert (raised.value.kind, raised.value.submitted) == (kind, False)


def test_soniox_failure_after_submission_counts_as_paid():
    with pytest.raises(soniox_batch.SonioxBatchError) as raised:
        soniox(soniox_handler(poll_status='error'), sleep=lambda _: asyncio.sleep(0))
    assert (raised.value.kind, raised.value.submitted) == ('error_5xx', True)


@pytest.mark.parametrize(
    'error,outcome',
    [
        (modulate_batch.ModulateBatchError('breaker_open'), VendorAttemptOutcome.RATE_LIMITED),
        (modulate_batch.ModulateBatchError('credit_refusal', posted=True), VendorAttemptOutcome.CREDIT_REFUSAL),
        (modulate_batch.ModulateBatchError('timeout', posted=True), VendorAttemptOutcome.TIMEOUT),
        (modulate_batch.ModulateBatchError('error_5xx', posted=True), VendorAttemptOutcome.ERROR_5XX),
        (modulate_batch.ModulateBatchError('invalid_response', posted=True), VendorAttemptOutcome.INVALID_RESPONSE),
    ],
)
def test_stage_transcribe_maps_typed_client_failures_onto_attempt_outcomes(monkeypatch, error, outcome):
    async def failing(*args, **kwargs):
        raise error

    monkeypatch.setattr(modulate_batch, 'modulate_batch_async', failing)
    item = WorkItem('p1', 'synthetic-owner', 10, 'gs://synthetic/audio/p1', 5.0, Priority.FRESH)
    inspected = (b'\0\0' * 16000 * 5, 5.0, [{'start': 0.5, 'end': 1.0}])
    with pytest.raises(provider_stt.VendorCallFailure) as raised:
        asyncio.run(provider_stt.transcribe_async(item, 'ja', inspected, service='modulate'))
    assert raised.value.outcome is outcome and provider_stt.attempt_outcome_for(raised.value) is outcome


def test_stage_transcribe_keeps_vendor_speaker_turns_discarded(monkeypatch):
    async def words(*args, **kwargs):
        return [{'text': 'synthetic', 'timestamp': [0.5, 1.0], 'speaker': 'SPEAKER_01'}], 'ja'

    monkeypatch.setattr(modulate_batch, 'modulate_batch_async', words)
    item = WorkItem('p1', 'synthetic-owner', 10, 'gs://synthetic/audio/p1', 5.0, Priority.FRESH)
    inspected = (b'\0\0' * 16000 * 5, 5.0, [{'start': 0.5, 'end': 1.0}])
    payload = asyncio.run(provider_stt.transcribe_async(item, 'ja', inspected, service='modulate'))
    assert payload['diarization'] == {'turns': []} and payload['words_provider'] == 'modulate'


# --- LID survives a Modulate outage --------------------------------------------------------------


def outage(monkeypatch, outcome='breaker_open'):
    monkeypatch.setattr(
        lid, '_detect', lambda audio, **kwargs: (lid.LanguageDecision('und', 0.0, 'unavailable'), outcome)
    )
    monkeypatch.setattr(language_gate, 'enforced_for', lambda *args: False)
    monkeypatch.setattr(lid, 'language_gate_shadow_enabled', lambda: False)


def self_verdict(monkeypatch, language='en', p_supported=0.99, seconds=6.0):
    detect = Mock(return_value=language_gate.SelfVerdict(language, 0.99, p_supported, seconds))
    monkeypatch.setattr(language_gate, 'self_detect', lambda probe, *, surface: detect(probe, surface))
    return detect


@pytest.mark.parametrize('outcome', sorted(lid.VENDOR_OUTAGE_OUTCOMES))
def test_vendor_lid_outage_uses_the_self_gate_verdict_under_its_floor(monkeypatch, outcome):
    outage(monkeypatch, outcome)
    detect = self_verdict(monkeypatch)
    authorize = Mock(return_value=True)
    decision = lid.resolve_language('multi', wav(6), surface='batch', before_self_probe=authorize)
    assert (decision.language, decision.evidence) == ('en', 'self_lid') and decision.parakeet_safe
    authorize.assert_called_once_with()
    assert detect.call_count == 1


@pytest.mark.parametrize('outcome', ['skipped', 'no_key', 'unsupported_format'])
def test_our_own_refusals_are_not_an_outage(monkeypatch, outcome):
    outage(monkeypatch, outcome)
    detect = self_verdict(monkeypatch)
    assert lid.resolve_language('multi', wav(6), surface='batch').language == 'und'
    detect.assert_not_called()


def test_an_unsafe_or_unauthorized_self_verdict_keeps_und(monkeypatch):
    outage(monkeypatch)
    self_verdict(monkeypatch, p_supported=0.2)
    assert lid.resolve_language('multi', wav(6), surface='batch').language == 'und'
    detect = self_verdict(monkeypatch)
    denied = lid.resolve_language('multi', wav(6), surface='batch', before_self_probe=lambda: False)
    assert denied.language == 'und'
    detect.assert_not_called()


def test_failover_kill_switch_restores_vendor_only_lid(monkeypatch):
    monkeypatch.setenv('BATCH_VENDOR_FAILOVER_ENABLED', 'false')
    outage(monkeypatch)
    detect = self_verdict(monkeypatch)
    assert lid.resolve_language('multi', wav(6), surface='batch').language == 'und'
    detect.assert_not_called()


def test_declared_language_never_probes(monkeypatch):
    outage(monkeypatch)
    detect = self_verdict(monkeypatch)
    decision = lid.resolve_language('ja', wav(6), surface='batch')
    assert (decision.language, decision.evidence) == ('ja', 'declared')
    detect.assert_not_called()
