"""Serving intake wiring: non-affirmative speech units take the provider lane.

Driving ``accept_upload`` end to end with synthetic units proves the flip on
the admitted job row: a request whose unit plan proves speech the GPU words
engine can never serve stages with no compute admission and the closed
provider route, while silent and unmeasured units keep today's compute lane.
"""

import asyncio
import hashlib
import wave
from contextlib import contextmanager
from dataclasses import replace
from io import BytesIO
from types import SimpleNamespace

import pytest

from config.policy import BatchUnitPolicy
from tests.unit.fixtures.strict_firestore_transaction import (
    StrictFirestore,
    StrictFirestoreDocument,
    StrictFirestoreSnapshot,
)
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline import intake
from utils.batch_pipeline.artifacts import ProtectionContext
from utils.batch_pipeline.intake_outcome import IntakeRouteEvidence
from utils.sync.legacy_dark import LegacySyncMode

UID, CID = 'lane-uid', 'lane-conversation'
USER = ('users', UID)
CONVERSATION = (*USER, 'conversations', CID)
NAMESPACE = 'batch_pipeline_dev'


def unit_wav(seconds=2.0, frequency=440):
    import struct
    import math

    buffer = BytesIO()
    with wave.open(buffer, 'wb') as source:
        source.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        for index in range(int(seconds * 16000)):
            source.writeframesraw(struct.pack('<h', int(12000 * math.sin(2 * math.pi * frequency * index / 16000))))
    return buffer.getvalue()


class FakeUnit:
    def __init__(self, wav, duration=2.0, capture_at=1000.0):
        self.wav = wav
        self.duration_seconds = duration
        self.capture_at = capture_at
        self.coverage_runs = ()


@contextmanager
def intake_world(monkeypatch, decision, speech_windows='speech', conversation_language='multi', units=1):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BATCH_ADMISSION_LANGUAGE_EXCLUSION_ENABLED', 'false')
    monkeypatch.setattr(StrictFirestoreSnapshot, 'update_time', property(lambda self: 1), raising=False)
    user = {'language': 'en', 'transcription_preferences': {'single_language_mode': False}}
    conversation = {'language': conversation_language, '_test_revision': 1}
    client = StrictFirestore({USER: user, CONVERSATION: conversation})
    store = MemoryStore()
    store.client, store.namespace = client, NAMESPACE
    monkeypatch.setattr(intake, 'FirestoreStore', lambda *_: store)
    monkeypatch.setattr(intake, 'legacy_dark', SimpleNamespace(current_mode=lambda uid=None: LegacySyncMode.ON))
    monkeypatch.setattr(intake, 'language_inheritance_enabled', lambda: False)
    monkeypatch.setattr(
        intake,
        'batch_artifact_authorize',
        lambda store_, work, snapshots=None: (
            snapshots.__setitem__('user', dict(user)),
            snapshots.__setitem__('conversations', {CID: dict(conversation)}),
            ProtectionContext('standard', 0),
        )[-1],
    )

    def stage_audio(item, frozen):
        from database.batch_pipeline_staging import artifact_id

        uri = f'gs://synthetic-lane/{item.segment_id}.enc'

        def reserve(tx):
            tx.put(
                'artifacts',
                artifact_id(item.segment_id, uri),
                {'owner_id': item.owner_id, 'privacy_generation': item.privacy_generation, 'write_pending_until': 0},
            )

        store.run(reserve)
        return uri

    monkeypatch.setattr(intake, 'artifacts_for', lambda store_: SimpleNamespace(stage_audio=stage_audio))
    monkeypatch.setattr(intake, 'with_context', lambda wav, context: wav)
    monkeypatch.setattr(
        intake,
        'outbox_for',
        lambda kind: SimpleNamespace(enqueue=lambda *a, **k: SimpleNamespace(wake_token=''), wake=lambda *a, **k: None),
    )

    from utils.stt import batch_language

    monkeypatch.setattr(batch_language, 'resolve_language', lambda *a, **k: decision)
    if speech_windows == 'speech':
        monkeypatch.setattr(intake, '_speech_windows', lambda wav: [wav[:32]])
    elif speech_windows == 'silent':
        monkeypatch.setattr(intake, '_speech_windows', lambda wav: None)
    else:

        def broken(wav):
            raise RuntimeError('strict VAD unavailable')

        monkeypatch.setattr(intake, '_speech_windows', broken)

    def decode(max_seconds):
        for index in range(units):
            yield FakeUnit(unit_wav())

    yield store, decode


