"""PL-049/050: lossless recovery and bound evidence on old/new job stores.

Use the production scheduler, recovery coordinator and intent protocol with the
shared sim/Firestore-emulator/Postgres matrix. Only audio inspection, vendor IO,
artifact IO and metering are synthetic; no real model, cloud or user data is used.
Run with OMI_REQUIRE_STORE_BACKENDS=all: skips cannot qualify migration parity.
Postgres uses the existing harness-only customer tables, not the serving A4 bridge.
"""

from __future__ import annotations

from dataclasses import asdict
import io
from unittest.mock import ANY, Mock, call
import wave

import pytest

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from testing.store_fixtures import store_backend  # noqa: F401
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem, WorkResult, vad_receipt
from utils.batch_pipeline import quarantine_recovery
from utils.batch_pipeline.recovery_disposition import MultilingualEmpty
from utils.batch_pipeline.scheduler import Scheduler
from utils.stt import local_vad

pytestmark = pytest.mark.integration
T0 = 1000.0
DURATION = 4


def synthetic_wav():
    output = io.BytesIO()
    with wave.open(output, 'wb') as handle:
        handle.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        handle.writeframes(b'\0' * (DURATION * 32000))
    return output.getvalue()


@pytest.fixture
def h(store_backend, monkeypatch):  # noqa: F811
    owner = store_backend.seed_user('recovery')
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_MODE', 'on')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_ALL_ADMITTED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST', owner)
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_TERMINAL_EMPTY_DISPOSITION_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_SPEECH_EMPTY_MULTILINGUAL_ENABLED', 'true')
    # Exercise the ship-on default against the legacy terminal disposition flag.
    monkeypatch.delenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', raising=False)
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setattr(quarantine_recovery, 'sync_allowed', lambda *_args, **_kwargs: True)
    monkeypatch.setattr(quarantine_recovery, 'metered', lambda *_args: None)
    return store_backend


def leased(h):
    item = WorkItem('speech', h.uid('recovery'), T0, 'gs://synthetic/input#17', DURATION, Priority.FRESH)
    scheduler = Scheduler(h.store)
    assert scheduler.enqueue(item, T0)
    (lease,) = scheduler.pull(T0)
    assert lease.item.segment_id == item.segment_id
    return item, scheduler, lease


def job(h):
    return h.store.run(lambda tx: tx.get('jobs', 'speech'))


def held_recovery(h, monkeypatch, *, speech=1.0):
    item, scheduler, lease = leased(h)
    assert scheduler.fail(
        item.segment_id,
        lease.token,
        T0 + 1,
        quarantine=True,
        padded_retry_empty=True,
        measured_held_vad_speech_seconds=speech,
    )
    binding = ProjectionBinding(item.owner_id, 'upload', 'content', (item.segment_id,))

    def bind(tx):
        current = tx.get('jobs', item.segment_id)
        tx.put('jobs', item.segment_id, {**current, 'projection_binding': asdict(binding)})
        tx.put(
            'content',
            f'{item.owner_id}/{binding.content_id}',
            {
                'dispatch_protocol': 'batch_v1',
                'status': 'processing',
                'job_id': binding.job_id,
                'batch_pipeline': {'protocol_version': 1, 'namespace': h.namespace, 'segment_ids': [item.segment_id]},
            },
        )

    h.store.run(bind)
    spans = [{'start': 0, 'end': speech}] if speech else []
    monkeypatch.setattr(local_vad, 'offline_pcm_speech_segments', lambda _: spans)
    artifacts = Mock()
    artifacts.fetch_audio.return_value = synthetic_wav()
    artifacts.find_recovery_result.return_value = None
    artifacts.persist_recovery_result.return_value = 'gs://synthetic/result#18'
    provider = Mock(side_effect=MultilingualEmpty(DURATION, spans))
    second = Mock(side_effect=AssertionError('no second provider is admitted'))
    recovery = quarantine_recovery.QuarantineRecovery(
        h.store,
        artifacts,
        stt=provider,
        second_stt=second,
        clock=lambda: T0 + 2,
    )
    return item, recovery, artifacts, provider, second


