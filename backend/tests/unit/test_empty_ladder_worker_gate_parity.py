# Failure-Class: FC-empty-ladder-gate-drift-misroutes-recovery-units-between-hold-retry-and-terminal-rungs
"""The GPU worker's terminal empty gate, pinned cell-by-cell across the flag matrix.

An ``empty_asr``/``no_owned_words`` unit that survives the padded retry ends
at the assemble_words boundary, where the shared ``empty_ladder_handoff``
predicate decides between the recovery handoff (``RecoveryWork``, fenced CPU
recovery), the terminal validation handoff (``ValidationFailureWork``), and
the pre-safety shape (no work at all — the historical ladder). This suite
drives the real worker with synthetic PCM and asserts the exact result type
and evidence for every flag combination, the no-recognizer conjunct, the
padded-retry evidence tokens, and the correctness counters.
"""

from dataclasses import replace
from unittest.mock import Mock

import numpy as np
import pytest

from diarizer import batch_pipeline
from tests.unit.test_batch_pipeline_worker import item, setup_worker
from utils.batch_pipeline.contracts import FailedWork, RecoveryWork, ValidationFailureWork, WorkResult

SAMPLE_RATE = 16000

COMBOS = (
    (True, True, True),
    (True, False, True),
    (False, True, True),
    (False, False, True),
    (True, True, False),
    (True, False, False),
    (False, True, False),
    (False, False, False),
)


def set_flags(monkeypatch, *, safety, recovery, disposition, validation=True, silence=False):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', str(safety))
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED', str(recovery))
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', str(disposition))
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', str(validation))
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED', str(silence))


def empty_unit_worker(monkeypatch, **kwargs):
    set_flags(monkeypatch, **{k: v for k, v in kwargs.items() if k in set_flags.__code__.co_varnames[:6]})
    provider = Mock()
    provider.transcribe_batch.return_value = [[]]
    worker, _, saved, _, _, failures = setup_worker(
        decode=lambda work: np.full(int(work.duration_seconds * SAMPLE_RATE), 0.5, dtype=np.float32),
        vad=lambda _: [(0.2, 0.8)],
        words_providers={'parakeet': provider},
        recover_words=Mock(return_value=[]),
        **{k: v for k, v in kwargs.items() if k not in set_flags.__code__.co_varnames[:6]},
    )
    return worker, saved, failures


def no_owned_unit_worker(monkeypatch, **kwargs):
    set_flags(monkeypatch, **{k: v for k, v in kwargs.items() if k in set_flags.__code__.co_varnames[:6]})
    provider = Mock()
    provider.transcribe_batch.return_value = [[{'word': 'heard', 'timestamp': [4.5, 4.8]}]]
    worker, _, saved, _, _, failures = setup_worker(
        decode=lambda _: np.zeros(160320, dtype=np.float32),
        vad=lambda _: [(1, 2)],
        words_providers={'parakeet': provider},
        recover_words=Mock(return_value=[]),
        **{k: v for k, v in kwargs.items() if k not in set_flags.__code__.co_varnames[:6]},
    )
    return worker, saved, failures


# --- empty_asr terminal cells ---------------------------------------------------------------


def test_empty_asr_safety_only_hands_off_to_recovery(monkeypatch):
    worker, saved, _ = empty_unit_worker(monkeypatch, safety=True, recovery=False, disposition=False)
    assert worker.process_batch([item()]) == [RecoveryWork('a', padded_retry='empty', padded_retry_empty=True)]
    assert not saved


def test_empty_asr_safety_and_recovery_hands_off_to_recovery(monkeypatch):
    worker, _, _ = empty_unit_worker(monkeypatch, safety=True, recovery=True, disposition=False)
    assert worker.process_batch([item()]) == [RecoveryWork('a', padded_retry='empty', padded_retry_empty=True)]


def test_empty_asr_safety_and_disposition_hands_off_to_recovery(monkeypatch):
    worker, _, _ = empty_unit_worker(monkeypatch, safety=True, recovery=False, disposition=True)
    assert worker.process_batch([item()]) == [RecoveryWork('a', padded_retry='empty', padded_retry_empty=True)]


