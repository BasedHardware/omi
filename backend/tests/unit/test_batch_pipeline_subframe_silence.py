"""Sub-frame captures: the vad_windows evidence-selection contract.

A capture shorter than one complete Silero frame (512 samples at 16 kHz)
cannot contain measurable speech. The model VAD's padded frames can only
fabricate spans that start beyond the buffer — the deterministic
``vad_bounds`` raise whose disposition branch re-derives the same answer
from the strict CPU inspector, and whose quarantined units then burn a
fenced recovery sweep that settles them with the recovery lane's own
below-frame rule. The worker therefore asks the strict inspector first for
sub-frame captures: strict silence disposes the unit with no model
forward, while strict speech or unavailable evidence keeps today's hold
semantics unchanged.

Failure-Class: FC-subframe-capture-burns-model-vad-and-fenced-recovery-hop
"""

import numpy as np
import pytest
from unittest.mock import Mock

from config.batch_language_recovery import below_silence_threshold
from config.batch_pipeline import worker_validation_disposition_enabled
from diarizer import batch_pipeline
from tests.unit.test_batch_pipeline_worker import item, setup_worker
from utils.batch_pipeline.contracts import ValidationFailureWork, WorkResult
from utils.batch_pipeline.recovery_disposition import silence_payload
from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason


@pytest.fixture(autouse=True)
def _quiet_env(monkeypatch):
    # Deterministic evidence selection: no shadow sampling, no post-ASR
    # silence re-derivation, serial (non-flight) chain — the prod default.
    # The safety net stays off unless a test pins it on: the strict adapter
    # mocks below target the off-adapter seam (inspect_worker_silence).
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_STRICT_VAD_SHADOW_PERCENT', '0')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED', 'false')
    monkeypatch.delenv('BATCH_PIPELINE_FLIGHT_BATCHING_ENABLED', raising=False)


def silence(duration=0.02):
    return silence_payload(duration)


def strict_returns_silence(monkeypatch, duration=0.02):
    mock = Mock(return_value=silence(duration))
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', mock)
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_vad', Mock(return_value=(duration, [])))
    return mock


def strict_returns_speech(monkeypatch):
    mock = Mock(return_value=None)  # inspect_worker_silence: None means spans (speech).
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', mock)
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_vad', Mock(return_value=(0.02, [{'start': 0.0, 'end': 0.02}])))
    return mock


def strict_unavailable(monkeypatch):
    mock = Mock(side_effect=RuntimeError('synthetic-private-error'))
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', mock)
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_vad', mock)
    return mock


def run_worker(monkeypatch, *, key='sub', duration=0.02, vad=None, strict=None, language='en'):
    if strict is not None:
        strict(monkeypatch)
    vad = vad if vad is not None else Mock(return_value=[(0, duration)])
    worker, provider, saved, decoded, diarized, failures = setup_worker(vad=vad, language_of=lambda work_item: language)
    results = worker.process_batch([item(key, duration)])
    return worker, vad, saved, decoded, diarized, failures, results


# --- The strict inspector decides the sub-frame boundary --------------------


def test_predicate_rejects_a_single_sample_capture():
    assert below_silence_threshold(1 / 16000)


def test_predicate_accepts_a_half_frame_capture():
    assert below_silence_threshold(256 / 16000)


def test_predicate_rejects_one_sample_below_the_full_frame():
    assert below_silence_threshold(511 / 16000)


def test_predicate_rejects_the_last_sub_frame_sample_count():
    assert below_silence_threshold(511.4 / 16000)


def test_predicate_keeps_exactly_one_full_frame():
    assert not below_silence_threshold(512 / 16000)


def test_predicate_keeps_one_sample_past_the_full_frame():
    assert not below_silence_threshold(513 / 16000)


def test_predicate_keeps_a_twenty_millisecond_buffer_one_frame_short_of_speech():
    assert below_silence_threshold(0.02)


def test_predicate_keeps_the_silence_threshold_itself():
    assert not below_silence_threshold(0.032)


def test_predicate_is_false_for_a_second_long_capture():
    assert not below_silence_threshold(1.0)


def test_predicate_is_false_for_a_long_unit():
    assert not below_silence_threshold(3600.0)


def test_predicate_rounds_a_partial_sample_up_before_comparing():
    # 511.6 samples rounds to 512: one complete frame, not sub-frame.
    assert not below_silence_threshold(511.6 / 16000)


def test_predicate_floor_matches_the_recovery_lanes_threshold_constant():
    from config.batch_language_recovery import SILENCE_THRESHOLD_SECONDS

    assert not below_silence_threshold(SILENCE_THRESHOLD_SECONDS)
    assert below_silence_threshold(SILENCE_THRESHOLD_SECONDS - 1 / 16000)


# --- Sub-frame strict silence disposes without a model forward --------------


@pytest.mark.parametrize('duration', [0.001, 0.005, 0.01, 0.02, 0.03])
def test_sub_frame_strict_silence_completes_as_silence(monkeypatch, duration):
    monkeypatch, vad, saved, decoded, diarized, failures, results = run_worker(
        monkeypatch, key=f'sub{duration}', duration=duration, strict=strict_returns_silence
    )
    assert results[0].outcome == 'silence'
    assert not failures


@pytest.mark.parametrize('duration', [0.001, 0.01, 0.02, 0.0319])
def test_sub_frame_strict_silence_never_calls_the_model_vad(monkeypatch, duration):
    vad = Mock(return_value=[(0, duration)])
    _, vad, *_rest = run_worker(monkeypatch, duration=duration, vad=vad, strict=strict_returns_silence)
    assert vad.call_count == 0


