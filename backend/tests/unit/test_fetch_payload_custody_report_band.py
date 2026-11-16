"""Generated fetch-decode payload-poison custody band test_fetch_payload_custody_report_band.

Cross-verified cell by cell at emit time: every expected literal below was
derived from the documented contract (the closed vocabularies and the family
rules) and checked against the live boundary before this file was written.
The independent spec walk and the emitter live outside the tree. Do not edit
frozen literals by hand.

Failure-Class: FC-fetch-decode-valueerror-poison-walks-gpu-ladder-as-anonymous-per-attempt
"""

import json
import os
import wave

import google.api_core.exceptions as api_core
import google.cloud.exceptions as gce_mod
from google.api_core.exceptions import GoogleAPIError

import logging

from diarizer.batch_pipeline import transient_failure_evidence
from utils.batch_pipeline.errors import (
    report_terminal_quarantine,
    validate_worker_failure,
    validation_disposition_failure,
)
from utils.observability.reasons import WorkerValidationReason

_LOGGER = logging.getLogger('diarizer.batch_pipeline')


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)


def _drive(diagnosis, attempt, flag):
    old = os.environ.get('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED')
    os.environ['BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED'] = flag
    capture = _Capture()
    root = logging.getLogger()
    root.addHandler(capture)
    logger = logging.getLogger('diarizer.batch_pipeline')
    old_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        report_terminal_quarantine(_LOGGER, attempt=attempt, diagnosis=diagnosis)
    finally:
        root.removeHandler(capture)
        logger.setLevel(old_level)
        if old is None:
            os.environ.pop('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', None)
        else:
            os.environ['BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED'] = old
    return [(record.levelname, record.getMessage()) for record in capture.records]


POISON = WorkerValidationReason.DECODE_PAYLOAD_INVALID.value

_FAULTS = {
    'api_Aborted': lambda: api_core.Aborted('synthetic fault message'),
    'api_AlreadyExists': lambda: api_core.AlreadyExists('synthetic fault message'),
    'api_BadGateway': lambda: api_core.BadGateway('synthetic fault message'),
    'api_BadRequest': lambda: api_core.BadRequest('synthetic fault message'),
    'api_Cancelled': lambda: api_core.Cancelled('synthetic fault message'),
    'api_ClientError': lambda: api_core.ClientError('synthetic fault message'),
    'api_Conflict': lambda: api_core.Conflict('synthetic fault message'),
    'api_DataLoss': lambda: api_core.DataLoss('synthetic fault message'),
    'api_DeadlineExceeded': lambda: api_core.DeadlineExceeded('synthetic fault message'),
    'api_DuplicateCredentialArgs': lambda: api_core.DuplicateCredentialArgs('synthetic fault message'),
    'api_FailedPrecondition': lambda: api_core.FailedPrecondition('synthetic fault message'),
    'api_Forbidden': lambda: api_core.Forbidden('synthetic fault message'),
    'api_GatewayTimeout': lambda: api_core.GatewayTimeout('synthetic fault message'),
    'api_GoogleAPICallError': lambda: api_core.GoogleAPICallError('synthetic fault message'),
    'api_GoogleAPIError': lambda: api_core.GoogleAPIError('synthetic fault message'),
    'api_InternalServerError': lambda: api_core.InternalServerError('synthetic fault message'),
    'api_InvalidArgument': lambda: api_core.InvalidArgument('synthetic fault message'),
    'api_LengthRequired': lambda: api_core.LengthRequired('synthetic fault message'),
    'api_MethodNotAllowed': lambda: api_core.MethodNotAllowed('synthetic fault message'),
    'api_MethodNotImplemented': lambda: api_core.MethodNotImplemented('synthetic fault message'),
    'api_MovedPermanently': lambda: api_core.MovedPermanently('synthetic fault message'),
    'api_NotFound': lambda: api_core.NotFound('synthetic fault message'),
    'api_NotModified': lambda: api_core.NotModified('synthetic fault message'),
    'api_OutOfRange': lambda: api_core.OutOfRange('synthetic fault message'),
    'api_PermissionDenied': lambda: api_core.PermissionDenied('synthetic fault message'),
    'api_PreconditionFailed': lambda: api_core.PreconditionFailed('synthetic fault message'),
    'api_Redirection': lambda: api_core.Redirection('synthetic fault message'),
    'api_RequestRangeNotSatisfiable': lambda: api_core.RequestRangeNotSatisfiable('synthetic fault message'),
    'api_ResourceExhausted': lambda: api_core.ResourceExhausted('synthetic fault message'),
    'api_ResumeIncomplete': lambda: api_core.ResumeIncomplete('synthetic fault message'),
    'api_RetryError': lambda: api_core.RetryError('deadline reached', Exception('cause')),
    'api_ServerError': lambda: api_core.ServerError('synthetic fault message'),
    'api_ServiceUnavailable': lambda: api_core.ServiceUnavailable('synthetic fault message'),
    'api_TemporaryRedirect': lambda: api_core.TemporaryRedirect('synthetic fault message'),
    'api_TooManyRequests': lambda: api_core.TooManyRequests('synthetic fault message'),
    'api_Unauthenticated': lambda: api_core.Unauthenticated('synthetic fault message'),
    'api_Unauthorized': lambda: api_core.Unauthorized('synthetic fault message'),
    'api_Unknown': lambda: api_core.Unknown('synthetic fault message'),
    'b_ArithmeticError': lambda: ArithmeticError('synthetic fault message'),
    'b_AssertionError': lambda: AssertionError('synthetic fault message'),
    'b_AttributeError': lambda: AttributeError('synthetic fault message'),
    'b_BrokenPipeError': lambda: BrokenPipeError('synthetic fault message'),
    'b_ConnectionAbortedError': lambda: ConnectionAbortedError('synthetic fault message'),
    'b_ConnectionError': lambda: ConnectionError('synthetic fault message'),
    'b_ConnectionRefusedError': lambda: ConnectionRefusedError('synthetic fault message'),
    'b_ConnectionResetError': lambda: ConnectionResetError('synthetic fault message'),
    'b_EOFError': lambda: EOFError('synthetic fault message'),
    'b_Exception': lambda: Exception('synthetic fault message'),
    'b_GeneratorExit': lambda: GeneratorExit('synthetic fault message'),
    'b_IndexError': lambda: IndexError('synthetic fault message'),
    'b_JSONDecodeError': lambda: json.JSONDecodeError('bad json', 'doc', 1),
    'b_KeyError': lambda: KeyError('synthetic fault message'),
    'b_LookupError': lambda: LookupError('synthetic fault message'),
    'b_MemoryError': lambda: MemoryError('synthetic fault message'),
    'b_NotImplementedError': lambda: NotImplementedError('synthetic fault message'),
    'b_OSError': lambda: OSError('synthetic fault message'),
    'b_OverflowError': lambda: OverflowError('synthetic fault message'),
    'b_RecursionError': lambda: RecursionError('synthetic fault message'),
    'b_RuntimeError': lambda: RuntimeError('synthetic fault message'),
    'b_StopIteration': lambda: StopIteration('synthetic fault message'),
    'b_TimeoutError': lambda: TimeoutError('synthetic fault message'),
    'b_TypeError': lambda: TypeError('synthetic fault message'),
    'b_UnicodeDecodeError': lambda: UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'invalid start byte'),
    'b_ValueError': lambda: ValueError('synthetic fault message'),
    'b_ZeroDivisionError': lambda: ZeroDivisionError('synthetic fault message'),
    'b_wave_Error': lambda: wave.Error('synthetic fault message'),
    't_DecodedDurationMismatch': lambda: DecodedDurationMismatch('synthetic fault message'),
    't_FirestoreContentionExhausted': lambda: FirestoreContentionExhausted('synthetic fault message'),
    't_InvalidRetainedManifest': lambda: InvalidRetainedManifest('synthetic fault message'),
    't_RetainedAudioInvalid': lambda: RetainedAudioInvalid('synthetic fault message'),
    't_RetainedAudioOutsideAdmittedSource': lambda: RetainedAudioOutsideAdmittedSource('synthetic fault message'),
    't_StagedArtifactInvalid': lambda: StagedArtifactInvalid('synthetic fault message'),
    't_StagedAudioInvalid': lambda: StagedAudioInvalid('synthetic fault message'),
}


def _make(label):
    return _FAULTS[label]()


def test_b90_c00000_asr_recovery_decode_payload_invalid_1_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'decode_payload_invalid'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00001_asr_recovery_decode_payload_invalid_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'decode_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00002_asr_recovery_decode_payload_invalid_1_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'decode_payload_invalid'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00003_asr_recovery_decode_payload_invalid_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'decode_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00004_asr_recovery_decode_payload_invalid_2_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'decode_payload_invalid'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00005_asr_recovery_decode_payload_invalid_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'decode_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00006_asr_recovery_decode_payload_invalid_2_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'decode_payload_invalid'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00007_asr_recovery_decode_payload_invalid_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'decode_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00008_asr_recovery_decode_payload_invalid_7_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'decode_payload_invalid'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00009_asr_recovery_decode_payload_invalid_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'decode_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00010_asr_recovery_decode_payload_invalid_7_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'decode_payload_invalid'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00011_asr_recovery_decode_payload_invalid_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'decode_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00012_asr_recovery_decode_payload_invalid_99_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'decode_payload_invalid'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00013_asr_recovery_decode_payload_invalid_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'decode_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00014_asr_recovery_decode_payload_invalid_99_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'decode_payload_invalid'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00015_asr_recovery_decode_payload_invalid_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'decode_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00016_asr_recovery_decode_payload_invalid_evidence():
    assert transient_failure_evidence('asr_recovery', 'decode_payload_invalid') == {
        'stage': 'asr_recovery',
        'reason': 'decode_payload_invalid',
    }


def test_b90_c00017_asr_recovery_decode_payload_invalid_validator():
    try:
        validate_worker_failure({'stage': 'asr_recovery', 'reason': 'decode_payload_invalid'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00018_asr_recovery_decoded_duration_mismatch_1_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'decoded_duration_mismatch'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00019_asr_recovery_decoded_duration_mismatch_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00020_asr_recovery_decoded_duration_mismatch_1_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'decoded_duration_mismatch'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00021_asr_recovery_decoded_duration_mismatch_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00022_asr_recovery_decoded_duration_mismatch_2_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'decoded_duration_mismatch'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00023_asr_recovery_decoded_duration_mismatch_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00024_asr_recovery_decoded_duration_mismatch_2_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'decoded_duration_mismatch'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00025_asr_recovery_decoded_duration_mismatch_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00026_asr_recovery_decoded_duration_mismatch_7_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'decoded_duration_mismatch'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00027_asr_recovery_decoded_duration_mismatch_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00028_asr_recovery_decoded_duration_mismatch_7_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'decoded_duration_mismatch'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00029_asr_recovery_decoded_duration_mismatch_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00030_asr_recovery_decoded_duration_mismatch_99_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'decoded_duration_mismatch'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00031_asr_recovery_decoded_duration_mismatch_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00032_asr_recovery_decoded_duration_mismatch_99_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'decoded_duration_mismatch'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00033_asr_recovery_decoded_duration_mismatch_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00034_asr_recovery_decoded_duration_mismatch_evidence():
    assert transient_failure_evidence('asr_recovery', 'decoded_duration_mismatch') == {
        'stage': 'asr_recovery',
        'reason': 'decoded_duration_mismatch',
    }


def test_b90_c00035_asr_recovery_decoded_duration_mismatch_validator():
    try:
        validate_worker_failure({'stage': 'asr_recovery', 'reason': 'decoded_duration_mismatch'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00036_asr_recovery_empty_asr_1_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'empty_asr'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00037_asr_recovery_empty_asr_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'empty_asr'}, disposition_enabled=True)
        is False
    )


def test_b90_c00038_asr_recovery_empty_asr_1_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'empty_asr'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00039_asr_recovery_empty_asr_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'empty_asr'}, disposition_enabled=False)
        is False
    )


def test_b90_c00040_asr_recovery_empty_asr_2_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'empty_asr'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00041_asr_recovery_empty_asr_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'empty_asr'}, disposition_enabled=True)
        is False
    )


def test_b90_c00042_asr_recovery_empty_asr_2_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'empty_asr'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00043_asr_recovery_empty_asr_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'empty_asr'}, disposition_enabled=False)
        is False
    )


def test_b90_c00044_asr_recovery_empty_asr_7_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'empty_asr'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00045_asr_recovery_empty_asr_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'empty_asr'}, disposition_enabled=True)
        is False
    )


def test_b90_c00046_asr_recovery_empty_asr_7_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'empty_asr'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00047_asr_recovery_empty_asr_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'empty_asr'}, disposition_enabled=False)
        is False
    )


def test_b90_c00048_asr_recovery_empty_asr_99_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'empty_asr'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00049_asr_recovery_empty_asr_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'empty_asr'}, disposition_enabled=True)
        is False
    )


def test_b90_c00050_asr_recovery_empty_asr_99_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'empty_asr'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00051_asr_recovery_empty_asr_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'empty_asr'}, disposition_enabled=False)
        is False
    )


def test_b90_c00052_asr_recovery_empty_asr_evidence():
    assert transient_failure_evidence('asr_recovery', 'empty_asr') == {'stage': 'asr_recovery', 'reason': 'empty_asr'}


def test_b90_c00053_asr_recovery_empty_asr_validator():
    try:
        validate_worker_failure({'stage': 'asr_recovery', 'reason': 'empty_asr'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00054_asr_recovery_no_owned_words_1_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'no_owned_words'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00055_asr_recovery_no_owned_words_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'no_owned_words'}, disposition_enabled=True)
        is False
    )


def test_b90_c00056_asr_recovery_no_owned_words_1_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'no_owned_words'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00057_asr_recovery_no_owned_words_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'no_owned_words'}, disposition_enabled=False)
        is False
    )


def test_b90_c00058_asr_recovery_no_owned_words_2_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'no_owned_words'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00059_asr_recovery_no_owned_words_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'no_owned_words'}, disposition_enabled=True)
        is False
    )


def test_b90_c00060_asr_recovery_no_owned_words_2_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'no_owned_words'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00061_asr_recovery_no_owned_words_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'no_owned_words'}, disposition_enabled=False)
        is False
    )


def test_b90_c00062_asr_recovery_no_owned_words_7_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'no_owned_words'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00063_asr_recovery_no_owned_words_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'no_owned_words'}, disposition_enabled=True)
        is False
    )


def test_b90_c00064_asr_recovery_no_owned_words_7_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'no_owned_words'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00065_asr_recovery_no_owned_words_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'no_owned_words'}, disposition_enabled=False)
        is False
    )


def test_b90_c00066_asr_recovery_no_owned_words_99_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'no_owned_words'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00067_asr_recovery_no_owned_words_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'no_owned_words'}, disposition_enabled=True)
        is False
    )


def test_b90_c00068_asr_recovery_no_owned_words_99_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'no_owned_words'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00069_asr_recovery_no_owned_words_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'no_owned_words'}, disposition_enabled=False)
        is False
    )


def test_b90_c00070_asr_recovery_no_owned_words_evidence():
    assert transient_failure_evidence('asr_recovery', 'no_owned_words') == {
        'stage': 'asr_recovery',
        'reason': 'no_owned_words',
    }


def test_b90_c00071_asr_recovery_no_owned_words_validator():
    try:
        validate_worker_failure({'stage': 'asr_recovery', 'reason': 'no_owned_words'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00072_asr_recovery_outside_admitted_source_1_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'outside_admitted_source'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00073_asr_recovery_outside_admitted_source_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00074_asr_recovery_outside_admitted_source_1_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'outside_admitted_source'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00075_asr_recovery_outside_admitted_source_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00076_asr_recovery_outside_admitted_source_2_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'outside_admitted_source'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00077_asr_recovery_outside_admitted_source_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00078_asr_recovery_outside_admitted_source_2_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'outside_admitted_source'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00079_asr_recovery_outside_admitted_source_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00080_asr_recovery_outside_admitted_source_7_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'outside_admitted_source'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00081_asr_recovery_outside_admitted_source_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00082_asr_recovery_outside_admitted_source_7_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'outside_admitted_source'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00083_asr_recovery_outside_admitted_source_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00084_asr_recovery_outside_admitted_source_99_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'outside_admitted_source'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00085_asr_recovery_outside_admitted_source_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00086_asr_recovery_outside_admitted_source_99_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'outside_admitted_source'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00087_asr_recovery_outside_admitted_source_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00088_asr_recovery_outside_admitted_source_evidence():
    assert transient_failure_evidence('asr_recovery', 'outside_admitted_source') == {
        'stage': 'asr_recovery',
        'reason': 'outside_admitted_source',
    }


def test_b90_c00089_asr_recovery_outside_admitted_source_validator():
    try:
        validate_worker_failure({'stage': 'asr_recovery', 'reason': 'outside_admitted_source'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00090_asr_recovery_persist_payload_invalid_1_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'persist_payload_invalid'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00091_asr_recovery_persist_payload_invalid_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'persist_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00092_asr_recovery_persist_payload_invalid_1_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'persist_payload_invalid'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00093_asr_recovery_persist_payload_invalid_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'persist_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00094_asr_recovery_persist_payload_invalid_2_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'persist_payload_invalid'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00095_asr_recovery_persist_payload_invalid_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'persist_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00096_asr_recovery_persist_payload_invalid_2_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'persist_payload_invalid'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00097_asr_recovery_persist_payload_invalid_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'persist_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00098_asr_recovery_persist_payload_invalid_7_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'persist_payload_invalid'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00099_asr_recovery_persist_payload_invalid_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'persist_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00100_asr_recovery_persist_payload_invalid_7_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'persist_payload_invalid'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00101_asr_recovery_persist_payload_invalid_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'persist_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00102_asr_recovery_persist_payload_invalid_99_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'persist_payload_invalid'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00103_asr_recovery_persist_payload_invalid_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'persist_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00104_asr_recovery_persist_payload_invalid_99_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'persist_payload_invalid'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00105_asr_recovery_persist_payload_invalid_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'persist_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00106_asr_recovery_persist_payload_invalid_evidence():
    assert transient_failure_evidence('asr_recovery', 'persist_payload_invalid') == {
        'stage': 'asr_recovery',
        'reason': 'persist_payload_invalid',
    }


def test_b90_c00107_asr_recovery_persist_payload_invalid_validator():
    try:
        validate_worker_failure({'stage': 'asr_recovery', 'reason': 'persist_payload_invalid'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00108_asr_recovery_retained_audio_invalid_1_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'retained_audio_invalid'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00109_asr_recovery_retained_audio_invalid_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00110_asr_recovery_retained_audio_invalid_1_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'retained_audio_invalid'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00111_asr_recovery_retained_audio_invalid_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00112_asr_recovery_retained_audio_invalid_2_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'retained_audio_invalid'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00113_asr_recovery_retained_audio_invalid_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00114_asr_recovery_retained_audio_invalid_2_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'retained_audio_invalid'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00115_asr_recovery_retained_audio_invalid_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00116_asr_recovery_retained_audio_invalid_7_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'retained_audio_invalid'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00117_asr_recovery_retained_audio_invalid_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00118_asr_recovery_retained_audio_invalid_7_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'retained_audio_invalid'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00119_asr_recovery_retained_audio_invalid_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00120_asr_recovery_retained_audio_invalid_99_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'retained_audio_invalid'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00121_asr_recovery_retained_audio_invalid_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00122_asr_recovery_retained_audio_invalid_99_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'retained_audio_invalid'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00123_asr_recovery_retained_audio_invalid_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00124_asr_recovery_retained_audio_invalid_evidence():
    assert transient_failure_evidence('asr_recovery', 'retained_audio_invalid') == {
        'stage': 'asr_recovery',
        'reason': 'retained_audio_invalid',
    }


def test_b90_c00125_asr_recovery_retained_audio_invalid_validator():
    try:
        validate_worker_failure({'stage': 'asr_recovery', 'reason': 'retained_audio_invalid'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00126_asr_recovery_staged_audio_invalid_1_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'staged_audio_invalid'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00127_asr_recovery_staged_audio_invalid_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'staged_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00128_asr_recovery_staged_audio_invalid_1_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'staged_audio_invalid'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00129_asr_recovery_staged_audio_invalid_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00130_asr_recovery_staged_audio_invalid_2_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'staged_audio_invalid'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00131_asr_recovery_staged_audio_invalid_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'staged_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00132_asr_recovery_staged_audio_invalid_2_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'staged_audio_invalid'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00133_asr_recovery_staged_audio_invalid_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00134_asr_recovery_staged_audio_invalid_7_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'staged_audio_invalid'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00135_asr_recovery_staged_audio_invalid_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'staged_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00136_asr_recovery_staged_audio_invalid_7_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'staged_audio_invalid'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00137_asr_recovery_staged_audio_invalid_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00138_asr_recovery_staged_audio_invalid_99_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'staged_audio_invalid'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00139_asr_recovery_staged_audio_invalid_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'staged_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00140_asr_recovery_staged_audio_invalid_99_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'staged_audio_invalid'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00141_asr_recovery_staged_audio_invalid_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00142_asr_recovery_staged_audio_invalid_evidence():
    assert transient_failure_evidence('asr_recovery', 'staged_audio_invalid') == {
        'stage': 'asr_recovery',
        'reason': 'staged_audio_invalid',
    }


def test_b90_c00143_asr_recovery_staged_audio_invalid_validator():
    try:
        validate_worker_failure({'stage': 'asr_recovery', 'reason': 'staged_audio_invalid'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00144_asr_recovery_unknown_1_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'unknown'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00145_asr_recovery_unknown_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'unknown'}, disposition_enabled=True)
        is False
    )


def test_b90_c00146_asr_recovery_unknown_1_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'unknown'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00147_asr_recovery_unknown_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'unknown'}, disposition_enabled=False)
        is False
    )


def test_b90_c00148_asr_recovery_unknown_2_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'unknown'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00149_asr_recovery_unknown_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'unknown'}, disposition_enabled=True)
        is False
    )


def test_b90_c00150_asr_recovery_unknown_2_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'unknown'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00151_asr_recovery_unknown_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'unknown'}, disposition_enabled=False)
        is False
    )


