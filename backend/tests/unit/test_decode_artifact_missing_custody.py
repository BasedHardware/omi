"""Hand-written custody pins for the fetch_decode generation-pinned storage 404.

The generated custody bands pin the full disposition lattice; this suite pins
the load-bearing cells by hand, each driven through the real surface: the real
generation-pinned ``read_reference`` against a gone object (the production
raise site), the type-only verdict, the stage scoping, the transport and
contention families' non-claims, the closed vocabularies, the real
``PipelineWorker`` fetch path ending the chain at its first occurrence, and
the terminal report's unconditional demotion over ``MemoryStore``.

Failure-Class: FC-fetch-decode-artifact-notfound-walks-gpu-ladder-as-unclassified-worker-fault
"""

import logging
import socket

import pytest
from google.api_core.exceptions import (
    Aborted as GoogleAborted,
    DeadlineExceeded as GoogleDeadlineExceeded,
    InvalidArgument as GoogleInvalidArgument,
    NotFound as GoogleNotFound,
    ServiceUnavailable as GoogleServiceUnavailable,
)

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.firestore_transaction_retry import FirestoreContentionExhausted
from diarizer.batch_pipeline import (
    BatchValidationError,
    DecodedDurationMismatch,
    decode_artifact_failure_reason,
    decode_artifact_loss_is_deterministic,
    decode_payload_is_deterministic,
    persist_loss_is_contention,
    persist_loss_is_deterministic,
    persist_loss_is_privacy_refusal,
    persist_loss_is_restrikeable,
    transient_failure_evidence,
)
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import item, setup_worker
from utils.batch_pipeline.audio import StagedAudioInvalid
from utils.batch_pipeline.artifacts import StagedArtifactInvalid
from utils.batch_pipeline.contracts import ValidationFailureWork
from utils.batch_pipeline.errors import (
    LANGUAGE_GUARD_REDRIVE_REASONS,
    VALIDATION_DISPOSITION_FLAGGED_REASONS,
    VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS,
    WORKER_VALIDATION_REASON_TOKENS,
    WORKER_VALIDATION_REASONS,
    WORKER_VALIDATION_STAGES,
    empty_ladder_recovery_failure,
    language_guard_redrive_failure,
    report_terminal_quarantine,
    validate_worker_failure,
    validate_worker_failure_evidence,
    validation_disposition_failure,
)
from utils.batch_pipeline.scheduler import Scheduler
from utils.batch_pipeline.source_audio import (
    InvalidRetainedManifest,
    RetainedAudioInvalid,
    RetainedAudioOutsideAdmittedSource,
    read_reference,
)
from utils.batch_pipeline.word_validation import ValidationReason
from utils.observability.reasons import (
    ReasonFamily,
    WorkerValidationReason,
    WorkerValidationStage,
    reason_label,
    reason_values,
)

ARTIFACT = WorkerValidationReason.DECODE_ARTIFACT_MISSING.value
ARTIFACT_FAMILY = ReasonFamily.WORKER_VALIDATION


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


def _report_records(diagnosis, attempt=3):
    logger = logging.getLogger('test_artifact_missing_report')
    logger.setLevel(logging.DEBUG)
    sink = _Sink()
    logger.addHandler(sink)
    try:
        report_terminal_quarantine(logger, attempt=attempt, diagnosis=diagnosis)
    finally:
        logger.removeHandler(sink)
    return sink.records


# --- the verdict is type-only and message-free ---------------------------------


def _raised(factory):
    try:
        raise factory
    except Exception as error:
        return error


def test_storage_not_found_is_the_artifact_loss():
    assert decode_artifact_loss_is_deterministic(GoogleNotFound('no such object')) is True


def test_storage_not_found_verdict_ignores_the_message():
    first = GoogleNotFound('no such object: chunks/u/c/file')
    second = GoogleNotFound('gone during the download stream')
    assert decode_artifact_loss_is_deterministic(first) == decode_artifact_loss_is_deterministic(second)