def test_sub_frame_strict_silence_persists_an_empty_words_payload(monkeypatch):
    _, _, saved, *_rest = run_worker(monkeypatch, key='sub', strict=strict_returns_silence)
    assert saved['sub']['words'] == []
    assert saved['sub']['diarization']['outcome'] == 'silence'


def test_sub_frame_strict_silence_records_one_silence_unit(monkeypatch):
    worker, *_rest, results = run_worker(monkeypatch, strict=strict_returns_silence)
    assert worker.counts['silence'] == 1
    assert worker.counts['items'] == 1


def test_sub_frame_strict_silence_skips_diarization(monkeypatch):
    _, _, _, _, diarized, _, _ = run_worker(monkeypatch, strict=strict_returns_silence)
    assert diarized == []


def test_sub_frame_strict_silence_calls_the_strict_inspector_once(monkeypatch):
    mock = strict_returns_silence(monkeypatch)
    run_worker(monkeypatch, strict=None)
    assert mock.call_count == 1


def test_sub_frame_strict_silence_payload_is_bound_to_the_unit(monkeypatch):
    _, _, saved, *_rest = run_worker(monkeypatch, key='sub', duration=0.02, strict=strict_returns_silence)
    assert saved['sub']['speech_spans'] == []
    assert saved['sub']['audio_seconds'] == 0.02


@pytest.mark.parametrize('key', ['a', 'b', 'c'])
def test_each_sub_frame_unit_decides_independently(monkeypatch, key):
    monkeypatch, vad, saved, decoded, diarized, failures, results = run_worker(
        monkeypatch, key=key, strict=strict_returns_silence
    )
    assert results[0].segment_id == key
    assert results[0].outcome == 'silence'


def test_sub_frame_silence_keeps_the_decode_order(monkeypatch):
    worker, *_rest = setup_worker(vad=Mock(return_value=[]))
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', Mock(return_value=silence()))
    results = worker.process_batch([item('z', 0.01), item('a', 2.0)])
    assert [r.segment_id for r in results] == ['z', 'a']


def test_sub_frame_unit_sits_beside_a_normal_unit_in_one_batch(monkeypatch):
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', Mock(return_value=silence()))
    vad = Mock(return_value=[(0, 2.0)])
    worker, provider, saved, decoded, diarized, failures = setup_worker(vad=vad)
    results = worker.process_batch([item('sub', 0.02), item('norm', 2.0)])
    assert {r.segment_id for r in results} == {'sub', 'norm'}
    assert {r.outcome for r in results} == {'silence', 'success'}
    assert vad.call_count == 1  # Only the normal unit paid the model forward.
    assert not failures


def test_mixed_batch_keeps_the_sub_frame_unit_off_the_model_vad(monkeypatch):
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', Mock(return_value=silence()))
    vad = Mock(return_value=[(0, 2.0)])
    worker, *_rest = setup_worker(vad=vad)
    worker.process_batch([item('n1', 2.0), item('sub', 0.01), item('n2', 2.0)])
    assert vad.call_count == 2


def test_sub_frame_silence_result_carries_no_language_receipt_call(monkeypatch):
    worker, provider, *_rest = setup_worker()
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', Mock(return_value=silence()))
    results = worker.process_batch([item('sub', 0.02)])
    assert provider.calls == []


# --- Strict speech or unavailable evidence keeps today's hold semantics -----


def test_sub_frame_strict_speech_falls_through_to_the_model_vad(monkeypatch):
    vad = Mock(return_value=[(0, 0.02)])
    strict_returns_speech(monkeypatch)
    _, vad, *_rest = run_worker(monkeypatch, vad=vad)
    assert vad.call_count == 1


def test_sub_frame_strict_speech_with_model_spans_falls_through(monkeypatch):
    # The strict speech verdict never decides the unit: the model call runs,
    # and whatever the existing pipeline then does (words, word_clocks on a
    # window too small for the fixture's clocks) is today's behavior.
    vad = Mock(return_value=[(0, 0.02)])
    strict_returns_speech(monkeypatch)
    _, vad, *_rest = run_worker(monkeypatch, key='sub', vad=vad)
    assert vad.call_count == 1


def test_sub_frame_strict_unavailable_falls_through_to_the_model_vad(monkeypatch):
    vad = Mock(return_value=[(0, 0.02)])
    strict_unavailable(monkeypatch)
    _, vad, *_rest = run_worker(monkeypatch, vad=vad)
    assert vad.call_count == 1


def test_sub_frame_strict_unavailable_with_empty_model_spans_is_silence(monkeypatch):
    vad = Mock(return_value=[])
    strict_unavailable(monkeypatch)
    *_, results = run_worker(monkeypatch, key='sub', vad=vad)
    assert results[0].outcome == 'silence'


def test_strict_speech_on_a_normal_unit_never_short_circuits(monkeypatch):
    vad = Mock(return_value=[(0, 2.0)])
    strict_returns_speech(monkeypatch)
    _, vad, *_rest = run_worker(monkeypatch, key='norm', duration=2.0, vad=vad)
    assert vad.call_count == 1
    *_, results = run_worker(monkeypatch, key='norm', duration=2.0, vad=Mock(return_value=[(0, 2.0)]))
    assert results[0].outcome == 'success'


# --- Language-blocked sub-frame units keep the barrier semantics ------------