def test_b90_c00152_asr_recovery_unknown_7_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'unknown'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00153_asr_recovery_unknown_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'unknown'}, disposition_enabled=True)
        is False
    )


def test_b90_c00154_asr_recovery_unknown_7_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'unknown'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00155_asr_recovery_unknown_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'unknown'}, disposition_enabled=False)
        is False
    )


def test_b90_c00156_asr_recovery_unknown_99_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'unknown'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00157_asr_recovery_unknown_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'unknown'}, disposition_enabled=True)
        is False
    )


def test_b90_c00158_asr_recovery_unknown_99_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'unknown'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00159_asr_recovery_unknown_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'unknown'}, disposition_enabled=False)
        is False
    )


def test_b90_c00160_asr_recovery_unknown_evidence():
    assert transient_failure_evidence('asr_recovery', 'unknown') == {'stage': 'asr_recovery', 'reason': 'unknown'}


def test_b90_c00161_asr_recovery_unknown_validator():
    try:
        validate_worker_failure({'stage': 'asr_recovery', 'reason': 'unknown'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is False


def test_b90_c00162_asr_recovery_unsupported_language_1_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'unsupported_language'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00163_asr_recovery_unsupported_language_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'unsupported_language'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00164_asr_recovery_unsupported_language_1_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'unsupported_language'}, 1, 'false')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00165_asr_recovery_unsupported_language_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00166_asr_recovery_unsupported_language_2_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'unsupported_language'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00167_asr_recovery_unsupported_language_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'unsupported_language'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00168_asr_recovery_unsupported_language_2_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'unsupported_language'}, 2, 'false')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00169_asr_recovery_unsupported_language_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00170_asr_recovery_unsupported_language_7_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'unsupported_language'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00171_asr_recovery_unsupported_language_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'unsupported_language'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00172_asr_recovery_unsupported_language_7_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'unsupported_language'}, 7, 'false')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00173_asr_recovery_unsupported_language_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00174_asr_recovery_unsupported_language_99_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'unsupported_language'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00175_asr_recovery_unsupported_language_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'unsupported_language'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00176_asr_recovery_unsupported_language_99_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'unsupported_language'}, 99, 'false')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00177_asr_recovery_unsupported_language_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00178_asr_recovery_unsupported_language_evidence():
    assert transient_failure_evidence('asr_recovery', 'unsupported_language') == {
        'stage': 'asr_recovery',
        'reason': 'unsupported_language',
    }


def test_b90_c00179_asr_recovery_unsupported_language_validator():
    try:
        validate_worker_failure({'stage': 'asr_recovery', 'reason': 'unsupported_language'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00180_asr_recovery_vad_bounds_1_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'vad_bounds'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00181_asr_recovery_vad_bounds_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_bounds'}, disposition_enabled=True)
        is True
    )


def test_b90_c00182_asr_recovery_vad_bounds_1_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'vad_bounds'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00183_asr_recovery_vad_bounds_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_bounds'}, disposition_enabled=False)
        is False
    )


def test_b90_c00184_asr_recovery_vad_bounds_2_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'vad_bounds'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00185_asr_recovery_vad_bounds_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_bounds'}, disposition_enabled=True)
        is True
    )


def test_b90_c00186_asr_recovery_vad_bounds_2_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'vad_bounds'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00187_asr_recovery_vad_bounds_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_bounds'}, disposition_enabled=False)
        is False
    )


def test_b90_c00188_asr_recovery_vad_bounds_7_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'vad_bounds'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00189_asr_recovery_vad_bounds_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_bounds'}, disposition_enabled=True)
        is True
    )


def test_b90_c00190_asr_recovery_vad_bounds_7_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'vad_bounds'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00191_asr_recovery_vad_bounds_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_bounds'}, disposition_enabled=False)
        is False
    )


def test_b90_c00192_asr_recovery_vad_bounds_99_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'vad_bounds'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00193_asr_recovery_vad_bounds_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_bounds'}, disposition_enabled=True)
        is True
    )


def test_b90_c00194_asr_recovery_vad_bounds_99_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'vad_bounds'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00195_asr_recovery_vad_bounds_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_bounds'}, disposition_enabled=False)
        is False
    )


def test_b90_c00196_asr_recovery_vad_bounds_evidence():
    assert transient_failure_evidence('asr_recovery', 'vad_bounds') == {'stage': 'asr_recovery', 'reason': 'vad_bounds'}


def test_b90_c00197_asr_recovery_vad_bounds_validator():
    try:
        validate_worker_failure({'stage': 'asr_recovery', 'reason': 'vad_bounds'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00198_asr_recovery_vad_nonfinite_1_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'vad_nonfinite'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00199_asr_recovery_vad_nonfinite_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_b90_c00200_asr_recovery_vad_nonfinite_1_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'vad_nonfinite'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00201_asr_recovery_vad_nonfinite_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_nonfinite'}, disposition_enabled=False)
        is False
    )


def test_b90_c00202_asr_recovery_vad_nonfinite_2_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'vad_nonfinite'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00203_asr_recovery_vad_nonfinite_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_b90_c00204_asr_recovery_vad_nonfinite_2_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'vad_nonfinite'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00205_asr_recovery_vad_nonfinite_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_nonfinite'}, disposition_enabled=False)
        is False
    )


def test_b90_c00206_asr_recovery_vad_nonfinite_7_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'vad_nonfinite'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00207_asr_recovery_vad_nonfinite_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_b90_c00208_asr_recovery_vad_nonfinite_7_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'vad_nonfinite'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00209_asr_recovery_vad_nonfinite_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_nonfinite'}, disposition_enabled=False)
        is False
    )


def test_b90_c00210_asr_recovery_vad_nonfinite_99_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'vad_nonfinite'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00211_asr_recovery_vad_nonfinite_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_b90_c00212_asr_recovery_vad_nonfinite_99_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'vad_nonfinite'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00213_asr_recovery_vad_nonfinite_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_nonfinite'}, disposition_enabled=False)
        is False
    )


def test_b90_c00214_asr_recovery_vad_nonfinite_evidence():
    assert transient_failure_evidence('asr_recovery', 'vad_nonfinite') == {
        'stage': 'asr_recovery',
        'reason': 'vad_nonfinite',
    }


def test_b90_c00215_asr_recovery_vad_nonfinite_validator():
    try:
        validate_worker_failure({'stage': 'asr_recovery', 'reason': 'vad_nonfinite'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00216_asr_recovery_vad_order_1_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'vad_order'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00217_asr_recovery_vad_order_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_order'}, disposition_enabled=True)
        is True
    )


def test_b90_c00218_asr_recovery_vad_order_1_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'vad_order'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00219_asr_recovery_vad_order_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_order'}, disposition_enabled=False)
        is False
    )


def test_b90_c00220_asr_recovery_vad_order_2_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'vad_order'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00221_asr_recovery_vad_order_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_order'}, disposition_enabled=True)
        is True
    )


def test_b90_c00222_asr_recovery_vad_order_2_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'vad_order'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00223_asr_recovery_vad_order_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_order'}, disposition_enabled=False)
        is False
    )


def test_b90_c00224_asr_recovery_vad_order_7_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'vad_order'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00225_asr_recovery_vad_order_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_order'}, disposition_enabled=True)
        is True
    )


def test_b90_c00226_asr_recovery_vad_order_7_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'vad_order'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00227_asr_recovery_vad_order_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_order'}, disposition_enabled=False)
        is False
    )


def test_b90_c00228_asr_recovery_vad_order_99_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'vad_order'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00229_asr_recovery_vad_order_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_order'}, disposition_enabled=True)
        is True
    )


def test_b90_c00230_asr_recovery_vad_order_99_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'vad_order'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00231_asr_recovery_vad_order_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_order'}, disposition_enabled=False)
        is False
    )


def test_b90_c00232_asr_recovery_vad_order_evidence():
    assert transient_failure_evidence('asr_recovery', 'vad_order') == {'stage': 'asr_recovery', 'reason': 'vad_order'}


def test_b90_c00233_asr_recovery_vad_order_validator():
    try:
        validate_worker_failure({'stage': 'asr_recovery', 'reason': 'vad_order'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00234_asr_recovery_word_clock_1_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'word_clock'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00235_asr_recovery_word_clock_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_clock'}, disposition_enabled=True)
        is True
    )


def test_b90_c00236_asr_recovery_word_clock_1_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'word_clock'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00237_asr_recovery_word_clock_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_clock'}, disposition_enabled=False)
        is False
    )


def test_b90_c00238_asr_recovery_word_clock_2_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'word_clock'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00239_asr_recovery_word_clock_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_clock'}, disposition_enabled=True)
        is True
    )


def test_b90_c00240_asr_recovery_word_clock_2_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'word_clock'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00241_asr_recovery_word_clock_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_clock'}, disposition_enabled=False)
        is False
    )


def test_b90_c00242_asr_recovery_word_clock_7_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'word_clock'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00243_asr_recovery_word_clock_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_clock'}, disposition_enabled=True)
        is True
    )


def test_b90_c00244_asr_recovery_word_clock_7_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'word_clock'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00245_asr_recovery_word_clock_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_clock'}, disposition_enabled=False)
        is False
    )


def test_b90_c00246_asr_recovery_word_clock_99_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'word_clock'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00247_asr_recovery_word_clock_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_clock'}, disposition_enabled=True)
        is True
    )


def test_b90_c00248_asr_recovery_word_clock_99_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'word_clock'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00249_asr_recovery_word_clock_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_clock'}, disposition_enabled=False)
        is False
    )


def test_b90_c00250_asr_recovery_word_clock_evidence():
    assert transient_failure_evidence('asr_recovery', 'word_clock') == {'stage': 'asr_recovery', 'reason': 'word_clock'}


def test_b90_c00251_asr_recovery_word_clock_validator():
    try:
        validate_worker_failure({'stage': 'asr_recovery', 'reason': 'word_clock'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00252_asr_recovery_word_sequence_1_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'word_sequence'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00253_asr_recovery_word_sequence_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_b90_c00254_asr_recovery_word_sequence_1_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'word_sequence'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00255_asr_recovery_word_sequence_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_sequence'}, disposition_enabled=False)
        is False
    )


def test_b90_c00256_asr_recovery_word_sequence_2_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'word_sequence'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00257_asr_recovery_word_sequence_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_b90_c00258_asr_recovery_word_sequence_2_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'word_sequence'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00259_asr_recovery_word_sequence_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_sequence'}, disposition_enabled=False)
        is False
    )


def test_b90_c00260_asr_recovery_word_sequence_7_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'word_sequence'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00261_asr_recovery_word_sequence_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_b90_c00262_asr_recovery_word_sequence_7_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'word_sequence'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00263_asr_recovery_word_sequence_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_sequence'}, disposition_enabled=False)
        is False
    )


def test_b90_c00264_asr_recovery_word_sequence_99_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'word_sequence'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00265_asr_recovery_word_sequence_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_b90_c00266_asr_recovery_word_sequence_99_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'word_sequence'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00267_asr_recovery_word_sequence_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_sequence'}, disposition_enabled=False)
        is False
    )


def test_b90_c00268_asr_recovery_word_sequence_evidence():
    assert transient_failure_evidence('asr_recovery', 'word_sequence') == {
        'stage': 'asr_recovery',
        'reason': 'word_sequence',
    }


def test_b90_c00269_asr_recovery_word_sequence_validator():
    try:
        validate_worker_failure({'stage': 'asr_recovery', 'reason': 'word_sequence'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00270_asr_recovery_word_shape_1_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'word_shape'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00271_asr_recovery_word_shape_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_shape'}, disposition_enabled=True)
        is True
    )


def test_b90_c00272_asr_recovery_word_shape_1_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'word_shape'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00273_asr_recovery_word_shape_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_shape'}, disposition_enabled=False)
        is False
    )


def test_b90_c00274_asr_recovery_word_shape_2_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'word_shape'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00275_asr_recovery_word_shape_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_shape'}, disposition_enabled=True)
        is True
    )


def test_b90_c00276_asr_recovery_word_shape_2_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'word_shape'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00277_asr_recovery_word_shape_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_shape'}, disposition_enabled=False)
        is False
    )


def test_b90_c00278_asr_recovery_word_shape_7_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'word_shape'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00279_asr_recovery_word_shape_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_shape'}, disposition_enabled=True)
        is True
    )


def test_b90_c00280_asr_recovery_word_shape_7_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'word_shape'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00281_asr_recovery_word_shape_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_shape'}, disposition_enabled=False)
        is False
    )


def test_b90_c00282_asr_recovery_word_shape_99_true():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'word_shape'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00283_asr_recovery_word_shape_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_shape'}, disposition_enabled=True)
        is True
    )


def test_b90_c00284_asr_recovery_word_shape_99_false():
    lines = _drive({'stage': 'asr_recovery', 'reason': 'word_shape'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00285_asr_recovery_word_shape_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_shape'}, disposition_enabled=False)
        is False
    )


def test_b90_c00286_asr_recovery_word_shape_evidence():
    assert transient_failure_evidence('asr_recovery', 'word_shape') == {'stage': 'asr_recovery', 'reason': 'word_shape'}


def test_b90_c00287_asr_recovery_word_shape_validator():
    try:
        validate_worker_failure({'stage': 'asr_recovery', 'reason': 'word_shape'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00288_assemble_words_decode_payload_invalid_1_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'decode_payload_invalid'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00289_assemble_words_decode_payload_invalid_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'decode_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00290_assemble_words_decode_payload_invalid_1_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'decode_payload_invalid'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00291_assemble_words_decode_payload_invalid_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'decode_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00292_assemble_words_decode_payload_invalid_2_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'decode_payload_invalid'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00293_assemble_words_decode_payload_invalid_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'decode_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00294_assemble_words_decode_payload_invalid_2_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'decode_payload_invalid'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00295_assemble_words_decode_payload_invalid_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'decode_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00296_assemble_words_decode_payload_invalid_7_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'decode_payload_invalid'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00297_assemble_words_decode_payload_invalid_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'decode_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00298_assemble_words_decode_payload_invalid_7_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'decode_payload_invalid'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00299_assemble_words_decode_payload_invalid_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'decode_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00300_assemble_words_decode_payload_invalid_99_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'decode_payload_invalid'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00301_assemble_words_decode_payload_invalid_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'decode_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00302_assemble_words_decode_payload_invalid_99_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'decode_payload_invalid'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00303_assemble_words_decode_payload_invalid_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'decode_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00304_assemble_words_decode_payload_invalid_evidence():
    assert transient_failure_evidence('assemble_words', 'decode_payload_invalid') == {
        'stage': 'assemble_words',
        'reason': 'decode_payload_invalid',
    }


def test_b90_c00305_assemble_words_decode_payload_invalid_validator():
    try:
        validate_worker_failure({'stage': 'assemble_words', 'reason': 'decode_payload_invalid'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00306_assemble_words_decoded_duration_mismatch_1_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'decoded_duration_mismatch'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00307_assemble_words_decoded_duration_mismatch_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00308_assemble_words_decoded_duration_mismatch_1_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'decoded_duration_mismatch'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00309_assemble_words_decoded_duration_mismatch_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00310_assemble_words_decoded_duration_mismatch_2_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'decoded_duration_mismatch'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00311_assemble_words_decoded_duration_mismatch_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00312_assemble_words_decoded_duration_mismatch_2_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'decoded_duration_mismatch'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00313_assemble_words_decoded_duration_mismatch_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00314_assemble_words_decoded_duration_mismatch_7_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'decoded_duration_mismatch'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00315_assemble_words_decoded_duration_mismatch_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00316_assemble_words_decoded_duration_mismatch_7_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'decoded_duration_mismatch'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00317_assemble_words_decoded_duration_mismatch_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00318_assemble_words_decoded_duration_mismatch_99_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'decoded_duration_mismatch'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00319_assemble_words_decoded_duration_mismatch_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00320_assemble_words_decoded_duration_mismatch_99_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'decoded_duration_mismatch'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00321_assemble_words_decoded_duration_mismatch_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00322_assemble_words_decoded_duration_mismatch_evidence():
    assert transient_failure_evidence('assemble_words', 'decoded_duration_mismatch') == {
        'stage': 'assemble_words',
        'reason': 'decoded_duration_mismatch',
    }


def test_b90_c00323_assemble_words_decoded_duration_mismatch_validator():
    try:
        validate_worker_failure({'stage': 'assemble_words', 'reason': 'decoded_duration_mismatch'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00324_assemble_words_empty_asr_1_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'empty_asr'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_empty_ladder' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00325_assemble_words_empty_asr_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'empty_asr'}, disposition_enabled=True)
        is False
    )


def test_b90_c00326_assemble_words_empty_asr_1_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'empty_asr'}, 1, 'false')
    assert ('INFO', True) in [(level, 'event=batch_empty_ladder' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00327_assemble_words_empty_asr_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'empty_asr'}, disposition_enabled=False)
        is False
    )


def test_b90_c00328_assemble_words_empty_asr_2_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'empty_asr'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_empty_ladder' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00329_assemble_words_empty_asr_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'empty_asr'}, disposition_enabled=True)
        is False
    )


def test_b90_c00330_assemble_words_empty_asr_2_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'empty_asr'}, 2, 'false')
    assert ('INFO', True) in [(level, 'event=batch_empty_ladder' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00331_assemble_words_empty_asr_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'empty_asr'}, disposition_enabled=False)
        is False
    )


def test_b90_c00332_assemble_words_empty_asr_7_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'empty_asr'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_empty_ladder' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00333_assemble_words_empty_asr_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'empty_asr'}, disposition_enabled=True)
        is False
    )


def test_b90_c00334_assemble_words_empty_asr_7_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'empty_asr'}, 7, 'false')
    assert ('INFO', True) in [(level, 'event=batch_empty_ladder' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00335_assemble_words_empty_asr_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'empty_asr'}, disposition_enabled=False)
        is False
    )


def test_b90_c00336_assemble_words_empty_asr_99_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'empty_asr'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_empty_ladder' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00337_assemble_words_empty_asr_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'empty_asr'}, disposition_enabled=True)
        is False
    )


def test_b90_c00338_assemble_words_empty_asr_99_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'empty_asr'}, 99, 'false')
    assert ('INFO', True) in [(level, 'event=batch_empty_ladder' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00339_assemble_words_empty_asr_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'empty_asr'}, disposition_enabled=False)
        is False
    )


def test_b90_c00340_assemble_words_empty_asr_evidence():
    assert transient_failure_evidence('assemble_words', 'empty_asr') == {
        'stage': 'assemble_words',
        'reason': 'empty_asr',
    }