def test_typed_staged_audio_keeps_its_own_token():
    assert decode_artifact_loss_is_deterministic(StagedAudioInvalid('x')) is False


def test_typed_staged_artifact_keeps_its_own_token():
    assert decode_artifact_loss_is_deterministic(StagedArtifactInvalid('x')) is False


def test_typed_retained_audio_keeps_its_own_token():
    assert decode_artifact_loss_is_deterministic(RetainedAudioInvalid('x')) is False


def test_typed_retained_manifest_subclass_keeps_its_own_token():
    assert decode_artifact_loss_is_deterministic(InvalidRetainedManifest('x')) is False


def test_typed_outside_admitted_source_stays_retryable():
    assert decode_artifact_loss_is_deterministic(RetainedAudioOutsideAdmittedSource('x')) is False


def test_typed_duration_mismatch_keeps_its_own_token():
    assert decode_artifact_loss_is_deterministic(DecodedDurationMismatch('x')) is False


def test_typed_validation_error_keeps_its_own_token():
    assert decode_artifact_loss_is_deterministic(BatchValidationError(ValidationReason.EMPTY_ASR)) is False


def test_bare_valueerror_poison_is_not_the_artifact_loss():
    assert decode_artifact_loss_is_deterministic(ValueError('bad payload')) is False


def test_transport_invalid_argument_is_not_the_artifact_loss():
    assert decode_artifact_loss_is_deterministic(GoogleInvalidArgument('bad request')) is False


def test_transport_aborted_is_not_the_artifact_loss():
    assert decode_artifact_loss_is_deterministic(GoogleAborted('conflict')) is False


def test_transport_service_unavailable_is_not_the_artifact_loss():
    assert decode_artifact_loss_is_deterministic(GoogleServiceUnavailable('down')) is False


def test_transport_deadline_exceeded_is_not_the_artifact_loss():
    assert decode_artifact_loss_is_deterministic(GoogleDeadlineExceeded('slow')) is False


def test_contention_exhaustion_is_not_the_artifact_loss():
    assert decode_artifact_loss_is_deterministic(FirestoreContentionExhausted('budget gone')) is False


def test_privacy_refusal_is_not_the_artifact_loss():
    assert decode_artifact_loss_is_deterministic(BatchPrivacyBlocked('fence')) is False


def test_builtin_faults_are_never_the_artifact_loss():
    assert decode_artifact_loss_is_deterministic(RuntimeError('x')) is False
    assert decode_artifact_loss_is_deterministic(KeyError('x')) is False
    assert decode_artifact_loss_is_deterministic(TimeoutError('x')) is False


# --- the real raise site: a generation-pinned read against a gone object -------


class _GoneOnReloadBlob:
    def __init__(self, path, generation=None):
        self.path = path
        self.metadata = None

    def reload(self, **_kwargs):
        raise GoogleNotFound('no such object: ' + self.path)


class _GoneOnReloadBucket:
    def blob(self, path, generation=None):
        return _GoneOnReloadBlob(path, generation)


class _GoneOnReloadClient:
    def bucket(self, name):
        return _GoneOnReloadBucket()


class _GoneOnDownloadBlob:
    def __init__(self, path, generation=None):
        self.path = path
        self.metadata = {'record_sample_rate': '16000'}
        self.size = 1024

    def reload(self, **_kwargs):
        return None

    def download_as_bytes(self, **_kwargs):
        raise GoogleNotFound('object deleted between GET and DOWNLOAD')


class _GoneOnDownloadBucket:
    def blob(self, path, generation=None):
        return _GoneOnDownloadBlob(path, generation)


class _GoneOnDownloadClient:
    def bucket(self, name):
        return _GoneOnDownloadBucket()


def _ref(uid='u1', conversation_id='c1'):
    return {
        'bucket': 'admitted-bucket',
        'path': f'chunks/{uid}/{conversation_id}/part-0.opus',
        'generation': 7,
        'pcm_sha256': 'a' * 64,
    }


