"""The evidence wiring walk: every stage x the named token, end to end.

The named fault's evidence must be accepted by every surface it can touch —
the transient evidence closer, both validation gates, the FailedWork and
ValidationFailureWork carriers, the scheduler fence, the recovery-held row —
and the docs must keep telling operators exactly that. One walk per surface.

Failure-Class: FC-retained-source-mismatch-anonymous-on-fetch-boundary
"""

import logging
import time

import pytest

from diarizer.batch_pipeline import transient_failure_evidence
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import item
from utils.batch_pipeline.contracts import FailedWork, ValidationFailureWork
from utils.batch_pipeline.errors import (
    WORKER_VALIDATION_STAGES,
    validate_worker_failure,
    validate_worker_failure_evidence,
)
from utils.batch_pipeline.scheduler import Scheduler
from utils.batch_pipeline.source_audio import RetainedAudioOutsideAdmittedSource
from utils.observability.reasons import WorkerValidationReason, WorkerValidationStage

NAMED = {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}


def _walk(queue, store, now):
    """Drive the ladder to quarantine; attempt 1 carries the named evidence."""
    attempt = 0
    while attempt < 6:
        lease = queue.pull(now)
        while not lease:
            now += 30
            queue.recover(now)
            lease = queue.pull(now)
        now += 30
        attempt += 1
        queue.fail('a', lease[0].token, now, worker_failure_evidence=NAMED if attempt == 1 else None)
        if store.rows['jobs', 'a']['state'] == 'quarantined':
            return attempt
    raise AssertionError('never quarantined')


# --- transient_failure_evidence over every stage with the named token ---------------


def test_evidence_closer_fetch_decode():
    assert transient_failure_evidence('fetch_decode', 'outside_admitted_source')['stage'] == 'fetch_decode'


def test_evidence_closer_vad_windows():
    assert transient_failure_evidence('vad_windows', 'outside_admitted_source')['reason'] == 'outside_admitted_source'


def test_evidence_closer_word_clocks():
    assert transient_failure_evidence('word_clocks', 'outside_admitted_source') is not None


def test_evidence_closer_assemble_words():
    assert (
        transient_failure_evidence('assemble_words', 'outside_admitted_source')['reason'] == 'outside_admitted_source'
    )


def test_evidence_closer_asr_recovery():
    assert transient_failure_evidence('asr_recovery', 'outside_admitted_source') is not None


def test_evidence_closer_unknown_stage_returns_none():
    assert transient_failure_evidence('unknown', 'outside_admitted_source') is None


def test_evidence_closer_output_is_always_a_two_key_dict():
    for stage in WORKER_VALIDATION_STAGES:
        closed = transient_failure_evidence(stage, 'outside_admitted_source')
        assert set(closed) == {'stage', 'reason'}


def test_evidence_closer_output_never_carries_the_raw_exception_text():
    for stage in WORKER_VALIDATION_STAGES:
        closed = transient_failure_evidence(stage, 'outside_admitted_source')
        assert 'retained audio reference' not in str(closed)


def test_evidence_closer_output_passes_the_gate_for_every_stage():
    for stage in WORKER_VALIDATION_STAGES:
        assert validate_worker_failure_evidence(transient_failure_evidence(stage, 'outside_admitted_source')) is None


def test_evidence_closer_output_passes_the_terminal_gate_for_every_stage():
    for stage in WORKER_VALIDATION_STAGES:
        assert validate_worker_failure(transient_failure_evidence(stage, 'outside_admitted_source')) is None


# --- The enum's own walk with the named token -----------------------------------------


def test_enum_walk_fetch_decode_member_carries_the_token():
    closed = transient_failure_evidence(WorkerValidationStage.FETCH_DECODE.value, 'outside_admitted_source')
    assert closed == {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}


def test_enum_walk_named_token_is_the_reason_string():
    assert transient_failure_evidence('fetch_decode', WorkerValidationReason.OUTSIDE_ADMITTED_SOURCE.value)[
        'reason'
    ] == ('outside_admitted_source')


