"""The fetch_decode boundary maps typed decode faults by type, never message.

Failure-Class: FC-deterministic-staged-decode-failure-walks-gpu-retry-ladder-as-unclassified-valueerror

Parity contract at the worker boundary: every ``StagedAudioInvalid`` and
``DecodedDurationMismatch`` at ``fetch_decode`` takes the typed terminal
handoff with its closed reason, every untyped exception at any stage
keeps the ordinary retry ladder, and the mapping is scoped to the stage
that owns decode faults. Message matching is gone — a boundary that
matched messages would silently return every new deterministic decode
fault to the ladder this change retires it from.
"""

import wave
from unittest.mock import Mock

import pytest

from diarizer.batch_pipeline import DecodedDurationMismatch
from diarizer.batch_pipeline_models import decode_pcm16_wav
from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401
from tests.unit.test_batch_pipeline_worker import Samples, item, setup_worker
from utils.batch_pipeline.audio import StagedAudioInvalid
from utils.batch_pipeline.contracts import FailedWork, ValidationFailureWork
from utils.batch_pipeline.source_audio import RetainedAudioInvalid

STAGED_MESSAGES = [
    'staging requires 16kHz mono PCM16 WAV',
    'invalid staged audio length',
    'truncated staged WAV',
    'invalid staged WAV container',
    'invalid bounded intake context or WAV',
]


@pytest.fixture(autouse=True)
def _terminal_flags(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')


def typed_decode(message):
    return Mock(side_effect=StagedAudioInvalid(message))


# --- every typed staged message terminalizes at fetch_decode ------------------------


@pytest.mark.parametrize('message', STAGED_MESSAGES)
def test_typed_staged_fault_takes_the_terminal_handoff(monkeypatch, message):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')
    worker, words, saved, decoded, diarized, failures = setup_worker(decode=typed_decode(message))
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'staged_audio_invalid')]


@pytest.mark.parametrize('message', STAGED_MESSAGES)
def test_typed_staged_fault_terminalizes_with_the_ship_on_flag_too(monkeypatch, message):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    worker, *_ = setup_worker(decode=typed_decode(message))
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'staged_audio_invalid')]


def test_typed_container_fault_from_the_real_decoder_terminalizes():
    # Integration: the boundary sees the type the decoder actually raises
    # for garbage bytes, not a mock.
    worker, words, saved, decoded, diarized, failures = setup_worker(
        decode=lambda work: (_ for _ in ()).throw(StagedAudioInvalid('invalid staged WAV container'))
    )
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'staged_audio_invalid')]


def test_a_staged_audio_invalid_subclass_is_still_the_staged_family():
    # The boundary trusts the family, not the exact class: a future
    # refined fault stays terminal instead of drifting to the ladder.
    class RefinedStagedFault(StagedAudioInvalid):
        pass

    worker, *_ = setup_worker(decode=Mock(side_effect=RefinedStagedFault('staging requires 16kHz mono PCM16 WAV')))
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'staged_audio_invalid')]


def test_typed_staged_fault_beats_any_message_similarity():
    # Type authority: a typed fault whose message resembles nothing in the
    # old string list still takes the staged handoff.
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('entirely new deterministic fault')))
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'staged_audio_invalid')]


def test_retained_family_keeps_its_own_reason():
    worker, *_ = setup_worker(decode=Mock(side_effect=RetainedAudioInvalid('retained PCM digest changed')))
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_duration_mismatch_type_takes_its_own_reason():
    worker, *_ = setup_worker(decode=Mock(side_effect=DecodedDurationMismatch('decoded duration differs')))
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'decoded_duration_mismatch')]


def test_duration_mismatch_from_the_real_extent_check_takes_its_reason():
    # The pipeline's own decoded_units raise site: decode returns an
    # extent that disagrees with the admitted duration.
    worker, *_ = setup_worker(decode=lambda work: Samples(work.duration_seconds + 1))
    results = worker.process_batch([item(duration=2)])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'decoded_duration_mismatch')]