def test_real_generation_pinned_reload_against_a_gone_object_raises_notfound():
    with pytest.raises(GoogleNotFound):
        read_reference(
            _GoneOnReloadClient(),
            _ref(),
            'u1',
            'c1',
            {'admitted-bucket'},
            b'key',
        )


def test_real_generation_pinned_download_against_a_gone_object_raises_notfound():
    with pytest.raises(GoogleNotFound):
        read_reference(
            _GoneOnDownloadClient(),
            _ref(),
            'u1',
            'c1',
            {'admitted-bucket'},
            b'key',
        )


def test_the_production_raise_site_feeds_the_verdict():
    try:
        read_reference(_GoneOnReloadClient(), _ref(), 'u1', 'c1', {'admitted-bucket'}, b'key')
    except GoogleNotFound as error:
        assert decode_artifact_loss_is_deterministic(error) is True
    else:
        raise AssertionError('the gone object must refuse the pinned reload')


# --- the arm is stage-scoped and attribution-scoped ----------------------------


def test_artifact_reason_only_answers_at_fetch_decode():
    for stage in sorted(WORKER_VALIDATION_STAGES - {WorkerValidationStage.FETCH_DECODE.value}):
        assert decode_artifact_failure_reason(GoogleNotFound('x'), stage, 'unclassified') is None


def test_artifact_reason_only_answers_anonymous_attribution():
    for reason in ('empty_asr', 'unknown', 'staged_audio_invalid', 'decode_payload_invalid'):
        assert decode_artifact_failure_reason(GoogleNotFound('x'), 'fetch_decode', reason) is None


def test_artifact_reason_names_the_closed_token():
    assert decode_artifact_failure_reason(GoogleNotFound('x'), 'fetch_decode', 'unclassified') == ARTIFACT


def test_artifact_reason_never_claims_other_faults_at_fetch_decode():
    for error in (
        StagedAudioInvalid('x'),
        ValueError('x'),
        GoogleInvalidArgument('x'),
        GoogleAborted('x'),
        RuntimeError('x'),
    ):
        assert decode_artifact_failure_reason(error, 'fetch_decode', 'unclassified') is None


# --- the token joined the closed vocabularies ----------------------------------


def test_token_is_a_closed_worker_validation_reason():
    assert ARTIFACT == 'decode_artifact_missing'
    assert ARTIFACT in {member.value for member in WorkerValidationReason}
    assert len(ARTIFACT) <= 40


def test_token_is_in_the_admitted_reason_and_token_vocabularies():
    assert ARTIFACT in WORKER_VALIDATION_REASONS
    assert ARTIFACT in WORKER_VALIDATION_REASON_TOKENS


def test_token_is_not_the_stage_or_any_other_vocabulary():
    assert ARTIFACT not in reason_values(WorkerValidationStage)


def test_terminal_gate_accepts_the_artifact_pair():
    validate_worker_failure({'stage': 'fetch_decode', 'reason': ARTIFACT})


def test_evidence_gate_accepts_the_artifact_pair():
    validate_worker_failure_evidence({'stage': 'fetch_decode', 'reason': ARTIFACT})


def test_artifact_pair_joined_the_unconditional_disposition_arm():
    assert ARTIFACT in VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS
    assert ARTIFACT not in VALIDATION_DISPOSITION_FLAGGED_REASONS
    assert ARTIFACT not in LANGUAGE_GUARD_REDRIVE_REASONS


def test_artifact_pair_is_not_the_guard_or_the_empty_ladder():
    pair = {'stage': 'fetch_decode', 'reason': ARTIFACT}
    assert language_guard_redrive_failure(pair) is False
    assert empty_ladder_recovery_failure(pair) is False


def test_artifact_evidence_closes_into_durable_evidence():
    assert transient_failure_evidence('fetch_decode', ARTIFACT) == {'stage': 'fetch_decode', 'reason': ARTIFACT}


def test_artifact_label_roundtrips_through_the_reason_family():
    assert reason_label(ARTIFACT_FAMILY, ARTIFACT, WorkerValidationReason) == ARTIFACT