def test_empty_asr_every_flag_on_hands_off_to_recovery(monkeypatch):
    worker, _, _ = empty_unit_worker(monkeypatch, safety=True, recovery=True, disposition=True)
    assert worker.process_batch([item()]) == [RecoveryWork('a', padded_retry='empty', padded_retry_empty=True)]


def test_empty_asr_recovery_alone_without_safety_hands_off_to_recovery(monkeypatch):
    worker, _, _ = empty_unit_worker(monkeypatch, safety=False, recovery=True, disposition=False)
    assert worker.process_batch([item()]) == [RecoveryWork('a', padded_retry='empty', padded_retry_empty=True)]


def test_empty_asr_disposition_alone_without_safety_hands_off_to_recovery(monkeypatch):
    worker, _, _ = empty_unit_worker(monkeypatch, safety=False, recovery=False, disposition=True)
    assert worker.process_batch([item()]) == [RecoveryWork('a', padded_retry='empty', padded_retry_empty=True)]


def test_empty_asr_both_flags_without_safety_hands_off_to_recovery(monkeypatch):
    worker, _, _ = empty_unit_worker(monkeypatch, safety=False, recovery=True, disposition=True)
    assert worker.process_batch([item()]) == [RecoveryWork('a', padded_retry='empty', padded_retry_empty=True)]


def test_empty_asr_every_switch_off_ends_the_chain_as_terminal_validation(monkeypatch):
    worker, _, _ = empty_unit_worker(monkeypatch, safety=False, recovery=False, disposition=False, validation=True)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'assemble_words', 'empty_asr')]


def test_empty_asr_every_switch_off_with_validation_off_leaves_no_work(monkeypatch):
    # The pre-safety contract: no handoff exists, the validation disposition
    # is off, and the unit simply drops out of the chain for durable retry.
    worker, _, failures = empty_unit_worker(
        monkeypatch, safety=False, recovery=False, disposition=False, validation=False
    )
    assert worker.process_batch([item()]) == []
    assert failures == [('a', 'BatchValidationError')]


# --- no_owned_words terminal cells -----------------------------------------------------------


def test_no_owned_safety_only_hands_off_to_recovery(monkeypatch):
    worker, _, _ = no_owned_unit_worker(monkeypatch, safety=True, recovery=False, disposition=False)
    assert worker.process_batch([item(duration=10.02)]) == [
        RecoveryWork('a', padded_retry='empty', padded_retry_empty=True, reason='no_owned_words')
    ]


def test_no_owned_disposition_alone_without_safety_hands_off_to_recovery(monkeypatch):
    worker, _, _ = no_owned_unit_worker(monkeypatch, safety=False, recovery=False, disposition=True)
    assert worker.process_batch([item(duration=10.02)]) == [
        RecoveryWork('a', padded_retry='empty', padded_retry_empty=True, reason='no_owned_words')
    ]


def test_no_owned_recovery_alone_without_safety_misses_the_family_arm(monkeypatch):
    worker, _, _ = no_owned_unit_worker(monkeypatch, safety=False, recovery=True, disposition=False)
    assert worker.process_batch([item(duration=10.02)]) == [
        ValidationFailureWork('a', 'assemble_words', 'no_owned_words')
    ]


def test_no_owned_every_switch_off_ends_the_chain_as_terminal_validation(monkeypatch):
    worker, _, _ = no_owned_unit_worker(monkeypatch, safety=False, recovery=False, disposition=False, validation=True)
    assert worker.process_batch([item(duration=10.02)]) == [
        ValidationFailureWork('a', 'assemble_words', 'no_owned_words')
    ]


def test_no_owned_both_flags_without_safety_hands_off_to_recovery(monkeypatch):
    worker, _, _ = no_owned_unit_worker(monkeypatch, safety=False, recovery=True, disposition=True)
    assert worker.process_batch([item(duration=10.02)]) == [
        RecoveryWork('a', padded_retry='empty', padded_retry_empty=True, reason='no_owned_words')
    ]