def test_b90_c00341_assemble_words_empty_asr_validator():
    try:
        validate_worker_failure({'stage': 'assemble_words', 'reason': 'empty_asr'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00342_assemble_words_no_owned_words_1_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'no_owned_words'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_empty_ladder' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00343_assemble_words_no_owned_words_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'no_owned_words'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00344_assemble_words_no_owned_words_1_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'no_owned_words'}, 1, 'false')
    assert ('INFO', True) in [(level, 'event=batch_empty_ladder' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00345_assemble_words_no_owned_words_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'no_owned_words'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00346_assemble_words_no_owned_words_2_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'no_owned_words'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_empty_ladder' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00347_assemble_words_no_owned_words_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'no_owned_words'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00348_assemble_words_no_owned_words_2_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'no_owned_words'}, 2, 'false')
    assert ('INFO', True) in [(level, 'event=batch_empty_ladder' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00349_assemble_words_no_owned_words_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'no_owned_words'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00350_assemble_words_no_owned_words_7_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'no_owned_words'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_empty_ladder' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00351_assemble_words_no_owned_words_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'no_owned_words'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00352_assemble_words_no_owned_words_7_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'no_owned_words'}, 7, 'false')
    assert ('INFO', True) in [(level, 'event=batch_empty_ladder' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00353_assemble_words_no_owned_words_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'no_owned_words'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00354_assemble_words_no_owned_words_99_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'no_owned_words'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_empty_ladder' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00355_assemble_words_no_owned_words_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'no_owned_words'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00356_assemble_words_no_owned_words_99_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'no_owned_words'}, 99, 'false')
    assert ('INFO', True) in [(level, 'event=batch_empty_ladder' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00357_assemble_words_no_owned_words_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'no_owned_words'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00358_assemble_words_no_owned_words_evidence():
    assert transient_failure_evidence('assemble_words', 'no_owned_words') == {
        'stage': 'assemble_words',
        'reason': 'no_owned_words',
    }


def test_b90_c00359_assemble_words_no_owned_words_validator():
    try:
        validate_worker_failure({'stage': 'assemble_words', 'reason': 'no_owned_words'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00360_assemble_words_outside_admitted_source_1_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'outside_admitted_source'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00361_assemble_words_outside_admitted_source_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00362_assemble_words_outside_admitted_source_1_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'outside_admitted_source'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00363_assemble_words_outside_admitted_source_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00364_assemble_words_outside_admitted_source_2_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'outside_admitted_source'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00365_assemble_words_outside_admitted_source_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00366_assemble_words_outside_admitted_source_2_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'outside_admitted_source'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00367_assemble_words_outside_admitted_source_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00368_assemble_words_outside_admitted_source_7_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'outside_admitted_source'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00369_assemble_words_outside_admitted_source_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00370_assemble_words_outside_admitted_source_7_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'outside_admitted_source'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00371_assemble_words_outside_admitted_source_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00372_assemble_words_outside_admitted_source_99_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'outside_admitted_source'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00373_assemble_words_outside_admitted_source_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00374_assemble_words_outside_admitted_source_99_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'outside_admitted_source'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00375_assemble_words_outside_admitted_source_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00376_assemble_words_outside_admitted_source_evidence():
    assert transient_failure_evidence('assemble_words', 'outside_admitted_source') == {
        'stage': 'assemble_words',
        'reason': 'outside_admitted_source',
    }


def test_b90_c00377_assemble_words_outside_admitted_source_validator():
    try:
        validate_worker_failure({'stage': 'assemble_words', 'reason': 'outside_admitted_source'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00378_assemble_words_persist_payload_invalid_1_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'persist_payload_invalid'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00379_assemble_words_persist_payload_invalid_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'persist_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00380_assemble_words_persist_payload_invalid_1_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'persist_payload_invalid'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00381_assemble_words_persist_payload_invalid_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'persist_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00382_assemble_words_persist_payload_invalid_2_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'persist_payload_invalid'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00383_assemble_words_persist_payload_invalid_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'persist_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00384_assemble_words_persist_payload_invalid_2_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'persist_payload_invalid'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00385_assemble_words_persist_payload_invalid_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'persist_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00386_assemble_words_persist_payload_invalid_7_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'persist_payload_invalid'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00387_assemble_words_persist_payload_invalid_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'persist_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00388_assemble_words_persist_payload_invalid_7_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'persist_payload_invalid'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00389_assemble_words_persist_payload_invalid_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'persist_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00390_assemble_words_persist_payload_invalid_99_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'persist_payload_invalid'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00391_assemble_words_persist_payload_invalid_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'persist_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00392_assemble_words_persist_payload_invalid_99_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'persist_payload_invalid'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00393_assemble_words_persist_payload_invalid_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'persist_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00394_assemble_words_persist_payload_invalid_evidence():
    assert transient_failure_evidence('assemble_words', 'persist_payload_invalid') == {
        'stage': 'assemble_words',
        'reason': 'persist_payload_invalid',
    }


def test_b90_c00395_assemble_words_persist_payload_invalid_validator():
    try:
        validate_worker_failure({'stage': 'assemble_words', 'reason': 'persist_payload_invalid'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00396_assemble_words_retained_audio_invalid_1_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'retained_audio_invalid'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00397_assemble_words_retained_audio_invalid_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00398_assemble_words_retained_audio_invalid_1_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'retained_audio_invalid'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00399_assemble_words_retained_audio_invalid_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00400_assemble_words_retained_audio_invalid_2_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'retained_audio_invalid'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00401_assemble_words_retained_audio_invalid_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00402_assemble_words_retained_audio_invalid_2_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'retained_audio_invalid'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00403_assemble_words_retained_audio_invalid_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00404_assemble_words_retained_audio_invalid_7_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'retained_audio_invalid'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00405_assemble_words_retained_audio_invalid_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00406_assemble_words_retained_audio_invalid_7_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'retained_audio_invalid'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00407_assemble_words_retained_audio_invalid_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00408_assemble_words_retained_audio_invalid_99_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'retained_audio_invalid'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00409_assemble_words_retained_audio_invalid_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00410_assemble_words_retained_audio_invalid_99_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'retained_audio_invalid'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00411_assemble_words_retained_audio_invalid_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00412_assemble_words_retained_audio_invalid_evidence():
    assert transient_failure_evidence('assemble_words', 'retained_audio_invalid') == {
        'stage': 'assemble_words',
        'reason': 'retained_audio_invalid',
    }


def test_b90_c00413_assemble_words_retained_audio_invalid_validator():
    try:
        validate_worker_failure({'stage': 'assemble_words', 'reason': 'retained_audio_invalid'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00414_assemble_words_staged_audio_invalid_1_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'staged_audio_invalid'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00415_assemble_words_staged_audio_invalid_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'staged_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00416_assemble_words_staged_audio_invalid_1_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'staged_audio_invalid'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00417_assemble_words_staged_audio_invalid_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00418_assemble_words_staged_audio_invalid_2_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'staged_audio_invalid'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00419_assemble_words_staged_audio_invalid_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'staged_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00420_assemble_words_staged_audio_invalid_2_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'staged_audio_invalid'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00421_assemble_words_staged_audio_invalid_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00422_assemble_words_staged_audio_invalid_7_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'staged_audio_invalid'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00423_assemble_words_staged_audio_invalid_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'staged_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00424_assemble_words_staged_audio_invalid_7_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'staged_audio_invalid'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00425_assemble_words_staged_audio_invalid_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00426_assemble_words_staged_audio_invalid_99_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'staged_audio_invalid'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00427_assemble_words_staged_audio_invalid_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'staged_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00428_assemble_words_staged_audio_invalid_99_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'staged_audio_invalid'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00429_assemble_words_staged_audio_invalid_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00430_assemble_words_staged_audio_invalid_evidence():
    assert transient_failure_evidence('assemble_words', 'staged_audio_invalid') == {
        'stage': 'assemble_words',
        'reason': 'staged_audio_invalid',
    }


def test_b90_c00431_assemble_words_staged_audio_invalid_validator():
    try:
        validate_worker_failure({'stage': 'assemble_words', 'reason': 'staged_audio_invalid'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00432_assemble_words_unknown_1_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'unknown'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00433_assemble_words_unknown_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'unknown'}, disposition_enabled=True)
        is False
    )


def test_b90_c00434_assemble_words_unknown_1_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'unknown'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00435_assemble_words_unknown_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'unknown'}, disposition_enabled=False)
        is False
    )


def test_b90_c00436_assemble_words_unknown_2_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'unknown'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00437_assemble_words_unknown_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'unknown'}, disposition_enabled=True)
        is False
    )


def test_b90_c00438_assemble_words_unknown_2_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'unknown'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00439_assemble_words_unknown_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'unknown'}, disposition_enabled=False)
        is False
    )


def test_b90_c00440_assemble_words_unknown_7_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'unknown'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00441_assemble_words_unknown_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'unknown'}, disposition_enabled=True)
        is False
    )


def test_b90_c00442_assemble_words_unknown_7_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'unknown'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00443_assemble_words_unknown_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'unknown'}, disposition_enabled=False)
        is False
    )


def test_b90_c00444_assemble_words_unknown_99_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'unknown'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00445_assemble_words_unknown_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'unknown'}, disposition_enabled=True)
        is False
    )


def test_b90_c00446_assemble_words_unknown_99_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'unknown'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00447_assemble_words_unknown_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'unknown'}, disposition_enabled=False)
        is False
    )


def test_b90_c00448_assemble_words_unknown_evidence():
    assert transient_failure_evidence('assemble_words', 'unknown') == {'stage': 'assemble_words', 'reason': 'unknown'}


def test_b90_c00449_assemble_words_unknown_validator():
    try:
        validate_worker_failure({'stage': 'assemble_words', 'reason': 'unknown'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is False


def test_b90_c00450_assemble_words_unsupported_language_1_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'unsupported_language'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00451_assemble_words_unsupported_language_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'unsupported_language'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00452_assemble_words_unsupported_language_1_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'unsupported_language'}, 1, 'false')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00453_assemble_words_unsupported_language_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00454_assemble_words_unsupported_language_2_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'unsupported_language'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00455_assemble_words_unsupported_language_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'unsupported_language'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00456_assemble_words_unsupported_language_2_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'unsupported_language'}, 2, 'false')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00457_assemble_words_unsupported_language_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00458_assemble_words_unsupported_language_7_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'unsupported_language'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00459_assemble_words_unsupported_language_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'unsupported_language'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00460_assemble_words_unsupported_language_7_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'unsupported_language'}, 7, 'false')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00461_assemble_words_unsupported_language_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00462_assemble_words_unsupported_language_99_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'unsupported_language'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00463_assemble_words_unsupported_language_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'unsupported_language'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00464_assemble_words_unsupported_language_99_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'unsupported_language'}, 99, 'false')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00465_assemble_words_unsupported_language_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00466_assemble_words_unsupported_language_evidence():
    assert transient_failure_evidence('assemble_words', 'unsupported_language') == {
        'stage': 'assemble_words',
        'reason': 'unsupported_language',
    }


def test_b90_c00467_assemble_words_unsupported_language_validator():
    try:
        validate_worker_failure({'stage': 'assemble_words', 'reason': 'unsupported_language'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00468_assemble_words_vad_bounds_1_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'vad_bounds'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00469_assemble_words_vad_bounds_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'vad_bounds'}, disposition_enabled=True)
        is True
    )


def test_b90_c00470_assemble_words_vad_bounds_1_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'vad_bounds'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00471_assemble_words_vad_bounds_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'vad_bounds'}, disposition_enabled=False)
        is False
    )


def test_b90_c00472_assemble_words_vad_bounds_2_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'vad_bounds'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00473_assemble_words_vad_bounds_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'vad_bounds'}, disposition_enabled=True)
        is True
    )


def test_b90_c00474_assemble_words_vad_bounds_2_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'vad_bounds'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00475_assemble_words_vad_bounds_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'vad_bounds'}, disposition_enabled=False)
        is False
    )


def test_b90_c00476_assemble_words_vad_bounds_7_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'vad_bounds'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00477_assemble_words_vad_bounds_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'vad_bounds'}, disposition_enabled=True)
        is True
    )


def test_b90_c00478_assemble_words_vad_bounds_7_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'vad_bounds'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00479_assemble_words_vad_bounds_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'vad_bounds'}, disposition_enabled=False)
        is False
    )


def test_b90_c00480_assemble_words_vad_bounds_99_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'vad_bounds'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00481_assemble_words_vad_bounds_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'vad_bounds'}, disposition_enabled=True)
        is True
    )


def test_b90_c00482_assemble_words_vad_bounds_99_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'vad_bounds'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00483_assemble_words_vad_bounds_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'vad_bounds'}, disposition_enabled=False)
        is False
    )


def test_b90_c00484_assemble_words_vad_bounds_evidence():
    assert transient_failure_evidence('assemble_words', 'vad_bounds') == {
        'stage': 'assemble_words',
        'reason': 'vad_bounds',
    }


def test_b90_c00485_assemble_words_vad_bounds_validator():
    try:
        validate_worker_failure({'stage': 'assemble_words', 'reason': 'vad_bounds'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00486_assemble_words_vad_nonfinite_1_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'vad_nonfinite'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00487_assemble_words_vad_nonfinite_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_b90_c00488_assemble_words_vad_nonfinite_1_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'vad_nonfinite'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00489_assemble_words_vad_nonfinite_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'vad_nonfinite'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00490_assemble_words_vad_nonfinite_2_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'vad_nonfinite'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00491_assemble_words_vad_nonfinite_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_b90_c00492_assemble_words_vad_nonfinite_2_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'vad_nonfinite'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00493_assemble_words_vad_nonfinite_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'vad_nonfinite'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00494_assemble_words_vad_nonfinite_7_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'vad_nonfinite'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00495_assemble_words_vad_nonfinite_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_b90_c00496_assemble_words_vad_nonfinite_7_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'vad_nonfinite'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00497_assemble_words_vad_nonfinite_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'vad_nonfinite'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00498_assemble_words_vad_nonfinite_99_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'vad_nonfinite'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00499_assemble_words_vad_nonfinite_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_b90_c00500_assemble_words_vad_nonfinite_99_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'vad_nonfinite'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00501_assemble_words_vad_nonfinite_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'vad_nonfinite'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00502_assemble_words_vad_nonfinite_evidence():
    assert transient_failure_evidence('assemble_words', 'vad_nonfinite') == {
        'stage': 'assemble_words',
        'reason': 'vad_nonfinite',
    }


def test_b90_c00503_assemble_words_vad_nonfinite_validator():
    try:
        validate_worker_failure({'stage': 'assemble_words', 'reason': 'vad_nonfinite'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00504_assemble_words_vad_order_1_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'vad_order'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00505_assemble_words_vad_order_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'vad_order'}, disposition_enabled=True)
        is True
    )


def test_b90_c00506_assemble_words_vad_order_1_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'vad_order'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00507_assemble_words_vad_order_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'vad_order'}, disposition_enabled=False)
        is False
    )


def test_b90_c00508_assemble_words_vad_order_2_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'vad_order'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00509_assemble_words_vad_order_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'vad_order'}, disposition_enabled=True)
        is True
    )


def test_b90_c00510_assemble_words_vad_order_2_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'vad_order'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00511_assemble_words_vad_order_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'vad_order'}, disposition_enabled=False)
        is False
    )


def test_b90_c00512_assemble_words_vad_order_7_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'vad_order'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00513_assemble_words_vad_order_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'vad_order'}, disposition_enabled=True)
        is True
    )


def test_b90_c00514_assemble_words_vad_order_7_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'vad_order'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00515_assemble_words_vad_order_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'vad_order'}, disposition_enabled=False)
        is False
    )


def test_b90_c00516_assemble_words_vad_order_99_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'vad_order'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00517_assemble_words_vad_order_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'vad_order'}, disposition_enabled=True)
        is True
    )


def test_b90_c00518_assemble_words_vad_order_99_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'vad_order'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00519_assemble_words_vad_order_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'vad_order'}, disposition_enabled=False)
        is False
    )


def test_b90_c00520_assemble_words_vad_order_evidence():
    assert transient_failure_evidence('assemble_words', 'vad_order') == {
        'stage': 'assemble_words',
        'reason': 'vad_order',
    }


def test_b90_c00521_assemble_words_vad_order_validator():
    try:
        validate_worker_failure({'stage': 'assemble_words', 'reason': 'vad_order'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00522_assemble_words_word_clock_1_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'word_clock'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00523_assemble_words_word_clock_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'word_clock'}, disposition_enabled=True)
        is True
    )


def test_b90_c00524_assemble_words_word_clock_1_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'word_clock'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00525_assemble_words_word_clock_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'word_clock'}, disposition_enabled=False)
        is False
    )


def test_b90_c00526_assemble_words_word_clock_2_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'word_clock'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00527_assemble_words_word_clock_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'word_clock'}, disposition_enabled=True)
        is True
    )


def test_b90_c00528_assemble_words_word_clock_2_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'word_clock'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00529_assemble_words_word_clock_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'word_clock'}, disposition_enabled=False)
        is False
    )


def test_b90_c00530_assemble_words_word_clock_7_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'word_clock'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00531_assemble_words_word_clock_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'word_clock'}, disposition_enabled=True)
        is True
    )


def test_b90_c00532_assemble_words_word_clock_7_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'word_clock'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00533_assemble_words_word_clock_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'word_clock'}, disposition_enabled=False)
        is False
    )


def test_b90_c00534_assemble_words_word_clock_99_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'word_clock'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00535_assemble_words_word_clock_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'word_clock'}, disposition_enabled=True)
        is True
    )


def test_b90_c00536_assemble_words_word_clock_99_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'word_clock'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00537_assemble_words_word_clock_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'word_clock'}, disposition_enabled=False)
        is False
    )


def test_b90_c00538_assemble_words_word_clock_evidence():
    assert transient_failure_evidence('assemble_words', 'word_clock') == {
        'stage': 'assemble_words',
        'reason': 'word_clock',
    }


def test_b90_c00539_assemble_words_word_clock_validator():
    try:
        validate_worker_failure({'stage': 'assemble_words', 'reason': 'word_clock'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00540_assemble_words_word_sequence_1_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'word_sequence'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00541_assemble_words_word_sequence_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_b90_c00542_assemble_words_word_sequence_1_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'word_sequence'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00543_assemble_words_word_sequence_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'word_sequence'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00544_assemble_words_word_sequence_2_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'word_sequence'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00545_assemble_words_word_sequence_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_b90_c00546_assemble_words_word_sequence_2_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'word_sequence'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00547_assemble_words_word_sequence_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'word_sequence'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00548_assemble_words_word_sequence_7_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'word_sequence'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00549_assemble_words_word_sequence_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_b90_c00550_assemble_words_word_sequence_7_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'word_sequence'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00551_assemble_words_word_sequence_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'word_sequence'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00552_assemble_words_word_sequence_99_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'word_sequence'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00553_assemble_words_word_sequence_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_b90_c00554_assemble_words_word_sequence_99_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'word_sequence'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00555_assemble_words_word_sequence_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'word_sequence'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00556_assemble_words_word_sequence_evidence():
    assert transient_failure_evidence('assemble_words', 'word_sequence') == {
        'stage': 'assemble_words',
        'reason': 'word_sequence',
    }


def test_b90_c00557_assemble_words_word_sequence_validator():
    try:
        validate_worker_failure({'stage': 'assemble_words', 'reason': 'word_sequence'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00558_assemble_words_word_shape_1_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'word_shape'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00559_assemble_words_word_shape_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'word_shape'}, disposition_enabled=True)
        is True
    )


def test_b90_c00560_assemble_words_word_shape_1_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'word_shape'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00561_assemble_words_word_shape_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'word_shape'}, disposition_enabled=False)
        is False
    )


def test_b90_c00562_assemble_words_word_shape_2_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'word_shape'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00563_assemble_words_word_shape_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'word_shape'}, disposition_enabled=True)
        is True
    )


def test_b90_c00564_assemble_words_word_shape_2_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'word_shape'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00565_assemble_words_word_shape_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'word_shape'}, disposition_enabled=False)
        is False
    )


def test_b90_c00566_assemble_words_word_shape_7_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'word_shape'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00567_assemble_words_word_shape_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'word_shape'}, disposition_enabled=True)
        is True
    )


def test_b90_c00568_assemble_words_word_shape_7_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'word_shape'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00569_assemble_words_word_shape_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'word_shape'}, disposition_enabled=False)
        is False
    )


def test_b90_c00570_assemble_words_word_shape_99_true():
    lines = _drive({'stage': 'assemble_words', 'reason': 'word_shape'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00571_assemble_words_word_shape_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'word_shape'}, disposition_enabled=True)
        is True
    )


def test_b90_c00572_assemble_words_word_shape_99_false():
    lines = _drive({'stage': 'assemble_words', 'reason': 'word_shape'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00573_assemble_words_word_shape_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'word_shape'}, disposition_enabled=False)
        is False
    )


def test_b90_c00574_assemble_words_word_shape_evidence():
    assert transient_failure_evidence('assemble_words', 'word_shape') == {
        'stage': 'assemble_words',
        'reason': 'word_shape',
    }


def test_b90_c00575_assemble_words_word_shape_validator():
    try:
        validate_worker_failure({'stage': 'assemble_words', 'reason': 'word_shape'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00576_fetch_decode_decode_payload_invalid_1_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'decode_payload_invalid'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00577_fetch_decode_decode_payload_invalid_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'decode_payload_invalid'}, disposition_enabled=True
        )
        is True
    )


def test_b90_c00578_fetch_decode_decode_payload_invalid_1_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'decode_payload_invalid'}, 1, 'false')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00579_fetch_decode_decode_payload_invalid_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'decode_payload_invalid'}, disposition_enabled=False
        )
        is True
    )


def test_b90_c00580_fetch_decode_decode_payload_invalid_2_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'decode_payload_invalid'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00581_fetch_decode_decode_payload_invalid_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'decode_payload_invalid'}, disposition_enabled=True
        )
        is True
    )


def test_b90_c00582_fetch_decode_decode_payload_invalid_2_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'decode_payload_invalid'}, 2, 'false')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00583_fetch_decode_decode_payload_invalid_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'decode_payload_invalid'}, disposition_enabled=False
        )
        is True
    )


def test_b90_c00584_fetch_decode_decode_payload_invalid_7_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'decode_payload_invalid'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00585_fetch_decode_decode_payload_invalid_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'decode_payload_invalid'}, disposition_enabled=True
        )
        is True
    )


def test_b90_c00586_fetch_decode_decode_payload_invalid_7_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'decode_payload_invalid'}, 7, 'false')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00587_fetch_decode_decode_payload_invalid_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'decode_payload_invalid'}, disposition_enabled=False
        )
        is True
    )


def test_b90_c00588_fetch_decode_decode_payload_invalid_99_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'decode_payload_invalid'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00589_fetch_decode_decode_payload_invalid_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'decode_payload_invalid'}, disposition_enabled=True
        )
        is True
    )


def test_b90_c00590_fetch_decode_decode_payload_invalid_99_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'decode_payload_invalid'}, 99, 'false')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00591_fetch_decode_decode_payload_invalid_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'decode_payload_invalid'}, disposition_enabled=False
        )
        is True
    )


def test_b90_c00592_fetch_decode_decode_payload_invalid_evidence():
    assert transient_failure_evidence('fetch_decode', 'decode_payload_invalid') == {
        'stage': 'fetch_decode',
        'reason': 'decode_payload_invalid',
    }


def test_b90_c00593_fetch_decode_decode_payload_invalid_validator():
    try:
        validate_worker_failure({'stage': 'fetch_decode', 'reason': 'decode_payload_invalid'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00594_fetch_decode_decoded_duration_mismatch_1_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00595_fetch_decode_decoded_duration_mismatch_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is True
    )


def test_b90_c00596_fetch_decode_decoded_duration_mismatch_1_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}, 1, 'false')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00597_fetch_decode_decoded_duration_mismatch_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is True
    )


def test_b90_c00598_fetch_decode_decoded_duration_mismatch_2_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00599_fetch_decode_decoded_duration_mismatch_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is True
    )


def test_b90_c00600_fetch_decode_decoded_duration_mismatch_2_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}, 2, 'false')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00601_fetch_decode_decoded_duration_mismatch_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is True
    )


def test_b90_c00602_fetch_decode_decoded_duration_mismatch_7_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00603_fetch_decode_decoded_duration_mismatch_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is True
    )


def test_b90_c00604_fetch_decode_decoded_duration_mismatch_7_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}, 7, 'false')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00605_fetch_decode_decoded_duration_mismatch_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is True
    )


def test_b90_c00606_fetch_decode_decoded_duration_mismatch_99_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00607_fetch_decode_decoded_duration_mismatch_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is True
    )


def test_b90_c00608_fetch_decode_decoded_duration_mismatch_99_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}, 99, 'false')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00609_fetch_decode_decoded_duration_mismatch_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is True
    )


def test_b90_c00610_fetch_decode_decoded_duration_mismatch_evidence():
    assert transient_failure_evidence('fetch_decode', 'decoded_duration_mismatch') == {
        'stage': 'fetch_decode',
        'reason': 'decoded_duration_mismatch',
    }


def test_b90_c00611_fetch_decode_decoded_duration_mismatch_validator():
    try:
        validate_worker_failure({'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00612_fetch_decode_empty_asr_1_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'empty_asr'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00613_fetch_decode_empty_asr_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'empty_asr'}, disposition_enabled=True)
        is False
    )


def test_b90_c00614_fetch_decode_empty_asr_1_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'empty_asr'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00615_fetch_decode_empty_asr_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'empty_asr'}, disposition_enabled=False)
        is False
    )