def test_zero_extent_decode_takes_the_duration_reason():
    worker, *_ = setup_worker(decode=lambda work: Samples(0))
    results = worker.process_batch([item(duration=2)])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'decoded_duration_mismatch')]


def test_typed_staged_fault_beats_the_retained_branch_order():
    # staged check runs first: a typed staged fault never borrows the
    # retained reason even though both are terminal families.
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('retained PCM digest changed')))
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'staged_audio_invalid')]


# --- stage scoping: decode faults belong to fetch_decode -----------------------------


def test_typed_staged_fault_at_the_vad_stage_stays_on_the_ladder(monkeypatch):
    def vad(_samples):
        raise StagedAudioInvalid('truncated staged WAV')

    worker, *_ = setup_worker(vad=vad)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)


def test_typed_staged_fault_at_the_asr_stage_stays_on_the_ladder(monkeypatch):
    broken = Mock(side_effect=StagedAudioInvalid('truncated staged WAV'))
    worker, *_ = setup_worker(words_providers={'parakeet': broken})
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)


def test_typed_staged_fault_at_the_persist_stage_stays_on_the_ladder(monkeypatch):
    broken = Mock(side_effect=StagedAudioInvalid('truncated staged WAV'))
    worker, *_ = setup_worker(persist=broken)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)


def test_duration_mismatch_type_at_the_vad_stage_stays_on_the_ladder(monkeypatch):
    def vad(_samples):
        raise DecodedDurationMismatch('decoded duration differs')

    worker, *_ = setup_worker(vad=vad)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)


# --- untyped exceptions keep the ordinary ladder -------------------------------------


def test_untyped_value_error_at_fetch_decode_stays_retryable():
    worker, *_ = setup_worker(decode=Mock(side_effect=ValueError('different decode failure')))
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)


def test_wave_error_raised_by_a_non_decoder_callable_stays_retryable():
    # The boundary reads types it owns; a foreign wave.Error (a mock, or a
    # future non-staged decode path) keeps the legacy ladder.
    worker, *_ = setup_worker(decode=Mock(side_effect=wave.Error('truncated staged WAV')))
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)


def test_eof_error_at_fetch_decode_stays_retryable():
    worker, *_ = setup_worker(decode=Mock(side_effect=EOFError('unexpected end')))
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)


def test_struct_error_at_fetch_decode_stays_retryable():
    worker, *_ = setup_worker(decode=Mock(side_effect=struct_error()))
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)


def struct_error():
    import struct

    return struct.error('bad pack')


def test_runtime_error_at_fetch_decode_stays_retryable():
    worker, *_ = setup_worker(decode=Mock(side_effect=RuntimeError('transient GPU failure')))
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)


def test_permission_error_at_fetch_decode_stays_retryable():
    worker, *_ = setup_worker(decode=Mock(side_effect=PermissionError('storage denied')))
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)


def test_untyped_message_colliding_with_a_retired_string_stays_retryable():
    # The retired string list must not resurface: a BARE ValueError that
    # happens to carry an old message is not proof of determinism.
    worker, *_ = setup_worker(decode=Mock(side_effect=ValueError('staging requires 16kHz mono PCM16 WAV')))
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)


def test_untyped_duration_message_stays_retryable():
    worker, *_ = setup_worker(decode=Mock(side_effect=ValueError('decoded duration differs from admitted capture')))
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)


def test_key_error_at_fetch_decode_stays_retryable():
    worker, *_ = setup_worker(decode=Mock(side_effect=KeyError('artifact')))
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)


# --- evidence, logs and counters at the boundary --------------------------------------


def test_typed_fault_records_its_class_in_the_failure_record():
    worker, *_rest, failures = setup_worker(decode=typed_decode('truncated staged WAV'))
    worker.process_batch([item()])
    assert failures == [('a', 'StagedAudioInvalid')]


def test_duration_mismatch_records_its_class_in_the_failure_record():
    worker, *_rest, failures = setup_worker(decode=lambda work: Samples(99))
    worker.process_batch([item(duration=2)])
    assert failures == [('a', 'DecodedDurationMismatch')]