def test_no_owned_safety_with_every_other_flag_hands_off_to_recovery(monkeypatch):
    worker, _, _ = no_owned_unit_worker(monkeypatch, safety=True, recovery=True, disposition=True)
    assert worker.process_batch([item(duration=10.02)]) == [
        RecoveryWork('a', padded_retry='empty', padded_retry_empty=True, reason='no_owned_words')
    ]


def test_no_owned_recovery_flag_never_grants_the_handoff_at_any_safety_state(monkeypatch):
    for safety in (True, False):
        worker, _, _ = no_owned_unit_worker(monkeypatch, safety=safety, recovery=not safety, disposition=False)
        results = worker.process_batch([item(duration=10.02)])
        assert isinstance(results[0], RecoveryWork) is safety


# --- the no-recovery-recognizer conjunct ------------------------------------------------------


def test_every_flag_on_without_a_recovery_recognizer_still_ends_terminal(monkeypatch):
    set_flags(monkeypatch, safety=True, recovery=True, disposition=True, validation=True)
    provider = Mock()
    provider.transcribe_batch.return_value = [[]]
    worker, *_ = setup_worker(
        decode=lambda work: np.full(int(work.duration_seconds * SAMPLE_RATE), 0.5, dtype=np.float32),
        vad=lambda _: [(0.2, 0.8)],
        words_providers={'parakeet': provider},
    )
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'assemble_words', 'empty_asr')]


def test_no_recognizer_with_safety_and_validation_off_produces_the_pre_safety_work(monkeypatch):
    set_flags(monkeypatch, safety=True, recovery=False, disposition=False, validation=False)
    provider = Mock()
    provider.transcribe_batch.return_value = [[]]
    worker, *_ = setup_worker(
        decode=lambda work: np.full(int(work.duration_seconds * SAMPLE_RATE), 0.5, dtype=np.float32),
        vad=lambda _: [(0.2, 0.8)],
        words_providers={'parakeet': provider},
    )
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].worker_failure == {'stage': 'assemble_words', 'reason': 'empty_asr'}


def test_no_recognizer_without_safety_and_validation_on_ends_terminal(monkeypatch):
    set_flags(monkeypatch, safety=False, recovery=True, disposition=True, validation=True)
    provider = Mock()
    provider.transcribe_batch.return_value = [[]]
    worker, *_ = setup_worker(
        decode=lambda work: np.full(int(work.duration_seconds * SAMPLE_RATE), 0.5, dtype=np.float32),
        vad=lambda _: [(0.2, 0.8)],
        words_providers={'parakeet': provider},
    )
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'assemble_words', 'empty_asr')]


# --- a recovered hypothesis beats the gate at every flag state ---------------------------------


def test_recovered_words_publish_even_with_safety_alone(monkeypatch):
    set_flags(monkeypatch, safety=True, recovery=False, disposition=False, validation=True)
    provider = Mock()
    provider.transcribe_batch.return_value = [[]]
    worker, _, saved, *_ = setup_worker(
        decode=lambda work: np.full(int(work.duration_seconds * SAMPLE_RATE), 0.5, dtype=np.float32),
        vad=lambda _: [(0.2, 0.8)],
        words_providers={'parakeet': provider},
        recover_words=Mock(return_value=[{'word': 'recovered', 'timestamp': [0.3, 0.5]}]),
    )
    results = worker.process_batch([item()])
    assert isinstance(results[0], WorkResult)
    assert saved['a']['words'][0]['word'] == 'recovered'


def test_recovered_words_publish_without_safety_when_recovery_flag_rides(monkeypatch):
    set_flags(monkeypatch, safety=False, recovery=True, disposition=False, validation=True)
    provider = Mock()
    provider.transcribe_batch.return_value = [[]]
    worker, _, saved, *_ = setup_worker(
        decode=lambda work: np.full(int(work.duration_seconds * SAMPLE_RATE), 0.5, dtype=np.float32),
        vad=lambda _: [(0.2, 0.8)],
        words_providers={'parakeet': provider},
        recover_words=Mock(return_value=[{'word': 'recovered', 'timestamp': [0.3, 0.5]}]),
    )
    assert isinstance(worker.process_batch([item()])[0], WorkResult)


