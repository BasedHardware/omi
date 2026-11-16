"""Generated fetch-decode payload-poison custody band test_fetch_payload_custody_grid_band_02.

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

from database.firestore_transaction_retry import FirestoreContentionExhausted
from diarizer.batch_pipeline import (
    DecodedDurationMismatch,
    decode_payload_failure_reason,
    decode_payload_is_deterministic,
)
from utils.batch_pipeline.audio import StagedAudioInvalid
from utils.batch_pipeline.artifacts import StagedArtifactInvalid
from utils.batch_pipeline.source_audio import (
    InvalidRetainedManifest,
    RetainedAudioInvalid,
    RetainedAudioOutsideAdmittedSource,
)
from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason
from utils.observability.reasons import WorkerValidationReason

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


def test_b02_c00000():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'persist', 'decode_payload_invalid') == None


def test_b02_c00001():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c00002():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'persist', 'empty_asr') == None


def test_b02_c00003():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'persist', 'no_owned_words') == None


def test_b02_c00004():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'persist', 'outside_admitted_source') == None


def test_b02_c00005():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'persist', 'persist_payload_invalid') == None


def test_b02_c00006():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'persist', 'retained_audio_invalid') == None


def test_b02_c00007():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'persist', 'staged_audio_invalid') == None


def test_b02_c00008():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'persist', 'unknown') == None


def test_b02_c00009():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'persist', 'unsupported_language') == None


def test_b02_c00010():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'persist', 'vad_bounds') == None


def test_b02_c00011():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'persist', 'vad_nonfinite') == None


def test_b02_c00012():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'persist', 'vad_order') == None


def test_b02_c00013():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'persist', 'word_clock') == None


def test_b02_c00014():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'persist', 'word_sequence') == None


def test_b02_c00015():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'persist', 'word_shape') == None


def test_b02_c00016():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'persist', 'unclassified') == None


def test_b02_c00017():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c00018():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'vad_windows', 'decoded_duration_mismatch') == None


def test_b02_c00019():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'vad_windows', 'empty_asr') == None


def test_b02_c00020():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'vad_windows', 'no_owned_words') == None


def test_b02_c00021():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'vad_windows', 'outside_admitted_source') == None


def test_b02_c00022():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'vad_windows', 'persist_payload_invalid') == None


def test_b02_c00023():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c00024():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c00025():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'vad_windows', 'unknown') == None


def test_b02_c00026():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'vad_windows', 'unsupported_language') == None


def test_b02_c00027():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'vad_windows', 'vad_bounds') == None


def test_b02_c00028():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c00029():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'vad_windows', 'vad_order') == None


def test_b02_c00030():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'vad_windows', 'word_clock') == None


def test_b02_c00031():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'vad_windows', 'word_sequence') == None


def test_b02_c00032():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'vad_windows', 'word_shape') == None


def test_b02_c00033():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'vad_windows', 'unclassified') == None


def test_b02_c00034():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c00035():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'word_clocks', 'decoded_duration_mismatch') == None


def test_b02_c00036():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'word_clocks', 'empty_asr') == None


def test_b02_c00037():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'word_clocks', 'no_owned_words') == None


def test_b02_c00038():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'word_clocks', 'outside_admitted_source') == None


def test_b02_c00039():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'word_clocks', 'persist_payload_invalid') == None


def test_b02_c00040():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c00041():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c00042():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'word_clocks', 'unknown') == None


def test_b02_c00043():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'word_clocks', 'unsupported_language') == None


def test_b02_c00044():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'word_clocks', 'vad_bounds') == None


def test_b02_c00045():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c00046():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'word_clocks', 'vad_order') == None


def test_b02_c00047():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'word_clocks', 'word_clock') == None


def test_b02_c00048():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'word_clocks', 'word_sequence') == None


def test_b02_c00049():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'word_clocks', 'word_shape') == None


def test_b02_c00050():
    assert decode_payload_failure_reason(_make('api_Unauthorized'), 'word_clocks', 'unclassified') == None


def test_b02_c00051():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'asr_recovery', 'decode_payload_invalid') == None


def test_b02_c00052():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'asr_recovery', 'decoded_duration_mismatch') == None


def test_b02_c00053():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'asr_recovery', 'empty_asr') == None


def test_b02_c00054():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c00055():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'asr_recovery', 'outside_admitted_source') == None


def test_b02_c00056():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'asr_recovery', 'persist_payload_invalid') == None


def test_b02_c00057():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'asr_recovery', 'retained_audio_invalid') == None


def test_b02_c00058():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c00059():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'asr_recovery', 'unknown') == None


def test_b02_c00060():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c00061():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c00062():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c00063():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'asr_recovery', 'vad_order') == None


def test_b02_c00064():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'asr_recovery', 'word_clock') == None


def test_b02_c00065():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'asr_recovery', 'word_sequence') == None


def test_b02_c00066():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'asr_recovery', 'word_shape') == None


def test_b02_c00067():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'asr_recovery', 'unclassified') == None


def test_b02_c00068():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'assemble_words', 'decode_payload_invalid') == None


def test_b02_c00069():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'assemble_words', 'decoded_duration_mismatch') == None


def test_b02_c00070():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'assemble_words', 'empty_asr') == None


def test_b02_c00071():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'assemble_words', 'no_owned_words') == None


def test_b02_c00072():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'assemble_words', 'outside_admitted_source') == None


def test_b02_c00073():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'assemble_words', 'persist_payload_invalid') == None


def test_b02_c00074():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'assemble_words', 'retained_audio_invalid') == None


def test_b02_c00075():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'assemble_words', 'staged_audio_invalid') == None


def test_b02_c00076():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'assemble_words', 'unknown') == None


def test_b02_c00077():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'assemble_words', 'unsupported_language') == None


def test_b02_c00078():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'assemble_words', 'vad_bounds') == None


def test_b02_c00079():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c00080():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'assemble_words', 'vad_order') == None


def test_b02_c00081():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'assemble_words', 'word_clock') == None


def test_b02_c00082():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'assemble_words', 'word_sequence') == None


def test_b02_c00083():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'assemble_words', 'word_shape') == None


def test_b02_c00084():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'assemble_words', 'unclassified') == None


def test_b02_c00085():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'fetch_decode', 'decode_payload_invalid') == None


def test_b02_c00086():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'fetch_decode', 'decoded_duration_mismatch') == None


def test_b02_c00087():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'fetch_decode', 'empty_asr') == None


def test_b02_c00088():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c00089():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'fetch_decode', 'outside_admitted_source') == None


def test_b02_c00090():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'fetch_decode', 'persist_payload_invalid') == None


def test_b02_c00091():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'fetch_decode', 'retained_audio_invalid') == None


def test_b02_c00092():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c00093():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'fetch_decode', 'unknown') == None


def test_b02_c00094():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c00095():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c00096():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c00097():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'fetch_decode', 'vad_order') == None


def test_b02_c00098():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'fetch_decode', 'word_clock') == None


def test_b02_c00099():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'fetch_decode', 'word_sequence') == None


def test_b02_c00100():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'fetch_decode', 'word_shape') == None


def test_b02_c00101():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'fetch_decode', 'unclassified') == None


def test_b02_c00102():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'persist', 'decode_payload_invalid') == None


def test_b02_c00103():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c00104():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'persist', 'empty_asr') == None


def test_b02_c00105():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'persist', 'no_owned_words') == None


def test_b02_c00106():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'persist', 'outside_admitted_source') == None


def test_b02_c00107():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'persist', 'persist_payload_invalid') == None


def test_b02_c00108():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'persist', 'retained_audio_invalid') == None


def test_b02_c00109():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'persist', 'staged_audio_invalid') == None


def test_b02_c00110():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'persist', 'unknown') == None


def test_b02_c00111():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'persist', 'unsupported_language') == None


def test_b02_c00112():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'persist', 'vad_bounds') == None


def test_b02_c00113():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'persist', 'vad_nonfinite') == None


def test_b02_c00114():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'persist', 'vad_order') == None


def test_b02_c00115():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'persist', 'word_clock') == None


def test_b02_c00116():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'persist', 'word_sequence') == None


def test_b02_c00117():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'persist', 'word_shape') == None


def test_b02_c00118():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'persist', 'unclassified') == None


def test_b02_c00119():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c00120():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'vad_windows', 'decoded_duration_mismatch') == None


def test_b02_c00121():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'vad_windows', 'empty_asr') == None


def test_b02_c00122():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'vad_windows', 'no_owned_words') == None


def test_b02_c00123():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'vad_windows', 'outside_admitted_source') == None


def test_b02_c00124():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'vad_windows', 'persist_payload_invalid') == None


def test_b02_c00125():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c00126():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c00127():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'vad_windows', 'unknown') == None


def test_b02_c00128():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'vad_windows', 'unsupported_language') == None


def test_b02_c00129():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'vad_windows', 'vad_bounds') == None


def test_b02_c00130():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c00131():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'vad_windows', 'vad_order') == None


def test_b02_c00132():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'vad_windows', 'word_clock') == None


def test_b02_c00133():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'vad_windows', 'word_sequence') == None


def test_b02_c00134():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'vad_windows', 'word_shape') == None


def test_b02_c00135():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'vad_windows', 'unclassified') == None


def test_b02_c00136():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c00137():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'word_clocks', 'decoded_duration_mismatch') == None


def test_b02_c00138():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'word_clocks', 'empty_asr') == None


def test_b02_c00139():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'word_clocks', 'no_owned_words') == None


def test_b02_c00140():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'word_clocks', 'outside_admitted_source') == None


def test_b02_c00141():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'word_clocks', 'persist_payload_invalid') == None


def test_b02_c00142():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c00143():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c00144():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'word_clocks', 'unknown') == None


def test_b02_c00145():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'word_clocks', 'unsupported_language') == None


def test_b02_c00146():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'word_clocks', 'vad_bounds') == None


def test_b02_c00147():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c00148():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'word_clocks', 'vad_order') == None


def test_b02_c00149():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'word_clocks', 'word_clock') == None


def test_b02_c00150():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'word_clocks', 'word_sequence') == None


def test_b02_c00151():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'word_clocks', 'word_shape') == None


def test_b02_c00152():
    assert decode_payload_failure_reason(_make('api_Unknown'), 'word_clocks', 'unclassified') == None


def test_b02_c00153():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'asr_recovery', 'decode_payload_invalid') == None


def test_b02_c00154():
    assert (
        decode_payload_failure_reason(_make('b_ArithmeticError'), 'asr_recovery', 'decoded_duration_mismatch') == None
    )


def test_b02_c00155():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'asr_recovery', 'empty_asr') == None


def test_b02_c00156():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c00157():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'asr_recovery', 'outside_admitted_source') == None


def test_b02_c00158():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'asr_recovery', 'persist_payload_invalid') == None


def test_b02_c00159():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'asr_recovery', 'retained_audio_invalid') == None


def test_b02_c00160():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c00161():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'asr_recovery', 'unknown') == None


def test_b02_c00162():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c00163():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c00164():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c00165():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'asr_recovery', 'vad_order') == None


def test_b02_c00166():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'asr_recovery', 'word_clock') == None


def test_b02_c00167():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'asr_recovery', 'word_sequence') == None


def test_b02_c00168():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'asr_recovery', 'word_shape') == None


def test_b02_c00169():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'asr_recovery', 'unclassified') == None


def test_b02_c00170():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'assemble_words', 'decode_payload_invalid') == None


def test_b02_c00171():
    assert (
        decode_payload_failure_reason(_make('b_ArithmeticError'), 'assemble_words', 'decoded_duration_mismatch') == None
    )


def test_b02_c00172():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'assemble_words', 'empty_asr') == None


def test_b02_c00173():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'assemble_words', 'no_owned_words') == None


def test_b02_c00174():
    assert (
        decode_payload_failure_reason(_make('b_ArithmeticError'), 'assemble_words', 'outside_admitted_source') == None
    )


def test_b02_c00175():
    assert (
        decode_payload_failure_reason(_make('b_ArithmeticError'), 'assemble_words', 'persist_payload_invalid') == None
    )


def test_b02_c00176():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'assemble_words', 'retained_audio_invalid') == None


def test_b02_c00177():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'assemble_words', 'staged_audio_invalid') == None


def test_b02_c00178():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'assemble_words', 'unknown') == None


def test_b02_c00179():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'assemble_words', 'unsupported_language') == None


def test_b02_c00180():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'assemble_words', 'vad_bounds') == None


def test_b02_c00181():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c00182():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'assemble_words', 'vad_order') == None


def test_b02_c00183():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'assemble_words', 'word_clock') == None


def test_b02_c00184():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'assemble_words', 'word_sequence') == None


def test_b02_c00185():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'assemble_words', 'word_shape') == None


def test_b02_c00186():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'assemble_words', 'unclassified') == None


def test_b02_c00187():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'fetch_decode', 'decode_payload_invalid') == None


def test_b02_c00188():
    assert (
        decode_payload_failure_reason(_make('b_ArithmeticError'), 'fetch_decode', 'decoded_duration_mismatch') == None
    )


def test_b02_c00189():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'fetch_decode', 'empty_asr') == None


def test_b02_c00190():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c00191():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'fetch_decode', 'outside_admitted_source') == None


def test_b02_c00192():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'fetch_decode', 'persist_payload_invalid') == None


def test_b02_c00193():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'fetch_decode', 'retained_audio_invalid') == None


def test_b02_c00194():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c00195():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'fetch_decode', 'unknown') == None


def test_b02_c00196():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c00197():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c00198():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c00199():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'fetch_decode', 'vad_order') == None


def test_b02_c00200():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'fetch_decode', 'word_clock') == None


def test_b02_c00201():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'fetch_decode', 'word_sequence') == None


def test_b02_c00202():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'fetch_decode', 'word_shape') == None


def test_b02_c00203():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'fetch_decode', 'unclassified') == None


def test_b02_c00204():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'persist', 'decode_payload_invalid') == None


def test_b02_c00205():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c00206():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'persist', 'empty_asr') == None


def test_b02_c00207():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'persist', 'no_owned_words') == None


def test_b02_c00208():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'persist', 'outside_admitted_source') == None


def test_b02_c00209():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'persist', 'persist_payload_invalid') == None


def test_b02_c00210():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'persist', 'retained_audio_invalid') == None


def test_b02_c00211():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'persist', 'staged_audio_invalid') == None


def test_b02_c00212():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'persist', 'unknown') == None


def test_b02_c00213():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'persist', 'unsupported_language') == None


def test_b02_c00214():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'persist', 'vad_bounds') == None


def test_b02_c00215():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'persist', 'vad_nonfinite') == None


def test_b02_c00216():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'persist', 'vad_order') == None


def test_b02_c00217():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'persist', 'word_clock') == None


def test_b02_c00218():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'persist', 'word_sequence') == None


def test_b02_c00219():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'persist', 'word_shape') == None


def test_b02_c00220():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'persist', 'unclassified') == None


def test_b02_c00221():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c00222():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'vad_windows', 'decoded_duration_mismatch') == None


def test_b02_c00223():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'vad_windows', 'empty_asr') == None


def test_b02_c00224():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'vad_windows', 'no_owned_words') == None


def test_b02_c00225():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'vad_windows', 'outside_admitted_source') == None


def test_b02_c00226():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'vad_windows', 'persist_payload_invalid') == None


def test_b02_c00227():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c00228():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c00229():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'vad_windows', 'unknown') == None


def test_b02_c00230():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'vad_windows', 'unsupported_language') == None


def test_b02_c00231():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'vad_windows', 'vad_bounds') == None


def test_b02_c00232():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c00233():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'vad_windows', 'vad_order') == None


def test_b02_c00234():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'vad_windows', 'word_clock') == None


def test_b02_c00235():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'vad_windows', 'word_sequence') == None


def test_b02_c00236():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'vad_windows', 'word_shape') == None


def test_b02_c00237():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'vad_windows', 'unclassified') == None


def test_b02_c00238():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c00239():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'word_clocks', 'decoded_duration_mismatch') == None


def test_b02_c00240():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'word_clocks', 'empty_asr') == None


def test_b02_c00241():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'word_clocks', 'no_owned_words') == None


def test_b02_c00242():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'word_clocks', 'outside_admitted_source') == None


def test_b02_c00243():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'word_clocks', 'persist_payload_invalid') == None


def test_b02_c00244():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c00245():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c00246():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'word_clocks', 'unknown') == None


def test_b02_c00247():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'word_clocks', 'unsupported_language') == None


def test_b02_c00248():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'word_clocks', 'vad_bounds') == None


def test_b02_c00249():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c00250():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'word_clocks', 'vad_order') == None


def test_b02_c00251():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'word_clocks', 'word_clock') == None


def test_b02_c00252():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'word_clocks', 'word_sequence') == None


def test_b02_c00253():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'word_clocks', 'word_shape') == None


def test_b02_c00254():
    assert decode_payload_failure_reason(_make('b_ArithmeticError'), 'word_clocks', 'unclassified') == None


def test_b02_c00255():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'asr_recovery', 'decode_payload_invalid') == None


def test_b02_c00256():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'asr_recovery', 'decoded_duration_mismatch') == None


def test_b02_c00257():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'asr_recovery', 'empty_asr') == None


def test_b02_c00258():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c00259():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'asr_recovery', 'outside_admitted_source') == None


def test_b02_c00260():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'asr_recovery', 'persist_payload_invalid') == None


def test_b02_c00261():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'asr_recovery', 'retained_audio_invalid') == None


def test_b02_c00262():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c00263():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'asr_recovery', 'unknown') == None


def test_b02_c00264():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c00265():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c00266():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c00267():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'asr_recovery', 'vad_order') == None


def test_b02_c00268():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'asr_recovery', 'word_clock') == None


def test_b02_c00269():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'asr_recovery', 'word_sequence') == None


def test_b02_c00270():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'asr_recovery', 'word_shape') == None


def test_b02_c00271():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'asr_recovery', 'unclassified') == None


def test_b02_c00272():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'assemble_words', 'decode_payload_invalid') == None


def test_b02_c00273():
    assert (
        decode_payload_failure_reason(_make('b_AssertionError'), 'assemble_words', 'decoded_duration_mismatch') == None
    )


def test_b02_c00274():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'assemble_words', 'empty_asr') == None


def test_b02_c00275():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'assemble_words', 'no_owned_words') == None


def test_b02_c00276():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'assemble_words', 'outside_admitted_source') == None


def test_b02_c00277():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'assemble_words', 'persist_payload_invalid') == None


def test_b02_c00278():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'assemble_words', 'retained_audio_invalid') == None


def test_b02_c00279():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'assemble_words', 'staged_audio_invalid') == None


def test_b02_c00280():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'assemble_words', 'unknown') == None


def test_b02_c00281():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'assemble_words', 'unsupported_language') == None


def test_b02_c00282():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'assemble_words', 'vad_bounds') == None


def test_b02_c00283():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c00284():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'assemble_words', 'vad_order') == None


def test_b02_c00285():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'assemble_words', 'word_clock') == None


def test_b02_c00286():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'assemble_words', 'word_sequence') == None


def test_b02_c00287():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'assemble_words', 'word_shape') == None


def test_b02_c00288():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'assemble_words', 'unclassified') == None


def test_b02_c00289():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'fetch_decode', 'decode_payload_invalid') == None


def test_b02_c00290():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'fetch_decode', 'decoded_duration_mismatch') == None


def test_b02_c00291():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'fetch_decode', 'empty_asr') == None


def test_b02_c00292():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c00293():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'fetch_decode', 'outside_admitted_source') == None


def test_b02_c00294():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'fetch_decode', 'persist_payload_invalid') == None


def test_b02_c00295():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'fetch_decode', 'retained_audio_invalid') == None


def test_b02_c00296():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c00297():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'fetch_decode', 'unknown') == None


def test_b02_c00298():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c00299():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c00300():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c00301():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'fetch_decode', 'vad_order') == None


def test_b02_c00302():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'fetch_decode', 'word_clock') == None


def test_b02_c00303():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'fetch_decode', 'word_sequence') == None


def test_b02_c00304():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'fetch_decode', 'word_shape') == None


def test_b02_c00305():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'fetch_decode', 'unclassified') == None


def test_b02_c00306():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'persist', 'decode_payload_invalid') == None


def test_b02_c00307():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c00308():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'persist', 'empty_asr') == None


def test_b02_c00309():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'persist', 'no_owned_words') == None


def test_b02_c00310():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'persist', 'outside_admitted_source') == None


def test_b02_c00311():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'persist', 'persist_payload_invalid') == None


def test_b02_c00312():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'persist', 'retained_audio_invalid') == None


def test_b02_c00313():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'persist', 'staged_audio_invalid') == None


def test_b02_c00314():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'persist', 'unknown') == None


def test_b02_c00315():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'persist', 'unsupported_language') == None


def test_b02_c00316():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'persist', 'vad_bounds') == None


def test_b02_c00317():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'persist', 'vad_nonfinite') == None


def test_b02_c00318():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'persist', 'vad_order') == None


def test_b02_c00319():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'persist', 'word_clock') == None


def test_b02_c00320():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'persist', 'word_sequence') == None


def test_b02_c00321():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'persist', 'word_shape') == None


def test_b02_c00322():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'persist', 'unclassified') == None


def test_b02_c00323():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c00324():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'vad_windows', 'decoded_duration_mismatch') == None


def test_b02_c00325():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'vad_windows', 'empty_asr') == None


def test_b02_c00326():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'vad_windows', 'no_owned_words') == None


def test_b02_c00327():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'vad_windows', 'outside_admitted_source') == None


def test_b02_c00328():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'vad_windows', 'persist_payload_invalid') == None


def test_b02_c00329():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c00330():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c00331():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'vad_windows', 'unknown') == None


def test_b02_c00332():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'vad_windows', 'unsupported_language') == None


def test_b02_c00333():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'vad_windows', 'vad_bounds') == None


def test_b02_c00334():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c00335():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'vad_windows', 'vad_order') == None


def test_b02_c00336():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'vad_windows', 'word_clock') == None


def test_b02_c00337():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'vad_windows', 'word_sequence') == None


def test_b02_c00338():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'vad_windows', 'word_shape') == None


def test_b02_c00339():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'vad_windows', 'unclassified') == None


def test_b02_c00340():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c00341():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'word_clocks', 'decoded_duration_mismatch') == None


def test_b02_c00342():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'word_clocks', 'empty_asr') == None


def test_b02_c00343():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'word_clocks', 'no_owned_words') == None


def test_b02_c00344():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'word_clocks', 'outside_admitted_source') == None


def test_b02_c00345():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'word_clocks', 'persist_payload_invalid') == None


def test_b02_c00346():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c00347():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c00348():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'word_clocks', 'unknown') == None


def test_b02_c00349():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'word_clocks', 'unsupported_language') == None


def test_b02_c00350():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'word_clocks', 'vad_bounds') == None


def test_b02_c00351():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c00352():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'word_clocks', 'vad_order') == None


def test_b02_c00353():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'word_clocks', 'word_clock') == None


def test_b02_c00354():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'word_clocks', 'word_sequence') == None


def test_b02_c00355():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'word_clocks', 'word_shape') == None


def test_b02_c00356():
    assert decode_payload_failure_reason(_make('b_AssertionError'), 'word_clocks', 'unclassified') == None


def test_b02_c00357():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'asr_recovery', 'decode_payload_invalid') == None


def test_b02_c00358():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'asr_recovery', 'decoded_duration_mismatch') == None


def test_b02_c00359():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'asr_recovery', 'empty_asr') == None


def test_b02_c00360():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c00361():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'asr_recovery', 'outside_admitted_source') == None


def test_b02_c00362():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'asr_recovery', 'persist_payload_invalid') == None


def test_b02_c00363():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'asr_recovery', 'retained_audio_invalid') == None


def test_b02_c00364():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c00365():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'asr_recovery', 'unknown') == None


def test_b02_c00366():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c00367():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c00368():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c00369():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'asr_recovery', 'vad_order') == None


def test_b02_c00370():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'asr_recovery', 'word_clock') == None


def test_b02_c00371():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'asr_recovery', 'word_sequence') == None


def test_b02_c00372():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'asr_recovery', 'word_shape') == None


def test_b02_c00373():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'asr_recovery', 'unclassified') == None


def test_b02_c00374():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'assemble_words', 'decode_payload_invalid') == None


def test_b02_c00375():
    assert (
        decode_payload_failure_reason(_make('b_AttributeError'), 'assemble_words', 'decoded_duration_mismatch') == None
    )


def test_b02_c00376():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'assemble_words', 'empty_asr') == None


def test_b02_c00377():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'assemble_words', 'no_owned_words') == None


def test_b02_c00378():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'assemble_words', 'outside_admitted_source') == None


def test_b02_c00379():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'assemble_words', 'persist_payload_invalid') == None


def test_b02_c00380():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'assemble_words', 'retained_audio_invalid') == None


def test_b02_c00381():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'assemble_words', 'staged_audio_invalid') == None


def test_b02_c00382():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'assemble_words', 'unknown') == None


def test_b02_c00383():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'assemble_words', 'unsupported_language') == None


def test_b02_c00384():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'assemble_words', 'vad_bounds') == None


def test_b02_c00385():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c00386():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'assemble_words', 'vad_order') == None


def test_b02_c00387():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'assemble_words', 'word_clock') == None


def test_b02_c00388():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'assemble_words', 'word_sequence') == None


def test_b02_c00389():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'assemble_words', 'word_shape') == None


def test_b02_c00390():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'assemble_words', 'unclassified') == None


def test_b02_c00391():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'fetch_decode', 'decode_payload_invalid') == None


def test_b02_c00392():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'fetch_decode', 'decoded_duration_mismatch') == None


def test_b02_c00393():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'fetch_decode', 'empty_asr') == None


def test_b02_c00394():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c00395():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'fetch_decode', 'outside_admitted_source') == None


def test_b02_c00396():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'fetch_decode', 'persist_payload_invalid') == None


def test_b02_c00397():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'fetch_decode', 'retained_audio_invalid') == None


def test_b02_c00398():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c00399():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'fetch_decode', 'unknown') == None


def test_b02_c00400():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c00401():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c00402():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c00403():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'fetch_decode', 'vad_order') == None


def test_b02_c00404():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'fetch_decode', 'word_clock') == None


def test_b02_c00405():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'fetch_decode', 'word_sequence') == None


def test_b02_c00406():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'fetch_decode', 'word_shape') == None


def test_b02_c00407():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'fetch_decode', 'unclassified') == None


def test_b02_c00408():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'persist', 'decode_payload_invalid') == None


def test_b02_c00409():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c00410():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'persist', 'empty_asr') == None


def test_b02_c00411():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'persist', 'no_owned_words') == None


def test_b02_c00412():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'persist', 'outside_admitted_source') == None


def test_b02_c00413():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'persist', 'persist_payload_invalid') == None


def test_b02_c00414():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'persist', 'retained_audio_invalid') == None


def test_b02_c00415():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'persist', 'staged_audio_invalid') == None


def test_b02_c00416():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'persist', 'unknown') == None


def test_b02_c00417():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'persist', 'unsupported_language') == None


def test_b02_c00418():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'persist', 'vad_bounds') == None


def test_b02_c00419():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'persist', 'vad_nonfinite') == None


def test_b02_c00420():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'persist', 'vad_order') == None


def test_b02_c00421():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'persist', 'word_clock') == None


def test_b02_c00422():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'persist', 'word_sequence') == None


def test_b02_c00423():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'persist', 'word_shape') == None


def test_b02_c00424():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'persist', 'unclassified') == None


def test_b02_c00425():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c00426():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'vad_windows', 'decoded_duration_mismatch') == None


def test_b02_c00427():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'vad_windows', 'empty_asr') == None


def test_b02_c00428():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'vad_windows', 'no_owned_words') == None


def test_b02_c00429():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'vad_windows', 'outside_admitted_source') == None


def test_b02_c00430():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'vad_windows', 'persist_payload_invalid') == None


def test_b02_c00431():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c00432():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c00433():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'vad_windows', 'unknown') == None


def test_b02_c00434():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'vad_windows', 'unsupported_language') == None


def test_b02_c00435():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'vad_windows', 'vad_bounds') == None


def test_b02_c00436():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c00437():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'vad_windows', 'vad_order') == None


def test_b02_c00438():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'vad_windows', 'word_clock') == None


def test_b02_c00439():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'vad_windows', 'word_sequence') == None


def test_b02_c00440():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'vad_windows', 'word_shape') == None


def test_b02_c00441():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'vad_windows', 'unclassified') == None


def test_b02_c00442():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c00443():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'word_clocks', 'decoded_duration_mismatch') == None


def test_b02_c00444():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'word_clocks', 'empty_asr') == None


def test_b02_c00445():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'word_clocks', 'no_owned_words') == None


def test_b02_c00446():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'word_clocks', 'outside_admitted_source') == None


def test_b02_c00447():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'word_clocks', 'persist_payload_invalid') == None


def test_b02_c00448():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c00449():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c00450():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'word_clocks', 'unknown') == None


def test_b02_c00451():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'word_clocks', 'unsupported_language') == None


def test_b02_c00452():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'word_clocks', 'vad_bounds') == None


def test_b02_c00453():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c00454():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'word_clocks', 'vad_order') == None


def test_b02_c00455():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'word_clocks', 'word_clock') == None


def test_b02_c00456():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'word_clocks', 'word_sequence') == None


def test_b02_c00457():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'word_clocks', 'word_shape') == None


def test_b02_c00458():
    assert decode_payload_failure_reason(_make('b_AttributeError'), 'word_clocks', 'unclassified') == None


def test_b02_c00459():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'asr_recovery', 'decode_payload_invalid') == None


def test_b02_c00460():
    assert (
        decode_payload_failure_reason(_make('b_BrokenPipeError'), 'asr_recovery', 'decoded_duration_mismatch') == None
    )


def test_b02_c00461():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'asr_recovery', 'empty_asr') == None


def test_b02_c00462():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c00463():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'asr_recovery', 'outside_admitted_source') == None


def test_b02_c00464():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'asr_recovery', 'persist_payload_invalid') == None


def test_b02_c00465():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'asr_recovery', 'retained_audio_invalid') == None


def test_b02_c00466():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c00467():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'asr_recovery', 'unknown') == None


def test_b02_c00468():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c00469():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c00470():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c00471():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'asr_recovery', 'vad_order') == None


def test_b02_c00472():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'asr_recovery', 'word_clock') == None


def test_b02_c00473():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'asr_recovery', 'word_sequence') == None


def test_b02_c00474():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'asr_recovery', 'word_shape') == None


def test_b02_c00475():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'asr_recovery', 'unclassified') == None


def test_b02_c00476():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'assemble_words', 'decode_payload_invalid') == None


def test_b02_c00477():
    assert (
        decode_payload_failure_reason(_make('b_BrokenPipeError'), 'assemble_words', 'decoded_duration_mismatch') == None
    )


def test_b02_c00478():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'assemble_words', 'empty_asr') == None


def test_b02_c00479():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'assemble_words', 'no_owned_words') == None


def test_b02_c00480():
    assert (
        decode_payload_failure_reason(_make('b_BrokenPipeError'), 'assemble_words', 'outside_admitted_source') == None
    )


def test_b02_c00481():
    assert (
        decode_payload_failure_reason(_make('b_BrokenPipeError'), 'assemble_words', 'persist_payload_invalid') == None
    )


def test_b02_c00482():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'assemble_words', 'retained_audio_invalid') == None


def test_b02_c00483():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'assemble_words', 'staged_audio_invalid') == None


def test_b02_c00484():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'assemble_words', 'unknown') == None


def test_b02_c00485():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'assemble_words', 'unsupported_language') == None


def test_b02_c00486():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'assemble_words', 'vad_bounds') == None


def test_b02_c00487():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c00488():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'assemble_words', 'vad_order') == None


def test_b02_c00489():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'assemble_words', 'word_clock') == None


def test_b02_c00490():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'assemble_words', 'word_sequence') == None


def test_b02_c00491():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'assemble_words', 'word_shape') == None


def test_b02_c00492():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'assemble_words', 'unclassified') == None


def test_b02_c00493():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'fetch_decode', 'decode_payload_invalid') == None


def test_b02_c00494():
    assert (
        decode_payload_failure_reason(_make('b_BrokenPipeError'), 'fetch_decode', 'decoded_duration_mismatch') == None
    )


def test_b02_c00495():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'fetch_decode', 'empty_asr') == None


def test_b02_c00496():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c00497():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'fetch_decode', 'outside_admitted_source') == None


def test_b02_c00498():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'fetch_decode', 'persist_payload_invalid') == None


def test_b02_c00499():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'fetch_decode', 'retained_audio_invalid') == None


def test_b02_c00500():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c00501():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'fetch_decode', 'unknown') == None


def test_b02_c00502():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c00503():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c00504():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c00505():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'fetch_decode', 'vad_order') == None


def test_b02_c00506():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'fetch_decode', 'word_clock') == None


def test_b02_c00507():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'fetch_decode', 'word_sequence') == None


def test_b02_c00508():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'fetch_decode', 'word_shape') == None


def test_b02_c00509():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'fetch_decode', 'unclassified') == None


def test_b02_c00510():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'persist', 'decode_payload_invalid') == None


def test_b02_c00511():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c00512():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'persist', 'empty_asr') == None


def test_b02_c00513():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'persist', 'no_owned_words') == None


def test_b02_c00514():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'persist', 'outside_admitted_source') == None


def test_b02_c00515():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'persist', 'persist_payload_invalid') == None


def test_b02_c00516():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'persist', 'retained_audio_invalid') == None


def test_b02_c00517():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'persist', 'staged_audio_invalid') == None


def test_b02_c00518():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'persist', 'unknown') == None


def test_b02_c00519():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'persist', 'unsupported_language') == None


def test_b02_c00520():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'persist', 'vad_bounds') == None


def test_b02_c00521():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'persist', 'vad_nonfinite') == None


def test_b02_c00522():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'persist', 'vad_order') == None


def test_b02_c00523():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'persist', 'word_clock') == None


def test_b02_c00524():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'persist', 'word_sequence') == None


def test_b02_c00525():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'persist', 'word_shape') == None


def test_b02_c00526():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'persist', 'unclassified') == None


def test_b02_c00527():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c00528():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'vad_windows', 'decoded_duration_mismatch') == None


def test_b02_c00529():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'vad_windows', 'empty_asr') == None


def test_b02_c00530():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'vad_windows', 'no_owned_words') == None


def test_b02_c00531():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'vad_windows', 'outside_admitted_source') == None


def test_b02_c00532():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'vad_windows', 'persist_payload_invalid') == None


def test_b02_c00533():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c00534():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c00535():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'vad_windows', 'unknown') == None


def test_b02_c00536():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'vad_windows', 'unsupported_language') == None


def test_b02_c00537():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'vad_windows', 'vad_bounds') == None


def test_b02_c00538():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c00539():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'vad_windows', 'vad_order') == None


def test_b02_c00540():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'vad_windows', 'word_clock') == None


def test_b02_c00541():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'vad_windows', 'word_sequence') == None


def test_b02_c00542():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'vad_windows', 'word_shape') == None


def test_b02_c00543():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'vad_windows', 'unclassified') == None


def test_b02_c00544():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c00545():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'word_clocks', 'decoded_duration_mismatch') == None


def test_b02_c00546():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'word_clocks', 'empty_asr') == None


def test_b02_c00547():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'word_clocks', 'no_owned_words') == None


def test_b02_c00548():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'word_clocks', 'outside_admitted_source') == None


def test_b02_c00549():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'word_clocks', 'persist_payload_invalid') == None


def test_b02_c00550():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c00551():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c00552():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'word_clocks', 'unknown') == None


def test_b02_c00553():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'word_clocks', 'unsupported_language') == None


def test_b02_c00554():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'word_clocks', 'vad_bounds') == None


def test_b02_c00555():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c00556():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'word_clocks', 'vad_order') == None


def test_b02_c00557():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'word_clocks', 'word_clock') == None


def test_b02_c00558():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'word_clocks', 'word_sequence') == None


def test_b02_c00559():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'word_clocks', 'word_shape') == None


def test_b02_c00560():
    assert decode_payload_failure_reason(_make('b_BrokenPipeError'), 'word_clocks', 'unclassified') == None


def test_b02_c00561():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'asr_recovery', 'decode_payload_invalid')
        == None
    )


def test_b02_c00562():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'asr_recovery', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c00563():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'asr_recovery', 'empty_asr') == None


def test_b02_c00564():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c00565():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'asr_recovery', 'outside_admitted_source')
        == None
    )


def test_b02_c00566():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'asr_recovery', 'persist_payload_invalid')
        == None
    )


def test_b02_c00567():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'asr_recovery', 'retained_audio_invalid')
        == None
    )


def test_b02_c00568():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'asr_recovery', 'staged_audio_invalid') == None
    )


def test_b02_c00569():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'asr_recovery', 'unknown') == None


def test_b02_c00570():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'asr_recovery', 'unsupported_language') == None
    )


def test_b02_c00571():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c00572():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c00573():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'asr_recovery', 'vad_order') == None


def test_b02_c00574():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'asr_recovery', 'word_clock') == None


def test_b02_c00575():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'asr_recovery', 'word_sequence') == None


def test_b02_c00576():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'asr_recovery', 'word_shape') == None


def test_b02_c00577():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'asr_recovery', 'unclassified') == None


def test_b02_c00578():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'assemble_words', 'decode_payload_invalid')
        == None
    )


def test_b02_c00579():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'assemble_words', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c00580():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'assemble_words', 'empty_asr') == None


def test_b02_c00581():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'assemble_words', 'no_owned_words') == None


def test_b02_c00582():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'assemble_words', 'outside_admitted_source')
        == None
    )


def test_b02_c00583():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'assemble_words', 'persist_payload_invalid')
        == None
    )


def test_b02_c00584():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'assemble_words', 'retained_audio_invalid')
        == None
    )


def test_b02_c00585():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'assemble_words', 'staged_audio_invalid')
        == None
    )


def test_b02_c00586():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'assemble_words', 'unknown') == None


def test_b02_c00587():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'assemble_words', 'unsupported_language')
        == None
    )


def test_b02_c00588():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'assemble_words', 'vad_bounds') == None


def test_b02_c00589():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c00590():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'assemble_words', 'vad_order') == None


def test_b02_c00591():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'assemble_words', 'word_clock') == None


def test_b02_c00592():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'assemble_words', 'word_sequence') == None


def test_b02_c00593():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'assemble_words', 'word_shape') == None


def test_b02_c00594():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'assemble_words', 'unclassified') == None


def test_b02_c00595():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'fetch_decode', 'decode_payload_invalid')
        == None
    )


def test_b02_c00596():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'fetch_decode', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c00597():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'fetch_decode', 'empty_asr') == None


def test_b02_c00598():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c00599():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'fetch_decode', 'outside_admitted_source')
        == None
    )


def test_b02_c00600():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'fetch_decode', 'persist_payload_invalid')
        == None
    )


def test_b02_c00601():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'fetch_decode', 'retained_audio_invalid')
        == None
    )


def test_b02_c00602():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'fetch_decode', 'staged_audio_invalid') == None
    )


def test_b02_c00603():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'fetch_decode', 'unknown') == None


def test_b02_c00604():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'fetch_decode', 'unsupported_language') == None
    )


def test_b02_c00605():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c00606():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c00607():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'fetch_decode', 'vad_order') == None


def test_b02_c00608():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'fetch_decode', 'word_clock') == None


def test_b02_c00609():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'fetch_decode', 'word_sequence') == None


def test_b02_c00610():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'fetch_decode', 'word_shape') == None


def test_b02_c00611():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'fetch_decode', 'unclassified') == None


def test_b02_c00612():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'persist', 'decode_payload_invalid') == None


def test_b02_c00613():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'persist', 'decoded_duration_mismatch') == None
    )


def test_b02_c00614():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'persist', 'empty_asr') == None


def test_b02_c00615():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'persist', 'no_owned_words') == None


def test_b02_c00616():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'persist', 'outside_admitted_source') == None
    )


def test_b02_c00617():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'persist', 'persist_payload_invalid') == None
    )


def test_b02_c00618():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'persist', 'retained_audio_invalid') == None


def test_b02_c00619():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'persist', 'staged_audio_invalid') == None


def test_b02_c00620():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'persist', 'unknown') == None


def test_b02_c00621():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'persist', 'unsupported_language') == None


def test_b02_c00622():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'persist', 'vad_bounds') == None


def test_b02_c00623():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'persist', 'vad_nonfinite') == None


def test_b02_c00624():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'persist', 'vad_order') == None


def test_b02_c00625():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'persist', 'word_clock') == None


def test_b02_c00626():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'persist', 'word_sequence') == None


def test_b02_c00627():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'persist', 'word_shape') == None


def test_b02_c00628():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'persist', 'unclassified') == None


def test_b02_c00629():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'vad_windows', 'decode_payload_invalid')
        == None
    )


def test_b02_c00630():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'vad_windows', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c00631():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'vad_windows', 'empty_asr') == None


def test_b02_c00632():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'vad_windows', 'no_owned_words') == None


def test_b02_c00633():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'vad_windows', 'outside_admitted_source')
        == None
    )


def test_b02_c00634():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'vad_windows', 'persist_payload_invalid')
        == None
    )


def test_b02_c00635():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'vad_windows', 'retained_audio_invalid')
        == None
    )


def test_b02_c00636():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'vad_windows', 'staged_audio_invalid') == None
    )


def test_b02_c00637():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'vad_windows', 'unknown') == None


def test_b02_c00638():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'vad_windows', 'unsupported_language') == None
    )


def test_b02_c00639():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'vad_windows', 'vad_bounds') == None


def test_b02_c00640():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c00641():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'vad_windows', 'vad_order') == None


def test_b02_c00642():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'vad_windows', 'word_clock') == None


def test_b02_c00643():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'vad_windows', 'word_sequence') == None


def test_b02_c00644():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'vad_windows', 'word_shape') == None


def test_b02_c00645():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'vad_windows', 'unclassified') == None


def test_b02_c00646():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'word_clocks', 'decode_payload_invalid')
        == None
    )


def test_b02_c00647():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'word_clocks', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c00648():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'word_clocks', 'empty_asr') == None


def test_b02_c00649():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'word_clocks', 'no_owned_words') == None


def test_b02_c00650():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'word_clocks', 'outside_admitted_source')
        == None
    )


def test_b02_c00651():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'word_clocks', 'persist_payload_invalid')
        == None
    )


def test_b02_c00652():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'word_clocks', 'retained_audio_invalid')
        == None
    )


def test_b02_c00653():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'word_clocks', 'staged_audio_invalid') == None
    )


def test_b02_c00654():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'word_clocks', 'unknown') == None


def test_b02_c00655():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'word_clocks', 'unsupported_language') == None
    )


def test_b02_c00656():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'word_clocks', 'vad_bounds') == None


def test_b02_c00657():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c00658():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'word_clocks', 'vad_order') == None


def test_b02_c00659():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'word_clocks', 'word_clock') == None


def test_b02_c00660():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'word_clocks', 'word_sequence') == None


def test_b02_c00661():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'word_clocks', 'word_shape') == None


def test_b02_c00662():
    assert decode_payload_failure_reason(_make('b_ConnectionAbortedError'), 'word_clocks', 'unclassified') == None


def test_b02_c00663():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'asr_recovery', 'decode_payload_invalid') == None


def test_b02_c00664():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionError'), 'asr_recovery', 'decoded_duration_mismatch') == None
    )


def test_b02_c00665():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'asr_recovery', 'empty_asr') == None


def test_b02_c00666():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c00667():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'asr_recovery', 'outside_admitted_source') == None


def test_b02_c00668():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'asr_recovery', 'persist_payload_invalid') == None


def test_b02_c00669():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'asr_recovery', 'retained_audio_invalid') == None


def test_b02_c00670():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c00671():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'asr_recovery', 'unknown') == None


def test_b02_c00672():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c00673():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c00674():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c00675():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'asr_recovery', 'vad_order') == None


def test_b02_c00676():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'asr_recovery', 'word_clock') == None


def test_b02_c00677():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'asr_recovery', 'word_sequence') == None


def test_b02_c00678():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'asr_recovery', 'word_shape') == None


def test_b02_c00679():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'asr_recovery', 'unclassified') == None


def test_b02_c00680():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'assemble_words', 'decode_payload_invalid') == None


def test_b02_c00681():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionError'), 'assemble_words', 'decoded_duration_mismatch') == None
    )


def test_b02_c00682():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'assemble_words', 'empty_asr') == None


def test_b02_c00683():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'assemble_words', 'no_owned_words') == None


def test_b02_c00684():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionError'), 'assemble_words', 'outside_admitted_source') == None
    )


def test_b02_c00685():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionError'), 'assemble_words', 'persist_payload_invalid') == None
    )


def test_b02_c00686():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'assemble_words', 'retained_audio_invalid') == None


def test_b02_c00687():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'assemble_words', 'staged_audio_invalid') == None


def test_b02_c00688():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'assemble_words', 'unknown') == None


def test_b02_c00689():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'assemble_words', 'unsupported_language') == None


def test_b02_c00690():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'assemble_words', 'vad_bounds') == None


def test_b02_c00691():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c00692():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'assemble_words', 'vad_order') == None


def test_b02_c00693():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'assemble_words', 'word_clock') == None


def test_b02_c00694():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'assemble_words', 'word_sequence') == None


def test_b02_c00695():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'assemble_words', 'word_shape') == None


def test_b02_c00696():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'assemble_words', 'unclassified') == None


def test_b02_c00697():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'fetch_decode', 'decode_payload_invalid') == None


def test_b02_c00698():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionError'), 'fetch_decode', 'decoded_duration_mismatch') == None
    )


def test_b02_c00699():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'fetch_decode', 'empty_asr') == None


def test_b02_c00700():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c00701():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'fetch_decode', 'outside_admitted_source') == None


def test_b02_c00702():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'fetch_decode', 'persist_payload_invalid') == None


def test_b02_c00703():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'fetch_decode', 'retained_audio_invalid') == None


def test_b02_c00704():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c00705():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'fetch_decode', 'unknown') == None


def test_b02_c00706():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c00707():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c00708():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c00709():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'fetch_decode', 'vad_order') == None


def test_b02_c00710():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'fetch_decode', 'word_clock') == None


def test_b02_c00711():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'fetch_decode', 'word_sequence') == None


def test_b02_c00712():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'fetch_decode', 'word_shape') == None


def test_b02_c00713():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'fetch_decode', 'unclassified') == None


def test_b02_c00714():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'persist', 'decode_payload_invalid') == None


def test_b02_c00715():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c00716():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'persist', 'empty_asr') == None


def test_b02_c00717():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'persist', 'no_owned_words') == None


def test_b02_c00718():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'persist', 'outside_admitted_source') == None


def test_b02_c00719():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'persist', 'persist_payload_invalid') == None


def test_b02_c00720():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'persist', 'retained_audio_invalid') == None


def test_b02_c00721():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'persist', 'staged_audio_invalid') == None


def test_b02_c00722():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'persist', 'unknown') == None


def test_b02_c00723():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'persist', 'unsupported_language') == None


def test_b02_c00724():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'persist', 'vad_bounds') == None


def test_b02_c00725():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'persist', 'vad_nonfinite') == None


def test_b02_c00726():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'persist', 'vad_order') == None


def test_b02_c00727():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'persist', 'word_clock') == None


def test_b02_c00728():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'persist', 'word_sequence') == None


def test_b02_c00729():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'persist', 'word_shape') == None


def test_b02_c00730():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'persist', 'unclassified') == None


def test_b02_c00731():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c00732():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'vad_windows', 'decoded_duration_mismatch') == None


def test_b02_c00733():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'vad_windows', 'empty_asr') == None


def test_b02_c00734():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'vad_windows', 'no_owned_words') == None


def test_b02_c00735():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'vad_windows', 'outside_admitted_source') == None


def test_b02_c00736():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'vad_windows', 'persist_payload_invalid') == None


def test_b02_c00737():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c00738():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c00739():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'vad_windows', 'unknown') == None


def test_b02_c00740():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'vad_windows', 'unsupported_language') == None


def test_b02_c00741():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'vad_windows', 'vad_bounds') == None


def test_b02_c00742():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c00743():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'vad_windows', 'vad_order') == None


def test_b02_c00744():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'vad_windows', 'word_clock') == None


def test_b02_c00745():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'vad_windows', 'word_sequence') == None


def test_b02_c00746():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'vad_windows', 'word_shape') == None


def test_b02_c00747():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'vad_windows', 'unclassified') == None


def test_b02_c00748():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c00749():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'word_clocks', 'decoded_duration_mismatch') == None


def test_b02_c00750():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'word_clocks', 'empty_asr') == None


def test_b02_c00751():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'word_clocks', 'no_owned_words') == None


def test_b02_c00752():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'word_clocks', 'outside_admitted_source') == None


def test_b02_c00753():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'word_clocks', 'persist_payload_invalid') == None


def test_b02_c00754():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c00755():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c00756():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'word_clocks', 'unknown') == None


def test_b02_c00757():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'word_clocks', 'unsupported_language') == None


def test_b02_c00758():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'word_clocks', 'vad_bounds') == None


def test_b02_c00759():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c00760():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'word_clocks', 'vad_order') == None


def test_b02_c00761():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'word_clocks', 'word_clock') == None


def test_b02_c00762():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'word_clocks', 'word_sequence') == None


def test_b02_c00763():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'word_clocks', 'word_shape') == None


def test_b02_c00764():
    assert decode_payload_failure_reason(_make('b_ConnectionError'), 'word_clocks', 'unclassified') == None


def test_b02_c00765():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'asr_recovery', 'decode_payload_invalid')
        == None
    )


def test_b02_c00766():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'asr_recovery', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c00767():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'asr_recovery', 'empty_asr') == None


def test_b02_c00768():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c00769():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'asr_recovery', 'outside_admitted_source')
        == None
    )


def test_b02_c00770():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'asr_recovery', 'persist_payload_invalid')
        == None
    )


def test_b02_c00771():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'asr_recovery', 'retained_audio_invalid')
        == None
    )


def test_b02_c00772():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'asr_recovery', 'staged_audio_invalid') == None
    )


def test_b02_c00773():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'asr_recovery', 'unknown') == None


def test_b02_c00774():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'asr_recovery', 'unsupported_language') == None
    )


def test_b02_c00775():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c00776():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c00777():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'asr_recovery', 'vad_order') == None


def test_b02_c00778():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'asr_recovery', 'word_clock') == None


def test_b02_c00779():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'asr_recovery', 'word_sequence') == None


def test_b02_c00780():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'asr_recovery', 'word_shape') == None


def test_b02_c00781():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'asr_recovery', 'unclassified') == None


def test_b02_c00782():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'assemble_words', 'decode_payload_invalid')
        == None
    )


def test_b02_c00783():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'assemble_words', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c00784():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'assemble_words', 'empty_asr') == None


def test_b02_c00785():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'assemble_words', 'no_owned_words') == None


def test_b02_c00786():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'assemble_words', 'outside_admitted_source')
        == None
    )


def test_b02_c00787():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'assemble_words', 'persist_payload_invalid')
        == None
    )


def test_b02_c00788():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'assemble_words', 'retained_audio_invalid')
        == None
    )


def test_b02_c00789():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'assemble_words', 'staged_audio_invalid')
        == None
    )


def test_b02_c00790():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'assemble_words', 'unknown') == None


def test_b02_c00791():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'assemble_words', 'unsupported_language')
        == None
    )


def test_b02_c00792():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'assemble_words', 'vad_bounds') == None


def test_b02_c00793():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c00794():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'assemble_words', 'vad_order') == None


def test_b02_c00795():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'assemble_words', 'word_clock') == None


def test_b02_c00796():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'assemble_words', 'word_sequence') == None


def test_b02_c00797():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'assemble_words', 'word_shape') == None


def test_b02_c00798():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'assemble_words', 'unclassified') == None


def test_b02_c00799():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'fetch_decode', 'decode_payload_invalid')
        == None
    )


def test_b02_c00800():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'fetch_decode', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c00801():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'fetch_decode', 'empty_asr') == None


def test_b02_c00802():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c00803():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'fetch_decode', 'outside_admitted_source')
        == None
    )


def test_b02_c00804():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'fetch_decode', 'persist_payload_invalid')
        == None
    )


def test_b02_c00805():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'fetch_decode', 'retained_audio_invalid')
        == None
    )


def test_b02_c00806():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'fetch_decode', 'staged_audio_invalid') == None
    )


def test_b02_c00807():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'fetch_decode', 'unknown') == None


def test_b02_c00808():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'fetch_decode', 'unsupported_language') == None
    )


def test_b02_c00809():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c00810():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c00811():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'fetch_decode', 'vad_order') == None


def test_b02_c00812():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'fetch_decode', 'word_clock') == None


def test_b02_c00813():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'fetch_decode', 'word_sequence') == None


def test_b02_c00814():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'fetch_decode', 'word_shape') == None


def test_b02_c00815():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'fetch_decode', 'unclassified') == None


def test_b02_c00816():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'persist', 'decode_payload_invalid') == None


def test_b02_c00817():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'persist', 'decoded_duration_mismatch') == None
    )


def test_b02_c00818():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'persist', 'empty_asr') == None


def test_b02_c00819():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'persist', 'no_owned_words') == None


def test_b02_c00820():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'persist', 'outside_admitted_source') == None
    )


def test_b02_c00821():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'persist', 'persist_payload_invalid') == None
    )


def test_b02_c00822():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'persist', 'retained_audio_invalid') == None


def test_b02_c00823():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'persist', 'staged_audio_invalid') == None


def test_b02_c00824():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'persist', 'unknown') == None


def test_b02_c00825():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'persist', 'unsupported_language') == None


def test_b02_c00826():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'persist', 'vad_bounds') == None


def test_b02_c00827():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'persist', 'vad_nonfinite') == None


def test_b02_c00828():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'persist', 'vad_order') == None


def test_b02_c00829():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'persist', 'word_clock') == None


def test_b02_c00830():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'persist', 'word_sequence') == None


def test_b02_c00831():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'persist', 'word_shape') == None


def test_b02_c00832():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'persist', 'unclassified') == None


def test_b02_c00833():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'vad_windows', 'decode_payload_invalid')
        == None
    )


def test_b02_c00834():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'vad_windows', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c00835():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'vad_windows', 'empty_asr') == None


def test_b02_c00836():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'vad_windows', 'no_owned_words') == None


def test_b02_c00837():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'vad_windows', 'outside_admitted_source')
        == None
    )


def test_b02_c00838():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'vad_windows', 'persist_payload_invalid')
        == None
    )


def test_b02_c00839():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'vad_windows', 'retained_audio_invalid')
        == None
    )


def test_b02_c00840():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'vad_windows', 'staged_audio_invalid') == None
    )


def test_b02_c00841():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'vad_windows', 'unknown') == None


def test_b02_c00842():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'vad_windows', 'unsupported_language') == None
    )


def test_b02_c00843():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'vad_windows', 'vad_bounds') == None


def test_b02_c00844():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c00845():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'vad_windows', 'vad_order') == None


def test_b02_c00846():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'vad_windows', 'word_clock') == None


def test_b02_c00847():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'vad_windows', 'word_sequence') == None


def test_b02_c00848():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'vad_windows', 'word_shape') == None


def test_b02_c00849():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'vad_windows', 'unclassified') == None


def test_b02_c00850():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'word_clocks', 'decode_payload_invalid')
        == None
    )


def test_b02_c00851():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'word_clocks', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c00852():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'word_clocks', 'empty_asr') == None


def test_b02_c00853():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'word_clocks', 'no_owned_words') == None


def test_b02_c00854():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'word_clocks', 'outside_admitted_source')
        == None
    )


def test_b02_c00855():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'word_clocks', 'persist_payload_invalid')
        == None
    )


def test_b02_c00856():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'word_clocks', 'retained_audio_invalid')
        == None
    )


def test_b02_c00857():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'word_clocks', 'staged_audio_invalid') == None
    )


def test_b02_c00858():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'word_clocks', 'unknown') == None


def test_b02_c00859():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'word_clocks', 'unsupported_language') == None
    )


def test_b02_c00860():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'word_clocks', 'vad_bounds') == None


def test_b02_c00861():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c00862():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'word_clocks', 'vad_order') == None


def test_b02_c00863():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'word_clocks', 'word_clock') == None


def test_b02_c00864():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'word_clocks', 'word_sequence') == None


def test_b02_c00865():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'word_clocks', 'word_shape') == None


def test_b02_c00866():
    assert decode_payload_failure_reason(_make('b_ConnectionRefusedError'), 'word_clocks', 'unclassified') == None


def test_b02_c00867():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'asr_recovery', 'decode_payload_invalid') == None
    )


def test_b02_c00868():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'asr_recovery', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c00869():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'asr_recovery', 'empty_asr') == None


def test_b02_c00870():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c00871():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'asr_recovery', 'outside_admitted_source')
        == None
    )


def test_b02_c00872():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'asr_recovery', 'persist_payload_invalid')
        == None
    )


def test_b02_c00873():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'asr_recovery', 'retained_audio_invalid') == None
    )


def test_b02_c00874():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'asr_recovery', 'staged_audio_invalid') == None
    )


def test_b02_c00875():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'asr_recovery', 'unknown') == None


def test_b02_c00876():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'asr_recovery', 'unsupported_language') == None
    )


def test_b02_c00877():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c00878():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c00879():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'asr_recovery', 'vad_order') == None


def test_b02_c00880():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'asr_recovery', 'word_clock') == None


def test_b02_c00881():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'asr_recovery', 'word_sequence') == None


def test_b02_c00882():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'asr_recovery', 'word_shape') == None


def test_b02_c00883():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'asr_recovery', 'unclassified') == None


def test_b02_c00884():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'assemble_words', 'decode_payload_invalid')
        == None
    )


def test_b02_c00885():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'assemble_words', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c00886():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'assemble_words', 'empty_asr') == None


def test_b02_c00887():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'assemble_words', 'no_owned_words') == None


def test_b02_c00888():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'assemble_words', 'outside_admitted_source')
        == None
    )


def test_b02_c00889():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'assemble_words', 'persist_payload_invalid')
        == None
    )


def test_b02_c00890():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'assemble_words', 'retained_audio_invalid')
        == None
    )


def test_b02_c00891():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'assemble_words', 'staged_audio_invalid') == None
    )


def test_b02_c00892():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'assemble_words', 'unknown') == None


def test_b02_c00893():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'assemble_words', 'unsupported_language') == None
    )


def test_b02_c00894():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'assemble_words', 'vad_bounds') == None


def test_b02_c00895():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c00896():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'assemble_words', 'vad_order') == None


def test_b02_c00897():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'assemble_words', 'word_clock') == None


def test_b02_c00898():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'assemble_words', 'word_sequence') == None


def test_b02_c00899():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'assemble_words', 'word_shape') == None


def test_b02_c00900():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'assemble_words', 'unclassified') == None


def test_b02_c00901():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'fetch_decode', 'decode_payload_invalid') == None
    )


def test_b02_c00902():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'fetch_decode', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c00903():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'fetch_decode', 'empty_asr') == None


def test_b02_c00904():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c00905():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'fetch_decode', 'outside_admitted_source')
        == None
    )


def test_b02_c00906():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'fetch_decode', 'persist_payload_invalid')
        == None
    )


def test_b02_c00907():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'fetch_decode', 'retained_audio_invalid') == None
    )


def test_b02_c00908():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'fetch_decode', 'staged_audio_invalid') == None
    )


def test_b02_c00909():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'fetch_decode', 'unknown') == None


def test_b02_c00910():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'fetch_decode', 'unsupported_language') == None
    )


def test_b02_c00911():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c00912():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c00913():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'fetch_decode', 'vad_order') == None


def test_b02_c00914():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'fetch_decode', 'word_clock') == None


def test_b02_c00915():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'fetch_decode', 'word_sequence') == None


def test_b02_c00916():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'fetch_decode', 'word_shape') == None


def test_b02_c00917():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'fetch_decode', 'unclassified') == None


def test_b02_c00918():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'persist', 'decode_payload_invalid') == None


def test_b02_c00919():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'persist', 'decoded_duration_mismatch') == None
    )


def test_b02_c00920():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'persist', 'empty_asr') == None


def test_b02_c00921():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'persist', 'no_owned_words') == None


def test_b02_c00922():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'persist', 'outside_admitted_source') == None


def test_b02_c00923():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'persist', 'persist_payload_invalid') == None


def test_b02_c00924():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'persist', 'retained_audio_invalid') == None


def test_b02_c00925():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'persist', 'staged_audio_invalid') == None


def test_b02_c00926():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'persist', 'unknown') == None


def test_b02_c00927():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'persist', 'unsupported_language') == None


def test_b02_c00928():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'persist', 'vad_bounds') == None


def test_b02_c00929():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'persist', 'vad_nonfinite') == None


def test_b02_c00930():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'persist', 'vad_order') == None


def test_b02_c00931():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'persist', 'word_clock') == None


def test_b02_c00932():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'persist', 'word_sequence') == None


def test_b02_c00933():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'persist', 'word_shape') == None


def test_b02_c00934():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'persist', 'unclassified') == None


def test_b02_c00935():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'vad_windows', 'decode_payload_invalid') == None
    )


def test_b02_c00936():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'vad_windows', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c00937():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'vad_windows', 'empty_asr') == None


def test_b02_c00938():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'vad_windows', 'no_owned_words') == None


def test_b02_c00939():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'vad_windows', 'outside_admitted_source') == None
    )


def test_b02_c00940():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'vad_windows', 'persist_payload_invalid') == None
    )


def test_b02_c00941():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'vad_windows', 'retained_audio_invalid') == None
    )


def test_b02_c00942():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c00943():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'vad_windows', 'unknown') == None


def test_b02_c00944():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'vad_windows', 'unsupported_language') == None


def test_b02_c00945():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'vad_windows', 'vad_bounds') == None


def test_b02_c00946():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c00947():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'vad_windows', 'vad_order') == None


def test_b02_c00948():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'vad_windows', 'word_clock') == None


def test_b02_c00949():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'vad_windows', 'word_sequence') == None


def test_b02_c00950():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'vad_windows', 'word_shape') == None


def test_b02_c00951():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'vad_windows', 'unclassified') == None


def test_b02_c00952():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'word_clocks', 'decode_payload_invalid') == None
    )


def test_b02_c00953():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'word_clocks', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c00954():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'word_clocks', 'empty_asr') == None


def test_b02_c00955():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'word_clocks', 'no_owned_words') == None


def test_b02_c00956():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'word_clocks', 'outside_admitted_source') == None
    )


def test_b02_c00957():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'word_clocks', 'persist_payload_invalid') == None
    )


def test_b02_c00958():
    assert (
        decode_payload_failure_reason(_make('b_ConnectionResetError'), 'word_clocks', 'retained_audio_invalid') == None
    )


def test_b02_c00959():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c00960():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'word_clocks', 'unknown') == None


def test_b02_c00961():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'word_clocks', 'unsupported_language') == None


def test_b02_c00962():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'word_clocks', 'vad_bounds') == None


def test_b02_c00963():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c00964():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'word_clocks', 'vad_order') == None


def test_b02_c00965():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'word_clocks', 'word_clock') == None


def test_b02_c00966():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'word_clocks', 'word_sequence') == None


def test_b02_c00967():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'word_clocks', 'word_shape') == None


def test_b02_c00968():
    assert decode_payload_failure_reason(_make('b_ConnectionResetError'), 'word_clocks', 'unclassified') == None


def test_b02_c00969():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'asr_recovery', 'decode_payload_invalid') == None


def test_b02_c00970():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'asr_recovery', 'decoded_duration_mismatch') == None


def test_b02_c00971():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'asr_recovery', 'empty_asr') == None


def test_b02_c00972():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c00973():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'asr_recovery', 'outside_admitted_source') == None


def test_b02_c00974():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'asr_recovery', 'persist_payload_invalid') == None


def test_b02_c00975():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'asr_recovery', 'retained_audio_invalid') == None


def test_b02_c00976():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c00977():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'asr_recovery', 'unknown') == None


def test_b02_c00978():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c00979():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c00980():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c00981():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'asr_recovery', 'vad_order') == None


def test_b02_c00982():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'asr_recovery', 'word_clock') == None


def test_b02_c00983():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'asr_recovery', 'word_sequence') == None


def test_b02_c00984():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'asr_recovery', 'word_shape') == None


def test_b02_c00985():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'asr_recovery', 'unclassified') == None


def test_b02_c00986():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'assemble_words', 'decode_payload_invalid') == None


def test_b02_c00987():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'assemble_words', 'decoded_duration_mismatch') == None


def test_b02_c00988():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'assemble_words', 'empty_asr') == None


def test_b02_c00989():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'assemble_words', 'no_owned_words') == None


def test_b02_c00990():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'assemble_words', 'outside_admitted_source') == None


def test_b02_c00991():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'assemble_words', 'persist_payload_invalid') == None


def test_b02_c00992():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'assemble_words', 'retained_audio_invalid') == None


def test_b02_c00993():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'assemble_words', 'staged_audio_invalid') == None


def test_b02_c00994():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'assemble_words', 'unknown') == None


def test_b02_c00995():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'assemble_words', 'unsupported_language') == None


def test_b02_c00996():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'assemble_words', 'vad_bounds') == None


def test_b02_c00997():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c00998():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'assemble_words', 'vad_order') == None


def test_b02_c00999():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'assemble_words', 'word_clock') == None


def test_b02_c01000():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'assemble_words', 'word_sequence') == None


def test_b02_c01001():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'assemble_words', 'word_shape') == None


def test_b02_c01002():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'assemble_words', 'unclassified') == None


def test_b02_c01003():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'fetch_decode', 'decode_payload_invalid') == None


def test_b02_c01004():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'fetch_decode', 'decoded_duration_mismatch') == None


def test_b02_c01005():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'fetch_decode', 'empty_asr') == None


def test_b02_c01006():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c01007():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'fetch_decode', 'outside_admitted_source') == None


def test_b02_c01008():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'fetch_decode', 'persist_payload_invalid') == None


def test_b02_c01009():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'fetch_decode', 'retained_audio_invalid') == None


def test_b02_c01010():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c01011():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'fetch_decode', 'unknown') == None


def test_b02_c01012():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c01013():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c01014():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c01015():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'fetch_decode', 'vad_order') == None


def test_b02_c01016():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'fetch_decode', 'word_clock') == None


def test_b02_c01017():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'fetch_decode', 'word_sequence') == None


def test_b02_c01018():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'fetch_decode', 'word_shape') == None


def test_b02_c01019():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'fetch_decode', 'unclassified') == None


def test_b02_c01020():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'persist', 'decode_payload_invalid') == None


def test_b02_c01021():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c01022():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'persist', 'empty_asr') == None


def test_b02_c01023():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'persist', 'no_owned_words') == None


def test_b02_c01024():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'persist', 'outside_admitted_source') == None


def test_b02_c01025():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'persist', 'persist_payload_invalid') == None


def test_b02_c01026():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'persist', 'retained_audio_invalid') == None


def test_b02_c01027():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'persist', 'staged_audio_invalid') == None


def test_b02_c01028():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'persist', 'unknown') == None


def test_b02_c01029():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'persist', 'unsupported_language') == None


def test_b02_c01030():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'persist', 'vad_bounds') == None


def test_b02_c01031():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'persist', 'vad_nonfinite') == None


def test_b02_c01032():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'persist', 'vad_order') == None


def test_b02_c01033():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'persist', 'word_clock') == None


def test_b02_c01034():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'persist', 'word_sequence') == None


def test_b02_c01035():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'persist', 'word_shape') == None


def test_b02_c01036():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'persist', 'unclassified') == None


def test_b02_c01037():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c01038():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'vad_windows', 'decoded_duration_mismatch') == None


def test_b02_c01039():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'vad_windows', 'empty_asr') == None


def test_b02_c01040():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'vad_windows', 'no_owned_words') == None


def test_b02_c01041():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'vad_windows', 'outside_admitted_source') == None


def test_b02_c01042():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'vad_windows', 'persist_payload_invalid') == None


def test_b02_c01043():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c01044():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c01045():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'vad_windows', 'unknown') == None


def test_b02_c01046():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'vad_windows', 'unsupported_language') == None


def test_b02_c01047():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'vad_windows', 'vad_bounds') == None


def test_b02_c01048():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c01049():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'vad_windows', 'vad_order') == None


def test_b02_c01050():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'vad_windows', 'word_clock') == None


def test_b02_c01051():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'vad_windows', 'word_sequence') == None


def test_b02_c01052():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'vad_windows', 'word_shape') == None


def test_b02_c01053():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'vad_windows', 'unclassified') == None


def test_b02_c01054():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c01055():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'word_clocks', 'decoded_duration_mismatch') == None


def test_b02_c01056():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'word_clocks', 'empty_asr') == None


def test_b02_c01057():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'word_clocks', 'no_owned_words') == None


def test_b02_c01058():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'word_clocks', 'outside_admitted_source') == None


def test_b02_c01059():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'word_clocks', 'persist_payload_invalid') == None


def test_b02_c01060():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c01061():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c01062():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'word_clocks', 'unknown') == None


def test_b02_c01063():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'word_clocks', 'unsupported_language') == None


def test_b02_c01064():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'word_clocks', 'vad_bounds') == None


def test_b02_c01065():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c01066():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'word_clocks', 'vad_order') == None


def test_b02_c01067():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'word_clocks', 'word_clock') == None


def test_b02_c01068():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'word_clocks', 'word_sequence') == None


def test_b02_c01069():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'word_clocks', 'word_shape') == None


def test_b02_c01070():
    assert decode_payload_failure_reason(_make('b_EOFError'), 'word_clocks', 'unclassified') == None


def test_b02_c01071():
    assert decode_payload_failure_reason(_make('b_Exception'), 'asr_recovery', 'decode_payload_invalid') == None


def test_b02_c01072():
    assert decode_payload_failure_reason(_make('b_Exception'), 'asr_recovery', 'decoded_duration_mismatch') == None


def test_b02_c01073():
    assert decode_payload_failure_reason(_make('b_Exception'), 'asr_recovery', 'empty_asr') == None


def test_b02_c01074():
    assert decode_payload_failure_reason(_make('b_Exception'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c01075():
    assert decode_payload_failure_reason(_make('b_Exception'), 'asr_recovery', 'outside_admitted_source') == None


def test_b02_c01076():
    assert decode_payload_failure_reason(_make('b_Exception'), 'asr_recovery', 'persist_payload_invalid') == None


def test_b02_c01077():
    assert decode_payload_failure_reason(_make('b_Exception'), 'asr_recovery', 'retained_audio_invalid') == None


def test_b02_c01078():
    assert decode_payload_failure_reason(_make('b_Exception'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c01079():
    assert decode_payload_failure_reason(_make('b_Exception'), 'asr_recovery', 'unknown') == None


def test_b02_c01080():
    assert decode_payload_failure_reason(_make('b_Exception'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c01081():
    assert decode_payload_failure_reason(_make('b_Exception'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c01082():
    assert decode_payload_failure_reason(_make('b_Exception'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c01083():
    assert decode_payload_failure_reason(_make('b_Exception'), 'asr_recovery', 'vad_order') == None


def test_b02_c01084():
    assert decode_payload_failure_reason(_make('b_Exception'), 'asr_recovery', 'word_clock') == None


def test_b02_c01085():
    assert decode_payload_failure_reason(_make('b_Exception'), 'asr_recovery', 'word_sequence') == None


def test_b02_c01086():
    assert decode_payload_failure_reason(_make('b_Exception'), 'asr_recovery', 'word_shape') == None


def test_b02_c01087():
    assert decode_payload_failure_reason(_make('b_Exception'), 'asr_recovery', 'unclassified') == None


def test_b02_c01088():
    assert decode_payload_failure_reason(_make('b_Exception'), 'assemble_words', 'decode_payload_invalid') == None


def test_b02_c01089():
    assert decode_payload_failure_reason(_make('b_Exception'), 'assemble_words', 'decoded_duration_mismatch') == None


def test_b02_c01090():
    assert decode_payload_failure_reason(_make('b_Exception'), 'assemble_words', 'empty_asr') == None


def test_b02_c01091():
    assert decode_payload_failure_reason(_make('b_Exception'), 'assemble_words', 'no_owned_words') == None


def test_b02_c01092():
    assert decode_payload_failure_reason(_make('b_Exception'), 'assemble_words', 'outside_admitted_source') == None


def test_b02_c01093():
    assert decode_payload_failure_reason(_make('b_Exception'), 'assemble_words', 'persist_payload_invalid') == None


def test_b02_c01094():
    assert decode_payload_failure_reason(_make('b_Exception'), 'assemble_words', 'retained_audio_invalid') == None


def test_b02_c01095():
    assert decode_payload_failure_reason(_make('b_Exception'), 'assemble_words', 'staged_audio_invalid') == None


def test_b02_c01096():
    assert decode_payload_failure_reason(_make('b_Exception'), 'assemble_words', 'unknown') == None


def test_b02_c01097():
    assert decode_payload_failure_reason(_make('b_Exception'), 'assemble_words', 'unsupported_language') == None


def test_b02_c01098():
    assert decode_payload_failure_reason(_make('b_Exception'), 'assemble_words', 'vad_bounds') == None


def test_b02_c01099():
    assert decode_payload_failure_reason(_make('b_Exception'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c01100():
    assert decode_payload_failure_reason(_make('b_Exception'), 'assemble_words', 'vad_order') == None


def test_b02_c01101():
    assert decode_payload_failure_reason(_make('b_Exception'), 'assemble_words', 'word_clock') == None


def test_b02_c01102():
    assert decode_payload_failure_reason(_make('b_Exception'), 'assemble_words', 'word_sequence') == None


def test_b02_c01103():
    assert decode_payload_failure_reason(_make('b_Exception'), 'assemble_words', 'word_shape') == None


def test_b02_c01104():
    assert decode_payload_failure_reason(_make('b_Exception'), 'assemble_words', 'unclassified') == None


def test_b02_c01105():
    assert decode_payload_failure_reason(_make('b_Exception'), 'fetch_decode', 'decode_payload_invalid') == None


def test_b02_c01106():
    assert decode_payload_failure_reason(_make('b_Exception'), 'fetch_decode', 'decoded_duration_mismatch') == None


def test_b02_c01107():
    assert decode_payload_failure_reason(_make('b_Exception'), 'fetch_decode', 'empty_asr') == None


def test_b02_c01108():
    assert decode_payload_failure_reason(_make('b_Exception'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c01109():
    assert decode_payload_failure_reason(_make('b_Exception'), 'fetch_decode', 'outside_admitted_source') == None


def test_b02_c01110():
    assert decode_payload_failure_reason(_make('b_Exception'), 'fetch_decode', 'persist_payload_invalid') == None


def test_b02_c01111():
    assert decode_payload_failure_reason(_make('b_Exception'), 'fetch_decode', 'retained_audio_invalid') == None


def test_b02_c01112():
    assert decode_payload_failure_reason(_make('b_Exception'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c01113():
    assert decode_payload_failure_reason(_make('b_Exception'), 'fetch_decode', 'unknown') == None


def test_b02_c01114():
    assert decode_payload_failure_reason(_make('b_Exception'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c01115():
    assert decode_payload_failure_reason(_make('b_Exception'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c01116():
    assert decode_payload_failure_reason(_make('b_Exception'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c01117():
    assert decode_payload_failure_reason(_make('b_Exception'), 'fetch_decode', 'vad_order') == None


def test_b02_c01118():
    assert decode_payload_failure_reason(_make('b_Exception'), 'fetch_decode', 'word_clock') == None


def test_b02_c01119():
    assert decode_payload_failure_reason(_make('b_Exception'), 'fetch_decode', 'word_sequence') == None


def test_b02_c01120():
    assert decode_payload_failure_reason(_make('b_Exception'), 'fetch_decode', 'word_shape') == None


def test_b02_c01121():
    assert decode_payload_failure_reason(_make('b_Exception'), 'fetch_decode', 'unclassified') == None


def test_b02_c01122():
    assert decode_payload_failure_reason(_make('b_Exception'), 'persist', 'decode_payload_invalid') == None


def test_b02_c01123():
    assert decode_payload_failure_reason(_make('b_Exception'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c01124():
    assert decode_payload_failure_reason(_make('b_Exception'), 'persist', 'empty_asr') == None


def test_b02_c01125():
    assert decode_payload_failure_reason(_make('b_Exception'), 'persist', 'no_owned_words') == None


def test_b02_c01126():
    assert decode_payload_failure_reason(_make('b_Exception'), 'persist', 'outside_admitted_source') == None


def test_b02_c01127():
    assert decode_payload_failure_reason(_make('b_Exception'), 'persist', 'persist_payload_invalid') == None


def test_b02_c01128():
    assert decode_payload_failure_reason(_make('b_Exception'), 'persist', 'retained_audio_invalid') == None


def test_b02_c01129():
    assert decode_payload_failure_reason(_make('b_Exception'), 'persist', 'staged_audio_invalid') == None


def test_b02_c01130():
    assert decode_payload_failure_reason(_make('b_Exception'), 'persist', 'unknown') == None


def test_b02_c01131():
    assert decode_payload_failure_reason(_make('b_Exception'), 'persist', 'unsupported_language') == None


def test_b02_c01132():
    assert decode_payload_failure_reason(_make('b_Exception'), 'persist', 'vad_bounds') == None


def test_b02_c01133():
    assert decode_payload_failure_reason(_make('b_Exception'), 'persist', 'vad_nonfinite') == None


def test_b02_c01134():
    assert decode_payload_failure_reason(_make('b_Exception'), 'persist', 'vad_order') == None


def test_b02_c01135():
    assert decode_payload_failure_reason(_make('b_Exception'), 'persist', 'word_clock') == None


def test_b02_c01136():
    assert decode_payload_failure_reason(_make('b_Exception'), 'persist', 'word_sequence') == None


def test_b02_c01137():
    assert decode_payload_failure_reason(_make('b_Exception'), 'persist', 'word_shape') == None


def test_b02_c01138():
    assert decode_payload_failure_reason(_make('b_Exception'), 'persist', 'unclassified') == None


def test_b02_c01139():
    assert decode_payload_failure_reason(_make('b_Exception'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c01140():
    assert decode_payload_failure_reason(_make('b_Exception'), 'vad_windows', 'decoded_duration_mismatch') == None


def test_b02_c01141():
    assert decode_payload_failure_reason(_make('b_Exception'), 'vad_windows', 'empty_asr') == None


def test_b02_c01142():
    assert decode_payload_failure_reason(_make('b_Exception'), 'vad_windows', 'no_owned_words') == None


def test_b02_c01143():
    assert decode_payload_failure_reason(_make('b_Exception'), 'vad_windows', 'outside_admitted_source') == None


def test_b02_c01144():
    assert decode_payload_failure_reason(_make('b_Exception'), 'vad_windows', 'persist_payload_invalid') == None


def test_b02_c01145():
    assert decode_payload_failure_reason(_make('b_Exception'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c01146():
    assert decode_payload_failure_reason(_make('b_Exception'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c01147():
    assert decode_payload_failure_reason(_make('b_Exception'), 'vad_windows', 'unknown') == None


def test_b02_c01148():
    assert decode_payload_failure_reason(_make('b_Exception'), 'vad_windows', 'unsupported_language') == None


def test_b02_c01149():
    assert decode_payload_failure_reason(_make('b_Exception'), 'vad_windows', 'vad_bounds') == None


def test_b02_c01150():
    assert decode_payload_failure_reason(_make('b_Exception'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c01151():
    assert decode_payload_failure_reason(_make('b_Exception'), 'vad_windows', 'vad_order') == None


def test_b02_c01152():
    assert decode_payload_failure_reason(_make('b_Exception'), 'vad_windows', 'word_clock') == None


def test_b02_c01153():
    assert decode_payload_failure_reason(_make('b_Exception'), 'vad_windows', 'word_sequence') == None


def test_b02_c01154():
    assert decode_payload_failure_reason(_make('b_Exception'), 'vad_windows', 'word_shape') == None


def test_b02_c01155():
    assert decode_payload_failure_reason(_make('b_Exception'), 'vad_windows', 'unclassified') == None


def test_b02_c01156():
    assert decode_payload_failure_reason(_make('b_Exception'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c01157():
    assert decode_payload_failure_reason(_make('b_Exception'), 'word_clocks', 'decoded_duration_mismatch') == None


def test_b02_c01158():
    assert decode_payload_failure_reason(_make('b_Exception'), 'word_clocks', 'empty_asr') == None


def test_b02_c01159():
    assert decode_payload_failure_reason(_make('b_Exception'), 'word_clocks', 'no_owned_words') == None


def test_b02_c01160():
    assert decode_payload_failure_reason(_make('b_Exception'), 'word_clocks', 'outside_admitted_source') == None


def test_b02_c01161():
    assert decode_payload_failure_reason(_make('b_Exception'), 'word_clocks', 'persist_payload_invalid') == None


def test_b02_c01162():
    assert decode_payload_failure_reason(_make('b_Exception'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c01163():
    assert decode_payload_failure_reason(_make('b_Exception'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c01164():
    assert decode_payload_failure_reason(_make('b_Exception'), 'word_clocks', 'unknown') == None


def test_b02_c01165():
    assert decode_payload_failure_reason(_make('b_Exception'), 'word_clocks', 'unsupported_language') == None


def test_b02_c01166():
    assert decode_payload_failure_reason(_make('b_Exception'), 'word_clocks', 'vad_bounds') == None


def test_b02_c01167():
    assert decode_payload_failure_reason(_make('b_Exception'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c01168():
    assert decode_payload_failure_reason(_make('b_Exception'), 'word_clocks', 'vad_order') == None


def test_b02_c01169():
    assert decode_payload_failure_reason(_make('b_Exception'), 'word_clocks', 'word_clock') == None


def test_b02_c01170():
    assert decode_payload_failure_reason(_make('b_Exception'), 'word_clocks', 'word_sequence') == None


def test_b02_c01171():
    assert decode_payload_failure_reason(_make('b_Exception'), 'word_clocks', 'word_shape') == None


def test_b02_c01172():
    assert decode_payload_failure_reason(_make('b_Exception'), 'word_clocks', 'unclassified') == None


def test_b02_c01173():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'asr_recovery', 'decode_payload_invalid') == None


def test_b02_c01174():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'asr_recovery', 'decoded_duration_mismatch') == None


def test_b02_c01175():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'asr_recovery', 'empty_asr') == None


def test_b02_c01176():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c01177():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'asr_recovery', 'outside_admitted_source') == None


def test_b02_c01178():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'asr_recovery', 'persist_payload_invalid') == None


def test_b02_c01179():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'asr_recovery', 'retained_audio_invalid') == None


def test_b02_c01180():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c01181():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'asr_recovery', 'unknown') == None


def test_b02_c01182():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c01183():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c01184():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c01185():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'asr_recovery', 'vad_order') == None


def test_b02_c01186():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'asr_recovery', 'word_clock') == None


def test_b02_c01187():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'asr_recovery', 'word_sequence') == None


def test_b02_c01188():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'asr_recovery', 'word_shape') == None


def test_b02_c01189():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'asr_recovery', 'unclassified') == None


def test_b02_c01190():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'assemble_words', 'decode_payload_invalid') == None


def test_b02_c01191():
    assert (
        decode_payload_failure_reason(_make('b_GeneratorExit'), 'assemble_words', 'decoded_duration_mismatch') == None
    )


def test_b02_c01192():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'assemble_words', 'empty_asr') == None


def test_b02_c01193():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'assemble_words', 'no_owned_words') == None


def test_b02_c01194():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'assemble_words', 'outside_admitted_source') == None


def test_b02_c01195():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'assemble_words', 'persist_payload_invalid') == None


def test_b02_c01196():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'assemble_words', 'retained_audio_invalid') == None


def test_b02_c01197():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'assemble_words', 'staged_audio_invalid') == None


def test_b02_c01198():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'assemble_words', 'unknown') == None


def test_b02_c01199():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'assemble_words', 'unsupported_language') == None


def test_b02_c01200():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'assemble_words', 'vad_bounds') == None


def test_b02_c01201():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c01202():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'assemble_words', 'vad_order') == None


def test_b02_c01203():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'assemble_words', 'word_clock') == None


def test_b02_c01204():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'assemble_words', 'word_sequence') == None


def test_b02_c01205():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'assemble_words', 'word_shape') == None


def test_b02_c01206():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'assemble_words', 'unclassified') == None


def test_b02_c01207():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'fetch_decode', 'decode_payload_invalid') == None


def test_b02_c01208():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'fetch_decode', 'decoded_duration_mismatch') == None


def test_b02_c01209():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'fetch_decode', 'empty_asr') == None


def test_b02_c01210():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c01211():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'fetch_decode', 'outside_admitted_source') == None


def test_b02_c01212():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'fetch_decode', 'persist_payload_invalid') == None


def test_b02_c01213():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'fetch_decode', 'retained_audio_invalid') == None


def test_b02_c01214():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c01215():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'fetch_decode', 'unknown') == None


def test_b02_c01216():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c01217():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c01218():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c01219():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'fetch_decode', 'vad_order') == None


def test_b02_c01220():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'fetch_decode', 'word_clock') == None


def test_b02_c01221():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'fetch_decode', 'word_sequence') == None


def test_b02_c01222():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'fetch_decode', 'word_shape') == None


def test_b02_c01223():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'fetch_decode', 'unclassified') == None


def test_b02_c01224():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'persist', 'decode_payload_invalid') == None


def test_b02_c01225():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c01226():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'persist', 'empty_asr') == None


def test_b02_c01227():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'persist', 'no_owned_words') == None


def test_b02_c01228():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'persist', 'outside_admitted_source') == None


def test_b02_c01229():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'persist', 'persist_payload_invalid') == None


def test_b02_c01230():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'persist', 'retained_audio_invalid') == None


def test_b02_c01231():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'persist', 'staged_audio_invalid') == None


def test_b02_c01232():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'persist', 'unknown') == None


def test_b02_c01233():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'persist', 'unsupported_language') == None


def test_b02_c01234():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'persist', 'vad_bounds') == None


def test_b02_c01235():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'persist', 'vad_nonfinite') == None


def test_b02_c01236():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'persist', 'vad_order') == None


def test_b02_c01237():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'persist', 'word_clock') == None


def test_b02_c01238():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'persist', 'word_sequence') == None


def test_b02_c01239():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'persist', 'word_shape') == None


def test_b02_c01240():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'persist', 'unclassified') == None


def test_b02_c01241():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c01242():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'vad_windows', 'decoded_duration_mismatch') == None


def test_b02_c01243():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'vad_windows', 'empty_asr') == None


def test_b02_c01244():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'vad_windows', 'no_owned_words') == None


def test_b02_c01245():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'vad_windows', 'outside_admitted_source') == None


def test_b02_c01246():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'vad_windows', 'persist_payload_invalid') == None


def test_b02_c01247():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c01248():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c01249():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'vad_windows', 'unknown') == None


def test_b02_c01250():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'vad_windows', 'unsupported_language') == None


def test_b02_c01251():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'vad_windows', 'vad_bounds') == None


def test_b02_c01252():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c01253():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'vad_windows', 'vad_order') == None


def test_b02_c01254():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'vad_windows', 'word_clock') == None


def test_b02_c01255():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'vad_windows', 'word_sequence') == None


def test_b02_c01256():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'vad_windows', 'word_shape') == None


def test_b02_c01257():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'vad_windows', 'unclassified') == None


def test_b02_c01258():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c01259():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'word_clocks', 'decoded_duration_mismatch') == None


def test_b02_c01260():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'word_clocks', 'empty_asr') == None


def test_b02_c01261():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'word_clocks', 'no_owned_words') == None


def test_b02_c01262():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'word_clocks', 'outside_admitted_source') == None


def test_b02_c01263():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'word_clocks', 'persist_payload_invalid') == None


def test_b02_c01264():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c01265():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c01266():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'word_clocks', 'unknown') == None


def test_b02_c01267():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'word_clocks', 'unsupported_language') == None


def test_b02_c01268():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'word_clocks', 'vad_bounds') == None


def test_b02_c01269():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c01270():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'word_clocks', 'vad_order') == None


def test_b02_c01271():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'word_clocks', 'word_clock') == None


def test_b02_c01272():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'word_clocks', 'word_sequence') == None


def test_b02_c01273():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'word_clocks', 'word_shape') == None


def test_b02_c01274():
    assert decode_payload_failure_reason(_make('b_GeneratorExit'), 'word_clocks', 'unclassified') == None


def test_b02_c01275():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'asr_recovery', 'decode_payload_invalid') == None


def test_b02_c01276():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'asr_recovery', 'decoded_duration_mismatch') == None


def test_b02_c01277():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'asr_recovery', 'empty_asr') == None


def test_b02_c01278():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c01279():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'asr_recovery', 'outside_admitted_source') == None


def test_b02_c01280():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'asr_recovery', 'persist_payload_invalid') == None


def test_b02_c01281():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'asr_recovery', 'retained_audio_invalid') == None


def test_b02_c01282():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c01283():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'asr_recovery', 'unknown') == None


def test_b02_c01284():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c01285():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c01286():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c01287():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'asr_recovery', 'vad_order') == None


def test_b02_c01288():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'asr_recovery', 'word_clock') == None


def test_b02_c01289():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'asr_recovery', 'word_sequence') == None


def test_b02_c01290():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'asr_recovery', 'word_shape') == None


def test_b02_c01291():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'asr_recovery', 'unclassified') == None


def test_b02_c01292():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'assemble_words', 'decode_payload_invalid') == None


def test_b02_c01293():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'assemble_words', 'decoded_duration_mismatch') == None


def test_b02_c01294():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'assemble_words', 'empty_asr') == None


def test_b02_c01295():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'assemble_words', 'no_owned_words') == None


def test_b02_c01296():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'assemble_words', 'outside_admitted_source') == None


def test_b02_c01297():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'assemble_words', 'persist_payload_invalid') == None


def test_b02_c01298():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'assemble_words', 'retained_audio_invalid') == None


def test_b02_c01299():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'assemble_words', 'staged_audio_invalid') == None


def test_b02_c01300():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'assemble_words', 'unknown') == None


def test_b02_c01301():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'assemble_words', 'unsupported_language') == None


def test_b02_c01302():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'assemble_words', 'vad_bounds') == None


def test_b02_c01303():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c01304():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'assemble_words', 'vad_order') == None


def test_b02_c01305():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'assemble_words', 'word_clock') == None


def test_b02_c01306():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'assemble_words', 'word_sequence') == None


def test_b02_c01307():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'assemble_words', 'word_shape') == None


def test_b02_c01308():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'assemble_words', 'unclassified') == None


def test_b02_c01309():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'fetch_decode', 'decode_payload_invalid') == None


def test_b02_c01310():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'fetch_decode', 'decoded_duration_mismatch') == None


def test_b02_c01311():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'fetch_decode', 'empty_asr') == None


def test_b02_c01312():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c01313():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'fetch_decode', 'outside_admitted_source') == None


def test_b02_c01314():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'fetch_decode', 'persist_payload_invalid') == None


def test_b02_c01315():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'fetch_decode', 'retained_audio_invalid') == None


def test_b02_c01316():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c01317():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'fetch_decode', 'unknown') == None


def test_b02_c01318():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c01319():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c01320():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c01321():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'fetch_decode', 'vad_order') == None


def test_b02_c01322():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'fetch_decode', 'word_clock') == None


def test_b02_c01323():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'fetch_decode', 'word_sequence') == None


def test_b02_c01324():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'fetch_decode', 'word_shape') == None


def test_b02_c01325():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'fetch_decode', 'unclassified') == None


def test_b02_c01326():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'persist', 'decode_payload_invalid') == None


def test_b02_c01327():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c01328():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'persist', 'empty_asr') == None


def test_b02_c01329():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'persist', 'no_owned_words') == None


def test_b02_c01330():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'persist', 'outside_admitted_source') == None


def test_b02_c01331():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'persist', 'persist_payload_invalid') == None


def test_b02_c01332():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'persist', 'retained_audio_invalid') == None


def test_b02_c01333():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'persist', 'staged_audio_invalid') == None


def test_b02_c01334():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'persist', 'unknown') == None


def test_b02_c01335():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'persist', 'unsupported_language') == None


def test_b02_c01336():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'persist', 'vad_bounds') == None


def test_b02_c01337():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'persist', 'vad_nonfinite') == None


def test_b02_c01338():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'persist', 'vad_order') == None


def test_b02_c01339():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'persist', 'word_clock') == None


def test_b02_c01340():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'persist', 'word_sequence') == None


def test_b02_c01341():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'persist', 'word_shape') == None


def test_b02_c01342():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'persist', 'unclassified') == None


def test_b02_c01343():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c01344():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'vad_windows', 'decoded_duration_mismatch') == None


def test_b02_c01345():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'vad_windows', 'empty_asr') == None


def test_b02_c01346():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'vad_windows', 'no_owned_words') == None


def test_b02_c01347():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'vad_windows', 'outside_admitted_source') == None


def test_b02_c01348():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'vad_windows', 'persist_payload_invalid') == None


def test_b02_c01349():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c01350():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c01351():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'vad_windows', 'unknown') == None


def test_b02_c01352():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'vad_windows', 'unsupported_language') == None


def test_b02_c01353():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'vad_windows', 'vad_bounds') == None


def test_b02_c01354():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c01355():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'vad_windows', 'vad_order') == None


def test_b02_c01356():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'vad_windows', 'word_clock') == None


def test_b02_c01357():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'vad_windows', 'word_sequence') == None


def test_b02_c01358():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'vad_windows', 'word_shape') == None


def test_b02_c01359():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'vad_windows', 'unclassified') == None


def test_b02_c01360():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c01361():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'word_clocks', 'decoded_duration_mismatch') == None


def test_b02_c01362():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'word_clocks', 'empty_asr') == None


def test_b02_c01363():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'word_clocks', 'no_owned_words') == None


def test_b02_c01364():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'word_clocks', 'outside_admitted_source') == None


def test_b02_c01365():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'word_clocks', 'persist_payload_invalid') == None


def test_b02_c01366():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c01367():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c01368():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'word_clocks', 'unknown') == None


def test_b02_c01369():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'word_clocks', 'unsupported_language') == None


def test_b02_c01370():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'word_clocks', 'vad_bounds') == None


def test_b02_c01371():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c01372():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'word_clocks', 'vad_order') == None


def test_b02_c01373():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'word_clocks', 'word_clock') == None


def test_b02_c01374():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'word_clocks', 'word_sequence') == None


def test_b02_c01375():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'word_clocks', 'word_shape') == None


def test_b02_c01376():
    assert decode_payload_failure_reason(_make('b_IndexError'), 'word_clocks', 'unclassified') == None


def test_b02_c01377():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'asr_recovery', 'decode_payload_invalid') == None


def test_b02_c01378():
    assert (
        decode_payload_failure_reason(_make('b_JSONDecodeError'), 'asr_recovery', 'decoded_duration_mismatch') == None
    )


def test_b02_c01379():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'asr_recovery', 'empty_asr') == None


def test_b02_c01380():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c01381():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'asr_recovery', 'outside_admitted_source') == None


def test_b02_c01382():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'asr_recovery', 'persist_payload_invalid') == None


def test_b02_c01383():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'asr_recovery', 'retained_audio_invalid') == None


def test_b02_c01384():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c01385():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'asr_recovery', 'unknown') == None


def test_b02_c01386():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c01387():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c01388():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c01389():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'asr_recovery', 'vad_order') == None


def test_b02_c01390():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'asr_recovery', 'word_clock') == None


def test_b02_c01391():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'asr_recovery', 'word_sequence') == None


def test_b02_c01392():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'asr_recovery', 'word_shape') == None


def test_b02_c01393():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'asr_recovery', 'unclassified') == None


def test_b02_c01394():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'assemble_words', 'decode_payload_invalid') == None


def test_b02_c01395():
    assert (
        decode_payload_failure_reason(_make('b_JSONDecodeError'), 'assemble_words', 'decoded_duration_mismatch') == None
    )


def test_b02_c01396():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'assemble_words', 'empty_asr') == None


def test_b02_c01397():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'assemble_words', 'no_owned_words') == None


def test_b02_c01398():
    assert (
        decode_payload_failure_reason(_make('b_JSONDecodeError'), 'assemble_words', 'outside_admitted_source') == None
    )


def test_b02_c01399():
    assert (
        decode_payload_failure_reason(_make('b_JSONDecodeError'), 'assemble_words', 'persist_payload_invalid') == None
    )


def test_b02_c01400():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'assemble_words', 'retained_audio_invalid') == None


def test_b02_c01401():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'assemble_words', 'staged_audio_invalid') == None


def test_b02_c01402():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'assemble_words', 'unknown') == None


def test_b02_c01403():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'assemble_words', 'unsupported_language') == None


def test_b02_c01404():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'assemble_words', 'vad_bounds') == None


def test_b02_c01405():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c01406():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'assemble_words', 'vad_order') == None


def test_b02_c01407():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'assemble_words', 'word_clock') == None


def test_b02_c01408():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'assemble_words', 'word_sequence') == None


def test_b02_c01409():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'assemble_words', 'word_shape') == None


def test_b02_c01410():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'assemble_words', 'unclassified') == None


def test_b02_c01411():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'fetch_decode', 'decode_payload_invalid') == None


def test_b02_c01412():
    assert (
        decode_payload_failure_reason(_make('b_JSONDecodeError'), 'fetch_decode', 'decoded_duration_mismatch') == None
    )


def test_b02_c01413():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'fetch_decode', 'empty_asr') == None


def test_b02_c01414():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c01415():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'fetch_decode', 'outside_admitted_source') == None


def test_b02_c01416():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'fetch_decode', 'persist_payload_invalid') == None


def test_b02_c01417():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'fetch_decode', 'retained_audio_invalid') == None


def test_b02_c01418():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c01419():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'fetch_decode', 'unknown') == None


def test_b02_c01420():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c01421():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c01422():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c01423():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'fetch_decode', 'vad_order') == None


def test_b02_c01424():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'fetch_decode', 'word_clock') == None


def test_b02_c01425():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'fetch_decode', 'word_sequence') == None


def test_b02_c01426():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'fetch_decode', 'word_shape') == None


def test_b02_c01427():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'fetch_decode', 'unclassified') == POISON


def test_b02_c01428():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'persist', 'decode_payload_invalid') == None


def test_b02_c01429():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c01430():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'persist', 'empty_asr') == None


def test_b02_c01431():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'persist', 'no_owned_words') == None


def test_b02_c01432():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'persist', 'outside_admitted_source') == None


def test_b02_c01433():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'persist', 'persist_payload_invalid') == None


def test_b02_c01434():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'persist', 'retained_audio_invalid') == None


def test_b02_c01435():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'persist', 'staged_audio_invalid') == None


def test_b02_c01436():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'persist', 'unknown') == None


def test_b02_c01437():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'persist', 'unsupported_language') == None


def test_b02_c01438():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'persist', 'vad_bounds') == None


def test_b02_c01439():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'persist', 'vad_nonfinite') == None


def test_b02_c01440():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'persist', 'vad_order') == None


def test_b02_c01441():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'persist', 'word_clock') == None


def test_b02_c01442():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'persist', 'word_sequence') == None


def test_b02_c01443():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'persist', 'word_shape') == None


def test_b02_c01444():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'persist', 'unclassified') == None


def test_b02_c01445():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c01446():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'vad_windows', 'decoded_duration_mismatch') == None


def test_b02_c01447():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'vad_windows', 'empty_asr') == None


def test_b02_c01448():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'vad_windows', 'no_owned_words') == None


def test_b02_c01449():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'vad_windows', 'outside_admitted_source') == None


def test_b02_c01450():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'vad_windows', 'persist_payload_invalid') == None


def test_b02_c01451():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c01452():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c01453():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'vad_windows', 'unknown') == None


def test_b02_c01454():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'vad_windows', 'unsupported_language') == None


def test_b02_c01455():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'vad_windows', 'vad_bounds') == None


def test_b02_c01456():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c01457():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'vad_windows', 'vad_order') == None


def test_b02_c01458():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'vad_windows', 'word_clock') == None


def test_b02_c01459():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'vad_windows', 'word_sequence') == None


def test_b02_c01460():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'vad_windows', 'word_shape') == None


def test_b02_c01461():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'vad_windows', 'unclassified') == None


def test_b02_c01462():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c01463():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'word_clocks', 'decoded_duration_mismatch') == None


def test_b02_c01464():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'word_clocks', 'empty_asr') == None


def test_b02_c01465():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'word_clocks', 'no_owned_words') == None


def test_b02_c01466():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'word_clocks', 'outside_admitted_source') == None


def test_b02_c01467():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'word_clocks', 'persist_payload_invalid') == None


def test_b02_c01468():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c01469():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c01470():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'word_clocks', 'unknown') == None


def test_b02_c01471():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'word_clocks', 'unsupported_language') == None


def test_b02_c01472():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'word_clocks', 'vad_bounds') == None


def test_b02_c01473():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c01474():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'word_clocks', 'vad_order') == None


def test_b02_c01475():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'word_clocks', 'word_clock') == None


def test_b02_c01476():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'word_clocks', 'word_sequence') == None


def test_b02_c01477():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'word_clocks', 'word_shape') == None


def test_b02_c01478():
    assert decode_payload_failure_reason(_make('b_JSONDecodeError'), 'word_clocks', 'unclassified') == None


def test_b02_c01479():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'asr_recovery', 'decode_payload_invalid') == None


def test_b02_c01480():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'asr_recovery', 'decoded_duration_mismatch') == None


def test_b02_c01481():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'asr_recovery', 'empty_asr') == None


def test_b02_c01482():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c01483():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'asr_recovery', 'outside_admitted_source') == None


def test_b02_c01484():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'asr_recovery', 'persist_payload_invalid') == None


def test_b02_c01485():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'asr_recovery', 'retained_audio_invalid') == None


def test_b02_c01486():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c01487():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'asr_recovery', 'unknown') == None


def test_b02_c01488():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c01489():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c01490():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c01491():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'asr_recovery', 'vad_order') == None


def test_b02_c01492():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'asr_recovery', 'word_clock') == None


def test_b02_c01493():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'asr_recovery', 'word_sequence') == None


def test_b02_c01494():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'asr_recovery', 'word_shape') == None


def test_b02_c01495():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'asr_recovery', 'unclassified') == None


def test_b02_c01496():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'assemble_words', 'decode_payload_invalid') == None


def test_b02_c01497():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'assemble_words', 'decoded_duration_mismatch') == None


def test_b02_c01498():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'assemble_words', 'empty_asr') == None


def test_b02_c01499():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'assemble_words', 'no_owned_words') == None


def test_b02_c01500():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'assemble_words', 'outside_admitted_source') == None


def test_b02_c01501():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'assemble_words', 'persist_payload_invalid') == None


def test_b02_c01502():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'assemble_words', 'retained_audio_invalid') == None


def test_b02_c01503():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'assemble_words', 'staged_audio_invalid') == None


def test_b02_c01504():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'assemble_words', 'unknown') == None


def test_b02_c01505():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'assemble_words', 'unsupported_language') == None


def test_b02_c01506():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'assemble_words', 'vad_bounds') == None


def test_b02_c01507():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c01508():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'assemble_words', 'vad_order') == None


def test_b02_c01509():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'assemble_words', 'word_clock') == None


def test_b02_c01510():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'assemble_words', 'word_sequence') == None


def test_b02_c01511():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'assemble_words', 'word_shape') == None


def test_b02_c01512():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'assemble_words', 'unclassified') == None


def test_b02_c01513():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'fetch_decode', 'decode_payload_invalid') == None


def test_b02_c01514():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'fetch_decode', 'decoded_duration_mismatch') == None


def test_b02_c01515():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'fetch_decode', 'empty_asr') == None


def test_b02_c01516():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c01517():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'fetch_decode', 'outside_admitted_source') == None


def test_b02_c01518():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'fetch_decode', 'persist_payload_invalid') == None


def test_b02_c01519():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'fetch_decode', 'retained_audio_invalid') == None


def test_b02_c01520():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c01521():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'fetch_decode', 'unknown') == None


def test_b02_c01522():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c01523():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c01524():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c01525():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'fetch_decode', 'vad_order') == None


def test_b02_c01526():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'fetch_decode', 'word_clock') == None


def test_b02_c01527():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'fetch_decode', 'word_sequence') == None


def test_b02_c01528():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'fetch_decode', 'word_shape') == None


def test_b02_c01529():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'fetch_decode', 'unclassified') == None


def test_b02_c01530():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'persist', 'decode_payload_invalid') == None


def test_b02_c01531():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c01532():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'persist', 'empty_asr') == None


def test_b02_c01533():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'persist', 'no_owned_words') == None


def test_b02_c01534():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'persist', 'outside_admitted_source') == None


def test_b02_c01535():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'persist', 'persist_payload_invalid') == None


def test_b02_c01536():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'persist', 'retained_audio_invalid') == None


def test_b02_c01537():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'persist', 'staged_audio_invalid') == None


def test_b02_c01538():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'persist', 'unknown') == None


def test_b02_c01539():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'persist', 'unsupported_language') == None


def test_b02_c01540():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'persist', 'vad_bounds') == None


def test_b02_c01541():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'persist', 'vad_nonfinite') == None


def test_b02_c01542():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'persist', 'vad_order') == None


def test_b02_c01543():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'persist', 'word_clock') == None


def test_b02_c01544():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'persist', 'word_sequence') == None


def test_b02_c01545():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'persist', 'word_shape') == None


def test_b02_c01546():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'persist', 'unclassified') == None


def test_b02_c01547():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c01548():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'vad_windows', 'decoded_duration_mismatch') == None


def test_b02_c01549():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'vad_windows', 'empty_asr') == None


def test_b02_c01550():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'vad_windows', 'no_owned_words') == None


def test_b02_c01551():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'vad_windows', 'outside_admitted_source') == None


def test_b02_c01552():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'vad_windows', 'persist_payload_invalid') == None


def test_b02_c01553():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c01554():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c01555():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'vad_windows', 'unknown') == None


def test_b02_c01556():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'vad_windows', 'unsupported_language') == None


def test_b02_c01557():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'vad_windows', 'vad_bounds') == None


def test_b02_c01558():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c01559():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'vad_windows', 'vad_order') == None


def test_b02_c01560():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'vad_windows', 'word_clock') == None


def test_b02_c01561():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'vad_windows', 'word_sequence') == None


def test_b02_c01562():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'vad_windows', 'word_shape') == None


def test_b02_c01563():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'vad_windows', 'unclassified') == None


def test_b02_c01564():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c01565():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'word_clocks', 'decoded_duration_mismatch') == None


def test_b02_c01566():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'word_clocks', 'empty_asr') == None


def test_b02_c01567():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'word_clocks', 'no_owned_words') == None


def test_b02_c01568():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'word_clocks', 'outside_admitted_source') == None


def test_b02_c01569():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'word_clocks', 'persist_payload_invalid') == None


def test_b02_c01570():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c01571():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c01572():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'word_clocks', 'unknown') == None


def test_b02_c01573():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'word_clocks', 'unsupported_language') == None


def test_b02_c01574():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'word_clocks', 'vad_bounds') == None


def test_b02_c01575():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c01576():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'word_clocks', 'vad_order') == None


def test_b02_c01577():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'word_clocks', 'word_clock') == None


def test_b02_c01578():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'word_clocks', 'word_sequence') == None


def test_b02_c01579():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'word_clocks', 'word_shape') == None


def test_b02_c01580():
    assert decode_payload_failure_reason(_make('b_KeyError'), 'word_clocks', 'unclassified') == None


def test_b02_c01581():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'asr_recovery', 'decode_payload_invalid') == None


def test_b02_c01582():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'asr_recovery', 'decoded_duration_mismatch') == None


def test_b02_c01583():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'asr_recovery', 'empty_asr') == None


def test_b02_c01584():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c01585():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'asr_recovery', 'outside_admitted_source') == None


def test_b02_c01586():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'asr_recovery', 'persist_payload_invalid') == None


def test_b02_c01587():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'asr_recovery', 'retained_audio_invalid') == None


def test_b02_c01588():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c01589():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'asr_recovery', 'unknown') == None


def test_b02_c01590():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c01591():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c01592():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c01593():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'asr_recovery', 'vad_order') == None


def test_b02_c01594():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'asr_recovery', 'word_clock') == None


def test_b02_c01595():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'asr_recovery', 'word_sequence') == None


def test_b02_c01596():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'asr_recovery', 'word_shape') == None


def test_b02_c01597():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'asr_recovery', 'unclassified') == None


def test_b02_c01598():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'assemble_words', 'decode_payload_invalid') == None


def test_b02_c01599():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'assemble_words', 'decoded_duration_mismatch') == None


def test_b02_c01600():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'assemble_words', 'empty_asr') == None


def test_b02_c01601():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'assemble_words', 'no_owned_words') == None


def test_b02_c01602():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'assemble_words', 'outside_admitted_source') == None


def test_b02_c01603():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'assemble_words', 'persist_payload_invalid') == None


def test_b02_c01604():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'assemble_words', 'retained_audio_invalid') == None


def test_b02_c01605():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'assemble_words', 'staged_audio_invalid') == None


def test_b02_c01606():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'assemble_words', 'unknown') == None


def test_b02_c01607():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'assemble_words', 'unsupported_language') == None


def test_b02_c01608():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'assemble_words', 'vad_bounds') == None


def test_b02_c01609():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c01610():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'assemble_words', 'vad_order') == None


def test_b02_c01611():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'assemble_words', 'word_clock') == None


def test_b02_c01612():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'assemble_words', 'word_sequence') == None


def test_b02_c01613():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'assemble_words', 'word_shape') == None


def test_b02_c01614():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'assemble_words', 'unclassified') == None


def test_b02_c01615():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'fetch_decode', 'decode_payload_invalid') == None


def test_b02_c01616():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'fetch_decode', 'decoded_duration_mismatch') == None


def test_b02_c01617():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'fetch_decode', 'empty_asr') == None


def test_b02_c01618():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c01619():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'fetch_decode', 'outside_admitted_source') == None


def test_b02_c01620():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'fetch_decode', 'persist_payload_invalid') == None


def test_b02_c01621():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'fetch_decode', 'retained_audio_invalid') == None


def test_b02_c01622():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c01623():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'fetch_decode', 'unknown') == None


def test_b02_c01624():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c01625():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c01626():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c01627():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'fetch_decode', 'vad_order') == None


def test_b02_c01628():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'fetch_decode', 'word_clock') == None


def test_b02_c01629():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'fetch_decode', 'word_sequence') == None


def test_b02_c01630():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'fetch_decode', 'word_shape') == None


def test_b02_c01631():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'fetch_decode', 'unclassified') == None


def test_b02_c01632():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'persist', 'decode_payload_invalid') == None


def test_b02_c01633():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c01634():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'persist', 'empty_asr') == None


def test_b02_c01635():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'persist', 'no_owned_words') == None


def test_b02_c01636():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'persist', 'outside_admitted_source') == None


def test_b02_c01637():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'persist', 'persist_payload_invalid') == None


def test_b02_c01638():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'persist', 'retained_audio_invalid') == None


def test_b02_c01639():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'persist', 'staged_audio_invalid') == None


def test_b02_c01640():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'persist', 'unknown') == None


def test_b02_c01641():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'persist', 'unsupported_language') == None


def test_b02_c01642():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'persist', 'vad_bounds') == None


def test_b02_c01643():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'persist', 'vad_nonfinite') == None


def test_b02_c01644():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'persist', 'vad_order') == None


def test_b02_c01645():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'persist', 'word_clock') == None


def test_b02_c01646():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'persist', 'word_sequence') == None


def test_b02_c01647():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'persist', 'word_shape') == None


def test_b02_c01648():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'persist', 'unclassified') == None


def test_b02_c01649():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c01650():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'vad_windows', 'decoded_duration_mismatch') == None


def test_b02_c01651():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'vad_windows', 'empty_asr') == None


def test_b02_c01652():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'vad_windows', 'no_owned_words') == None


def test_b02_c01653():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'vad_windows', 'outside_admitted_source') == None


def test_b02_c01654():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'vad_windows', 'persist_payload_invalid') == None


def test_b02_c01655():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c01656():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c01657():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'vad_windows', 'unknown') == None


def test_b02_c01658():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'vad_windows', 'unsupported_language') == None


def test_b02_c01659():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'vad_windows', 'vad_bounds') == None


def test_b02_c01660():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c01661():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'vad_windows', 'vad_order') == None


def test_b02_c01662():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'vad_windows', 'word_clock') == None


def test_b02_c01663():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'vad_windows', 'word_sequence') == None


def test_b02_c01664():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'vad_windows', 'word_shape') == None


def test_b02_c01665():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'vad_windows', 'unclassified') == None


def test_b02_c01666():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c01667():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'word_clocks', 'decoded_duration_mismatch') == None


def test_b02_c01668():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'word_clocks', 'empty_asr') == None


def test_b02_c01669():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'word_clocks', 'no_owned_words') == None


def test_b02_c01670():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'word_clocks', 'outside_admitted_source') == None


def test_b02_c01671():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'word_clocks', 'persist_payload_invalid') == None


def test_b02_c01672():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c01673():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c01674():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'word_clocks', 'unknown') == None


def test_b02_c01675():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'word_clocks', 'unsupported_language') == None


def test_b02_c01676():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'word_clocks', 'vad_bounds') == None


def test_b02_c01677():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c01678():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'word_clocks', 'vad_order') == None


def test_b02_c01679():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'word_clocks', 'word_clock') == None


def test_b02_c01680():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'word_clocks', 'word_sequence') == None


def test_b02_c01681():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'word_clocks', 'word_shape') == None


def test_b02_c01682():
    assert decode_payload_failure_reason(_make('b_LookupError'), 'word_clocks', 'unclassified') == None


def test_b02_c01683():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'asr_recovery', 'decode_payload_invalid') == None


def test_b02_c01684():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'asr_recovery', 'decoded_duration_mismatch') == None


def test_b02_c01685():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'asr_recovery', 'empty_asr') == None


def test_b02_c01686():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c01687():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'asr_recovery', 'outside_admitted_source') == None


def test_b02_c01688():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'asr_recovery', 'persist_payload_invalid') == None


def test_b02_c01689():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'asr_recovery', 'retained_audio_invalid') == None


def test_b02_c01690():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c01691():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'asr_recovery', 'unknown') == None


def test_b02_c01692():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c01693():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c01694():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c01695():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'asr_recovery', 'vad_order') == None


def test_b02_c01696():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'asr_recovery', 'word_clock') == None


def test_b02_c01697():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'asr_recovery', 'word_sequence') == None


def test_b02_c01698():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'asr_recovery', 'word_shape') == None


def test_b02_c01699():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'asr_recovery', 'unclassified') == None


def test_b02_c01700():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'assemble_words', 'decode_payload_invalid') == None


def test_b02_c01701():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'assemble_words', 'decoded_duration_mismatch') == None


def test_b02_c01702():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'assemble_words', 'empty_asr') == None


def test_b02_c01703():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'assemble_words', 'no_owned_words') == None


def test_b02_c01704():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'assemble_words', 'outside_admitted_source') == None


def test_b02_c01705():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'assemble_words', 'persist_payload_invalid') == None


def test_b02_c01706():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'assemble_words', 'retained_audio_invalid') == None


def test_b02_c01707():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'assemble_words', 'staged_audio_invalid') == None


def test_b02_c01708():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'assemble_words', 'unknown') == None


def test_b02_c01709():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'assemble_words', 'unsupported_language') == None


def test_b02_c01710():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'assemble_words', 'vad_bounds') == None


def test_b02_c01711():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c01712():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'assemble_words', 'vad_order') == None


def test_b02_c01713():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'assemble_words', 'word_clock') == None


def test_b02_c01714():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'assemble_words', 'word_sequence') == None


def test_b02_c01715():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'assemble_words', 'word_shape') == None


def test_b02_c01716():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'assemble_words', 'unclassified') == None


def test_b02_c01717():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'fetch_decode', 'decode_payload_invalid') == None


def test_b02_c01718():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'fetch_decode', 'decoded_duration_mismatch') == None


def test_b02_c01719():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'fetch_decode', 'empty_asr') == None


def test_b02_c01720():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c01721():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'fetch_decode', 'outside_admitted_source') == None


def test_b02_c01722():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'fetch_decode', 'persist_payload_invalid') == None


def test_b02_c01723():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'fetch_decode', 'retained_audio_invalid') == None


def test_b02_c01724():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c01725():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'fetch_decode', 'unknown') == None


def test_b02_c01726():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c01727():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c01728():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c01729():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'fetch_decode', 'vad_order') == None


def test_b02_c01730():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'fetch_decode', 'word_clock') == None


def test_b02_c01731():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'fetch_decode', 'word_sequence') == None


def test_b02_c01732():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'fetch_decode', 'word_shape') == None


def test_b02_c01733():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'fetch_decode', 'unclassified') == None


def test_b02_c01734():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'persist', 'decode_payload_invalid') == None


def test_b02_c01735():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c01736():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'persist', 'empty_asr') == None


def test_b02_c01737():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'persist', 'no_owned_words') == None


def test_b02_c01738():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'persist', 'outside_admitted_source') == None


def test_b02_c01739():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'persist', 'persist_payload_invalid') == None


def test_b02_c01740():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'persist', 'retained_audio_invalid') == None


def test_b02_c01741():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'persist', 'staged_audio_invalid') == None


def test_b02_c01742():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'persist', 'unknown') == None


def test_b02_c01743():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'persist', 'unsupported_language') == None


def test_b02_c01744():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'persist', 'vad_bounds') == None


def test_b02_c01745():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'persist', 'vad_nonfinite') == None


def test_b02_c01746():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'persist', 'vad_order') == None


def test_b02_c01747():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'persist', 'word_clock') == None


def test_b02_c01748():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'persist', 'word_sequence') == None


def test_b02_c01749():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'persist', 'word_shape') == None


def test_b02_c01750():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'persist', 'unclassified') == None


def test_b02_c01751():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c01752():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'vad_windows', 'decoded_duration_mismatch') == None


def test_b02_c01753():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'vad_windows', 'empty_asr') == None


def test_b02_c01754():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'vad_windows', 'no_owned_words') == None


def test_b02_c01755():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'vad_windows', 'outside_admitted_source') == None


def test_b02_c01756():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'vad_windows', 'persist_payload_invalid') == None


def test_b02_c01757():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c01758():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c01759():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'vad_windows', 'unknown') == None


def test_b02_c01760():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'vad_windows', 'unsupported_language') == None


def test_b02_c01761():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'vad_windows', 'vad_bounds') == None


def test_b02_c01762():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c01763():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'vad_windows', 'vad_order') == None


def test_b02_c01764():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'vad_windows', 'word_clock') == None


def test_b02_c01765():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'vad_windows', 'word_sequence') == None


def test_b02_c01766():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'vad_windows', 'word_shape') == None


def test_b02_c01767():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'vad_windows', 'unclassified') == None


def test_b02_c01768():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c01769():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'word_clocks', 'decoded_duration_mismatch') == None


def test_b02_c01770():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'word_clocks', 'empty_asr') == None


def test_b02_c01771():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'word_clocks', 'no_owned_words') == None


def test_b02_c01772():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'word_clocks', 'outside_admitted_source') == None


def test_b02_c01773():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'word_clocks', 'persist_payload_invalid') == None


def test_b02_c01774():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c01775():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c01776():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'word_clocks', 'unknown') == None


def test_b02_c01777():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'word_clocks', 'unsupported_language') == None


def test_b02_c01778():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'word_clocks', 'vad_bounds') == None


def test_b02_c01779():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c01780():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'word_clocks', 'vad_order') == None


def test_b02_c01781():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'word_clocks', 'word_clock') == None


def test_b02_c01782():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'word_clocks', 'word_sequence') == None


def test_b02_c01783():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'word_clocks', 'word_shape') == None


def test_b02_c01784():
    assert decode_payload_failure_reason(_make('b_MemoryError'), 'word_clocks', 'unclassified') == None


def test_b02_c01785():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'asr_recovery', 'decode_payload_invalid') == None
    )


def test_b02_c01786():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'asr_recovery', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c01787():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'asr_recovery', 'empty_asr') == None


def test_b02_c01788():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c01789():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'asr_recovery', 'outside_admitted_source') == None
    )


def test_b02_c01790():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'asr_recovery', 'persist_payload_invalid') == None
    )


def test_b02_c01791():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'asr_recovery', 'retained_audio_invalid') == None
    )


def test_b02_c01792():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c01793():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'asr_recovery', 'unknown') == None


def test_b02_c01794():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c01795():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c01796():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c01797():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'asr_recovery', 'vad_order') == None


def test_b02_c01798():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'asr_recovery', 'word_clock') == None


def test_b02_c01799():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'asr_recovery', 'word_sequence') == None


def test_b02_c01800():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'asr_recovery', 'word_shape') == None


def test_b02_c01801():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'asr_recovery', 'unclassified') == None


def test_b02_c01802():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'assemble_words', 'decode_payload_invalid')
        == None
    )


def test_b02_c01803():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'assemble_words', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c01804():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'assemble_words', 'empty_asr') == None


def test_b02_c01805():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'assemble_words', 'no_owned_words') == None


def test_b02_c01806():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'assemble_words', 'outside_admitted_source')
        == None
    )


def test_b02_c01807():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'assemble_words', 'persist_payload_invalid')
        == None
    )


def test_b02_c01808():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'assemble_words', 'retained_audio_invalid')
        == None
    )


def test_b02_c01809():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'assemble_words', 'staged_audio_invalid') == None
    )


def test_b02_c01810():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'assemble_words', 'unknown') == None


def test_b02_c01811():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'assemble_words', 'unsupported_language') == None
    )


def test_b02_c01812():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'assemble_words', 'vad_bounds') == None


def test_b02_c01813():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c01814():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'assemble_words', 'vad_order') == None


def test_b02_c01815():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'assemble_words', 'word_clock') == None


def test_b02_c01816():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'assemble_words', 'word_sequence') == None


def test_b02_c01817():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'assemble_words', 'word_shape') == None


def test_b02_c01818():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'assemble_words', 'unclassified') == None


def test_b02_c01819():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'fetch_decode', 'decode_payload_invalid') == None
    )


def test_b02_c01820():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'fetch_decode', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c01821():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'fetch_decode', 'empty_asr') == None


def test_b02_c01822():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c01823():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'fetch_decode', 'outside_admitted_source') == None
    )


def test_b02_c01824():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'fetch_decode', 'persist_payload_invalid') == None
    )


def test_b02_c01825():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'fetch_decode', 'retained_audio_invalid') == None
    )


def test_b02_c01826():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c01827():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'fetch_decode', 'unknown') == None


def test_b02_c01828():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c01829():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c01830():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c01831():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'fetch_decode', 'vad_order') == None


def test_b02_c01832():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'fetch_decode', 'word_clock') == None


def test_b02_c01833():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'fetch_decode', 'word_sequence') == None


def test_b02_c01834():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'fetch_decode', 'word_shape') == None


def test_b02_c01835():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'fetch_decode', 'unclassified') == None


def test_b02_c01836():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'persist', 'decode_payload_invalid') == None


def test_b02_c01837():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c01838():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'persist', 'empty_asr') == None


def test_b02_c01839():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'persist', 'no_owned_words') == None


def test_b02_c01840():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'persist', 'outside_admitted_source') == None


def test_b02_c01841():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'persist', 'persist_payload_invalid') == None


def test_b02_c01842():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'persist', 'retained_audio_invalid') == None


def test_b02_c01843():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'persist', 'staged_audio_invalid') == None


def test_b02_c01844():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'persist', 'unknown') == None


def test_b02_c01845():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'persist', 'unsupported_language') == None


def test_b02_c01846():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'persist', 'vad_bounds') == None


def test_b02_c01847():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'persist', 'vad_nonfinite') == None


def test_b02_c01848():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'persist', 'vad_order') == None


def test_b02_c01849():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'persist', 'word_clock') == None


def test_b02_c01850():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'persist', 'word_sequence') == None


def test_b02_c01851():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'persist', 'word_shape') == None


def test_b02_c01852():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'persist', 'unclassified') == None


def test_b02_c01853():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'vad_windows', 'decode_payload_invalid') == None
    )


def test_b02_c01854():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'vad_windows', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c01855():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'vad_windows', 'empty_asr') == None


def test_b02_c01856():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'vad_windows', 'no_owned_words') == None


def test_b02_c01857():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'vad_windows', 'outside_admitted_source') == None
    )


def test_b02_c01858():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'vad_windows', 'persist_payload_invalid') == None
    )


def test_b02_c01859():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'vad_windows', 'retained_audio_invalid') == None
    )


def test_b02_c01860():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c01861():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'vad_windows', 'unknown') == None


def test_b02_c01862():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'vad_windows', 'unsupported_language') == None


def test_b02_c01863():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'vad_windows', 'vad_bounds') == None


def test_b02_c01864():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c01865():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'vad_windows', 'vad_order') == None


def test_b02_c01866():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'vad_windows', 'word_clock') == None


def test_b02_c01867():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'vad_windows', 'word_sequence') == None


def test_b02_c01868():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'vad_windows', 'word_shape') == None


def test_b02_c01869():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'vad_windows', 'unclassified') == None


def test_b02_c01870():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'word_clocks', 'decode_payload_invalid') == None
    )


def test_b02_c01871():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'word_clocks', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c01872():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'word_clocks', 'empty_asr') == None


def test_b02_c01873():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'word_clocks', 'no_owned_words') == None


def test_b02_c01874():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'word_clocks', 'outside_admitted_source') == None
    )


def test_b02_c01875():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'word_clocks', 'persist_payload_invalid') == None
    )


def test_b02_c01876():
    assert (
        decode_payload_failure_reason(_make('b_NotImplementedError'), 'word_clocks', 'retained_audio_invalid') == None
    )


def test_b02_c01877():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c01878():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'word_clocks', 'unknown') == None


def test_b02_c01879():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'word_clocks', 'unsupported_language') == None


def test_b02_c01880():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'word_clocks', 'vad_bounds') == None


def test_b02_c01881():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c01882():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'word_clocks', 'vad_order') == None


def test_b02_c01883():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'word_clocks', 'word_clock') == None


def test_b02_c01884():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'word_clocks', 'word_sequence') == None


def test_b02_c01885():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'word_clocks', 'word_shape') == None


def test_b02_c01886():
    assert decode_payload_failure_reason(_make('b_NotImplementedError'), 'word_clocks', 'unclassified') == None


def test_b02_c01887():
    assert decode_payload_failure_reason(_make('b_OSError'), 'asr_recovery', 'decode_payload_invalid') == None


def test_b02_c01888():
    assert decode_payload_failure_reason(_make('b_OSError'), 'asr_recovery', 'decoded_duration_mismatch') == None


def test_b02_c01889():
    assert decode_payload_failure_reason(_make('b_OSError'), 'asr_recovery', 'empty_asr') == None


def test_b02_c01890():
    assert decode_payload_failure_reason(_make('b_OSError'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c01891():
    assert decode_payload_failure_reason(_make('b_OSError'), 'asr_recovery', 'outside_admitted_source') == None


def test_b02_c01892():
    assert decode_payload_failure_reason(_make('b_OSError'), 'asr_recovery', 'persist_payload_invalid') == None


def test_b02_c01893():
    assert decode_payload_failure_reason(_make('b_OSError'), 'asr_recovery', 'retained_audio_invalid') == None


def test_b02_c01894():
    assert decode_payload_failure_reason(_make('b_OSError'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c01895():
    assert decode_payload_failure_reason(_make('b_OSError'), 'asr_recovery', 'unknown') == None


def test_b02_c01896():
    assert decode_payload_failure_reason(_make('b_OSError'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c01897():
    assert decode_payload_failure_reason(_make('b_OSError'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c01898():
    assert decode_payload_failure_reason(_make('b_OSError'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c01899():
    assert decode_payload_failure_reason(_make('b_OSError'), 'asr_recovery', 'vad_order') == None


def test_b02_c01900():
    assert decode_payload_failure_reason(_make('b_OSError'), 'asr_recovery', 'word_clock') == None


def test_b02_c01901():
    assert decode_payload_failure_reason(_make('b_OSError'), 'asr_recovery', 'word_sequence') == None


def test_b02_c01902():
    assert decode_payload_failure_reason(_make('b_OSError'), 'asr_recovery', 'word_shape') == None


def test_b02_c01903():
    assert decode_payload_failure_reason(_make('b_OSError'), 'asr_recovery', 'unclassified') == None


def test_b02_c01904():
    assert decode_payload_failure_reason(_make('b_OSError'), 'assemble_words', 'decode_payload_invalid') == None


def test_b02_c01905():
    assert decode_payload_failure_reason(_make('b_OSError'), 'assemble_words', 'decoded_duration_mismatch') == None


def test_b02_c01906():
    assert decode_payload_failure_reason(_make('b_OSError'), 'assemble_words', 'empty_asr') == None


def test_b02_c01907():
    assert decode_payload_failure_reason(_make('b_OSError'), 'assemble_words', 'no_owned_words') == None


def test_b02_c01908():
    assert decode_payload_failure_reason(_make('b_OSError'), 'assemble_words', 'outside_admitted_source') == None


def test_b02_c01909():
    assert decode_payload_failure_reason(_make('b_OSError'), 'assemble_words', 'persist_payload_invalid') == None


def test_b02_c01910():
    assert decode_payload_failure_reason(_make('b_OSError'), 'assemble_words', 'retained_audio_invalid') == None


def test_b02_c01911():
    assert decode_payload_failure_reason(_make('b_OSError'), 'assemble_words', 'staged_audio_invalid') == None


def test_b02_c01912():
    assert decode_payload_failure_reason(_make('b_OSError'), 'assemble_words', 'unknown') == None


def test_b02_c01913():
    assert decode_payload_failure_reason(_make('b_OSError'), 'assemble_words', 'unsupported_language') == None


def test_b02_c01914():
    assert decode_payload_failure_reason(_make('b_OSError'), 'assemble_words', 'vad_bounds') == None


def test_b02_c01915():
    assert decode_payload_failure_reason(_make('b_OSError'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c01916():
    assert decode_payload_failure_reason(_make('b_OSError'), 'assemble_words', 'vad_order') == None


def test_b02_c01917():
    assert decode_payload_failure_reason(_make('b_OSError'), 'assemble_words', 'word_clock') == None


def test_b02_c01918():
    assert decode_payload_failure_reason(_make('b_OSError'), 'assemble_words', 'word_sequence') == None


def test_b02_c01919():
    assert decode_payload_failure_reason(_make('b_OSError'), 'assemble_words', 'word_shape') == None


def test_b02_c01920():
    assert decode_payload_failure_reason(_make('b_OSError'), 'assemble_words', 'unclassified') == None


def test_b02_c01921():
    assert decode_payload_failure_reason(_make('b_OSError'), 'fetch_decode', 'decode_payload_invalid') == None


def test_b02_c01922():
    assert decode_payload_failure_reason(_make('b_OSError'), 'fetch_decode', 'decoded_duration_mismatch') == None


def test_b02_c01923():
    assert decode_payload_failure_reason(_make('b_OSError'), 'fetch_decode', 'empty_asr') == None


def test_b02_c01924():
    assert decode_payload_failure_reason(_make('b_OSError'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c01925():
    assert decode_payload_failure_reason(_make('b_OSError'), 'fetch_decode', 'outside_admitted_source') == None


def test_b02_c01926():
    assert decode_payload_failure_reason(_make('b_OSError'), 'fetch_decode', 'persist_payload_invalid') == None


def test_b02_c01927():
    assert decode_payload_failure_reason(_make('b_OSError'), 'fetch_decode', 'retained_audio_invalid') == None


def test_b02_c01928():
    assert decode_payload_failure_reason(_make('b_OSError'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c01929():
    assert decode_payload_failure_reason(_make('b_OSError'), 'fetch_decode', 'unknown') == None


def test_b02_c01930():
    assert decode_payload_failure_reason(_make('b_OSError'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c01931():
    assert decode_payload_failure_reason(_make('b_OSError'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c01932():
    assert decode_payload_failure_reason(_make('b_OSError'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c01933():
    assert decode_payload_failure_reason(_make('b_OSError'), 'fetch_decode', 'vad_order') == None


def test_b02_c01934():
    assert decode_payload_failure_reason(_make('b_OSError'), 'fetch_decode', 'word_clock') == None


def test_b02_c01935():
    assert decode_payload_failure_reason(_make('b_OSError'), 'fetch_decode', 'word_sequence') == None


def test_b02_c01936():
    assert decode_payload_failure_reason(_make('b_OSError'), 'fetch_decode', 'word_shape') == None


def test_b02_c01937():
    assert decode_payload_failure_reason(_make('b_OSError'), 'fetch_decode', 'unclassified') == None


def test_b02_c01938():
    assert decode_payload_failure_reason(_make('b_OSError'), 'persist', 'decode_payload_invalid') == None


def test_b02_c01939():
    assert decode_payload_failure_reason(_make('b_OSError'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c01940():
    assert decode_payload_failure_reason(_make('b_OSError'), 'persist', 'empty_asr') == None


def test_b02_c01941():
    assert decode_payload_failure_reason(_make('b_OSError'), 'persist', 'no_owned_words') == None


def test_b02_c01942():
    assert decode_payload_failure_reason(_make('b_OSError'), 'persist', 'outside_admitted_source') == None


def test_b02_c01943():
    assert decode_payload_failure_reason(_make('b_OSError'), 'persist', 'persist_payload_invalid') == None


def test_b02_c01944():
    assert decode_payload_failure_reason(_make('b_OSError'), 'persist', 'retained_audio_invalid') == None


def test_b02_c01945():
    assert decode_payload_failure_reason(_make('b_OSError'), 'persist', 'staged_audio_invalid') == None


def test_b02_c01946():
    assert decode_payload_failure_reason(_make('b_OSError'), 'persist', 'unknown') == None


def test_b02_c01947():
    assert decode_payload_failure_reason(_make('b_OSError'), 'persist', 'unsupported_language') == None


def test_b02_c01948():
    assert decode_payload_failure_reason(_make('b_OSError'), 'persist', 'vad_bounds') == None


def test_b02_c01949():
    assert decode_payload_failure_reason(_make('b_OSError'), 'persist', 'vad_nonfinite') == None


def test_b02_c01950():
    assert decode_payload_failure_reason(_make('b_OSError'), 'persist', 'vad_order') == None


def test_b02_c01951():
    assert decode_payload_failure_reason(_make('b_OSError'), 'persist', 'word_clock') == None


def test_b02_c01952():
    assert decode_payload_failure_reason(_make('b_OSError'), 'persist', 'word_sequence') == None


def test_b02_c01953():
    assert decode_payload_failure_reason(_make('b_OSError'), 'persist', 'word_shape') == None


def test_b02_c01954():
    assert decode_payload_failure_reason(_make('b_OSError'), 'persist', 'unclassified') == None


def test_b02_c01955():
    assert decode_payload_failure_reason(_make('b_OSError'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c01956():
    assert decode_payload_failure_reason(_make('b_OSError'), 'vad_windows', 'decoded_duration_mismatch') == None


def test_b02_c01957():
    assert decode_payload_failure_reason(_make('b_OSError'), 'vad_windows', 'empty_asr') == None


def test_b02_c01958():
    assert decode_payload_failure_reason(_make('b_OSError'), 'vad_windows', 'no_owned_words') == None


def test_b02_c01959():
    assert decode_payload_failure_reason(_make('b_OSError'), 'vad_windows', 'outside_admitted_source') == None


def test_b02_c01960():
    assert decode_payload_failure_reason(_make('b_OSError'), 'vad_windows', 'persist_payload_invalid') == None


def test_b02_c01961():
    assert decode_payload_failure_reason(_make('b_OSError'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c01962():
    assert decode_payload_failure_reason(_make('b_OSError'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c01963():
    assert decode_payload_failure_reason(_make('b_OSError'), 'vad_windows', 'unknown') == None


def test_b02_c01964():
    assert decode_payload_failure_reason(_make('b_OSError'), 'vad_windows', 'unsupported_language') == None


def test_b02_c01965():
    assert decode_payload_failure_reason(_make('b_OSError'), 'vad_windows', 'vad_bounds') == None


def test_b02_c01966():
    assert decode_payload_failure_reason(_make('b_OSError'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c01967():
    assert decode_payload_failure_reason(_make('b_OSError'), 'vad_windows', 'vad_order') == None


def test_b02_c01968():
    assert decode_payload_failure_reason(_make('b_OSError'), 'vad_windows', 'word_clock') == None


def test_b02_c01969():
    assert decode_payload_failure_reason(_make('b_OSError'), 'vad_windows', 'word_sequence') == None


def test_b02_c01970():
    assert decode_payload_failure_reason(_make('b_OSError'), 'vad_windows', 'word_shape') == None


def test_b02_c01971():
    assert decode_payload_failure_reason(_make('b_OSError'), 'vad_windows', 'unclassified') == None


def test_b02_c01972():
    assert decode_payload_failure_reason(_make('b_OSError'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c01973():
    assert decode_payload_failure_reason(_make('b_OSError'), 'word_clocks', 'decoded_duration_mismatch') == None


def test_b02_c01974():
    assert decode_payload_failure_reason(_make('b_OSError'), 'word_clocks', 'empty_asr') == None


def test_b02_c01975():
    assert decode_payload_failure_reason(_make('b_OSError'), 'word_clocks', 'no_owned_words') == None


def test_b02_c01976():
    assert decode_payload_failure_reason(_make('b_OSError'), 'word_clocks', 'outside_admitted_source') == None


def test_b02_c01977():
    assert decode_payload_failure_reason(_make('b_OSError'), 'word_clocks', 'persist_payload_invalid') == None


def test_b02_c01978():
    assert decode_payload_failure_reason(_make('b_OSError'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c01979():
    assert decode_payload_failure_reason(_make('b_OSError'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c01980():
    assert decode_payload_failure_reason(_make('b_OSError'), 'word_clocks', 'unknown') == None


def test_b02_c01981():
    assert decode_payload_failure_reason(_make('b_OSError'), 'word_clocks', 'unsupported_language') == None


def test_b02_c01982():
    assert decode_payload_failure_reason(_make('b_OSError'), 'word_clocks', 'vad_bounds') == None


def test_b02_c01983():
    assert decode_payload_failure_reason(_make('b_OSError'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c01984():
    assert decode_payload_failure_reason(_make('b_OSError'), 'word_clocks', 'vad_order') == None


def test_b02_c01985():
    assert decode_payload_failure_reason(_make('b_OSError'), 'word_clocks', 'word_clock') == None


def test_b02_c01986():
    assert decode_payload_failure_reason(_make('b_OSError'), 'word_clocks', 'word_sequence') == None


def test_b02_c01987():
    assert decode_payload_failure_reason(_make('b_OSError'), 'word_clocks', 'word_shape') == None


def test_b02_c01988():
    assert decode_payload_failure_reason(_make('b_OSError'), 'word_clocks', 'unclassified') == None


def test_b02_c01989():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'asr_recovery', 'decode_payload_invalid') == None


def test_b02_c01990():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'asr_recovery', 'decoded_duration_mismatch') == None


def test_b02_c01991():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'asr_recovery', 'empty_asr') == None


def test_b02_c01992():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c01993():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'asr_recovery', 'outside_admitted_source') == None


def test_b02_c01994():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'asr_recovery', 'persist_payload_invalid') == None


def test_b02_c01995():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'asr_recovery', 'retained_audio_invalid') == None


def test_b02_c01996():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c01997():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'asr_recovery', 'unknown') == None


def test_b02_c01998():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c01999():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c02000():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c02001():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'asr_recovery', 'vad_order') == None


def test_b02_c02002():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'asr_recovery', 'word_clock') == None


def test_b02_c02003():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'asr_recovery', 'word_sequence') == None


def test_b02_c02004():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'asr_recovery', 'word_shape') == None


def test_b02_c02005():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'asr_recovery', 'unclassified') == None


def test_b02_c02006():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'assemble_words', 'decode_payload_invalid') == None


def test_b02_c02007():
    assert (
        decode_payload_failure_reason(_make('b_OverflowError'), 'assemble_words', 'decoded_duration_mismatch') == None
    )


def test_b02_c02008():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'assemble_words', 'empty_asr') == None


def test_b02_c02009():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'assemble_words', 'no_owned_words') == None


def test_b02_c02010():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'assemble_words', 'outside_admitted_source') == None


def test_b02_c02011():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'assemble_words', 'persist_payload_invalid') == None


def test_b02_c02012():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'assemble_words', 'retained_audio_invalid') == None


def test_b02_c02013():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'assemble_words', 'staged_audio_invalid') == None


def test_b02_c02014():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'assemble_words', 'unknown') == None


def test_b02_c02015():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'assemble_words', 'unsupported_language') == None


def test_b02_c02016():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'assemble_words', 'vad_bounds') == None


def test_b02_c02017():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c02018():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'assemble_words', 'vad_order') == None


def test_b02_c02019():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'assemble_words', 'word_clock') == None


def test_b02_c02020():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'assemble_words', 'word_sequence') == None


def test_b02_c02021():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'assemble_words', 'word_shape') == None


def test_b02_c02022():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'assemble_words', 'unclassified') == None


def test_b02_c02023():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'fetch_decode', 'decode_payload_invalid') == None


def test_b02_c02024():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'fetch_decode', 'decoded_duration_mismatch') == None


def test_b02_c02025():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'fetch_decode', 'empty_asr') == None


def test_b02_c02026():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c02027():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'fetch_decode', 'outside_admitted_source') == None


def test_b02_c02028():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'fetch_decode', 'persist_payload_invalid') == None


def test_b02_c02029():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'fetch_decode', 'retained_audio_invalid') == None


def test_b02_c02030():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c02031():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'fetch_decode', 'unknown') == None


def test_b02_c02032():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c02033():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c02034():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c02035():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'fetch_decode', 'vad_order') == None


def test_b02_c02036():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'fetch_decode', 'word_clock') == None


def test_b02_c02037():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'fetch_decode', 'word_sequence') == None


def test_b02_c02038():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'fetch_decode', 'word_shape') == None


def test_b02_c02039():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'fetch_decode', 'unclassified') == None


def test_b02_c02040():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'persist', 'decode_payload_invalid') == None


def test_b02_c02041():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c02042():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'persist', 'empty_asr') == None


def test_b02_c02043():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'persist', 'no_owned_words') == None


def test_b02_c02044():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'persist', 'outside_admitted_source') == None


def test_b02_c02045():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'persist', 'persist_payload_invalid') == None


def test_b02_c02046():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'persist', 'retained_audio_invalid') == None


def test_b02_c02047():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'persist', 'staged_audio_invalid') == None


def test_b02_c02048():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'persist', 'unknown') == None


def test_b02_c02049():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'persist', 'unsupported_language') == None


def test_b02_c02050():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'persist', 'vad_bounds') == None


def test_b02_c02051():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'persist', 'vad_nonfinite') == None


def test_b02_c02052():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'persist', 'vad_order') == None


def test_b02_c02053():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'persist', 'word_clock') == None


def test_b02_c02054():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'persist', 'word_sequence') == None


def test_b02_c02055():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'persist', 'word_shape') == None


def test_b02_c02056():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'persist', 'unclassified') == None


def test_b02_c02057():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c02058():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'vad_windows', 'decoded_duration_mismatch') == None


def test_b02_c02059():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'vad_windows', 'empty_asr') == None


def test_b02_c02060():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'vad_windows', 'no_owned_words') == None


def test_b02_c02061():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'vad_windows', 'outside_admitted_source') == None


def test_b02_c02062():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'vad_windows', 'persist_payload_invalid') == None


def test_b02_c02063():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c02064():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c02065():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'vad_windows', 'unknown') == None


def test_b02_c02066():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'vad_windows', 'unsupported_language') == None


def test_b02_c02067():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'vad_windows', 'vad_bounds') == None


def test_b02_c02068():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c02069():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'vad_windows', 'vad_order') == None


def test_b02_c02070():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'vad_windows', 'word_clock') == None


def test_b02_c02071():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'vad_windows', 'word_sequence') == None


def test_b02_c02072():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'vad_windows', 'word_shape') == None


def test_b02_c02073():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'vad_windows', 'unclassified') == None


def test_b02_c02074():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c02075():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'word_clocks', 'decoded_duration_mismatch') == None


def test_b02_c02076():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'word_clocks', 'empty_asr') == None


def test_b02_c02077():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'word_clocks', 'no_owned_words') == None


def test_b02_c02078():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'word_clocks', 'outside_admitted_source') == None


def test_b02_c02079():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'word_clocks', 'persist_payload_invalid') == None


def test_b02_c02080():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c02081():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c02082():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'word_clocks', 'unknown') == None


def test_b02_c02083():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'word_clocks', 'unsupported_language') == None


def test_b02_c02084():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'word_clocks', 'vad_bounds') == None


def test_b02_c02085():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c02086():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'word_clocks', 'vad_order') == None


def test_b02_c02087():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'word_clocks', 'word_clock') == None


def test_b02_c02088():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'word_clocks', 'word_sequence') == None


def test_b02_c02089():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'word_clocks', 'word_shape') == None


def test_b02_c02090():
    assert decode_payload_failure_reason(_make('b_OverflowError'), 'word_clocks', 'unclassified') == None


def test_b02_c02091():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'asr_recovery', 'decode_payload_invalid') == None


def test_b02_c02092():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'asr_recovery', 'decoded_duration_mismatch') == None


def test_b02_c02093():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'asr_recovery', 'empty_asr') == None


def test_b02_c02094():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c02095():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'asr_recovery', 'outside_admitted_source') == None


def test_b02_c02096():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'asr_recovery', 'persist_payload_invalid') == None


def test_b02_c02097():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'asr_recovery', 'retained_audio_invalid') == None


def test_b02_c02098():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c02099():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'asr_recovery', 'unknown') == None


def test_b02_c02100():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c02101():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c02102():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c02103():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'asr_recovery', 'vad_order') == None


def test_b02_c02104():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'asr_recovery', 'word_clock') == None


def test_b02_c02105():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'asr_recovery', 'word_sequence') == None


def test_b02_c02106():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'asr_recovery', 'word_shape') == None


def test_b02_c02107():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'asr_recovery', 'unclassified') == None


def test_b02_c02108():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'assemble_words', 'decode_payload_invalid') == None


def test_b02_c02109():
    assert (
        decode_payload_failure_reason(_make('b_RecursionError'), 'assemble_words', 'decoded_duration_mismatch') == None
    )


def test_b02_c02110():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'assemble_words', 'empty_asr') == None


def test_b02_c02111():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'assemble_words', 'no_owned_words') == None


def test_b02_c02112():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'assemble_words', 'outside_admitted_source') == None


def test_b02_c02113():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'assemble_words', 'persist_payload_invalid') == None


def test_b02_c02114():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'assemble_words', 'retained_audio_invalid') == None


def test_b02_c02115():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'assemble_words', 'staged_audio_invalid') == None


def test_b02_c02116():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'assemble_words', 'unknown') == None


def test_b02_c02117():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'assemble_words', 'unsupported_language') == None


def test_b02_c02118():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'assemble_words', 'vad_bounds') == None


def test_b02_c02119():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c02120():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'assemble_words', 'vad_order') == None


def test_b02_c02121():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'assemble_words', 'word_clock') == None


def test_b02_c02122():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'assemble_words', 'word_sequence') == None


def test_b02_c02123():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'assemble_words', 'word_shape') == None


def test_b02_c02124():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'assemble_words', 'unclassified') == None


def test_b02_c02125():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'fetch_decode', 'decode_payload_invalid') == None


def test_b02_c02126():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'fetch_decode', 'decoded_duration_mismatch') == None


def test_b02_c02127():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'fetch_decode', 'empty_asr') == None


def test_b02_c02128():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c02129():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'fetch_decode', 'outside_admitted_source') == None


def test_b02_c02130():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'fetch_decode', 'persist_payload_invalid') == None


def test_b02_c02131():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'fetch_decode', 'retained_audio_invalid') == None


def test_b02_c02132():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c02133():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'fetch_decode', 'unknown') == None


def test_b02_c02134():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c02135():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c02136():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c02137():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'fetch_decode', 'vad_order') == None


def test_b02_c02138():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'fetch_decode', 'word_clock') == None


def test_b02_c02139():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'fetch_decode', 'word_sequence') == None


def test_b02_c02140():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'fetch_decode', 'word_shape') == None


def test_b02_c02141():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'fetch_decode', 'unclassified') == None


def test_b02_c02142():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'persist', 'decode_payload_invalid') == None


def test_b02_c02143():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c02144():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'persist', 'empty_asr') == None


def test_b02_c02145():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'persist', 'no_owned_words') == None


def test_b02_c02146():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'persist', 'outside_admitted_source') == None


def test_b02_c02147():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'persist', 'persist_payload_invalid') == None


def test_b02_c02148():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'persist', 'retained_audio_invalid') == None


def test_b02_c02149():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'persist', 'staged_audio_invalid') == None


def test_b02_c02150():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'persist', 'unknown') == None


def test_b02_c02151():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'persist', 'unsupported_language') == None


def test_b02_c02152():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'persist', 'vad_bounds') == None


def test_b02_c02153():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'persist', 'vad_nonfinite') == None


def test_b02_c02154():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'persist', 'vad_order') == None


def test_b02_c02155():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'persist', 'word_clock') == None


def test_b02_c02156():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'persist', 'word_sequence') == None


def test_b02_c02157():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'persist', 'word_shape') == None


def test_b02_c02158():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'persist', 'unclassified') == None


def test_b02_c02159():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c02160():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'vad_windows', 'decoded_duration_mismatch') == None


def test_b02_c02161():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'vad_windows', 'empty_asr') == None


def test_b02_c02162():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'vad_windows', 'no_owned_words') == None


def test_b02_c02163():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'vad_windows', 'outside_admitted_source') == None


def test_b02_c02164():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'vad_windows', 'persist_payload_invalid') == None


def test_b02_c02165():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c02166():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c02167():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'vad_windows', 'unknown') == None


def test_b02_c02168():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'vad_windows', 'unsupported_language') == None


def test_b02_c02169():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'vad_windows', 'vad_bounds') == None


def test_b02_c02170():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c02171():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'vad_windows', 'vad_order') == None


def test_b02_c02172():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'vad_windows', 'word_clock') == None


def test_b02_c02173():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'vad_windows', 'word_sequence') == None


def test_b02_c02174():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'vad_windows', 'word_shape') == None


def test_b02_c02175():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'vad_windows', 'unclassified') == None


def test_b02_c02176():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c02177():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'word_clocks', 'decoded_duration_mismatch') == None


def test_b02_c02178():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'word_clocks', 'empty_asr') == None


def test_b02_c02179():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'word_clocks', 'no_owned_words') == None


def test_b02_c02180():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'word_clocks', 'outside_admitted_source') == None


def test_b02_c02181():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'word_clocks', 'persist_payload_invalid') == None


def test_b02_c02182():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c02183():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c02184():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'word_clocks', 'unknown') == None


def test_b02_c02185():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'word_clocks', 'unsupported_language') == None


def test_b02_c02186():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'word_clocks', 'vad_bounds') == None


def test_b02_c02187():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c02188():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'word_clocks', 'vad_order') == None


def test_b02_c02189():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'word_clocks', 'word_clock') == None


def test_b02_c02190():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'word_clocks', 'word_sequence') == None


def test_b02_c02191():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'word_clocks', 'word_shape') == None


def test_b02_c02192():
    assert decode_payload_failure_reason(_make('b_RecursionError'), 'word_clocks', 'unclassified') == None


def test_b02_c02193():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'asr_recovery', 'decode_payload_invalid') == None


def test_b02_c02194():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'asr_recovery', 'decoded_duration_mismatch') == None


def test_b02_c02195():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'asr_recovery', 'empty_asr') == None


def test_b02_c02196():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c02197():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'asr_recovery', 'outside_admitted_source') == None


def test_b02_c02198():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'asr_recovery', 'persist_payload_invalid') == None


def test_b02_c02199():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'asr_recovery', 'retained_audio_invalid') == None


def test_b02_c02200():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c02201():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'asr_recovery', 'unknown') == None


def test_b02_c02202():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c02203():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c02204():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c02205():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'asr_recovery', 'vad_order') == None


def test_b02_c02206():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'asr_recovery', 'word_clock') == None


def test_b02_c02207():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'asr_recovery', 'word_sequence') == None


def test_b02_c02208():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'asr_recovery', 'word_shape') == None


def test_b02_c02209():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'asr_recovery', 'unclassified') == None


def test_b02_c02210():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'assemble_words', 'decode_payload_invalid') == None


def test_b02_c02211():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'assemble_words', 'decoded_duration_mismatch') == None


def test_b02_c02212():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'assemble_words', 'empty_asr') == None


def test_b02_c02213():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'assemble_words', 'no_owned_words') == None


def test_b02_c02214():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'assemble_words', 'outside_admitted_source') == None


def test_b02_c02215():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'assemble_words', 'persist_payload_invalid') == None


def test_b02_c02216():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'assemble_words', 'retained_audio_invalid') == None


def test_b02_c02217():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'assemble_words', 'staged_audio_invalid') == None


def test_b02_c02218():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'assemble_words', 'unknown') == None


def test_b02_c02219():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'assemble_words', 'unsupported_language') == None


def test_b02_c02220():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'assemble_words', 'vad_bounds') == None


def test_b02_c02221():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c02222():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'assemble_words', 'vad_order') == None


def test_b02_c02223():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'assemble_words', 'word_clock') == None


def test_b02_c02224():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'assemble_words', 'word_sequence') == None


def test_b02_c02225():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'assemble_words', 'word_shape') == None


def test_b02_c02226():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'assemble_words', 'unclassified') == None


def test_b02_c02227():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'fetch_decode', 'decode_payload_invalid') == None


def test_b02_c02228():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'fetch_decode', 'decoded_duration_mismatch') == None


def test_b02_c02229():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'fetch_decode', 'empty_asr') == None


def test_b02_c02230():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c02231():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'fetch_decode', 'outside_admitted_source') == None


def test_b02_c02232():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'fetch_decode', 'persist_payload_invalid') == None


def test_b02_c02233():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'fetch_decode', 'retained_audio_invalid') == None


def test_b02_c02234():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c02235():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'fetch_decode', 'unknown') == None


def test_b02_c02236():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c02237():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c02238():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c02239():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'fetch_decode', 'vad_order') == None


def test_b02_c02240():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'fetch_decode', 'word_clock') == None


def test_b02_c02241():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'fetch_decode', 'word_sequence') == None


def test_b02_c02242():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'fetch_decode', 'word_shape') == None


def test_b02_c02243():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'fetch_decode', 'unclassified') == None


def test_b02_c02244():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'persist', 'decode_payload_invalid') == None


def test_b02_c02245():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c02246():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'persist', 'empty_asr') == None


def test_b02_c02247():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'persist', 'no_owned_words') == None


def test_b02_c02248():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'persist', 'outside_admitted_source') == None


def test_b02_c02249():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'persist', 'persist_payload_invalid') == None


def test_b02_c02250():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'persist', 'retained_audio_invalid') == None


def test_b02_c02251():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'persist', 'staged_audio_invalid') == None


def test_b02_c02252():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'persist', 'unknown') == None


def test_b02_c02253():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'persist', 'unsupported_language') == None


def test_b02_c02254():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'persist', 'vad_bounds') == None


def test_b02_c02255():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'persist', 'vad_nonfinite') == None


def test_b02_c02256():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'persist', 'vad_order') == None


def test_b02_c02257():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'persist', 'word_clock') == None


def test_b02_c02258():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'persist', 'word_sequence') == None


def test_b02_c02259():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'persist', 'word_shape') == None


def test_b02_c02260():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'persist', 'unclassified') == None


def test_b02_c02261():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c02262():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'vad_windows', 'decoded_duration_mismatch') == None


def test_b02_c02263():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'vad_windows', 'empty_asr') == None


def test_b02_c02264():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'vad_windows', 'no_owned_words') == None


def test_b02_c02265():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'vad_windows', 'outside_admitted_source') == None


def test_b02_c02266():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'vad_windows', 'persist_payload_invalid') == None


def test_b02_c02267():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c02268():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c02269():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'vad_windows', 'unknown') == None


def test_b02_c02270():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'vad_windows', 'unsupported_language') == None


def test_b02_c02271():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'vad_windows', 'vad_bounds') == None


def test_b02_c02272():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c02273():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'vad_windows', 'vad_order') == None


def test_b02_c02274():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'vad_windows', 'word_clock') == None


def test_b02_c02275():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'vad_windows', 'word_sequence') == None


def test_b02_c02276():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'vad_windows', 'word_shape') == None


def test_b02_c02277():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'vad_windows', 'unclassified') == None


def test_b02_c02278():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c02279():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'word_clocks', 'decoded_duration_mismatch') == None


def test_b02_c02280():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'word_clocks', 'empty_asr') == None


def test_b02_c02281():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'word_clocks', 'no_owned_words') == None


def test_b02_c02282():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'word_clocks', 'outside_admitted_source') == None


def test_b02_c02283():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'word_clocks', 'persist_payload_invalid') == None


def test_b02_c02284():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c02285():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c02286():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'word_clocks', 'unknown') == None


def test_b02_c02287():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'word_clocks', 'unsupported_language') == None


def test_b02_c02288():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'word_clocks', 'vad_bounds') == None


def test_b02_c02289():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c02290():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'word_clocks', 'vad_order') == None


def test_b02_c02291():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'word_clocks', 'word_clock') == None


def test_b02_c02292():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'word_clocks', 'word_sequence') == None


def test_b02_c02293():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'word_clocks', 'word_shape') == None


def test_b02_c02294():
    assert decode_payload_failure_reason(_make('b_RuntimeError'), 'word_clocks', 'unclassified') == None


def test_b02_c02295():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'asr_recovery', 'decode_payload_invalid') == None


def test_b02_c02296():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'asr_recovery', 'decoded_duration_mismatch') == None


def test_b02_c02297():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'asr_recovery', 'empty_asr') == None


def test_b02_c02298():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c02299():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'asr_recovery', 'outside_admitted_source') == None


def test_b02_c02300():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'asr_recovery', 'persist_payload_invalid') == None


def test_b02_c02301():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'asr_recovery', 'retained_audio_invalid') == None


def test_b02_c02302():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c02303():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'asr_recovery', 'unknown') == None


def test_b02_c02304():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c02305():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c02306():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c02307():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'asr_recovery', 'vad_order') == None


def test_b02_c02308():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'asr_recovery', 'word_clock') == None


def test_b02_c02309():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'asr_recovery', 'word_sequence') == None


def test_b02_c02310():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'asr_recovery', 'word_shape') == None


def test_b02_c02311():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'asr_recovery', 'unclassified') == None


def test_b02_c02312():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'assemble_words', 'decode_payload_invalid') == None


def test_b02_c02313():
    assert (
        decode_payload_failure_reason(_make('b_StopIteration'), 'assemble_words', 'decoded_duration_mismatch') == None
    )


def test_b02_c02314():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'assemble_words', 'empty_asr') == None


def test_b02_c02315():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'assemble_words', 'no_owned_words') == None


def test_b02_c02316():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'assemble_words', 'outside_admitted_source') == None


def test_b02_c02317():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'assemble_words', 'persist_payload_invalid') == None


def test_b02_c02318():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'assemble_words', 'retained_audio_invalid') == None


def test_b02_c02319():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'assemble_words', 'staged_audio_invalid') == None


def test_b02_c02320():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'assemble_words', 'unknown') == None


def test_b02_c02321():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'assemble_words', 'unsupported_language') == None


def test_b02_c02322():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'assemble_words', 'vad_bounds') == None


def test_b02_c02323():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c02324():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'assemble_words', 'vad_order') == None


def test_b02_c02325():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'assemble_words', 'word_clock') == None


def test_b02_c02326():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'assemble_words', 'word_sequence') == None


def test_b02_c02327():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'assemble_words', 'word_shape') == None


def test_b02_c02328():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'assemble_words', 'unclassified') == None


def test_b02_c02329():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'fetch_decode', 'decode_payload_invalid') == None


def test_b02_c02330():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'fetch_decode', 'decoded_duration_mismatch') == None


def test_b02_c02331():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'fetch_decode', 'empty_asr') == None


def test_b02_c02332():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c02333():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'fetch_decode', 'outside_admitted_source') == None


def test_b02_c02334():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'fetch_decode', 'persist_payload_invalid') == None


def test_b02_c02335():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'fetch_decode', 'retained_audio_invalid') == None


def test_b02_c02336():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c02337():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'fetch_decode', 'unknown') == None


def test_b02_c02338():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c02339():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c02340():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c02341():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'fetch_decode', 'vad_order') == None


def test_b02_c02342():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'fetch_decode', 'word_clock') == None


def test_b02_c02343():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'fetch_decode', 'word_sequence') == None


def test_b02_c02344():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'fetch_decode', 'word_shape') == None


def test_b02_c02345():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'fetch_decode', 'unclassified') == None


def test_b02_c02346():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'persist', 'decode_payload_invalid') == None


def test_b02_c02347():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c02348():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'persist', 'empty_asr') == None


def test_b02_c02349():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'persist', 'no_owned_words') == None


def test_b02_c02350():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'persist', 'outside_admitted_source') == None


def test_b02_c02351():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'persist', 'persist_payload_invalid') == None


def test_b02_c02352():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'persist', 'retained_audio_invalid') == None


def test_b02_c02353():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'persist', 'staged_audio_invalid') == None


def test_b02_c02354():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'persist', 'unknown') == None


def test_b02_c02355():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'persist', 'unsupported_language') == None


def test_b02_c02356():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'persist', 'vad_bounds') == None


def test_b02_c02357():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'persist', 'vad_nonfinite') == None


def test_b02_c02358():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'persist', 'vad_order') == None


def test_b02_c02359():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'persist', 'word_clock') == None


def test_b02_c02360():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'persist', 'word_sequence') == None


def test_b02_c02361():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'persist', 'word_shape') == None


def test_b02_c02362():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'persist', 'unclassified') == None


def test_b02_c02363():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c02364():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'vad_windows', 'decoded_duration_mismatch') == None


def test_b02_c02365():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'vad_windows', 'empty_asr') == None


def test_b02_c02366():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'vad_windows', 'no_owned_words') == None


def test_b02_c02367():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'vad_windows', 'outside_admitted_source') == None


def test_b02_c02368():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'vad_windows', 'persist_payload_invalid') == None


def test_b02_c02369():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c02370():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c02371():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'vad_windows', 'unknown') == None


def test_b02_c02372():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'vad_windows', 'unsupported_language') == None


def test_b02_c02373():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'vad_windows', 'vad_bounds') == None


def test_b02_c02374():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c02375():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'vad_windows', 'vad_order') == None


def test_b02_c02376():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'vad_windows', 'word_clock') == None


def test_b02_c02377():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'vad_windows', 'word_sequence') == None


def test_b02_c02378():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'vad_windows', 'word_shape') == None


def test_b02_c02379():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'vad_windows', 'unclassified') == None


def test_b02_c02380():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c02381():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'word_clocks', 'decoded_duration_mismatch') == None


def test_b02_c02382():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'word_clocks', 'empty_asr') == None


def test_b02_c02383():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'word_clocks', 'no_owned_words') == None


def test_b02_c02384():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'word_clocks', 'outside_admitted_source') == None


def test_b02_c02385():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'word_clocks', 'persist_payload_invalid') == None


def test_b02_c02386():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c02387():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c02388():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'word_clocks', 'unknown') == None


def test_b02_c02389():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'word_clocks', 'unsupported_language') == None


def test_b02_c02390():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'word_clocks', 'vad_bounds') == None


def test_b02_c02391():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c02392():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'word_clocks', 'vad_order') == None


def test_b02_c02393():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'word_clocks', 'word_clock') == None


def test_b02_c02394():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'word_clocks', 'word_sequence') == None


def test_b02_c02395():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'word_clocks', 'word_shape') == None


def test_b02_c02396():
    assert decode_payload_failure_reason(_make('b_StopIteration'), 'word_clocks', 'unclassified') == None


def test_b02_c02397():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'asr_recovery', 'decode_payload_invalid') == None


def test_b02_c02398():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'asr_recovery', 'decoded_duration_mismatch') == None


def test_b02_c02399():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'asr_recovery', 'empty_asr') == None


def test_b02_c02400():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c02401():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'asr_recovery', 'outside_admitted_source') == None


def test_b02_c02402():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'asr_recovery', 'persist_payload_invalid') == None


def test_b02_c02403():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'asr_recovery', 'retained_audio_invalid') == None


def test_b02_c02404():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c02405():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'asr_recovery', 'unknown') == None


def test_b02_c02406():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c02407():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c02408():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c02409():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'asr_recovery', 'vad_order') == None


def test_b02_c02410():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'asr_recovery', 'word_clock') == None


def test_b02_c02411():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'asr_recovery', 'word_sequence') == None


def test_b02_c02412():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'asr_recovery', 'word_shape') == None


def test_b02_c02413():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'asr_recovery', 'unclassified') == None


def test_b02_c02414():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'assemble_words', 'decode_payload_invalid') == None


def test_b02_c02415():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'assemble_words', 'decoded_duration_mismatch') == None


def test_b02_c02416():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'assemble_words', 'empty_asr') == None


def test_b02_c02417():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'assemble_words', 'no_owned_words') == None


def test_b02_c02418():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'assemble_words', 'outside_admitted_source') == None


def test_b02_c02419():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'assemble_words', 'persist_payload_invalid') == None


def test_b02_c02420():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'assemble_words', 'retained_audio_invalid') == None


def test_b02_c02421():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'assemble_words', 'staged_audio_invalid') == None


def test_b02_c02422():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'assemble_words', 'unknown') == None


def test_b02_c02423():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'assemble_words', 'unsupported_language') == None


def test_b02_c02424():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'assemble_words', 'vad_bounds') == None


def test_b02_c02425():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c02426():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'assemble_words', 'vad_order') == None


def test_b02_c02427():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'assemble_words', 'word_clock') == None


def test_b02_c02428():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'assemble_words', 'word_sequence') == None


def test_b02_c02429():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'assemble_words', 'word_shape') == None


def test_b02_c02430():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'assemble_words', 'unclassified') == None


def test_b02_c02431():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'fetch_decode', 'decode_payload_invalid') == None


def test_b02_c02432():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'fetch_decode', 'decoded_duration_mismatch') == None


def test_b02_c02433():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'fetch_decode', 'empty_asr') == None


def test_b02_c02434():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c02435():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'fetch_decode', 'outside_admitted_source') == None


def test_b02_c02436():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'fetch_decode', 'persist_payload_invalid') == None


def test_b02_c02437():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'fetch_decode', 'retained_audio_invalid') == None


def test_b02_c02438():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c02439():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'fetch_decode', 'unknown') == None


def test_b02_c02440():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c02441():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c02442():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c02443():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'fetch_decode', 'vad_order') == None


def test_b02_c02444():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'fetch_decode', 'word_clock') == None


def test_b02_c02445():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'fetch_decode', 'word_sequence') == None


def test_b02_c02446():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'fetch_decode', 'word_shape') == None


def test_b02_c02447():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'fetch_decode', 'unclassified') == None


def test_b02_c02448():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'persist', 'decode_payload_invalid') == None


def test_b02_c02449():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c02450():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'persist', 'empty_asr') == None


def test_b02_c02451():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'persist', 'no_owned_words') == None


def test_b02_c02452():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'persist', 'outside_admitted_source') == None


def test_b02_c02453():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'persist', 'persist_payload_invalid') == None


def test_b02_c02454():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'persist', 'retained_audio_invalid') == None


def test_b02_c02455():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'persist', 'staged_audio_invalid') == None


def test_b02_c02456():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'persist', 'unknown') == None


def test_b02_c02457():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'persist', 'unsupported_language') == None


def test_b02_c02458():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'persist', 'vad_bounds') == None


def test_b02_c02459():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'persist', 'vad_nonfinite') == None


def test_b02_c02460():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'persist', 'vad_order') == None


def test_b02_c02461():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'persist', 'word_clock') == None


def test_b02_c02462():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'persist', 'word_sequence') == None


def test_b02_c02463():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'persist', 'word_shape') == None


def test_b02_c02464():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'persist', 'unclassified') == None


def test_b02_c02465():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c02466():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'vad_windows', 'decoded_duration_mismatch') == None


def test_b02_c02467():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'vad_windows', 'empty_asr') == None


def test_b02_c02468():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'vad_windows', 'no_owned_words') == None


def test_b02_c02469():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'vad_windows', 'outside_admitted_source') == None


def test_b02_c02470():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'vad_windows', 'persist_payload_invalid') == None


def test_b02_c02471():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c02472():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c02473():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'vad_windows', 'unknown') == None


def test_b02_c02474():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'vad_windows', 'unsupported_language') == None


def test_b02_c02475():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'vad_windows', 'vad_bounds') == None


def test_b02_c02476():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c02477():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'vad_windows', 'vad_order') == None


def test_b02_c02478():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'vad_windows', 'word_clock') == None


def test_b02_c02479():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'vad_windows', 'word_sequence') == None


def test_b02_c02480():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'vad_windows', 'word_shape') == None


def test_b02_c02481():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'vad_windows', 'unclassified') == None


def test_b02_c02482():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c02483():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'word_clocks', 'decoded_duration_mismatch') == None


def test_b02_c02484():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'word_clocks', 'empty_asr') == None


def test_b02_c02485():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'word_clocks', 'no_owned_words') == None


def test_b02_c02486():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'word_clocks', 'outside_admitted_source') == None


def test_b02_c02487():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'word_clocks', 'persist_payload_invalid') == None


def test_b02_c02488():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c02489():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c02490():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'word_clocks', 'unknown') == None


def test_b02_c02491():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'word_clocks', 'unsupported_language') == None


def test_b02_c02492():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'word_clocks', 'vad_bounds') == None


def test_b02_c02493():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c02494():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'word_clocks', 'vad_order') == None


def test_b02_c02495():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'word_clocks', 'word_clock') == None


def test_b02_c02496():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'word_clocks', 'word_sequence') == None


def test_b02_c02497():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'word_clocks', 'word_shape') == None


def test_b02_c02498():
    assert decode_payload_failure_reason(_make('b_TimeoutError'), 'word_clocks', 'unclassified') == None


def test_b02_c02499():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'asr_recovery', 'decode_payload_invalid') == None


def test_b02_c02500():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'asr_recovery', 'decoded_duration_mismatch') == None


def test_b02_c02501():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'asr_recovery', 'empty_asr') == None


def test_b02_c02502():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c02503():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'asr_recovery', 'outside_admitted_source') == None


def test_b02_c02504():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'asr_recovery', 'persist_payload_invalid') == None


def test_b02_c02505():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'asr_recovery', 'retained_audio_invalid') == None


def test_b02_c02506():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c02507():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'asr_recovery', 'unknown') == None


def test_b02_c02508():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c02509():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c02510():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c02511():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'asr_recovery', 'vad_order') == None


def test_b02_c02512():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'asr_recovery', 'word_clock') == None


def test_b02_c02513():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'asr_recovery', 'word_sequence') == None


def test_b02_c02514():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'asr_recovery', 'word_shape') == None


def test_b02_c02515():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'asr_recovery', 'unclassified') == None


def test_b02_c02516():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'assemble_words', 'decode_payload_invalid') == None


def test_b02_c02517():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'assemble_words', 'decoded_duration_mismatch') == None


def test_b02_c02518():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'assemble_words', 'empty_asr') == None


def test_b02_c02519():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'assemble_words', 'no_owned_words') == None


def test_b02_c02520():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'assemble_words', 'outside_admitted_source') == None


def test_b02_c02521():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'assemble_words', 'persist_payload_invalid') == None


def test_b02_c02522():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'assemble_words', 'retained_audio_invalid') == None


def test_b02_c02523():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'assemble_words', 'staged_audio_invalid') == None


def test_b02_c02524():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'assemble_words', 'unknown') == None


def test_b02_c02525():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'assemble_words', 'unsupported_language') == None


def test_b02_c02526():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'assemble_words', 'vad_bounds') == None


def test_b02_c02527():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c02528():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'assemble_words', 'vad_order') == None


def test_b02_c02529():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'assemble_words', 'word_clock') == None


def test_b02_c02530():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'assemble_words', 'word_sequence') == None


def test_b02_c02531():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'assemble_words', 'word_shape') == None


def test_b02_c02532():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'assemble_words', 'unclassified') == None


def test_b02_c02533():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'fetch_decode', 'decode_payload_invalid') == None


def test_b02_c02534():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'fetch_decode', 'decoded_duration_mismatch') == None


def test_b02_c02535():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'fetch_decode', 'empty_asr') == None


def test_b02_c02536():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c02537():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'fetch_decode', 'outside_admitted_source') == None


def test_b02_c02538():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'fetch_decode', 'persist_payload_invalid') == None


def test_b02_c02539():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'fetch_decode', 'retained_audio_invalid') == None


def test_b02_c02540():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c02541():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'fetch_decode', 'unknown') == None


def test_b02_c02542():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c02543():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c02544():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c02545():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'fetch_decode', 'vad_order') == None


def test_b02_c02546():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'fetch_decode', 'word_clock') == None


def test_b02_c02547():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'fetch_decode', 'word_sequence') == None


def test_b02_c02548():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'fetch_decode', 'word_shape') == None


def test_b02_c02549():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'fetch_decode', 'unclassified') == None


def test_b02_c02550():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'persist', 'decode_payload_invalid') == None


def test_b02_c02551():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c02552():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'persist', 'empty_asr') == None


def test_b02_c02553():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'persist', 'no_owned_words') == None


def test_b02_c02554():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'persist', 'outside_admitted_source') == None


def test_b02_c02555():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'persist', 'persist_payload_invalid') == None


def test_b02_c02556():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'persist', 'retained_audio_invalid') == None


def test_b02_c02557():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'persist', 'staged_audio_invalid') == None


def test_b02_c02558():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'persist', 'unknown') == None


def test_b02_c02559():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'persist', 'unsupported_language') == None


def test_b02_c02560():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'persist', 'vad_bounds') == None


def test_b02_c02561():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'persist', 'vad_nonfinite') == None


def test_b02_c02562():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'persist', 'vad_order') == None


def test_b02_c02563():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'persist', 'word_clock') == None


def test_b02_c02564():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'persist', 'word_sequence') == None


def test_b02_c02565():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'persist', 'word_shape') == None


def test_b02_c02566():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'persist', 'unclassified') == None


def test_b02_c02567():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c02568():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'vad_windows', 'decoded_duration_mismatch') == None


def test_b02_c02569():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'vad_windows', 'empty_asr') == None


def test_b02_c02570():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'vad_windows', 'no_owned_words') == None


def test_b02_c02571():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'vad_windows', 'outside_admitted_source') == None


def test_b02_c02572():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'vad_windows', 'persist_payload_invalid') == None


def test_b02_c02573():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c02574():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c02575():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'vad_windows', 'unknown') == None


def test_b02_c02576():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'vad_windows', 'unsupported_language') == None


def test_b02_c02577():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'vad_windows', 'vad_bounds') == None


def test_b02_c02578():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c02579():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'vad_windows', 'vad_order') == None


def test_b02_c02580():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'vad_windows', 'word_clock') == None


def test_b02_c02581():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'vad_windows', 'word_sequence') == None


def test_b02_c02582():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'vad_windows', 'word_shape') == None


def test_b02_c02583():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'vad_windows', 'unclassified') == None


def test_b02_c02584():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c02585():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'word_clocks', 'decoded_duration_mismatch') == None


def test_b02_c02586():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'word_clocks', 'empty_asr') == None


def test_b02_c02587():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'word_clocks', 'no_owned_words') == None


def test_b02_c02588():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'word_clocks', 'outside_admitted_source') == None


def test_b02_c02589():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'word_clocks', 'persist_payload_invalid') == None


def test_b02_c02590():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c02591():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c02592():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'word_clocks', 'unknown') == None


def test_b02_c02593():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'word_clocks', 'unsupported_language') == None


def test_b02_c02594():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'word_clocks', 'vad_bounds') == None


def test_b02_c02595():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c02596():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'word_clocks', 'vad_order') == None


def test_b02_c02597():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'word_clocks', 'word_clock') == None


def test_b02_c02598():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'word_clocks', 'word_sequence') == None


def test_b02_c02599():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'word_clocks', 'word_shape') == None


def test_b02_c02600():
    assert decode_payload_failure_reason(_make('b_TypeError'), 'word_clocks', 'unclassified') == None


def test_b02_c02601():
    assert (
        decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'asr_recovery', 'decode_payload_invalid') == None
    )


def test_b02_c02602():
    assert (
        decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'asr_recovery', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c02603():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'asr_recovery', 'empty_asr') == None


def test_b02_c02604():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c02605():
    assert (
        decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'asr_recovery', 'outside_admitted_source') == None
    )


def test_b02_c02606():
    assert (
        decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'asr_recovery', 'persist_payload_invalid') == None
    )


def test_b02_c02607():
    assert (
        decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'asr_recovery', 'retained_audio_invalid') == None
    )


def test_b02_c02608():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c02609():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'asr_recovery', 'unknown') == None


def test_b02_c02610():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c02611():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c02612():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c02613():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'asr_recovery', 'vad_order') == None


def test_b02_c02614():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'asr_recovery', 'word_clock') == None


def test_b02_c02615():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'asr_recovery', 'word_sequence') == None


def test_b02_c02616():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'asr_recovery', 'word_shape') == None


def test_b02_c02617():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'asr_recovery', 'unclassified') == None


def test_b02_c02618():
    assert (
        decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'assemble_words', 'decode_payload_invalid') == None
    )


def test_b02_c02619():
    assert (
        decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'assemble_words', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c02620():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'assemble_words', 'empty_asr') == None


def test_b02_c02621():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'assemble_words', 'no_owned_words') == None


def test_b02_c02622():
    assert (
        decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'assemble_words', 'outside_admitted_source')
        == None
    )


def test_b02_c02623():
    assert (
        decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'assemble_words', 'persist_payload_invalid')
        == None
    )


def test_b02_c02624():
    assert (
        decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'assemble_words', 'retained_audio_invalid') == None
    )


def test_b02_c02625():
    assert (
        decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'assemble_words', 'staged_audio_invalid') == None
    )


def test_b02_c02626():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'assemble_words', 'unknown') == None


def test_b02_c02627():
    assert (
        decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'assemble_words', 'unsupported_language') == None
    )


def test_b02_c02628():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'assemble_words', 'vad_bounds') == None


def test_b02_c02629():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c02630():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'assemble_words', 'vad_order') == None


def test_b02_c02631():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'assemble_words', 'word_clock') == None


def test_b02_c02632():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'assemble_words', 'word_sequence') == None


def test_b02_c02633():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'assemble_words', 'word_shape') == None


def test_b02_c02634():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'assemble_words', 'unclassified') == None


def test_b02_c02635():
    assert (
        decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'fetch_decode', 'decode_payload_invalid') == None
    )


def test_b02_c02636():
    assert (
        decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'fetch_decode', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c02637():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'fetch_decode', 'empty_asr') == None


def test_b02_c02638():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c02639():
    assert (
        decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'fetch_decode', 'outside_admitted_source') == None
    )


def test_b02_c02640():
    assert (
        decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'fetch_decode', 'persist_payload_invalid') == None
    )


def test_b02_c02641():
    assert (
        decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'fetch_decode', 'retained_audio_invalid') == None
    )


def test_b02_c02642():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c02643():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'fetch_decode', 'unknown') == None


def test_b02_c02644():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c02645():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c02646():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c02647():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'fetch_decode', 'vad_order') == None


def test_b02_c02648():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'fetch_decode', 'word_clock') == None


def test_b02_c02649():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'fetch_decode', 'word_sequence') == None


def test_b02_c02650():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'fetch_decode', 'word_shape') == None


def test_b02_c02651():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'fetch_decode', 'unclassified') == POISON


def test_b02_c02652():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'persist', 'decode_payload_invalid') == None


def test_b02_c02653():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c02654():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'persist', 'empty_asr') == None


def test_b02_c02655():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'persist', 'no_owned_words') == None


def test_b02_c02656():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'persist', 'outside_admitted_source') == None


def test_b02_c02657():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'persist', 'persist_payload_invalid') == None


def test_b02_c02658():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'persist', 'retained_audio_invalid') == None


def test_b02_c02659():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'persist', 'staged_audio_invalid') == None


def test_b02_c02660():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'persist', 'unknown') == None


def test_b02_c02661():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'persist', 'unsupported_language') == None


def test_b02_c02662():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'persist', 'vad_bounds') == None


def test_b02_c02663():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'persist', 'vad_nonfinite') == None


def test_b02_c02664():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'persist', 'vad_order') == None


def test_b02_c02665():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'persist', 'word_clock') == None


def test_b02_c02666():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'persist', 'word_sequence') == None


def test_b02_c02667():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'persist', 'word_shape') == None


def test_b02_c02668():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'persist', 'unclassified') == None


def test_b02_c02669():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c02670():
    assert (
        decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'vad_windows', 'decoded_duration_mismatch') == None
    )


def test_b02_c02671():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'vad_windows', 'empty_asr') == None


def test_b02_c02672():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'vad_windows', 'no_owned_words') == None


def test_b02_c02673():
    assert (
        decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'vad_windows', 'outside_admitted_source') == None
    )


def test_b02_c02674():
    assert (
        decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'vad_windows', 'persist_payload_invalid') == None
    )


def test_b02_c02675():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c02676():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c02677():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'vad_windows', 'unknown') == None


def test_b02_c02678():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'vad_windows', 'unsupported_language') == None


def test_b02_c02679():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'vad_windows', 'vad_bounds') == None


def test_b02_c02680():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c02681():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'vad_windows', 'vad_order') == None


def test_b02_c02682():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'vad_windows', 'word_clock') == None


def test_b02_c02683():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'vad_windows', 'word_sequence') == None


def test_b02_c02684():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'vad_windows', 'word_shape') == None


def test_b02_c02685():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'vad_windows', 'unclassified') == None


def test_b02_c02686():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c02687():
    assert (
        decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'word_clocks', 'decoded_duration_mismatch') == None
    )


def test_b02_c02688():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'word_clocks', 'empty_asr') == None


def test_b02_c02689():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'word_clocks', 'no_owned_words') == None


def test_b02_c02690():
    assert (
        decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'word_clocks', 'outside_admitted_source') == None
    )


def test_b02_c02691():
    assert (
        decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'word_clocks', 'persist_payload_invalid') == None
    )


def test_b02_c02692():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c02693():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c02694():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'word_clocks', 'unknown') == None


def test_b02_c02695():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'word_clocks', 'unsupported_language') == None


def test_b02_c02696():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'word_clocks', 'vad_bounds') == None


def test_b02_c02697():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c02698():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'word_clocks', 'vad_order') == None


def test_b02_c02699():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'word_clocks', 'word_clock') == None


def test_b02_c02700():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'word_clocks', 'word_sequence') == None


def test_b02_c02701():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'word_clocks', 'word_shape') == None


def test_b02_c02702():
    assert decode_payload_failure_reason(_make('b_UnicodeDecodeError'), 'word_clocks', 'unclassified') == None


def test_b02_c02703():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'asr_recovery', 'decode_payload_invalid') == None


def test_b02_c02704():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'asr_recovery', 'decoded_duration_mismatch') == None


def test_b02_c02705():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'asr_recovery', 'empty_asr') == None


def test_b02_c02706():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c02707():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'asr_recovery', 'outside_admitted_source') == None


def test_b02_c02708():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'asr_recovery', 'persist_payload_invalid') == None


def test_b02_c02709():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'asr_recovery', 'retained_audio_invalid') == None


def test_b02_c02710():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c02711():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'asr_recovery', 'unknown') == None


def test_b02_c02712():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c02713():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c02714():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c02715():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'asr_recovery', 'vad_order') == None


def test_b02_c02716():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'asr_recovery', 'word_clock') == None


def test_b02_c02717():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'asr_recovery', 'word_sequence') == None


def test_b02_c02718():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'asr_recovery', 'word_shape') == None


def test_b02_c02719():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'asr_recovery', 'unclassified') == None


def test_b02_c02720():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'assemble_words', 'decode_payload_invalid') == None


def test_b02_c02721():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'assemble_words', 'decoded_duration_mismatch') == None


def test_b02_c02722():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'assemble_words', 'empty_asr') == None


def test_b02_c02723():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'assemble_words', 'no_owned_words') == None


def test_b02_c02724():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'assemble_words', 'outside_admitted_source') == None


def test_b02_c02725():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'assemble_words', 'persist_payload_invalid') == None


def test_b02_c02726():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'assemble_words', 'retained_audio_invalid') == None


def test_b02_c02727():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'assemble_words', 'staged_audio_invalid') == None


def test_b02_c02728():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'assemble_words', 'unknown') == None


def test_b02_c02729():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'assemble_words', 'unsupported_language') == None


def test_b02_c02730():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'assemble_words', 'vad_bounds') == None


def test_b02_c02731():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c02732():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'assemble_words', 'vad_order') == None


def test_b02_c02733():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'assemble_words', 'word_clock') == None


def test_b02_c02734():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'assemble_words', 'word_sequence') == None


def test_b02_c02735():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'assemble_words', 'word_shape') == None


def test_b02_c02736():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'assemble_words', 'unclassified') == None


def test_b02_c02737():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'fetch_decode', 'decode_payload_invalid') == None


def test_b02_c02738():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'fetch_decode', 'decoded_duration_mismatch') == None


def test_b02_c02739():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'fetch_decode', 'empty_asr') == None


def test_b02_c02740():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c02741():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'fetch_decode', 'outside_admitted_source') == None


def test_b02_c02742():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'fetch_decode', 'persist_payload_invalid') == None


def test_b02_c02743():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'fetch_decode', 'retained_audio_invalid') == None


def test_b02_c02744():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c02745():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'fetch_decode', 'unknown') == None


def test_b02_c02746():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c02747():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c02748():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c02749():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'fetch_decode', 'vad_order') == None


def test_b02_c02750():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'fetch_decode', 'word_clock') == None


def test_b02_c02751():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'fetch_decode', 'word_sequence') == None


def test_b02_c02752():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'fetch_decode', 'word_shape') == None


def test_b02_c02753():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'fetch_decode', 'unclassified') == POISON


def test_b02_c02754():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'persist', 'decode_payload_invalid') == None


def test_b02_c02755():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c02756():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'persist', 'empty_asr') == None


def test_b02_c02757():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'persist', 'no_owned_words') == None


def test_b02_c02758():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'persist', 'outside_admitted_source') == None


def test_b02_c02759():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'persist', 'persist_payload_invalid') == None


def test_b02_c02760():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'persist', 'retained_audio_invalid') == None


def test_b02_c02761():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'persist', 'staged_audio_invalid') == None


def test_b02_c02762():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'persist', 'unknown') == None


def test_b02_c02763():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'persist', 'unsupported_language') == None


def test_b02_c02764():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'persist', 'vad_bounds') == None


def test_b02_c02765():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'persist', 'vad_nonfinite') == None


def test_b02_c02766():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'persist', 'vad_order') == None


def test_b02_c02767():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'persist', 'word_clock') == None


def test_b02_c02768():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'persist', 'word_sequence') == None


def test_b02_c02769():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'persist', 'word_shape') == None


def test_b02_c02770():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'persist', 'unclassified') == None


def test_b02_c02771():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c02772():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'vad_windows', 'decoded_duration_mismatch') == None


def test_b02_c02773():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'vad_windows', 'empty_asr') == None


def test_b02_c02774():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'vad_windows', 'no_owned_words') == None


def test_b02_c02775():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'vad_windows', 'outside_admitted_source') == None


def test_b02_c02776():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'vad_windows', 'persist_payload_invalid') == None


def test_b02_c02777():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c02778():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c02779():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'vad_windows', 'unknown') == None


def test_b02_c02780():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'vad_windows', 'unsupported_language') == None


def test_b02_c02781():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'vad_windows', 'vad_bounds') == None


def test_b02_c02782():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c02783():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'vad_windows', 'vad_order') == None


def test_b02_c02784():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'vad_windows', 'word_clock') == None


def test_b02_c02785():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'vad_windows', 'word_sequence') == None


def test_b02_c02786():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'vad_windows', 'word_shape') == None


def test_b02_c02787():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'vad_windows', 'unclassified') == None


def test_b02_c02788():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c02789():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'word_clocks', 'decoded_duration_mismatch') == None


def test_b02_c02790():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'word_clocks', 'empty_asr') == None


def test_b02_c02791():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'word_clocks', 'no_owned_words') == None


def test_b02_c02792():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'word_clocks', 'outside_admitted_source') == None


def test_b02_c02793():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'word_clocks', 'persist_payload_invalid') == None


def test_b02_c02794():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c02795():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c02796():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'word_clocks', 'unknown') == None


def test_b02_c02797():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'word_clocks', 'unsupported_language') == None


def test_b02_c02798():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'word_clocks', 'vad_bounds') == None


def test_b02_c02799():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c02800():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'word_clocks', 'vad_order') == None


def test_b02_c02801():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'word_clocks', 'word_clock') == None


def test_b02_c02802():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'word_clocks', 'word_sequence') == None


def test_b02_c02803():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'word_clocks', 'word_shape') == None


def test_b02_c02804():
    assert decode_payload_failure_reason(_make('b_ValueError'), 'word_clocks', 'unclassified') == None


def test_b02_c02805():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'asr_recovery', 'decode_payload_invalid') == None


def test_b02_c02806():
    assert (
        decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'asr_recovery', 'decoded_duration_mismatch') == None
    )


def test_b02_c02807():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'asr_recovery', 'empty_asr') == None


def test_b02_c02808():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c02809():
    assert (
        decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'asr_recovery', 'outside_admitted_source') == None
    )


def test_b02_c02810():
    assert (
        decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'asr_recovery', 'persist_payload_invalid') == None
    )


def test_b02_c02811():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'asr_recovery', 'retained_audio_invalid') == None


def test_b02_c02812():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c02813():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'asr_recovery', 'unknown') == None


def test_b02_c02814():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c02815():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c02816():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c02817():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'asr_recovery', 'vad_order') == None


def test_b02_c02818():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'asr_recovery', 'word_clock') == None


def test_b02_c02819():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'asr_recovery', 'word_sequence') == None


def test_b02_c02820():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'asr_recovery', 'word_shape') == None


def test_b02_c02821():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'asr_recovery', 'unclassified') == None


def test_b02_c02822():
    assert (
        decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'assemble_words', 'decode_payload_invalid') == None
    )


def test_b02_c02823():
    assert (
        decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'assemble_words', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c02824():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'assemble_words', 'empty_asr') == None


def test_b02_c02825():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'assemble_words', 'no_owned_words') == None


def test_b02_c02826():
    assert (
        decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'assemble_words', 'outside_admitted_source') == None
    )


def test_b02_c02827():
    assert (
        decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'assemble_words', 'persist_payload_invalid') == None
    )


def test_b02_c02828():
    assert (
        decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'assemble_words', 'retained_audio_invalid') == None
    )


def test_b02_c02829():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'assemble_words', 'staged_audio_invalid') == None


def test_b02_c02830():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'assemble_words', 'unknown') == None


def test_b02_c02831():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'assemble_words', 'unsupported_language') == None


def test_b02_c02832():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'assemble_words', 'vad_bounds') == None


def test_b02_c02833():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c02834():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'assemble_words', 'vad_order') == None


def test_b02_c02835():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'assemble_words', 'word_clock') == None


def test_b02_c02836():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'assemble_words', 'word_sequence') == None


def test_b02_c02837():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'assemble_words', 'word_shape') == None


def test_b02_c02838():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'assemble_words', 'unclassified') == None


def test_b02_c02839():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'fetch_decode', 'decode_payload_invalid') == None


def test_b02_c02840():
    assert (
        decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'fetch_decode', 'decoded_duration_mismatch') == None
    )


def test_b02_c02841():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'fetch_decode', 'empty_asr') == None


def test_b02_c02842():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c02843():
    assert (
        decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'fetch_decode', 'outside_admitted_source') == None
    )


def test_b02_c02844():
    assert (
        decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'fetch_decode', 'persist_payload_invalid') == None
    )


def test_b02_c02845():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'fetch_decode', 'retained_audio_invalid') == None


def test_b02_c02846():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c02847():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'fetch_decode', 'unknown') == None


def test_b02_c02848():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c02849():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c02850():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c02851():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'fetch_decode', 'vad_order') == None


def test_b02_c02852():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'fetch_decode', 'word_clock') == None


def test_b02_c02853():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'fetch_decode', 'word_sequence') == None


def test_b02_c02854():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'fetch_decode', 'word_shape') == None


def test_b02_c02855():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'fetch_decode', 'unclassified') == None


def test_b02_c02856():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'persist', 'decode_payload_invalid') == None


def test_b02_c02857():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c02858():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'persist', 'empty_asr') == None


def test_b02_c02859():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'persist', 'no_owned_words') == None


def test_b02_c02860():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'persist', 'outside_admitted_source') == None


def test_b02_c02861():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'persist', 'persist_payload_invalid') == None


def test_b02_c02862():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'persist', 'retained_audio_invalid') == None


def test_b02_c02863():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'persist', 'staged_audio_invalid') == None


def test_b02_c02864():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'persist', 'unknown') == None


def test_b02_c02865():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'persist', 'unsupported_language') == None


def test_b02_c02866():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'persist', 'vad_bounds') == None


def test_b02_c02867():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'persist', 'vad_nonfinite') == None


def test_b02_c02868():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'persist', 'vad_order') == None


def test_b02_c02869():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'persist', 'word_clock') == None


def test_b02_c02870():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'persist', 'word_sequence') == None


def test_b02_c02871():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'persist', 'word_shape') == None


def test_b02_c02872():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'persist', 'unclassified') == None


def test_b02_c02873():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c02874():
    assert (
        decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'vad_windows', 'decoded_duration_mismatch') == None
    )


def test_b02_c02875():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'vad_windows', 'empty_asr') == None


def test_b02_c02876():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'vad_windows', 'no_owned_words') == None


def test_b02_c02877():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'vad_windows', 'outside_admitted_source') == None


def test_b02_c02878():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'vad_windows', 'persist_payload_invalid') == None


def test_b02_c02879():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c02880():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c02881():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'vad_windows', 'unknown') == None


def test_b02_c02882():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'vad_windows', 'unsupported_language') == None


def test_b02_c02883():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'vad_windows', 'vad_bounds') == None


def test_b02_c02884():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c02885():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'vad_windows', 'vad_order') == None


def test_b02_c02886():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'vad_windows', 'word_clock') == None


def test_b02_c02887():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'vad_windows', 'word_sequence') == None


def test_b02_c02888():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'vad_windows', 'word_shape') == None


def test_b02_c02889():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'vad_windows', 'unclassified') == None


def test_b02_c02890():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c02891():
    assert (
        decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'word_clocks', 'decoded_duration_mismatch') == None
    )


def test_b02_c02892():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'word_clocks', 'empty_asr') == None


def test_b02_c02893():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'word_clocks', 'no_owned_words') == None


def test_b02_c02894():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'word_clocks', 'outside_admitted_source') == None


def test_b02_c02895():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'word_clocks', 'persist_payload_invalid') == None


def test_b02_c02896():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c02897():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c02898():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'word_clocks', 'unknown') == None


def test_b02_c02899():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'word_clocks', 'unsupported_language') == None


def test_b02_c02900():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'word_clocks', 'vad_bounds') == None


def test_b02_c02901():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c02902():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'word_clocks', 'vad_order') == None


def test_b02_c02903():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'word_clocks', 'word_clock') == None


def test_b02_c02904():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'word_clocks', 'word_sequence') == None


def test_b02_c02905():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'word_clocks', 'word_shape') == None


def test_b02_c02906():
    assert decode_payload_failure_reason(_make('b_ZeroDivisionError'), 'word_clocks', 'unclassified') == None


def test_b02_c02907():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'asr_recovery', 'decode_payload_invalid') == None


def test_b02_c02908():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'asr_recovery', 'decoded_duration_mismatch') == None


def test_b02_c02909():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'asr_recovery', 'empty_asr') == None


def test_b02_c02910():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c02911():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'asr_recovery', 'outside_admitted_source') == None


def test_b02_c02912():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'asr_recovery', 'persist_payload_invalid') == None


def test_b02_c02913():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'asr_recovery', 'retained_audio_invalid') == None


def test_b02_c02914():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c02915():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'asr_recovery', 'unknown') == None


def test_b02_c02916():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c02917():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c02918():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c02919():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'asr_recovery', 'vad_order') == None


def test_b02_c02920():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'asr_recovery', 'word_clock') == None


def test_b02_c02921():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'asr_recovery', 'word_sequence') == None


def test_b02_c02922():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'asr_recovery', 'word_shape') == None


def test_b02_c02923():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'asr_recovery', 'unclassified') == None


def test_b02_c02924():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'assemble_words', 'decode_payload_invalid') == None


def test_b02_c02925():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'assemble_words', 'decoded_duration_mismatch') == None


def test_b02_c02926():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'assemble_words', 'empty_asr') == None


def test_b02_c02927():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'assemble_words', 'no_owned_words') == None


def test_b02_c02928():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'assemble_words', 'outside_admitted_source') == None


def test_b02_c02929():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'assemble_words', 'persist_payload_invalid') == None


def test_b02_c02930():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'assemble_words', 'retained_audio_invalid') == None


def test_b02_c02931():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'assemble_words', 'staged_audio_invalid') == None


def test_b02_c02932():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'assemble_words', 'unknown') == None


def test_b02_c02933():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'assemble_words', 'unsupported_language') == None


def test_b02_c02934():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'assemble_words', 'vad_bounds') == None


def test_b02_c02935():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c02936():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'assemble_words', 'vad_order') == None


def test_b02_c02937():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'assemble_words', 'word_clock') == None


def test_b02_c02938():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'assemble_words', 'word_sequence') == None


def test_b02_c02939():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'assemble_words', 'word_shape') == None


def test_b02_c02940():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'assemble_words', 'unclassified') == None


def test_b02_c02941():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'fetch_decode', 'decode_payload_invalid') == None


def test_b02_c02942():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'fetch_decode', 'decoded_duration_mismatch') == None


def test_b02_c02943():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'fetch_decode', 'empty_asr') == None


def test_b02_c02944():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c02945():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'fetch_decode', 'outside_admitted_source') == None


def test_b02_c02946():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'fetch_decode', 'persist_payload_invalid') == None


def test_b02_c02947():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'fetch_decode', 'retained_audio_invalid') == None


def test_b02_c02948():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c02949():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'fetch_decode', 'unknown') == None


def test_b02_c02950():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c02951():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c02952():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c02953():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'fetch_decode', 'vad_order') == None


def test_b02_c02954():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'fetch_decode', 'word_clock') == None


def test_b02_c02955():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'fetch_decode', 'word_sequence') == None


def test_b02_c02956():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'fetch_decode', 'word_shape') == None


def test_b02_c02957():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'fetch_decode', 'unclassified') == None


def test_b02_c02958():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'persist', 'decode_payload_invalid') == None


def test_b02_c02959():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c02960():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'persist', 'empty_asr') == None


def test_b02_c02961():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'persist', 'no_owned_words') == None


def test_b02_c02962():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'persist', 'outside_admitted_source') == None


def test_b02_c02963():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'persist', 'persist_payload_invalid') == None


def test_b02_c02964():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'persist', 'retained_audio_invalid') == None


def test_b02_c02965():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'persist', 'staged_audio_invalid') == None


def test_b02_c02966():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'persist', 'unknown') == None


def test_b02_c02967():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'persist', 'unsupported_language') == None


def test_b02_c02968():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'persist', 'vad_bounds') == None


def test_b02_c02969():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'persist', 'vad_nonfinite') == None


def test_b02_c02970():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'persist', 'vad_order') == None


def test_b02_c02971():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'persist', 'word_clock') == None


def test_b02_c02972():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'persist', 'word_sequence') == None


def test_b02_c02973():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'persist', 'word_shape') == None


def test_b02_c02974():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'persist', 'unclassified') == None


def test_b02_c02975():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c02976():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'vad_windows', 'decoded_duration_mismatch') == None


def test_b02_c02977():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'vad_windows', 'empty_asr') == None


def test_b02_c02978():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'vad_windows', 'no_owned_words') == None


def test_b02_c02979():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'vad_windows', 'outside_admitted_source') == None


def test_b02_c02980():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'vad_windows', 'persist_payload_invalid') == None


def test_b02_c02981():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c02982():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c02983():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'vad_windows', 'unknown') == None


def test_b02_c02984():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'vad_windows', 'unsupported_language') == None


def test_b02_c02985():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'vad_windows', 'vad_bounds') == None


def test_b02_c02986():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c02987():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'vad_windows', 'vad_order') == None


def test_b02_c02988():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'vad_windows', 'word_clock') == None


def test_b02_c02989():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'vad_windows', 'word_sequence') == None


def test_b02_c02990():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'vad_windows', 'word_shape') == None


def test_b02_c02991():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'vad_windows', 'unclassified') == None


def test_b02_c02992():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c02993():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'word_clocks', 'decoded_duration_mismatch') == None


def test_b02_c02994():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'word_clocks', 'empty_asr') == None


def test_b02_c02995():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'word_clocks', 'no_owned_words') == None


def test_b02_c02996():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'word_clocks', 'outside_admitted_source') == None


def test_b02_c02997():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'word_clocks', 'persist_payload_invalid') == None


def test_b02_c02998():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c02999():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c03000():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'word_clocks', 'unknown') == None


def test_b02_c03001():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'word_clocks', 'unsupported_language') == None


def test_b02_c03002():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'word_clocks', 'vad_bounds') == None


def test_b02_c03003():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c03004():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'word_clocks', 'vad_order') == None


def test_b02_c03005():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'word_clocks', 'word_clock') == None


def test_b02_c03006():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'word_clocks', 'word_sequence') == None


def test_b02_c03007():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'word_clocks', 'word_shape') == None


def test_b02_c03008():
    assert decode_payload_failure_reason(_make('b_wave_Error'), 'word_clocks', 'unclassified') == None


def test_b02_c03009():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'asr_recovery', 'decode_payload_invalid')
        == None
    )


def test_b02_c03010():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'asr_recovery', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03011():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'asr_recovery', 'empty_asr') == None


def test_b02_c03012():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c03013():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'asr_recovery', 'outside_admitted_source')
        == None
    )


def test_b02_c03014():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'asr_recovery', 'persist_payload_invalid')
        == None
    )


def test_b02_c03015():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'asr_recovery', 'retained_audio_invalid')
        == None
    )


def test_b02_c03016():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'asr_recovery', 'staged_audio_invalid')
        == None
    )


def test_b02_c03017():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'asr_recovery', 'unknown') == None


def test_b02_c03018():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'asr_recovery', 'unsupported_language')
        == None
    )


def test_b02_c03019():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c03020():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c03021():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'asr_recovery', 'vad_order') == None


def test_b02_c03022():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'asr_recovery', 'word_clock') == None


def test_b02_c03023():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'asr_recovery', 'word_sequence') == None


def test_b02_c03024():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'asr_recovery', 'word_shape') == None


def test_b02_c03025():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'asr_recovery', 'unclassified') == None


def test_b02_c03026():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'assemble_words', 'decode_payload_invalid')
        == None
    )


def test_b02_c03027():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'assemble_words', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03028():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'assemble_words', 'empty_asr') == None


def test_b02_c03029():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'assemble_words', 'no_owned_words') == None


def test_b02_c03030():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'assemble_words', 'outside_admitted_source')
        == None
    )


def test_b02_c03031():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'assemble_words', 'persist_payload_invalid')
        == None
    )


def test_b02_c03032():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'assemble_words', 'retained_audio_invalid')
        == None
    )


def test_b02_c03033():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'assemble_words', 'staged_audio_invalid')
        == None
    )


def test_b02_c03034():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'assemble_words', 'unknown') == None


def test_b02_c03035():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'assemble_words', 'unsupported_language')
        == None
    )


def test_b02_c03036():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'assemble_words', 'vad_bounds') == None


def test_b02_c03037():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c03038():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'assemble_words', 'vad_order') == None


def test_b02_c03039():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'assemble_words', 'word_clock') == None


def test_b02_c03040():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'assemble_words', 'word_sequence') == None


def test_b02_c03041():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'assemble_words', 'word_shape') == None


def test_b02_c03042():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'assemble_words', 'unclassified') == None


def test_b02_c03043():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'fetch_decode', 'decode_payload_invalid')
        == None
    )


def test_b02_c03044():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'fetch_decode', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03045():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'fetch_decode', 'empty_asr') == None


def test_b02_c03046():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c03047():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'fetch_decode', 'outside_admitted_source')
        == None
    )


def test_b02_c03048():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'fetch_decode', 'persist_payload_invalid')
        == None
    )


def test_b02_c03049():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'fetch_decode', 'retained_audio_invalid')
        == None
    )


def test_b02_c03050():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'fetch_decode', 'staged_audio_invalid')
        == None
    )


def test_b02_c03051():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'fetch_decode', 'unknown') == None


def test_b02_c03052():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'fetch_decode', 'unsupported_language')
        == None
    )


def test_b02_c03053():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c03054():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c03055():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'fetch_decode', 'vad_order') == None


def test_b02_c03056():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'fetch_decode', 'word_clock') == None


def test_b02_c03057():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'fetch_decode', 'word_sequence') == None


def test_b02_c03058():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'fetch_decode', 'word_shape') == None


def test_b02_c03059():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'fetch_decode', 'unclassified') == None


def test_b02_c03060():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'persist', 'decode_payload_invalid') == None
    )


def test_b02_c03061():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'persist', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03062():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'persist', 'empty_asr') == None


def test_b02_c03063():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'persist', 'no_owned_words') == None


def test_b02_c03064():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'persist', 'outside_admitted_source') == None
    )


def test_b02_c03065():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'persist', 'persist_payload_invalid') == None
    )


def test_b02_c03066():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'persist', 'retained_audio_invalid') == None
    )


def test_b02_c03067():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'persist', 'staged_audio_invalid') == None


def test_b02_c03068():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'persist', 'unknown') == None


def test_b02_c03069():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'persist', 'unsupported_language') == None


def test_b02_c03070():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'persist', 'vad_bounds') == None


def test_b02_c03071():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'persist', 'vad_nonfinite') == None


def test_b02_c03072():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'persist', 'vad_order') == None


def test_b02_c03073():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'persist', 'word_clock') == None


def test_b02_c03074():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'persist', 'word_sequence') == None


def test_b02_c03075():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'persist', 'word_shape') == None


def test_b02_c03076():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'persist', 'unclassified') == None


def test_b02_c03077():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'vad_windows', 'decode_payload_invalid')
        == None
    )


def test_b02_c03078():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'vad_windows', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03079():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'vad_windows', 'empty_asr') == None


def test_b02_c03080():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'vad_windows', 'no_owned_words') == None


def test_b02_c03081():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'vad_windows', 'outside_admitted_source')
        == None
    )


def test_b02_c03082():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'vad_windows', 'persist_payload_invalid')
        == None
    )


def test_b02_c03083():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'vad_windows', 'retained_audio_invalid')
        == None
    )


def test_b02_c03084():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'vad_windows', 'staged_audio_invalid') == None
    )


def test_b02_c03085():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'vad_windows', 'unknown') == None


def test_b02_c03086():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'vad_windows', 'unsupported_language') == None
    )


def test_b02_c03087():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'vad_windows', 'vad_bounds') == None


def test_b02_c03088():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c03089():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'vad_windows', 'vad_order') == None


def test_b02_c03090():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'vad_windows', 'word_clock') == None


def test_b02_c03091():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'vad_windows', 'word_sequence') == None


def test_b02_c03092():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'vad_windows', 'word_shape') == None


def test_b02_c03093():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'vad_windows', 'unclassified') == None


def test_b02_c03094():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'word_clocks', 'decode_payload_invalid')
        == None
    )


def test_b02_c03095():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'word_clocks', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03096():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'word_clocks', 'empty_asr') == None


def test_b02_c03097():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'word_clocks', 'no_owned_words') == None


def test_b02_c03098():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'word_clocks', 'outside_admitted_source')
        == None
    )


def test_b02_c03099():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'word_clocks', 'persist_payload_invalid')
        == None
    )


def test_b02_c03100():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'word_clocks', 'retained_audio_invalid')
        == None
    )


def test_b02_c03101():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'word_clocks', 'staged_audio_invalid') == None
    )


def test_b02_c03102():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'word_clocks', 'unknown') == None


def test_b02_c03103():
    assert (
        decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'word_clocks', 'unsupported_language') == None
    )


def test_b02_c03104():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'word_clocks', 'vad_bounds') == None


def test_b02_c03105():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c03106():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'word_clocks', 'vad_order') == None


def test_b02_c03107():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'word_clocks', 'word_clock') == None


def test_b02_c03108():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'word_clocks', 'word_sequence') == None


def test_b02_c03109():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'word_clocks', 'word_shape') == None


def test_b02_c03110():
    assert decode_payload_failure_reason(_make('t_DecodedDurationMismatch'), 'word_clocks', 'unclassified') == None


def test_b02_c03111():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'asr_recovery', 'decode_payload_invalid')
        == None
    )


def test_b02_c03112():
    assert (
        decode_payload_failure_reason(
            _make('t_FirestoreContentionExhausted'), 'asr_recovery', 'decoded_duration_mismatch'
        )
        == None
    )


def test_b02_c03113():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'asr_recovery', 'empty_asr') == None


def test_b02_c03114():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'asr_recovery', 'no_owned_words') == None
    )


def test_b02_c03115():
    assert (
        decode_payload_failure_reason(
            _make('t_FirestoreContentionExhausted'), 'asr_recovery', 'outside_admitted_source'
        )
        == None
    )


def test_b02_c03116():
    assert (
        decode_payload_failure_reason(
            _make('t_FirestoreContentionExhausted'), 'asr_recovery', 'persist_payload_invalid'
        )
        == None
    )


def test_b02_c03117():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'asr_recovery', 'retained_audio_invalid')
        == None
    )


def test_b02_c03118():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'asr_recovery', 'staged_audio_invalid')
        == None
    )


def test_b02_c03119():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'asr_recovery', 'unknown') == None


def test_b02_c03120():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'asr_recovery', 'unsupported_language')
        == None
    )


def test_b02_c03121():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c03122():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'asr_recovery', 'vad_nonfinite') == None
    )


def test_b02_c03123():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'asr_recovery', 'vad_order') == None


def test_b02_c03124():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'asr_recovery', 'word_clock') == None


def test_b02_c03125():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'asr_recovery', 'word_sequence') == None
    )


def test_b02_c03126():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'asr_recovery', 'word_shape') == None


def test_b02_c03127():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'asr_recovery', 'unclassified') == None
    )


def test_b02_c03128():
    assert (
        decode_payload_failure_reason(
            _make('t_FirestoreContentionExhausted'), 'assemble_words', 'decode_payload_invalid'
        )
        == None
    )


def test_b02_c03129():
    assert (
        decode_payload_failure_reason(
            _make('t_FirestoreContentionExhausted'), 'assemble_words', 'decoded_duration_mismatch'
        )
        == None
    )


def test_b02_c03130():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'assemble_words', 'empty_asr') == None


def test_b02_c03131():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'assemble_words', 'no_owned_words')
        == None
    )


def test_b02_c03132():
    assert (
        decode_payload_failure_reason(
            _make('t_FirestoreContentionExhausted'), 'assemble_words', 'outside_admitted_source'
        )
        == None
    )


def test_b02_c03133():
    assert (
        decode_payload_failure_reason(
            _make('t_FirestoreContentionExhausted'), 'assemble_words', 'persist_payload_invalid'
        )
        == None
    )


def test_b02_c03134():
    assert (
        decode_payload_failure_reason(
            _make('t_FirestoreContentionExhausted'), 'assemble_words', 'retained_audio_invalid'
        )
        == None
    )


def test_b02_c03135():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'assemble_words', 'staged_audio_invalid')
        == None
    )


def test_b02_c03136():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'assemble_words', 'unknown') == None


def test_b02_c03137():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'assemble_words', 'unsupported_language')
        == None
    )


def test_b02_c03138():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'assemble_words', 'vad_bounds') == None
    )


def test_b02_c03139():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'assemble_words', 'vad_nonfinite')
        == None
    )


def test_b02_c03140():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'assemble_words', 'vad_order') == None


def test_b02_c03141():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'assemble_words', 'word_clock') == None
    )


def test_b02_c03142():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'assemble_words', 'word_sequence')
        == None
    )


def test_b02_c03143():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'assemble_words', 'word_shape') == None
    )


def test_b02_c03144():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'assemble_words', 'unclassified') == None
    )


def test_b02_c03145():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'fetch_decode', 'decode_payload_invalid')
        == None
    )


def test_b02_c03146():
    assert (
        decode_payload_failure_reason(
            _make('t_FirestoreContentionExhausted'), 'fetch_decode', 'decoded_duration_mismatch'
        )
        == None
    )


def test_b02_c03147():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'fetch_decode', 'empty_asr') == None


def test_b02_c03148():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'fetch_decode', 'no_owned_words') == None
    )


def test_b02_c03149():
    assert (
        decode_payload_failure_reason(
            _make('t_FirestoreContentionExhausted'), 'fetch_decode', 'outside_admitted_source'
        )
        == None
    )


def test_b02_c03150():
    assert (
        decode_payload_failure_reason(
            _make('t_FirestoreContentionExhausted'), 'fetch_decode', 'persist_payload_invalid'
        )
        == None
    )


def test_b02_c03151():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'fetch_decode', 'retained_audio_invalid')
        == None
    )


def test_b02_c03152():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'fetch_decode', 'staged_audio_invalid')
        == None
    )


def test_b02_c03153():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'fetch_decode', 'unknown') == None


def test_b02_c03154():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'fetch_decode', 'unsupported_language')
        == None
    )


def test_b02_c03155():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c03156():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'fetch_decode', 'vad_nonfinite') == None
    )


def test_b02_c03157():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'fetch_decode', 'vad_order') == None


def test_b02_c03158():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'fetch_decode', 'word_clock') == None


def test_b02_c03159():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'fetch_decode', 'word_sequence') == None
    )


def test_b02_c03160():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'fetch_decode', 'word_shape') == None


def test_b02_c03161():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'fetch_decode', 'unclassified') == None
    )


def test_b02_c03162():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'persist', 'decode_payload_invalid')
        == None
    )


def test_b02_c03163():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'persist', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03164():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'persist', 'empty_asr') == None


def test_b02_c03165():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'persist', 'no_owned_words') == None


def test_b02_c03166():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'persist', 'outside_admitted_source')
        == None
    )


def test_b02_c03167():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'persist', 'persist_payload_invalid')
        == None
    )


def test_b02_c03168():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'persist', 'retained_audio_invalid')
        == None
    )


def test_b02_c03169():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'persist', 'staged_audio_invalid')
        == None
    )


def test_b02_c03170():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'persist', 'unknown') == None


def test_b02_c03171():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'persist', 'unsupported_language')
        == None
    )


def test_b02_c03172():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'persist', 'vad_bounds') == None


def test_b02_c03173():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'persist', 'vad_nonfinite') == None


def test_b02_c03174():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'persist', 'vad_order') == None


def test_b02_c03175():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'persist', 'word_clock') == None


def test_b02_c03176():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'persist', 'word_sequence') == None


def test_b02_c03177():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'persist', 'word_shape') == None


def test_b02_c03178():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'persist', 'unclassified') == None


def test_b02_c03179():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'vad_windows', 'decode_payload_invalid')
        == None
    )


def test_b02_c03180():
    assert (
        decode_payload_failure_reason(
            _make('t_FirestoreContentionExhausted'), 'vad_windows', 'decoded_duration_mismatch'
        )
        == None
    )


def test_b02_c03181():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'vad_windows', 'empty_asr') == None


def test_b02_c03182():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'vad_windows', 'no_owned_words') == None
    )


def test_b02_c03183():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'vad_windows', 'outside_admitted_source')
        == None
    )


def test_b02_c03184():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'vad_windows', 'persist_payload_invalid')
        == None
    )


def test_b02_c03185():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'vad_windows', 'retained_audio_invalid')
        == None
    )


def test_b02_c03186():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'vad_windows', 'staged_audio_invalid')
        == None
    )


def test_b02_c03187():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'vad_windows', 'unknown') == None


def test_b02_c03188():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'vad_windows', 'unsupported_language')
        == None
    )


def test_b02_c03189():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'vad_windows', 'vad_bounds') == None


def test_b02_c03190():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'vad_windows', 'vad_nonfinite') == None
    )


def test_b02_c03191():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'vad_windows', 'vad_order') == None


def test_b02_c03192():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'vad_windows', 'word_clock') == None


def test_b02_c03193():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'vad_windows', 'word_sequence') == None
    )


def test_b02_c03194():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'vad_windows', 'word_shape') == None


def test_b02_c03195():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'vad_windows', 'unclassified') == None


def test_b02_c03196():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'word_clocks', 'decode_payload_invalid')
        == None
    )


def test_b02_c03197():
    assert (
        decode_payload_failure_reason(
            _make('t_FirestoreContentionExhausted'), 'word_clocks', 'decoded_duration_mismatch'
        )
        == None
    )


def test_b02_c03198():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'word_clocks', 'empty_asr') == None


def test_b02_c03199():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'word_clocks', 'no_owned_words') == None
    )


def test_b02_c03200():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'word_clocks', 'outside_admitted_source')
        == None
    )


def test_b02_c03201():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'word_clocks', 'persist_payload_invalid')
        == None
    )


def test_b02_c03202():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'word_clocks', 'retained_audio_invalid')
        == None
    )


def test_b02_c03203():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'word_clocks', 'staged_audio_invalid')
        == None
    )


def test_b02_c03204():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'word_clocks', 'unknown') == None


def test_b02_c03205():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'word_clocks', 'unsupported_language')
        == None
    )


def test_b02_c03206():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'word_clocks', 'vad_bounds') == None


def test_b02_c03207():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'word_clocks', 'vad_nonfinite') == None
    )


def test_b02_c03208():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'word_clocks', 'vad_order') == None


def test_b02_c03209():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'word_clocks', 'word_clock') == None


def test_b02_c03210():
    assert (
        decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'word_clocks', 'word_sequence') == None
    )


def test_b02_c03211():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'word_clocks', 'word_shape') == None


def test_b02_c03212():
    assert decode_payload_failure_reason(_make('t_FirestoreContentionExhausted'), 'word_clocks', 'unclassified') == None


def test_b02_c03213():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'asr_recovery', 'decode_payload_invalid')
        == None
    )


def test_b02_c03214():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'asr_recovery', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03215():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'asr_recovery', 'empty_asr') == None


def test_b02_c03216():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c03217():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'asr_recovery', 'outside_admitted_source')
        == None
    )


def test_b02_c03218():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'asr_recovery', 'persist_payload_invalid')
        == None
    )


def test_b02_c03219():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'asr_recovery', 'retained_audio_invalid')
        == None
    )


def test_b02_c03220():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'asr_recovery', 'staged_audio_invalid')
        == None
    )


def test_b02_c03221():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'asr_recovery', 'unknown') == None


def test_b02_c03222():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'asr_recovery', 'unsupported_language')
        == None
    )


def test_b02_c03223():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c03224():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c03225():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'asr_recovery', 'vad_order') == None


def test_b02_c03226():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'asr_recovery', 'word_clock') == None


def test_b02_c03227():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'asr_recovery', 'word_sequence') == None


def test_b02_c03228():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'asr_recovery', 'word_shape') == None


def test_b02_c03229():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'asr_recovery', 'unclassified') == None


def test_b02_c03230():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'assemble_words', 'decode_payload_invalid')
        == None
    )


def test_b02_c03231():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'assemble_words', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03232():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'assemble_words', 'empty_asr') == None


def test_b02_c03233():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'assemble_words', 'no_owned_words') == None


def test_b02_c03234():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'assemble_words', 'outside_admitted_source')
        == None
    )


def test_b02_c03235():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'assemble_words', 'persist_payload_invalid')
        == None
    )


def test_b02_c03236():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'assemble_words', 'retained_audio_invalid')
        == None
    )


def test_b02_c03237():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'assemble_words', 'staged_audio_invalid')
        == None
    )


def test_b02_c03238():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'assemble_words', 'unknown') == None


def test_b02_c03239():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'assemble_words', 'unsupported_language')
        == None
    )


def test_b02_c03240():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'assemble_words', 'vad_bounds') == None


def test_b02_c03241():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c03242():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'assemble_words', 'vad_order') == None


def test_b02_c03243():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'assemble_words', 'word_clock') == None


def test_b02_c03244():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'assemble_words', 'word_sequence') == None


def test_b02_c03245():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'assemble_words', 'word_shape') == None


def test_b02_c03246():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'assemble_words', 'unclassified') == None


def test_b02_c03247():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'fetch_decode', 'decode_payload_invalid')
        == None
    )


def test_b02_c03248():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'fetch_decode', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03249():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'fetch_decode', 'empty_asr') == None


def test_b02_c03250():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c03251():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'fetch_decode', 'outside_admitted_source')
        == None
    )


def test_b02_c03252():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'fetch_decode', 'persist_payload_invalid')
        == None
    )


def test_b02_c03253():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'fetch_decode', 'retained_audio_invalid')
        == None
    )


def test_b02_c03254():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'fetch_decode', 'staged_audio_invalid')
        == None
    )


def test_b02_c03255():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'fetch_decode', 'unknown') == None


def test_b02_c03256():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'fetch_decode', 'unsupported_language')
        == None
    )


def test_b02_c03257():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c03258():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c03259():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'fetch_decode', 'vad_order') == None


def test_b02_c03260():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'fetch_decode', 'word_clock') == None


def test_b02_c03261():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'fetch_decode', 'word_sequence') == None


def test_b02_c03262():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'fetch_decode', 'word_shape') == None


def test_b02_c03263():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'fetch_decode', 'unclassified') == None


def test_b02_c03264():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'persist', 'decode_payload_invalid') == None
    )


def test_b02_c03265():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'persist', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03266():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'persist', 'empty_asr') == None


def test_b02_c03267():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'persist', 'no_owned_words') == None


def test_b02_c03268():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'persist', 'outside_admitted_source') == None
    )


def test_b02_c03269():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'persist', 'persist_payload_invalid') == None
    )


def test_b02_c03270():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'persist', 'retained_audio_invalid') == None
    )


def test_b02_c03271():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'persist', 'staged_audio_invalid') == None


def test_b02_c03272():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'persist', 'unknown') == None


def test_b02_c03273():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'persist', 'unsupported_language') == None


def test_b02_c03274():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'persist', 'vad_bounds') == None


def test_b02_c03275():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'persist', 'vad_nonfinite') == None


def test_b02_c03276():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'persist', 'vad_order') == None


def test_b02_c03277():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'persist', 'word_clock') == None


def test_b02_c03278():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'persist', 'word_sequence') == None


def test_b02_c03279():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'persist', 'word_shape') == None


def test_b02_c03280():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'persist', 'unclassified') == None


def test_b02_c03281():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'vad_windows', 'decode_payload_invalid')
        == None
    )


def test_b02_c03282():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'vad_windows', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03283():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'vad_windows', 'empty_asr') == None


def test_b02_c03284():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'vad_windows', 'no_owned_words') == None


def test_b02_c03285():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'vad_windows', 'outside_admitted_source')
        == None
    )


def test_b02_c03286():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'vad_windows', 'persist_payload_invalid')
        == None
    )


def test_b02_c03287():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'vad_windows', 'retained_audio_invalid')
        == None
    )


def test_b02_c03288():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'vad_windows', 'staged_audio_invalid') == None
    )


def test_b02_c03289():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'vad_windows', 'unknown') == None


def test_b02_c03290():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'vad_windows', 'unsupported_language') == None
    )


def test_b02_c03291():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'vad_windows', 'vad_bounds') == None


def test_b02_c03292():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c03293():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'vad_windows', 'vad_order') == None


def test_b02_c03294():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'vad_windows', 'word_clock') == None


def test_b02_c03295():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'vad_windows', 'word_sequence') == None


def test_b02_c03296():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'vad_windows', 'word_shape') == None


def test_b02_c03297():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'vad_windows', 'unclassified') == None


def test_b02_c03298():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'word_clocks', 'decode_payload_invalid')
        == None
    )


def test_b02_c03299():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'word_clocks', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03300():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'word_clocks', 'empty_asr') == None


def test_b02_c03301():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'word_clocks', 'no_owned_words') == None


def test_b02_c03302():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'word_clocks', 'outside_admitted_source')
        == None
    )


def test_b02_c03303():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'word_clocks', 'persist_payload_invalid')
        == None
    )


def test_b02_c03304():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'word_clocks', 'retained_audio_invalid')
        == None
    )


def test_b02_c03305():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'word_clocks', 'staged_audio_invalid') == None
    )


def test_b02_c03306():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'word_clocks', 'unknown') == None


def test_b02_c03307():
    assert (
        decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'word_clocks', 'unsupported_language') == None
    )


def test_b02_c03308():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'word_clocks', 'vad_bounds') == None


def test_b02_c03309():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c03310():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'word_clocks', 'vad_order') == None


def test_b02_c03311():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'word_clocks', 'word_clock') == None


def test_b02_c03312():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'word_clocks', 'word_sequence') == None


def test_b02_c03313():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'word_clocks', 'word_shape') == None


def test_b02_c03314():
    assert decode_payload_failure_reason(_make('t_InvalidRetainedManifest'), 'word_clocks', 'unclassified') == None


def test_b02_c03315():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'asr_recovery', 'decode_payload_invalid') == None
    )


def test_b02_c03316():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'asr_recovery', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03317():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'asr_recovery', 'empty_asr') == None


def test_b02_c03318():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c03319():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'asr_recovery', 'outside_admitted_source')
        == None
    )


def test_b02_c03320():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'asr_recovery', 'persist_payload_invalid')
        == None
    )


def test_b02_c03321():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'asr_recovery', 'retained_audio_invalid') == None
    )


def test_b02_c03322():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'asr_recovery', 'staged_audio_invalid') == None
    )


def test_b02_c03323():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'asr_recovery', 'unknown') == None


def test_b02_c03324():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'asr_recovery', 'unsupported_language') == None
    )


def test_b02_c03325():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c03326():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c03327():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'asr_recovery', 'vad_order') == None


def test_b02_c03328():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'asr_recovery', 'word_clock') == None


def test_b02_c03329():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'asr_recovery', 'word_sequence') == None


def test_b02_c03330():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'asr_recovery', 'word_shape') == None


def test_b02_c03331():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'asr_recovery', 'unclassified') == None


def test_b02_c03332():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'assemble_words', 'decode_payload_invalid')
        == None
    )


def test_b02_c03333():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'assemble_words', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03334():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'assemble_words', 'empty_asr') == None


def test_b02_c03335():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'assemble_words', 'no_owned_words') == None


def test_b02_c03336():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'assemble_words', 'outside_admitted_source')
        == None
    )


def test_b02_c03337():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'assemble_words', 'persist_payload_invalid')
        == None
    )


def test_b02_c03338():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'assemble_words', 'retained_audio_invalid')
        == None
    )


def test_b02_c03339():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'assemble_words', 'staged_audio_invalid') == None
    )


def test_b02_c03340():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'assemble_words', 'unknown') == None


def test_b02_c03341():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'assemble_words', 'unsupported_language') == None
    )


def test_b02_c03342():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'assemble_words', 'vad_bounds') == None


def test_b02_c03343():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c03344():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'assemble_words', 'vad_order') == None


def test_b02_c03345():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'assemble_words', 'word_clock') == None


def test_b02_c03346():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'assemble_words', 'word_sequence') == None


def test_b02_c03347():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'assemble_words', 'word_shape') == None


def test_b02_c03348():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'assemble_words', 'unclassified') == None


def test_b02_c03349():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'fetch_decode', 'decode_payload_invalid') == None
    )


def test_b02_c03350():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'fetch_decode', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03351():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'fetch_decode', 'empty_asr') == None


def test_b02_c03352():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c03353():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'fetch_decode', 'outside_admitted_source')
        == None
    )


def test_b02_c03354():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'fetch_decode', 'persist_payload_invalid')
        == None
    )


def test_b02_c03355():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'fetch_decode', 'retained_audio_invalid') == None
    )


def test_b02_c03356():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'fetch_decode', 'staged_audio_invalid') == None
    )


def test_b02_c03357():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'fetch_decode', 'unknown') == None


def test_b02_c03358():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'fetch_decode', 'unsupported_language') == None
    )


def test_b02_c03359():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c03360():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c03361():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'fetch_decode', 'vad_order') == None


def test_b02_c03362():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'fetch_decode', 'word_clock') == None


def test_b02_c03363():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'fetch_decode', 'word_sequence') == None


def test_b02_c03364():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'fetch_decode', 'word_shape') == None


def test_b02_c03365():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'fetch_decode', 'unclassified') == None


def test_b02_c03366():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'persist', 'decode_payload_invalid') == None


def test_b02_c03367():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'persist', 'decoded_duration_mismatch') == None
    )


def test_b02_c03368():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'persist', 'empty_asr') == None


def test_b02_c03369():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'persist', 'no_owned_words') == None


def test_b02_c03370():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'persist', 'outside_admitted_source') == None


def test_b02_c03371():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'persist', 'persist_payload_invalid') == None


def test_b02_c03372():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'persist', 'retained_audio_invalid') == None


def test_b02_c03373():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'persist', 'staged_audio_invalid') == None


def test_b02_c03374():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'persist', 'unknown') == None


def test_b02_c03375():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'persist', 'unsupported_language') == None


def test_b02_c03376():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'persist', 'vad_bounds') == None


def test_b02_c03377():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'persist', 'vad_nonfinite') == None


def test_b02_c03378():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'persist', 'vad_order') == None


def test_b02_c03379():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'persist', 'word_clock') == None


def test_b02_c03380():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'persist', 'word_sequence') == None


def test_b02_c03381():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'persist', 'word_shape') == None


def test_b02_c03382():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'persist', 'unclassified') == None


def test_b02_c03383():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'vad_windows', 'decode_payload_invalid') == None
    )


def test_b02_c03384():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'vad_windows', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03385():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'vad_windows', 'empty_asr') == None


def test_b02_c03386():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'vad_windows', 'no_owned_words') == None


def test_b02_c03387():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'vad_windows', 'outside_admitted_source') == None
    )


def test_b02_c03388():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'vad_windows', 'persist_payload_invalid') == None
    )


def test_b02_c03389():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'vad_windows', 'retained_audio_invalid') == None
    )


def test_b02_c03390():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c03391():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'vad_windows', 'unknown') == None


def test_b02_c03392():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'vad_windows', 'unsupported_language') == None


def test_b02_c03393():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'vad_windows', 'vad_bounds') == None


def test_b02_c03394():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c03395():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'vad_windows', 'vad_order') == None


def test_b02_c03396():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'vad_windows', 'word_clock') == None


def test_b02_c03397():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'vad_windows', 'word_sequence') == None


def test_b02_c03398():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'vad_windows', 'word_shape') == None


def test_b02_c03399():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'vad_windows', 'unclassified') == None


def test_b02_c03400():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'word_clocks', 'decode_payload_invalid') == None
    )


def test_b02_c03401():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'word_clocks', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03402():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'word_clocks', 'empty_asr') == None


def test_b02_c03403():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'word_clocks', 'no_owned_words') == None


def test_b02_c03404():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'word_clocks', 'outside_admitted_source') == None
    )


def test_b02_c03405():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'word_clocks', 'persist_payload_invalid') == None
    )


def test_b02_c03406():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'word_clocks', 'retained_audio_invalid') == None
    )


def test_b02_c03407():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c03408():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'word_clocks', 'unknown') == None


def test_b02_c03409():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'word_clocks', 'unsupported_language') == None


def test_b02_c03410():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'word_clocks', 'vad_bounds') == None


def test_b02_c03411():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c03412():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'word_clocks', 'vad_order') == None


def test_b02_c03413():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'word_clocks', 'word_clock') == None


def test_b02_c03414():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'word_clocks', 'word_sequence') == None


def test_b02_c03415():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'word_clocks', 'word_shape') == None


def test_b02_c03416():
    assert decode_payload_failure_reason(_make('t_RetainedAudioInvalid'), 'word_clocks', 'unclassified') == None


def test_b02_c03417():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'asr_recovery', 'decode_payload_invalid'
        )
        == None
    )


def test_b02_c03418():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'asr_recovery', 'decoded_duration_mismatch'
        )
        == None
    )


def test_b02_c03419():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'asr_recovery', 'empty_asr')
        == None
    )


def test_b02_c03420():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'asr_recovery', 'no_owned_words')
        == None
    )


def test_b02_c03421():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'asr_recovery', 'outside_admitted_source'
        )
        == None
    )


def test_b02_c03422():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'asr_recovery', 'persist_payload_invalid'
        )
        == None
    )


def test_b02_c03423():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'asr_recovery', 'retained_audio_invalid'
        )
        == None
    )


def test_b02_c03424():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'asr_recovery', 'staged_audio_invalid'
        )
        == None
    )


def test_b02_c03425():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'asr_recovery', 'unknown') == None
    )


def test_b02_c03426():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'asr_recovery', 'unsupported_language'
        )
        == None
    )


def test_b02_c03427():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'asr_recovery', 'vad_bounds')
        == None
    )


def test_b02_c03428():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'asr_recovery', 'vad_nonfinite')
        == None
    )


def test_b02_c03429():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'asr_recovery', 'vad_order')
        == None
    )


def test_b02_c03430():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'asr_recovery', 'word_clock')
        == None
    )


def test_b02_c03431():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'asr_recovery', 'word_sequence')
        == None
    )


def test_b02_c03432():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'asr_recovery', 'word_shape')
        == None
    )


def test_b02_c03433():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'asr_recovery', 'unclassified')
        == None
    )


def test_b02_c03434():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'assemble_words', 'decode_payload_invalid'
        )
        == None
    )


def test_b02_c03435():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'assemble_words', 'decoded_duration_mismatch'
        )
        == None
    )


def test_b02_c03436():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'assemble_words', 'empty_asr')
        == None
    )


def test_b02_c03437():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'assemble_words', 'no_owned_words')
        == None
    )


def test_b02_c03438():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'assemble_words', 'outside_admitted_source'
        )
        == None
    )


def test_b02_c03439():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'assemble_words', 'persist_payload_invalid'
        )
        == None
    )


def test_b02_c03440():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'assemble_words', 'retained_audio_invalid'
        )
        == None
    )


def test_b02_c03441():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'assemble_words', 'staged_audio_invalid'
        )
        == None
    )


def test_b02_c03442():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'assemble_words', 'unknown')
        == None
    )


def test_b02_c03443():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'assemble_words', 'unsupported_language'
        )
        == None
    )


def test_b02_c03444():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'assemble_words', 'vad_bounds')
        == None
    )


def test_b02_c03445():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'assemble_words', 'vad_nonfinite')
        == None
    )


def test_b02_c03446():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'assemble_words', 'vad_order')
        == None
    )


def test_b02_c03447():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'assemble_words', 'word_clock')
        == None
    )


def test_b02_c03448():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'assemble_words', 'word_sequence')
        == None
    )


def test_b02_c03449():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'assemble_words', 'word_shape')
        == None
    )


def test_b02_c03450():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'assemble_words', 'unclassified')
        == None
    )


def test_b02_c03451():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'fetch_decode', 'decode_payload_invalid'
        )
        == None
    )


def test_b02_c03452():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'fetch_decode', 'decoded_duration_mismatch'
        )
        == None
    )


def test_b02_c03453():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'fetch_decode', 'empty_asr')
        == None
    )


def test_b02_c03454():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'fetch_decode', 'no_owned_words')
        == None
    )


def test_b02_c03455():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'fetch_decode', 'outside_admitted_source'
        )
        == None
    )


def test_b02_c03456():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'fetch_decode', 'persist_payload_invalid'
        )
        == None
    )


def test_b02_c03457():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'fetch_decode', 'retained_audio_invalid'
        )
        == None
    )


def test_b02_c03458():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'fetch_decode', 'staged_audio_invalid'
        )
        == None
    )


def test_b02_c03459():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'fetch_decode', 'unknown') == None
    )


def test_b02_c03460():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'fetch_decode', 'unsupported_language'
        )
        == None
    )


def test_b02_c03461():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'fetch_decode', 'vad_bounds')
        == None
    )


def test_b02_c03462():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'fetch_decode', 'vad_nonfinite')
        == None
    )


def test_b02_c03463():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'fetch_decode', 'vad_order')
        == None
    )


def test_b02_c03464():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'fetch_decode', 'word_clock')
        == None
    )


def test_b02_c03465():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'fetch_decode', 'word_sequence')
        == None
    )


def test_b02_c03466():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'fetch_decode', 'word_shape')
        == None
    )


def test_b02_c03467():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'fetch_decode', 'unclassified')
        == None
    )


def test_b02_c03468():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'persist', 'decode_payload_invalid'
        )
        == None
    )


def test_b02_c03469():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'persist', 'decoded_duration_mismatch'
        )
        == None
    )


def test_b02_c03470():
    assert decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'persist', 'empty_asr') == None


def test_b02_c03471():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'persist', 'no_owned_words')
        == None
    )


def test_b02_c03472():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'persist', 'outside_admitted_source'
        )
        == None
    )


def test_b02_c03473():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'persist', 'persist_payload_invalid'
        )
        == None
    )


def test_b02_c03474():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'persist', 'retained_audio_invalid'
        )
        == None
    )


def test_b02_c03475():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'persist', 'staged_audio_invalid')
        == None
    )


def test_b02_c03476():
    assert decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'persist', 'unknown') == None


def test_b02_c03477():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'persist', 'unsupported_language')
        == None
    )


def test_b02_c03478():
    assert decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'persist', 'vad_bounds') == None


def test_b02_c03479():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'persist', 'vad_nonfinite') == None
    )


def test_b02_c03480():
    assert decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'persist', 'vad_order') == None


def test_b02_c03481():
    assert decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'persist', 'word_clock') == None


def test_b02_c03482():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'persist', 'word_sequence') == None
    )


def test_b02_c03483():
    assert decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'persist', 'word_shape') == None


def test_b02_c03484():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'persist', 'unclassified') == None
    )


def test_b02_c03485():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'vad_windows', 'decode_payload_invalid'
        )
        == None
    )


def test_b02_c03486():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'vad_windows', 'decoded_duration_mismatch'
        )
        == None
    )


def test_b02_c03487():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'vad_windows', 'empty_asr') == None
    )


def test_b02_c03488():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'vad_windows', 'no_owned_words')
        == None
    )


def test_b02_c03489():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'vad_windows', 'outside_admitted_source'
        )
        == None
    )


def test_b02_c03490():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'vad_windows', 'persist_payload_invalid'
        )
        == None
    )


def test_b02_c03491():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'vad_windows', 'retained_audio_invalid'
        )
        == None
    )


def test_b02_c03492():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'vad_windows', 'staged_audio_invalid'
        )
        == None
    )


def test_b02_c03493():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'vad_windows', 'unknown') == None
    )


def test_b02_c03494():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'vad_windows', 'unsupported_language'
        )
        == None
    )


def test_b02_c03495():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'vad_windows', 'vad_bounds')
        == None
    )


def test_b02_c03496():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'vad_windows', 'vad_nonfinite')
        == None
    )


def test_b02_c03497():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'vad_windows', 'vad_order') == None
    )


def test_b02_c03498():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'vad_windows', 'word_clock')
        == None
    )


def test_b02_c03499():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'vad_windows', 'word_sequence')
        == None
    )


def test_b02_c03500():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'vad_windows', 'word_shape')
        == None
    )


def test_b02_c03501():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'vad_windows', 'unclassified')
        == None
    )


def test_b02_c03502():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'word_clocks', 'decode_payload_invalid'
        )
        == None
    )


def test_b02_c03503():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'word_clocks', 'decoded_duration_mismatch'
        )
        == None
    )


def test_b02_c03504():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'word_clocks', 'empty_asr') == None
    )


def test_b02_c03505():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'word_clocks', 'no_owned_words')
        == None
    )


def test_b02_c03506():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'word_clocks', 'outside_admitted_source'
        )
        == None
    )


def test_b02_c03507():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'word_clocks', 'persist_payload_invalid'
        )
        == None
    )


def test_b02_c03508():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'word_clocks', 'retained_audio_invalid'
        )
        == None
    )


def test_b02_c03509():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'word_clocks', 'staged_audio_invalid'
        )
        == None
    )


def test_b02_c03510():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'word_clocks', 'unknown') == None
    )


def test_b02_c03511():
    assert (
        decode_payload_failure_reason(
            _make('t_RetainedAudioOutsideAdmittedSource'), 'word_clocks', 'unsupported_language'
        )
        == None
    )


def test_b02_c03512():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'word_clocks', 'vad_bounds')
        == None
    )


def test_b02_c03513():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'word_clocks', 'vad_nonfinite')
        == None
    )


def test_b02_c03514():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'word_clocks', 'vad_order') == None
    )


def test_b02_c03515():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'word_clocks', 'word_clock')
        == None
    )


def test_b02_c03516():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'word_clocks', 'word_sequence')
        == None
    )


def test_b02_c03517():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'word_clocks', 'word_shape')
        == None
    )


def test_b02_c03518():
    assert (
        decode_payload_failure_reason(_make('t_RetainedAudioOutsideAdmittedSource'), 'word_clocks', 'unclassified')
        == None
    )


def test_b02_c03519():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'asr_recovery', 'decode_payload_invalid')
        == None
    )


def test_b02_c03520():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'asr_recovery', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03521():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'asr_recovery', 'empty_asr') == None


def test_b02_c03522():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c03523():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'asr_recovery', 'outside_admitted_source')
        == None
    )


def test_b02_c03524():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'asr_recovery', 'persist_payload_invalid')
        == None
    )


def test_b02_c03525():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'asr_recovery', 'retained_audio_invalid')
        == None
    )


def test_b02_c03526():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'asr_recovery', 'staged_audio_invalid') == None
    )


def test_b02_c03527():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'asr_recovery', 'unknown') == None


def test_b02_c03528():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'asr_recovery', 'unsupported_language') == None
    )


def test_b02_c03529():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c03530():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c03531():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'asr_recovery', 'vad_order') == None


def test_b02_c03532():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'asr_recovery', 'word_clock') == None


def test_b02_c03533():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'asr_recovery', 'word_sequence') == None


def test_b02_c03534():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'asr_recovery', 'word_shape') == None


def test_b02_c03535():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'asr_recovery', 'unclassified') == None


def test_b02_c03536():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'assemble_words', 'decode_payload_invalid')
        == None
    )


def test_b02_c03537():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'assemble_words', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03538():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'assemble_words', 'empty_asr') == None


def test_b02_c03539():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'assemble_words', 'no_owned_words') == None


def test_b02_c03540():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'assemble_words', 'outside_admitted_source')
        == None
    )


def test_b02_c03541():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'assemble_words', 'persist_payload_invalid')
        == None
    )


def test_b02_c03542():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'assemble_words', 'retained_audio_invalid')
        == None
    )


def test_b02_c03543():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'assemble_words', 'staged_audio_invalid')
        == None
    )


def test_b02_c03544():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'assemble_words', 'unknown') == None


def test_b02_c03545():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'assemble_words', 'unsupported_language')
        == None
    )


def test_b02_c03546():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'assemble_words', 'vad_bounds') == None


def test_b02_c03547():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c03548():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'assemble_words', 'vad_order') == None


def test_b02_c03549():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'assemble_words', 'word_clock') == None


def test_b02_c03550():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'assemble_words', 'word_sequence') == None


def test_b02_c03551():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'assemble_words', 'word_shape') == None


def test_b02_c03552():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'assemble_words', 'unclassified') == None


def test_b02_c03553():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'fetch_decode', 'decode_payload_invalid')
        == None
    )


def test_b02_c03554():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'fetch_decode', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03555():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'fetch_decode', 'empty_asr') == None


def test_b02_c03556():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c03557():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'fetch_decode', 'outside_admitted_source')
        == None
    )


def test_b02_c03558():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'fetch_decode', 'persist_payload_invalid')
        == None
    )


def test_b02_c03559():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'fetch_decode', 'retained_audio_invalid')
        == None
    )


def test_b02_c03560():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'fetch_decode', 'staged_audio_invalid') == None
    )


def test_b02_c03561():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'fetch_decode', 'unknown') == None


def test_b02_c03562():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'fetch_decode', 'unsupported_language') == None
    )


def test_b02_c03563():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c03564():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c03565():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'fetch_decode', 'vad_order') == None


def test_b02_c03566():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'fetch_decode', 'word_clock') == None


def test_b02_c03567():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'fetch_decode', 'word_sequence') == None


def test_b02_c03568():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'fetch_decode', 'word_shape') == None


def test_b02_c03569():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'fetch_decode', 'unclassified') == None


def test_b02_c03570():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'persist', 'decode_payload_invalid') == None


def test_b02_c03571():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'persist', 'decoded_duration_mismatch') == None
    )


def test_b02_c03572():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'persist', 'empty_asr') == None


def test_b02_c03573():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'persist', 'no_owned_words') == None


def test_b02_c03574():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'persist', 'outside_admitted_source') == None


def test_b02_c03575():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'persist', 'persist_payload_invalid') == None


def test_b02_c03576():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'persist', 'retained_audio_invalid') == None


def test_b02_c03577():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'persist', 'staged_audio_invalid') == None


def test_b02_c03578():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'persist', 'unknown') == None


def test_b02_c03579():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'persist', 'unsupported_language') == None


def test_b02_c03580():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'persist', 'vad_bounds') == None


def test_b02_c03581():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'persist', 'vad_nonfinite') == None


def test_b02_c03582():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'persist', 'vad_order') == None


def test_b02_c03583():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'persist', 'word_clock') == None


def test_b02_c03584():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'persist', 'word_sequence') == None


def test_b02_c03585():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'persist', 'word_shape') == None


def test_b02_c03586():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'persist', 'unclassified') == None


def test_b02_c03587():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'vad_windows', 'decode_payload_invalid') == None
    )


def test_b02_c03588():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'vad_windows', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03589():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'vad_windows', 'empty_asr') == None


def test_b02_c03590():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'vad_windows', 'no_owned_words') == None


def test_b02_c03591():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'vad_windows', 'outside_admitted_source')
        == None
    )


def test_b02_c03592():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'vad_windows', 'persist_payload_invalid')
        == None
    )


def test_b02_c03593():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'vad_windows', 'retained_audio_invalid') == None
    )


def test_b02_c03594():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'vad_windows', 'staged_audio_invalid') == None
    )


def test_b02_c03595():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'vad_windows', 'unknown') == None


def test_b02_c03596():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'vad_windows', 'unsupported_language') == None
    )


def test_b02_c03597():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'vad_windows', 'vad_bounds') == None


def test_b02_c03598():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c03599():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'vad_windows', 'vad_order') == None


def test_b02_c03600():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'vad_windows', 'word_clock') == None


def test_b02_c03601():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'vad_windows', 'word_sequence') == None


def test_b02_c03602():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'vad_windows', 'word_shape') == None


def test_b02_c03603():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'vad_windows', 'unclassified') == None


def test_b02_c03604():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'word_clocks', 'decode_payload_invalid') == None
    )


def test_b02_c03605():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'word_clocks', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03606():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'word_clocks', 'empty_asr') == None


def test_b02_c03607():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'word_clocks', 'no_owned_words') == None


def test_b02_c03608():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'word_clocks', 'outside_admitted_source')
        == None
    )


def test_b02_c03609():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'word_clocks', 'persist_payload_invalid')
        == None
    )


def test_b02_c03610():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'word_clocks', 'retained_audio_invalid') == None
    )


def test_b02_c03611():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'word_clocks', 'staged_audio_invalid') == None
    )


def test_b02_c03612():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'word_clocks', 'unknown') == None


def test_b02_c03613():
    assert (
        decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'word_clocks', 'unsupported_language') == None
    )


def test_b02_c03614():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'word_clocks', 'vad_bounds') == None


def test_b02_c03615():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c03616():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'word_clocks', 'vad_order') == None


def test_b02_c03617():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'word_clocks', 'word_clock') == None


def test_b02_c03618():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'word_clocks', 'word_sequence') == None


def test_b02_c03619():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'word_clocks', 'word_shape') == None


def test_b02_c03620():
    assert decode_payload_failure_reason(_make('t_StagedArtifactInvalid'), 'word_clocks', 'unclassified') == None


def test_b02_c03621():
    assert (
        decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'asr_recovery', 'decode_payload_invalid') == None
    )


def test_b02_c03622():
    assert (
        decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'asr_recovery', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03623():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'asr_recovery', 'empty_asr') == None


def test_b02_c03624():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'asr_recovery', 'no_owned_words') == None


def test_b02_c03625():
    assert (
        decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'asr_recovery', 'outside_admitted_source') == None
    )


def test_b02_c03626():
    assert (
        decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'asr_recovery', 'persist_payload_invalid') == None
    )


def test_b02_c03627():
    assert (
        decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'asr_recovery', 'retained_audio_invalid') == None
    )


def test_b02_c03628():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'asr_recovery', 'staged_audio_invalid') == None


def test_b02_c03629():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'asr_recovery', 'unknown') == None


def test_b02_c03630():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'asr_recovery', 'unsupported_language') == None


def test_b02_c03631():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'asr_recovery', 'vad_bounds') == None


def test_b02_c03632():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'asr_recovery', 'vad_nonfinite') == None


def test_b02_c03633():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'asr_recovery', 'vad_order') == None


def test_b02_c03634():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'asr_recovery', 'word_clock') == None


def test_b02_c03635():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'asr_recovery', 'word_sequence') == None


def test_b02_c03636():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'asr_recovery', 'word_shape') == None


def test_b02_c03637():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'asr_recovery', 'unclassified') == None


def test_b02_c03638():
    assert (
        decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'assemble_words', 'decode_payload_invalid') == None
    )


def test_b02_c03639():
    assert (
        decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'assemble_words', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03640():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'assemble_words', 'empty_asr') == None


def test_b02_c03641():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'assemble_words', 'no_owned_words') == None


def test_b02_c03642():
    assert (
        decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'assemble_words', 'outside_admitted_source')
        == None
    )


def test_b02_c03643():
    assert (
        decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'assemble_words', 'persist_payload_invalid')
        == None
    )


def test_b02_c03644():
    assert (
        decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'assemble_words', 'retained_audio_invalid') == None
    )


def test_b02_c03645():
    assert (
        decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'assemble_words', 'staged_audio_invalid') == None
    )


def test_b02_c03646():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'assemble_words', 'unknown') == None


def test_b02_c03647():
    assert (
        decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'assemble_words', 'unsupported_language') == None
    )


def test_b02_c03648():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'assemble_words', 'vad_bounds') == None


def test_b02_c03649():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'assemble_words', 'vad_nonfinite') == None


def test_b02_c03650():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'assemble_words', 'vad_order') == None


def test_b02_c03651():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'assemble_words', 'word_clock') == None


def test_b02_c03652():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'assemble_words', 'word_sequence') == None


def test_b02_c03653():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'assemble_words', 'word_shape') == None


def test_b02_c03654():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'assemble_words', 'unclassified') == None


def test_b02_c03655():
    assert (
        decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'fetch_decode', 'decode_payload_invalid') == None
    )


def test_b02_c03656():
    assert (
        decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'fetch_decode', 'decoded_duration_mismatch')
        == None
    )


def test_b02_c03657():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'fetch_decode', 'empty_asr') == None


def test_b02_c03658():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'fetch_decode', 'no_owned_words') == None


def test_b02_c03659():
    assert (
        decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'fetch_decode', 'outside_admitted_source') == None
    )


def test_b02_c03660():
    assert (
        decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'fetch_decode', 'persist_payload_invalid') == None
    )


def test_b02_c03661():
    assert (
        decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'fetch_decode', 'retained_audio_invalid') == None
    )


def test_b02_c03662():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'fetch_decode', 'staged_audio_invalid') == None


def test_b02_c03663():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'fetch_decode', 'unknown') == None


def test_b02_c03664():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'fetch_decode', 'unsupported_language') == None


def test_b02_c03665():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'fetch_decode', 'vad_bounds') == None


def test_b02_c03666():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'fetch_decode', 'vad_nonfinite') == None


def test_b02_c03667():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'fetch_decode', 'vad_order') == None


def test_b02_c03668():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'fetch_decode', 'word_clock') == None


def test_b02_c03669():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'fetch_decode', 'word_sequence') == None


def test_b02_c03670():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'fetch_decode', 'word_shape') == None


def test_b02_c03671():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'fetch_decode', 'unclassified') == None


def test_b02_c03672():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'persist', 'decode_payload_invalid') == None


def test_b02_c03673():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'persist', 'decoded_duration_mismatch') == None


def test_b02_c03674():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'persist', 'empty_asr') == None


def test_b02_c03675():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'persist', 'no_owned_words') == None


def test_b02_c03676():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'persist', 'outside_admitted_source') == None


def test_b02_c03677():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'persist', 'persist_payload_invalid') == None


def test_b02_c03678():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'persist', 'retained_audio_invalid') == None


def test_b02_c03679():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'persist', 'staged_audio_invalid') == None


def test_b02_c03680():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'persist', 'unknown') == None


def test_b02_c03681():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'persist', 'unsupported_language') == None


def test_b02_c03682():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'persist', 'vad_bounds') == None


def test_b02_c03683():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'persist', 'vad_nonfinite') == None


def test_b02_c03684():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'persist', 'vad_order') == None


def test_b02_c03685():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'persist', 'word_clock') == None


def test_b02_c03686():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'persist', 'word_sequence') == None


def test_b02_c03687():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'persist', 'word_shape') == None


def test_b02_c03688():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'persist', 'unclassified') == None


def test_b02_c03689():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'vad_windows', 'decode_payload_invalid') == None


def test_b02_c03690():
    assert (
        decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'vad_windows', 'decoded_duration_mismatch') == None
    )


def test_b02_c03691():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'vad_windows', 'empty_asr') == None


def test_b02_c03692():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'vad_windows', 'no_owned_words') == None


def test_b02_c03693():
    assert (
        decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'vad_windows', 'outside_admitted_source') == None
    )


def test_b02_c03694():
    assert (
        decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'vad_windows', 'persist_payload_invalid') == None
    )


def test_b02_c03695():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'vad_windows', 'retained_audio_invalid') == None


def test_b02_c03696():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'vad_windows', 'staged_audio_invalid') == None


def test_b02_c03697():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'vad_windows', 'unknown') == None


def test_b02_c03698():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'vad_windows', 'unsupported_language') == None


def test_b02_c03699():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'vad_windows', 'vad_bounds') == None


def test_b02_c03700():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'vad_windows', 'vad_nonfinite') == None


def test_b02_c03701():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'vad_windows', 'vad_order') == None


def test_b02_c03702():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'vad_windows', 'word_clock') == None


def test_b02_c03703():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'vad_windows', 'word_sequence') == None


def test_b02_c03704():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'vad_windows', 'word_shape') == None


def test_b02_c03705():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'vad_windows', 'unclassified') == None


def test_b02_c03706():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'word_clocks', 'decode_payload_invalid') == None


def test_b02_c03707():
    assert (
        decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'word_clocks', 'decoded_duration_mismatch') == None
    )


def test_b02_c03708():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'word_clocks', 'empty_asr') == None


def test_b02_c03709():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'word_clocks', 'no_owned_words') == None


def test_b02_c03710():
    assert (
        decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'word_clocks', 'outside_admitted_source') == None
    )


def test_b02_c03711():
    assert (
        decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'word_clocks', 'persist_payload_invalid') == None
    )


def test_b02_c03712():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'word_clocks', 'retained_audio_invalid') == None


def test_b02_c03713():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'word_clocks', 'staged_audio_invalid') == None


def test_b02_c03714():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'word_clocks', 'unknown') == None


def test_b02_c03715():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'word_clocks', 'unsupported_language') == None


def test_b02_c03716():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'word_clocks', 'vad_bounds') == None


def test_b02_c03717():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'word_clocks', 'vad_nonfinite') == None


def test_b02_c03718():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'word_clocks', 'vad_order') == None


def test_b02_c03719():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'word_clocks', 'word_clock') == None


def test_b02_c03720():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'word_clocks', 'word_sequence') == None


def test_b02_c03721():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'word_clocks', 'word_shape') == None


def test_b02_c03722():
    assert decode_payload_failure_reason(_make('t_StagedAudioInvalid'), 'word_clocks', 'unclassified') == None