def test_b90_c00616_fetch_decode_empty_asr_2_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'empty_asr'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00617_fetch_decode_empty_asr_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'empty_asr'}, disposition_enabled=True)
        is False
    )


def test_b90_c00618_fetch_decode_empty_asr_2_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'empty_asr'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00619_fetch_decode_empty_asr_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'empty_asr'}, disposition_enabled=False)
        is False
    )


def test_b90_c00620_fetch_decode_empty_asr_7_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'empty_asr'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00621_fetch_decode_empty_asr_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'empty_asr'}, disposition_enabled=True)
        is False
    )


def test_b90_c00622_fetch_decode_empty_asr_7_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'empty_asr'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00623_fetch_decode_empty_asr_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'empty_asr'}, disposition_enabled=False)
        is False
    )


def test_b90_c00624_fetch_decode_empty_asr_99_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'empty_asr'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00625_fetch_decode_empty_asr_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'empty_asr'}, disposition_enabled=True)
        is False
    )


def test_b90_c00626_fetch_decode_empty_asr_99_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'empty_asr'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00627_fetch_decode_empty_asr_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'empty_asr'}, disposition_enabled=False)
        is False
    )


def test_b90_c00628_fetch_decode_empty_asr_evidence():
    assert transient_failure_evidence('fetch_decode', 'empty_asr') == {'stage': 'fetch_decode', 'reason': 'empty_asr'}


def test_b90_c00629_fetch_decode_empty_asr_validator():
    try:
        validate_worker_failure({'stage': 'fetch_decode', 'reason': 'empty_asr'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00630_fetch_decode_no_owned_words_1_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'no_owned_words'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00631_fetch_decode_no_owned_words_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'no_owned_words'}, disposition_enabled=True)
        is False
    )


def test_b90_c00632_fetch_decode_no_owned_words_1_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'no_owned_words'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00633_fetch_decode_no_owned_words_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'no_owned_words'}, disposition_enabled=False)
        is False
    )


def test_b90_c00634_fetch_decode_no_owned_words_2_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'no_owned_words'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00635_fetch_decode_no_owned_words_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'no_owned_words'}, disposition_enabled=True)
        is False
    )


def test_b90_c00636_fetch_decode_no_owned_words_2_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'no_owned_words'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00637_fetch_decode_no_owned_words_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'no_owned_words'}, disposition_enabled=False)
        is False
    )


def test_b90_c00638_fetch_decode_no_owned_words_7_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'no_owned_words'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00639_fetch_decode_no_owned_words_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'no_owned_words'}, disposition_enabled=True)
        is False
    )


def test_b90_c00640_fetch_decode_no_owned_words_7_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'no_owned_words'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00641_fetch_decode_no_owned_words_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'no_owned_words'}, disposition_enabled=False)
        is False
    )


def test_b90_c00642_fetch_decode_no_owned_words_99_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'no_owned_words'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00643_fetch_decode_no_owned_words_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'no_owned_words'}, disposition_enabled=True)
        is False
    )


def test_b90_c00644_fetch_decode_no_owned_words_99_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'no_owned_words'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00645_fetch_decode_no_owned_words_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'no_owned_words'}, disposition_enabled=False)
        is False
    )


def test_b90_c00646_fetch_decode_no_owned_words_evidence():
    assert transient_failure_evidence('fetch_decode', 'no_owned_words') == {
        'stage': 'fetch_decode',
        'reason': 'no_owned_words',
    }


def test_b90_c00647_fetch_decode_no_owned_words_validator():
    try:
        validate_worker_failure({'stage': 'fetch_decode', 'reason': 'no_owned_words'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00648_fetch_decode_outside_admitted_source_1_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00649_fetch_decode_outside_admitted_source_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00650_fetch_decode_outside_admitted_source_1_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00651_fetch_decode_outside_admitted_source_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00652_fetch_decode_outside_admitted_source_2_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00653_fetch_decode_outside_admitted_source_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00654_fetch_decode_outside_admitted_source_2_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00655_fetch_decode_outside_admitted_source_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00656_fetch_decode_outside_admitted_source_7_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00657_fetch_decode_outside_admitted_source_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00658_fetch_decode_outside_admitted_source_7_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00659_fetch_decode_outside_admitted_source_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00660_fetch_decode_outside_admitted_source_99_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00661_fetch_decode_outside_admitted_source_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00662_fetch_decode_outside_admitted_source_99_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00663_fetch_decode_outside_admitted_source_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00664_fetch_decode_outside_admitted_source_evidence():
    assert transient_failure_evidence('fetch_decode', 'outside_admitted_source') == {
        'stage': 'fetch_decode',
        'reason': 'outside_admitted_source',
    }


def test_b90_c00665_fetch_decode_outside_admitted_source_validator():
    try:
        validate_worker_failure({'stage': 'fetch_decode', 'reason': 'outside_admitted_source'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00666_fetch_decode_persist_payload_invalid_1_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'persist_payload_invalid'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00667_fetch_decode_persist_payload_invalid_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'persist_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00668_fetch_decode_persist_payload_invalid_1_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'persist_payload_invalid'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00669_fetch_decode_persist_payload_invalid_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'persist_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00670_fetch_decode_persist_payload_invalid_2_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'persist_payload_invalid'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00671_fetch_decode_persist_payload_invalid_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'persist_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00672_fetch_decode_persist_payload_invalid_2_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'persist_payload_invalid'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00673_fetch_decode_persist_payload_invalid_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'persist_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00674_fetch_decode_persist_payload_invalid_7_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'persist_payload_invalid'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00675_fetch_decode_persist_payload_invalid_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'persist_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00676_fetch_decode_persist_payload_invalid_7_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'persist_payload_invalid'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00677_fetch_decode_persist_payload_invalid_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'persist_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00678_fetch_decode_persist_payload_invalid_99_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'persist_payload_invalid'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00679_fetch_decode_persist_payload_invalid_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'persist_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00680_fetch_decode_persist_payload_invalid_99_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'persist_payload_invalid'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00681_fetch_decode_persist_payload_invalid_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'persist_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00682_fetch_decode_persist_payload_invalid_evidence():
    assert transient_failure_evidence('fetch_decode', 'persist_payload_invalid') == {
        'stage': 'fetch_decode',
        'reason': 'persist_payload_invalid',
    }


def test_b90_c00683_fetch_decode_persist_payload_invalid_validator():
    try:
        validate_worker_failure({'stage': 'fetch_decode', 'reason': 'persist_payload_invalid'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00684_fetch_decode_retained_audio_invalid_1_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00685_fetch_decode_retained_audio_invalid_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is True
    )


def test_b90_c00686_fetch_decode_retained_audio_invalid_1_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}, 1, 'false')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00687_fetch_decode_retained_audio_invalid_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is True
    )


def test_b90_c00688_fetch_decode_retained_audio_invalid_2_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00689_fetch_decode_retained_audio_invalid_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is True
    )


def test_b90_c00690_fetch_decode_retained_audio_invalid_2_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}, 2, 'false')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00691_fetch_decode_retained_audio_invalid_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is True
    )


def test_b90_c00692_fetch_decode_retained_audio_invalid_7_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00693_fetch_decode_retained_audio_invalid_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is True
    )


def test_b90_c00694_fetch_decode_retained_audio_invalid_7_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}, 7, 'false')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00695_fetch_decode_retained_audio_invalid_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is True
    )


def test_b90_c00696_fetch_decode_retained_audio_invalid_99_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00697_fetch_decode_retained_audio_invalid_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is True
    )


def test_b90_c00698_fetch_decode_retained_audio_invalid_99_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}, 99, 'false')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00699_fetch_decode_retained_audio_invalid_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is True
    )


def test_b90_c00700_fetch_decode_retained_audio_invalid_evidence():
    assert transient_failure_evidence('fetch_decode', 'retained_audio_invalid') == {
        'stage': 'fetch_decode',
        'reason': 'retained_audio_invalid',
    }


def test_b90_c00701_fetch_decode_retained_audio_invalid_validator():
    try:
        validate_worker_failure({'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00702_fetch_decode_staged_audio_invalid_1_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00703_fetch_decode_staged_audio_invalid_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}, disposition_enabled=True
        )
        is True
    )


def test_b90_c00704_fetch_decode_staged_audio_invalid_1_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}, 1, 'false')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00705_fetch_decode_staged_audio_invalid_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is True
    )


def test_b90_c00706_fetch_decode_staged_audio_invalid_2_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00707_fetch_decode_staged_audio_invalid_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}, disposition_enabled=True
        )
        is True
    )


def test_b90_c00708_fetch_decode_staged_audio_invalid_2_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}, 2, 'false')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00709_fetch_decode_staged_audio_invalid_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is True
    )


def test_b90_c00710_fetch_decode_staged_audio_invalid_7_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00711_fetch_decode_staged_audio_invalid_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}, disposition_enabled=True
        )
        is True
    )


def test_b90_c00712_fetch_decode_staged_audio_invalid_7_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}, 7, 'false')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00713_fetch_decode_staged_audio_invalid_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is True
    )


def test_b90_c00714_fetch_decode_staged_audio_invalid_99_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00715_fetch_decode_staged_audio_invalid_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}, disposition_enabled=True
        )
        is True
    )


def test_b90_c00716_fetch_decode_staged_audio_invalid_99_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}, 99, 'false')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00717_fetch_decode_staged_audio_invalid_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is True
    )


def test_b90_c00718_fetch_decode_staged_audio_invalid_evidence():
    assert transient_failure_evidence('fetch_decode', 'staged_audio_invalid') == {
        'stage': 'fetch_decode',
        'reason': 'staged_audio_invalid',
    }


def test_b90_c00719_fetch_decode_staged_audio_invalid_validator():
    try:
        validate_worker_failure({'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00720_fetch_decode_unknown_1_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'unknown'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00721_fetch_decode_unknown_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'unknown'}, disposition_enabled=True)
        is False
    )


def test_b90_c00722_fetch_decode_unknown_1_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'unknown'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00723_fetch_decode_unknown_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'unknown'}, disposition_enabled=False)
        is False
    )


def test_b90_c00724_fetch_decode_unknown_2_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'unknown'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00725_fetch_decode_unknown_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'unknown'}, disposition_enabled=True)
        is False
    )


def test_b90_c00726_fetch_decode_unknown_2_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'unknown'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00727_fetch_decode_unknown_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'unknown'}, disposition_enabled=False)
        is False
    )


def test_b90_c00728_fetch_decode_unknown_7_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'unknown'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00729_fetch_decode_unknown_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'unknown'}, disposition_enabled=True)
        is False
    )


def test_b90_c00730_fetch_decode_unknown_7_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'unknown'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00731_fetch_decode_unknown_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'unknown'}, disposition_enabled=False)
        is False
    )


def test_b90_c00732_fetch_decode_unknown_99_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'unknown'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00733_fetch_decode_unknown_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'unknown'}, disposition_enabled=True)
        is False
    )


def test_b90_c00734_fetch_decode_unknown_99_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'unknown'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00735_fetch_decode_unknown_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'unknown'}, disposition_enabled=False)
        is False
    )


def test_b90_c00736_fetch_decode_unknown_evidence():
    assert transient_failure_evidence('fetch_decode', 'unknown') == {'stage': 'fetch_decode', 'reason': 'unknown'}


def test_b90_c00737_fetch_decode_unknown_validator():
    try:
        validate_worker_failure({'stage': 'fetch_decode', 'reason': 'unknown'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is False


def test_b90_c00738_fetch_decode_unsupported_language_1_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'unsupported_language'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00739_fetch_decode_unsupported_language_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'unsupported_language'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00740_fetch_decode_unsupported_language_1_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'unsupported_language'}, 1, 'false')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00741_fetch_decode_unsupported_language_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00742_fetch_decode_unsupported_language_2_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'unsupported_language'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00743_fetch_decode_unsupported_language_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'unsupported_language'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00744_fetch_decode_unsupported_language_2_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'unsupported_language'}, 2, 'false')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00745_fetch_decode_unsupported_language_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00746_fetch_decode_unsupported_language_7_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'unsupported_language'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00747_fetch_decode_unsupported_language_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'unsupported_language'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00748_fetch_decode_unsupported_language_7_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'unsupported_language'}, 7, 'false')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00749_fetch_decode_unsupported_language_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00750_fetch_decode_unsupported_language_99_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'unsupported_language'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00751_fetch_decode_unsupported_language_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'unsupported_language'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00752_fetch_decode_unsupported_language_99_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'unsupported_language'}, 99, 'false')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00753_fetch_decode_unsupported_language_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00754_fetch_decode_unsupported_language_evidence():
    assert transient_failure_evidence('fetch_decode', 'unsupported_language') == {
        'stage': 'fetch_decode',
        'reason': 'unsupported_language',
    }


def test_b90_c00755_fetch_decode_unsupported_language_validator():
    try:
        validate_worker_failure({'stage': 'fetch_decode', 'reason': 'unsupported_language'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00756_fetch_decode_vad_bounds_1_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'vad_bounds'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00757_fetch_decode_vad_bounds_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_bounds'}, disposition_enabled=True)
        is True
    )


def test_b90_c00758_fetch_decode_vad_bounds_1_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'vad_bounds'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00759_fetch_decode_vad_bounds_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_bounds'}, disposition_enabled=False)
        is False
    )


def test_b90_c00760_fetch_decode_vad_bounds_2_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'vad_bounds'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00761_fetch_decode_vad_bounds_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_bounds'}, disposition_enabled=True)
        is True
    )


def test_b90_c00762_fetch_decode_vad_bounds_2_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'vad_bounds'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00763_fetch_decode_vad_bounds_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_bounds'}, disposition_enabled=False)
        is False
    )


def test_b90_c00764_fetch_decode_vad_bounds_7_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'vad_bounds'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00765_fetch_decode_vad_bounds_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_bounds'}, disposition_enabled=True)
        is True
    )


def test_b90_c00766_fetch_decode_vad_bounds_7_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'vad_bounds'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00767_fetch_decode_vad_bounds_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_bounds'}, disposition_enabled=False)
        is False
    )


def test_b90_c00768_fetch_decode_vad_bounds_99_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'vad_bounds'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00769_fetch_decode_vad_bounds_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_bounds'}, disposition_enabled=True)
        is True
    )


def test_b90_c00770_fetch_decode_vad_bounds_99_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'vad_bounds'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00771_fetch_decode_vad_bounds_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_bounds'}, disposition_enabled=False)
        is False
    )


def test_b90_c00772_fetch_decode_vad_bounds_evidence():
    assert transient_failure_evidence('fetch_decode', 'vad_bounds') == {'stage': 'fetch_decode', 'reason': 'vad_bounds'}


def test_b90_c00773_fetch_decode_vad_bounds_validator():
    try:
        validate_worker_failure({'stage': 'fetch_decode', 'reason': 'vad_bounds'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00774_fetch_decode_vad_nonfinite_1_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'vad_nonfinite'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00775_fetch_decode_vad_nonfinite_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_b90_c00776_fetch_decode_vad_nonfinite_1_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'vad_nonfinite'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00777_fetch_decode_vad_nonfinite_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_nonfinite'}, disposition_enabled=False)
        is False
    )


def test_b90_c00778_fetch_decode_vad_nonfinite_2_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'vad_nonfinite'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00779_fetch_decode_vad_nonfinite_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_b90_c00780_fetch_decode_vad_nonfinite_2_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'vad_nonfinite'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00781_fetch_decode_vad_nonfinite_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_nonfinite'}, disposition_enabled=False)
        is False
    )


def test_b90_c00782_fetch_decode_vad_nonfinite_7_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'vad_nonfinite'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00783_fetch_decode_vad_nonfinite_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_b90_c00784_fetch_decode_vad_nonfinite_7_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'vad_nonfinite'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00785_fetch_decode_vad_nonfinite_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_nonfinite'}, disposition_enabled=False)
        is False
    )


def test_b90_c00786_fetch_decode_vad_nonfinite_99_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'vad_nonfinite'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00787_fetch_decode_vad_nonfinite_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_b90_c00788_fetch_decode_vad_nonfinite_99_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'vad_nonfinite'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00789_fetch_decode_vad_nonfinite_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_nonfinite'}, disposition_enabled=False)
        is False
    )


def test_b90_c00790_fetch_decode_vad_nonfinite_evidence():
    assert transient_failure_evidence('fetch_decode', 'vad_nonfinite') == {
        'stage': 'fetch_decode',
        'reason': 'vad_nonfinite',
    }


def test_b90_c00791_fetch_decode_vad_nonfinite_validator():
    try:
        validate_worker_failure({'stage': 'fetch_decode', 'reason': 'vad_nonfinite'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00792_fetch_decode_vad_order_1_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'vad_order'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00793_fetch_decode_vad_order_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_order'}, disposition_enabled=True)
        is True
    )


def test_b90_c00794_fetch_decode_vad_order_1_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'vad_order'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00795_fetch_decode_vad_order_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_order'}, disposition_enabled=False)
        is False
    )


def test_b90_c00796_fetch_decode_vad_order_2_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'vad_order'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00797_fetch_decode_vad_order_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_order'}, disposition_enabled=True)
        is True
    )


def test_b90_c00798_fetch_decode_vad_order_2_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'vad_order'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00799_fetch_decode_vad_order_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_order'}, disposition_enabled=False)
        is False
    )


def test_b90_c00800_fetch_decode_vad_order_7_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'vad_order'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00801_fetch_decode_vad_order_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_order'}, disposition_enabled=True)
        is True
    )


def test_b90_c00802_fetch_decode_vad_order_7_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'vad_order'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00803_fetch_decode_vad_order_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_order'}, disposition_enabled=False)
        is False
    )


def test_b90_c00804_fetch_decode_vad_order_99_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'vad_order'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00805_fetch_decode_vad_order_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_order'}, disposition_enabled=True)
        is True
    )


def test_b90_c00806_fetch_decode_vad_order_99_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'vad_order'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00807_fetch_decode_vad_order_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_order'}, disposition_enabled=False)
        is False
    )


def test_b90_c00808_fetch_decode_vad_order_evidence():
    assert transient_failure_evidence('fetch_decode', 'vad_order') == {'stage': 'fetch_decode', 'reason': 'vad_order'}


def test_b90_c00809_fetch_decode_vad_order_validator():
    try:
        validate_worker_failure({'stage': 'fetch_decode', 'reason': 'vad_order'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00810_fetch_decode_word_clock_1_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'word_clock'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00811_fetch_decode_word_clock_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_clock'}, disposition_enabled=True)
        is True
    )


def test_b90_c00812_fetch_decode_word_clock_1_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'word_clock'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00813_fetch_decode_word_clock_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_clock'}, disposition_enabled=False)
        is False
    )


def test_b90_c00814_fetch_decode_word_clock_2_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'word_clock'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00815_fetch_decode_word_clock_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_clock'}, disposition_enabled=True)
        is True
    )


def test_b90_c00816_fetch_decode_word_clock_2_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'word_clock'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00817_fetch_decode_word_clock_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_clock'}, disposition_enabled=False)
        is False
    )


def test_b90_c00818_fetch_decode_word_clock_7_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'word_clock'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00819_fetch_decode_word_clock_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_clock'}, disposition_enabled=True)
        is True
    )


def test_b90_c00820_fetch_decode_word_clock_7_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'word_clock'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00821_fetch_decode_word_clock_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_clock'}, disposition_enabled=False)
        is False
    )


def test_b90_c00822_fetch_decode_word_clock_99_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'word_clock'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00823_fetch_decode_word_clock_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_clock'}, disposition_enabled=True)
        is True
    )


def test_b90_c00824_fetch_decode_word_clock_99_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'word_clock'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00825_fetch_decode_word_clock_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_clock'}, disposition_enabled=False)
        is False
    )


def test_b90_c00826_fetch_decode_word_clock_evidence():
    assert transient_failure_evidence('fetch_decode', 'word_clock') == {'stage': 'fetch_decode', 'reason': 'word_clock'}


def test_b90_c00827_fetch_decode_word_clock_validator():
    try:
        validate_worker_failure({'stage': 'fetch_decode', 'reason': 'word_clock'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00828_fetch_decode_word_sequence_1_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'word_sequence'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00829_fetch_decode_word_sequence_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_b90_c00830_fetch_decode_word_sequence_1_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'word_sequence'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00831_fetch_decode_word_sequence_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_sequence'}, disposition_enabled=False)
        is False
    )


def test_b90_c00832_fetch_decode_word_sequence_2_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'word_sequence'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00833_fetch_decode_word_sequence_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_b90_c00834_fetch_decode_word_sequence_2_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'word_sequence'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00835_fetch_decode_word_sequence_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_sequence'}, disposition_enabled=False)
        is False
    )


def test_b90_c00836_fetch_decode_word_sequence_7_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'word_sequence'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00837_fetch_decode_word_sequence_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_b90_c00838_fetch_decode_word_sequence_7_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'word_sequence'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00839_fetch_decode_word_sequence_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_sequence'}, disposition_enabled=False)
        is False
    )


def test_b90_c00840_fetch_decode_word_sequence_99_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'word_sequence'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00841_fetch_decode_word_sequence_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_b90_c00842_fetch_decode_word_sequence_99_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'word_sequence'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00843_fetch_decode_word_sequence_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_sequence'}, disposition_enabled=False)
        is False
    )


def test_b90_c00844_fetch_decode_word_sequence_evidence():
    assert transient_failure_evidence('fetch_decode', 'word_sequence') == {
        'stage': 'fetch_decode',
        'reason': 'word_sequence',
    }


def test_b90_c00845_fetch_decode_word_sequence_validator():
    try:
        validate_worker_failure({'stage': 'fetch_decode', 'reason': 'word_sequence'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00846_fetch_decode_word_shape_1_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'word_shape'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00847_fetch_decode_word_shape_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_shape'}, disposition_enabled=True)
        is True
    )


def test_b90_c00848_fetch_decode_word_shape_1_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'word_shape'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00849_fetch_decode_word_shape_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_shape'}, disposition_enabled=False)
        is False
    )


def test_b90_c00850_fetch_decode_word_shape_2_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'word_shape'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00851_fetch_decode_word_shape_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_shape'}, disposition_enabled=True)
        is True
    )