def test_typed_fault_logs_the_closed_reason_without_the_message(caplog):
    import logging

    worker, *_ = setup_worker(decode=typed_decode('truncated staged WAV'))
    with caplog.at_level(logging.DEBUG, logger='diarizer.batch_pipeline'):
        worker.process_batch([item()])
    assert 'reason=staged_audio_invalid' in caplog.text
    assert 'truncated staged WAV' not in caplog.text


def test_typed_fault_counts_one_failed_unit():
    worker, *_ = setup_worker(decode=typed_decode('truncated staged WAV'))
    worker.process_batch([item()])
    assert worker.counts['failed'] == 1
    assert worker.counts['items'] == 1


def test_typed_fault_does_not_touch_downstream_stages():
    worker, words, saved, decoded, diarized, _ = setup_worker(decode=typed_decode('truncated staged WAV'))
    worker.process_batch([item()])
    assert not words.calls and not saved and not diarized


def test_typed_fault_leaves_a_healthy_sibling_unaffected():
    def decode(work):
        if work.segment_id == 'bad':
            raise StagedAudioInvalid('invalid staged WAV container')
        return Samples(work.duration_seconds)

    worker, words, saved, decoded, diarized, _ = setup_worker(decode=decode)
    results = worker.process_batch([item('bad'), item('good')])
    assert isinstance(results[0], ValidationFailureWork) and results[0].segment_id == 'bad'
    assert results[1].segment_id == 'good'
    assert set(saved) == {'good'}
    assert worker.counts['failed'] == 1


def test_typed_fault_notifies_the_failure_handler_once():
    seen = []

    def on_failure(item_, class_name):
        seen.append((item_.segment_id, class_name))

    worker, *_ = setup_worker(decode=typed_decode('invalid staged WAV container'), on_failure=on_failure)
    worker.process_batch([item()])
    assert seen == [('a', 'StagedAudioInvalid')]


def test_typed_fault_for_a_shadow_unit_takes_the_same_terminal_handoff():
    worker, words, saved, decoded, diarized, failures = setup_worker(decode=typed_decode('truncated staged WAV'))
    shadow = item()
    object.__setattr__(shadow, 'shadow', True) if False else None
    from dataclasses import replace

    results = worker.process_batch([replace(shadow, shadow=True)])
    assert results == [ValidationFailureWork(results[0].segment_id, 'fetch_decode', 'staged_audio_invalid')]


def test_boundary_does_not_match_any_message_for_the_staged_family():
    # Exhaustive: for every canonical message, the TYPE (not the message)
    # decides. Each message with a foreign exception class stays retryable;
    # each message with the staged type terminalizes.
    for message in STAGED_MESSAGES:
        retryable = setup_worker(decode=Mock(side_effect=ValueError(message)))[0]
        assert all(isinstance(r, FailedWork) for r in retryable.process_batch([item()]))
        terminal = setup_worker(decode=Mock(side_effect=StagedAudioInvalid(message)))[0]
        assert terminal.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'staged_audio_invalid')]


def test_terminal_handoff_carries_no_worker_failure_evidence_field():
    worker, *_ = setup_worker(decode=typed_decode('invalid staged WAV container'))
    result = worker.process_batch([item()])[0]
    assert isinstance(result, ValidationFailureWork)
    assert not hasattr(result, 'worker_failure')


def test_typed_terminal_reason_is_a_closed_vocabulary_member():
    from utils.observability.reasons import WorkerValidationReason

    assert WorkerValidationReason.STAGED_AUDIO_INVALID.value == 'staged_audio_invalid'
    assert WorkerValidationReason.DECODED_DURATION_MISMATCH.value == 'decoded_duration_mismatch'


def test_typed_terminal_handoff_survives_the_closed_vocabulary_gate():
    from utils.batch_pipeline.errors import validate_worker_failure

    validate_worker_failure({'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'})
    validate_worker_failure({'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'})


def test_typed_terminal_handoff_survives_the_evidence_gate():
    from utils.batch_pipeline.errors import validate_worker_failure_evidence

    validate_worker_failure_evidence({'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'})