def run(coro):
    # pytest-asyncio may have closed the thread's current loop; own one instead.
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def submit(store, decode, monkeypatch, job='lane-job'):
    import asyncio

    policy = BatchUnitPolicy(batch_enabled=True, live_admission_enabled=True, live_record_enabled=False)
    from utils.batch_pipeline.capture_decode import decode_units

    result = run(
        intake.accept_upload(
            uid=UID,
            job_id=job,
            content_id='lane-content',
            paths=['/synthetic/one.bin'],
            lane='backfill',
            recording_age_seconds=0,
            source='omi',
            should_lock=False,
            conversation_id=CID,
            client_device_id=None,
            client_platform=None,
            policy=policy,
            decode=decode,
        )
    )
    return result


def admitted_job(store, content_id='lane-content', index=0):
    segment = hashlib.sha256(f'{content_id}:{index}'.encode()).hexdigest()
    return segment, store.rows.get(('jobs', segment))


def test_speech_with_a_detected_unsupported_code_admits_on_the_provider_lane(monkeypatch):
    from utils.stt.batch_language import LanguageDecision

    with intake_world(monkeypatch, LanguageDecision('ja', 0.95, 'audio_lid', 6.0)) as (store, decode):
        submit(store, decode, monkeypatch)
        segment, job = admitted_job(store)
        assert job is not None
        assert job['stt_route']['stt_route'] == 'provider'


def test_speech_with_a_detected_unsupported_code_names_the_unsupported_reason(monkeypatch):
    from utils.stt.batch_language import LanguageDecision

    with intake_world(monkeypatch, LanguageDecision('ja', 0.95, 'audio_lid', 6.0)) as (store, decode):
        submit(store, decode, monkeypatch)
        _, job = admitted_job(store)
        assert job['stt_route']['provider_reason'] == 'unsupported_language'


def test_speech_with_a_detected_unsupported_code_names_modulate(monkeypatch):
    from utils.stt.batch_language import LanguageDecision

    with intake_world(monkeypatch, LanguageDecision('ja', 0.95, 'audio_lid', 6.0)) as (store, decode):
        submit(store, decode, monkeypatch)
        _, job = admitted_job(store)
        assert job['stt_route']['provider_service'] == 'modulate'


def test_speech_with_a_detected_unsupported_code_stages_without_compute_admission(monkeypatch):
    from utils.stt.batch_language import LanguageDecision

    with intake_world(monkeypatch, LanguageDecision('ja', 0.95, 'audio_lid', 6.0)) as (store, decode):
        submit(store, decode, monkeypatch)
        _, job = admitted_job(store)
        assert job['requires_compute_admission'] is False


def test_speech_with_a_detected_unsupported_code_stamps_the_provider_policy(monkeypatch):
    from utils.stt.batch_language import LanguageDecision

    with intake_world(monkeypatch, LanguageDecision('ja', 0.95, 'audio_lid', 6.0)) as (store, decode):
        submit(store, decode, monkeypatch)
        _, job = admitted_job(store)
        assert job['policy']['stt_route'] == 'provider'
        assert job['policy']['provider_reason'] == 'unsupported_language'
        assert job['policy']['provider_service'] == 'modulate'


def test_speech_with_a_detected_unsupported_code_freezes_the_detected_code(monkeypatch):
    from utils.stt.batch_language import LanguageDecision

    with intake_world(monkeypatch, LanguageDecision('ja', 0.95, 'audio_lid', 6.0)) as (store, decode):
        seen = {}
        from database.batch_pipeline_staging import artifact_id

        def stage_audio(item, frozen):
            uri = f'gs://synthetic-lane/{item.segment_id}.enc'

            def reserve(tx):
                tx.put(
                    'artifacts',
                    artifact_id(item.segment_id, uri),
                    {
                        'owner_id': item.owner_id,
                        'privacy_generation': item.privacy_generation,
                        'write_pending_until': 0,
                    },
                )

            store.run(reserve)
            seen[item.segment_id] = frozen
            return uri

        monkeypatch.setattr(intake, 'artifacts_for', lambda store_: SimpleNamespace(stage_audio=stage_audio))
        submit(store, decode, monkeypatch)
        segment, _ = admitted_job(store)
        intake_row = store.rows[('intakes', 'bp_lane-job')]
        assert intake_row['repair_languages'][segment]['stt_language'] == 'ja'