def test_enum_walk_never_collapses_the_named_token_to_unknown():
    for stage in WORKER_VALIDATION_STAGES:
        closed = transient_failure_evidence(stage, 'outside_admitted_source')
        assert closed['reason'] != 'unknown'


def test_enum_walk_preserves_the_stage_identity():
    for stage in WORKER_VALIDATION_STAGES:
        assert transient_failure_evidence(stage, 'outside_admitted_source')['stage'] == stage


# --- The scheduler's named walk keeps every downstream field named ---------------------


def test_walk_terminal_job_names_the_token():
    store = MemoryStore()
    queue = Scheduler(store)
    now = time.time()
    queue.enqueue(item(), now)
    _walk(queue, store, now)
    assert store.rows['jobs', 'a']['worker_failure_evidence']['reason'] == 'outside_admitted_source'


def test_walk_terminal_job_stage_is_fetch_decode():
    store = MemoryStore()
    queue = Scheduler(store)
    now = time.time()
    queue.enqueue(item(), now)
    _walk(queue, store, now)
    assert store.rows['jobs', 'a']['worker_failure_evidence']['stage'] == 'fetch_decode'


def test_walk_terminal_row_names_the_machine_reason_worker_failed():
    store = MemoryStore()
    queue = Scheduler(store)
    now = time.time()
    queue.enqueue(item(), now)
    _walk(queue, store, now)
    assert store.rows['jobs', 'a']['failure'] == 'worker_failed'


def test_walk_uses_exactly_five_attempts():
    store = MemoryStore()
    queue = Scheduler(store)
    now = time.time()
    queue.enqueue(item(), now)
    assert _walk(queue, store, now) == 5


def test_walk_never_sets_worker_empty_evidence():
    store = MemoryStore()
    queue = Scheduler(store)
    now = time.time()
    queue.enqueue(item(), now)
    _walk(queue, store, now)
    assert 'worker_empty_evidence' not in store.rows['jobs', 'a']


def test_walk_never_sets_padded_retry_state():
    store = MemoryStore()
    queue = Scheduler(store)
    now = time.time()
    queue.enqueue(item(), now)
    _walk(queue, store, now)
    job = store.rows['jobs', 'a']
    assert 'padded_retry' not in job
    assert 'padded_retry_empty' not in job


def test_walk_leaves_the_audio_reference_intact_for_recovery():
    store = MemoryStore()
    queue = Scheduler(store)
    now = time.time()
    queue.enqueue(item(), now)
    audio_before = store.rows['jobs', 'a']['audio_uri']
    _walk(queue, store, now)
    assert store.rows['jobs', 'a']['audio_uri'] == audio_before


# --- The carriers keep the token copy-safe ----------------------------------------------


def test_failed_work_diagnosis_is_stored_by_reference():
    # The dataclass stores the caller's dict as-is; the SCHEDULER's commit
    # does the defensive dict() copy when it rides the diagnosis onto the job
    # (pinned separately below). The boundary contract lives there, not here.
    evidence = dict(NAMED)
    work = FailedWork('a', None, None, worker_failure=evidence)
    evidence['reason'] = 'tampered'
    assert work.worker_failure['reason'] == 'tampered'


def test_scheduler_commit_copies_the_evidence():
    store = MemoryStore()
    queue = Scheduler(store)
    now = time.time()
    queue.enqueue(item(), now)
    lease = queue.pull(now)[0]
    evidence = dict(NAMED)
    queue.fail('a', lease.token, now, worker_failure_evidence=evidence)
    evidence['reason'] = 'tampered'
    assert store.rows['jobs', 'a']['worker_failure_evidence']['reason'] == 'outside_admitted_source'


def test_validation_failure_work_carries_the_named_reason_verbatim():
    work = ValidationFailureWork('a', 'fetch_decode', 'outside_admitted_source')
    assert work.reason == 'outside_admitted_source'
    assert work.measured_held_vad_speech_seconds is None


def test_the_scheduler_reads_the_job_row_copy_not_the_callers_dict():
    store = MemoryStore()
    queue = Scheduler(store)
    now = time.time()
    queue.enqueue(item(), now)
    lease = queue.pull(now)[0]
    queue.fail('a', lease.token, now, worker_failure_evidence=NAMED)
    row = store.rows['jobs', 'a']
    assert row['worker_failure_evidence'] == {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}