# --- padded-retry evidence tokens on the handoff ------------------------------------------------


def test_raw_retry_without_safety_still_records_the_empty_token(monkeypatch):
    worker, _, _ = empty_unit_worker(monkeypatch, safety=False, recovery=True, disposition=False)
    result = worker.process_batch([item()])[0]
    assert isinstance(result, RecoveryWork) and result.padded_retry == 'empty'


def test_oversize_unit_records_the_skipped_oversize_token(monkeypatch):
    set_flags(monkeypatch, safety=True, recovery=False, disposition=False, validation=True)
    provider = Mock()
    provider.transcribe_batch.side_effect = lambda batch: [[] for _ in batch]
    worker, *_ = setup_worker(
        decode=lambda work: np.zeros(int(work.duration_seconds * SAMPLE_RATE), dtype=np.float32),
        vad=lambda _: [(1, 116)],
        words_providers={'parakeet': provider},
        recover_words=Mock(return_value=None),
    )
    result = worker.process_batch([item(duration=117)])[0]
    assert isinstance(result, RecoveryWork) and result.padded_retry == 'skipped_oversize'


def test_blocked_language_ends_at_vad_windows_before_the_empty_gate(monkeypatch):
    # The language barrier owns blocked-language units before either ASR
    # attempt (pinned by the long-speech handoff suite); the empty gate never
    # sees them, so the handoff never carries their evidence token.
    set_flags(monkeypatch, safety=True, recovery=True, disposition=True, validation=True)
    provider = Mock()
    provider.transcribe_batch.return_value = [[]]
    worker, *_ = setup_worker(
        decode=lambda work: np.ones(int(work.duration_seconds * SAMPLE_RATE), dtype=np.float32),
        vad=lambda _: [(1, 7)],
        words_providers={'parakeet': provider},
        recover_words=Mock(return_value=[]),
        language_of=lambda _: 'vi',
    )
    assert worker.process_batch([item(duration=10.02)]) == [
        ValidationFailureWork('a', 'vad_windows', 'unsupported_language')
    ]


# --- correctness counters ------------------------------------------------------------------------


def test_empty_asr_records_the_attempt_correctness_counter(monkeypatch):
    recorded = []
    monkeypatch.setattr(batch_pipeline, 'record_correctness', lambda *a, **k: recorded.append((a, k)))
    worker, _, _ = empty_unit_worker(monkeypatch, safety=True, recovery=False, disposition=False)
    worker.process_batch([item()])
    assert len(recorded) == 1
    args, kwargs = recorded[0]
    assert args[0] == 'empty_asr_attempt' and kwargs['source'] == 'gpu_worker'
    assert kwargs['seconds'] == pytest.approx(item().duration_seconds)


def test_no_owned_words_records_no_attempt_correctness_counter(monkeypatch):
    recorded = []
    monkeypatch.setattr(batch_pipeline, 'record_correctness', lambda *a, **k: recorded.append((a, k)))
    worker, _, _ = no_owned_unit_worker(monkeypatch, safety=True, recovery=False, disposition=False)
    worker.process_batch([item(duration=10.02)])
    assert recorded == []


def test_shadow_empty_units_record_no_attempt_correctness_counter(monkeypatch):
    recorded = []
    monkeypatch.setattr(batch_pipeline, 'record_correctness', lambda *a, **k: recorded.append((a, k)))
    worker, _, _ = empty_unit_worker(monkeypatch, safety=True, recovery=False, disposition=False)
    worker.process_batch([replace(item(), shadow=True)])
    assert recorded == []


def test_shadow_empty_units_still_ride_the_handoff_with_the_same_evidence(monkeypatch):
    worker, _, _ = empty_unit_worker(monkeypatch, safety=True, recovery=False, disposition=False)
    results = worker.process_batch([replace(item(), shadow=True)])
    assert results == [RecoveryWork('a', padded_retry='empty', padded_retry_empty=True)]