def test_unknown_low_confidence_speech_admits_on_the_provider_lane(monkeypatch):
    from utils.stt.batch_language import LanguageDecision

    with intake_world(monkeypatch, LanguageDecision('en', 0.5, 'audio_lid', 6.0)) as (store, decode):
        submit(store, decode, monkeypatch)
        _, job = admitted_job(store)
        assert job['stt_route']['stt_route'] == 'provider'


def test_unknown_low_confidence_speech_stages_without_compute_admission(monkeypatch):
    from utils.stt.batch_language import LanguageDecision

    with intake_world(monkeypatch, LanguageDecision('en', 0.5, 'audio_lid', 6.0)) as (store, decode):
        submit(store, decode, monkeypatch)
        _, job = admitted_job(store)
        assert job['requires_compute_admission'] is False


def test_unavailable_detection_with_strict_speech_admits_on_the_provider_lane(monkeypatch):
    from utils.stt.batch_language import LanguageDecision

    with intake_world(monkeypatch, LanguageDecision('und', 0.0, 'unavailable')) as (store, decode):
        submit(store, decode, monkeypatch)
        _, job = admitted_job(store)
        assert job['stt_route']['stt_route'] == 'provider'


def test_silent_unknown_units_keep_the_compute_lane(monkeypatch):
    from utils.stt.batch_language import LanguageDecision

    with intake_world(monkeypatch, LanguageDecision('und', 0.0, 'unavailable'), speech_windows='silent') as (
        store,
        decode,
    ):
        submit(store, decode, monkeypatch)
        _, job = admitted_job(store)
        assert job['policy']['stt_route'] == 'parakeet'
        assert 'stt_route' not in job or job['stt_route']['stt_route'] == 'parakeet'


def test_silent_unknown_units_keep_compute_admission(monkeypatch):
    from utils.stt.batch_language import LanguageDecision

    with intake_world(monkeypatch, LanguageDecision('und', 0.0, 'unavailable'), speech_windows='silent') as (
        store,
        decode,
    ):
        submit(store, decode, monkeypatch)
        _, job = admitted_job(store)
        assert job['requires_compute_admission'] is True


def test_silent_unknown_units_keep_the_legacy_freeze(monkeypatch):
    from utils.stt.batch_language import LanguageDecision

    with intake_world(monkeypatch, LanguageDecision('und', 0.0, 'unavailable'), speech_windows='silent') as (
        store,
        decode,
    ):
        seen = {}
        from database.batch_pipeline_staging import artifact_id

        def stage_audio(item, frozen):
            uri = f'gs://synthetic-lane/{item.segment_id}.enc'

            def reserve(tx):
                tx.put(
                    'artifacts',
                    artifact_id(item.segment_id, uri),
                    {
                        'owner_id': item.owner_id,
                        'privacy_generation': item.privacy_generation,
                        'write_pending_until': 0,
                    },
                )

            store.run(reserve)
            seen[item.segment_id] = frozen
            return uri

        monkeypatch.setattr(intake, 'artifacts_for', lambda store_: SimpleNamespace(stage_audio=stage_audio))
        submit(store, decode, monkeypatch)
        segment, _ = admitted_job(store)
        intake_row = store.rows[('intakes', 'bp_lane-job')]
        assert intake_row['repair_languages'][segment]['stt_language'] == 'und'


def test_unmeasured_strict_vad_keeps_the_compute_lane(monkeypatch):
    from utils.stt.batch_language import LanguageDecision

    with intake_world(monkeypatch, LanguageDecision('und', 0.0, 'unavailable'), speech_windows='broken') as (
        store,
        decode,
    ):
        submit(store, decode, monkeypatch)
        _, job = admitted_job(store)
        assert job['policy']['stt_route'] == 'parakeet'
        assert 'stt_route' not in job or job['stt_route']['stt_route'] == 'parakeet'