def test_language_blocked_sub_frame_strict_silence_is_silence_not_a_barrier_raise(monkeypatch):
    vad = Mock(return_value=[])
    strict_returns_silence(monkeypatch)
    *_, results = run_worker(monkeypatch, key='sub', vad=vad, language='zh')
    assert results[0].outcome == 'silence'
    assert not failures_if_any(results)


def failures_if_any(results):
    return [r for r in results if isinstance(r, ValidationFailureWork)]


def test_language_blocked_sub_frame_strict_speech_raises_at_the_language_barrier(monkeypatch):
    vad = Mock(return_value=[(0, 0.02)])
    strict_returns_speech(monkeypatch)
    worker, vad, *_rest, results = run_worker(monkeypatch, key='sub', vad=vad, language='zh')
    barrier = [r for r in results if isinstance(r, ValidationFailureWork)]
    assert barrier and barrier[0].reason == 'unsupported_language'


def test_language_blocked_normal_unit_strict_speech_still_raises(monkeypatch):
    vad = Mock(return_value=[(0, 2.0)])
    strict_returns_speech(monkeypatch)
    worker, *_rest, results = run_worker(monkeypatch, key='norm', duration=2.0, vad=vad, language='zh')
    barrier = [r for r in results if isinstance(r, ValidationFailureWork)]
    assert barrier and barrier[0].reason == 'unsupported_language'


def test_language_blocked_normal_unit_is_not_strict_first(monkeypatch):
    # Only sub-frame captures gained strict-first; normal captures keep the
    # model-VAD-first contract so the evidence mix never changes for them.
    vad = Mock(return_value=[(0, 2.0)])
    mock = strict_returns_silence(monkeypatch)
    run_worker(monkeypatch, key='norm', duration=2.0, vad=vad, language='zh')
    assert mock.call_count == 0


def test_language_blocked_sub_frame_strict_silence_never_calls_the_model_vad(monkeypatch):
    vad = Mock(return_value=[])
    strict_returns_silence(monkeypatch)
    _, vad, *_rest = run_worker(monkeypatch, key='sub', vad=vad, language='zh')
    assert vad.call_count == 0


# --- The vad_bounds disposition contract is unchanged for framed captures ---


def vad_bounds_vad():
    return Mock(side_effect=BatchValidationError(ValidationReason.VAD_BOUNDS))


def test_vad_bounds_with_strict_silence_disposes_silence(monkeypatch):
    strict_returns_silence(monkeypatch)
    *_, results = run_worker(monkeypatch, key='norm', duration=2.0, vad=vad_bounds_vad())
    assert results[0].outcome == 'silence'


def test_vad_bounds_with_strict_speech_re_raises(monkeypatch):
    strict_returns_speech(monkeypatch)
    *_, results = run_worker(monkeypatch, key='norm', duration=2.0, vad=vad_bounds_vad())
    failure = [r for r in results if isinstance(r, ValidationFailureWork)]
    assert failure and failure[0].reason == 'vad_bounds'


def test_vad_bounds_with_strict_unavailable_re_raises(monkeypatch):
    strict_unavailable(monkeypatch)
    *_, results = run_worker(monkeypatch, key='norm', duration=2.0, vad=vad_bounds_vad())
    failure = [r for r in results if isinstance(r, ValidationFailureWork)]
    assert failure and failure[0].reason == 'vad_bounds'


def test_vad_bounds_failure_carries_the_vad_windows_stage(monkeypatch):
    strict_unavailable(monkeypatch)
    *_, results = run_worker(monkeypatch, key='norm', duration=2.0, vad=vad_bounds_vad())
    failure = [r for r in results if isinstance(r, ValidationFailureWork)]
    assert failure[0].stage == 'vad_windows'


def test_vad_bounds_records_the_worker_failure_callback(monkeypatch):
    strict_unavailable(monkeypatch)
    worker, vad, saved, decoded, diarized, failures = setup_worker(vad=vad_bounds_vad())
    worker.process_batch([item('norm', 2.0)])
    assert failures and failures[0][1] == 'BatchValidationError'


def test_vad_bounds_on_a_sub_frame_unit_with_strict_speech_still_holds(monkeypatch):
    vad = vad_bounds_vad()
    strict_returns_speech(monkeypatch)
    *_, results = run_worker(monkeypatch, key='sub', vad=vad)
    failure = [r for r in results if isinstance(r, ValidationFailureWork)]
    assert failure and failure[0].reason == 'vad_bounds'


def test_vad_bounds_on_a_sub_frame_unit_with_strict_unavailable_still_holds(monkeypatch):
    vad = vad_bounds_vad()
    strict_unavailable(monkeypatch)
    *_, results = run_worker(monkeypatch, key='sub', vad=vad)
    failure = [r for r in results if isinstance(r, ValidationFailureWork)]
    assert failure and failure[0].reason == 'vad_bounds'


@pytest.mark.parametrize('reason', [ValidationReason.VAD_NONFINITE, ValidationReason.VAD_ORDER])
def test_non_bounds_vad_reasons_re_raise_even_with_strict_silence(monkeypatch, reason):
    vad = Mock(side_effect=BatchValidationError(reason))
    strict_returns_silence(monkeypatch)
    *_, results = run_worker(monkeypatch, key='norm', duration=2.0, vad=vad)
    failure = [r for r in results if isinstance(r, ValidationFailureWork)]
    assert failure and failure[0].reason == reason.value


# --- Flag and safety-matrix behavior ----------------------------------------