def test_b90_c00852_fetch_decode_word_shape_2_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'word_shape'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00853_fetch_decode_word_shape_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_shape'}, disposition_enabled=False)
        is False
    )


def test_b90_c00854_fetch_decode_word_shape_7_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'word_shape'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00855_fetch_decode_word_shape_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_shape'}, disposition_enabled=True)
        is True
    )


def test_b90_c00856_fetch_decode_word_shape_7_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'word_shape'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00857_fetch_decode_word_shape_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_shape'}, disposition_enabled=False)
        is False
    )


def test_b90_c00858_fetch_decode_word_shape_99_true():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'word_shape'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00859_fetch_decode_word_shape_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_shape'}, disposition_enabled=True)
        is True
    )


def test_b90_c00860_fetch_decode_word_shape_99_false():
    lines = _drive({'stage': 'fetch_decode', 'reason': 'word_shape'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00861_fetch_decode_word_shape_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_shape'}, disposition_enabled=False)
        is False
    )


def test_b90_c00862_fetch_decode_word_shape_evidence():
    assert transient_failure_evidence('fetch_decode', 'word_shape') == {'stage': 'fetch_decode', 'reason': 'word_shape'}


def test_b90_c00863_fetch_decode_word_shape_validator():
    try:
        validate_worker_failure({'stage': 'fetch_decode', 'reason': 'word_shape'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00864_persist_decode_payload_invalid_1_true():
    lines = _drive({'stage': 'persist', 'reason': 'decode_payload_invalid'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00865_persist_decode_payload_invalid_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'decode_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00866_persist_decode_payload_invalid_1_false():
    lines = _drive({'stage': 'persist', 'reason': 'decode_payload_invalid'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00867_persist_decode_payload_invalid_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'decode_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00868_persist_decode_payload_invalid_2_true():
    lines = _drive({'stage': 'persist', 'reason': 'decode_payload_invalid'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00869_persist_decode_payload_invalid_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'decode_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00870_persist_decode_payload_invalid_2_false():
    lines = _drive({'stage': 'persist', 'reason': 'decode_payload_invalid'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00871_persist_decode_payload_invalid_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'decode_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00872_persist_decode_payload_invalid_7_true():
    lines = _drive({'stage': 'persist', 'reason': 'decode_payload_invalid'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00873_persist_decode_payload_invalid_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'decode_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00874_persist_decode_payload_invalid_7_false():
    lines = _drive({'stage': 'persist', 'reason': 'decode_payload_invalid'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00875_persist_decode_payload_invalid_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'decode_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00876_persist_decode_payload_invalid_99_true():
    lines = _drive({'stage': 'persist', 'reason': 'decode_payload_invalid'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00877_persist_decode_payload_invalid_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'decode_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00878_persist_decode_payload_invalid_99_false():
    lines = _drive({'stage': 'persist', 'reason': 'decode_payload_invalid'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00879_persist_decode_payload_invalid_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'decode_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00880_persist_decode_payload_invalid_evidence():
    assert transient_failure_evidence('persist', 'decode_payload_invalid') == {
        'stage': 'persist',
        'reason': 'decode_payload_invalid',
    }


def test_b90_c00881_persist_decode_payload_invalid_validator():
    try:
        validate_worker_failure({'stage': 'persist', 'reason': 'decode_payload_invalid'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00882_persist_decoded_duration_mismatch_1_true():
    lines = _drive({'stage': 'persist', 'reason': 'decoded_duration_mismatch'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00883_persist_decoded_duration_mismatch_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00884_persist_decoded_duration_mismatch_1_false():
    lines = _drive({'stage': 'persist', 'reason': 'decoded_duration_mismatch'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00885_persist_decoded_duration_mismatch_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00886_persist_decoded_duration_mismatch_2_true():
    lines = _drive({'stage': 'persist', 'reason': 'decoded_duration_mismatch'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00887_persist_decoded_duration_mismatch_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00888_persist_decoded_duration_mismatch_2_false():
    lines = _drive({'stage': 'persist', 'reason': 'decoded_duration_mismatch'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00889_persist_decoded_duration_mismatch_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00890_persist_decoded_duration_mismatch_7_true():
    lines = _drive({'stage': 'persist', 'reason': 'decoded_duration_mismatch'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00891_persist_decoded_duration_mismatch_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00892_persist_decoded_duration_mismatch_7_false():
    lines = _drive({'stage': 'persist', 'reason': 'decoded_duration_mismatch'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00893_persist_decoded_duration_mismatch_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00894_persist_decoded_duration_mismatch_99_true():
    lines = _drive({'stage': 'persist', 'reason': 'decoded_duration_mismatch'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00895_persist_decoded_duration_mismatch_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00896_persist_decoded_duration_mismatch_99_false():
    lines = _drive({'stage': 'persist', 'reason': 'decoded_duration_mismatch'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00897_persist_decoded_duration_mismatch_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00898_persist_decoded_duration_mismatch_evidence():
    assert transient_failure_evidence('persist', 'decoded_duration_mismatch') == {
        'stage': 'persist',
        'reason': 'decoded_duration_mismatch',
    }


def test_b90_c00899_persist_decoded_duration_mismatch_validator():
    try:
        validate_worker_failure({'stage': 'persist', 'reason': 'decoded_duration_mismatch'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00900_persist_empty_asr_1_true():
    lines = _drive({'stage': 'persist', 'reason': 'empty_asr'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00901_persist_empty_asr_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'empty_asr'}, disposition_enabled=True) is False
    )


def test_b90_c00902_persist_empty_asr_1_false():
    lines = _drive({'stage': 'persist', 'reason': 'empty_asr'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00903_persist_empty_asr_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'empty_asr'}, disposition_enabled=False) is False
    )


def test_b90_c00904_persist_empty_asr_2_true():
    lines = _drive({'stage': 'persist', 'reason': 'empty_asr'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00905_persist_empty_asr_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'empty_asr'}, disposition_enabled=True) is False
    )


def test_b90_c00906_persist_empty_asr_2_false():
    lines = _drive({'stage': 'persist', 'reason': 'empty_asr'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00907_persist_empty_asr_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'empty_asr'}, disposition_enabled=False) is False
    )


def test_b90_c00908_persist_empty_asr_7_true():
    lines = _drive({'stage': 'persist', 'reason': 'empty_asr'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00909_persist_empty_asr_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'empty_asr'}, disposition_enabled=True) is False
    )


def test_b90_c00910_persist_empty_asr_7_false():
    lines = _drive({'stage': 'persist', 'reason': 'empty_asr'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00911_persist_empty_asr_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'empty_asr'}, disposition_enabled=False) is False
    )


def test_b90_c00912_persist_empty_asr_99_true():
    lines = _drive({'stage': 'persist', 'reason': 'empty_asr'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00913_persist_empty_asr_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'empty_asr'}, disposition_enabled=True) is False
    )


def test_b90_c00914_persist_empty_asr_99_false():
    lines = _drive({'stage': 'persist', 'reason': 'empty_asr'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00915_persist_empty_asr_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'empty_asr'}, disposition_enabled=False) is False
    )


def test_b90_c00916_persist_empty_asr_evidence():
    assert transient_failure_evidence('persist', 'empty_asr') == {'stage': 'persist', 'reason': 'empty_asr'}


def test_b90_c00917_persist_empty_asr_validator():
    try:
        validate_worker_failure({'stage': 'persist', 'reason': 'empty_asr'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00918_persist_no_owned_words_1_true():
    lines = _drive({'stage': 'persist', 'reason': 'no_owned_words'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00919_persist_no_owned_words_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'no_owned_words'}, disposition_enabled=True)
        is False
    )


def test_b90_c00920_persist_no_owned_words_1_false():
    lines = _drive({'stage': 'persist', 'reason': 'no_owned_words'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00921_persist_no_owned_words_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'no_owned_words'}, disposition_enabled=False)
        is False
    )


def test_b90_c00922_persist_no_owned_words_2_true():
    lines = _drive({'stage': 'persist', 'reason': 'no_owned_words'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00923_persist_no_owned_words_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'no_owned_words'}, disposition_enabled=True)
        is False
    )


def test_b90_c00924_persist_no_owned_words_2_false():
    lines = _drive({'stage': 'persist', 'reason': 'no_owned_words'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00925_persist_no_owned_words_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'no_owned_words'}, disposition_enabled=False)
        is False
    )


def test_b90_c00926_persist_no_owned_words_7_true():
    lines = _drive({'stage': 'persist', 'reason': 'no_owned_words'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00927_persist_no_owned_words_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'no_owned_words'}, disposition_enabled=True)
        is False
    )


def test_b90_c00928_persist_no_owned_words_7_false():
    lines = _drive({'stage': 'persist', 'reason': 'no_owned_words'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00929_persist_no_owned_words_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'no_owned_words'}, disposition_enabled=False)
        is False
    )


def test_b90_c00930_persist_no_owned_words_99_true():
    lines = _drive({'stage': 'persist', 'reason': 'no_owned_words'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00931_persist_no_owned_words_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'no_owned_words'}, disposition_enabled=True)
        is False
    )


def test_b90_c00932_persist_no_owned_words_99_false():
    lines = _drive({'stage': 'persist', 'reason': 'no_owned_words'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00933_persist_no_owned_words_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'no_owned_words'}, disposition_enabled=False)
        is False
    )


def test_b90_c00934_persist_no_owned_words_evidence():
    assert transient_failure_evidence('persist', 'no_owned_words') == {'stage': 'persist', 'reason': 'no_owned_words'}


def test_b90_c00935_persist_no_owned_words_validator():
    try:
        validate_worker_failure({'stage': 'persist', 'reason': 'no_owned_words'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00936_persist_outside_admitted_source_1_true():
    lines = _drive({'stage': 'persist', 'reason': 'outside_admitted_source'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00937_persist_outside_admitted_source_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00938_persist_outside_admitted_source_1_false():
    lines = _drive({'stage': 'persist', 'reason': 'outside_admitted_source'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00939_persist_outside_admitted_source_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00940_persist_outside_admitted_source_2_true():
    lines = _drive({'stage': 'persist', 'reason': 'outside_admitted_source'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00941_persist_outside_admitted_source_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00942_persist_outside_admitted_source_2_false():
    lines = _drive({'stage': 'persist', 'reason': 'outside_admitted_source'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00943_persist_outside_admitted_source_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00944_persist_outside_admitted_source_7_true():
    lines = _drive({'stage': 'persist', 'reason': 'outside_admitted_source'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00945_persist_outside_admitted_source_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00946_persist_outside_admitted_source_7_false():
    lines = _drive({'stage': 'persist', 'reason': 'outside_admitted_source'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00947_persist_outside_admitted_source_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00948_persist_outside_admitted_source_99_true():
    lines = _drive({'stage': 'persist', 'reason': 'outside_admitted_source'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00949_persist_outside_admitted_source_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00950_persist_outside_admitted_source_99_false():
    lines = _drive({'stage': 'persist', 'reason': 'outside_admitted_source'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00951_persist_outside_admitted_source_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00952_persist_outside_admitted_source_evidence():
    assert transient_failure_evidence('persist', 'outside_admitted_source') == {
        'stage': 'persist',
        'reason': 'outside_admitted_source',
    }


def test_b90_c00953_persist_outside_admitted_source_validator():
    try:
        validate_worker_failure({'stage': 'persist', 'reason': 'outside_admitted_source'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00954_persist_persist_payload_invalid_1_true():
    lines = _drive({'stage': 'persist', 'reason': 'persist_payload_invalid'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00955_persist_persist_payload_invalid_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'persist_payload_invalid'}, disposition_enabled=True
        )
        is True
    )


def test_b90_c00956_persist_persist_payload_invalid_1_false():
    lines = _drive({'stage': 'persist', 'reason': 'persist_payload_invalid'}, 1, 'false')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00957_persist_persist_payload_invalid_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'persist_payload_invalid'}, disposition_enabled=False
        )
        is True
    )


def test_b90_c00958_persist_persist_payload_invalid_2_true():
    lines = _drive({'stage': 'persist', 'reason': 'persist_payload_invalid'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00959_persist_persist_payload_invalid_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'persist_payload_invalid'}, disposition_enabled=True
        )
        is True
    )


def test_b90_c00960_persist_persist_payload_invalid_2_false():
    lines = _drive({'stage': 'persist', 'reason': 'persist_payload_invalid'}, 2, 'false')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00961_persist_persist_payload_invalid_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'persist_payload_invalid'}, disposition_enabled=False
        )
        is True
    )


def test_b90_c00962_persist_persist_payload_invalid_7_true():
    lines = _drive({'stage': 'persist', 'reason': 'persist_payload_invalid'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00963_persist_persist_payload_invalid_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'persist_payload_invalid'}, disposition_enabled=True
        )
        is True
    )


def test_b90_c00964_persist_persist_payload_invalid_7_false():
    lines = _drive({'stage': 'persist', 'reason': 'persist_payload_invalid'}, 7, 'false')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00965_persist_persist_payload_invalid_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'persist_payload_invalid'}, disposition_enabled=False
        )
        is True
    )


def test_b90_c00966_persist_persist_payload_invalid_99_true():
    lines = _drive({'stage': 'persist', 'reason': 'persist_payload_invalid'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00967_persist_persist_payload_invalid_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'persist_payload_invalid'}, disposition_enabled=True
        )
        is True
    )


def test_b90_c00968_persist_persist_payload_invalid_99_false():
    lines = _drive({'stage': 'persist', 'reason': 'persist_payload_invalid'}, 99, 'false')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00969_persist_persist_payload_invalid_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'persist_payload_invalid'}, disposition_enabled=False
        )
        is True
    )


def test_b90_c00970_persist_persist_payload_invalid_evidence():
    assert transient_failure_evidence('persist', 'persist_payload_invalid') == {
        'stage': 'persist',
        'reason': 'persist_payload_invalid',
    }


def test_b90_c00971_persist_persist_payload_invalid_validator():
    try:
        validate_worker_failure({'stage': 'persist', 'reason': 'persist_payload_invalid'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00972_persist_retained_audio_invalid_1_true():
    lines = _drive({'stage': 'persist', 'reason': 'retained_audio_invalid'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00973_persist_retained_audio_invalid_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00974_persist_retained_audio_invalid_1_false():
    lines = _drive({'stage': 'persist', 'reason': 'retained_audio_invalid'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00975_persist_retained_audio_invalid_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00976_persist_retained_audio_invalid_2_true():
    lines = _drive({'stage': 'persist', 'reason': 'retained_audio_invalid'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00977_persist_retained_audio_invalid_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00978_persist_retained_audio_invalid_2_false():
    lines = _drive({'stage': 'persist', 'reason': 'retained_audio_invalid'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00979_persist_retained_audio_invalid_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00980_persist_retained_audio_invalid_7_true():
    lines = _drive({'stage': 'persist', 'reason': 'retained_audio_invalid'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00981_persist_retained_audio_invalid_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00982_persist_retained_audio_invalid_7_false():
    lines = _drive({'stage': 'persist', 'reason': 'retained_audio_invalid'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00983_persist_retained_audio_invalid_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00984_persist_retained_audio_invalid_99_true():
    lines = _drive({'stage': 'persist', 'reason': 'retained_audio_invalid'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00985_persist_retained_audio_invalid_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c00986_persist_retained_audio_invalid_99_false():
    lines = _drive({'stage': 'persist', 'reason': 'retained_audio_invalid'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00987_persist_retained_audio_invalid_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00988_persist_retained_audio_invalid_evidence():
    assert transient_failure_evidence('persist', 'retained_audio_invalid') == {
        'stage': 'persist',
        'reason': 'retained_audio_invalid',
    }


def test_b90_c00989_persist_retained_audio_invalid_validator():
    try:
        validate_worker_failure({'stage': 'persist', 'reason': 'retained_audio_invalid'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c00990_persist_staged_audio_invalid_1_true():
    lines = _drive({'stage': 'persist', 'reason': 'staged_audio_invalid'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00991_persist_staged_audio_invalid_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'staged_audio_invalid'}, disposition_enabled=True)
        is False
    )


def test_b90_c00992_persist_staged_audio_invalid_1_false():
    lines = _drive({'stage': 'persist', 'reason': 'staged_audio_invalid'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00993_persist_staged_audio_invalid_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00994_persist_staged_audio_invalid_2_true():
    lines = _drive({'stage': 'persist', 'reason': 'staged_audio_invalid'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00995_persist_staged_audio_invalid_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'staged_audio_invalid'}, disposition_enabled=True)
        is False
    )


def test_b90_c00996_persist_staged_audio_invalid_2_false():
    lines = _drive({'stage': 'persist', 'reason': 'staged_audio_invalid'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00997_persist_staged_audio_invalid_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c00998_persist_staged_audio_invalid_7_true():
    lines = _drive({'stage': 'persist', 'reason': 'staged_audio_invalid'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c00999_persist_staged_audio_invalid_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'staged_audio_invalid'}, disposition_enabled=True)
        is False
    )


def test_b90_c01000_persist_staged_audio_invalid_7_false():
    lines = _drive({'stage': 'persist', 'reason': 'staged_audio_invalid'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01001_persist_staged_audio_invalid_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01002_persist_staged_audio_invalid_99_true():
    lines = _drive({'stage': 'persist', 'reason': 'staged_audio_invalid'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01003_persist_staged_audio_invalid_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'staged_audio_invalid'}, disposition_enabled=True)
        is False
    )


def test_b90_c01004_persist_staged_audio_invalid_99_false():
    lines = _drive({'stage': 'persist', 'reason': 'staged_audio_invalid'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01005_persist_staged_audio_invalid_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01006_persist_staged_audio_invalid_evidence():
    assert transient_failure_evidence('persist', 'staged_audio_invalid') == {
        'stage': 'persist',
        'reason': 'staged_audio_invalid',
    }


def test_b90_c01007_persist_staged_audio_invalid_validator():
    try:
        validate_worker_failure({'stage': 'persist', 'reason': 'staged_audio_invalid'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01008_persist_unknown_1_true():
    lines = _drive({'stage': 'persist', 'reason': 'unknown'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01009_persist_unknown_1_true_predicate():
    assert validation_disposition_failure({'stage': 'persist', 'reason': 'unknown'}, disposition_enabled=True) is False


def test_b90_c01010_persist_unknown_1_false():
    lines = _drive({'stage': 'persist', 'reason': 'unknown'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01011_persist_unknown_1_false_predicate():
    assert validation_disposition_failure({'stage': 'persist', 'reason': 'unknown'}, disposition_enabled=False) is False


def test_b90_c01012_persist_unknown_2_true():
    lines = _drive({'stage': 'persist', 'reason': 'unknown'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01013_persist_unknown_2_true_predicate():
    assert validation_disposition_failure({'stage': 'persist', 'reason': 'unknown'}, disposition_enabled=True) is False


def test_b90_c01014_persist_unknown_2_false():
    lines = _drive({'stage': 'persist', 'reason': 'unknown'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01015_persist_unknown_2_false_predicate():
    assert validation_disposition_failure({'stage': 'persist', 'reason': 'unknown'}, disposition_enabled=False) is False


def test_b90_c01016_persist_unknown_7_true():
    lines = _drive({'stage': 'persist', 'reason': 'unknown'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01017_persist_unknown_7_true_predicate():
    assert validation_disposition_failure({'stage': 'persist', 'reason': 'unknown'}, disposition_enabled=True) is False


def test_b90_c01018_persist_unknown_7_false():
    lines = _drive({'stage': 'persist', 'reason': 'unknown'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01019_persist_unknown_7_false_predicate():
    assert validation_disposition_failure({'stage': 'persist', 'reason': 'unknown'}, disposition_enabled=False) is False


def test_b90_c01020_persist_unknown_99_true():
    lines = _drive({'stage': 'persist', 'reason': 'unknown'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01021_persist_unknown_99_true_predicate():
    assert validation_disposition_failure({'stage': 'persist', 'reason': 'unknown'}, disposition_enabled=True) is False


def test_b90_c01022_persist_unknown_99_false():
    lines = _drive({'stage': 'persist', 'reason': 'unknown'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01023_persist_unknown_99_false_predicate():
    assert validation_disposition_failure({'stage': 'persist', 'reason': 'unknown'}, disposition_enabled=False) is False


def test_b90_c01024_persist_unknown_evidence():
    assert transient_failure_evidence('persist', 'unknown') == {'stage': 'persist', 'reason': 'unknown'}


def test_b90_c01025_persist_unknown_validator():
    try:
        validate_worker_failure({'stage': 'persist', 'reason': 'unknown'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is False


def test_b90_c01026_persist_unsupported_language_1_true():
    lines = _drive({'stage': 'persist', 'reason': 'unsupported_language'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01027_persist_unsupported_language_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'unsupported_language'}, disposition_enabled=True)
        is False
    )


def test_b90_c01028_persist_unsupported_language_1_false():
    lines = _drive({'stage': 'persist', 'reason': 'unsupported_language'}, 1, 'false')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01029_persist_unsupported_language_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01030_persist_unsupported_language_2_true():
    lines = _drive({'stage': 'persist', 'reason': 'unsupported_language'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01031_persist_unsupported_language_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'unsupported_language'}, disposition_enabled=True)
        is False
    )


def test_b90_c01032_persist_unsupported_language_2_false():
    lines = _drive({'stage': 'persist', 'reason': 'unsupported_language'}, 2, 'false')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01033_persist_unsupported_language_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01034_persist_unsupported_language_7_true():
    lines = _drive({'stage': 'persist', 'reason': 'unsupported_language'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01035_persist_unsupported_language_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'unsupported_language'}, disposition_enabled=True)
        is False
    )


def test_b90_c01036_persist_unsupported_language_7_false():
    lines = _drive({'stage': 'persist', 'reason': 'unsupported_language'}, 7, 'false')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01037_persist_unsupported_language_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01038_persist_unsupported_language_99_true():
    lines = _drive({'stage': 'persist', 'reason': 'unsupported_language'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01039_persist_unsupported_language_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'unsupported_language'}, disposition_enabled=True)
        is False
    )


def test_b90_c01040_persist_unsupported_language_99_false():
    lines = _drive({'stage': 'persist', 'reason': 'unsupported_language'}, 99, 'false')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01041_persist_unsupported_language_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'persist', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01042_persist_unsupported_language_evidence():
    assert transient_failure_evidence('persist', 'unsupported_language') == {
        'stage': 'persist',
        'reason': 'unsupported_language',
    }


def test_b90_c01043_persist_unsupported_language_validator():
    try:
        validate_worker_failure({'stage': 'persist', 'reason': 'unsupported_language'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01044_persist_vad_bounds_1_true():
    lines = _drive({'stage': 'persist', 'reason': 'vad_bounds'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01045_persist_vad_bounds_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'vad_bounds'}, disposition_enabled=True) is True
    )


def test_b90_c01046_persist_vad_bounds_1_false():
    lines = _drive({'stage': 'persist', 'reason': 'vad_bounds'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01047_persist_vad_bounds_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'vad_bounds'}, disposition_enabled=False) is False
    )


def test_b90_c01048_persist_vad_bounds_2_true():
    lines = _drive({'stage': 'persist', 'reason': 'vad_bounds'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01049_persist_vad_bounds_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'vad_bounds'}, disposition_enabled=True) is True
    )


def test_b90_c01050_persist_vad_bounds_2_false():
    lines = _drive({'stage': 'persist', 'reason': 'vad_bounds'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01051_persist_vad_bounds_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'vad_bounds'}, disposition_enabled=False) is False
    )


def test_b90_c01052_persist_vad_bounds_7_true():
    lines = _drive({'stage': 'persist', 'reason': 'vad_bounds'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01053_persist_vad_bounds_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'vad_bounds'}, disposition_enabled=True) is True
    )


def test_b90_c01054_persist_vad_bounds_7_false():
    lines = _drive({'stage': 'persist', 'reason': 'vad_bounds'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01055_persist_vad_bounds_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'vad_bounds'}, disposition_enabled=False) is False
    )


def test_b90_c01056_persist_vad_bounds_99_true():
    lines = _drive({'stage': 'persist', 'reason': 'vad_bounds'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01057_persist_vad_bounds_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'vad_bounds'}, disposition_enabled=True) is True
    )


def test_b90_c01058_persist_vad_bounds_99_false():
    lines = _drive({'stage': 'persist', 'reason': 'vad_bounds'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01059_persist_vad_bounds_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'vad_bounds'}, disposition_enabled=False) is False
    )


def test_b90_c01060_persist_vad_bounds_evidence():
    assert transient_failure_evidence('persist', 'vad_bounds') == {'stage': 'persist', 'reason': 'vad_bounds'}


def test_b90_c01061_persist_vad_bounds_validator():
    try:
        validate_worker_failure({'stage': 'persist', 'reason': 'vad_bounds'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01062_persist_vad_nonfinite_1_true():
    lines = _drive({'stage': 'persist', 'reason': 'vad_nonfinite'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01063_persist_vad_nonfinite_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_b90_c01064_persist_vad_nonfinite_1_false():
    lines = _drive({'stage': 'persist', 'reason': 'vad_nonfinite'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01065_persist_vad_nonfinite_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'vad_nonfinite'}, disposition_enabled=False)
        is False
    )


def test_b90_c01066_persist_vad_nonfinite_2_true():
    lines = _drive({'stage': 'persist', 'reason': 'vad_nonfinite'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01067_persist_vad_nonfinite_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_b90_c01068_persist_vad_nonfinite_2_false():
    lines = _drive({'stage': 'persist', 'reason': 'vad_nonfinite'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01069_persist_vad_nonfinite_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'vad_nonfinite'}, disposition_enabled=False)
        is False
    )


def test_b90_c01070_persist_vad_nonfinite_7_true():
    lines = _drive({'stage': 'persist', 'reason': 'vad_nonfinite'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01071_persist_vad_nonfinite_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_b90_c01072_persist_vad_nonfinite_7_false():
    lines = _drive({'stage': 'persist', 'reason': 'vad_nonfinite'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01073_persist_vad_nonfinite_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'vad_nonfinite'}, disposition_enabled=False)
        is False
    )


def test_b90_c01074_persist_vad_nonfinite_99_true():
    lines = _drive({'stage': 'persist', 'reason': 'vad_nonfinite'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01075_persist_vad_nonfinite_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_b90_c01076_persist_vad_nonfinite_99_false():
    lines = _drive({'stage': 'persist', 'reason': 'vad_nonfinite'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01077_persist_vad_nonfinite_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'vad_nonfinite'}, disposition_enabled=False)
        is False
    )


def test_b90_c01078_persist_vad_nonfinite_evidence():
    assert transient_failure_evidence('persist', 'vad_nonfinite') == {'stage': 'persist', 'reason': 'vad_nonfinite'}


def test_b90_c01079_persist_vad_nonfinite_validator():
    try:
        validate_worker_failure({'stage': 'persist', 'reason': 'vad_nonfinite'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01080_persist_vad_order_1_true():
    lines = _drive({'stage': 'persist', 'reason': 'vad_order'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01081_persist_vad_order_1_true_predicate():
    assert validation_disposition_failure({'stage': 'persist', 'reason': 'vad_order'}, disposition_enabled=True) is True


def test_b90_c01082_persist_vad_order_1_false():
    lines = _drive({'stage': 'persist', 'reason': 'vad_order'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01083_persist_vad_order_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'vad_order'}, disposition_enabled=False) is False
    )


def test_b90_c01084_persist_vad_order_2_true():
    lines = _drive({'stage': 'persist', 'reason': 'vad_order'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01085_persist_vad_order_2_true_predicate():
    assert validation_disposition_failure({'stage': 'persist', 'reason': 'vad_order'}, disposition_enabled=True) is True


def test_b90_c01086_persist_vad_order_2_false():
    lines = _drive({'stage': 'persist', 'reason': 'vad_order'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01087_persist_vad_order_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'vad_order'}, disposition_enabled=False) is False
    )


def test_b90_c01088_persist_vad_order_7_true():
    lines = _drive({'stage': 'persist', 'reason': 'vad_order'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01089_persist_vad_order_7_true_predicate():
    assert validation_disposition_failure({'stage': 'persist', 'reason': 'vad_order'}, disposition_enabled=True) is True


def test_b90_c01090_persist_vad_order_7_false():
    lines = _drive({'stage': 'persist', 'reason': 'vad_order'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01091_persist_vad_order_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'vad_order'}, disposition_enabled=False) is False
    )


def test_b90_c01092_persist_vad_order_99_true():
    lines = _drive({'stage': 'persist', 'reason': 'vad_order'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01093_persist_vad_order_99_true_predicate():
    assert validation_disposition_failure({'stage': 'persist', 'reason': 'vad_order'}, disposition_enabled=True) is True


def test_b90_c01094_persist_vad_order_99_false():
    lines = _drive({'stage': 'persist', 'reason': 'vad_order'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01095_persist_vad_order_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'vad_order'}, disposition_enabled=False) is False
    )


def test_b90_c01096_persist_vad_order_evidence():
    assert transient_failure_evidence('persist', 'vad_order') == {'stage': 'persist', 'reason': 'vad_order'}


def test_b90_c01097_persist_vad_order_validator():
    try:
        validate_worker_failure({'stage': 'persist', 'reason': 'vad_order'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01098_persist_word_clock_1_true():
    lines = _drive({'stage': 'persist', 'reason': 'word_clock'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01099_persist_word_clock_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'word_clock'}, disposition_enabled=True) is True
    )


def test_b90_c01100_persist_word_clock_1_false():
    lines = _drive({'stage': 'persist', 'reason': 'word_clock'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01101_persist_word_clock_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'word_clock'}, disposition_enabled=False) is False
    )


def test_b90_c01102_persist_word_clock_2_true():
    lines = _drive({'stage': 'persist', 'reason': 'word_clock'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01103_persist_word_clock_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'word_clock'}, disposition_enabled=True) is True
    )


def test_b90_c01104_persist_word_clock_2_false():
    lines = _drive({'stage': 'persist', 'reason': 'word_clock'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01105_persist_word_clock_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'word_clock'}, disposition_enabled=False) is False
    )


def test_b90_c01106_persist_word_clock_7_true():
    lines = _drive({'stage': 'persist', 'reason': 'word_clock'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01107_persist_word_clock_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'word_clock'}, disposition_enabled=True) is True
    )


def test_b90_c01108_persist_word_clock_7_false():
    lines = _drive({'stage': 'persist', 'reason': 'word_clock'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01109_persist_word_clock_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'word_clock'}, disposition_enabled=False) is False
    )


def test_b90_c01110_persist_word_clock_99_true():
    lines = _drive({'stage': 'persist', 'reason': 'word_clock'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01111_persist_word_clock_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'word_clock'}, disposition_enabled=True) is True
    )


def test_b90_c01112_persist_word_clock_99_false():
    lines = _drive({'stage': 'persist', 'reason': 'word_clock'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01113_persist_word_clock_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'word_clock'}, disposition_enabled=False) is False
    )


def test_b90_c01114_persist_word_clock_evidence():
    assert transient_failure_evidence('persist', 'word_clock') == {'stage': 'persist', 'reason': 'word_clock'}


def test_b90_c01115_persist_word_clock_validator():
    try:
        validate_worker_failure({'stage': 'persist', 'reason': 'word_clock'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01116_persist_word_sequence_1_true():
    lines = _drive({'stage': 'persist', 'reason': 'word_sequence'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01117_persist_word_sequence_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_b90_c01118_persist_word_sequence_1_false():
    lines = _drive({'stage': 'persist', 'reason': 'word_sequence'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01119_persist_word_sequence_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'word_sequence'}, disposition_enabled=False)
        is False
    )


def test_b90_c01120_persist_word_sequence_2_true():
    lines = _drive({'stage': 'persist', 'reason': 'word_sequence'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01121_persist_word_sequence_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_b90_c01122_persist_word_sequence_2_false():
    lines = _drive({'stage': 'persist', 'reason': 'word_sequence'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01123_persist_word_sequence_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'word_sequence'}, disposition_enabled=False)
        is False
    )


def test_b90_c01124_persist_word_sequence_7_true():
    lines = _drive({'stage': 'persist', 'reason': 'word_sequence'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01125_persist_word_sequence_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_b90_c01126_persist_word_sequence_7_false():
    lines = _drive({'stage': 'persist', 'reason': 'word_sequence'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01127_persist_word_sequence_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'word_sequence'}, disposition_enabled=False)
        is False
    )


def test_b90_c01128_persist_word_sequence_99_true():
    lines = _drive({'stage': 'persist', 'reason': 'word_sequence'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01129_persist_word_sequence_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_b90_c01130_persist_word_sequence_99_false():
    lines = _drive({'stage': 'persist', 'reason': 'word_sequence'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01131_persist_word_sequence_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'word_sequence'}, disposition_enabled=False)
        is False
    )


def test_b90_c01132_persist_word_sequence_evidence():
    assert transient_failure_evidence('persist', 'word_sequence') == {'stage': 'persist', 'reason': 'word_sequence'}


def test_b90_c01133_persist_word_sequence_validator():
    try:
        validate_worker_failure({'stage': 'persist', 'reason': 'word_sequence'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01134_persist_word_shape_1_true():
    lines = _drive({'stage': 'persist', 'reason': 'word_shape'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01135_persist_word_shape_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'word_shape'}, disposition_enabled=True) is True
    )


def test_b90_c01136_persist_word_shape_1_false():
    lines = _drive({'stage': 'persist', 'reason': 'word_shape'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01137_persist_word_shape_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'word_shape'}, disposition_enabled=False) is False
    )


def test_b90_c01138_persist_word_shape_2_true():
    lines = _drive({'stage': 'persist', 'reason': 'word_shape'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01139_persist_word_shape_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'word_shape'}, disposition_enabled=True) is True
    )


def test_b90_c01140_persist_word_shape_2_false():
    lines = _drive({'stage': 'persist', 'reason': 'word_shape'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01141_persist_word_shape_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'word_shape'}, disposition_enabled=False) is False
    )


def test_b90_c01142_persist_word_shape_7_true():
    lines = _drive({'stage': 'persist', 'reason': 'word_shape'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01143_persist_word_shape_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'word_shape'}, disposition_enabled=True) is True
    )


def test_b90_c01144_persist_word_shape_7_false():
    lines = _drive({'stage': 'persist', 'reason': 'word_shape'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01145_persist_word_shape_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'word_shape'}, disposition_enabled=False) is False
    )


def test_b90_c01146_persist_word_shape_99_true():
    lines = _drive({'stage': 'persist', 'reason': 'word_shape'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01147_persist_word_shape_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'word_shape'}, disposition_enabled=True) is True
    )


def test_b90_c01148_persist_word_shape_99_false():
    lines = _drive({'stage': 'persist', 'reason': 'word_shape'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01149_persist_word_shape_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'word_shape'}, disposition_enabled=False) is False
    )


def test_b90_c01150_persist_word_shape_evidence():
    assert transient_failure_evidence('persist', 'word_shape') == {'stage': 'persist', 'reason': 'word_shape'}


def test_b90_c01151_persist_word_shape_validator():
    try:
        validate_worker_failure({'stage': 'persist', 'reason': 'word_shape'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01152_vad_windows_decode_payload_invalid_1_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'decode_payload_invalid'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01153_vad_windows_decode_payload_invalid_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'decode_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01154_vad_windows_decode_payload_invalid_1_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'decode_payload_invalid'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01155_vad_windows_decode_payload_invalid_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'decode_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01156_vad_windows_decode_payload_invalid_2_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'decode_payload_invalid'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01157_vad_windows_decode_payload_invalid_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'decode_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01158_vad_windows_decode_payload_invalid_2_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'decode_payload_invalid'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01159_vad_windows_decode_payload_invalid_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'decode_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01160_vad_windows_decode_payload_invalid_7_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'decode_payload_invalid'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01161_vad_windows_decode_payload_invalid_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'decode_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01162_vad_windows_decode_payload_invalid_7_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'decode_payload_invalid'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01163_vad_windows_decode_payload_invalid_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'decode_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01164_vad_windows_decode_payload_invalid_99_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'decode_payload_invalid'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01165_vad_windows_decode_payload_invalid_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'decode_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01166_vad_windows_decode_payload_invalid_99_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'decode_payload_invalid'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01167_vad_windows_decode_payload_invalid_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'decode_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01168_vad_windows_decode_payload_invalid_evidence():
    assert transient_failure_evidence('vad_windows', 'decode_payload_invalid') == {
        'stage': 'vad_windows',
        'reason': 'decode_payload_invalid',
    }


def test_b90_c01169_vad_windows_decode_payload_invalid_validator():
    try:
        validate_worker_failure({'stage': 'vad_windows', 'reason': 'decode_payload_invalid'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01170_vad_windows_decoded_duration_mismatch_1_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'decoded_duration_mismatch'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01171_vad_windows_decoded_duration_mismatch_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01172_vad_windows_decoded_duration_mismatch_1_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'decoded_duration_mismatch'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01173_vad_windows_decoded_duration_mismatch_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01174_vad_windows_decoded_duration_mismatch_2_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'decoded_duration_mismatch'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01175_vad_windows_decoded_duration_mismatch_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01176_vad_windows_decoded_duration_mismatch_2_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'decoded_duration_mismatch'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01177_vad_windows_decoded_duration_mismatch_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01178_vad_windows_decoded_duration_mismatch_7_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'decoded_duration_mismatch'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01179_vad_windows_decoded_duration_mismatch_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01180_vad_windows_decoded_duration_mismatch_7_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'decoded_duration_mismatch'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01181_vad_windows_decoded_duration_mismatch_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01182_vad_windows_decoded_duration_mismatch_99_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'decoded_duration_mismatch'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01183_vad_windows_decoded_duration_mismatch_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01184_vad_windows_decoded_duration_mismatch_99_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'decoded_duration_mismatch'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01185_vad_windows_decoded_duration_mismatch_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01186_vad_windows_decoded_duration_mismatch_evidence():
    assert transient_failure_evidence('vad_windows', 'decoded_duration_mismatch') == {
        'stage': 'vad_windows',
        'reason': 'decoded_duration_mismatch',
    }


def test_b90_c01187_vad_windows_decoded_duration_mismatch_validator():
    try:
        validate_worker_failure({'stage': 'vad_windows', 'reason': 'decoded_duration_mismatch'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01188_vad_windows_empty_asr_1_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'empty_asr'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01189_vad_windows_empty_asr_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'empty_asr'}, disposition_enabled=True)
        is False
    )


def test_b90_c01190_vad_windows_empty_asr_1_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'empty_asr'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01191_vad_windows_empty_asr_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'empty_asr'}, disposition_enabled=False)
        is False
    )


def test_b90_c01192_vad_windows_empty_asr_2_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'empty_asr'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01193_vad_windows_empty_asr_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'empty_asr'}, disposition_enabled=True)
        is False
    )


def test_b90_c01194_vad_windows_empty_asr_2_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'empty_asr'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01195_vad_windows_empty_asr_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'empty_asr'}, disposition_enabled=False)
        is False
    )


def test_b90_c01196_vad_windows_empty_asr_7_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'empty_asr'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01197_vad_windows_empty_asr_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'empty_asr'}, disposition_enabled=True)
        is False
    )


def test_b90_c01198_vad_windows_empty_asr_7_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'empty_asr'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01199_vad_windows_empty_asr_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'empty_asr'}, disposition_enabled=False)
        is False
    )


def test_b90_c01200_vad_windows_empty_asr_99_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'empty_asr'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01201_vad_windows_empty_asr_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'empty_asr'}, disposition_enabled=True)
        is False
    )


def test_b90_c01202_vad_windows_empty_asr_99_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'empty_asr'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01203_vad_windows_empty_asr_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'empty_asr'}, disposition_enabled=False)
        is False
    )


def test_b90_c01204_vad_windows_empty_asr_evidence():
    assert transient_failure_evidence('vad_windows', 'empty_asr') == {'stage': 'vad_windows', 'reason': 'empty_asr'}


def test_b90_c01205_vad_windows_empty_asr_validator():
    try:
        validate_worker_failure({'stage': 'vad_windows', 'reason': 'empty_asr'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01206_vad_windows_no_owned_words_1_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'no_owned_words'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01207_vad_windows_no_owned_words_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'no_owned_words'}, disposition_enabled=True)
        is False
    )


def test_b90_c01208_vad_windows_no_owned_words_1_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'no_owned_words'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01209_vad_windows_no_owned_words_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'no_owned_words'}, disposition_enabled=False)
        is False
    )


def test_b90_c01210_vad_windows_no_owned_words_2_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'no_owned_words'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01211_vad_windows_no_owned_words_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'no_owned_words'}, disposition_enabled=True)
        is False
    )


def test_b90_c01212_vad_windows_no_owned_words_2_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'no_owned_words'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01213_vad_windows_no_owned_words_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'no_owned_words'}, disposition_enabled=False)
        is False
    )


def test_b90_c01214_vad_windows_no_owned_words_7_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'no_owned_words'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01215_vad_windows_no_owned_words_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'no_owned_words'}, disposition_enabled=True)
        is False
    )


def test_b90_c01216_vad_windows_no_owned_words_7_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'no_owned_words'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01217_vad_windows_no_owned_words_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'no_owned_words'}, disposition_enabled=False)
        is False
    )


def test_b90_c01218_vad_windows_no_owned_words_99_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'no_owned_words'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01219_vad_windows_no_owned_words_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'no_owned_words'}, disposition_enabled=True)
        is False
    )


def test_b90_c01220_vad_windows_no_owned_words_99_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'no_owned_words'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01221_vad_windows_no_owned_words_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'no_owned_words'}, disposition_enabled=False)
        is False
    )


def test_b90_c01222_vad_windows_no_owned_words_evidence():
    assert transient_failure_evidence('vad_windows', 'no_owned_words') == {
        'stage': 'vad_windows',
        'reason': 'no_owned_words',
    }


def test_b90_c01223_vad_windows_no_owned_words_validator():
    try:
        validate_worker_failure({'stage': 'vad_windows', 'reason': 'no_owned_words'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01224_vad_windows_outside_admitted_source_1_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'outside_admitted_source'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01225_vad_windows_outside_admitted_source_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01226_vad_windows_outside_admitted_source_1_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'outside_admitted_source'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01227_vad_windows_outside_admitted_source_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01228_vad_windows_outside_admitted_source_2_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'outside_admitted_source'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01229_vad_windows_outside_admitted_source_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01230_vad_windows_outside_admitted_source_2_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'outside_admitted_source'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01231_vad_windows_outside_admitted_source_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01232_vad_windows_outside_admitted_source_7_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'outside_admitted_source'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01233_vad_windows_outside_admitted_source_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01234_vad_windows_outside_admitted_source_7_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'outside_admitted_source'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01235_vad_windows_outside_admitted_source_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01236_vad_windows_outside_admitted_source_99_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'outside_admitted_source'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01237_vad_windows_outside_admitted_source_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01238_vad_windows_outside_admitted_source_99_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'outside_admitted_source'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01239_vad_windows_outside_admitted_source_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01240_vad_windows_outside_admitted_source_evidence():
    assert transient_failure_evidence('vad_windows', 'outside_admitted_source') == {
        'stage': 'vad_windows',
        'reason': 'outside_admitted_source',
    }


def test_b90_c01241_vad_windows_outside_admitted_source_validator():
    try:
        validate_worker_failure({'stage': 'vad_windows', 'reason': 'outside_admitted_source'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01242_vad_windows_persist_payload_invalid_1_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'persist_payload_invalid'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01243_vad_windows_persist_payload_invalid_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'persist_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01244_vad_windows_persist_payload_invalid_1_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'persist_payload_invalid'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01245_vad_windows_persist_payload_invalid_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'persist_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01246_vad_windows_persist_payload_invalid_2_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'persist_payload_invalid'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01247_vad_windows_persist_payload_invalid_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'persist_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01248_vad_windows_persist_payload_invalid_2_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'persist_payload_invalid'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01249_vad_windows_persist_payload_invalid_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'persist_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01250_vad_windows_persist_payload_invalid_7_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'persist_payload_invalid'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01251_vad_windows_persist_payload_invalid_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'persist_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01252_vad_windows_persist_payload_invalid_7_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'persist_payload_invalid'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01253_vad_windows_persist_payload_invalid_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'persist_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01254_vad_windows_persist_payload_invalid_99_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'persist_payload_invalid'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01255_vad_windows_persist_payload_invalid_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'persist_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01256_vad_windows_persist_payload_invalid_99_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'persist_payload_invalid'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01257_vad_windows_persist_payload_invalid_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'persist_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01258_vad_windows_persist_payload_invalid_evidence():
    assert transient_failure_evidence('vad_windows', 'persist_payload_invalid') == {
        'stage': 'vad_windows',
        'reason': 'persist_payload_invalid',
    }


def test_b90_c01259_vad_windows_persist_payload_invalid_validator():
    try:
        validate_worker_failure({'stage': 'vad_windows', 'reason': 'persist_payload_invalid'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01260_vad_windows_retained_audio_invalid_1_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'retained_audio_invalid'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01261_vad_windows_retained_audio_invalid_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01262_vad_windows_retained_audio_invalid_1_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'retained_audio_invalid'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01263_vad_windows_retained_audio_invalid_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01264_vad_windows_retained_audio_invalid_2_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'retained_audio_invalid'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01265_vad_windows_retained_audio_invalid_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01266_vad_windows_retained_audio_invalid_2_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'retained_audio_invalid'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01267_vad_windows_retained_audio_invalid_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01268_vad_windows_retained_audio_invalid_7_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'retained_audio_invalid'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01269_vad_windows_retained_audio_invalid_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01270_vad_windows_retained_audio_invalid_7_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'retained_audio_invalid'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01271_vad_windows_retained_audio_invalid_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01272_vad_windows_retained_audio_invalid_99_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'retained_audio_invalid'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01273_vad_windows_retained_audio_invalid_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01274_vad_windows_retained_audio_invalid_99_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'retained_audio_invalid'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01275_vad_windows_retained_audio_invalid_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01276_vad_windows_retained_audio_invalid_evidence():
    assert transient_failure_evidence('vad_windows', 'retained_audio_invalid') == {
        'stage': 'vad_windows',
        'reason': 'retained_audio_invalid',
    }


def test_b90_c01277_vad_windows_retained_audio_invalid_validator():
    try:
        validate_worker_failure({'stage': 'vad_windows', 'reason': 'retained_audio_invalid'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01278_vad_windows_staged_audio_invalid_1_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'staged_audio_invalid'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01279_vad_windows_staged_audio_invalid_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'staged_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01280_vad_windows_staged_audio_invalid_1_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'staged_audio_invalid'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01281_vad_windows_staged_audio_invalid_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01282_vad_windows_staged_audio_invalid_2_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'staged_audio_invalid'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01283_vad_windows_staged_audio_invalid_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'staged_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01284_vad_windows_staged_audio_invalid_2_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'staged_audio_invalid'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01285_vad_windows_staged_audio_invalid_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01286_vad_windows_staged_audio_invalid_7_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'staged_audio_invalid'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01287_vad_windows_staged_audio_invalid_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'staged_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01288_vad_windows_staged_audio_invalid_7_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'staged_audio_invalid'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01289_vad_windows_staged_audio_invalid_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01290_vad_windows_staged_audio_invalid_99_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'staged_audio_invalid'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01291_vad_windows_staged_audio_invalid_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'staged_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01292_vad_windows_staged_audio_invalid_99_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'staged_audio_invalid'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01293_vad_windows_staged_audio_invalid_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01294_vad_windows_staged_audio_invalid_evidence():
    assert transient_failure_evidence('vad_windows', 'staged_audio_invalid') == {
        'stage': 'vad_windows',
        'reason': 'staged_audio_invalid',
    }


def test_b90_c01295_vad_windows_staged_audio_invalid_validator():
    try:
        validate_worker_failure({'stage': 'vad_windows', 'reason': 'staged_audio_invalid'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01296_vad_windows_unknown_1_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'unknown'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01297_vad_windows_unknown_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'unknown'}, disposition_enabled=True) is False
    )


def test_b90_c01298_vad_windows_unknown_1_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'unknown'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01299_vad_windows_unknown_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'unknown'}, disposition_enabled=False)
        is False
    )


def test_b90_c01300_vad_windows_unknown_2_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'unknown'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01301_vad_windows_unknown_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'unknown'}, disposition_enabled=True) is False
    )


def test_b90_c01302_vad_windows_unknown_2_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'unknown'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01303_vad_windows_unknown_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'unknown'}, disposition_enabled=False)
        is False
    )


def test_b90_c01304_vad_windows_unknown_7_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'unknown'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01305_vad_windows_unknown_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'unknown'}, disposition_enabled=True) is False
    )


def test_b90_c01306_vad_windows_unknown_7_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'unknown'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01307_vad_windows_unknown_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'unknown'}, disposition_enabled=False)
        is False
    )


def test_b90_c01308_vad_windows_unknown_99_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'unknown'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01309_vad_windows_unknown_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'unknown'}, disposition_enabled=True) is False
    )


def test_b90_c01310_vad_windows_unknown_99_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'unknown'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01311_vad_windows_unknown_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'unknown'}, disposition_enabled=False)
        is False
    )


def test_b90_c01312_vad_windows_unknown_evidence():
    assert transient_failure_evidence('vad_windows', 'unknown') == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_b90_c01313_vad_windows_unknown_validator():
    try:
        validate_worker_failure({'stage': 'vad_windows', 'reason': 'unknown'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is False


def test_b90_c01314_vad_windows_unsupported_language_1_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'unsupported_language'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01315_vad_windows_unsupported_language_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'unsupported_language'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01316_vad_windows_unsupported_language_1_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'unsupported_language'}, 1, 'false')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01317_vad_windows_unsupported_language_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01318_vad_windows_unsupported_language_2_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'unsupported_language'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01319_vad_windows_unsupported_language_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'unsupported_language'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01320_vad_windows_unsupported_language_2_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'unsupported_language'}, 2, 'false')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01321_vad_windows_unsupported_language_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01322_vad_windows_unsupported_language_7_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'unsupported_language'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01323_vad_windows_unsupported_language_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'unsupported_language'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01324_vad_windows_unsupported_language_7_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'unsupported_language'}, 7, 'false')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01325_vad_windows_unsupported_language_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01326_vad_windows_unsupported_language_99_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'unsupported_language'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01327_vad_windows_unsupported_language_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'unsupported_language'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01328_vad_windows_unsupported_language_99_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'unsupported_language'}, 99, 'false')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01329_vad_windows_unsupported_language_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01330_vad_windows_unsupported_language_evidence():
    assert transient_failure_evidence('vad_windows', 'unsupported_language') == {
        'stage': 'vad_windows',
        'reason': 'unsupported_language',
    }


def test_b90_c01331_vad_windows_unsupported_language_validator():
    try:
        validate_worker_failure({'stage': 'vad_windows', 'reason': 'unsupported_language'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01332_vad_windows_vad_bounds_1_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'vad_bounds'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01333_vad_windows_vad_bounds_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_bounds'}, disposition_enabled=True)
        is True
    )


def test_b90_c01334_vad_windows_vad_bounds_1_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'vad_bounds'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01335_vad_windows_vad_bounds_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_bounds'}, disposition_enabled=False)
        is False
    )


def test_b90_c01336_vad_windows_vad_bounds_2_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'vad_bounds'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01337_vad_windows_vad_bounds_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_bounds'}, disposition_enabled=True)
        is True
    )


def test_b90_c01338_vad_windows_vad_bounds_2_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'vad_bounds'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01339_vad_windows_vad_bounds_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_bounds'}, disposition_enabled=False)
        is False
    )


def test_b90_c01340_vad_windows_vad_bounds_7_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'vad_bounds'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01341_vad_windows_vad_bounds_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_bounds'}, disposition_enabled=True)
        is True
    )


def test_b90_c01342_vad_windows_vad_bounds_7_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'vad_bounds'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01343_vad_windows_vad_bounds_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_bounds'}, disposition_enabled=False)
        is False
    )


def test_b90_c01344_vad_windows_vad_bounds_99_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'vad_bounds'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01345_vad_windows_vad_bounds_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_bounds'}, disposition_enabled=True)
        is True
    )


def test_b90_c01346_vad_windows_vad_bounds_99_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'vad_bounds'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01347_vad_windows_vad_bounds_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_bounds'}, disposition_enabled=False)
        is False
    )


def test_b90_c01348_vad_windows_vad_bounds_evidence():
    assert transient_failure_evidence('vad_windows', 'vad_bounds') == {'stage': 'vad_windows', 'reason': 'vad_bounds'}


def test_b90_c01349_vad_windows_vad_bounds_validator():
    try:
        validate_worker_failure({'stage': 'vad_windows', 'reason': 'vad_bounds'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01350_vad_windows_vad_nonfinite_1_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'vad_nonfinite'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01351_vad_windows_vad_nonfinite_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_b90_c01352_vad_windows_vad_nonfinite_1_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'vad_nonfinite'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01353_vad_windows_vad_nonfinite_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_nonfinite'}, disposition_enabled=False)
        is False
    )


def test_b90_c01354_vad_windows_vad_nonfinite_2_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'vad_nonfinite'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01355_vad_windows_vad_nonfinite_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_b90_c01356_vad_windows_vad_nonfinite_2_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'vad_nonfinite'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01357_vad_windows_vad_nonfinite_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_nonfinite'}, disposition_enabled=False)
        is False
    )


def test_b90_c01358_vad_windows_vad_nonfinite_7_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'vad_nonfinite'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01359_vad_windows_vad_nonfinite_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_b90_c01360_vad_windows_vad_nonfinite_7_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'vad_nonfinite'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01361_vad_windows_vad_nonfinite_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_nonfinite'}, disposition_enabled=False)
        is False
    )


def test_b90_c01362_vad_windows_vad_nonfinite_99_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'vad_nonfinite'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01363_vad_windows_vad_nonfinite_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_b90_c01364_vad_windows_vad_nonfinite_99_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'vad_nonfinite'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01365_vad_windows_vad_nonfinite_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_nonfinite'}, disposition_enabled=False)
        is False
    )


def test_b90_c01366_vad_windows_vad_nonfinite_evidence():
    assert transient_failure_evidence('vad_windows', 'vad_nonfinite') == {
        'stage': 'vad_windows',
        'reason': 'vad_nonfinite',
    }


def test_b90_c01367_vad_windows_vad_nonfinite_validator():
    try:
        validate_worker_failure({'stage': 'vad_windows', 'reason': 'vad_nonfinite'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01368_vad_windows_vad_order_1_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'vad_order'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01369_vad_windows_vad_order_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_order'}, disposition_enabled=True)
        is True
    )


def test_b90_c01370_vad_windows_vad_order_1_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'vad_order'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01371_vad_windows_vad_order_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_order'}, disposition_enabled=False)
        is False
    )


def test_b90_c01372_vad_windows_vad_order_2_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'vad_order'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01373_vad_windows_vad_order_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_order'}, disposition_enabled=True)
        is True
    )