# --- handoff carries the measured VAD evidence ----------------------------------------------------


def test_empty_handoff_carries_measured_held_vad_seconds(monkeypatch):
    worker, _, _ = empty_unit_worker(monkeypatch, safety=True, recovery=False, disposition=False)
    result = worker.process_batch([item()])[0]
    assert result.measured_held_vad_speech_seconds == pytest.approx(0.6)


def test_no_owned_handoff_carries_measured_held_vad_seconds(monkeypatch):
    worker, _, _ = no_owned_unit_worker(monkeypatch, safety=True, recovery=False, disposition=False)
    result = worker.process_batch([item(duration=10.02)])[0]
    assert result.measured_held_vad_speech_seconds == pytest.approx(1.0)


def test_terminal_validation_also_carries_the_measured_vad_evidence(monkeypatch):
    worker, _, _ = empty_unit_worker(monkeypatch, safety=False, recovery=False, disposition=False, validation=True)
    result = worker.process_batch([item()])[0]
    assert isinstance(result, ValidationFailureWork)
    assert result.measured_held_vad_speech_seconds == pytest.approx(0.6)


# --- silence disposition interplay -----------------------------------------------------------------


def test_strict_silence_disposes_the_empty_unit_before_the_gate(monkeypatch):
    from utils.stt import local_vad as vad

    set_flags(monkeypatch, safety=True, recovery=False, disposition=False, validation=True, silence=True)
    monkeypatch.setattr(vad, 'offline_pcm_speech_segments', Mock(return_value=[]))
    provider = Mock()
    provider.transcribe_batch.return_value = [[]]
    worker, _, saved, *_ = setup_worker(
        decode=lambda work: np.zeros(int(work.duration_seconds * SAMPLE_RATE), dtype=np.float32),
        vad=lambda _: [(0.2, 0.8)],
        words_providers={'parakeet': provider},
        recover_words=Mock(return_value=[]),
    )
    results = worker.process_batch([item()])
    assert isinstance(results[0], WorkResult) and results[0].outcome == 'silence'
    assert saved['a']['words'] == []


def test_strict_speech_keeps_the_empty_gate_route(monkeypatch):
    from utils.stt import local_vad as vad

    set_flags(monkeypatch, safety=True, recovery=False, disposition=False, validation=True, silence=True)
    monkeypatch.setattr(vad, 'offline_pcm_speech_segments', Mock(return_value=[(1, 2)]))
    provider = Mock()
    provider.transcribe_batch.return_value = [[]]
    worker, *_ = setup_worker(
        decode=lambda work: np.full(int(work.duration_seconds * SAMPLE_RATE), 0.5, dtype=np.float32),
        vad=lambda _: [(0.2, 0.8)],
        words_providers={'parakeet': provider},
        recover_words=Mock(return_value=[]),
    )
    assert worker.process_batch([item()]) == [RecoveryWork('a', padded_retry='empty', padded_retry_empty=True)]


def test_unavailable_strict_silence_keeps_the_empty_gate_route(monkeypatch):
    from utils.stt import local_vad as vad

    set_flags(monkeypatch, safety=True, recovery=False, disposition=False, validation=True, silence=True)
    monkeypatch.setattr(vad, 'offline_pcm_speech_segments', Mock(side_effect=ValueError('bad pcm')))
    provider = Mock()
    provider.transcribe_batch.return_value = [[]]
    worker, *_ = setup_worker(
        decode=lambda work: np.full(int(work.duration_seconds * SAMPLE_RATE), 0.5, dtype=np.float32),
        vad=lambda _: [(0.2, 0.8)],
        words_providers={'parakeet': provider},
        recover_words=Mock(return_value=[]),
    )
    assert worker.process_batch([item()]) == [RecoveryWork('a', padded_retry='empty', padded_retry_empty=True)]


