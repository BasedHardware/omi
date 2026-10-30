"""Long-speech empty units in a language Parakeet lacks skip the padded Parakeet retry.

Staging (2026-10-20): 104/109 quarantined empties with >=5 s worker-VAD speech were
Vietnamese; repadding cannot make Parakeet TDT v3 transcribe a language it lacks.
"""

import logging
import time
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from diarizer.batch_pipeline import PipelineWorker
from diarizer.batch_pipeline_models import ParakeetWords, StagedAudio, stt_language
from utils.batch_pipeline import intake  # module level: its import cost stays outside the fast-unit call budget
from utils.batch_pipeline.audio import audio_unit, with_context
from utils.batch_pipeline.contracts import Priority, RecoveryWork, ValidationFailureWork, WorkItem
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.recovery_disposition import padded_empty, padded_skipped
from utils.batch_pipeline.scheduler import Scheduler
from tests.unit.test_batch_pipeline_scheduler import MemoryStore


@pytest.fixture(autouse=True)
def _recovery_route(monkeypatch):
    monkeypatch.setenv('BATCH_ADMISSION_LANGUAGE_EXCLUSION_ENABLED', 'false')
    # Rollback must still retain unsafe admitted audio before a model call.
    monkeypatch.setenv('STT_PRERECORDED_LANGUAGE_GUARD_ENABLED', 'false')
    # This suite pins the legacy GPU route; batch language eligibility is covered in its own suite.
    monkeypatch.setenv('BATCH_PIPELINE_LANGUAGE_ELIGIBILITY_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'false')
    monkeypatch.delenv('BATCH_PIPELINE_LONG_SPEECH_HANDOFF_ENABLED', raising=False)


def item(key='a', duration=10):
    return WorkItem(key, 'owner-' + key, 100, 'encrypted://' + key, duration, Priority.FRESH)


def worker(language, *, speech_seconds=None, recover=None):
    """A worker whose Parakeet returns nothing; intake recorded ``language``."""
    model = Mock()
    model.transcribe.side_effect = lambda arrays, **_: [
        SimpleNamespace(text='', timestamp={'word': []}) for _ in arrays
    ]
    provider = ParakeetWords(model)
    failures, saved = [], {}
    built = PipelineWorker(
        decode=lambda work: np.ones(int(work.duration_seconds * 16000), dtype=np.float32),
        vad=lambda s: [(0, speech_seconds if speech_seconds is not None else len(s) / 16000)],
        words_providers={'parakeet': provider},
        diarizers={'pyannote': lambda samples: {'turns': []}},
        persist=lambda work, payload: saved.__setitem__(work.segment_id, payload) or 'r://' + work.segment_id,
        on_failure=lambda i, e: failures.append((i.segment_id, e)),
        recover_words=recover or provider.recover_empty,
        language_of=lambda work: language,
        io_concurrency=1,
    )
    return built, model, failures, saved


@pytest.mark.asyncio
@pytest.mark.parametrize('language', ['vi', 'ja', 'multi', ''])
async def test_unsupported_or_unknown_language_is_held_before_either_attempt_even_on_rollback(language, caplog):
    built, model, failures, saved = worker(language)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), time.time())
    with caplog.at_level(logging.INFO):
        await Pump(queue, built).run_once()
    assert model.transcribe.call_count == 0
    assert not saved and failures == [('a', 'BatchValidationError')]
    assert 'language_class=' in caplog.text and 'route=blocked' in caplog.text
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined' and job['recovery_state'] == 'held'
    assert 'worker_empty_evidence' not in job
    assert not padded_skipped(job) and not padded_empty(job)
    direct = worker(language)[0].process_batch([item('b')])
    assert direct == [ValidationFailureWork('b', 'vad_windows', 'unsupported_language')]


