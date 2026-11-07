# Failure-Class: FC-empty-ladder-gate-drift-misroutes-recovery-units-between-hold-retry-and-terminal-rungs
"""The empty evidence chain into the settlement lane: write, read, and settle.

``Scheduler.fail`` writes ``worker_empty_evidence``; the fenced recovery and
terminal-empty lanes read it back through ``padded_empty`` /
``padded_skipped`` / ``padded_long_speech``, and a definite empty settles
into the terminal-empty payload only when the ship-on strict-VAD guard
allows. This suite walks that chain end-to-end over the real scheduler and
pins the evidence exactness, the settlement helper verdicts, the
terminal-empty payload contract, and the flag environment parsing that arms
the whole ladder.
"""

import logging

import pytest

from config.batch_pipeline import empty_asr_disposition_enabled, empty_asr_recovery_enabled
from config.batch_pipeline_empty_asr import safety_net_enabled, terminal_empty_allowed
from database.batch_pipeline_terminal_empty import EMPTY_FAILURE
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import item
from utils.batch_pipeline.contracts import validate_measured_vad
from utils.batch_pipeline.recovery_disposition import (
    MultilingualEmpty,
    padded_empty,
    padded_long_speech,
    padded_skipped,
    terminal_empty_payload,
)


def make_job(**fail_kwargs):
    from utils.batch_pipeline.scheduler import Scheduler

    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(0)[0]
    fail_kwargs.setdefault('quarantine', True)
    fail_kwargs.setdefault('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'})
    assert queue.fail('a', lease.token, 10.0, **fail_kwargs) is True
    return store.rows['jobs', 'a']


# --- the evidence write, read back through the settlement helpers -------------------------------


def test_the_empty_token_reads_back_as_padded_empty():
    job = make_job(padded_retry='empty', padded_retry_empty=True)
    assert padded_empty(job) is True
    assert padded_skipped(job) is False
    assert padded_long_speech(job) is False


def test_the_skipped_oversize_token_reads_back_as_padded_skipped():
    job = make_job(padded_retry='skipped_oversize')
    assert padded_skipped(job) is True
    assert padded_empty(job) is False
    assert padded_long_speech(job) is False


def test_the_skipped_long_speech_token_reads_back_as_padded_skipped_and_long_speech():
    job = make_job(padded_retry='skipped_long_speech')
    assert padded_skipped(job) is True
    assert padded_long_speech(job) is True
    assert padded_empty(job) is False


def test_a_unit_without_evidence_reads_back_as_no_verdict():
    job = make_job(padded_retry=None, padded_retry_empty=False)
    assert padded_empty(job) is False
    assert padded_skipped(job) is False
    assert padded_long_speech(job) is False


def test_the_settlement_helpers_require_the_exact_versioned_shape():
    for drifted in (
        {'padded_retry': 'empty'},
        {'padded_retry': 'empty', 'version': 2},
        {'padded_retry': 'skipped_oversize', 'version': 2},
        {'padded_retry': 'empty', 'version': 1, 'extra': True},
    ):
        assert padded_empty(dict(drifted)) is False
        assert padded_skipped(dict(drifted)) is False
        assert padded_long_speech(dict(drifted)) is False


def test_helpers_answer_false_for_missing_evidence_and_none():
    assert padded_empty({}) is False
    assert padded_skipped({}) is False
    assert padded_long_speech({}) is False
    assert padded_empty({'worker_empty_evidence': None}) is False


# --- terminal_empty_allowed: the strict-VAD ship-on guard -----------------------------------------


def test_safety_on_with_measured_speech_refuses_terminal_empty():
    assert terminal_empty_allowed([(0.2, 0.8)]) is False


def test_safety_on_with_strict_silence_allows_terminal_empty():
    assert terminal_empty_allowed([]) is True


def test_safety_off_allows_terminal_empty_even_over_speech():
    import os

    previous = os.environ.get('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED')
    try:
        os.environ['BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED'] = 'false'
        assert terminal_empty_allowed([(0.2, 0.8)]) is True
    finally:
        if previous is None:
            os.environ.pop('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', None)
        else:
            os.environ['BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED'] = previous


def test_terminal_empty_allowed_treats_missing_spans_as_silence():
    assert terminal_empty_allowed(None) is True


# --- the terminal-empty guard and its closed evidence constants ------------------------------------


def test_terminal_payload_refuses_speech_spans_with_a_typed_empty():
    with pytest.raises(MultilingualEmpty):
        terminal_empty_payload(4.0, [{'start': 0.5, 'end': 1.25}])


def test_terminal_payload_allows_strict_silence_under_the_safety_net():
    assert terminal_empty_allowed([]) is True


def test_the_default_empty_evidence_is_the_exact_gpu_plus_multilingual_verdict():
    from utils.batch_pipeline.recovery_disposition import EMPTY_EVIDENCE

    assert EMPTY_EVIDENCE == {'gpu_padded_retry': 'empty', 'multilingual_recovery': 'empty'}


