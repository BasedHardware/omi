"""The worker language barrier stays the safety net behind the intake lane flip.

Intake now routes proven non-Parakeet speech to the provider lane, but any
unit that still reaches the GPU with an unservable frozen language must keep
the exact documented behavior: strict silence disposes with no ASR, strict or
model-observed speech raises ``unsupported_language`` at ``vad_windows`` as a
terminal validation failure, and named supported languages never meet the
barrier at all.
"""

import logging
from dataclasses import replace
from types import SimpleNamespace

import pytest

from config import stt_cap_dispatch as cap_policy  # noqa: F401
from diarizer import batch_pipeline
from tests.unit.test_batch_pipeline_worker import Samples, item, setup_worker
from utils.batch_pipeline.contracts import ValidationFailureWork


@pytest.fixture(autouse=True)
def _disposition_on(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')


def strict_speech(monkeypatch):
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', lambda item_, samples: None)
    monkeypatch.setattr(
        batch_pipeline,
        'inspect_worker_vad',
        lambda item_, samples: (len(samples) / 16000, [{'start': 0.0, 'end': len(samples) / 16000}]),
    )


def strict_silence(monkeypatch):
    monkeypatch.setattr(
        batch_pipeline,
        'inspect_worker_silence',
        lambda item_, samples: {'outcome': 'silence', 'duration_seconds': len(samples) / 16000},
    )
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_vad', lambda item_, samples: (len(samples) / 16000, []))


def strict_unavailable(monkeypatch):
    def broken(item_, samples):
        raise RuntimeError('strict VAD unavailable')

    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', broken)
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_vad', broken)


def test_unsupported_frozen_language_speech_ends_the_chain(monkeypatch):
    strict_speech(monkeypatch)
    worker, words, saved, *_ = setup_worker(language_of=lambda _: 'ja')
    result = worker.process_batch([item()])
    assert len(result) == 1 and isinstance(result[0], ValidationFailureWork)


def test_unsupported_frozen_language_speech_names_the_barrier_reason(monkeypatch):
    strict_speech(monkeypatch)
    worker, *_ = setup_worker(language_of=lambda _: 'ja')
    assert worker.process_batch([item()])[0].reason == 'unsupported_language'


def test_unsupported_frozen_language_speech_fails_at_vad_windows(monkeypatch):
    strict_speech(monkeypatch)
    worker, *_ = setup_worker(language_of=lambda _: 'ja')
    assert worker.process_batch([item()])[0].stage == 'vad_windows'


def test_unsupported_frozen_language_speech_never_reaches_asr(monkeypatch):
    strict_speech(monkeypatch)
    worker, words, saved, *_ = setup_worker(language_of=lambda _: 'ja')
    worker.process_batch([item()])
    assert not words.calls and not saved


def test_und_frozen_speech_ends_the_chain(monkeypatch):
    strict_speech(monkeypatch)
    worker, words, *_ = setup_worker(language_of=lambda _: 'und')
    result = worker.process_batch([item()])
    assert isinstance(result[0], ValidationFailureWork) and result[0].reason == 'unsupported_language'


def test_und_frozen_speech_never_reaches_asr(monkeypatch):
    strict_speech(monkeypatch)
    worker, words, *_ = setup_worker(language_of=lambda _: 'und')
    worker.process_batch([item()])
    assert not words.calls


def test_unknown_frozen_speech_ends_the_chain(monkeypatch):
    strict_speech(monkeypatch)
    worker, *_ = setup_worker(language_of=lambda _: '')
    result = worker.process_batch([item()])
    assert isinstance(result[0], ValidationFailureWork) and result[0].reason == 'unsupported_language'


def test_multi_frozen_speech_ends_the_chain(monkeypatch):
    strict_speech(monkeypatch)
    worker, *_ = setup_worker(language_of=lambda _: 'multi')
    assert worker.process_batch([item()])[0].reason == 'unsupported_language'


def test_none_frozen_speech_ends_the_chain(monkeypatch):
    strict_speech(monkeypatch)
    worker, *_ = setup_worker(language_of=lambda _: None)
    assert worker.process_batch([item()])[0].reason == 'unsupported_language'


def test_vietnamese_frozen_speech_ends_the_chain(monkeypatch):
    strict_speech(monkeypatch)
    worker, *_ = setup_worker(language_of=lambda _: 'vi')
    assert worker.process_batch([item()])[0].reason == 'unsupported_language'


def test_unsupported_frozen_silence_disposes_with_no_asr(monkeypatch):
    worker, words, saved, *_ = setup_worker(language_of=lambda _: 'ja', vad=lambda s: [])
    result = worker.process_batch([item()])
    assert result[0].outcome == 'silence'
    assert not words.calls


def test_unsupported_frozen_silence_persists_empty_words(monkeypatch):
    worker, _, saved, *_ = setup_worker(language_of=lambda _: 'ja', vad=lambda s: [])
    worker.process_batch([item()])
    assert saved['a']['words'] == []


def test_unsupported_frozen_silence_never_quarantines(monkeypatch):
    worker, _, saved, *_ = setup_worker(language_of=lambda _: 'und', vad=lambda s: [])
    result = worker.process_batch([item()])
    assert not any(isinstance(r, ValidationFailureWork) for r in result)


def test_und_frozen_silence_disposes_with_no_asr(monkeypatch):
    worker, words, *_ = setup_worker(language_of=lambda _: 'und', vad=lambda s: [])
    assert worker.process_batch([item()])[0].outcome == 'silence'
    assert not words.calls


def test_unavailable_strict_evidence_falls_back_to_the_model_vad(monkeypatch):
    strict_unavailable(monkeypatch)
    worker, words, saved, diarized, *_ = setup_worker(language_of=lambda _: 'ja', vad=lambda s: [(0, len(s) / 16000)])
    result = worker.process_batch([item()])
    # The serial model VAD observed speech; the barrier still ends the chain.
    assert isinstance(result[0], ValidationFailureWork) and result[0].reason == 'unsupported_language'


def test_unavailable_strict_evidence_with_model_silence_disposes_clean(monkeypatch):
    strict_unavailable(monkeypatch)
    worker, words, *_ = setup_worker(language_of=lambda _: 'ja', vad=lambda s: [])
    assert worker.process_batch([item()])[0].outcome == 'silence'
    assert not words.calls


def test_supported_language_never_meets_the_strict_first_path(monkeypatch):
    strict_speech(monkeypatch)
    calls = []
    worker, words, saved, *_ = setup_worker(language_of=lambda _: 'en')
    worker.process_batch([item()])
    assert words.calls and saved['a']['words']


def test_supported_language_never_raises_the_barrier(monkeypatch):
    strict_speech(monkeypatch)
    worker, *_ = setup_worker(language_of=lambda _: 'en')
    result = worker.process_batch([item()])
    assert not any(isinstance(r, ValidationFailureWork) for r in result)


def test_named_unsupported_language_records_a_blocked_route(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    strict_speech(monkeypatch)
    worker, *_ = setup_worker(language_of=lambda _: 'ja')
    worker.process_batch([item()])
    routes = [r.message for r in caplog.records if 'event=batch_language_route' in r.message]
    assert any('route=blocked' in message for message in routes)


def test_named_supported_language_records_a_parakeet_route(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    worker, *_ = setup_worker(language_of=lambda _: 'en')
    worker.process_batch([item()])
    routes = [r.message for r in caplog.records if 'event=batch_language_route' in r.message]
    assert any('route=parakeet' in message for message in routes)


def test_und_frozen_language_records_a_blocked_route(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    strict_speech(monkeypatch)
    worker, *_ = setup_worker(language_of=lambda _: 'und')
    worker.process_batch([item()])
    routes = [r.message for r in caplog.records if 'event=batch_language_route' in r.message]
    assert routes and all('route=blocked' in message for message in routes)


def test_barrier_failure_records_carry_the_closed_error_class(monkeypatch):
    strict_speech(monkeypatch)
    worker, *_ = setup_worker(language_of=lambda _: 'ja')
    worker.process_batch([item()])
    assert worker.counts['failed'] == 1


def test_barrier_failure_keeps_healthy_siblings(monkeypatch):
    strict_speech(monkeypatch)
    worker, words, *_ = setup_worker(language_of=lambda item_: 'ja' if item_.segment_id == 'a' else 'en')
    results = worker.process_batch([item('a'), item('b', 2)])
    reasons = [(r.segment_id, type(r).__name__) for r in results]
    assert ('a', 'ValidationFailureWork') in reasons
    assert ('b', 'WorkResult') in reasons
    assert words.calls == [[2]]


def test_barrier_failure_carries_stage_vad_windows(monkeypatch):
    strict_speech(monkeypatch)
    worker, *_ = setup_worker(language_of=lambda _: 'ja')
    assert worker.process_batch([item()])[0].stage == 'vad_windows'


def test_shadow_language_blocked_speech_still_ends_its_chain(monkeypatch):
    strict_speech(monkeypatch)
    worker, *_ = setup_worker(language_of=lambda _: 'ja')
    result = worker.process_batch([replace(item(), shadow=True)])
    assert isinstance(result[0], ValidationFailureWork)


def test_shadow_supported_language_runs_the_models(monkeypatch):
    worker, words, *_ = setup_worker(language_of=lambda _: 'en')
    assert worker.process_batch([replace(item(), shadow=True)])[0].outcome == 'success'
    assert words.calls


def test_unsupported_language_is_terminal_even_with_the_disposition_flag_off(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')
    worker, words, *_ = setup_worker(language_of=lambda _: 'ja', vad=lambda s: [(0, len(s) / 16000)])
    result = worker.process_batch([item()])
    assert isinstance(result[0], ValidationFailureWork)
    assert not words.calls


def test_other_validation_faults_keep_their_ladder_with_the_flag_off(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')
    strict_unavailable(monkeypatch)
    worker, words, saved, *_ = setup_worker(language_of=lambda _: 'en', vad=lambda s: [(0, len(s) / 16000)])
    result = worker.process_batch([item('short', 2)])
    # vad_bounds on a two-second buffer is not a language fault: with the flag
    # off it rides the safety net as an ordinary retryable failure.
    assert not isinstance(result[0], ValidationFailureWork)


def test_disposition_flag_default_keeps_the_barrier_terminal(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', raising=False)
    strict_speech(monkeypatch)
    worker, *_ = setup_worker(language_of=lambda _: 'ja')
    assert isinstance(worker.process_batch([item()])[0], ValidationFailureWork)


def test_long_unsupported_speech_ends_the_chain_the_same_way(monkeypatch):
    strict_speech(monkeypatch)
    worker, words, *_ = setup_worker(language_of=lambda _: 'ja')
    result = worker.process_batch([item('long', 30)])
    assert isinstance(result[0], ValidationFailureWork)
    assert not words.calls


def test_short_unsupported_speech_ends_the_chain_the_same_way(monkeypatch):
    strict_speech(monkeypatch)
    worker, *_ = setup_worker(language_of=lambda _: 'ja')
    assert isinstance(worker.process_batch([item('short', 1)])[0], ValidationFailureWork)


def test_subframe_unsupported_speech_takes_the_same_strict_first_path(monkeypatch):
    strict_speech(monkeypatch)
    worker, words, *_ = setup_worker(language_of=lambda _: 'ja')
    assert isinstance(worker.process_batch([item('tiny', 0.01)])[0], ValidationFailureWork)


def test_unsupported_silence_and_speech_mix_dispose_independently(monkeypatch):
    strict_speech(monkeypatch)

    def vad(samples):
        return [] if len(samples) < 16000 else [(0, len(samples) / 16000)]

    worker, words, saved, *_ = setup_worker(language_of=lambda _: 'ja', vad=vad)
    results = worker.process_batch([item('quiet', 0.5), item('loud', 4)])
    kinds = {type(r).__name__ for r in results}
    assert 'ValidationFailureWork' in kinds
    assert not words.calls


def test_unsupported_frozen_stream_is_never_reused(monkeypatch):
    strict_speech(monkeypatch)
    streams = []

    def stream_of(item_):
        streams.append(item_.segment_id)
        return 'stream'

    worker, *_ = setup_worker(language_of=lambda _: 'ja', stream_of=stream_of)
    worker.process_batch([item()])
    assert streams == ['a']


def test_barrier_failure_does_not_poison_the_owner_tail(monkeypatch):
    strict_speech(monkeypatch)
    worker, words, saved, *_ = setup_worker(language_of=lambda item_: 'ja' if item_.segment_id == 'a' else 'en')
    worker.process_batch([item('a'), item('b', 2)])
    assert 'b' in saved


def test_unsupported_language_is_never_an_empty_asr_record(monkeypatch):
    strict_speech(monkeypatch)
    worker, *_ = setup_worker(language_of=lambda _: 'ja')
    worker.process_batch([item()])
    assert worker.counts['failed'] == 1 and worker.counts['silence'] == 0


def test_supported_silence_and_unsupported_speech_share_one_flight(monkeypatch):
    strict_speech(monkeypatch)

    def vad(samples):
        return []

    worker, words, saved, *_ = setup_worker(
        language_of=lambda item_: 'ja' if item_.segment_id == 'a' else 'en', vad=vad
    )
    results = worker.process_batch([item('a'), item('b', 2)])
    assert {type(r).__name__ for r in results} == {'WorkResult'}


def test_empty_ladder_never_claims_a_barrier_failure(monkeypatch):
    strict_speech(monkeypatch)
    worker, *_ = setup_worker(language_of=lambda _: 'ja', recover_words=lambda item_, samples: ({}, 'raw'))
    result = worker.process_batch([item()])
    assert isinstance(result[0], ValidationFailureWork)
    assert result[0].reason == 'unsupported_language'


def test_language_blocked_units_never_join_the_packed_pass(monkeypatch):
    strict_speech(monkeypatch)
    segmented = []

    def segment(samples):
        segmented.append(list(samples))
        return ['features']

    flight = SimpleNamespace(segment=segment, vad_spans=lambda samples, features: [(0, len(samples) / 16000)])
    worker, *_ = setup_worker(language_of=lambda item_: 'ja' if item_.segment_id == 'a' else 'en', flight_models=flight)
    worker.process_batch([item('a'), item('b', 2)])
    assert len(segmented) == 1  # Only the supported unit entered the packed segmentation.


def test_supported_units_keep_the_packed_features(monkeypatch):
    strict_speech(monkeypatch)

    def vad(samples, features):
        assert features is not None
        return [(0, len(samples) / 16000)]

    flight = SimpleNamespace(segment=lambda samples: ['features'], vad_spans=vad)
    worker, *_ = setup_worker(flight_models=flight)
    assert worker.process_batch([item()])[0].outcome == 'success'


def test_language_blocked_unit_never_takes_packed_features(monkeypatch):
    strict_speech(monkeypatch)

    def vad(samples, features):
        return [(0, len(samples) / 16000)]

    flight = SimpleNamespace(segment=lambda samples: ['features'], vad_spans=vad)
    worker, *_ = setup_worker(language_of=lambda _: 'ja', flight_models=flight)
    result = worker.process_batch([item('a')])
    assert isinstance(result[0], ValidationFailureWork)


def test_the_route_record_precedes_any_asr_work(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    worker, words, *_ = setup_worker(language_of=lambda _: 'ja')
    worker.process_batch([item()])
    routes = [r.message for r in caplog.records if 'event=batch_language_route' in r.message]
    assert routes and not words.calls


def test_two_unsupported_units_both_end_their_chains(monkeypatch):
    strict_speech(monkeypatch)
    worker, words, *_ = setup_worker(language_of=lambda _: 'ja')
    results = worker.process_batch([item('a'), item('b', 3)])
    assert len(results) == 2
    assert all(isinstance(r, ValidationFailureWork) for r in results)
    assert not words.calls


def test_validation_failure_carries_no_words_and_no_save(monkeypatch):
    strict_speech(monkeypatch)
    worker, words, saved, *_ = setup_worker(language_of=lambda _: 'ja')
    worker.process_batch([item()])
    assert not words.calls and not saved


def test_the_reason_vocabulary_stays_closed(monkeypatch):
    from utils.batch_pipeline.word_validation import ValidationReason

    assert {reason.value for reason in ValidationReason} == {
        'unsupported_language',
        'word_shape',
        'word_clock',
        'word_sequence',
        'vad_nonfinite',
        'vad_order',
        'vad_bounds',
        'empty_asr',
        'no_owned_words',
    }


def test_unsupported_language_is_a_closed_member(monkeypatch):
    from utils.batch_pipeline.word_validation import ValidationReason

    assert ValidationReason.UNSUPPORTED_LANGUAGE.value == 'unsupported_language'


def test_batch_validation_error_rejects_free_form_reasons():
    from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason

    with pytest.raises(ValueError):
        BatchValidationError('because')


def test_batch_validation_error_carries_the_value_string():
    from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason

    assert BatchValidationError(ValidationReason.UNSUPPORTED_LANGUAGE).reason == 'unsupported_language'


def test_unsupported_failure_is_a_value_error_subclass():
    from utils.batch_pipeline.word_validation import BatchValidationError

    assert issubclass(BatchValidationError, ValueError)


def test_validation_failure_work_is_terminal_not_failed_work():
    from utils.batch_pipeline.contracts import FailedWork

    assert not issubclass(ValidationFailureWork, FailedWork)


def test_validation_failure_work_carries_stage_reason_and_receipt():
    failure = ValidationFailureWork('seg', 'vad_windows', 'unsupported_language', None, None)
    assert (failure.segment_id, failure.stage, failure.reason) == ('seg', 'vad_windows', 'unsupported_language')


def test_worker_route_counter_records_the_worker_surface(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    worker, *_ = setup_worker(language_of=lambda _: 'ja')
    worker.process_batch([item()])
    routes = [r.message for r in caplog.records if 'event=batch_language_route' in r.message]
    assert routes and 'surface=worker' in routes[0]
