"""Synthetic wrong-script soak regression across selection, intake and worker custody."""

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config.policy import BatchUnitPolicy

from config.prerecorded_language import language_class, language_guard_enabled
from config.prerecorded_stt import TranscriptionOutcome
from tests.unit.test_batch_pipeline_worker import item, setup_worker
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline.contracts import ValidationFailureWork
from utils.stt import pre_recorded as stt
from utils.stt.outcomes import TranscriptionFailure

CASES = json.loads(Path(__file__).with_name('fixtures').joinpath('batch_wrong_script.json').read_text())['cases']


@pytest.fixture(autouse=True)
def guard_default(monkeypatch):
    monkeypatch.delenv('STT_PRERECORDED_LANGUAGE_GUARD_ENABLED', raising=False)
    monkeypatch.setenv('STT_PRERECORDED_MODEL', 'parakeet,modulate-velma-2')


@pytest.mark.parametrize('value', [None, '', 'und', 'multi', 'unknown', ' MULTI ', 'und-US'])
def test_unknown_language_never_selects_parakeet(value, monkeypatch):
    for preference in ['parakeet', 'modulate-velma-2', 'parakeet,modulate-velma-2', 'retired-token']:
        monkeypatch.setenv('STT_PRERECORDED_MODEL', preference)
        assert stt.get_prerecorded_service(value) == ('modulate', 'multi', 'velma-2')


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['case_id'])
def test_soak_nonempty_latin_hypothesis_cannot_escape_the_guard(case, caplog):
    caplog.set_level(logging.INFO)
    worker, parakeet, saved, *_ = setup_worker(language_of=lambda _: case['intake_language'])
    # This recognizer would return the exact nonempty bad soak text. It must
    # never be called; output-script detection alone cannot catch Vietnamese.
    parakeet.transcribe_batch = Mock(
        return_value=[
            [
                {
                    'word': case['parakeet_observed'],
                    'timestamp': [0, 5],
                }
            ]
        ]
    )
    result = worker.process_batch([item(duration=6)])
    assert result == [ValidationFailureWork('a', 'vad_windows', 'unsupported_language')]
    parakeet.transcribe_batch.assert_not_called()
    assert saved == {}
    assert 'language_class=unknown route=blocked' in caplog.text
    assert case['expected'] not in caplog.text and case['parakeet_observed'] not in caplog.text


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['case_id'])
def test_soak_language_codes_use_multilingual_and_preserve_native_text(case, monkeypatch):
    assert stt.get_prerecorded_service(case['language'])[0] == 'modulate'
    provider = Mock()
    provider.transcribe_bytes.return_value = [{'text': case['expected'], 'timestamp': [0, 6]}]
    monkeypatch.setattr(stt, 'ModulatePrerecordedProvider', lambda: provider)
    forbidden = Mock(side_effect=AssertionError('unsafe recognizer selected'))
    monkeypatch.setattr(stt, 'ParakeetPrerecordedProvider', forbidden)
    result = stt.prerecorded_from_bytes(b'synthetic-pcm', language='und')
    assert result[0]['text'] == case['expected']
    forbidden.assert_not_called()


@pytest.mark.parametrize('language', ['en', 'fr', 'de', 'pt-BR', 'ru', 'el', 'uk'])
def test_named_supported_languages_keep_the_cheap_path(language):
    assert language_class(language) == 'supported'
    assert stt.get_prerecorded_service(language)[0] == 'parakeet'
    worker, _, saved, *_ = setup_worker(language_of=lambda _: language)
    assert worker.process_batch([item()])[0].outcome == 'success'
    assert saved['a']['words']


@pytest.mark.parametrize('language', [None, '', 'multi', 'vi', 'ja'])
def test_missing_or_unsupported_intake_metadata_fails_closed_without_recovery_adapter(language):
    worker, provider, saved, *_ = setup_worker(language_of=lambda _: language)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'vad_windows', 'unsupported_language')]
    assert not provider.calls and not saved


def test_language_metadata_failure_is_unknown():
    worker, provider, saved, *_ = setup_worker(language_of=Mock(side_effect=RuntimeError('private-error')))
    assert worker.process_batch([item()])[0].reason == 'unsupported_language'
    assert not provider.calls and not saved