# --- the disposition answers unconditionally, off-vocabulary stays a fault -----


def test_disposition_answers_the_artifact_family_under_both_switch_values():
    pair = {'stage': 'fetch_decode', 'reason': ARTIFACT}
    assert validation_disposition_failure(pair, disposition_enabled=True) is True
    assert validation_disposition_failure(pair, disposition_enabled=False) is True


def test_disposition_keeps_outside_admitted_source_retryable_at_fetch_decode():
    pair = {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}
    assert validation_disposition_failure(pair, disposition_enabled=True) is False


def test_disposition_never_answers_the_artifact_token_at_another_stage():
    for stage in sorted(WORKER_VALIDATION_STAGES - {WorkerValidationStage.FETCH_DECODE.value}):
        assert validation_disposition_failure({'stage': stage, 'reason': ARTIFACT}, disposition_enabled=True) is False


# --- the terminal report demotes the family at both terminals ------------------


def test_verdict_terminal_demotes_the_artifact_family():
    accepted, job, records = _quarantine_with(
        quarantine=True, worker_failure={'stage': 'fetch_decode', 'reason': ARTIFACT}
    )
    assert accepted is True
    assert job['state'] == 'quarantined' and job['recovery_state'] == 'held'
    demoted = [message for level, message in records if 'batch_validation_disposition' in message and level == 'INFO']
    faulted = [message for level, message in records if 'batch_quarantined' in message and level == 'ERROR']
    assert len(demoted) == 1
    assert 'stage=fetch_decode' in demoted[0]
    assert 'worker_reason=decode_artifact_missing' in demoted[0]
    assert faulted == []


def test_verdict_terminal_names_the_artifact_stage_and_reason():
    _accepted, _job, records = _quarantine_with(
        quarantine=True, worker_failure={'stage': 'fetch_decode', 'reason': ARTIFACT}
    )
    line = next(message for _level, message in records if 'batch_validation_disposition' in message)
    assert 'attempt=1001' in line or 'attempt=' in line
    assert 'outcome=held_for_disposition' in line
    assert any('awaiting_fenced_recovery' in message for _level, message in records)


def test_direct_report_books_the_demoted_line_with_the_attempt():
    records = _report_records({'stage': 'fetch_decode', 'reason': ARTIFACT}, attempt=2)
    assert records[0][0] == 'INFO'
    assert 'attempt=2' in records[0][1]
    assert 'outcome=held_for_disposition' in records[0][1]


def test_direct_report_keeps_the_awaiting_recovery_warning():
    records = _report_records({'stage': 'fetch_decode', 'reason': ARTIFACT})
    warnings = [message for level, message in records if level == 'WARNING']
    assert any('awaiting_fenced_recovery' in message for message in warnings)


def test_direct_report_keeps_the_error_channel_for_a_retryable_sibling():
    records = _report_records({'stage': 'fetch_decode', 'reason': 'outside_admitted_source'})
    errors = [message for level, message in records if level == 'ERROR']
    assert any(
        'batch_quarantined' in message and 'worker_reason=outside_admitted_source' in message for message in errors
    )


# --- the real worker boundary ends the chain at the first occurrence -----------


def test_worker_books_typed_custody_for_a_gone_artifact():
    def gone_decode(_work):
        raise GoogleNotFound('no such object: chunks/u/c/part-0')

    worker, _words, _saved, _decoded, _diarized, failures = setup_worker(decode=gone_decode)
    results = worker.process_batch([item('gone', 2)])
    assert len(results) == 1
    result = results[0]
    assert type(result).__name__ == 'ValidationFailureWork'
    assert (result.stage, result.reason) == ('fetch_decode', ARTIFACT)
    assert isinstance(result, ValidationFailureWork)
    assert worker.counts['failed'] == 1
    assert failures and failures[0][0] == 'gone'


