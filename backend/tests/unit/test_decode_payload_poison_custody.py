"""Hand-written custody pins for the fetch_decode bare-ValueError poison.

The generated walk bands pin the full lattice; this suite pins the load-
bearing cells by hand, each one driven through the real boundary: the real
``round(NaN)`` refuse inside the retained-manifest builder, a real text-
decode ``UnicodeDecodeError`` through the real ``PipelineWorker`` fetch
path, the typed decode family's non-claim, the stage scoping of the poison
verdict, the vocabulary gates, and the terminal report's unconditional
demotion of the poison token at the scheduler over ``MemoryStore``.

Failure-Class: FC-fetch-decode-valueerror-poison-walks-gpu-ladder-as-anonymous-per-attempt
"""

import logging

from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import item, setup_worker
from utils.batch_pipeline.errors import (
    LANGUAGE_GUARD_REDRIVE_REASONS,
    VALIDATION_DISPOSITION_FLAGGED_REASONS,
    VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS,
    report_terminal_quarantine,
    validate_worker_failure,
    validate_worker_failure_evidence,
)
from diarizer.batch_pipeline import (
    BatchValidationError,
    DecodedDurationMismatch,
    decode_payload_failure_reason,
    decode_payload_is_deterministic,
    transient_failure_evidence,
)
from utils.batch_pipeline.scheduler import Scheduler
from utils.observability.reasons import WorkerValidationReason
from utils.batch_pipeline.audio import StagedAudioInvalid
from utils.batch_pipeline.artifacts import StagedArtifactInvalid
from utils.batch_pipeline.source_audio import (
    InvalidRetainedManifest,
    RetainedAudioInvalid,
    RetainedAudioOutsideAdmittedSource,
)
from utils.observability.reasons import WorkerValidationReason as _WVR

POISON = _WVR.DECODE_PAYLOAD_INVALID.value


class _Sink(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append((record.levelname, record.getMessage()))


def _quarantine_with(**kwargs):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0.0)
    queue.recover(1000.0)
    lease = queue.pull(1000.0)[0]
    sink = _Sink()
    root = logging.getLogger()
    root.addHandler(sink)
    previous = root.level
    root.setLevel(logging.DEBUG)
    try:
        accepted = queue.fail('a', lease.token, 1001.0, **kwargs)
        job = store.rows['jobs', 'a']
    finally:
        root.removeHandler(sink)
        root.setLevel(previous)
    return accepted, job, sink.records


# --- the verdict is type-only and message-free ---------------------------------


def _real_round_poison():
    try:
        round(float('nan'))
    except ValueError as error:
        return error
    raise AssertionError('round(NaN) must refuse')


def test_real_round_nan_poison_is_deterministic():
    assert decode_payload_is_deterministic(_real_round_poison()) is True


def test_real_text_decode_poison_is_deterministic():
    try:
        b'\xff'.decode('utf-8')
    except UnicodeDecodeError as error:
        assert decode_payload_is_deterministic(error) is True
    else:
        raise AssertionError('the bytes must refuse to decode')


def test_verdict_ignores_the_exception_message():
    first = ValueError('path to /private/audio omitted')
    second = ValueError('totally different wording')
    assert decode_payload_is_deterministic(first) == decode_payload_is_deterministic(second)


def test_typed_staged_audio_stays_with_its_own_token():
    assert decode_payload_is_deterministic(StagedAudioInvalid('x')) is False


def test_typed_staged_artifact_stays_with_its_own_token():
    assert decode_payload_is_deterministic(StagedArtifactInvalid('x')) is False


def test_typed_retained_audio_stays_with_its_own_token():
    assert decode_payload_is_deterministic(RetainedAudioInvalid('x')) is False


def test_typed_retained_manifest_subclass_stays_with_its_own_token():
    assert decode_payload_is_deterministic(InvalidRetainedManifest('x')) is False


def test_typed_outside_admitted_source_stays_retryable():
    assert decode_payload_is_deterministic(RetainedAudioOutsideAdmittedSource('x')) is False


def test_typed_duration_mismatch_stays_with_its_own_token():
    assert decode_payload_is_deterministic(DecodedDurationMismatch('x')) is False


def test_typed_validation_error_stays_with_its_own_token():
    from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason

    assert decode_payload_is_deterministic(BatchValidationError(ValidationReason.EMPTY_ASR)) is False


def test_transport_invalid_argument_is_not_the_poison():
    import google.api_core.exceptions as api_core

    assert decode_payload_is_deterministic(api_core.InvalidArgument('bad request')) is False


def test_non_valueerror_faults_are_never_the_poison():
    assert decode_payload_is_deterministic(KeyError('x')) is False
    assert decode_payload_is_deterministic(RuntimeError('x')) is False


# --- the verdict is stage-scoped and attribution-scoped ------------------------


def test_poison_reason_only_answers_at_fetch_decode():
    for stage in ('unknown', 'vad_windows', 'word_clocks', 'assemble_words', 'asr_recovery', 'persist'):
        assert decode_payload_failure_reason(ValueError('x'), stage, 'unclassified') is None