def test_unmeasured_strict_vad_never_turns_into_a_paid_lane(monkeypatch):
    from utils.stt.batch_language import LanguageDecision

    with intake_world(monkeypatch, LanguageDecision('ja', 0.95, 'audio_lid', 6.0), speech_windows='broken') as (
        store,
        decode,
    ):
        submit(store, decode, monkeypatch)
        _, job = admitted_job(store)
        assert job['policy']['provider_service'] == 'none'
        assert 'stt_route' not in job or job['stt_route']['stt_route'] == 'parakeet'


def test_a_safe_decision_never_flips_even_with_strict_speech(monkeypatch):
    from utils.stt.batch_language import LanguageDecision

    with intake_world(monkeypatch, LanguageDecision('en', 0.95, 'audio_lid', 12.0)) as (store, decode):
        submit(store, decode, monkeypatch)
        _, job = admitted_job(store)
        assert job['policy']['stt_route'] == 'parakeet'
        assert 'stt_route' not in job or job['stt_route']['stt_route'] == 'parakeet'


def test_a_safe_decision_keeps_compute_admission(monkeypatch):
    from utils.stt.batch_language import LanguageDecision

    with intake_world(monkeypatch, LanguageDecision('en', 0.95, 'audio_lid', 12.0)) as (store, decode):
        submit(store, decode, monkeypatch)
        _, job = admitted_job(store)
        assert job['requires_compute_admission'] is True


def test_one_speech_unit_flips_a_multi_unit_request(monkeypatch):
    from utils.stt.batch_language import LanguageDecision

    decisions = [LanguageDecision('en', 0.95, 'audio_lid', 12.0), LanguageDecision('ja', 0.95, 'audio_lid', 6.0)]
    calls = []

    def decide(*args, **kwargs):
        index = min(len(calls), len(decisions) - 1)
        calls.append(index)
        return decisions[index]

    with intake_world(monkeypatch, None, units=2) as (store, decode):
        from utils.stt import batch_language

        monkeypatch.setattr(batch_language, 'resolve_language', decide)
        submit(store, decode, monkeypatch)
        _, first = admitted_job(store, index=0)
        _, second = admitted_job(store, index=1)
        assert first['stt_route']['stt_route'] == 'provider'
        assert second['stt_route']['stt_route'] == 'provider'


def test_flip_units_all_stage_without_compute_admission(monkeypatch):
    from utils.stt.batch_language import LanguageDecision

    with intake_world(monkeypatch, LanguageDecision('ja', 0.95, 'audio_lid', 6.0), units=2) as (store, decode):
        submit(store, decode, monkeypatch)
        _, first = admitted_job(store, index=0)
        _, second = admitted_job(store, index=1)
        assert first['requires_compute_admission'] is False
        assert second['requires_compute_admission'] is False


def test_flip_freeze_stays_per_unit(monkeypatch):
    from utils.stt.batch_language import LanguageDecision

    with intake_world(monkeypatch, LanguageDecision('ja', 0.95, 'audio_lid', 6.0), units=2) as (store, decode):
        seen = {}
        from database.batch_pipeline_staging import artifact_id

        def stage_audio(item, frozen):
            uri = f'gs://synthetic-lane/{item.segment_id}.enc'

            def reserve(tx):
                tx.put(
                    'artifacts',
                    artifact_id(item.segment_id, uri),
                    {
                        'owner_id': item.owner_id,
                        'privacy_generation': item.privacy_generation,
                        'write_pending_until': 0,
                    },
                )

            store.run(reserve)
            seen[item.segment_id] = frozen
            return uri

        monkeypatch.setattr(intake, 'artifacts_for', lambda store_: SimpleNamespace(stage_audio=stage_audio))
        submit(store, decode, monkeypatch)
        segment_zero, _ = admitted_job(store, index=0)
        segment_one, _ = admitted_job(store, index=1)
        intake_row = store.rows[('intakes', 'bp_lane-job')]
        assert intake_row['repair_languages'][segment_zero]['stt_language'] == 'ja'
        assert intake_row['repair_languages'][segment_one]['stt_language'] == 'ja'