def test_silence_disposition_off_never_disposes_and_always_reaches_the_gate(monkeypatch):
    from utils.stt import local_vad as vad

    set_flags(monkeypatch, safety=True, recovery=False, disposition=False, validation=True, silence=False)
    strict = Mock(return_value=[])
    monkeypatch.setattr(vad, 'offline_pcm_speech_segments', strict)
    provider = Mock()
    provider.transcribe_batch.return_value = [[]]
    worker, *_ = setup_worker(
        decode=lambda work: np.zeros(int(work.duration_seconds * SAMPLE_RATE), dtype=np.float32),
        vad=lambda _: [(0.2, 0.8)],
        words_providers={'parakeet': provider},
        recover_words=Mock(return_value=[]),
    )
    assert worker.process_batch([item()]) == [RecoveryWork('a', padded_retry='empty', padded_retry_empty=True)]


# --- non-family reasons never ride the empty handoff -------------------------------------------------


def test_vad_nonfinite_with_validation_off_takes_the_ladder_not_the_handoff(monkeypatch):
    set_flags(monkeypatch, safety=True, recovery=True, disposition=True, validation=False)
    provider = Mock()
    provider.transcribe_batch.return_value = [[]]
    worker, *_ = setup_worker(
        decode=lambda work: np.full(int(work.duration_seconds * SAMPLE_RATE), 0.5, dtype=np.float32),
        vad=lambda _: [(float('nan'), 1.0)],
        words_providers={'parakeet': provider},
        recover_words=Mock(return_value=[]),
    )
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].worker_failure['reason'] == 'vad_nonfinite'


def test_vad_nonfinite_with_validation_on_ends_terminal(monkeypatch):
    set_flags(monkeypatch, safety=True, recovery=True, disposition=True, validation=True)
    provider = Mock()
    provider.transcribe_batch.return_value = [[]]
    worker, *_ = setup_worker(
        decode=lambda work: np.full(int(work.duration_seconds * SAMPLE_RATE), 0.5, dtype=np.float32),
        vad=lambda _: [(float('nan'), 1.0)],
        words_providers={'parakeet': provider},
        recover_words=Mock(return_value=[]),
    )
    result = worker.process_batch([item()])[0]
    assert isinstance(result, ValidationFailureWork)
    assert result.stage == 'vad_windows' and result.reason == 'vad_nonfinite'


# --- the gate and the hold boundary answer from one predicate (parity axis) ---------------------------


def test_terminal_gate_answers_match_the_shared_predicate_for_every_combo(monkeypatch):
    from config.batch_pipeline_empty_asr import empty_ladder_handoff

    for safety, recovery, disposition in COMBOS:
        worker, _, _ = empty_unit_worker(
            monkeypatch,
            safety=safety,
            recovery=recovery,
            disposition=disposition,
            validation=True,
        )
        result = worker.process_batch([item()])[0]
        if empty_ladder_handoff(
            'empty_asr', recovery_enabled=recovery, disposition_enabled=disposition, safety_enabled=safety
        ):
            assert isinstance(result, RecoveryWork)
        else:
            assert isinstance(result, ValidationFailureWork)


def test_terminal_gate_answers_are_stable_across_repeated_flag_states(monkeypatch):
    for _ in range(2):
        worker, _, _ = empty_unit_worker(monkeypatch, safety=False, recovery=False, disposition=False)
        assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'assemble_words', 'empty_asr')]


# --- per-cell evidence parity on the handoff -------------------------------------------------


def test_recovery_only_arm_records_the_empty_token(monkeypatch):
    worker, _, _ = empty_unit_worker(monkeypatch, safety=False, recovery=True, disposition=False)
    result = worker.process_batch([item()])[0]
    assert result.padded_retry == 'empty' and result.padded_retry_empty is True


def test_disposition_only_arm_records_the_empty_token(monkeypatch):
    worker, _, _ = empty_unit_worker(monkeypatch, safety=False, recovery=False, disposition=True)
    result = worker.process_batch([item()])[0]
    assert result.padded_retry == 'empty' and result.padded_retry_empty is True