# --- Docs statements operators will actually act on ---------------------------------------


def test_docs_tell_the_operator_to_fix_the_env_not_the_bytes():
    text = open('docs/retained-source-outside-admitted-source.md').read()
    assert 'Fix the deployment env' in text or 'Fix the deployment' in text


def test_docs_explain_the_recovery_lane_needs_no_data_repair():
    text = open('docs/retained-source-outside-admitted-source.md').read()
    assert 'without any data repair' in text


def test_docs_name_the_worker_chart_env_pair():
    text = open('docs/retained-source-outside-admitted-source.md').read()
    assert 'BUCKET_PRIVATE_CLOUD_SYNC' in text
    assert 'BUCKET_AUDIO_DERIVED' in text


def test_docs_describe_the_generation_terminal_flip():
    text = open('docs/retained-source-outside-admitted-source.md').read()
    assert 'InvalidRetainedManifest' in text
    assert 'terminal' in text.lower()


def test_docs_describe_the_restore_redrive_evidence_clearing():
    text = open('docs/retained-source-outside-admitted-source.md').read()
    assert 'collects its own diagnosis' in text


def test_docs_keep_the_signature_family_attribution():
    text = open('docs/retained-source-outside-admitted-source.md').read()
    assert 'x386/30m' in text
    assert 'unclassified' in text


def test_docs_carry_exactly_one_failure_class_trailer():
    text = open('docs/retained-source-outside-admitted-source.md').read()
    assert text.count('Failure-Class:') == 1


def test_docs_name_the_fetch_decode_stage_in_the_operator_note():
    text = open('docs/retained-source-outside-admitted-source.md').read()
    assert 'fetch_decode' in text


def test_docs_describe_the_renamed_but_retryable_semantics():
    text = open('docs/retained-source-outside-admitted-source.md').read()
    assert 'keeps walking' in text or 'keeps walking the bounded ladder' in text


def test_docs_do_not_promise_an_automatic_recovery_the_code_lacks():
    text = open('docs/retained-source-outside-admitted-source.md').read()
    assert 'recovers on its next ladder attempt' in text


# --- Cross-suite sanity: the token never leaks into other lanes' vocabularies --------------


def test_recovery_failure_vocabulary_is_untouched_by_the_addition():
    from utils.observability.reasons import RecoveryFailureReason

    values = {reason.value for reason in RecoveryFailureReason}
    assert 'outside_admitted_source' not in values


def test_capture_retry_cap_vocabulary_is_untouched_by_the_addition():
    from utils.capture.retry_cap import retry_cap

    decision = retry_cap('uid', 5, 5)
    if decision is not None:
        assert not hasattr(decision, 'outside_admitted_source')


def test_the_worker_validation_stage_vocabulary_has_no_bucket_stage():
    values = {stage.value for stage in WorkerValidationStage}
    assert 'bucket_check' not in values
    assert 'source_check' not in values


def test_the_named_fault_still_surfaces_through_the_worker_counts():
    from tests.unit.test_batch_pipeline_worker import setup_worker

    worker, *_ = setup_worker(
        decode=lambda work: (_ for _ in ()).throw(
            RetainedAudioOutsideAdmittedSource('retained audio reference is outside admitted source')
        )
    )
    worker.process_batch([item()])
    assert worker.counts['failed'] == 1


def test_the_named_fault_per_attempt_record_is_error_level():
    from tests.unit.test_batch_pipeline_worker import setup_worker

    worker, *_ = setup_worker(
        decode=lambda work: (_ for _ in ()).throw(
            RetainedAudioOutsideAdmittedSource('retained audio reference is outside admitted source')
        )
    )
    record = []

    class Capture(logging.Handler):
        def emit(self, entry):
            record.append((entry.levelno, entry.getMessage()))

    logging.getLogger('diarizer.batch_pipeline').addHandler(Capture())
    worker.process_batch([item()])
    assert any(level == logging.ERROR and 'event=batch_worker_failed' in message for level, message in record)