def test_kill_value_restores_new_call_selection_but_cannot_revoke_worker_custody(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    for value in ['true', 'off', '0', 'typo', '']:
        monkeypatch.setenv('STT_PRERECORDED_LANGUAGE_GUARD_ENABLED', value)
        assert language_guard_enabled()
    monkeypatch.setenv('STT_PRERECORDED_LANGUAGE_GUARD_ENABLED', 'false')
    assert stt.get_prerecorded_service('multi')[0] == 'parakeet'
    worker, provider, saved, *_ = setup_worker(language_of=lambda _: 'multi')
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'vad_windows', 'unsupported_language')]
    assert not provider.calls and not saved
    assert 'language_class=unknown route=blocked' in caplog.text


def test_unavailable_multilingual_provider_never_falls_back_to_unsafe_parakeet(monkeypatch):
    monkeypatch.setattr(stt, 'provider_is_enabled', lambda provider, surface: provider == 'parakeet')
    with pytest.raises(TranscriptionFailure) as raised:
        stt.get_prerecorded_service('multi')
    assert raised.value.outcome == TranscriptionOutcome.CONFIG_ERROR


@pytest.mark.parametrize('proof', [None, 'declared', 'audio_lid'])
def test_gauntlet_worker_uses_real_frozen_language_adapter(monkeypatch, proof):
    from testing.sync_cloud_tasks_stack import batch_providers
    from utils.batch_pipeline.audio import audio_unit, with_context

    events = Mock()
    monkeypatch.setattr(batch_providers, 'write_event', events)
    body = audio_unit(100, b'\x01\x00' * 32000).wav
    context = {'stt_language': 'en'}
    if proof:
        context.update(stt_language_evidence=proof, stt_language_confidence=0.99)
    artifacts = SimpleNamespace(
        fetch_audio=lambda _: with_context(body, context), persist_result=Mock(return_value='r')
    )
    result = batch_providers.ModeRoutingWorker(artifacts).process_batch([item()])
    calls = [call for call in events.call_args_list if call.args[1]['event'] == 'words_started']
    if proof:
        assert result[0].outcome == 'success' and len(calls) == 1
    else:
        assert result == [ValidationFailureWork('a', 'vad_windows', 'unsupported_language')]
        assert not calls and not artifacts.persist_result.called


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'language,single,escapes',
    [(None, False, False), ('und', True, False), ('vi', True, True), ('en', False, False), ('en', True, False)],
)
async def test_new_batch_intake_routes_by_effective_sync_language(monkeypatch, language, single, escapes):
    from utils.batch_pipeline import intake
    from utils.batch_pipeline.artifacts import ProtectionContext

    store = MemoryStore()
    staged = Mock(side_effect=RuntimeError('stop after routing'))

    def authorize(store, seed, snapshots):
        snapshots['user'] = {'language': language, 'transcription_preferences': {'single_language_mode': single}}
        return ProtectionContext('standard', 0)

    monkeypatch.setattr(intake, 'FirestoreStore', lambda _: store)
    monkeypatch.setattr(intake, 'current_stage', lambda: 'dev')
    monkeypatch.setattr(intake, 'batch_artifact_authorize', authorize)
    monkeypatch.setattr(intake, 'artifacts_for', staged)
    result = await intake.accept_upload(
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
        policy=BatchUnitPolicy(batch_enabled=True, live_record_enabled=False),
    )
    assert (result is None) == escapes
    assert staged.call_count == (0 if escapes else 1)


@pytest.mark.asyncio
async def test_worker_guard_keeps_durable_custody_without_claiming_empty(monkeypatch):
    from utils.batch_pipeline.pump import Pump
    from utils.batch_pipeline.scheduler import Scheduler
    import time

    worker, provider, saved, *_ = setup_worker(language_of=lambda _: 'und')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    await Pump(queue, worker).run_once()
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined' and job['recovery_state'] == 'held'
    assert job['worker_failure'] == {'stage': 'vad_windows', 'reason': 'unsupported_language'}
    assert 'worker_empty_evidence' not in job
    assert not provider.calls and not saved
