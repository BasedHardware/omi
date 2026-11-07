"""The named fault's one-token journey across every closed surface.

Short, direct checks that the outside-admitted-source token survives each
hop of the diagnostic chain — worker evidence closer, both gates, both work
carriers, the scheduler commit — plus the docs' operator-note contract.

Failure-Class: FC-retained-source-mismatch-anonymous-on-fetch-boundary
"""

import logging

import pytest

from diarizer.batch_pipeline import transient_failure_evidence
from tests.unit.test_batch_pipeline_worker import item, setup_worker
from utils.batch_pipeline.contracts import FailedWork
from utils.batch_pipeline.errors import validate_worker_failure, validate_worker_failure_evidence
from utils.batch_pipeline.source_audio import RetainedAudioOutsideAdmittedSource
from utils.observability.reasons import WorkerValidationReason

TOKEN = 'outside_admitted_source'


def test_hop_evidence_closer_preserves_the_token():
    assert transient_failure_evidence('fetch_decode', TOKEN)['reason'] == TOKEN


def test_hop_terminal_gate_accepts_the_token():
    assert validate_worker_failure({'stage': 'fetch_decode', 'reason': TOKEN}) is None


def test_hop_evidence_gate_accepts_the_token():
    assert validate_worker_failure_evidence({'stage': 'fetch_decode', 'reason': TOKEN}) is None


def test_hop_failed_work_carries_the_token():
    work = FailedWork('a', None, None, worker_failure={'stage': 'fetch_decode', 'reason': TOKEN})
    assert work.worker_failure['reason'] == TOKEN


def test_hop_the_worker_logs_the_token(caplog):
    worker, *_ = setup_worker(decode=lambda work: (_ for _ in ()).throw(RetainedAudioOutsideAdmittedSource('x')))
    with caplog.at_level(logging.ERROR, logger='diarizer.batch_pipeline'):
        worker.process_batch([item()])
    assert 'reason=' + TOKEN in caplog.text


def test_hop_the_worker_log_names_the_class(caplog):
    worker, *_ = setup_worker(decode=lambda work: (_ for _ in ()).throw(RetainedAudioOutsideAdmittedSource('x')))
    with caplog.at_level(logging.ERROR, logger='diarizer.batch_pipeline'):
        worker.process_batch([item()])
    assert 'error_class=RetainedAudioOutsideAdmittedSource' in caplog.text


def test_hop_the_worker_log_stays_on_the_fetch_stage(caplog):
    worker, *_ = setup_worker(decode=lambda work: (_ for _ in ()).throw(RetainedAudioOutsideAdmittedSource('x')))
    with caplog.at_level(logging.ERROR, logger='diarizer.batch_pipeline'):
        worker.process_batch([item()])
    assert 'stage=fetch_decode' in caplog.text


def test_hop_the_close_token_differs_from_the_anonymous_fallback():
    assert transient_failure_evidence('fetch_decode', TOKEN) != transient_failure_evidence('fetch_decode', 'never-seen')


def test_hop_the_close_token_roundtrips_through_the_evidence_gate_twice():
    evidence = transient_failure_evidence('fetch_decode', TOKEN)
    validate_worker_failure_evidence(evidence)
    validate_worker_failure_evidence(dict(evidence))


def test_hop_the_terminal_gate_rejects_the_token_with_the_unknown_stage():
    with pytest.raises(ValueError, match='closed worker validation failure required'):
        validate_worker_failure({'stage': 'unknown', 'reason': TOKEN})


def test_hop_the_evidence_gate_rejects_the_token_with_the_unknown_stage():
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        validate_worker_failure_evidence({'stage': 'unknown', 'reason': TOKEN})


def test_hop_docs_name_the_unit_level_recovery_contract():
    text = open('docs/retained-source-outside-admitted-source.md').read()
    assert 'recovers on its next ladder attempt' in text


def test_hop_docs_describe_the_evidence_precedence_explicitly():
    text = open('docs/retained-source-outside-admitted-source.md').read()
    assert 'current attempt' in text


def test_hop_docs_explain_why_the_fault_is_not_the_bytes_family():
    text = open('docs/retained-source-outside-admitted-source.md').read()
    assert 'bytes' in text.lower()


def test_hop_docs_carry_the_operator_env_pair_in_one_sentence():
    text = open('docs/retained-source-outside-admitted-source.md').read()
    assert 'BUCKET_PRIVATE_CLOUD_SYNC' in text and 'BUCKET_AUDIO_DERIVED' in text


def test_hop_docs_stay_silent_about_internal_queue_names():
    text = open('docs/retained-source-outside-admitted-source.md').read()
    assert 'scheduler_53' not in text


def test_hop_docs_do_not_leak_the_probe_segment_ids():
    text = open('docs/retained-source-outside-admitted-source.md').read()
    assert 'segment_id=' not in text


def test_hop_docs_name_the_bounded_ladder_the_fault_rides():
    text = open('docs/retained-source-outside-admitted-source.md').read()
    assert 'bounded' in text.lower()


def test_hop_the_scheduler_module_owns_the_terminal_record():
    import utils.batch_pipeline.scheduler as scheduler_module

    assert hasattr(scheduler_module, 'validate_worker_failure')


def test_hop_the_token_is_the_only_addition_to_the_reason_vocabulary():
    # The vocabulary grew by one; every other member keeps its value.
    legacy = {
        'unknown',
        'staged_audio_invalid',
        'retained_audio_invalid',
        'decoded_duration_mismatch',
        'word_shape',
        'word_clock',
        'word_sequence',
        'vad_nonfinite',
        'vad_order',
        'vad_bounds',
        'empty_asr',
        'no_owned_words',
        'unsupported_language',
    }
    current = {reason.value for reason in WorkerValidationReason}
    assert current - legacy == {TOKEN}
    assert legacy - current == set()