def test_flip_jobs_still_carry_durable_intake_custody(monkeypatch):
    from utils.stt.batch_language import LanguageDecision

    with intake_world(monkeypatch, LanguageDecision('ja', 0.95, 'audio_lid', 6.0)) as (store, decode):
        submit(store, decode, monkeypatch)
        segment, job = admitted_job(store)
        assert job['owner_id'] == UID
        assert job['audio_uri'] == f'gs://synthetic-lane/{segment}.enc'
        assert job['state'] == 'provider_pending'


def test_flip_lands_an_outbox_row_intent_through_the_provider_enqueue_hook(monkeypatch):
    from utils.stt.batch_language import LanguageDecision

    enqueued = []

    def enqueue(*args, **kwargs):
        enqueued.append((args[0], args[1]))
        return SimpleNamespace(wake_token='')

    with intake_world(monkeypatch, LanguageDecision('ja', 0.95, 'audio_lid', 6.0)) as (store, decode):
        monkeypatch.setattr(
            intake,
            'outbox_for',
            lambda kind: SimpleNamespace(enqueue=enqueue, wake=lambda *a, **k: None),
        )
        submit(store, decode, monkeypatch)
        segment, _ = admitted_job(store)
        assert enqueued and enqueued[0][0] == segment


def test_compute_lane_admission_keeps_the_plain_gpu_path(monkeypatch):
    from utils.stt.batch_language import LanguageDecision

    with intake_world(monkeypatch, LanguageDecision('en', 0.95, 'audio_lid', 12.0)) as (store, decode):
        submit(store, decode, monkeypatch)
        _, job = admitted_job(store)
        assert job['state'] == 'ready'
        assert job['policy']['provider_service'] == 'none'
        assert 'stt_route' not in job


def test_the_evidence_object_stays_unexcluded_for_a_provider_flip(monkeypatch):
    from utils.stt.batch_language import LanguageDecision

    evidence = IntakeRouteEvidence()
    with intake_world(monkeypatch, LanguageDecision('ja', 0.95, 'audio_lid', 6.0)) as (store, decode):
        policy = BatchUnitPolicy(batch_enabled=True, live_admission_enabled=True, live_record_enabled=False)
        run(
            intake.accept_upload(
                uid=UID,
                job_id='evidence-job',
                content_id='lane-content',
                paths=['/synthetic/one.bin'],
                lane='backfill',
                recording_age_seconds=0,
                source='omi',
                should_lock=False,
                conversation_id=CID,
                client_device_id=None,
                client_platform=None,
                policy=policy,
                decode=decode,
                evidence=evidence,
            )
        )
        assert evidence.language_excluded is False


def test_a_second_identical_request_is_answered_from_the_durable_receipt(monkeypatch):
    from utils.stt.batch_language import LanguageDecision

    with intake_world(monkeypatch, LanguageDecision('ja', 0.95, 'audio_lid', 6.0)) as (store, decode):
        first = submit(store, decode, monkeypatch, job='dup-job')
        assert first is not None
        store.rows.pop(('content', f'{UID}/lane-content'), None)
        store.rows['content', f'{UID}/lane-content'] = {
            'dispatch_protocol': 'batch_v1',
            'job_id': 'bp_dup-job',
            'status': 'processing',
        }
        second = submit(store, decode, monkeypatch, job='dup-job')
        assert second is not None


def test_a_flipped_desktop_record_never_takes_the_record_origin(monkeypatch):
    from utils.stt.batch_language import LanguageDecision

    with intake_world(monkeypatch, LanguageDecision('ja', 0.95, 'audio_lid', 6.0), conversation_language='en') as (
        store,
        decode,
    ):
        import asyncio

        policy = BatchUnitPolicy(batch_enabled=True, live_admission_enabled=True, live_record_enabled=True)
        run(
            intake.accept_upload(
                uid=UID,
                job_id='origin-job',
                content_id='lane-content',
                paths=['/synthetic/one.bin'],
                lane='backfill',
                recording_age_seconds=0,
                source='desktop',
                should_lock=False,
                conversation_id=CID,
                client_device_id='dev',
                client_platform='macos',
                policy=policy,
                decode=decode,
            )
        )
        segment, job = admitted_job(store)
        assert job['stt_route']['stt_route'] == 'provider'
        assert job['projection_binding']['record_origin'] is False