def test_b90_c01374_vad_windows_vad_order_2_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'vad_order'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01375_vad_windows_vad_order_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_order'}, disposition_enabled=False)
        is False
    )


def test_b90_c01376_vad_windows_vad_order_7_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'vad_order'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01377_vad_windows_vad_order_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_order'}, disposition_enabled=True)
        is True
    )


def test_b90_c01378_vad_windows_vad_order_7_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'vad_order'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01379_vad_windows_vad_order_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_order'}, disposition_enabled=False)
        is False
    )


def test_b90_c01380_vad_windows_vad_order_99_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'vad_order'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01381_vad_windows_vad_order_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_order'}, disposition_enabled=True)
        is True
    )


def test_b90_c01382_vad_windows_vad_order_99_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'vad_order'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01383_vad_windows_vad_order_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_order'}, disposition_enabled=False)
        is False
    )


def test_b90_c01384_vad_windows_vad_order_evidence():
    assert transient_failure_evidence('vad_windows', 'vad_order') == {'stage': 'vad_windows', 'reason': 'vad_order'}


def test_b90_c01385_vad_windows_vad_order_validator():
    try:
        validate_worker_failure({'stage': 'vad_windows', 'reason': 'vad_order'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01386_vad_windows_word_clock_1_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'word_clock'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01387_vad_windows_word_clock_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_clock'}, disposition_enabled=True)
        is True
    )


def test_b90_c01388_vad_windows_word_clock_1_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'word_clock'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01389_vad_windows_word_clock_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_clock'}, disposition_enabled=False)
        is False
    )