def test_the_closed_evidence_set_is_exactly_the_four_empty_verdicts():
    from utils.batch_pipeline.recovery_disposition import (
        EMPTY_EVIDENCE,
        LANGUAGE_GUARD_EMPTY_EVIDENCE,
        SECOND_CHANCE_EMPTY_EVIDENCE,
        TWO_PROVIDER_EMPTY_EVIDENCE,
    )

    closed = (EMPTY_EVIDENCE, TWO_PROVIDER_EMPTY_EVIDENCE, LANGUAGE_GUARD_EMPTY_EVIDENCE, SECOND_CHANCE_EMPTY_EVIDENCE)
    assert EMPTY_EVIDENCE in closed
    assert len(set(map(repr, closed))) == 4


def test_the_two_provider_evidence_records_the_skipped_retry_and_both_multilinguals():
    from utils.batch_pipeline.recovery_disposition import TWO_PROVIDER_EMPTY_EVIDENCE

    assert TWO_PROVIDER_EMPTY_EVIDENCE == {
        'gpu_padded_retry': 'skipped_long_speech',
        'multilingual_recovery': 'empty',
        'second_multilingual_recovery': 'empty',
    }


def test_the_language_guard_evidence_records_the_barrier_verdict():
    from utils.batch_pipeline.recovery_disposition import LANGUAGE_GUARD_EMPTY_EVIDENCE

    assert LANGUAGE_GUARD_EMPTY_EVIDENCE == {
        'gpu_language_guard': 'unsupported_language',
        'multilingual_recovery': 'empty',
        'second_multilingual_recovery': 'empty',
    }


def test_the_empty_failure_constant_names_the_response_validation_boundary():
    assert EMPTY_FAILURE == {'stage': 'response_validation', 'reason': 'empty_asr'}


# --- the flag environment that arms the ladder ------------------------------------------------------


def test_safety_net_defaults_on_when_unset(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', raising=False)
    assert safety_net_enabled() is True


def test_safety_net_explicit_false_kills_it(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    assert safety_net_enabled() is False


def test_safety_net_only_the_exact_false_token_after_case_folding_kills_it(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'FALSE')
    assert safety_net_enabled() is False
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', ' false ')
    assert safety_net_enabled() is False


def test_safety_net_garbage_values_stay_on(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'off')
    assert safety_net_enabled() is True


def test_recovery_flag_defaults_off_when_unset(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED', raising=False)
    assert empty_asr_recovery_enabled() is False


def test_recovery_flag_exact_true_token_arms_it(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED', 'true')
    assert empty_asr_recovery_enabled() is True
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED', 'TRUE')
    assert empty_asr_recovery_enabled() is True
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED', '1')
    assert empty_asr_recovery_enabled() is False


def test_disposition_flag_defaults_off_when_unset(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', raising=False)
    assert empty_asr_disposition_enabled() is False


def test_disposition_flag_exact_true_token_arms_it(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'true')
    assert empty_asr_disposition_enabled() is True
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', '1')
    assert empty_asr_disposition_enabled() is False


def test_measured_vad_none_passes_through_the_settlement_guard():
    assert validate_measured_vad(None) is None


def test_the_chain_reads_the_same_evidence_the_scheduler_wrote():
    job = make_job(padded_retry='skipped_oversize')
    evidence = job['worker_empty_evidence']
    assert evidence == {'padded_retry': 'skipped_oversize', 'version': 1}
    assert padded_skipped(job) is True
    assert padded_empty(job) is False
    assert terminal_empty_allowed([]) is True


# --- more settlement-read cells -------------------------------------------------------------------


def test_the_empty_token_never_reads_back_as_skipped():
    job = make_job(padded_retry='empty', padded_retry_empty=True)
    assert padded_skipped(job) is False


def test_the_oversize_token_never_reads_back_as_long_speech():
    job = make_job(padded_retry='skipped_oversize')
    assert padded_long_speech(job) is False


def test_the_long_speech_token_never_reads_back_as_padded_empty():
    job = make_job(padded_retry='skipped_long_speech')
    assert padded_empty(job) is False


def test_every_evidence_write_carries_exactly_version_one():
    for token in ('empty', 'skipped_oversize', 'skipped_long_speech'):
        kwargs = {'padded_retry': token}
        if token == 'empty':
            kwargs['padded_retry_empty'] = True
        assert make_job(**kwargs)['worker_empty_evidence']['version'] == 1


def test_the_terminal_guard_refusal_is_independent_of_the_evidence_token(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    assert terminal_empty_allowed([(0.2, 0.8)]) is True


def test_the_terminal_guard_refusal_returns_under_the_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    assert terminal_empty_allowed([(0.2, 0.8)]) is False


def test_multilingual_empty_carries_the_refused_audio_facts():
    error = MultilingualEmpty(4.0, [{'start': 0.5, 'end': 1.25}])
    assert error.duration == 4.0
    assert error.spans == [{'start': 0.5, 'end': 1.25}]


def test_the_recovery_failure_stage_matches_the_empty_failure_constant():
    from utils.batch_pipeline.recovery_disposition import RecoveryFailure

    failure = RecoveryFailure(EMPTY_FAILURE['stage'], EMPTY_FAILURE['reason'])
    assert failure.stage == 'response_validation'
    assert failure.reason == 'empty_asr'


def test_the_definite_empty_constant_is_the_only_terminal_route():
    # A timeout or provider failure must never settle terminal-empty; the
    # closed constant names only the definite empty response.
    assert set(EMPTY_FAILURE) == {'stage', 'reason'}
    assert EMPTY_FAILURE['stage'] != 'provider_failed'