@pytest.mark.parametrize('speech', [0.46, 1.0, 3.9])
def test_pl049_positive_speech_empty_recovery_keeps_custody_and_spends_once(h, monkeypatch, speech):
    item, recovery, artifacts, provider, second = held_recovery(h, monkeypatch, speech=speech)
    assert recovery.recover(item.segment_id, item.owner_id) == 'failed_held'
    held = job(h)
    assert (held['state'], held['recovery_state']) == ('quarantined', 'failed_held')
    assert held['audio_uri'] == item.audio_uri
    assert held['capture_at'] == item.capture_at and held['duration_seconds'] == item.duration_seconds
    assert held['measured_held_vad_speech_seconds'] == speech
    assert held['recovery']['failure'] == {'stage': 'response_validation', 'reason': 'empty_asr'}
    assert held['recovery']['provider'] == 'modulate' and held['recovery']['started_at'] == T0 + 2
    assert not held.get('result') and not held['merge_pending']
    assert h.store.run(lambda tx: tx.get('results', item.segment_id)) == {}
    intent = dict(held['recovery'])
    for _ in range(2):
        assert recovery.recover(item.segment_id, item.owner_id) == 'held'
    assert job(h)['recovery'] == intent
    assert provider.call_count == artifacts.fetch_audio.call_count == 1
    artifacts.persist_recovery_result.assert_not_called()
    assert artifacts.method_calls == [call.fetch_audio(ANY)]
    second.assert_not_called()


def test_pl049_measured_silence_can_settle_without_paid_recovery(h, monkeypatch):
    item, recovery, artifacts, provider, second = held_recovery(h, monkeypatch, speech=0)
    assert recovery.recover(item.segment_id, item.owner_id) == 'recovered'
    assert job(h)['result']['outcome'] == 'silence'
    assert job(h)['audio_uri'] == item.audio_uri
    payload = artifacts.persist_recovery_result.call_args.args[1]
    assert payload['speech_seconds'] == 0 and payload['speech_spans'] == payload['words'] == []
    provider.assert_not_called()
    second.assert_not_called()


@pytest.mark.parametrize('speech', [None, 0.0, 1.25])
def test_pl050_only_current_lease_persists_unknown_or_measured_evidence(h, speech):
    item, scheduler, lease = leased(h)
    receipt = None if speech is None else vad_receipt(item.audio_uri, DURATION * 16000, speech)
    before = job(h)
    assert not scheduler.fail(
        item.segment_id,
        'foreign',
        T0 + 1,
        quarantine=True,
        measured_held_vad_speech_seconds=speech,
        worker_vad_receipt=receipt,
    )
    assert job(h) == before
    assert scheduler.fail(
        item.segment_id,
        lease.token,
        T0 + 2,
        quarantine=True,
        measured_held_vad_speech_seconds=speech,
        worker_vad_receipt=receipt,
    )
    held = job(h)
    assert 'measured_held_vad_speech_seconds' in held
    assert held['measured_held_vad_speech_seconds'] == speech
    assert held.get('worker_vad_receipt') == receipt
    assert held['audio_uri'] == item.audio_uri and held['recovery_state'] == 'held'
    assert not scheduler.complete(WorkResult(item.segment_id, 'gs://synthetic/stale'), lease.token, T0 + 3)
    assert job(h) == held


@pytest.mark.parametrize('change', ['foreign_input', 'zero_capture', 'speech_mismatch'])
def test_pl050_invalid_input_evidence_rolls_back_the_whole_transition(h, change):
    item, scheduler, lease = leased(h)
    receipt = vad_receipt(item.audio_uri, DURATION * 16000, 1.25)
    if change == 'foreign_input':
        receipt = vad_receipt('gs://synthetic/other#19', DURATION * 16000, 1.25)
    elif change == 'zero_capture':
        receipt['captured_samples'] = 0
    else:
        receipt['speech_samples'] += 16000
    before = job(h)
    with pytest.raises(ValueError, match='invalid bound VAD receipt'):
        scheduler.fail(
            item.segment_id,
            lease.token,
            T0 + 1,
            quarantine=True,
            measured_held_vad_speech_seconds=1.25,
            worker_vad_receipt=receipt,
        )
    assert job(h) == before
    assert scheduler.heartbeat(item.segment_id, lease.token, T0 + 2)


def test_pl050_privacy_fence_rejects_late_worker_evidence(h):
    item, scheduler, lease = leased(h)
    before = job(h)
    h.customer.block_privacy(item.owner_id)
    with pytest.raises(BatchPrivacyBlocked):
        scheduler.fail(
            item.segment_id,
            lease.token,
            T0 + 1,
            quarantine=True,
            measured_held_vad_speech_seconds=1.25,
            worker_vad_receipt=vad_receipt(item.audio_uri, DURATION * 16000, 1.25),
        )
    assert job(h) == before


def test_pl050_expired_lease_cannot_attach_evidence(h):
    item, scheduler, lease = leased(h)
    before = job(h)
    assert not scheduler.fail(
        item.segment_id,
        lease.token,
        lease.lease_until + 1,
        quarantine=True,
        measured_held_vad_speech_seconds=1.25,
        worker_vad_receipt=vad_receipt(item.audio_uri, DURATION * 16000, 1.25),
    )
    assert job(h) == before