def test_disposition_flag_defaults_on(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', raising=False)
    assert worker_validation_disposition_enabled()


def test_disposition_flag_kill_switch(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')
    assert not worker_validation_disposition_enabled()


def test_safety_net_on_strict_silence_still_disposes_sub_frames(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    measured = Mock(return_value=(0.02, []))
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_vad', measured)
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', Mock(return_value=silence()))
    vad = Mock(return_value=[(0, 0.02)])
    worker, *_rest = setup_worker(vad=vad)
    results = worker.process_batch([item('sub', 0.02)])
    assert results[0].outcome == 'silence'
    assert measured.call_count == 1


def test_safety_net_on_measured_sub_frame_speech_falls_through(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    measured = Mock(return_value=(0.02, [{'start': 0.0, 'end': 0.02}]))
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_vad', measured)
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', Mock(return_value=None))
    vad = Mock(return_value=[(0, 0.02)])
    worker, _provider, _saved, _decoded, _diarized, _failures = setup_worker(vad=vad)
    worker.process_batch([item('sub', 0.02)])
    assert vad.call_count == 1


def test_safety_net_off_uses_the_silence_adapter_directly(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    adapter = Mock(return_value=silence())
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    worker, *_rest = setup_worker(vad=Mock(return_value=[(0, 0.02)]))
    worker.process_batch([item('sub', 0.02)])
    assert adapter.call_count == 1


def test_shadow_sub_frame_unit_takes_the_same_strict_first_path(monkeypatch):
    from dataclasses import replace

    adapter = Mock(return_value=silence())
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    vad = Mock(return_value=[(0, 0.02)])
    worker, *_rest = setup_worker(vad=vad)
    results = worker.process_batch([replace(item('sub', 0.02), shadow=True)])
    assert results[0].outcome == 'silence'
    assert adapter.call_count == 1


def test_shadow_sub_frame_unit_skips_diarization_and_words(monkeypatch):
    from dataclasses import replace

    adapter = Mock(return_value=silence())
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    worker, provider, saved, decoded, diarized, failures = setup_worker(vad=Mock(return_value=[]))
    results = worker.process_batch([replace(item('sub', 0.02), shadow=True)])
    assert results[0].outcome == 'silence'
    assert diarized == [] and provider.calls == [] and failures == []


# --- Evidence: receipts, counters and state fields --------------------------


def test_sub_frame_silence_counts_zero_vad_spans_and_windows(monkeypatch):
    worker, *_rest = setup_worker(vad=Mock(return_value=[]))
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', Mock(return_value=silence()))
    worker.process_batch([item('sub', 0.02)])
    assert worker.counts['silence'] == 1


def test_normal_unit_with_model_silence_counts_silence_too(monkeypatch):
    worker, *_rest = setup_worker(vad=Mock(return_value=[]))
    worker.process_batch([item('norm', 2.0)])
    assert worker.counts['silence'] == 1


def test_sub_frame_silence_does_not_touch_the_failure_callback(monkeypatch):
    worker, vad, saved, decoded, diarized, failures = setup_worker(vad=Mock(return_value=[]))
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', Mock(return_value=silence()))
    worker.process_batch([item('sub', 0.02)])
    assert failures == []


def test_sub_frame_strict_silence_decode_runs_once(monkeypatch):
    adapter = Mock(return_value=silence())
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    worker, vad, saved, decoded, diarized, failures = setup_worker(vad=Mock(return_value=[]))
    worker.process_batch([item('sub', 0.02)])
    assert decoded == ['sub']


def test_two_sub_frame_units_both_dispose(monkeypatch):
    adapter = Mock(return_value=silence())
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    worker, *_rest = setup_worker(vad=Mock(return_value=[]))
    results = worker.process_batch([item('s1', 0.01), item('s2', 0.02)])
    assert [r.outcome for r in results] == ['silence', 'silence']


def test_sub_frame_then_normal_then_sub_frame_order_survives(monkeypatch):
    adapter = Mock(return_value=silence())
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    worker, *_rest = setup_worker(vad=Mock(return_value=[(0, 2.0)]))
    results = worker.process_batch([item('s1', 0.02), item('n', 2.0), item('s2', 0.01)])
    assert [r.segment_id for r in results] == ['s1', 'n', 's2']


# --- The real strict inspector handles the sub-frame length -----------------


def test_real_strict_inspector_silences_a_20ms_buffer():
    from utils.batch_pipeline.worker_silence import inspect_worker_silence

    payload = inspect_worker_silence(item('short', 0.02), np.zeros(320, dtype=np.float32))
    assert payload['outcome'] == 'silence' and payload['speech_spans'] == []


def test_real_strict_inspector_silences_a_single_sample_buffer():
    from utils.batch_pipeline.worker_silence import inspect_worker_silence

    payload = inspect_worker_silence(item('tiny', 1 / 16000), np.zeros(1, dtype=np.float32))
    assert payload['outcome'] == 'silence'


def test_real_strict_inspector_silences_a_511_sample_buffer():
    from utils.batch_pipeline.worker_silence import inspect_worker_silence

    payload = inspect_worker_silence(item('edge', 511 / 16000), np.zeros(511, dtype=np.float32))
    assert payload['outcome'] == 'silence'


def test_real_strict_inspector_rejects_non_canonical_samples():
    from utils.batch_pipeline.worker_silence import inspect_worker_silence

    with pytest.raises(ValueError):
        inspect_worker_silence(item('bad', 0.02), np.full(320, 1.1, dtype=np.float32))


# --- The worker predicate agrees with the recovery lane's rule --------------


def test_worker_disposition_and_recovery_rule_agree_at_the_boundary():
    # The recovery lane settles held audio with below_silence_threshold
    # (independent arm); the worker now applies the same rule, so a unit the
    # worker disposes is one recovery would never hold for speech evidence.
    from config.batch_language_recovery import below_silence_threshold as rule

    for samples in (1, 320, 511, 512, 513, 1600):
        duration = samples / 16000
        assert below_silence_threshold(duration) == rule(duration)


def test_recovery_rule_below_frame_is_the_only_independent_silence(monkeypatch):
    from utils.batch_pipeline.contracts import held_silence_allowed

    job = {'duration_seconds': 0.02, 'measured_held_vad_speech_seconds': 0.0}
    assert held_silence_allowed(job, 0.0, independent=True)
    assert not held_silence_allowed({**job, 'measured_held_vad_speech_seconds': 0.05}, 0.05, independent=True)


def test_quarantined_vad_bounds_unit_without_evidence_stays_unsettled():
    from utils.batch_pipeline.contracts import held_silence_allowed

    # Anti-fabrication: no measurement anywhere means silence is never allowed.
    assert not held_silence_allowed({'duration_seconds': 2.0}, None)


def test_quarantined_unit_with_zero_census_allows_silence_off_the_guard():
    from utils.batch_pipeline.contracts import held_silence_allowed

    job = {'duration_seconds': 2.0, 'measured_held_vad_speech_seconds': 0.0}
    assert held_silence_allowed(job, 0.0)


def test_quarantined_guarded_unit_never_takes_the_plain_silence_arm():
    from utils.batch_pipeline.contracts import held_silence_allowed

    job = {
        'duration_seconds': 2.0,
        'measured_held_vad_speech_seconds': 0.0,
        'worker_failure': {'stage': 'vad_windows', 'reason': 'unsupported_language'},
    }
    assert not held_silence_allowed(job, 0.0)


# --- WorkResult and payload shape for the sub-frame silence outcome ---------


@pytest.mark.parametrize('duration', [0.001, 0.02, 0.0319])
def test_silence_result_outcome_is_the_plain_silence_token(monkeypatch, duration):
    adapter = Mock(return_value=silence(duration))
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    worker, *_rest = setup_worker(vad=Mock(return_value=[]))
    results = worker.process_batch([item('sub', duration)])
    assert isinstance(results[0], WorkResult)
    assert results[0].outcome == 'silence'


def test_silence_payload_duration_is_the_captured_extent(monkeypatch):
    adapter = Mock(return_value=silence(0.02))
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    worker, _, saved, *_rest = setup_worker(vad=Mock(return_value=[]))
    worker.process_batch([item('sub', 0.02)])
    assert saved['sub']['audio_seconds'] == pytest.approx(0.02)


def test_silence_payload_speech_seconds_is_zero(monkeypatch):
    adapter = Mock(return_value=silence(0.02))
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    worker, _, saved, *_rest = setup_worker(vad=Mock(return_value=[]))
    worker.process_batch([item('sub', 0.02)])
    assert saved['sub']['speech_seconds'] == 0.0


def test_payload_words_provider_marks_strict_local_vad_for_sub_frame_silence(monkeypatch):
    # The established strict-VAD silence marker: the transcript-free payload
    # names the evidence source, never the untouched word provider.
    adapter = Mock(return_value=silence())
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    worker, _, saved, *_rest = setup_worker(vad=Mock(return_value=[]))
    worker.process_batch([item('sub', 0.02)])
    assert saved['sub']['words_provider'] == 'strict_local_vad'


def test_payload_diarizer_field_is_unchanged_for_sub_frame_units(monkeypatch):
    adapter = Mock(return_value=silence())
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    worker, _, saved, *_rest = setup_worker(vad=Mock(return_value=[]))
    worker.process_batch([item('sub', 0.02)])
    assert 'diarizer' in saved['sub']


# --- Failure isolation: a strict error must not poison siblings -------------


def test_strict_error_on_one_sub_frame_unit_keeps_the_sibling(monkeypatch):
    worker, *_rest = setup_worker(vad=Mock(return_value=[]))
    calls = {'n': 0}

    def flaky(item_work, samples):
        calls['n'] += 1
        if calls['n'] == 1:
            raise RuntimeError('synthetic-private-error')
        return silence()

    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', flaky)
    results = worker.process_batch([item('s1', 0.02), item('s2', 0.02)])
    assert {r.segment_id for r in results} == {'s1', 's2'}


def test_strict_error_on_a_sub_frame_unit_falls_through_to_the_model(monkeypatch):
    vad = Mock(return_value=[])
    strict_unavailable(monkeypatch)
    *_, results = run_worker(monkeypatch, key='sub', vad=vad)
    assert results[0].outcome == 'silence'


def test_vad_bounds_and_silence_units_share_one_batch_safely(monkeypatch):
    def silence_by_length(item_work, samples):
        return silence_payload(len(samples) / 16000)

    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', silence_by_length)
    responses = [BatchValidationError(ValidationReason.VAD_BOUNDS), []]

    def vad(samples):
        raise responses.pop(0)

    worker, *_rest = setup_worker(vad=vad)
    results = worker.process_batch([item('bounds', 2.0), item('sub', 0.02)])
    assert len(results) == 2
    assert {r.segment_id for r in results} == {'bounds', 'sub'}
    assert all(r.outcome == 'silence' for r in results)


# --- Batch-level invariants --------------------------------------------------


def test_empty_batch_stays_empty(monkeypatch):
    worker, *_rest = setup_worker()
    assert worker.process_batch([]) == []


def test_counts_items_counts_every_pulled_unit(monkeypatch):
    adapter = Mock(return_value=silence())
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    worker, *_rest = setup_worker(vad=Mock(return_value=[]))
    worker.process_batch([item('a', 0.02), item('b', 0.02), item('c', 2.0)])
    assert worker.counts['items'] == 3


def test_failed_decode_still_reports_the_fetch_decode_stage(monkeypatch):
    def bad_decode(work):
        raise ValueError('decoded duration differs from admitted capture')

    worker, *_rest = setup_worker(decode=bad_decode)
    results = worker.process_batch([item('x', 0.02)])
    failure = [r for r in results if isinstance(r, ValidationFailureWork)]
    assert failure and failure[0].stage == 'fetch_decode'


def test_sub_frame_unit_after_a_failed_decode_sibling_still_disposes(monkeypatch):
    adapter = Mock(return_value=silence())
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    calls = {'n': 0}

    def decode(work):
        calls['n'] += 1
        if work.segment_id == 'boom':
            raise ValueError('decoded duration differs from admitted capture')
        return type('S', (), {'__len__': lambda self: int(work.duration_seconds * 16000)})()

    worker, *_rest = setup_worker(decode=decode, vad=Mock(return_value=[]))
    results = worker.process_batch([item('boom', 0.02), item('sub', 0.02)])
    assert {r.segment_id for r in results} == {'boom', 'sub'}


# --- The new disposition eliminates the deterministic word_clocks hop -------


def test_sub_frame_strict_silence_never_reaches_the_word_clocks_stage(monkeypatch):
    # Current-code shape: the model VAD's padded span cuts a window, the fixed
    # recognizer answers with clocks that cannot fit it, and the unit dies at
    # word_clocks. The strict-first disposition removes the hop entirely.
    vad = Mock(return_value=[(0, 0.02)])
    strict_returns_silence(monkeypatch)
    worker, vad, saved, decoded, diarized, failures = setup_worker(vad=vad)
    results = worker.process_batch([item('sub', 0.02)])
    assert [r for r in results if isinstance(r, ValidationFailureWork)] == []
    assert failures == []
    assert results[0].outcome == 'silence'


def test_sub_frame_model_spans_without_strict_evidence_still_die_at_word_clocks(monkeypatch):
    # The pre-existing degenerate shape, pinned so the disposition's scope
    # stays exact: only strict silence removes the hop.
    vad = Mock(return_value=[(0, 0.02)])
    worker, vad, saved, decoded, diarized, failures = setup_worker(vad=vad)
    results = worker.process_batch([item('sub', 0.02)])
    assert failures and failures[0][1] == 'BatchValidationError'


def test_strict_silence_precedes_the_words_provider_for_sub_frames(monkeypatch):
    provider = Mock()
    provider.transcribe_batch = Mock(return_value=[[{'word': 'hello', 'timestamp': [0.0, 0.01]}]])
    adapter = Mock(return_value=silence())
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    worker, *_rest = setup_worker(words_providers={'parakeet': provider}, vad=Mock(return_value=[]))
    worker.process_batch([item('sub', 0.02)])
    assert provider.transcribe_batch.call_count == 0


def test_sub_frame_silence_leaves_no_recovery_record(monkeypatch):
    adapter = Mock(return_value=silence())
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    worker, *_rest = setup_worker(vad=Mock(return_value=[]))
    results = worker.process_batch([item('sub', 0.02)])
    assert all(r.outcome == 'silence' for r in results)


# --- Language classes at the sub-frame boundary ------------------------------


@pytest.mark.parametrize('language', ['zh', 'ja', 'de'])
def test_language_blocked_sub_frame_strict_silence_disposes(monkeypatch, language):
    adapter = Mock(return_value=silence())
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    worker, *_rest = setup_worker(vad=Mock(return_value=[]), language_of=lambda work_item: language)
    results = worker.process_batch([item('sub', 0.02)])
    assert results[0].outcome == 'silence'
    assert adapter.call_count == 1


def test_unknown_language_sub_frame_strict_silence_disposes(monkeypatch):
    adapter = Mock(return_value=silence())
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    worker, *_rest = setup_worker(vad=Mock(return_value=[]), language_of=lambda work_item: None)
    results = worker.process_batch([item('sub', 0.02)])
    assert results[0].outcome == 'silence'


def test_unsupported_language_sub_frame_strict_speech_raises_for_the_recovery_lane(monkeypatch):
    vad = Mock(return_value=[(0, 0.02)])
    strict_returns_speech(monkeypatch)
    *_, results = run_worker(monkeypatch, key='sub', vad=vad, language='zh')
    barrier = [r for r in results if isinstance(r, ValidationFailureWork)]
    assert barrier and barrier[0].reason == 'unsupported_language'


def test_unsupported_language_barrier_raise_lists_the_vad_windows_stage(monkeypatch):
    vad = Mock(return_value=[(0, 0.02)])
    strict_returns_speech(monkeypatch)
    *_, results = run_worker(monkeypatch, key='sub', vad=vad, language='zh')
    barrier = [r for r in results if isinstance(r, ValidationFailureWork)]
    assert barrier[0].stage == 'vad_windows'


# --- Disposition-flag rollback arms ------------------------------------------


def test_sub_frame_strict_silence_disposition_survives_the_flag_kill_switch(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')
    adapter = Mock(return_value=silence())
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    worker, *_rest = setup_worker(vad=Mock(return_value=[]))
    results = worker.process_batch([item('sub', 0.02)])
    assert results[0].outcome == 'silence'


def test_vad_bounds_without_the_disposition_flag_takes_the_safety_net_arm(monkeypatch):
    # Rollback shape: the disposition branch is off, so the vad_bounds raise
    # re-raises into the plain safety-net failure instead of a strict-silence
    # disposition; the strict inspector is never consulted for framed units.
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')
    adapter = Mock(return_value=silence())
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    vad = vad_bounds_vad()
    worker, provider, saved, decoded, diarized, failures = setup_worker(vad=vad)
    results = worker.process_batch([item('norm', 2.0)])
    assert adapter.call_count == 0
    assert failures and failures[0][1] == 'BatchValidationError'


def test_vad_bounds_without_the_disposition_flag_never_asks_strict_first_for_normal_units(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')
    mock = strict_returns_silence(monkeypatch)
    run_worker(monkeypatch, key='norm', duration=2.0, vad=Mock(return_value=[(0, 2.0)]))
    assert mock.call_count == 0


# --- Predicate determinism ----------------------------------------------------


@pytest.mark.parametrize('samples', [1, 2, 160, 320, 480, 511])
def test_every_sample_count_below_one_frame_is_sub_frame(samples):
    assert below_silence_threshold(samples / 16000)


@pytest.mark.parametrize('samples', [512, 513, 800, 1600, 16000])
def test_every_sample_count_from_one_frame_up_is_not_sub_frame(samples):
    assert not below_silence_threshold(samples / 16000)


def test_predicate_exits_only_at_the_full_frame_sample_count():
    assert below_silence_threshold(255 / 16000)
    assert below_silence_threshold(257 / 16000)
    assert below_silence_threshold(511 / 16000)
    assert not below_silence_threshold(512 / 16000)


def test_predicate_evaluations_are_stable():
    first = below_silence_threshold(0.02)
    assert all(below_silence_threshold(0.02) == first for _ in range(3))


# --- Payload shape across the sub-frame band ---------------------------------


@pytest.mark.parametrize('duration', [0.001, 0.02, 0.0319])
def test_persisted_audio_seconds_equal_the_admitted_extent(monkeypatch, duration):
    adapter = Mock(return_value=silence(duration))
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    worker, _, saved, *_rest = setup_worker(vad=Mock(return_value=[]))
    worker.process_batch([item('sub', duration)])
    assert saved['sub']['audio_seconds'] == pytest.approx(duration)


def test_persisted_payload_keeps_the_silence_outcome_field(monkeypatch):
    adapter = Mock(return_value=silence())
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    worker, _, saved, *_rest = setup_worker(vad=Mock(return_value=[]))
    worker.process_batch([item('sub', 0.02)])
    assert saved['sub']['diarization']['outcome'] == 'silence'


def test_persisted_payload_has_no_turns_for_sub_frame_silence(monkeypatch):
    adapter = Mock(return_value=silence())
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    worker, _, saved, *_rest = setup_worker(vad=Mock(return_value=[]))
    worker.process_batch([item('sub', 0.02)])
    assert saved['sub']['diarization']['turns'] == []


# --- Real strict inspector through the worker --------------------------------


def real_decode(work):
    return np.zeros(int(work.duration_seconds * 16000), dtype=np.float32)


def test_worker_with_real_strict_inspector_disposes_a_20ms_unit(monkeypatch):
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', batch_pipeline.inspect_worker_silence)
    worker, *_rest = setup_worker(decode=real_decode, vad=Mock(side_effect=AssertionError('model VAD must not run')))
    results = worker.process_batch([item('sub', 0.02)])
    assert results[0].outcome == 'silence'


def test_worker_with_real_strict_inspector_disposes_a_511_sample_unit(monkeypatch):
    worker, *_rest = setup_worker(decode=real_decode, vad=Mock(side_effect=AssertionError('model VAD must not run')))
    results = worker.process_batch([item('edge', 511 / 16000)])
    assert results[0].outcome == 'silence'


def test_worker_with_real_strict_inspector_runs_the_model_from_one_frame_up(monkeypatch):
    vad = Mock(return_value=[])
    worker, *_rest = setup_worker(decode=real_decode, vad=vad)
    results = worker.process_batch([item('oneframe', 0.032)])
    assert results[0].outcome == 'silence'
    assert vad.call_count == 1


# --- Short-speech and safety-net interplay ------------------------------------


def test_short_speech_single_flag_is_irrelevant_for_sub_frame_silence(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'true')
    adapter = Mock(return_value=silence())
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    worker, *_rest = setup_worker(vad=Mock(return_value=[]))
    results = worker.process_batch([item('sub', 0.02)])
    assert results[0].outcome == 'silence'


def test_diarize_speech_only_flag_is_irrelevant_for_sub_frame_silence(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', 'true')
    adapter = Mock(return_value=silence())
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    worker, *_rest = setup_worker(vad=Mock(return_value=[]))
    results = worker.process_batch([item('sub', 0.02)])
    assert results[0].outcome == 'silence'


def test_safety_net_on_strict_unavailable_sub_frame_falls_through(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    measured = Mock(side_effect=RuntimeError('synthetic-private-error'))
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_vad', measured)
    vad = Mock(return_value=[])
    worker, *_rest = setup_worker(vad=vad)
    results = worker.process_batch([item('sub', 0.02)])
    assert results[0].outcome == 'silence'
    assert vad.call_count == 1


def test_safety_net_on_strict_silence_measures_before_the_model_call(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    measured = Mock(return_value=(0.02, []))
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_vad', measured)
    vad = Mock(return_value=[(0, 0.02)])
    worker, *_rest = setup_worker(vad=vad)
    results = worker.process_batch([item('sub', 0.02)])
    assert results[0].outcome == 'silence'
    assert measured.call_count == 1
    assert vad.call_count == 0


# --- Batch composition edges --------------------------------------------------


def test_three_sub_frame_units_cost_three_strict_calls_and_zero_model_calls(monkeypatch):
    adapter = Mock(return_value=silence())
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    vad = Mock(return_value=[(0, 2.0)])
    worker, *_rest = setup_worker(vad=vad)
    results = worker.process_batch([item('s1', 0.02), item('s2', 0.01), item('s3', 0.03)])
    assert [r.outcome for r in results] == ['silence', 'silence', 'silence']
    assert adapter.call_count == 3
    assert vad.call_count == 0


def test_a_single_frame_unit_pays_the_model_but_not_the_strict_inspector(monkeypatch):
    adapter = Mock(return_value=silence())
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    vad = Mock(return_value=[])
    worker, *_rest = setup_worker(vad=vad)
    results = worker.process_batch([item('oneframe', 0.032)])
    assert results[0].outcome == 'silence'
    assert vad.call_count == 1 and adapter.call_count == 0


def test_long_unit_pays_neither_strict_nor_shortcuts(monkeypatch):
    adapter = Mock(return_value=silence())
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    vad = Mock(return_value=[(0, 2.0)])
    worker, provider, saved, *_rest = setup_worker(vad=vad)
    results = worker.process_batch([item('norm', 2.0)])
    assert results[0].outcome == 'success'
    assert adapter.call_count == 0
    assert provider.calls


# --- Framed language-blocked units keep the original arm exactly -------------


def test_framed_language_blocked_strict_failure_falls_back_to_the_model_and_raises(monkeypatch):
    # The old arm's fallback is intact: a framed language-blocked unit whose
    # strict inspector is unavailable pays the model VAD, and speech then
    # raises at the serial language barrier — never a vad_bounds quarantine.
    vad = Mock(return_value=[(0, 2.0)])
    strict_unavailable(monkeypatch)
    *_, results = run_worker(monkeypatch, key='norm', duration=2.0, vad=vad, language='zh')
    barrier = [r for r in results if isinstance(r, ValidationFailureWork)]
    assert barrier and barrier[0].reason == 'unsupported_language'


def test_framed_multi_class_unit_raises_at_the_serial_language_barrier(monkeypatch):
    # 'multi' is the default intake language: an unknown frozen class with
    # model speech windows still raises the barrier in the serial path.
    vad = Mock(return_value=[(0, 2.0)])
    strict_returns_silence(monkeypatch)
    *_, results = run_worker(monkeypatch, key='norm', duration=2.0, vad=vad, language='multi')
    barrier = [r for r in results if isinstance(r, ValidationFailureWork)]
    assert barrier and barrier[0].reason == 'unsupported_language'


def test_barrier_raise_at_the_frame_boundary_is_the_language_barrier(monkeypatch):
    # Exactly one full frame: the sub-frame arm does not run, so the framed
    # language-blocked path keeps the barrier raise for speech.
    vad = Mock(return_value=[(0, 512 / 16000)])
    strict_returns_speech(monkeypatch)
    *_, results = run_worker(monkeypatch, key='oneframe', duration=512 / 16000, vad=vad, language='zh')
    barrier = [r for r in results if isinstance(r, ValidationFailureWork)]
    assert barrier and barrier[0].reason == 'unsupported_language'


def test_framed_non_blocked_units_pay_zero_strict_calls(monkeypatch):
    vad = Mock(return_value=[(0, 2.0)])
    mock = strict_returns_silence(monkeypatch)
    run_worker(monkeypatch, key='norm', duration=2.0, vad=vad, language='en')
    assert mock.call_count == 0


def test_vad_bounds_error_str_is_the_closed_reason_token():
    error = BatchValidationError(ValidationReason.VAD_BOUNDS)
    assert str(error) == 'vad_bounds' and error.reason == 'vad_bounds'


def test_strict_arm_receives_the_decoded_samples_for_the_unit(monkeypatch):
    seen = {}

    def spy(item_work, samples):
        seen['samples'] = len(samples)
        return silence()

    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', spy)
    worker, *_rest = setup_worker(vad=Mock(return_value=[]))
    worker.process_batch([item('sub', 0.02)])
    assert seen['samples'] == 320


@pytest.mark.parametrize('duration', [0.001, 0.02, 0.0319])
def test_sub_frame_arm_runs_for_every_duration_below_one_frame(monkeypatch, duration):
    vad = Mock(return_value=[(0, duration)])
    adapter = Mock(return_value=silence(duration))
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    worker, *_rest = setup_worker(vad=vad)
    results = worker.process_batch([item('sub', duration)])
    assert results[0].outcome == 'silence'
    assert adapter.call_count == 1 and vad.call_count == 0


def test_vad_bounds_disposition_for_framed_units_consults_strict_once(monkeypatch):
    adapter = Mock(return_value=silence())
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', adapter)
    worker, *_rest = setup_worker(vad=vad_bounds_vad())
    results = worker.process_batch([item('norm', 2.0)])
    assert results[0].outcome == 'silence'
    assert adapter.call_count == 1