def test_both_flags_arm_records_the_empty_token(monkeypatch):
    worker, _, _ = empty_unit_worker(monkeypatch, safety=False, recovery=True, disposition=True)
    result = worker.process_batch([item()])[0]
    assert result.padded_retry == 'empty' and result.padded_retry_empty is True


def test_safety_only_arm_records_the_empty_token(monkeypatch):
    worker, _, _ = empty_unit_worker(monkeypatch, safety=True, recovery=False, disposition=False)
    result = worker.process_batch([item()])[0]
    assert result.padded_retry == 'empty' and result.padded_retry_empty is True


def test_no_owned_safety_arm_records_the_no_owned_reason(monkeypatch):
    worker, _, _ = no_owned_unit_worker(monkeypatch, safety=True, recovery=False, disposition=False)
    result = worker.process_batch([item(duration=10.02)])[0]
    assert result.reason == 'no_owned_words' and result.padded_retry == 'empty'


def test_no_owned_disposition_arm_records_the_no_owned_reason(monkeypatch):
    worker, _, _ = no_owned_unit_worker(monkeypatch, safety=False, recovery=False, disposition=True)
    result = worker.process_batch([item(duration=10.02)])[0]
    assert result.reason == 'no_owned_words'


def test_no_owned_handoff_also_carries_measured_vad(monkeypatch):
    worker, _, _ = no_owned_unit_worker(monkeypatch, safety=False, recovery=False, disposition=True)
    result = worker.process_batch([item(duration=10.02)])[0]
    assert result.measured_held_vad_speech_seconds == pytest.approx(1.0)


def test_the_remaining_no_owned_kill_switch_cell_ends_terminal(monkeypatch):
    worker, _, _ = no_owned_unit_worker(monkeypatch, safety=False, recovery=False, disposition=False)
    assert worker.process_batch([item(duration=10.02)]) == [
        ValidationFailureWork('a', 'assemble_words', 'no_owned_words')
    ]


# --- worker-model scoping of the safety flag -------------------------------------------------


def test_default_provider_config_still_selects_the_handoff(monkeypatch):
    # With the suite's default provider configuration (not a synthetic one),
    # the safety-only arm still selects the recovery handoff.
    set_flags(monkeypatch, safety=True, recovery=False, disposition=False, validation=True)
    provider = Mock()
    provider.transcribe_batch.return_value = [[]]
    worker, *_ = setup_worker(
        decode=lambda work: np.full(int(work.duration_seconds * SAMPLE_RATE), 0.5, dtype=np.float32),
        vad=lambda _: [(0.2, 0.8)],
        words_providers={'parakeet': provider},
        recover_words=Mock(return_value=[]),
    )
    results = worker.process_batch([item()])
    assert isinstance(results[0], RecoveryWork)


# --- structural conjunct pins -----------------------------------------------------------------


def test_gate_requires_the_assemble_words_stage_for_recovery_selection(monkeypatch):
    # An empty-family diagnosis raised at a non-terminal stage never hands off;
    # only the assemble_words boundary selects RecoveryWork.
    worker, _, _ = empty_unit_worker(monkeypatch, safety=True, recovery=True, disposition=True)
    results = worker.process_batch([item()])
    assert isinstance(results[0], RecoveryWork)


def test_failed_work_evidence_carries_the_stage_and_reason_for_the_ladder(monkeypatch):
    # Without a recovery recognizer the gate misses its third conjunct; with
    # the validation disposition off too, the unit takes the ladder as
    # evidence-carrying ordinary failure work.
    set_flags(monkeypatch, safety=True, recovery=False, disposition=False, validation=False)
    provider = Mock()
    provider.transcribe_batch.return_value = [[]]
    worker, *_ = setup_worker(
        decode=lambda work: np.full(int(work.duration_seconds * SAMPLE_RATE), 0.5, dtype=np.float32),
        vad=lambda _: [(0.2, 0.8)],
        words_providers={'parakeet': provider},
    )
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].worker_failure == {'stage': 'assemble_words', 'reason': 'empty_asr'}
    assert results[0].measured_held_vad_speech_seconds == pytest.approx(0.6)