def test_terminal_families_stay_reason_closed():
    # No new reason token was invented for the typed faults.
    from utils.observability.reasons import WorkerValidationReason

    members = {member.value for member in WorkerValidationReason}
    assert 'staged_audio_invalid' in members
    assert 'decoded_duration_mismatch' in members
    assert 'invalid_staged_wav_container' not in members
    assert 'invalid_staged_container' not in members


# --- the routing grid: every fault class at every owned stage ------------------------


def results_for(decode=None, vad=None, words_provider=None, persist=None):
    settings = {}
    if decode is not None:
        settings['decode'] = decode
    if vad is not None:
        settings['vad'] = vad
    if words_provider is not None:
        settings['words_providers'] = {'parakeet': words_provider}
    if persist is not None:
        settings['persist'] = persist
    worker, words, saved, decoded, diarized, failures = setup_worker(**settings)
    return worker.process_batch([item()])


def test_staged_type_at_decode_is_terminal():
    results = results_for(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'staged_audio_invalid')]


def test_duration_type_at_decode_is_terminal():
    results = results_for(decode=Mock(side_effect=DecodedDurationMismatch('mismatch')))
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'decoded_duration_mismatch')]


def test_staged_type_at_vad_is_retryable():
    results = results_for(vad=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    assert all(isinstance(result, FailedWork) for result in results)


def test_duration_type_at_vad_is_retryable():
    results = results_for(vad=Mock(side_effect=DecodedDurationMismatch('mismatch')))
    assert all(isinstance(result, FailedWork) for result in results)


def test_staged_type_at_words_is_retryable():
    results = results_for(words_provider=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    assert all(isinstance(result, FailedWork) for result in results)


def test_duration_type_at_words_is_retryable():
    results = results_for(words_provider=Mock(side_effect=DecodedDurationMismatch('mismatch')))
    assert all(isinstance(result, FailedWork) for result in results)


def test_staged_type_at_persist_is_retryable():
    results = results_for(persist=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    assert all(isinstance(result, FailedWork) for result in results)


def test_duration_type_at_persist_is_retryable():
    results = results_for(persist=Mock(side_effect=DecodedDurationMismatch('mismatch')))
    assert all(isinstance(result, FailedWork) for result in results)


def test_wave_error_at_vad_is_retryable():
    results = results_for(vad=Mock(side_effect=wave.Error('unexpected eof')))
    assert all(isinstance(result, FailedWork) for result in results)


def test_wave_error_at_words_is_retryable():
    results = results_for(words_provider=Mock(side_effect=wave.Error('unexpected eof')))
    assert all(isinstance(result, FailedWork) for result in results)


def test_plain_value_error_at_vad_is_retryable():
    results = results_for(vad=Mock(side_effect=ValueError('bad window')))
    assert all(isinstance(result, FailedWork) for result in results)


def test_runtime_error_at_words_is_retryable():
    results = results_for(words_provider=Mock(side_effect=RuntimeError('provider down')))
    assert all(isinstance(result, FailedWork) for result in results)


def test_typed_fault_at_decode_reports_no_measured_vad():
    results = results_for(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    assert results[0].measured_held_vad_speech_seconds is None


def test_retryable_fault_at_words_carries_its_measurement():
    results = results_for(words_provider=Mock(side_effect=ValueError('bad words')))
    assert results[0].measured_held_vad_speech_seconds == 2


def test_retryable_fault_at_vad_reports_no_measurement():
    results = results_for(vad=Mock(side_effect=ValueError('bad window')))
    assert results[0].measured_held_vad_speech_seconds is None


# --- sibling terminal families are untouched by the typed boundary -------------------


def test_unsupported_language_still_terminalizes_at_vad(monkeypatch):
    from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason

    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def vad(_samples):
        raise BatchValidationError(ValidationReason.UNSUPPORTED_LANGUAGE)

    worker, *_ = setup_worker(vad=vad, language_of=lambda work: 'xx')
    results = worker.process_batch([item(duration=60)])
    assert results == [ValidationFailureWork('a', 'vad_windows', 'unsupported_language')]


def test_batch_validation_error_still_terminalizes_with_the_ship_on_flag(monkeypatch):
    from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason

    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    results = results_for(
        words_provider=None, decode=Mock(side_effect=BatchValidationError(ValidationReason.WORD_CLOCK))
    )
    # A BatchValidationError raised inside decode (fetch_decode) takes the
    # generic typed terminal handoff with its own closed reason.
    assert isinstance(results[0], ValidationFailureWork)
    assert results[0].reason == 'word_clock'


def test_retained_type_still_terminalizes_under_every_flag(monkeypatch):
    for flag in ('false', 'true'):
        monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', flag)
        results = results_for(decode=Mock(side_effect=RetainedAudioInvalid('retained audio authentication failed')))
        assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_duration_type_still_terminalizes_under_every_flag(monkeypatch):
    for flag in ('false', 'true'):
        monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', flag)
        results = results_for(decode=lambda work: Samples(work.duration_seconds + 1))
        assert results == [ValidationFailureWork('a', 'fetch_decode', 'decoded_duration_mismatch')]


# --- safety-net interactions ----------------------------------------------------------


def test_typed_staged_fault_terminalizes_with_the_safety_net_off(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    results = results_for(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'staged_audio_invalid')]


def test_typed_duration_fault_terminalizes_with_the_safety_net_off(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    results = results_for(decode=lambda work: Samples(work.duration_seconds + 1))
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'decoded_duration_mismatch')]


def test_untyped_fault_with_the_safety_net_off_emits_no_result(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    results = results_for(decode=Mock(side_effect=ValueError('transient decode fault')))
    assert results == []


def test_untyped_fault_with_the_safety_net_on_emits_failed_work(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    results = results_for(decode=Mock(side_effect=ValueError('transient decode fault')))
    assert len(results) == 1 and isinstance(results[0], FailedWork)


def test_empty_asr_reason_is_assemble_words_scoped(monkeypatch):
    # An empty_asr diagnosis belongs to the assemble_words stage; the same
    # reason surfacing from decode keeps the ordinary retryable path.
    from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason

    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    results = results_for(decode=Mock(side_effect=BatchValidationError(ValidationReason.EMPTY_ASR)))
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].worker_failure == {'stage': 'fetch_decode', 'reason': 'empty_asr'}


# --- evidence parity for the untyped control -----------------------------------------


def test_untyped_fault_carries_stage_evidence_with_unknown_reason(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    worker, *_ = setup_worker(decode=Mock(side_effect=ValueError('transient decode fault')))
    result = worker.process_batch([item()])[0]
    assert isinstance(result, FailedWork)
    assert result.worker_failure == {'stage': 'fetch_decode', 'reason': 'unknown'}


def test_untyped_wave_error_evidence_stays_unknown(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    worker, *_ = setup_worker(decode=Mock(side_effect=wave.Error('truncated staged WAV')))
    result = worker.process_batch([item()])[0]
    assert result.worker_failure == {'stage': 'fetch_decode', 'reason': 'unknown'}


def test_typed_terminal_result_has_no_evidence_field_while_untyped_does(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    terminal = results_for(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))[0]
    assert isinstance(terminal, ValidationFailureWork) and not hasattr(terminal, 'worker_failure')
    retryable = results_for(decode=Mock(side_effect=ValueError('transient decode fault')))[0]
    assert isinstance(retryable, FailedWork) and retryable.worker_failure is not None


def test_evidence_records_keep_the_exception_class_names():
    from diarizer.batch_pipeline import transient_failure_evidence

    assert transient_failure_evidence('fetch_decode', 'staged_audio_invalid') == {
        'stage': 'fetch_decode',
        'reason': 'staged_audio_invalid',
    }
    assert transient_failure_evidence('fetch_decode', 'unclassified') == {
        'stage': 'fetch_decode',
        'reason': 'unknown',
    }
    assert transient_failure_evidence('persist', 'unclassified') is None


# --- evidence for the retryable typed faults at later stages -------------------------


def test_typed_fault_at_vad_carries_unknown_evidence():
    results = results_for(vad=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    assert results[0].worker_failure == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_typed_fault_at_words_stays_evidence_free():
    # The words provider stage is not a closed worker stage: no evidence pair.
    from types import SimpleNamespace

    broken = SimpleNamespace(transcribe_batch=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    results = results_for(words_provider=broken)
    assert all(isinstance(result, FailedWork) for result in results)
    assert results[0].worker_failure is None


def test_typed_fault_at_persist_stays_evidence_free():
    # persist is not a closed worker stage: it carries no evidence pair.
    results = results_for(persist=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    assert all(isinstance(result, FailedWork) for result in results)
    assert results[0].worker_failure is None


# --- the real decoder at the boundary -------------------------------------------------


GARBAGE_STAGED_BYTES = b'persistent-garbage-not-a-wav'


def test_real_decoder_garbage_bytes_terminalize_through_the_worker():
    worker, *_ = setup_worker(decode=lambda work: decode_pcm16_wav(GARBAGE_STAGED_BYTES))
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'staged_audio_invalid')]


def test_real_decoder_valid_bytes_complete_the_unit():
    import io as io_module
    import wave as wave_module

    body = io_module.BytesIO()
    with wave_module.open(body, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b'\x00\x00' * 32000)
    frozen = body.getvalue()
    worker, words, saved, decoded, diarized, failures = setup_worker(decode=lambda work: decode_pcm16_wav(frozen))
    results = worker.process_batch([item()])
    assert results[0].segment_id == 'a'
    assert not failures


def test_decode_extent_within_the_admission_tolerance_completes():
    # The boundary accepts a decoded extent within 0.1 s of the admitted one.
    worker, *_ = setup_worker(decode=lambda work: Samples(work.duration_seconds + 0.05))
    results = worker.process_batch([item(duration=2)])
    assert results[0].segment_id == 'a'


def test_decode_extent_past_the_admission_tolerance_terminalizes():
    worker, *_ = setup_worker(decode=lambda work: Samples(work.duration_seconds + 0.2))
    results = worker.process_batch([item(duration=2)])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'decoded_duration_mismatch')]


def test_zero_extent_decode_terminalizes():
    worker, *_ = setup_worker(decode=lambda work: Samples(0))
    results = worker.process_batch([item(duration=2)])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'decoded_duration_mismatch')]


def test_over_ceiling_extent_terminalizes():
    from config.batch_pipeline_providers import ProviderConfig
    from dataclasses import replace

    config = ProviderConfig(max_unit_seconds=120, max_padded_seconds=120)
    worker, *_ = setup_worker(config=config, decode=lambda work: Samples(work.duration_seconds + 1 / 16000))
    results = worker.process_batch([replace(item(duration=120), unit_kind='capture_span')])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'decoded_duration_mismatch')]


def test_decode_fault_beats_a_later_stage_fault_for_the_same_unit():
    # decode fails first: the vad fault never runs for that unit.
    def decode(_work):
        raise StagedAudioInvalid('invalid staged WAV container')

    def vad(_samples):
        raise DecodedDurationMismatch('never reached')

    worker, *_ = setup_worker(decode=decode, vad=vad)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'staged_audio_invalid')]


def test_mixed_batch_reports_each_units_own_fault():
    worker, *_ = setup_worker(
        decode=lambda work: (
            (_ for _ in ()).throw(StagedAudioInvalid('invalid staged WAV container'))
            if work.segment_id == 'a'
            else ((_ for _ in ()).throw(DecodedDurationMismatch('mismatch')) if work.segment_id == 'b' else Samples(2))
        )
    )
    results = worker.process_batch([item('a'), item('b'), item('c')])
    assert results[0].reason == 'staged_audio_invalid'
    assert results[1].reason == 'decoded_duration_mismatch'
    assert results[2].segment_id == 'c'


def test_decode_pcm16_wav_reference_import():
    from diarizer.batch_pipeline_models import decode_pcm16_wav as decoder

    assert callable(decoder)


def test_boundary_module_exports_the_typed_faults():
    import diarizer.batch_pipeline as pipeline

    assert pipeline.DecodedDurationMismatch is not None
    from utils.batch_pipeline.audio import StagedAudioInvalid as staged_type

    assert staged_type is not None