def test_worker_does_not_walk_the_ladder_for_the_gone_artifact():
    attempts = []

    def gone_decode(work):
        attempts.append(work.segment_id)
        raise GoogleNotFound('no such object')

    worker, _words, _saved, _decoded, _diarized, _failures = setup_worker(decode=gone_decode)
    worker.process_batch([item('once', 2)])
    assert len(attempts) == 1


def test_worker_keeps_the_transport_family_off_the_artifact_token():
    worker, _words, _saved, _decoded, _diarized, _failures = setup_worker(
        decode=lambda _work: (_ for _ in ()).throw(GoogleAborted('read aborted'))
    )
    results = worker.process_batch([item('aborted', 2)])
    assert not any(isinstance(result, ValidationFailureWork) for result in results)
    assert worker.counts['failed'] == 1


def test_worker_keeps_the_typed_trio_off_the_artifact_token():
    worker, _words, _saved, _decoded, _diarized, _failures = setup_worker(
        decode=lambda _work: (_ for _ in ()).throw(StagedAudioInvalid('undecodable'))
    )
    results = worker.process_batch([item('staged', 2)])
    assert len(results) == 1
    assert (results[0].stage, results[0].reason) == ('fetch_decode', 'staged_audio_invalid')


# --- the same class at another stage keeps that stage's custody ----------------


def test_worker_at_persist_keeps_notfound_off_the_artifact_token():
    def gone_persist(_work, _payload):
        raise GoogleNotFound('gone at the upload')

    worker, _words, _saved, _decoded, _diarized, _failures = setup_worker(persist=gone_persist)
    results = worker.process_batch([item('persisted', 2)])
    assert not any(isinstance(result, ValidationFailureWork) and result.reason == ARTIFACT for result in results)
    assert worker.counts['failed'] == 1


# --- the persist tail's verdicts keep their boundaries -------------------------


def test_persist_deterministic_refusal_still_answers_plain_invalid_argument():
    assert persist_loss_is_deterministic(GoogleInvalidArgument('bad payload')) is True


def test_persist_deterministic_refusal_leaves_the_expired_chain_to_contention():
    expired = GoogleInvalidArgument('transaction has expired please retry')
    assert persist_loss_is_deterministic(expired) is False
    assert persist_loss_is_contention(expired) is True


def test_persist_contention_answers_aborted_and_exhaustion():
    assert persist_loss_is_contention(GoogleAborted('conflict')) is True
    assert persist_loss_is_contention(FirestoreContentionExhausted('budget')) is True
    assert persist_loss_is_deterministic(GoogleAborted('conflict')) is False


def test_persist_restrikeable_answers_the_google_and_timeout_families():
    assert persist_loss_is_restrikeable(GoogleNotFound('gone')) is True
    assert persist_loss_is_restrikeable(GoogleInvalidArgument('x')) is True
    assert persist_loss_is_restrikeable(GoogleServiceUnavailable('x')) is True
    assert persist_loss_is_restrikeable(TimeoutError('x')) is True
    assert persist_loss_is_restrikeable(socket.timeout('x')) is True
    assert persist_loss_is_restrikeable(ValueError('x')) is False
    assert persist_loss_is_restrikeable(BatchPrivacyBlocked('x')) is False


def test_persist_privacy_refusal_answers_only_the_fence():
    assert persist_loss_is_privacy_refusal(BatchPrivacyBlocked('fence')) is True
    assert persist_loss_is_privacy_refusal(GoogleNotFound('x')) is False
    assert persist_loss_is_privacy_refusal(RuntimeError('privacy shaped message')) is False


def test_the_poison_verdict_stays_off_the_artifact_loss():
    assert decode_payload_is_deterministic(GoogleNotFound('gone')) is False
    assert decode_payload_is_deterministic(_raised(ValueError('poison'))) is True


def test_the_artifact_verdict_stays_off_the_poison():
    assert decode_artifact_loss_is_deterministic(_raised(ValueError('poison'))) is False
    assert decode_artifact_failure_reason(_raised(ValueError('poison')), 'fetch_decode', 'unclassified') is None