@pytest.mark.parametrize(
    'language,speech_seconds,env',
    [
        ('en', None, {}),  # Parakeet language: the retry may recover it
        ('de', None, {}),
    ],
)
def test_retry_still_runs_otherwise(monkeypatch, language, speech_seconds, env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    built, model, _, _ = worker(language, speech_seconds=speech_seconds)
    results = built.process_batch([item('a')])
    assert model.transcribe.call_count == 2  # first pass + padded retry
    assert results == [RecoveryWork('a', padded_retry='empty')]


def test_no_recovery_route_keeps_the_retry(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    # Without the RecoveryWork handoff the retry is the only remaining attempt.
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'false')
    built, model, _, _ = worker('en')
    results = built.process_batch([item('a')])
    assert model.transcribe.call_count == 2
    assert results == [ValidationFailureWork('a', 'assemble_words', 'empty_asr')]


def test_partial_first_pass_words_keep_the_retry():
    # no_owned_words: Parakeet produced words, so the unit may be in its language.
    from diarizer.batch_pipeline import long_speech_handoff

    state = {'stt_language': 'vi', 'speech_seconds': 30.0}
    assert long_speech_handoff(state, 'empty_asr')
    assert not long_speech_handoff(state, 'no_owned_words')


def staged(context):
    return with_context(audio_unit(100, b'\x00\x00' * 16000).wav, context)


def test_staged_audio_reads_the_intake_language():
    for context, expected in (
        ({'source': 'omi', 'stt_language': 'vi'}, 'vi'),
        ({'source': 'omi', 'stt_language': ''}, ''),
        ({'source': 'omi'}, None),  # staged before intake recorded a language
        ({'source': 'omi', 'stt_language': 7}, None),
    ):
        source = StagedAudio(lambda work, body=staged(context): body)
        work = item('a', duration=1)
        source.decode(work)
        assert source.language(work) == expected
        assert source.language(work) is None  # popped once
    plain = StagedAudio(lambda work: audio_unit(100, b'\x00\x00' * 16000).wav)  # no context chunk
    plain.decode(item('a', duration=1))
    assert plain.language(item('a', duration=1)) is None
    assert stt_language(None) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'inherit,user_language,expected',
    [
        (True, 'vi', 'vi'),
        (True, 'pt-BR', 'pt'),
        (True, None, 'multi'),
        (False, 'vi', 'vi'),
        (False, 'pt-BR', 'pt'),
        (False, None, ''),
    ],
)
async def test_intake_freezes_the_resolved_stt_language(monkeypatch, inherit, user_language, expected):
    from utils.batch_pipeline.artifacts import ProtectionContext
    from utils.batch_pipeline.audio import read_context

    monkeypatch.setenv('BATCH_PIPELINE_LANGUAGE_INHERITANCE_ENABLED', 'true' if inherit else 'false')
    store = MemoryStore()
    frozen = []

    class Captured(Exception):
        pass

    def authorize(store_, seed, snapshots):
        snapshots['user'] = {'language': user_language} if user_language else {}
        snapshots['user']['transcription_preferences'] = {'single_language_mode': True}
        return ProtectionContext('standard', 0)

    def stage_audio(work, body):
        frozen.append(read_context(body))
        raise Captured

    monkeypatch.setattr(intake, 'FirestoreStore', lambda *a, **kw: store)
    monkeypatch.setattr(intake, 'current_stage', lambda: 'dev')
    monkeypatch.setattr(intake, 'batch_artifact_authorize', authorize)
    monkeypatch.setattr(
        intake, 'provider_config', lambda: SimpleNamespace(pool_kind='dedicated_batch', max_unit_seconds=600)
    )

    def decode_units(paths, max_seconds):
        yield audio_unit(100, b'\x00\x00' * 1600)

    monkeypatch.setattr(intake, 'decode_units', decode_units)
    monkeypatch.setattr(intake, 'artifacts_for', lambda store_: SimpleNamespace(stage_audio=stage_audio))
    from config.policy import BatchUnitPolicy

    # Integration: intake records the route with dataclasses.replace (contract (c)), so a real policy.
    policy = BatchUnitPolicy(batch_enabled=True, live_record_enabled=False)
    try:
        await intake.accept_upload(
            uid='synthetic-owner',
            job_id='job',
            content_id='content',
            paths=['a.bin'],
            lane='backfill',
            recording_age_seconds=60,
            source='omi',
            should_lock=False,
            conversation_id=None,
            client_device_id='pendant-1',
            client_platform='ios',
            intake_context={'stt_language': 'en'},  # caller context cannot override it
            policy=policy,
        )
    except Captured:
        pass
    assert len(frozen) == 1 and frozen[0]['stt_language'] == expected