def test_poison_reason_only_answers_anonymous_attribution():
    assert decode_payload_failure_reason(ValueError('x'), 'fetch_decode', 'empty_asr') is None


def test_poison_reason_names_the_closed_token():
    assert decode_payload_failure_reason(ValueError('x'), 'fetch_decode', 'unclassified') == POISON


# --- the token joined the closed vocabularies ----------------------------------


def test_token_is_a_closed_worker_validation_reason():
    assert POISON in {member.value for member in WorkerValidationReason}
    assert len(POISON) <= 40


def test_terminal_gate_accepts_the_poison_pair():
    validate_worker_failure({'stage': 'fetch_decode', 'reason': POISON})


def test_evidence_gate_accepts_the_poison_pair():
    validate_worker_failure_evidence({'stage': 'fetch_decode', 'reason': POISON})


def test_poison_joined_the_unconditional_disposition_arm():
    assert POISON in VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS
    assert POISON not in VALIDATION_DISPOSITION_FLAGGED_REASONS
    assert POISON not in LANGUAGE_GUARD_REDRIVE_REASONS


def test_poison_evidence_closes_into_durable_evidence():
    evidence = transient_failure_evidence('fetch_decode', POISON)
    assert evidence == {'stage': 'fetch_decode', 'reason': POISON}


# --- the real worker boundary ends the chain with the typed custody ------------


def test_worker_books_typed_custody_for_a_real_decode_poison():
    def poisoned_decode(work):
        b'\xff'.decode('utf-8')

    worker, _words, _saved, _decoded, _diarized, failures = setup_worker(decode=poisoned_decode)
    results = worker.process_batch([item('poison', 2)])
    assert len(results) == 1
    result = results[0]
    assert type(result).__name__ == 'ValidationFailureWork'
    assert (result.stage, result.reason) == ('fetch_decode', POISON)
    assert worker.counts['failed'] == 1
    assert failures and failures[0][0] == 'poison'


def test_worker_books_anonymous_fault_for_a_transport_loss():
    worker, _words, _saved, _decoded, _diarized, failures = setup_worker(
        decode=lambda _work: (_ for _ in ()).throw(RuntimeError('storage down'))
    )
    results = worker.process_batch([item('flaky', 2)])
    assert type(results[0]).__name__ == 'FailedWork'
    assert worker.counts['failed'] == 1
    assert failures


# --- the terminal report demotes the poison unconditionally ---------------------


def test_scheduler_terminal_demotes_the_poison_to_the_disposition_event():
    accepted, job, records = _quarantine_with(
        quarantine=True, worker_failure={'stage': 'fetch_decode', 'reason': POISON}
    )
    assert accepted is True
    assert job['state'] == 'quarantined' and job['recovery_state'] == 'held'
    assert [level for level, _message in records if 'batch_validation_disposition' in _message] == ['INFO']
    assert not any('batch_quarantined' in message for _level, message in records)
    assert any('awaiting_fenced_recovery' in message for _level, message in records)


def test_scheduler_terminal_names_the_poison_stage_and_reason():
    _accepted, _job, records = _quarantine_with(
        quarantine=True, worker_failure={'stage': 'fetch_decode', 'reason': POISON}
    )
    line = next(message for _level, message in records if 'batch_validation_disposition' in message)
    assert 'stage=fetch_decode' in line and 'worker_reason=decode_payload_invalid' in line


def test_poison_ladder_preserves_evidence_to_an_evidenceless_exhaustion():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0.0)
    for attempt in range(1, 6):
        now = attempt * 1000.0
        queue.recover(now)
        lease = queue.pull(now)[0]
        kwargs = {}
        if attempt < 5:
            kwargs = {'worker_failure_evidence': {'stage': 'fetch_decode', 'reason': POISON}}
        assert queue.fail('a', lease.token, now + 1.0, **kwargs) is True
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined'
    assert job['worker_failure_evidence'] == {'stage': 'fetch_decode', 'reason': POISON}
    sink = _Sink()
    root = logging.getLogger()
    root.addHandler(sink)
    previous = root.level
    root.setLevel(logging.DEBUG)
    try:
        report_terminal_quarantine(
            logging.getLogger('utils.batch_pipeline.scheduler'), attempt=5, diagnosis=job.get('worker_failure_evidence')
        )
    finally:
        root.removeHandler(sink)
        root.setLevel(previous)
    line = next(message for _level, message in sink.records if 'batch_validation_disposition' in message)
    assert 'worker_reason=decode_payload_invalid' in line


def test_quarantined_poison_unit_leaves_the_ladder_for_good():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0.0)
    queue.recover(1000.0)
    lease = queue.pull(1000.0)[0]
    queue.fail('a', lease.token, 1001.0, quarantine=True, worker_failure={'stage': 'fetch_decode', 'reason': POISON})
    assert queue.recover(99999.0) == 0
    assert queue.pull(99999.0) == []
    assert not queue.redrive_dead('a', 99999.0)