def test_b90_c01390_vad_windows_word_clock_2_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'word_clock'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01391_vad_windows_word_clock_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_clock'}, disposition_enabled=True)
        is True
    )


def test_b90_c01392_vad_windows_word_clock_2_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'word_clock'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01393_vad_windows_word_clock_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_clock'}, disposition_enabled=False)
        is False
    )


def test_b90_c01394_vad_windows_word_clock_7_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'word_clock'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01395_vad_windows_word_clock_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_clock'}, disposition_enabled=True)
        is True
    )


def test_b90_c01396_vad_windows_word_clock_7_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'word_clock'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01397_vad_windows_word_clock_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_clock'}, disposition_enabled=False)
        is False
    )


def test_b90_c01398_vad_windows_word_clock_99_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'word_clock'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01399_vad_windows_word_clock_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_clock'}, disposition_enabled=True)
        is True
    )


def test_b90_c01400_vad_windows_word_clock_99_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'word_clock'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01401_vad_windows_word_clock_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_clock'}, disposition_enabled=False)
        is False
    )


def test_b90_c01402_vad_windows_word_clock_evidence():
    assert transient_failure_evidence('vad_windows', 'word_clock') == {'stage': 'vad_windows', 'reason': 'word_clock'}


def test_b90_c01403_vad_windows_word_clock_validator():
    try:
        validate_worker_failure({'stage': 'vad_windows', 'reason': 'word_clock'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01404_vad_windows_word_sequence_1_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'word_sequence'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01405_vad_windows_word_sequence_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_b90_c01406_vad_windows_word_sequence_1_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'word_sequence'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01407_vad_windows_word_sequence_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_sequence'}, disposition_enabled=False)
        is False
    )


def test_b90_c01408_vad_windows_word_sequence_2_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'word_sequence'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01409_vad_windows_word_sequence_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_b90_c01410_vad_windows_word_sequence_2_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'word_sequence'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01411_vad_windows_word_sequence_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_sequence'}, disposition_enabled=False)
        is False
    )


def test_b90_c01412_vad_windows_word_sequence_7_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'word_sequence'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01413_vad_windows_word_sequence_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_b90_c01414_vad_windows_word_sequence_7_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'word_sequence'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01415_vad_windows_word_sequence_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_sequence'}, disposition_enabled=False)
        is False
    )


def test_b90_c01416_vad_windows_word_sequence_99_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'word_sequence'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01417_vad_windows_word_sequence_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_b90_c01418_vad_windows_word_sequence_99_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'word_sequence'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01419_vad_windows_word_sequence_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_sequence'}, disposition_enabled=False)
        is False
    )


def test_b90_c01420_vad_windows_word_sequence_evidence():
    assert transient_failure_evidence('vad_windows', 'word_sequence') == {
        'stage': 'vad_windows',
        'reason': 'word_sequence',
    }


def test_b90_c01421_vad_windows_word_sequence_validator():
    try:
        validate_worker_failure({'stage': 'vad_windows', 'reason': 'word_sequence'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01422_vad_windows_word_shape_1_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'word_shape'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01423_vad_windows_word_shape_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_shape'}, disposition_enabled=True)
        is True
    )


def test_b90_c01424_vad_windows_word_shape_1_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'word_shape'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01425_vad_windows_word_shape_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_shape'}, disposition_enabled=False)
        is False
    )


def test_b90_c01426_vad_windows_word_shape_2_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'word_shape'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01427_vad_windows_word_shape_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_shape'}, disposition_enabled=True)
        is True
    )


def test_b90_c01428_vad_windows_word_shape_2_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'word_shape'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01429_vad_windows_word_shape_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_shape'}, disposition_enabled=False)
        is False
    )


def test_b90_c01430_vad_windows_word_shape_7_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'word_shape'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01431_vad_windows_word_shape_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_shape'}, disposition_enabled=True)
        is True
    )


def test_b90_c01432_vad_windows_word_shape_7_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'word_shape'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01433_vad_windows_word_shape_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_shape'}, disposition_enabled=False)
        is False
    )


def test_b90_c01434_vad_windows_word_shape_99_true():
    lines = _drive({'stage': 'vad_windows', 'reason': 'word_shape'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01435_vad_windows_word_shape_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_shape'}, disposition_enabled=True)
        is True
    )


def test_b90_c01436_vad_windows_word_shape_99_false():
    lines = _drive({'stage': 'vad_windows', 'reason': 'word_shape'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01437_vad_windows_word_shape_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_shape'}, disposition_enabled=False)
        is False
    )


def test_b90_c01438_vad_windows_word_shape_evidence():
    assert transient_failure_evidence('vad_windows', 'word_shape') == {'stage': 'vad_windows', 'reason': 'word_shape'}


def test_b90_c01439_vad_windows_word_shape_validator():
    try:
        validate_worker_failure({'stage': 'vad_windows', 'reason': 'word_shape'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01440_word_clocks_decode_payload_invalid_1_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'decode_payload_invalid'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01441_word_clocks_decode_payload_invalid_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'decode_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01442_word_clocks_decode_payload_invalid_1_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'decode_payload_invalid'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01443_word_clocks_decode_payload_invalid_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'decode_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01444_word_clocks_decode_payload_invalid_2_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'decode_payload_invalid'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01445_word_clocks_decode_payload_invalid_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'decode_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01446_word_clocks_decode_payload_invalid_2_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'decode_payload_invalid'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01447_word_clocks_decode_payload_invalid_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'decode_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01448_word_clocks_decode_payload_invalid_7_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'decode_payload_invalid'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01449_word_clocks_decode_payload_invalid_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'decode_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01450_word_clocks_decode_payload_invalid_7_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'decode_payload_invalid'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01451_word_clocks_decode_payload_invalid_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'decode_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01452_word_clocks_decode_payload_invalid_99_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'decode_payload_invalid'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01453_word_clocks_decode_payload_invalid_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'decode_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01454_word_clocks_decode_payload_invalid_99_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'decode_payload_invalid'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01455_word_clocks_decode_payload_invalid_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'decode_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01456_word_clocks_decode_payload_invalid_evidence():
    assert transient_failure_evidence('word_clocks', 'decode_payload_invalid') == {
        'stage': 'word_clocks',
        'reason': 'decode_payload_invalid',
    }


def test_b90_c01457_word_clocks_decode_payload_invalid_validator():
    try:
        validate_worker_failure({'stage': 'word_clocks', 'reason': 'decode_payload_invalid'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01458_word_clocks_decoded_duration_mismatch_1_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'decoded_duration_mismatch'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01459_word_clocks_decoded_duration_mismatch_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01460_word_clocks_decoded_duration_mismatch_1_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'decoded_duration_mismatch'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01461_word_clocks_decoded_duration_mismatch_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01462_word_clocks_decoded_duration_mismatch_2_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'decoded_duration_mismatch'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01463_word_clocks_decoded_duration_mismatch_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01464_word_clocks_decoded_duration_mismatch_2_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'decoded_duration_mismatch'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01465_word_clocks_decoded_duration_mismatch_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01466_word_clocks_decoded_duration_mismatch_7_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'decoded_duration_mismatch'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01467_word_clocks_decoded_duration_mismatch_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01468_word_clocks_decoded_duration_mismatch_7_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'decoded_duration_mismatch'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01469_word_clocks_decoded_duration_mismatch_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01470_word_clocks_decoded_duration_mismatch_99_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'decoded_duration_mismatch'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01471_word_clocks_decoded_duration_mismatch_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01472_word_clocks_decoded_duration_mismatch_99_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'decoded_duration_mismatch'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01473_word_clocks_decoded_duration_mismatch_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01474_word_clocks_decoded_duration_mismatch_evidence():
    assert transient_failure_evidence('word_clocks', 'decoded_duration_mismatch') == {
        'stage': 'word_clocks',
        'reason': 'decoded_duration_mismatch',
    }


def test_b90_c01475_word_clocks_decoded_duration_mismatch_validator():
    try:
        validate_worker_failure({'stage': 'word_clocks', 'reason': 'decoded_duration_mismatch'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01476_word_clocks_empty_asr_1_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'empty_asr'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01477_word_clocks_empty_asr_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'empty_asr'}, disposition_enabled=True)
        is False
    )


def test_b90_c01478_word_clocks_empty_asr_1_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'empty_asr'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01479_word_clocks_empty_asr_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'empty_asr'}, disposition_enabled=False)
        is False
    )


def test_b90_c01480_word_clocks_empty_asr_2_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'empty_asr'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01481_word_clocks_empty_asr_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'empty_asr'}, disposition_enabled=True)
        is False
    )


def test_b90_c01482_word_clocks_empty_asr_2_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'empty_asr'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01483_word_clocks_empty_asr_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'empty_asr'}, disposition_enabled=False)
        is False
    )


def test_b90_c01484_word_clocks_empty_asr_7_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'empty_asr'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01485_word_clocks_empty_asr_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'empty_asr'}, disposition_enabled=True)
        is False
    )


def test_b90_c01486_word_clocks_empty_asr_7_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'empty_asr'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01487_word_clocks_empty_asr_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'empty_asr'}, disposition_enabled=False)
        is False
    )


def test_b90_c01488_word_clocks_empty_asr_99_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'empty_asr'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01489_word_clocks_empty_asr_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'empty_asr'}, disposition_enabled=True)
        is False
    )


def test_b90_c01490_word_clocks_empty_asr_99_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'empty_asr'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01491_word_clocks_empty_asr_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'empty_asr'}, disposition_enabled=False)
        is False
    )


def test_b90_c01492_word_clocks_empty_asr_evidence():
    assert transient_failure_evidence('word_clocks', 'empty_asr') == {'stage': 'word_clocks', 'reason': 'empty_asr'}


def test_b90_c01493_word_clocks_empty_asr_validator():
    try:
        validate_worker_failure({'stage': 'word_clocks', 'reason': 'empty_asr'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01494_word_clocks_no_owned_words_1_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'no_owned_words'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01495_word_clocks_no_owned_words_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'no_owned_words'}, disposition_enabled=True)
        is False
    )


def test_b90_c01496_word_clocks_no_owned_words_1_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'no_owned_words'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01497_word_clocks_no_owned_words_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'no_owned_words'}, disposition_enabled=False)
        is False
    )


def test_b90_c01498_word_clocks_no_owned_words_2_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'no_owned_words'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01499_word_clocks_no_owned_words_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'no_owned_words'}, disposition_enabled=True)
        is False
    )


def test_b90_c01500_word_clocks_no_owned_words_2_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'no_owned_words'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01501_word_clocks_no_owned_words_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'no_owned_words'}, disposition_enabled=False)
        is False
    )


def test_b90_c01502_word_clocks_no_owned_words_7_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'no_owned_words'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01503_word_clocks_no_owned_words_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'no_owned_words'}, disposition_enabled=True)
        is False
    )


def test_b90_c01504_word_clocks_no_owned_words_7_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'no_owned_words'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01505_word_clocks_no_owned_words_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'no_owned_words'}, disposition_enabled=False)
        is False
    )


def test_b90_c01506_word_clocks_no_owned_words_99_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'no_owned_words'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01507_word_clocks_no_owned_words_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'no_owned_words'}, disposition_enabled=True)
        is False
    )


def test_b90_c01508_word_clocks_no_owned_words_99_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'no_owned_words'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01509_word_clocks_no_owned_words_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'no_owned_words'}, disposition_enabled=False)
        is False
    )


def test_b90_c01510_word_clocks_no_owned_words_evidence():
    assert transient_failure_evidence('word_clocks', 'no_owned_words') == {
        'stage': 'word_clocks',
        'reason': 'no_owned_words',
    }


def test_b90_c01511_word_clocks_no_owned_words_validator():
    try:
        validate_worker_failure({'stage': 'word_clocks', 'reason': 'no_owned_words'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01512_word_clocks_outside_admitted_source_1_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'outside_admitted_source'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01513_word_clocks_outside_admitted_source_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01514_word_clocks_outside_admitted_source_1_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'outside_admitted_source'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01515_word_clocks_outside_admitted_source_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01516_word_clocks_outside_admitted_source_2_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'outside_admitted_source'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01517_word_clocks_outside_admitted_source_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01518_word_clocks_outside_admitted_source_2_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'outside_admitted_source'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01519_word_clocks_outside_admitted_source_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01520_word_clocks_outside_admitted_source_7_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'outside_admitted_source'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01521_word_clocks_outside_admitted_source_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01522_word_clocks_outside_admitted_source_7_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'outside_admitted_source'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01523_word_clocks_outside_admitted_source_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01524_word_clocks_outside_admitted_source_99_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'outside_admitted_source'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01525_word_clocks_outside_admitted_source_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01526_word_clocks_outside_admitted_source_99_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'outside_admitted_source'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01527_word_clocks_outside_admitted_source_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01528_word_clocks_outside_admitted_source_evidence():
    assert transient_failure_evidence('word_clocks', 'outside_admitted_source') == {
        'stage': 'word_clocks',
        'reason': 'outside_admitted_source',
    }


def test_b90_c01529_word_clocks_outside_admitted_source_validator():
    try:
        validate_worker_failure({'stage': 'word_clocks', 'reason': 'outside_admitted_source'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01530_word_clocks_persist_payload_invalid_1_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'persist_payload_invalid'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01531_word_clocks_persist_payload_invalid_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'persist_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01532_word_clocks_persist_payload_invalid_1_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'persist_payload_invalid'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01533_word_clocks_persist_payload_invalid_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'persist_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01534_word_clocks_persist_payload_invalid_2_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'persist_payload_invalid'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01535_word_clocks_persist_payload_invalid_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'persist_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01536_word_clocks_persist_payload_invalid_2_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'persist_payload_invalid'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01537_word_clocks_persist_payload_invalid_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'persist_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01538_word_clocks_persist_payload_invalid_7_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'persist_payload_invalid'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01539_word_clocks_persist_payload_invalid_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'persist_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01540_word_clocks_persist_payload_invalid_7_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'persist_payload_invalid'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01541_word_clocks_persist_payload_invalid_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'persist_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01542_word_clocks_persist_payload_invalid_99_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'persist_payload_invalid'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01543_word_clocks_persist_payload_invalid_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'persist_payload_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01544_word_clocks_persist_payload_invalid_99_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'persist_payload_invalid'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01545_word_clocks_persist_payload_invalid_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'persist_payload_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01546_word_clocks_persist_payload_invalid_evidence():
    assert transient_failure_evidence('word_clocks', 'persist_payload_invalid') == {
        'stage': 'word_clocks',
        'reason': 'persist_payload_invalid',
    }


def test_b90_c01547_word_clocks_persist_payload_invalid_validator():
    try:
        validate_worker_failure({'stage': 'word_clocks', 'reason': 'persist_payload_invalid'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01548_word_clocks_retained_audio_invalid_1_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'retained_audio_invalid'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01549_word_clocks_retained_audio_invalid_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01550_word_clocks_retained_audio_invalid_1_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'retained_audio_invalid'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01551_word_clocks_retained_audio_invalid_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01552_word_clocks_retained_audio_invalid_2_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'retained_audio_invalid'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01553_word_clocks_retained_audio_invalid_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01554_word_clocks_retained_audio_invalid_2_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'retained_audio_invalid'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01555_word_clocks_retained_audio_invalid_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01556_word_clocks_retained_audio_invalid_7_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'retained_audio_invalid'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01557_word_clocks_retained_audio_invalid_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01558_word_clocks_retained_audio_invalid_7_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'retained_audio_invalid'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01559_word_clocks_retained_audio_invalid_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01560_word_clocks_retained_audio_invalid_99_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'retained_audio_invalid'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01561_word_clocks_retained_audio_invalid_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01562_word_clocks_retained_audio_invalid_99_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'retained_audio_invalid'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01563_word_clocks_retained_audio_invalid_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01564_word_clocks_retained_audio_invalid_evidence():
    assert transient_failure_evidence('word_clocks', 'retained_audio_invalid') == {
        'stage': 'word_clocks',
        'reason': 'retained_audio_invalid',
    }


def test_b90_c01565_word_clocks_retained_audio_invalid_validator():
    try:
        validate_worker_failure({'stage': 'word_clocks', 'reason': 'retained_audio_invalid'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01566_word_clocks_staged_audio_invalid_1_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'staged_audio_invalid'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01567_word_clocks_staged_audio_invalid_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'staged_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01568_word_clocks_staged_audio_invalid_1_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'staged_audio_invalid'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01569_word_clocks_staged_audio_invalid_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01570_word_clocks_staged_audio_invalid_2_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'staged_audio_invalid'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01571_word_clocks_staged_audio_invalid_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'staged_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01572_word_clocks_staged_audio_invalid_2_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'staged_audio_invalid'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01573_word_clocks_staged_audio_invalid_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01574_word_clocks_staged_audio_invalid_7_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'staged_audio_invalid'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01575_word_clocks_staged_audio_invalid_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'staged_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01576_word_clocks_staged_audio_invalid_7_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'staged_audio_invalid'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01577_word_clocks_staged_audio_invalid_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01578_word_clocks_staged_audio_invalid_99_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'staged_audio_invalid'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01579_word_clocks_staged_audio_invalid_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'staged_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01580_word_clocks_staged_audio_invalid_99_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'staged_audio_invalid'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01581_word_clocks_staged_audio_invalid_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01582_word_clocks_staged_audio_invalid_evidence():
    assert transient_failure_evidence('word_clocks', 'staged_audio_invalid') == {
        'stage': 'word_clocks',
        'reason': 'staged_audio_invalid',
    }


def test_b90_c01583_word_clocks_staged_audio_invalid_validator():
    try:
        validate_worker_failure({'stage': 'word_clocks', 'reason': 'staged_audio_invalid'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01584_word_clocks_unknown_1_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'unknown'}, 1, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01585_word_clocks_unknown_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'unknown'}, disposition_enabled=True) is False
    )


def test_b90_c01586_word_clocks_unknown_1_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'unknown'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01587_word_clocks_unknown_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'unknown'}, disposition_enabled=False)
        is False
    )


def test_b90_c01588_word_clocks_unknown_2_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'unknown'}, 2, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01589_word_clocks_unknown_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'unknown'}, disposition_enabled=True) is False
    )


def test_b90_c01590_word_clocks_unknown_2_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'unknown'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01591_word_clocks_unknown_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'unknown'}, disposition_enabled=False)
        is False
    )


def test_b90_c01592_word_clocks_unknown_7_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'unknown'}, 7, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01593_word_clocks_unknown_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'unknown'}, disposition_enabled=True) is False
    )


def test_b90_c01594_word_clocks_unknown_7_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'unknown'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01595_word_clocks_unknown_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'unknown'}, disposition_enabled=False)
        is False
    )


def test_b90_c01596_word_clocks_unknown_99_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'unknown'}, 99, 'true')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01597_word_clocks_unknown_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'unknown'}, disposition_enabled=True) is False
    )


def test_b90_c01598_word_clocks_unknown_99_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'unknown'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01599_word_clocks_unknown_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'unknown'}, disposition_enabled=False)
        is False
    )


def test_b90_c01600_word_clocks_unknown_evidence():
    assert transient_failure_evidence('word_clocks', 'unknown') == {'stage': 'word_clocks', 'reason': 'unknown'}


def test_b90_c01601_word_clocks_unknown_validator():
    try:
        validate_worker_failure({'stage': 'word_clocks', 'reason': 'unknown'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is False


def test_b90_c01602_word_clocks_unsupported_language_1_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'unsupported_language'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01603_word_clocks_unsupported_language_1_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'unsupported_language'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01604_word_clocks_unsupported_language_1_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'unsupported_language'}, 1, 'false')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01605_word_clocks_unsupported_language_1_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01606_word_clocks_unsupported_language_2_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'unsupported_language'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01607_word_clocks_unsupported_language_2_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'unsupported_language'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01608_word_clocks_unsupported_language_2_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'unsupported_language'}, 2, 'false')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01609_word_clocks_unsupported_language_2_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01610_word_clocks_unsupported_language_7_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'unsupported_language'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01611_word_clocks_unsupported_language_7_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'unsupported_language'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01612_word_clocks_unsupported_language_7_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'unsupported_language'}, 7, 'false')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01613_word_clocks_unsupported_language_7_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01614_word_clocks_unsupported_language_99_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'unsupported_language'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01615_word_clocks_unsupported_language_99_true_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'unsupported_language'}, disposition_enabled=True
        )
        is False
    )


def test_b90_c01616_word_clocks_unsupported_language_99_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'unsupported_language'}, 99, 'false')
    assert ('INFO', True) in [(level, 'event=batch_language_guard' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01617_word_clocks_unsupported_language_99_false_predicate():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_b90_c01618_word_clocks_unsupported_language_evidence():
    assert transient_failure_evidence('word_clocks', 'unsupported_language') == {
        'stage': 'word_clocks',
        'reason': 'unsupported_language',
    }


def test_b90_c01619_word_clocks_unsupported_language_validator():
    try:
        validate_worker_failure({'stage': 'word_clocks', 'reason': 'unsupported_language'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01620_word_clocks_vad_bounds_1_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'vad_bounds'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01621_word_clocks_vad_bounds_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_bounds'}, disposition_enabled=True)
        is True
    )


def test_b90_c01622_word_clocks_vad_bounds_1_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'vad_bounds'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01623_word_clocks_vad_bounds_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_bounds'}, disposition_enabled=False)
        is False
    )


def test_b90_c01624_word_clocks_vad_bounds_2_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'vad_bounds'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01625_word_clocks_vad_bounds_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_bounds'}, disposition_enabled=True)
        is True
    )


def test_b90_c01626_word_clocks_vad_bounds_2_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'vad_bounds'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01627_word_clocks_vad_bounds_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_bounds'}, disposition_enabled=False)
        is False
    )


def test_b90_c01628_word_clocks_vad_bounds_7_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'vad_bounds'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01629_word_clocks_vad_bounds_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_bounds'}, disposition_enabled=True)
        is True
    )


def test_b90_c01630_word_clocks_vad_bounds_7_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'vad_bounds'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01631_word_clocks_vad_bounds_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_bounds'}, disposition_enabled=False)
        is False
    )


def test_b90_c01632_word_clocks_vad_bounds_99_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'vad_bounds'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01633_word_clocks_vad_bounds_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_bounds'}, disposition_enabled=True)
        is True
    )


def test_b90_c01634_word_clocks_vad_bounds_99_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'vad_bounds'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01635_word_clocks_vad_bounds_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_bounds'}, disposition_enabled=False)
        is False
    )


def test_b90_c01636_word_clocks_vad_bounds_evidence():
    assert transient_failure_evidence('word_clocks', 'vad_bounds') == {'stage': 'word_clocks', 'reason': 'vad_bounds'}


def test_b90_c01637_word_clocks_vad_bounds_validator():
    try:
        validate_worker_failure({'stage': 'word_clocks', 'reason': 'vad_bounds'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01638_word_clocks_vad_nonfinite_1_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'vad_nonfinite'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01639_word_clocks_vad_nonfinite_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_b90_c01640_word_clocks_vad_nonfinite_1_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'vad_nonfinite'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01641_word_clocks_vad_nonfinite_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_nonfinite'}, disposition_enabled=False)
        is False
    )


def test_b90_c01642_word_clocks_vad_nonfinite_2_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'vad_nonfinite'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01643_word_clocks_vad_nonfinite_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_b90_c01644_word_clocks_vad_nonfinite_2_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'vad_nonfinite'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01645_word_clocks_vad_nonfinite_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_nonfinite'}, disposition_enabled=False)
        is False
    )


def test_b90_c01646_word_clocks_vad_nonfinite_7_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'vad_nonfinite'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01647_word_clocks_vad_nonfinite_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_b90_c01648_word_clocks_vad_nonfinite_7_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'vad_nonfinite'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01649_word_clocks_vad_nonfinite_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_nonfinite'}, disposition_enabled=False)
        is False
    )


def test_b90_c01650_word_clocks_vad_nonfinite_99_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'vad_nonfinite'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01651_word_clocks_vad_nonfinite_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_b90_c01652_word_clocks_vad_nonfinite_99_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'vad_nonfinite'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01653_word_clocks_vad_nonfinite_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_nonfinite'}, disposition_enabled=False)
        is False
    )


def test_b90_c01654_word_clocks_vad_nonfinite_evidence():
    assert transient_failure_evidence('word_clocks', 'vad_nonfinite') == {
        'stage': 'word_clocks',
        'reason': 'vad_nonfinite',
    }


def test_b90_c01655_word_clocks_vad_nonfinite_validator():
    try:
        validate_worker_failure({'stage': 'word_clocks', 'reason': 'vad_nonfinite'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01656_word_clocks_vad_order_1_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'vad_order'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01657_word_clocks_vad_order_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_order'}, disposition_enabled=True)
        is True
    )


def test_b90_c01658_word_clocks_vad_order_1_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'vad_order'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01659_word_clocks_vad_order_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_order'}, disposition_enabled=False)
        is False
    )


def test_b90_c01660_word_clocks_vad_order_2_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'vad_order'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01661_word_clocks_vad_order_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_order'}, disposition_enabled=True)
        is True
    )


def test_b90_c01662_word_clocks_vad_order_2_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'vad_order'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01663_word_clocks_vad_order_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_order'}, disposition_enabled=False)
        is False
    )


def test_b90_c01664_word_clocks_vad_order_7_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'vad_order'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01665_word_clocks_vad_order_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_order'}, disposition_enabled=True)
        is True
    )


def test_b90_c01666_word_clocks_vad_order_7_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'vad_order'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01667_word_clocks_vad_order_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_order'}, disposition_enabled=False)
        is False
    )


def test_b90_c01668_word_clocks_vad_order_99_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'vad_order'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01669_word_clocks_vad_order_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_order'}, disposition_enabled=True)
        is True
    )


def test_b90_c01670_word_clocks_vad_order_99_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'vad_order'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01671_word_clocks_vad_order_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_order'}, disposition_enabled=False)
        is False
    )


def test_b90_c01672_word_clocks_vad_order_evidence():
    assert transient_failure_evidence('word_clocks', 'vad_order') == {'stage': 'word_clocks', 'reason': 'vad_order'}


def test_b90_c01673_word_clocks_vad_order_validator():
    try:
        validate_worker_failure({'stage': 'word_clocks', 'reason': 'vad_order'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01674_word_clocks_word_clock_1_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'word_clock'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01675_word_clocks_word_clock_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_clock'}, disposition_enabled=True)
        is True
    )


def test_b90_c01676_word_clocks_word_clock_1_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'word_clock'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01677_word_clocks_word_clock_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_clock'}, disposition_enabled=False)
        is False
    )


def test_b90_c01678_word_clocks_word_clock_2_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'word_clock'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01679_word_clocks_word_clock_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_clock'}, disposition_enabled=True)
        is True
    )


def test_b90_c01680_word_clocks_word_clock_2_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'word_clock'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01681_word_clocks_word_clock_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_clock'}, disposition_enabled=False)
        is False
    )


def test_b90_c01682_word_clocks_word_clock_7_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'word_clock'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01683_word_clocks_word_clock_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_clock'}, disposition_enabled=True)
        is True
    )


def test_b90_c01684_word_clocks_word_clock_7_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'word_clock'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01685_word_clocks_word_clock_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_clock'}, disposition_enabled=False)
        is False
    )


def test_b90_c01686_word_clocks_word_clock_99_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'word_clock'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01687_word_clocks_word_clock_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_clock'}, disposition_enabled=True)
        is True
    )


def test_b90_c01688_word_clocks_word_clock_99_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'word_clock'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01689_word_clocks_word_clock_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_clock'}, disposition_enabled=False)
        is False
    )


def test_b90_c01690_word_clocks_word_clock_evidence():
    assert transient_failure_evidence('word_clocks', 'word_clock') == {'stage': 'word_clocks', 'reason': 'word_clock'}


def test_b90_c01691_word_clocks_word_clock_validator():
    try:
        validate_worker_failure({'stage': 'word_clocks', 'reason': 'word_clock'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01692_word_clocks_word_sequence_1_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'word_sequence'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01693_word_clocks_word_sequence_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_b90_c01694_word_clocks_word_sequence_1_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'word_sequence'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01695_word_clocks_word_sequence_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_sequence'}, disposition_enabled=False)
        is False
    )


def test_b90_c01696_word_clocks_word_sequence_2_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'word_sequence'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01697_word_clocks_word_sequence_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_b90_c01698_word_clocks_word_sequence_2_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'word_sequence'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01699_word_clocks_word_sequence_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_sequence'}, disposition_enabled=False)
        is False
    )


def test_b90_c01700_word_clocks_word_sequence_7_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'word_sequence'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01701_word_clocks_word_sequence_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_b90_c01702_word_clocks_word_sequence_7_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'word_sequence'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01703_word_clocks_word_sequence_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_sequence'}, disposition_enabled=False)
        is False
    )


def test_b90_c01704_word_clocks_word_sequence_99_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'word_sequence'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01705_word_clocks_word_sequence_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_b90_c01706_word_clocks_word_sequence_99_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'word_sequence'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01707_word_clocks_word_sequence_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_sequence'}, disposition_enabled=False)
        is False
    )


def test_b90_c01708_word_clocks_word_sequence_evidence():
    assert transient_failure_evidence('word_clocks', 'word_sequence') == {
        'stage': 'word_clocks',
        'reason': 'word_sequence',
    }


def test_b90_c01709_word_clocks_word_sequence_validator():
    try:
        validate_worker_failure({'stage': 'word_clocks', 'reason': 'word_sequence'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True


def test_b90_c01710_word_clocks_word_shape_1_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'word_shape'}, 1, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01711_word_clocks_word_shape_1_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_shape'}, disposition_enabled=True)
        is True
    )


def test_b90_c01712_word_clocks_word_shape_1_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'word_shape'}, 1, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01713_word_clocks_word_shape_1_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_shape'}, disposition_enabled=False)
        is False
    )


def test_b90_c01714_word_clocks_word_shape_2_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'word_shape'}, 2, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01715_word_clocks_word_shape_2_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_shape'}, disposition_enabled=True)
        is True
    )


def test_b90_c01716_word_clocks_word_shape_2_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'word_shape'}, 2, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01717_word_clocks_word_shape_2_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_shape'}, disposition_enabled=False)
        is False
    )


def test_b90_c01718_word_clocks_word_shape_7_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'word_shape'}, 7, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01719_word_clocks_word_shape_7_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_shape'}, disposition_enabled=True)
        is True
    )


def test_b90_c01720_word_clocks_word_shape_7_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'word_shape'}, 7, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01721_word_clocks_word_shape_7_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_shape'}, disposition_enabled=False)
        is False
    )


def test_b90_c01722_word_clocks_word_shape_99_true():
    lines = _drive({'stage': 'word_clocks', 'reason': 'word_shape'}, 99, 'true')
    assert ('INFO', True) in [(level, 'event=batch_validation_disposition' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01723_word_clocks_word_shape_99_true_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_shape'}, disposition_enabled=True)
        is True
    )


def test_b90_c01724_word_clocks_word_shape_99_false():
    lines = _drive({'stage': 'word_clocks', 'reason': 'word_shape'}, 99, 'false')
    assert ('ERROR', True) in [(level, 'event=batch_quarantined' in message) for level, message in lines]
    assert any('outcome=held reason=awaiting_fenced_recovery' in message for _, message in lines)


def test_b90_c01725_word_clocks_word_shape_99_false_predicate():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_shape'}, disposition_enabled=False)
        is False
    )


def test_b90_c01726_word_clocks_word_shape_evidence():
    assert transient_failure_evidence('word_clocks', 'word_shape') == {'stage': 'word_clocks', 'reason': 'word_shape'}


def test_b90_c01727_word_clocks_word_shape_validator():
    try:
        validate_worker_failure({'stage': 'word_clocks', 'reason': 'word_shape'})
        accepted = True
    except ValueError:
        accepted = False
    assert accepted is True
