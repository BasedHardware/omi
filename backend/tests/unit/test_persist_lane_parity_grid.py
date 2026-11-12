#!/usr/bin/env python3
"""Sibling-lane parity grid: the persist and publication contention arms agree.

Every cell pins that the persist boundary contention arm and the pump
publication lane classify the same fault shape identically and read the same
storm window out of the same damper stamp. A failing cell means the two
lanes drifted apart on the shared contention vocabulary.

Failure-Class: FC-persist-contention-exhaustion-discards-completed-gpu-results
"""

import socket
import types

import google.api_core.exceptions as gax
from database.firestore_transaction_retry import FirestoreContentionExhausted
from google.api_core.exceptions import Aborted, InvalidArgument
from utils.batch_pipeline.artifacts import StagedArtifactInvalid
from utils.batch_pipeline.audio import StagedAudioInvalid
from utils.batch_pipeline.source_audio import InvalidRetainedManifest, RetainedAudioInvalid
from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason
from diarizer import batch_pipeline as bp


def _chain(outer, cause):
    outer.__cause__ = cause
    return outer


def _expired():
    return InvalidArgument('400 ' + _EXPIRED_MARKER.capitalize() + '.')


def _bver(value):
    return BatchValidationError(ValidationReason(value))


def _carrier(stamp):
    ns = types.SimpleNamespace(args=('carrier',))
    ns.retry_after = stamp
    return ns


def _stamperr(stamp):
    err = RuntimeError('carrier')
    err.retry_after = stamp
    return err


_EXPIRED_MARKER = 'the referenced transaction has expired or is no longer valid'

from utils.batch_pipeline import pump as pump_mod

_SHAPE_BUILDERS = {
    'sdk_Aborted_bare_1': lambda: gax.Aborted('transport'),
    'sdk_Aborted_cause_aborted_1': lambda: _chain(gax.Aborted('transport'), Aborted('conflict')),
    'sdk_Aborted_cause_expired_1': lambda: _chain(gax.Aborted('transport'), _expired()),
    'sdk_Aborted_cause_timeout_1': lambda: _chain(gax.Aborted('transport'), TimeoutError('deadline')),
    'sdk_Aborted_cause_value_1': lambda: _chain(gax.Aborted('transport'), ValueError('custody')),
    'sdk_Aborted_bare_0': lambda: gax.Aborted(''),
    'sdk_Aborted_cause_aborted_0': lambda: _chain(gax.Aborted(''), Aborted('conflict')),
    'sdk_Aborted_cause_expired_0': lambda: _chain(gax.Aborted(''), _expired()),
    'sdk_Aborted_cause_timeout_0': lambda: _chain(gax.Aborted(''), TimeoutError('deadline')),
    'sdk_Aborted_cause_value_0': lambda: _chain(gax.Aborted(''), ValueError('custody')),
    'sdk_AlreadyExists_bare_1': lambda: gax.AlreadyExists('transport'),
    'sdk_AlreadyExists_cause_aborted_1': lambda: _chain(gax.AlreadyExists('transport'), Aborted('conflict')),
    'sdk_AlreadyExists_cause_expired_1': lambda: _chain(gax.AlreadyExists('transport'), _expired()),
    'sdk_AlreadyExists_cause_timeout_1': lambda: _chain(gax.AlreadyExists('transport'), TimeoutError('deadline')),
    'sdk_AlreadyExists_cause_value_1': lambda: _chain(gax.AlreadyExists('transport'), ValueError('custody')),
    'sdk_AlreadyExists_bare_0': lambda: gax.AlreadyExists(''),
    'sdk_AlreadyExists_cause_aborted_0': lambda: _chain(gax.AlreadyExists(''), Aborted('conflict')),
    'sdk_AlreadyExists_cause_expired_0': lambda: _chain(gax.AlreadyExists(''), _expired()),
    'sdk_AlreadyExists_cause_timeout_0': lambda: _chain(gax.AlreadyExists(''), TimeoutError('deadline')),
    'sdk_AlreadyExists_cause_value_0': lambda: _chain(gax.AlreadyExists(''), ValueError('custody')),
    'sdk_BadGateway_bare_1': lambda: gax.BadGateway('transport'),
    'sdk_BadGateway_cause_aborted_1': lambda: _chain(gax.BadGateway('transport'), Aborted('conflict')),
    'sdk_BadGateway_cause_expired_1': lambda: _chain(gax.BadGateway('transport'), _expired()),
    'sdk_BadGateway_cause_timeout_1': lambda: _chain(gax.BadGateway('transport'), TimeoutError('deadline')),
    'sdk_BadGateway_cause_value_1': lambda: _chain(gax.BadGateway('transport'), ValueError('custody')),
    'sdk_BadGateway_bare_0': lambda: gax.BadGateway(''),
    'sdk_BadGateway_cause_aborted_0': lambda: _chain(gax.BadGateway(''), Aborted('conflict')),
    'sdk_BadGateway_cause_expired_0': lambda: _chain(gax.BadGateway(''), _expired()),
    'sdk_BadGateway_cause_timeout_0': lambda: _chain(gax.BadGateway(''), TimeoutError('deadline')),
    'sdk_BadGateway_cause_value_0': lambda: _chain(gax.BadGateway(''), ValueError('custody')),
    'sdk_BadRequest_bare_1': lambda: gax.BadRequest('transport'),
    'sdk_BadRequest_cause_aborted_1': lambda: _chain(gax.BadRequest('transport'), Aborted('conflict')),
    'sdk_BadRequest_cause_expired_1': lambda: _chain(gax.BadRequest('transport'), _expired()),
    'sdk_BadRequest_cause_timeout_1': lambda: _chain(gax.BadRequest('transport'), TimeoutError('deadline')),
    'sdk_BadRequest_cause_value_1': lambda: _chain(gax.BadRequest('transport'), ValueError('custody')),
    'sdk_BadRequest_bare_0': lambda: gax.BadRequest(''),
    'sdk_BadRequest_cause_aborted_0': lambda: _chain(gax.BadRequest(''), Aborted('conflict')),
    'sdk_BadRequest_cause_expired_0': lambda: _chain(gax.BadRequest(''), _expired()),
    'sdk_BadRequest_cause_timeout_0': lambda: _chain(gax.BadRequest(''), TimeoutError('deadline')),
    'sdk_BadRequest_cause_value_0': lambda: _chain(gax.BadRequest(''), ValueError('custody')),
    'sdk_Cancelled_bare_1': lambda: gax.Cancelled('transport'),
    'sdk_Cancelled_cause_aborted_1': lambda: _chain(gax.Cancelled('transport'), Aborted('conflict')),
    'sdk_Cancelled_cause_expired_1': lambda: _chain(gax.Cancelled('transport'), _expired()),
    'sdk_Cancelled_cause_timeout_1': lambda: _chain(gax.Cancelled('transport'), TimeoutError('deadline')),
    'sdk_Cancelled_cause_value_1': lambda: _chain(gax.Cancelled('transport'), ValueError('custody')),
    'sdk_Cancelled_bare_0': lambda: gax.Cancelled(''),
    'sdk_Cancelled_cause_aborted_0': lambda: _chain(gax.Cancelled(''), Aborted('conflict')),
    'sdk_Cancelled_cause_expired_0': lambda: _chain(gax.Cancelled(''), _expired()),
    'sdk_Cancelled_cause_timeout_0': lambda: _chain(gax.Cancelled(''), TimeoutError('deadline')),
    'sdk_Cancelled_cause_value_0': lambda: _chain(gax.Cancelled(''), ValueError('custody')),
    'sdk_ClientError_bare_1': lambda: gax.ClientError('transport'),
    'sdk_ClientError_cause_aborted_1': lambda: _chain(gax.ClientError('transport'), Aborted('conflict')),
    'sdk_ClientError_cause_expired_1': lambda: _chain(gax.ClientError('transport'), _expired()),
    'sdk_ClientError_cause_timeout_1': lambda: _chain(gax.ClientError('transport'), TimeoutError('deadline')),
    'sdk_ClientError_cause_value_1': lambda: _chain(gax.ClientError('transport'), ValueError('custody')),
    'sdk_ClientError_bare_0': lambda: gax.ClientError(''),
    'sdk_ClientError_cause_aborted_0': lambda: _chain(gax.ClientError(''), Aborted('conflict')),
    'sdk_ClientError_cause_expired_0': lambda: _chain(gax.ClientError(''), _expired()),
    'sdk_ClientError_cause_timeout_0': lambda: _chain(gax.ClientError(''), TimeoutError('deadline')),
    'sdk_ClientError_cause_value_0': lambda: _chain(gax.ClientError(''), ValueError('custody')),
    'sdk_Conflict_bare_1': lambda: gax.Conflict('transport'),
    'sdk_Conflict_cause_aborted_1': lambda: _chain(gax.Conflict('transport'), Aborted('conflict')),
    'sdk_Conflict_cause_expired_1': lambda: _chain(gax.Conflict('transport'), _expired()),
    'sdk_Conflict_cause_timeout_1': lambda: _chain(gax.Conflict('transport'), TimeoutError('deadline')),
    'sdk_Conflict_cause_value_1': lambda: _chain(gax.Conflict('transport'), ValueError('custody')),
    'sdk_Conflict_bare_0': lambda: gax.Conflict(''),
    'sdk_Conflict_cause_aborted_0': lambda: _chain(gax.Conflict(''), Aborted('conflict')),
    'sdk_Conflict_cause_expired_0': lambda: _chain(gax.Conflict(''), _expired()),
    'sdk_Conflict_cause_timeout_0': lambda: _chain(gax.Conflict(''), TimeoutError('deadline')),
    'sdk_Conflict_cause_value_0': lambda: _chain(gax.Conflict(''), ValueError('custody')),
    'sdk_DataLoss_bare_1': lambda: gax.DataLoss('transport'),
    'sdk_DataLoss_cause_aborted_1': lambda: _chain(gax.DataLoss('transport'), Aborted('conflict')),
    'sdk_DataLoss_cause_expired_1': lambda: _chain(gax.DataLoss('transport'), _expired()),
    'sdk_DataLoss_cause_timeout_1': lambda: _chain(gax.DataLoss('transport'), TimeoutError('deadline')),
    'sdk_DataLoss_cause_value_1': lambda: _chain(gax.DataLoss('transport'), ValueError('custody')),
    'sdk_DataLoss_bare_0': lambda: gax.DataLoss(''),
    'sdk_DataLoss_cause_aborted_0': lambda: _chain(gax.DataLoss(''), Aborted('conflict')),
    'sdk_DataLoss_cause_expired_0': lambda: _chain(gax.DataLoss(''), _expired()),
    'sdk_DataLoss_cause_timeout_0': lambda: _chain(gax.DataLoss(''), TimeoutError('deadline')),
    'sdk_DataLoss_cause_value_0': lambda: _chain(gax.DataLoss(''), ValueError('custody')),
    'sdk_DeadlineExceeded_bare_1': lambda: gax.DeadlineExceeded('transport'),
    'sdk_DeadlineExceeded_cause_aborted_1': lambda: _chain(gax.DeadlineExceeded('transport'), Aborted('conflict')),
    'sdk_DeadlineExceeded_cause_expired_1': lambda: _chain(gax.DeadlineExceeded('transport'), _expired()),
    'sdk_DeadlineExceeded_cause_timeout_1': lambda: _chain(gax.DeadlineExceeded('transport'), TimeoutError('deadline')),
    'sdk_DeadlineExceeded_cause_value_1': lambda: _chain(gax.DeadlineExceeded('transport'), ValueError('custody')),
    'sdk_DeadlineExceeded_bare_0': lambda: gax.DeadlineExceeded(''),
    'sdk_DeadlineExceeded_cause_aborted_0': lambda: _chain(gax.DeadlineExceeded(''), Aborted('conflict')),
    'sdk_DeadlineExceeded_cause_expired_0': lambda: _chain(gax.DeadlineExceeded(''), _expired()),
    'sdk_DeadlineExceeded_cause_timeout_0': lambda: _chain(gax.DeadlineExceeded(''), TimeoutError('deadline')),
    'sdk_DeadlineExceeded_cause_value_0': lambda: _chain(gax.DeadlineExceeded(''), ValueError('custody')),
    'sdk_DuplicateCredentialArgs_bare_1': lambda: gax.DuplicateCredentialArgs('transport'),
    'sdk_DuplicateCredentialArgs_cause_aborted_1': lambda: _chain(
        gax.DuplicateCredentialArgs('transport'), Aborted('conflict')
    ),
    'sdk_DuplicateCredentialArgs_cause_expired_1': lambda: _chain(gax.DuplicateCredentialArgs('transport'), _expired()),
    'sdk_DuplicateCredentialArgs_cause_timeout_1': lambda: _chain(
        gax.DuplicateCredentialArgs('transport'), TimeoutError('deadline')
    ),
    'sdk_DuplicateCredentialArgs_cause_value_1': lambda: _chain(
        gax.DuplicateCredentialArgs('transport'), ValueError('custody')
    ),
    'sdk_DuplicateCredentialArgs_bare_0': lambda: gax.DuplicateCredentialArgs(''),
    'sdk_DuplicateCredentialArgs_cause_aborted_0': lambda: _chain(gax.DuplicateCredentialArgs(''), Aborted('conflict')),
    'sdk_DuplicateCredentialArgs_cause_expired_0': lambda: _chain(gax.DuplicateCredentialArgs(''), _expired()),
    'sdk_DuplicateCredentialArgs_cause_timeout_0': lambda: _chain(
        gax.DuplicateCredentialArgs(''), TimeoutError('deadline')
    ),
    'sdk_DuplicateCredentialArgs_cause_value_0': lambda: _chain(gax.DuplicateCredentialArgs(''), ValueError('custody')),
    'sdk_FailedPrecondition_bare_1': lambda: gax.FailedPrecondition('transport'),
    'sdk_FailedPrecondition_cause_aborted_1': lambda: _chain(gax.FailedPrecondition('transport'), Aborted('conflict')),
    'sdk_FailedPrecondition_cause_expired_1': lambda: _chain(gax.FailedPrecondition('transport'), _expired()),
    'sdk_FailedPrecondition_cause_timeout_1': lambda: _chain(
        gax.FailedPrecondition('transport'), TimeoutError('deadline')
    ),
    'sdk_FailedPrecondition_cause_value_1': lambda: _chain(gax.FailedPrecondition('transport'), ValueError('custody')),
    'sdk_FailedPrecondition_bare_0': lambda: gax.FailedPrecondition(''),
    'sdk_FailedPrecondition_cause_aborted_0': lambda: _chain(gax.FailedPrecondition(''), Aborted('conflict')),
    'sdk_FailedPrecondition_cause_expired_0': lambda: _chain(gax.FailedPrecondition(''), _expired()),
    'sdk_FailedPrecondition_cause_timeout_0': lambda: _chain(gax.FailedPrecondition(''), TimeoutError('deadline')),
    'sdk_FailedPrecondition_cause_value_0': lambda: _chain(gax.FailedPrecondition(''), ValueError('custody')),
    'sdk_Forbidden_bare_1': lambda: gax.Forbidden('transport'),
    'sdk_Forbidden_cause_aborted_1': lambda: _chain(gax.Forbidden('transport'), Aborted('conflict')),
    'sdk_Forbidden_cause_expired_1': lambda: _chain(gax.Forbidden('transport'), _expired()),
    'sdk_Forbidden_cause_timeout_1': lambda: _chain(gax.Forbidden('transport'), TimeoutError('deadline')),
    'sdk_Forbidden_cause_value_1': lambda: _chain(gax.Forbidden('transport'), ValueError('custody')),
    'sdk_Forbidden_bare_0': lambda: gax.Forbidden(''),
    'sdk_Forbidden_cause_aborted_0': lambda: _chain(gax.Forbidden(''), Aborted('conflict')),
    'sdk_Forbidden_cause_expired_0': lambda: _chain(gax.Forbidden(''), _expired()),
    'sdk_Forbidden_cause_timeout_0': lambda: _chain(gax.Forbidden(''), TimeoutError('deadline')),
    'sdk_Forbidden_cause_value_0': lambda: _chain(gax.Forbidden(''), ValueError('custody')),
    'sdk_GatewayTimeout_bare_1': lambda: gax.GatewayTimeout('transport'),
    'sdk_GatewayTimeout_cause_aborted_1': lambda: _chain(gax.GatewayTimeout('transport'), Aborted('conflict')),
    'sdk_GatewayTimeout_cause_expired_1': lambda: _chain(gax.GatewayTimeout('transport'), _expired()),
    'sdk_GatewayTimeout_cause_timeout_1': lambda: _chain(gax.GatewayTimeout('transport'), TimeoutError('deadline')),
    'sdk_GatewayTimeout_cause_value_1': lambda: _chain(gax.GatewayTimeout('transport'), ValueError('custody')),
    'sdk_GatewayTimeout_bare_0': lambda: gax.GatewayTimeout(''),
    'sdk_GatewayTimeout_cause_aborted_0': lambda: _chain(gax.GatewayTimeout(''), Aborted('conflict')),
    'sdk_GatewayTimeout_cause_expired_0': lambda: _chain(gax.GatewayTimeout(''), _expired()),
    'sdk_GatewayTimeout_cause_timeout_0': lambda: _chain(gax.GatewayTimeout(''), TimeoutError('deadline')),
    'sdk_GatewayTimeout_cause_value_0': lambda: _chain(gax.GatewayTimeout(''), ValueError('custody')),
    'sdk_GoogleAPICallError_bare_1': lambda: gax.GoogleAPICallError('transport'),
    'sdk_GoogleAPICallError_cause_aborted_1': lambda: _chain(gax.GoogleAPICallError('transport'), Aborted('conflict')),
    'sdk_GoogleAPICallError_cause_expired_1': lambda: _chain(gax.GoogleAPICallError('transport'), _expired()),
    'sdk_GoogleAPICallError_cause_timeout_1': lambda: _chain(
        gax.GoogleAPICallError('transport'), TimeoutError('deadline')
    ),
    'sdk_GoogleAPICallError_cause_value_1': lambda: _chain(gax.GoogleAPICallError('transport'), ValueError('custody')),
    'sdk_GoogleAPICallError_bare_0': lambda: gax.GoogleAPICallError(''),
    'sdk_GoogleAPICallError_cause_aborted_0': lambda: _chain(gax.GoogleAPICallError(''), Aborted('conflict')),
    'sdk_GoogleAPICallError_cause_expired_0': lambda: _chain(gax.GoogleAPICallError(''), _expired()),
    'sdk_GoogleAPICallError_cause_timeout_0': lambda: _chain(gax.GoogleAPICallError(''), TimeoutError('deadline')),
    'sdk_GoogleAPICallError_cause_value_0': lambda: _chain(gax.GoogleAPICallError(''), ValueError('custody')),
    'sdk_GoogleAPIError_bare_1': lambda: gax.GoogleAPIError('transport'),
    'sdk_GoogleAPIError_cause_aborted_1': lambda: _chain(gax.GoogleAPIError('transport'), Aborted('conflict')),
    'sdk_GoogleAPIError_cause_expired_1': lambda: _chain(gax.GoogleAPIError('transport'), _expired()),
    'sdk_GoogleAPIError_cause_timeout_1': lambda: _chain(gax.GoogleAPIError('transport'), TimeoutError('deadline')),
    'sdk_GoogleAPIError_cause_value_1': lambda: _chain(gax.GoogleAPIError('transport'), ValueError('custody')),
    'sdk_GoogleAPIError_bare_0': lambda: gax.GoogleAPIError(''),
    'sdk_GoogleAPIError_cause_aborted_0': lambda: _chain(gax.GoogleAPIError(''), Aborted('conflict')),
    'sdk_GoogleAPIError_cause_expired_0': lambda: _chain(gax.GoogleAPIError(''), _expired()),
    'sdk_GoogleAPIError_cause_timeout_0': lambda: _chain(gax.GoogleAPIError(''), TimeoutError('deadline')),
    'sdk_GoogleAPIError_cause_value_0': lambda: _chain(gax.GoogleAPIError(''), ValueError('custody')),
    'sdk_InternalServerError_bare_1': lambda: gax.InternalServerError('transport'),
    'sdk_InternalServerError_cause_aborted_1': lambda: _chain(
        gax.InternalServerError('transport'), Aborted('conflict')
    ),
    'sdk_InternalServerError_cause_expired_1': lambda: _chain(gax.InternalServerError('transport'), _expired()),
    'sdk_InternalServerError_cause_timeout_1': lambda: _chain(
        gax.InternalServerError('transport'), TimeoutError('deadline')
    ),
    'sdk_InternalServerError_cause_value_1': lambda: _chain(
        gax.InternalServerError('transport'), ValueError('custody')
    ),
    'sdk_InternalServerError_bare_0': lambda: gax.InternalServerError(''),
    'sdk_InternalServerError_cause_aborted_0': lambda: _chain(gax.InternalServerError(''), Aborted('conflict')),
    'sdk_InternalServerError_cause_expired_0': lambda: _chain(gax.InternalServerError(''), _expired()),
    'sdk_InternalServerError_cause_timeout_0': lambda: _chain(gax.InternalServerError(''), TimeoutError('deadline')),
    'sdk_InternalServerError_cause_value_0': lambda: _chain(gax.InternalServerError(''), ValueError('custody')),
    'sdk_InvalidArgument_bare_1': lambda: gax.InvalidArgument('transport'),
    'sdk_InvalidArgument_cause_aborted_1': lambda: _chain(gax.InvalidArgument('transport'), Aborted('conflict')),
    'sdk_InvalidArgument_cause_expired_1': lambda: _chain(gax.InvalidArgument('transport'), _expired()),
    'sdk_InvalidArgument_cause_timeout_1': lambda: _chain(gax.InvalidArgument('transport'), TimeoutError('deadline')),
    'sdk_InvalidArgument_cause_value_1': lambda: _chain(gax.InvalidArgument('transport'), ValueError('custody')),
    'sdk_InvalidArgument_bare_0': lambda: gax.InvalidArgument(''),
    'sdk_InvalidArgument_cause_aborted_0': lambda: _chain(gax.InvalidArgument(''), Aborted('conflict')),
    'sdk_InvalidArgument_cause_expired_0': lambda: _chain(gax.InvalidArgument(''), _expired()),
    'sdk_InvalidArgument_cause_timeout_0': lambda: _chain(gax.InvalidArgument(''), TimeoutError('deadline')),
    'sdk_InvalidArgument_cause_value_0': lambda: _chain(gax.InvalidArgument(''), ValueError('custody')),
    'sdk_LengthRequired_bare_1': lambda: gax.LengthRequired('transport'),
    'sdk_LengthRequired_cause_aborted_1': lambda: _chain(gax.LengthRequired('transport'), Aborted('conflict')),
    'sdk_LengthRequired_cause_expired_1': lambda: _chain(gax.LengthRequired('transport'), _expired()),
    'sdk_LengthRequired_cause_timeout_1': lambda: _chain(gax.LengthRequired('transport'), TimeoutError('deadline')),
    'sdk_LengthRequired_cause_value_1': lambda: _chain(gax.LengthRequired('transport'), ValueError('custody')),
    'sdk_LengthRequired_bare_0': lambda: gax.LengthRequired(''),
    'sdk_LengthRequired_cause_aborted_0': lambda: _chain(gax.LengthRequired(''), Aborted('conflict')),
    'sdk_LengthRequired_cause_expired_0': lambda: _chain(gax.LengthRequired(''), _expired()),
    'sdk_LengthRequired_cause_timeout_0': lambda: _chain(gax.LengthRequired(''), TimeoutError('deadline')),
    'sdk_LengthRequired_cause_value_0': lambda: _chain(gax.LengthRequired(''), ValueError('custody')),
    'sdk_MethodNotAllowed_bare_1': lambda: gax.MethodNotAllowed('transport'),
    'sdk_MethodNotAllowed_cause_aborted_1': lambda: _chain(gax.MethodNotAllowed('transport'), Aborted('conflict')),
    'sdk_MethodNotAllowed_cause_expired_1': lambda: _chain(gax.MethodNotAllowed('transport'), _expired()),
    'sdk_MethodNotAllowed_cause_timeout_1': lambda: _chain(gax.MethodNotAllowed('transport'), TimeoutError('deadline')),
    'sdk_MethodNotAllowed_cause_value_1': lambda: _chain(gax.MethodNotAllowed('transport'), ValueError('custody')),
    'sdk_MethodNotAllowed_bare_0': lambda: gax.MethodNotAllowed(''),
    'sdk_MethodNotAllowed_cause_aborted_0': lambda: _chain(gax.MethodNotAllowed(''), Aborted('conflict')),
    'sdk_MethodNotAllowed_cause_expired_0': lambda: _chain(gax.MethodNotAllowed(''), _expired()),
    'sdk_MethodNotAllowed_cause_timeout_0': lambda: _chain(gax.MethodNotAllowed(''), TimeoutError('deadline')),
    'sdk_MethodNotAllowed_cause_value_0': lambda: _chain(gax.MethodNotAllowed(''), ValueError('custody')),
    'sdk_MethodNotImplemented_bare_1': lambda: gax.MethodNotImplemented('transport'),
    'sdk_MethodNotImplemented_cause_aborted_1': lambda: _chain(
        gax.MethodNotImplemented('transport'), Aborted('conflict')
    ),
    'sdk_MethodNotImplemented_cause_expired_1': lambda: _chain(gax.MethodNotImplemented('transport'), _expired()),
    'sdk_MethodNotImplemented_cause_timeout_1': lambda: _chain(
        gax.MethodNotImplemented('transport'), TimeoutError('deadline')
    ),
    'sdk_MethodNotImplemented_cause_value_1': lambda: _chain(
        gax.MethodNotImplemented('transport'), ValueError('custody')
    ),
    'sdk_MethodNotImplemented_bare_0': lambda: gax.MethodNotImplemented(''),
    'sdk_MethodNotImplemented_cause_aborted_0': lambda: _chain(gax.MethodNotImplemented(''), Aborted('conflict')),
    'sdk_MethodNotImplemented_cause_expired_0': lambda: _chain(gax.MethodNotImplemented(''), _expired()),
    'sdk_MethodNotImplemented_cause_timeout_0': lambda: _chain(gax.MethodNotImplemented(''), TimeoutError('deadline')),
    'sdk_MethodNotImplemented_cause_value_0': lambda: _chain(gax.MethodNotImplemented(''), ValueError('custody')),
    'sdk_MovedPermanently_bare_1': lambda: gax.MovedPermanently('transport'),
    'sdk_MovedPermanently_cause_aborted_1': lambda: _chain(gax.MovedPermanently('transport'), Aborted('conflict')),
    'sdk_MovedPermanently_cause_expired_1': lambda: _chain(gax.MovedPermanently('transport'), _expired()),
    'sdk_MovedPermanently_cause_timeout_1': lambda: _chain(gax.MovedPermanently('transport'), TimeoutError('deadline')),
    'sdk_MovedPermanently_cause_value_1': lambda: _chain(gax.MovedPermanently('transport'), ValueError('custody')),
    'sdk_MovedPermanently_bare_0': lambda: gax.MovedPermanently(''),
    'sdk_MovedPermanently_cause_aborted_0': lambda: _chain(gax.MovedPermanently(''), Aborted('conflict')),
    'sdk_MovedPermanently_cause_expired_0': lambda: _chain(gax.MovedPermanently(''), _expired()),
    'sdk_MovedPermanently_cause_timeout_0': lambda: _chain(gax.MovedPermanently(''), TimeoutError('deadline')),
    'sdk_MovedPermanently_cause_value_0': lambda: _chain(gax.MovedPermanently(''), ValueError('custody')),
    'sdk_NotFound_bare_1': lambda: gax.NotFound('transport'),
    'sdk_NotFound_cause_aborted_1': lambda: _chain(gax.NotFound('transport'), Aborted('conflict')),
    'sdk_NotFound_cause_expired_1': lambda: _chain(gax.NotFound('transport'), _expired()),
    'sdk_NotFound_cause_timeout_1': lambda: _chain(gax.NotFound('transport'), TimeoutError('deadline')),
    'sdk_NotFound_cause_value_1': lambda: _chain(gax.NotFound('transport'), ValueError('custody')),
    'sdk_NotFound_bare_0': lambda: gax.NotFound(''),
    'sdk_NotFound_cause_aborted_0': lambda: _chain(gax.NotFound(''), Aborted('conflict')),
    'sdk_NotFound_cause_expired_0': lambda: _chain(gax.NotFound(''), _expired()),
    'sdk_NotFound_cause_timeout_0': lambda: _chain(gax.NotFound(''), TimeoutError('deadline')),
    'sdk_NotFound_cause_value_0': lambda: _chain(gax.NotFound(''), ValueError('custody')),
    'sdk_NotModified_bare_1': lambda: gax.NotModified('transport'),
    'sdk_NotModified_cause_aborted_1': lambda: _chain(gax.NotModified('transport'), Aborted('conflict')),
    'sdk_NotModified_cause_expired_1': lambda: _chain(gax.NotModified('transport'), _expired()),
    'sdk_NotModified_cause_timeout_1': lambda: _chain(gax.NotModified('transport'), TimeoutError('deadline')),
    'sdk_NotModified_cause_value_1': lambda: _chain(gax.NotModified('transport'), ValueError('custody')),
    'sdk_NotModified_bare_0': lambda: gax.NotModified(''),
    'sdk_NotModified_cause_aborted_0': lambda: _chain(gax.NotModified(''), Aborted('conflict')),
    'sdk_NotModified_cause_expired_0': lambda: _chain(gax.NotModified(''), _expired()),
    'sdk_NotModified_cause_timeout_0': lambda: _chain(gax.NotModified(''), TimeoutError('deadline')),
    'sdk_NotModified_cause_value_0': lambda: _chain(gax.NotModified(''), ValueError('custody')),
    'sdk_OutOfRange_bare_1': lambda: gax.OutOfRange('transport'),
    'sdk_OutOfRange_cause_aborted_1': lambda: _chain(gax.OutOfRange('transport'), Aborted('conflict')),
    'sdk_OutOfRange_cause_expired_1': lambda: _chain(gax.OutOfRange('transport'), _expired()),
    'sdk_OutOfRange_cause_timeout_1': lambda: _chain(gax.OutOfRange('transport'), TimeoutError('deadline')),
    'sdk_OutOfRange_cause_value_1': lambda: _chain(gax.OutOfRange('transport'), ValueError('custody')),
    'sdk_OutOfRange_bare_0': lambda: gax.OutOfRange(''),
    'sdk_OutOfRange_cause_aborted_0': lambda: _chain(gax.OutOfRange(''), Aborted('conflict')),
    'sdk_OutOfRange_cause_expired_0': lambda: _chain(gax.OutOfRange(''), _expired()),
    'sdk_OutOfRange_cause_timeout_0': lambda: _chain(gax.OutOfRange(''), TimeoutError('deadline')),
    'sdk_OutOfRange_cause_value_0': lambda: _chain(gax.OutOfRange(''), ValueError('custody')),
    'sdk_PermissionDenied_bare_1': lambda: gax.PermissionDenied('transport'),
    'sdk_PermissionDenied_cause_aborted_1': lambda: _chain(gax.PermissionDenied('transport'), Aborted('conflict')),
    'sdk_PermissionDenied_cause_expired_1': lambda: _chain(gax.PermissionDenied('transport'), _expired()),
    'sdk_PermissionDenied_cause_timeout_1': lambda: _chain(gax.PermissionDenied('transport'), TimeoutError('deadline')),
    'sdk_PermissionDenied_cause_value_1': lambda: _chain(gax.PermissionDenied('transport'), ValueError('custody')),
    'sdk_PermissionDenied_bare_0': lambda: gax.PermissionDenied(''),
    'sdk_PermissionDenied_cause_aborted_0': lambda: _chain(gax.PermissionDenied(''), Aborted('conflict')),
    'sdk_PermissionDenied_cause_expired_0': lambda: _chain(gax.PermissionDenied(''), _expired()),
    'sdk_PermissionDenied_cause_timeout_0': lambda: _chain(gax.PermissionDenied(''), TimeoutError('deadline')),
    'sdk_PermissionDenied_cause_value_0': lambda: _chain(gax.PermissionDenied(''), ValueError('custody')),
    'sdk_PreconditionFailed_bare_1': lambda: gax.PreconditionFailed('transport'),
    'sdk_PreconditionFailed_cause_aborted_1': lambda: _chain(gax.PreconditionFailed('transport'), Aborted('conflict')),
    'sdk_PreconditionFailed_cause_expired_1': lambda: _chain(gax.PreconditionFailed('transport'), _expired()),
    'sdk_PreconditionFailed_cause_timeout_1': lambda: _chain(
        gax.PreconditionFailed('transport'), TimeoutError('deadline')
    ),
    'sdk_PreconditionFailed_cause_value_1': lambda: _chain(gax.PreconditionFailed('transport'), ValueError('custody')),
    'sdk_PreconditionFailed_bare_0': lambda: gax.PreconditionFailed(''),
    'sdk_PreconditionFailed_cause_aborted_0': lambda: _chain(gax.PreconditionFailed(''), Aborted('conflict')),
    'sdk_PreconditionFailed_cause_expired_0': lambda: _chain(gax.PreconditionFailed(''), _expired()),
    'sdk_PreconditionFailed_cause_timeout_0': lambda: _chain(gax.PreconditionFailed(''), TimeoutError('deadline')),
    'sdk_PreconditionFailed_cause_value_0': lambda: _chain(gax.PreconditionFailed(''), ValueError('custody')),
    'sdk_Redirection_bare_1': lambda: gax.Redirection('transport'),
    'sdk_Redirection_cause_aborted_1': lambda: _chain(gax.Redirection('transport'), Aborted('conflict')),
    'sdk_Redirection_cause_expired_1': lambda: _chain(gax.Redirection('transport'), _expired()),
    'sdk_Redirection_cause_timeout_1': lambda: _chain(gax.Redirection('transport'), TimeoutError('deadline')),
    'sdk_Redirection_cause_value_1': lambda: _chain(gax.Redirection('transport'), ValueError('custody')),
    'sdk_Redirection_bare_0': lambda: gax.Redirection(''),
    'sdk_Redirection_cause_aborted_0': lambda: _chain(gax.Redirection(''), Aborted('conflict')),
    'sdk_Redirection_cause_expired_0': lambda: _chain(gax.Redirection(''), _expired()),
    'sdk_Redirection_cause_timeout_0': lambda: _chain(gax.Redirection(''), TimeoutError('deadline')),
    'sdk_Redirection_cause_value_0': lambda: _chain(gax.Redirection(''), ValueError('custody')),
    'sdk_RequestRangeNotSatisfiable_bare_1': lambda: gax.RequestRangeNotSatisfiable('transport'),
    'sdk_RequestRangeNotSatisfiable_cause_aborted_1': lambda: _chain(
        gax.RequestRangeNotSatisfiable('transport'), Aborted('conflict')
    ),
    'sdk_RequestRangeNotSatisfiable_cause_expired_1': lambda: _chain(
        gax.RequestRangeNotSatisfiable('transport'), _expired()
    ),
    'sdk_RequestRangeNotSatisfiable_cause_timeout_1': lambda: _chain(
        gax.RequestRangeNotSatisfiable('transport'), TimeoutError('deadline')
    ),
    'sdk_RequestRangeNotSatisfiable_cause_value_1': lambda: _chain(
        gax.RequestRangeNotSatisfiable('transport'), ValueError('custody')
    ),
    'sdk_RequestRangeNotSatisfiable_bare_0': lambda: gax.RequestRangeNotSatisfiable(''),
    'sdk_RequestRangeNotSatisfiable_cause_aborted_0': lambda: _chain(
        gax.RequestRangeNotSatisfiable(''), Aborted('conflict')
    ),
    'sdk_RequestRangeNotSatisfiable_cause_expired_0': lambda: _chain(gax.RequestRangeNotSatisfiable(''), _expired()),
    'sdk_RequestRangeNotSatisfiable_cause_timeout_0': lambda: _chain(
        gax.RequestRangeNotSatisfiable(''), TimeoutError('deadline')
    ),
    'sdk_RequestRangeNotSatisfiable_cause_value_0': lambda: _chain(
        gax.RequestRangeNotSatisfiable(''), ValueError('custody')
    ),
    'sdk_ResourceExhausted_bare_1': lambda: gax.ResourceExhausted('transport'),
    'sdk_ResourceExhausted_cause_aborted_1': lambda: _chain(gax.ResourceExhausted('transport'), Aborted('conflict')),
    'sdk_ResourceExhausted_cause_expired_1': lambda: _chain(gax.ResourceExhausted('transport'), _expired()),
    'sdk_ResourceExhausted_cause_timeout_1': lambda: _chain(
        gax.ResourceExhausted('transport'), TimeoutError('deadline')
    ),
    'sdk_ResourceExhausted_cause_value_1': lambda: _chain(gax.ResourceExhausted('transport'), ValueError('custody')),
    'sdk_ResourceExhausted_bare_0': lambda: gax.ResourceExhausted(''),
    'sdk_ResourceExhausted_cause_aborted_0': lambda: _chain(gax.ResourceExhausted(''), Aborted('conflict')),
    'sdk_ResourceExhausted_cause_expired_0': lambda: _chain(gax.ResourceExhausted(''), _expired()),
    'sdk_ResourceExhausted_cause_timeout_0': lambda: _chain(gax.ResourceExhausted(''), TimeoutError('deadline')),
    'sdk_ResourceExhausted_cause_value_0': lambda: _chain(gax.ResourceExhausted(''), ValueError('custody')),
    'sdk_ResumeIncomplete_bare_1': lambda: gax.ResumeIncomplete('transport'),
    'sdk_ResumeIncomplete_cause_aborted_1': lambda: _chain(gax.ResumeIncomplete('transport'), Aborted('conflict')),
    'sdk_ResumeIncomplete_cause_expired_1': lambda: _chain(gax.ResumeIncomplete('transport'), _expired()),
    'sdk_ResumeIncomplete_cause_timeout_1': lambda: _chain(gax.ResumeIncomplete('transport'), TimeoutError('deadline')),
    'sdk_ResumeIncomplete_cause_value_1': lambda: _chain(gax.ResumeIncomplete('transport'), ValueError('custody')),
    'sdk_ResumeIncomplete_bare_0': lambda: gax.ResumeIncomplete(''),
    'sdk_ResumeIncomplete_cause_aborted_0': lambda: _chain(gax.ResumeIncomplete(''), Aborted('conflict')),
    'sdk_ResumeIncomplete_cause_expired_0': lambda: _chain(gax.ResumeIncomplete(''), _expired()),
    'sdk_ResumeIncomplete_cause_timeout_0': lambda: _chain(gax.ResumeIncomplete(''), TimeoutError('deadline')),
    'sdk_ResumeIncomplete_cause_value_0': lambda: _chain(gax.ResumeIncomplete(''), ValueError('custody')),
    'sdk_ServerError_bare_1': lambda: gax.ServerError('transport'),
    'sdk_ServerError_cause_aborted_1': lambda: _chain(gax.ServerError('transport'), Aborted('conflict')),
    'sdk_ServerError_cause_expired_1': lambda: _chain(gax.ServerError('transport'), _expired()),
    'sdk_ServerError_cause_timeout_1': lambda: _chain(gax.ServerError('transport'), TimeoutError('deadline')),
    'sdk_ServerError_cause_value_1': lambda: _chain(gax.ServerError('transport'), ValueError('custody')),
    'sdk_ServerError_bare_0': lambda: gax.ServerError(''),
    'sdk_ServerError_cause_aborted_0': lambda: _chain(gax.ServerError(''), Aborted('conflict')),
    'sdk_ServerError_cause_expired_0': lambda: _chain(gax.ServerError(''), _expired()),
    'sdk_ServerError_cause_timeout_0': lambda: _chain(gax.ServerError(''), TimeoutError('deadline')),
    'sdk_ServerError_cause_value_0': lambda: _chain(gax.ServerError(''), ValueError('custody')),
    'sdk_ServiceUnavailable_bare_1': lambda: gax.ServiceUnavailable('transport'),
    'sdk_ServiceUnavailable_cause_aborted_1': lambda: _chain(gax.ServiceUnavailable('transport'), Aborted('conflict')),
    'sdk_ServiceUnavailable_cause_expired_1': lambda: _chain(gax.ServiceUnavailable('transport'), _expired()),
    'sdk_ServiceUnavailable_cause_timeout_1': lambda: _chain(
        gax.ServiceUnavailable('transport'), TimeoutError('deadline')
    ),
    'sdk_ServiceUnavailable_cause_value_1': lambda: _chain(gax.ServiceUnavailable('transport'), ValueError('custody')),
    'sdk_ServiceUnavailable_bare_0': lambda: gax.ServiceUnavailable(''),
    'sdk_ServiceUnavailable_cause_aborted_0': lambda: _chain(gax.ServiceUnavailable(''), Aborted('conflict')),
    'sdk_ServiceUnavailable_cause_expired_0': lambda: _chain(gax.ServiceUnavailable(''), _expired()),
    'sdk_ServiceUnavailable_cause_timeout_0': lambda: _chain(gax.ServiceUnavailable(''), TimeoutError('deadline')),
    'sdk_ServiceUnavailable_cause_value_0': lambda: _chain(gax.ServiceUnavailable(''), ValueError('custody')),
    'sdk_TemporaryRedirect_bare_1': lambda: gax.TemporaryRedirect('transport'),
    'sdk_TemporaryRedirect_cause_aborted_1': lambda: _chain(gax.TemporaryRedirect('transport'), Aborted('conflict')),
    'sdk_TemporaryRedirect_cause_expired_1': lambda: _chain(gax.TemporaryRedirect('transport'), _expired()),
    'sdk_TemporaryRedirect_cause_timeout_1': lambda: _chain(
        gax.TemporaryRedirect('transport'), TimeoutError('deadline')
    ),
    'sdk_TemporaryRedirect_cause_value_1': lambda: _chain(gax.TemporaryRedirect('transport'), ValueError('custody')),
    'sdk_TemporaryRedirect_bare_0': lambda: gax.TemporaryRedirect(''),
    'sdk_TemporaryRedirect_cause_aborted_0': lambda: _chain(gax.TemporaryRedirect(''), Aborted('conflict')),
    'sdk_TemporaryRedirect_cause_expired_0': lambda: _chain(gax.TemporaryRedirect(''), _expired()),
    'sdk_TemporaryRedirect_cause_timeout_0': lambda: _chain(gax.TemporaryRedirect(''), TimeoutError('deadline')),
    'sdk_TemporaryRedirect_cause_value_0': lambda: _chain(gax.TemporaryRedirect(''), ValueError('custody')),
    'sdk_TooManyRequests_bare_1': lambda: gax.TooManyRequests('transport'),
    'sdk_TooManyRequests_cause_aborted_1': lambda: _chain(gax.TooManyRequests('transport'), Aborted('conflict')),
    'sdk_TooManyRequests_cause_expired_1': lambda: _chain(gax.TooManyRequests('transport'), _expired()),
    'sdk_TooManyRequests_cause_timeout_1': lambda: _chain(gax.TooManyRequests('transport'), TimeoutError('deadline')),
    'sdk_TooManyRequests_cause_value_1': lambda: _chain(gax.TooManyRequests('transport'), ValueError('custody')),
    'sdk_TooManyRequests_bare_0': lambda: gax.TooManyRequests(''),
    'sdk_TooManyRequests_cause_aborted_0': lambda: _chain(gax.TooManyRequests(''), Aborted('conflict')),
    'sdk_TooManyRequests_cause_expired_0': lambda: _chain(gax.TooManyRequests(''), _expired()),
    'sdk_TooManyRequests_cause_timeout_0': lambda: _chain(gax.TooManyRequests(''), TimeoutError('deadline')),
    'sdk_TooManyRequests_cause_value_0': lambda: _chain(gax.TooManyRequests(''), ValueError('custody')),
    'sdk_Unauthenticated_bare_1': lambda: gax.Unauthenticated('transport'),
    'sdk_Unauthenticated_cause_aborted_1': lambda: _chain(gax.Unauthenticated('transport'), Aborted('conflict')),
    'sdk_Unauthenticated_cause_expired_1': lambda: _chain(gax.Unauthenticated('transport'), _expired()),
    'sdk_Unauthenticated_cause_timeout_1': lambda: _chain(gax.Unauthenticated('transport'), TimeoutError('deadline')),
    'sdk_Unauthenticated_cause_value_1': lambda: _chain(gax.Unauthenticated('transport'), ValueError('custody')),
    'sdk_Unauthenticated_bare_0': lambda: gax.Unauthenticated(''),
    'sdk_Unauthenticated_cause_aborted_0': lambda: _chain(gax.Unauthenticated(''), Aborted('conflict')),
    'sdk_Unauthenticated_cause_expired_0': lambda: _chain(gax.Unauthenticated(''), _expired()),
    'sdk_Unauthenticated_cause_timeout_0': lambda: _chain(gax.Unauthenticated(''), TimeoutError('deadline')),
    'sdk_Unauthenticated_cause_value_0': lambda: _chain(gax.Unauthenticated(''), ValueError('custody')),
    'sdk_Unauthorized_bare_1': lambda: gax.Unauthorized('transport'),
    'sdk_Unauthorized_cause_aborted_1': lambda: _chain(gax.Unauthorized('transport'), Aborted('conflict')),
    'sdk_Unauthorized_cause_expired_1': lambda: _chain(gax.Unauthorized('transport'), _expired()),
    'sdk_Unauthorized_cause_timeout_1': lambda: _chain(gax.Unauthorized('transport'), TimeoutError('deadline')),
    'sdk_Unauthorized_cause_value_1': lambda: _chain(gax.Unauthorized('transport'), ValueError('custody')),
    'sdk_Unauthorized_bare_0': lambda: gax.Unauthorized(''),
    'sdk_Unauthorized_cause_aborted_0': lambda: _chain(gax.Unauthorized(''), Aborted('conflict')),
    'sdk_Unauthorized_cause_expired_0': lambda: _chain(gax.Unauthorized(''), _expired()),
    'sdk_Unauthorized_cause_timeout_0': lambda: _chain(gax.Unauthorized(''), TimeoutError('deadline')),
    'sdk_Unauthorized_cause_value_0': lambda: _chain(gax.Unauthorized(''), ValueError('custody')),
    'sdk_Unknown_bare_1': lambda: gax.Unknown('transport'),
    'sdk_Unknown_cause_aborted_1': lambda: _chain(gax.Unknown('transport'), Aborted('conflict')),
    'sdk_Unknown_cause_expired_1': lambda: _chain(gax.Unknown('transport'), _expired()),
    'sdk_Unknown_cause_timeout_1': lambda: _chain(gax.Unknown('transport'), TimeoutError('deadline')),
    'sdk_Unknown_cause_value_1': lambda: _chain(gax.Unknown('transport'), ValueError('custody')),
    'sdk_Unknown_bare_0': lambda: gax.Unknown(''),
    'sdk_Unknown_cause_aborted_0': lambda: _chain(gax.Unknown(''), Aborted('conflict')),
    'sdk_Unknown_cause_expired_0': lambda: _chain(gax.Unknown(''), _expired()),
    'sdk_Unknown_cause_timeout_0': lambda: _chain(gax.Unknown(''), TimeoutError('deadline')),
    'sdk_Unknown_cause_value_0': lambda: _chain(gax.Unknown(''), ValueError('custody')),
    'custody_staged_audio': lambda: StagedAudioInvalid('pinned bytes'),
    'custody_staged_audio_cause_aborted': lambda: _chain(StagedAudioInvalid('pinned bytes'), Aborted('conflict')),
    'custody_staged_artifact': lambda: StagedArtifactInvalid('pinned bytes'),
    'custody_staged_artifact_cause_aborted': lambda: _chain(StagedArtifactInvalid('pinned bytes'), Aborted('conflict')),
    'custody_retained_audio': lambda: RetainedAudioInvalid('pinned bytes'),
    'custody_retained_audio_cause_aborted': lambda: _chain(RetainedAudioInvalid('pinned bytes'), Aborted('conflict')),
    'custody_retained_manifest': lambda: InvalidRetainedManifest('pinned bytes'),
    'custody_retained_manifest_cause_aborted': lambda: _chain(
        InvalidRetainedManifest('pinned bytes'), Aborted('conflict')
    ),
    'custody_decoded_mismatch': lambda: bp.DecodedDurationMismatch('mismatch'),
    'custody_decoded_mismatch_cause_aborted': lambda: _chain(
        bp.DecodedDurationMismatch('mismatch'), Aborted('conflict')
    ),
    'custody_permission': lambda: PermissionError('policy'),
    'custody_permission_cause_aborted': lambda: _chain(PermissionError('policy'), Aborted('conflict')),
    'custody_os_error': lambda: OSError('disk'),
    'custody_os_error_cause_aborted': lambda: _chain(OSError('disk'), Aborted('conflict')),
    'custody_runtime': lambda: RuntimeError('worker'),
    'custody_runtime_cause_aborted': lambda: _chain(RuntimeError('worker'), Aborted('conflict')),
    'custody_value_error': lambda: ValueError('identity'),
    'custody_value_error_cause_aborted': lambda: _chain(ValueError('identity'), Aborted('conflict')),
    'custody_key_error': lambda: KeyError('k'),
    'custody_key_error_cause_aborted': lambda: _chain(KeyError('k'), Aborted('conflict')),
    'custody_type_error': lambda: TypeError('t'),
    'custody_type_error_cause_aborted': lambda: _chain(TypeError('t'), Aborted('conflict')),
    'custody_index_error': lambda: IndexError('i'),
    'custody_index_error_cause_aborted': lambda: _chain(IndexError('i'), Aborted('conflict')),
    'custody_zero_div': lambda: ZeroDivisionError('z'),
    'custody_zero_div_cause_aborted': lambda: _chain(ZeroDivisionError('z'), Aborted('conflict')),
    'custody_arith': lambda: ArithmeticError('a'),
    'custody_arith_cause_aborted': lambda: _chain(ArithmeticError('a'), Aborted('conflict')),
    'custody_lookup': lambda: LookupError('l'),
    'custody_lookup_cause_aborted': lambda: _chain(LookupError('l'), Aborted('conflict')),
    'custody_notimpl': lambda: NotImplementedError('n'),
    'custody_notimpl_cause_aborted': lambda: _chain(NotImplementedError('n'), Aborted('conflict')),
    'custody_recursion': lambda: RecursionError('r'),
    'custody_recursion_cause_aborted': lambda: _chain(RecursionError('r'), Aborted('conflict')),
    'custody_eof': lambda: EOFError('e'),
    'custody_eof_cause_aborted': lambda: _chain(EOFError('e'), Aborted('conflict')),
    'custody_batch_validation_unsupported_language': lambda: _bver('unsupported_language'),
    'custody_batch_validation_unsupported_language_cause_aborted': lambda: _chain(
        _bver('unsupported_language'), Aborted('conflict')
    ),
    'custody_batch_validation_word_shape': lambda: _bver('word_shape'),
    'custody_batch_validation_word_shape_cause_aborted': lambda: _chain(_bver('word_shape'), Aborted('conflict')),
    'custody_batch_validation_word_clock': lambda: _bver('word_clock'),
    'custody_batch_validation_word_clock_cause_aborted': lambda: _chain(_bver('word_clock'), Aborted('conflict')),
    'custody_batch_validation_word_sequence': lambda: _bver('word_sequence'),
    'custody_batch_validation_word_sequence_cause_aborted': lambda: _chain(_bver('word_sequence'), Aborted('conflict')),
    'custody_batch_validation_vad_nonfinite': lambda: _bver('vad_nonfinite'),
    'custody_batch_validation_vad_nonfinite_cause_aborted': lambda: _chain(_bver('vad_nonfinite'), Aborted('conflict')),
    'custody_batch_validation_vad_order': lambda: _bver('vad_order'),
    'custody_batch_validation_vad_order_cause_aborted': lambda: _chain(_bver('vad_order'), Aborted('conflict')),
    'custody_batch_validation_vad_bounds': lambda: _bver('vad_bounds'),
    'custody_batch_validation_vad_bounds_cause_aborted': lambda: _chain(_bver('vad_bounds'), Aborted('conflict')),
    'custody_batch_validation_empty_asr': lambda: _bver('empty_asr'),
    'custody_batch_validation_empty_asr_cause_aborted': lambda: _chain(_bver('empty_asr'), Aborted('conflict')),
    'custody_batch_validation_no_owned_words': lambda: _bver('no_owned_words'),
    'custody_batch_validation_no_owned_words_cause_aborted': lambda: _chain(
        _bver('no_owned_words'), Aborted('conflict')
    ),
    'timeout_family_6456': lambda: TimeoutError('deadline'),
    'timeout_family_9792': lambda: socket.timeout('socket'),
    'timeout_family_400': lambda: TimeoutError(),
    'wrapper_attempts_exhausted_0_0': lambda: FirestoreContentionExhausted(
        'chain', reason='attempts_exhausted', retry_after=0.0
    ),
    'wrapper_attempts_exhausted_0_1': lambda: FirestoreContentionExhausted(
        'chain', reason='attempts_exhausted', retry_after=0.1
    ),
    'wrapper_attempts_exhausted_0_25': lambda: FirestoreContentionExhausted(
        'chain', reason='attempts_exhausted', retry_after=0.25
    ),
    'wrapper_attempts_exhausted_0_5': lambda: FirestoreContentionExhausted(
        'chain', reason='attempts_exhausted', retry_after=0.5
    ),
    'wrapper_attempts_exhausted_1_0': lambda: FirestoreContentionExhausted(
        'chain', reason='attempts_exhausted', retry_after=1.0
    ),
    'wrapper_attempts_exhausted_1_5': lambda: FirestoreContentionExhausted(
        'chain', reason='attempts_exhausted', retry_after=1.5
    ),
    'wrapper_attempts_exhausted_2_0': lambda: FirestoreContentionExhausted(
        'chain', reason='attempts_exhausted', retry_after=2.0
    ),
    'wrapper_attempts_exhausted_2_5': lambda: FirestoreContentionExhausted(
        'chain', reason='attempts_exhausted', retry_after=2.5
    ),
    'wrapper_attempts_exhausted_3_0': lambda: FirestoreContentionExhausted(
        'chain', reason='attempts_exhausted', retry_after=3.0
    ),
    'wrapper_attempts_exhausted_3_9': lambda: FirestoreContentionExhausted(
        'chain', reason='attempts_exhausted', retry_after=3.9
    ),
    'wrapper_attempts_exhausted_4_0': lambda: FirestoreContentionExhausted(
        'chain', reason='attempts_exhausted', retry_after=4.0
    ),
    'wrapper_attempts_exhausted_4_1': lambda: FirestoreContentionExhausted(
        'chain', reason='attempts_exhausted', retry_after=4.1
    ),
    'wrapper_attempts_exhausted_8_0': lambda: FirestoreContentionExhausted(
        'chain', reason='attempts_exhausted', retry_after=8.0
    ),
    'wrapper_attempts_exhausted_50_0': lambda: FirestoreContentionExhausted(
        'chain', reason='attempts_exhausted', retry_after=50.0
    ),
    'wrapper_attempts_exhausted_1000000000_0': lambda: FirestoreContentionExhausted(
        'chain', reason='attempts_exhausted', retry_after=1000000000.0
    ),
    'wrapper_deadline_exhausted_0_0': lambda: FirestoreContentionExhausted(
        'chain', reason='deadline_exhausted', retry_after=0.0
    ),
    'wrapper_deadline_exhausted_0_1': lambda: FirestoreContentionExhausted(
        'chain', reason='deadline_exhausted', retry_after=0.1
    ),
    'wrapper_deadline_exhausted_0_25': lambda: FirestoreContentionExhausted(
        'chain', reason='deadline_exhausted', retry_after=0.25
    ),
    'wrapper_deadline_exhausted_0_5': lambda: FirestoreContentionExhausted(
        'chain', reason='deadline_exhausted', retry_after=0.5
    ),
    'wrapper_deadline_exhausted_1_0': lambda: FirestoreContentionExhausted(
        'chain', reason='deadline_exhausted', retry_after=1.0
    ),
    'wrapper_deadline_exhausted_1_5': lambda: FirestoreContentionExhausted(
        'chain', reason='deadline_exhausted', retry_after=1.5
    ),
    'wrapper_deadline_exhausted_2_0': lambda: FirestoreContentionExhausted(
        'chain', reason='deadline_exhausted', retry_after=2.0
    ),
    'wrapper_deadline_exhausted_2_5': lambda: FirestoreContentionExhausted(
        'chain', reason='deadline_exhausted', retry_after=2.5
    ),
    'wrapper_deadline_exhausted_3_0': lambda: FirestoreContentionExhausted(
        'chain', reason='deadline_exhausted', retry_after=3.0
    ),
    'wrapper_deadline_exhausted_3_9': lambda: FirestoreContentionExhausted(
        'chain', reason='deadline_exhausted', retry_after=3.9
    ),
    'wrapper_deadline_exhausted_4_0': lambda: FirestoreContentionExhausted(
        'chain', reason='deadline_exhausted', retry_after=4.0
    ),
    'wrapper_deadline_exhausted_4_1': lambda: FirestoreContentionExhausted(
        'chain', reason='deadline_exhausted', retry_after=4.1
    ),
    'wrapper_deadline_exhausted_8_0': lambda: FirestoreContentionExhausted(
        'chain', reason='deadline_exhausted', retry_after=8.0
    ),
    'wrapper_deadline_exhausted_50_0': lambda: FirestoreContentionExhausted(
        'chain', reason='deadline_exhausted', retry_after=50.0
    ),
    'wrapper_deadline_exhausted_1000000000_0': lambda: FirestoreContentionExhausted(
        'chain', reason='deadline_exhausted', retry_after=1000000000.0
    ),
    'carrier_ns_0': lambda: _carrier('9'),
    'carrier_err_0': lambda: _stamperr('9'),
    'carrier_ns_1': lambda: _carrier(b'9'),
    'carrier_err_1': lambda: _stamperr(b'9'),
    'carrier_ns_2': lambda: _carrier(None),
    'carrier_err_2': lambda: _stamperr(None),
    'carrier_ns_3': lambda: _carrier(True),
    'carrier_err_3': lambda: _stamperr(True),
    'carrier_ns_4': lambda: _carrier(False),
    'carrier_err_4': lambda: _stamperr(False),
    'carrier_ns_5': lambda: _carrier(float('nan')),
    'carrier_err_5': lambda: _stamperr(float('nan')),
    'carrier_ns_6': lambda: _carrier(float('inf')),
    'carrier_err_6': lambda: _stamperr(float('inf')),
    'carrier_ns_7': lambda: _carrier(float('-inf')),
    'carrier_err_7': lambda: _stamperr(float('-inf')),
    'carrier_ns_8': lambda: _carrier(-1.0),
    'carrier_err_8': lambda: _stamperr(-1.0),
    'carrier_ns_9': lambda: _carrier(0),
    'carrier_err_9': lambda: _stamperr(0),
    'carrier_ns_10': lambda: _carrier(0.0),
    'carrier_err_10': lambda: _stamperr(0.0),
    'carrier_ns_11': lambda: _carrier(1),
    'carrier_err_11': lambda: _stamperr(1),
    'carrier_ns_12': lambda: _carrier(3.9),
    'carrier_err_12': lambda: _stamperr(3.9),
    'carrier_ns_13': lambda: _carrier(4.0),
    'carrier_err_13': lambda: _stamperr(4.0),
    'carrier_ns_14': lambda: _carrier(4.5),
    'carrier_err_14': lambda: _stamperr(4.5),
    'carrier_ns_15': lambda: _carrier(100.0),
    'carrier_err_15': lambda: _stamperr(100.0),
    'carrier_ns_16': lambda: _carrier(1e308),
    'carrier_err_16': lambda: _stamperr(1e308),
    'carrier_ns_17': lambda: _carrier((1.0,)),
    'carrier_err_17': lambda: _stamperr((1.0,)),
    'carrier_ns_18': lambda: _carrier([1.0]),
    'carrier_err_18': lambda: _stamperr([1.0]),
    'carrier_ns_19': lambda: _carrier({'s': 1.0}),
    'carrier_err_19': lambda: _stamperr({'s': 1.0}),
    'carrier_ns_20': lambda: _carrier((1 + 1j)),
    'carrier_err_20': lambda: _stamperr((1 + 1j)),
    'hostile_0': lambda: None,
    'hostile_1': lambda: 0,
    'hostile_2': lambda: 7,
    'hostile_3': lambda: 'msg',
    'hostile_4': lambda: b'msg',
    'hostile_5': lambda: (),
    'hostile_6': lambda: [],
    'hostile_7': lambda: {},
    'hostile_8': lambda: set(),
    'hostile_9': lambda: object(),
    'hostile_10': lambda: 2.5,
}


def test_pump_admission_parity_00000():
    # sdk_Aborted_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_bare_1']()) is True


def test_pump_storm_parity_00000():
    # sdk_Aborted_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Aborted_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Aborted_bare_1']())


def test_pump_admission_parity_00001():
    # sdk_Aborted_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_cause_aborted_1']()) is True


def test_pump_storm_parity_00001():
    # sdk_Aborted_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Aborted_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Aborted_cause_aborted_1']())


def test_pump_admission_parity_00002():
    # sdk_Aborted_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_cause_expired_1']()) is True


def test_pump_storm_parity_00002():
    # sdk_Aborted_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Aborted_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Aborted_cause_expired_1']())


def test_pump_admission_parity_00003():
    # sdk_Aborted_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_cause_timeout_1']()) is True


def test_pump_storm_parity_00003():
    # sdk_Aborted_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Aborted_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Aborted_cause_timeout_1']())


def test_pump_admission_parity_00004():
    # sdk_Aborted_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_cause_value_1']()) is True


def test_pump_storm_parity_00004():
    # sdk_Aborted_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Aborted_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Aborted_cause_value_1']())


def test_pump_admission_parity_00005():
    # sdk_Aborted_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_bare_0']()) is True


def test_pump_storm_parity_00005():
    # sdk_Aborted_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Aborted_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Aborted_bare_0']())


def test_pump_admission_parity_00006():
    # sdk_Aborted_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_cause_aborted_0']()) is True


def test_pump_storm_parity_00006():
    # sdk_Aborted_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Aborted_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Aborted_cause_aborted_0']())


def test_pump_admission_parity_00007():
    # sdk_Aborted_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_cause_expired_0']()) is True


def test_pump_storm_parity_00007():
    # sdk_Aborted_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Aborted_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Aborted_cause_expired_0']())


def test_pump_admission_parity_00008():
    # sdk_Aborted_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_cause_timeout_0']()) is True


def test_pump_storm_parity_00008():
    # sdk_Aborted_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Aborted_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Aborted_cause_timeout_0']())


def test_pump_admission_parity_00009():
    # sdk_Aborted_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_cause_value_0']()) is True


def test_pump_storm_parity_00009():
    # sdk_Aborted_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Aborted_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Aborted_cause_value_0']())


def test_pump_admission_parity_00010():
    # sdk_AlreadyExists_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_bare_1']()) is False


def test_pump_storm_parity_00010():
    # sdk_AlreadyExists_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_AlreadyExists_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_AlreadyExists_bare_1']())


def test_pump_admission_parity_00011():
    # sdk_AlreadyExists_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_1']()) is True


def test_pump_storm_parity_00011():
    # sdk_AlreadyExists_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_1']())


def test_pump_admission_parity_00012():
    # sdk_AlreadyExists_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_1']()) is True


def test_pump_storm_parity_00012():
    # sdk_AlreadyExists_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_1']())


def test_pump_admission_parity_00013():
    # sdk_AlreadyExists_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_1']()) is False


def test_pump_storm_parity_00013():
    # sdk_AlreadyExists_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_1']())


def test_pump_admission_parity_00014():
    # sdk_AlreadyExists_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_1']()) is False


def test_pump_storm_parity_00014():
    # sdk_AlreadyExists_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_1']())


def test_pump_admission_parity_00015():
    # sdk_AlreadyExists_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_bare_0']()) is False


def test_pump_storm_parity_00015():
    # sdk_AlreadyExists_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_AlreadyExists_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_AlreadyExists_bare_0']())


def test_pump_admission_parity_00016():
    # sdk_AlreadyExists_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_0']()) is True


def test_pump_storm_parity_00016():
    # sdk_AlreadyExists_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_0']())


def test_pump_admission_parity_00017():
    # sdk_AlreadyExists_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_0']()) is True


def test_pump_storm_parity_00017():
    # sdk_AlreadyExists_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_0']())


def test_pump_admission_parity_00018():
    # sdk_AlreadyExists_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_0']()) is False


def test_pump_storm_parity_00018():
    # sdk_AlreadyExists_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_0']())


def test_pump_admission_parity_00019():
    # sdk_AlreadyExists_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_0']()) is False


def test_pump_storm_parity_00019():
    # sdk_AlreadyExists_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_0']())


def test_pump_admission_parity_00020():
    # sdk_BadGateway_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_bare_1']()) is False


def test_pump_storm_parity_00020():
    # sdk_BadGateway_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_BadGateway_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_BadGateway_bare_1']())


def test_pump_admission_parity_00021():
    # sdk_BadGateway_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_1']()) is True


def test_pump_storm_parity_00021():
    # sdk_BadGateway_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_1']())


def test_pump_admission_parity_00022():
    # sdk_BadGateway_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_cause_expired_1']()) is True


def test_pump_storm_parity_00022():
    # sdk_BadGateway_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_BadGateway_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_BadGateway_cause_expired_1']())


def test_pump_admission_parity_00023():
    # sdk_BadGateway_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_1']()) is False


def test_pump_storm_parity_00023():
    # sdk_BadGateway_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_1']())


def test_pump_admission_parity_00024():
    # sdk_BadGateway_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_cause_value_1']()) is False


def test_pump_storm_parity_00024():
    # sdk_BadGateway_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_BadGateway_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_BadGateway_cause_value_1']())


def test_pump_admission_parity_00025():
    # sdk_BadGateway_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_bare_0']()) is False


def test_pump_storm_parity_00025():
    # sdk_BadGateway_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_BadGateway_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_BadGateway_bare_0']())


def test_pump_admission_parity_00026():
    # sdk_BadGateway_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_0']()) is True


def test_pump_storm_parity_00026():
    # sdk_BadGateway_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_0']())


def test_pump_admission_parity_00027():
    # sdk_BadGateway_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_cause_expired_0']()) is True


def test_pump_storm_parity_00027():
    # sdk_BadGateway_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_BadGateway_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_BadGateway_cause_expired_0']())


def test_pump_admission_parity_00028():
    # sdk_BadGateway_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_0']()) is False


def test_pump_storm_parity_00028():
    # sdk_BadGateway_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_0']())


def test_pump_admission_parity_00029():
    # sdk_BadGateway_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_cause_value_0']()) is False


def test_pump_storm_parity_00029():
    # sdk_BadGateway_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_BadGateway_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_BadGateway_cause_value_0']())


def test_pump_admission_parity_00030():
    # sdk_BadRequest_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_bare_1']()) is False


def test_pump_storm_parity_00030():
    # sdk_BadRequest_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_BadRequest_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_BadRequest_bare_1']())


def test_pump_admission_parity_00031():
    # sdk_BadRequest_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_1']()) is True


def test_pump_storm_parity_00031():
    # sdk_BadRequest_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_1']())


def test_pump_admission_parity_00032():
    # sdk_BadRequest_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_cause_expired_1']()) is True


def test_pump_storm_parity_00032():
    # sdk_BadRequest_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_BadRequest_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_BadRequest_cause_expired_1']())


def test_pump_admission_parity_00033():
    # sdk_BadRequest_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_1']()) is False


def test_pump_storm_parity_00033():
    # sdk_BadRequest_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_1']())


def test_pump_admission_parity_00034():
    # sdk_BadRequest_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_cause_value_1']()) is False


def test_pump_storm_parity_00034():
    # sdk_BadRequest_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_BadRequest_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_BadRequest_cause_value_1']())


def test_pump_admission_parity_00035():
    # sdk_BadRequest_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_bare_0']()) is False


def test_pump_storm_parity_00035():
    # sdk_BadRequest_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_BadRequest_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_BadRequest_bare_0']())


def test_pump_admission_parity_00036():
    # sdk_BadRequest_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_0']()) is True


def test_pump_storm_parity_00036():
    # sdk_BadRequest_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_0']())


def test_pump_admission_parity_00037():
    # sdk_BadRequest_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_cause_expired_0']()) is True


def test_pump_storm_parity_00037():
    # sdk_BadRequest_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_BadRequest_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_BadRequest_cause_expired_0']())


def test_pump_admission_parity_00038():
    # sdk_BadRequest_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_0']()) is False


def test_pump_storm_parity_00038():
    # sdk_BadRequest_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_0']())


def test_pump_admission_parity_00039():
    # sdk_BadRequest_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_cause_value_0']()) is False


def test_pump_storm_parity_00039():
    # sdk_BadRequest_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_BadRequest_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_BadRequest_cause_value_0']())


def test_pump_admission_parity_00040():
    # sdk_Cancelled_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_bare_1']()) is False


def test_pump_storm_parity_00040():
    # sdk_Cancelled_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Cancelled_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Cancelled_bare_1']())


def test_pump_admission_parity_00041():
    # sdk_Cancelled_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_1']()) is True


def test_pump_storm_parity_00041():
    # sdk_Cancelled_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_1']())


def test_pump_admission_parity_00042():
    # sdk_Cancelled_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_cause_expired_1']()) is True


def test_pump_storm_parity_00042():
    # sdk_Cancelled_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Cancelled_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Cancelled_cause_expired_1']())


def test_pump_admission_parity_00043():
    # sdk_Cancelled_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_1']()) is False


def test_pump_storm_parity_00043():
    # sdk_Cancelled_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_1']())


def test_pump_admission_parity_00044():
    # sdk_Cancelled_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_cause_value_1']()) is False


def test_pump_storm_parity_00044():
    # sdk_Cancelled_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Cancelled_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Cancelled_cause_value_1']())


def test_pump_admission_parity_00045():
    # sdk_Cancelled_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_bare_0']()) is False


def test_pump_storm_parity_00045():
    # sdk_Cancelled_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Cancelled_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Cancelled_bare_0']())


def test_pump_admission_parity_00046():
    # sdk_Cancelled_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_0']()) is True


def test_pump_storm_parity_00046():
    # sdk_Cancelled_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_0']())


def test_pump_admission_parity_00047():
    # sdk_Cancelled_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_cause_expired_0']()) is True


def test_pump_storm_parity_00047():
    # sdk_Cancelled_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Cancelled_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Cancelled_cause_expired_0']())


def test_pump_admission_parity_00048():
    # sdk_Cancelled_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_0']()) is False


def test_pump_storm_parity_00048():
    # sdk_Cancelled_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_0']())


def test_pump_admission_parity_00049():
    # sdk_Cancelled_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_cause_value_0']()) is False


def test_pump_storm_parity_00049():
    # sdk_Cancelled_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Cancelled_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Cancelled_cause_value_0']())


def test_pump_admission_parity_00050():
    # sdk_ClientError_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_bare_1']()) is False


def test_pump_storm_parity_00050():
    # sdk_ClientError_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ClientError_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ClientError_bare_1']())


def test_pump_admission_parity_00051():
    # sdk_ClientError_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_cause_aborted_1']()) is True


def test_pump_storm_parity_00051():
    # sdk_ClientError_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ClientError_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ClientError_cause_aborted_1']())


def test_pump_admission_parity_00052():
    # sdk_ClientError_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_cause_expired_1']()) is True


def test_pump_storm_parity_00052():
    # sdk_ClientError_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ClientError_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ClientError_cause_expired_1']())


def test_pump_admission_parity_00053():
    # sdk_ClientError_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_cause_timeout_1']()) is False


def test_pump_storm_parity_00053():
    # sdk_ClientError_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ClientError_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ClientError_cause_timeout_1']())


def test_pump_admission_parity_00054():
    # sdk_ClientError_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_cause_value_1']()) is False


def test_pump_storm_parity_00054():
    # sdk_ClientError_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ClientError_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ClientError_cause_value_1']())


def test_pump_admission_parity_00055():
    # sdk_ClientError_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_bare_0']()) is False


def test_pump_storm_parity_00055():
    # sdk_ClientError_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ClientError_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ClientError_bare_0']())


def test_pump_admission_parity_00056():
    # sdk_ClientError_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_cause_aborted_0']()) is True


def test_pump_storm_parity_00056():
    # sdk_ClientError_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ClientError_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ClientError_cause_aborted_0']())


def test_pump_admission_parity_00057():
    # sdk_ClientError_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_cause_expired_0']()) is True


def test_pump_storm_parity_00057():
    # sdk_ClientError_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ClientError_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ClientError_cause_expired_0']())


def test_pump_admission_parity_00058():
    # sdk_ClientError_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_cause_timeout_0']()) is False


def test_pump_storm_parity_00058():
    # sdk_ClientError_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ClientError_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ClientError_cause_timeout_0']())


def test_pump_admission_parity_00059():
    # sdk_ClientError_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_cause_value_0']()) is False


def test_pump_storm_parity_00059():
    # sdk_ClientError_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ClientError_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ClientError_cause_value_0']())


def test_pump_admission_parity_00060():
    # sdk_Conflict_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_bare_1']()) is False


def test_pump_storm_parity_00060():
    # sdk_Conflict_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Conflict_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Conflict_bare_1']())


def test_pump_admission_parity_00061():
    # sdk_Conflict_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_cause_aborted_1']()) is True


def test_pump_storm_parity_00061():
    # sdk_Conflict_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Conflict_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Conflict_cause_aborted_1']())


def test_pump_admission_parity_00062():
    # sdk_Conflict_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_cause_expired_1']()) is True


def test_pump_storm_parity_00062():
    # sdk_Conflict_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Conflict_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Conflict_cause_expired_1']())


def test_pump_admission_parity_00063():
    # sdk_Conflict_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_cause_timeout_1']()) is False


def test_pump_storm_parity_00063():
    # sdk_Conflict_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Conflict_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Conflict_cause_timeout_1']())


def test_pump_admission_parity_00064():
    # sdk_Conflict_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_cause_value_1']()) is False


def test_pump_storm_parity_00064():
    # sdk_Conflict_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Conflict_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Conflict_cause_value_1']())


def test_pump_admission_parity_00065():
    # sdk_Conflict_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_bare_0']()) is False


def test_pump_storm_parity_00065():
    # sdk_Conflict_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Conflict_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Conflict_bare_0']())


def test_pump_admission_parity_00066():
    # sdk_Conflict_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_cause_aborted_0']()) is True


def test_pump_storm_parity_00066():
    # sdk_Conflict_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Conflict_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Conflict_cause_aborted_0']())


def test_pump_admission_parity_00067():
    # sdk_Conflict_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_cause_expired_0']()) is True


def test_pump_storm_parity_00067():
    # sdk_Conflict_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Conflict_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Conflict_cause_expired_0']())


def test_pump_admission_parity_00068():
    # sdk_Conflict_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_cause_timeout_0']()) is False


def test_pump_storm_parity_00068():
    # sdk_Conflict_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Conflict_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Conflict_cause_timeout_0']())


def test_pump_admission_parity_00069():
    # sdk_Conflict_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_cause_value_0']()) is False


def test_pump_storm_parity_00069():
    # sdk_Conflict_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Conflict_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Conflict_cause_value_0']())


def test_pump_admission_parity_00070():
    # sdk_DataLoss_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_bare_1']()) is False


def test_pump_storm_parity_00070():
    # sdk_DataLoss_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DataLoss_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DataLoss_bare_1']())


def test_pump_admission_parity_00071():
    # sdk_DataLoss_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_1']()) is True


def test_pump_storm_parity_00071():
    # sdk_DataLoss_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_1']())


def test_pump_admission_parity_00072():
    # sdk_DataLoss_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_cause_expired_1']()) is True


def test_pump_storm_parity_00072():
    # sdk_DataLoss_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DataLoss_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DataLoss_cause_expired_1']())


def test_pump_admission_parity_00073():
    # sdk_DataLoss_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_1']()) is False


def test_pump_storm_parity_00073():
    # sdk_DataLoss_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_1']())


def test_pump_admission_parity_00074():
    # sdk_DataLoss_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_cause_value_1']()) is False


def test_pump_storm_parity_00074():
    # sdk_DataLoss_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DataLoss_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DataLoss_cause_value_1']())


def test_pump_admission_parity_00075():
    # sdk_DataLoss_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_bare_0']()) is False


def test_pump_storm_parity_00075():
    # sdk_DataLoss_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DataLoss_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DataLoss_bare_0']())


def test_pump_admission_parity_00076():
    # sdk_DataLoss_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_0']()) is True


def test_pump_storm_parity_00076():
    # sdk_DataLoss_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_0']())


def test_pump_admission_parity_00077():
    # sdk_DataLoss_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_cause_expired_0']()) is True


def test_pump_storm_parity_00077():
    # sdk_DataLoss_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DataLoss_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DataLoss_cause_expired_0']())


def test_pump_admission_parity_00078():
    # sdk_DataLoss_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_0']()) is False


def test_pump_storm_parity_00078():
    # sdk_DataLoss_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_0']())


def test_pump_admission_parity_00079():
    # sdk_DataLoss_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_cause_value_0']()) is False


def test_pump_storm_parity_00079():
    # sdk_DataLoss_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DataLoss_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DataLoss_cause_value_0']())


def test_pump_admission_parity_00080():
    # sdk_DeadlineExceeded_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_1']()) is False


def test_pump_storm_parity_00080():
    # sdk_DeadlineExceeded_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_1']())


def test_pump_admission_parity_00081():
    # sdk_DeadlineExceeded_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_1']()) is True


def test_pump_storm_parity_00081():
    # sdk_DeadlineExceeded_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_1']())


def test_pump_admission_parity_00082():
    # sdk_DeadlineExceeded_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_1']()) is True


def test_pump_storm_parity_00082():
    # sdk_DeadlineExceeded_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_1']())


def test_pump_admission_parity_00083():
    # sdk_DeadlineExceeded_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_1']()) is False


def test_pump_storm_parity_00083():
    # sdk_DeadlineExceeded_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_1']())


def test_pump_admission_parity_00084():
    # sdk_DeadlineExceeded_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_1']()) is False


def test_pump_storm_parity_00084():
    # sdk_DeadlineExceeded_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_1']())


def test_pump_admission_parity_00085():
    # sdk_DeadlineExceeded_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_0']()) is False


def test_pump_storm_parity_00085():
    # sdk_DeadlineExceeded_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_0']())


def test_pump_admission_parity_00086():
    # sdk_DeadlineExceeded_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_0']()) is True


def test_pump_storm_parity_00086():
    # sdk_DeadlineExceeded_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_0']())


def test_pump_admission_parity_00087():
    # sdk_DeadlineExceeded_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_0']()) is True


def test_pump_storm_parity_00087():
    # sdk_DeadlineExceeded_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_0']())


def test_pump_admission_parity_00088():
    # sdk_DeadlineExceeded_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_0']()) is False


def test_pump_storm_parity_00088():
    # sdk_DeadlineExceeded_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_0']())


def test_pump_admission_parity_00089():
    # sdk_DeadlineExceeded_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_0']()) is False


def test_pump_storm_parity_00089():
    # sdk_DeadlineExceeded_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_0']())


def test_pump_admission_parity_00090():
    # sdk_DuplicateCredentialArgs_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_1']()) is False


def test_pump_storm_parity_00090():
    # sdk_DuplicateCredentialArgs_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_1']())


def test_pump_admission_parity_00091():
    # sdk_DuplicateCredentialArgs_cause_aborted_1
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_1']())
        is True
    )


def test_pump_storm_parity_00091():
    # sdk_DuplicateCredentialArgs_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_1']())


def test_pump_admission_parity_00092():
    # sdk_DuplicateCredentialArgs_cause_expired_1
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_1']())
        is True
    )


def test_pump_storm_parity_00092():
    # sdk_DuplicateCredentialArgs_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_1']())


def test_pump_admission_parity_00093():
    # sdk_DuplicateCredentialArgs_cause_timeout_1
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_1']())
        is False
    )


def test_pump_storm_parity_00093():
    # sdk_DuplicateCredentialArgs_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_1']())


def test_pump_admission_parity_00094():
    # sdk_DuplicateCredentialArgs_cause_value_1
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_1']()) is False
    )


def test_pump_storm_parity_00094():
    # sdk_DuplicateCredentialArgs_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_1']())


def test_pump_admission_parity_00095():
    # sdk_DuplicateCredentialArgs_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_0']()) is False


def test_pump_storm_parity_00095():
    # sdk_DuplicateCredentialArgs_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_0']())


def test_pump_admission_parity_00096():
    # sdk_DuplicateCredentialArgs_cause_aborted_0
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_0']())
        is True
    )


def test_pump_storm_parity_00096():
    # sdk_DuplicateCredentialArgs_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_0']())


def test_pump_admission_parity_00097():
    # sdk_DuplicateCredentialArgs_cause_expired_0
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_0']())
        is True
    )


def test_pump_storm_parity_00097():
    # sdk_DuplicateCredentialArgs_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_0']())


def test_pump_admission_parity_00098():
    # sdk_DuplicateCredentialArgs_cause_timeout_0
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_0']())
        is False
    )


def test_pump_storm_parity_00098():
    # sdk_DuplicateCredentialArgs_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_0']())


def test_pump_admission_parity_00099():
    # sdk_DuplicateCredentialArgs_cause_value_0
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_0']()) is False
    )


def test_pump_storm_parity_00099():
    # sdk_DuplicateCredentialArgs_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_0']())


def test_pump_admission_parity_00100():
    # sdk_FailedPrecondition_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_bare_1']()) is False


def test_pump_storm_parity_00100():
    # sdk_FailedPrecondition_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_FailedPrecondition_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_FailedPrecondition_bare_1']())


def test_pump_admission_parity_00101():
    # sdk_FailedPrecondition_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_1']()) is True


def test_pump_storm_parity_00101():
    # sdk_FailedPrecondition_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_1']())


def test_pump_admission_parity_00102():
    # sdk_FailedPrecondition_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_1']()) is True


def test_pump_storm_parity_00102():
    # sdk_FailedPrecondition_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_1']())


def test_pump_admission_parity_00103():
    # sdk_FailedPrecondition_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_1']()) is False


def test_pump_storm_parity_00103():
    # sdk_FailedPrecondition_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_1']())


def test_pump_admission_parity_00104():
    # sdk_FailedPrecondition_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_1']()) is False


def test_pump_storm_parity_00104():
    # sdk_FailedPrecondition_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_1']())


def test_pump_admission_parity_00105():
    # sdk_FailedPrecondition_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_bare_0']()) is False


def test_pump_storm_parity_00105():
    # sdk_FailedPrecondition_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_FailedPrecondition_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_FailedPrecondition_bare_0']())


def test_pump_admission_parity_00106():
    # sdk_FailedPrecondition_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_0']()) is True


def test_pump_storm_parity_00106():
    # sdk_FailedPrecondition_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_0']())


def test_pump_admission_parity_00107():
    # sdk_FailedPrecondition_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_0']()) is True


def test_pump_storm_parity_00107():
    # sdk_FailedPrecondition_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_0']())


def test_pump_admission_parity_00108():
    # sdk_FailedPrecondition_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_0']()) is False


def test_pump_storm_parity_00108():
    # sdk_FailedPrecondition_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_0']())


def test_pump_admission_parity_00109():
    # sdk_FailedPrecondition_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_0']()) is False


def test_pump_storm_parity_00109():
    # sdk_FailedPrecondition_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_0']())


def test_pump_admission_parity_00110():
    # sdk_Forbidden_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_bare_1']()) is False


def test_pump_storm_parity_00110():
    # sdk_Forbidden_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Forbidden_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Forbidden_bare_1']())


def test_pump_admission_parity_00111():
    # sdk_Forbidden_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_1']()) is True


def test_pump_storm_parity_00111():
    # sdk_Forbidden_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_1']())


def test_pump_admission_parity_00112():
    # sdk_Forbidden_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_cause_expired_1']()) is True


def test_pump_storm_parity_00112():
    # sdk_Forbidden_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Forbidden_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Forbidden_cause_expired_1']())


def test_pump_admission_parity_00113():
    # sdk_Forbidden_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_1']()) is False


def test_pump_storm_parity_00113():
    # sdk_Forbidden_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_1']())


def test_pump_admission_parity_00114():
    # sdk_Forbidden_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_cause_value_1']()) is False


def test_pump_storm_parity_00114():
    # sdk_Forbidden_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Forbidden_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Forbidden_cause_value_1']())


def test_pump_admission_parity_00115():
    # sdk_Forbidden_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_bare_0']()) is False


def test_pump_storm_parity_00115():
    # sdk_Forbidden_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Forbidden_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Forbidden_bare_0']())


def test_pump_admission_parity_00116():
    # sdk_Forbidden_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_0']()) is True


def test_pump_storm_parity_00116():
    # sdk_Forbidden_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_0']())


def test_pump_admission_parity_00117():
    # sdk_Forbidden_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_cause_expired_0']()) is True


def test_pump_storm_parity_00117():
    # sdk_Forbidden_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Forbidden_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Forbidden_cause_expired_0']())


def test_pump_admission_parity_00118():
    # sdk_Forbidden_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_0']()) is False


def test_pump_storm_parity_00118():
    # sdk_Forbidden_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_0']())


def test_pump_admission_parity_00119():
    # sdk_Forbidden_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_cause_value_0']()) is False


def test_pump_storm_parity_00119():
    # sdk_Forbidden_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Forbidden_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Forbidden_cause_value_0']())


def test_pump_admission_parity_00120():
    # sdk_GatewayTimeout_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_bare_1']()) is False


def test_pump_storm_parity_00120():
    # sdk_GatewayTimeout_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GatewayTimeout_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GatewayTimeout_bare_1']())


def test_pump_admission_parity_00121():
    # sdk_GatewayTimeout_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_1']()) is True


def test_pump_storm_parity_00121():
    # sdk_GatewayTimeout_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_1']())


def test_pump_admission_parity_00122():
    # sdk_GatewayTimeout_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_1']()) is True


def test_pump_storm_parity_00122():
    # sdk_GatewayTimeout_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_1']())


def test_pump_admission_parity_00123():
    # sdk_GatewayTimeout_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_1']()) is False


def test_pump_storm_parity_00123():
    # sdk_GatewayTimeout_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_1']())


def test_pump_admission_parity_00124():
    # sdk_GatewayTimeout_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_1']()) is False


def test_pump_storm_parity_00124():
    # sdk_GatewayTimeout_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_1']())


def test_pump_admission_parity_00125():
    # sdk_GatewayTimeout_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_bare_0']()) is False


def test_pump_storm_parity_00125():
    # sdk_GatewayTimeout_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GatewayTimeout_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GatewayTimeout_bare_0']())


def test_pump_admission_parity_00126():
    # sdk_GatewayTimeout_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_0']()) is True


def test_pump_storm_parity_00126():
    # sdk_GatewayTimeout_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_0']())


def test_pump_admission_parity_00127():
    # sdk_GatewayTimeout_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_0']()) is True


def test_pump_storm_parity_00127():
    # sdk_GatewayTimeout_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_0']())


def test_pump_admission_parity_00128():
    # sdk_GatewayTimeout_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_0']()) is False


def test_pump_storm_parity_00128():
    # sdk_GatewayTimeout_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_0']())


def test_pump_admission_parity_00129():
    # sdk_GatewayTimeout_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_0']()) is False


def test_pump_storm_parity_00129():
    # sdk_GatewayTimeout_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_0']())


def test_pump_admission_parity_00130():
    # sdk_GoogleAPICallError_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_1']()) is False


def test_pump_storm_parity_00130():
    # sdk_GoogleAPICallError_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_1']())


def test_pump_admission_parity_00131():
    # sdk_GoogleAPICallError_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_1']()) is True


def test_pump_storm_parity_00131():
    # sdk_GoogleAPICallError_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_1']())


def test_pump_admission_parity_00132():
    # sdk_GoogleAPICallError_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_1']()) is True


def test_pump_storm_parity_00132():
    # sdk_GoogleAPICallError_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_1']())


def test_pump_admission_parity_00133():
    # sdk_GoogleAPICallError_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_1']()) is False


def test_pump_storm_parity_00133():
    # sdk_GoogleAPICallError_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_1']())


def test_pump_admission_parity_00134():
    # sdk_GoogleAPICallError_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_1']()) is False


def test_pump_storm_parity_00134():
    # sdk_GoogleAPICallError_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_1']())


def test_pump_admission_parity_00135():
    # sdk_GoogleAPICallError_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_0']()) is False


def test_pump_storm_parity_00135():
    # sdk_GoogleAPICallError_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_0']())


def test_pump_admission_parity_00136():
    # sdk_GoogleAPICallError_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_0']()) is True


def test_pump_storm_parity_00136():
    # sdk_GoogleAPICallError_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_0']())


def test_pump_admission_parity_00137():
    # sdk_GoogleAPICallError_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_0']()) is True


def test_pump_storm_parity_00137():
    # sdk_GoogleAPICallError_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_0']())


def test_pump_admission_parity_00138():
    # sdk_GoogleAPICallError_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_0']()) is False


def test_pump_storm_parity_00138():
    # sdk_GoogleAPICallError_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_0']())


def test_pump_admission_parity_00139():
    # sdk_GoogleAPICallError_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_0']()) is False


def test_pump_storm_parity_00139():
    # sdk_GoogleAPICallError_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_0']())


def test_pump_admission_parity_00140():
    # sdk_GoogleAPIError_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_bare_1']()) is False


def test_pump_storm_parity_00140():
    # sdk_GoogleAPIError_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GoogleAPIError_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GoogleAPIError_bare_1']())


def test_pump_admission_parity_00141():
    # sdk_GoogleAPIError_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_1']()) is True


def test_pump_storm_parity_00141():
    # sdk_GoogleAPIError_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_1']())


def test_pump_admission_parity_00142():
    # sdk_GoogleAPIError_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_1']()) is True


def test_pump_storm_parity_00142():
    # sdk_GoogleAPIError_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_1']())


def test_pump_admission_parity_00143():
    # sdk_GoogleAPIError_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_1']()) is False


def test_pump_storm_parity_00143():
    # sdk_GoogleAPIError_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_1']())


def test_pump_admission_parity_00144():
    # sdk_GoogleAPIError_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_1']()) is False


def test_pump_storm_parity_00144():
    # sdk_GoogleAPIError_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_1']())


def test_pump_admission_parity_00145():
    # sdk_GoogleAPIError_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_bare_0']()) is False


def test_pump_storm_parity_00145():
    # sdk_GoogleAPIError_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GoogleAPIError_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GoogleAPIError_bare_0']())


def test_pump_admission_parity_00146():
    # sdk_GoogleAPIError_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_0']()) is True


def test_pump_storm_parity_00146():
    # sdk_GoogleAPIError_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_0']())


def test_pump_admission_parity_00147():
    # sdk_GoogleAPIError_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_0']()) is True


def test_pump_storm_parity_00147():
    # sdk_GoogleAPIError_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_0']())


def test_pump_admission_parity_00148():
    # sdk_GoogleAPIError_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_0']()) is False


def test_pump_storm_parity_00148():
    # sdk_GoogleAPIError_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_0']())


def test_pump_admission_parity_00149():
    # sdk_GoogleAPIError_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_0']()) is False


def test_pump_storm_parity_00149():
    # sdk_GoogleAPIError_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_0']())


def test_pump_admission_parity_00150():
    # sdk_InternalServerError_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_bare_1']()) is False


def test_pump_storm_parity_00150():
    # sdk_InternalServerError_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_InternalServerError_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_InternalServerError_bare_1']())


def test_pump_admission_parity_00151():
    # sdk_InternalServerError_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_1']()) is True


def test_pump_storm_parity_00151():
    # sdk_InternalServerError_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_1']())


def test_pump_admission_parity_00152():
    # sdk_InternalServerError_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_1']()) is True


def test_pump_storm_parity_00152():
    # sdk_InternalServerError_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_1']())


def test_pump_admission_parity_00153():
    # sdk_InternalServerError_cause_timeout_1
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_1']()) is False
    )


def test_pump_storm_parity_00153():
    # sdk_InternalServerError_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_1']())


def test_pump_admission_parity_00154():
    # sdk_InternalServerError_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_cause_value_1']()) is False


def test_pump_storm_parity_00154():
    # sdk_InternalServerError_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_InternalServerError_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_InternalServerError_cause_value_1']())


def test_pump_admission_parity_00155():
    # sdk_InternalServerError_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_bare_0']()) is False


def test_pump_storm_parity_00155():
    # sdk_InternalServerError_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_InternalServerError_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_InternalServerError_bare_0']())


def test_pump_admission_parity_00156():
    # sdk_InternalServerError_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_0']()) is True


def test_pump_storm_parity_00156():
    # sdk_InternalServerError_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_0']())


def test_pump_admission_parity_00157():
    # sdk_InternalServerError_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_0']()) is True


def test_pump_storm_parity_00157():
    # sdk_InternalServerError_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_0']())


def test_pump_admission_parity_00158():
    # sdk_InternalServerError_cause_timeout_0
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_0']()) is False
    )


def test_pump_storm_parity_00158():
    # sdk_InternalServerError_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_0']())


def test_pump_admission_parity_00159():
    # sdk_InternalServerError_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_cause_value_0']()) is False


def test_pump_storm_parity_00159():
    # sdk_InternalServerError_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_InternalServerError_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_InternalServerError_cause_value_0']())


def test_pump_admission_parity_00160():
    # sdk_InvalidArgument_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_bare_1']()) is False


def test_pump_storm_parity_00160():
    # sdk_InvalidArgument_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_InvalidArgument_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_InvalidArgument_bare_1']())


def test_pump_admission_parity_00161():
    # sdk_InvalidArgument_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_1']()) is True


def test_pump_storm_parity_00161():
    # sdk_InvalidArgument_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_1']())


def test_pump_admission_parity_00162():
    # sdk_InvalidArgument_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_1']()) is True


def test_pump_storm_parity_00162():
    # sdk_InvalidArgument_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_1']())


def test_pump_admission_parity_00163():
    # sdk_InvalidArgument_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_1']()) is False


def test_pump_storm_parity_00163():
    # sdk_InvalidArgument_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_1']())


def test_pump_admission_parity_00164():
    # sdk_InvalidArgument_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_1']()) is False


def test_pump_storm_parity_00164():
    # sdk_InvalidArgument_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_1']())


def test_pump_admission_parity_00165():
    # sdk_InvalidArgument_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_bare_0']()) is False


def test_pump_storm_parity_00165():
    # sdk_InvalidArgument_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_InvalidArgument_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_InvalidArgument_bare_0']())


def test_pump_admission_parity_00166():
    # sdk_InvalidArgument_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_0']()) is True


def test_pump_storm_parity_00166():
    # sdk_InvalidArgument_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_0']())


def test_pump_admission_parity_00167():
    # sdk_InvalidArgument_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_0']()) is True


def test_pump_storm_parity_00167():
    # sdk_InvalidArgument_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_0']())


def test_pump_admission_parity_00168():
    # sdk_InvalidArgument_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_0']()) is False


def test_pump_storm_parity_00168():
    # sdk_InvalidArgument_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_0']())


def test_pump_admission_parity_00169():
    # sdk_InvalidArgument_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_0']()) is False


def test_pump_storm_parity_00169():
    # sdk_InvalidArgument_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_0']())


def test_pump_admission_parity_00170():
    # sdk_LengthRequired_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_bare_1']()) is False


def test_pump_storm_parity_00170():
    # sdk_LengthRequired_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_LengthRequired_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_LengthRequired_bare_1']())


def test_pump_admission_parity_00171():
    # sdk_LengthRequired_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_1']()) is True


def test_pump_storm_parity_00171():
    # sdk_LengthRequired_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_1']())


def test_pump_admission_parity_00172():
    # sdk_LengthRequired_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_1']()) is True


def test_pump_storm_parity_00172():
    # sdk_LengthRequired_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_1']())


def test_pump_admission_parity_00173():
    # sdk_LengthRequired_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_1']()) is False


def test_pump_storm_parity_00173():
    # sdk_LengthRequired_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_1']())


def test_pump_admission_parity_00174():
    # sdk_LengthRequired_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_cause_value_1']()) is False


def test_pump_storm_parity_00174():
    # sdk_LengthRequired_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_LengthRequired_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_LengthRequired_cause_value_1']())


def test_pump_admission_parity_00175():
    # sdk_LengthRequired_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_bare_0']()) is False


def test_pump_storm_parity_00175():
    # sdk_LengthRequired_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_LengthRequired_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_LengthRequired_bare_0']())


def test_pump_admission_parity_00176():
    # sdk_LengthRequired_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_0']()) is True


def test_pump_storm_parity_00176():
    # sdk_LengthRequired_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_0']())


def test_pump_admission_parity_00177():
    # sdk_LengthRequired_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_0']()) is True


def test_pump_storm_parity_00177():
    # sdk_LengthRequired_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_0']())


def test_pump_admission_parity_00178():
    # sdk_LengthRequired_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_0']()) is False


def test_pump_storm_parity_00178():
    # sdk_LengthRequired_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_0']())


def test_pump_admission_parity_00179():
    # sdk_LengthRequired_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_cause_value_0']()) is False


def test_pump_storm_parity_00179():
    # sdk_LengthRequired_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_LengthRequired_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_LengthRequired_cause_value_0']())


def test_pump_admission_parity_00180():
    # sdk_MethodNotAllowed_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_1']()) is False


def test_pump_storm_parity_00180():
    # sdk_MethodNotAllowed_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_1']())


def test_pump_admission_parity_00181():
    # sdk_MethodNotAllowed_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_1']()) is True


def test_pump_storm_parity_00181():
    # sdk_MethodNotAllowed_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_1']())


def test_pump_admission_parity_00182():
    # sdk_MethodNotAllowed_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_1']()) is True


def test_pump_storm_parity_00182():
    # sdk_MethodNotAllowed_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_1']())


def test_pump_admission_parity_00183():
    # sdk_MethodNotAllowed_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_1']()) is False


def test_pump_storm_parity_00183():
    # sdk_MethodNotAllowed_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_1']())


def test_pump_admission_parity_00184():
    # sdk_MethodNotAllowed_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_1']()) is False


def test_pump_storm_parity_00184():
    # sdk_MethodNotAllowed_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_1']())


def test_pump_admission_parity_00185():
    # sdk_MethodNotAllowed_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_0']()) is False


def test_pump_storm_parity_00185():
    # sdk_MethodNotAllowed_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_0']())


def test_pump_admission_parity_00186():
    # sdk_MethodNotAllowed_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_0']()) is True


def test_pump_storm_parity_00186():
    # sdk_MethodNotAllowed_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_0']())


def test_pump_admission_parity_00187():
    # sdk_MethodNotAllowed_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_0']()) is True


def test_pump_storm_parity_00187():
    # sdk_MethodNotAllowed_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_0']())


def test_pump_admission_parity_00188():
    # sdk_MethodNotAllowed_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_0']()) is False


def test_pump_storm_parity_00188():
    # sdk_MethodNotAllowed_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_0']())


def test_pump_admission_parity_00189():
    # sdk_MethodNotAllowed_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_0']()) is False


def test_pump_storm_parity_00189():
    # sdk_MethodNotAllowed_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_0']())


def test_pump_admission_parity_00190():
    # sdk_MethodNotImplemented_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_1']()) is False


def test_pump_storm_parity_00190():
    # sdk_MethodNotImplemented_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_1']())


def test_pump_admission_parity_00191():
    # sdk_MethodNotImplemented_cause_aborted_1
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_1']()) is True
    )


def test_pump_storm_parity_00191():
    # sdk_MethodNotImplemented_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_1']())


def test_pump_admission_parity_00192():
    # sdk_MethodNotImplemented_cause_expired_1
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_1']()) is True
    )


def test_pump_storm_parity_00192():
    # sdk_MethodNotImplemented_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_1']())


def test_pump_admission_parity_00193():
    # sdk_MethodNotImplemented_cause_timeout_1
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_1']()) is False
    )


def test_pump_storm_parity_00193():
    # sdk_MethodNotImplemented_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_1']())


def test_pump_admission_parity_00194():
    # sdk_MethodNotImplemented_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_1']()) is False


def test_pump_storm_parity_00194():
    # sdk_MethodNotImplemented_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_1']())


def test_pump_admission_parity_00195():
    # sdk_MethodNotImplemented_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_0']()) is False


def test_pump_storm_parity_00195():
    # sdk_MethodNotImplemented_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_0']())


def test_pump_admission_parity_00196():
    # sdk_MethodNotImplemented_cause_aborted_0
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_0']()) is True
    )


def test_pump_storm_parity_00196():
    # sdk_MethodNotImplemented_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_0']())


def test_pump_admission_parity_00197():
    # sdk_MethodNotImplemented_cause_expired_0
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_0']()) is True
    )


def test_pump_storm_parity_00197():
    # sdk_MethodNotImplemented_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_0']())


def test_pump_admission_parity_00198():
    # sdk_MethodNotImplemented_cause_timeout_0
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_0']()) is False
    )


def test_pump_storm_parity_00198():
    # sdk_MethodNotImplemented_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_0']())


def test_pump_admission_parity_00199():
    # sdk_MethodNotImplemented_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_0']()) is False


def test_pump_storm_parity_00199():
    # sdk_MethodNotImplemented_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_0']())


def test_pump_admission_parity_00200():
    # sdk_MovedPermanently_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_bare_1']()) is False


def test_pump_storm_parity_00200():
    # sdk_MovedPermanently_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MovedPermanently_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MovedPermanently_bare_1']())


def test_pump_admission_parity_00201():
    # sdk_MovedPermanently_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_1']()) is True


def test_pump_storm_parity_00201():
    # sdk_MovedPermanently_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_1']())


def test_pump_admission_parity_00202():
    # sdk_MovedPermanently_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_1']()) is True


def test_pump_storm_parity_00202():
    # sdk_MovedPermanently_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_1']())


def test_pump_admission_parity_00203():
    # sdk_MovedPermanently_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_1']()) is False


def test_pump_storm_parity_00203():
    # sdk_MovedPermanently_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_1']())


def test_pump_admission_parity_00204():
    # sdk_MovedPermanently_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_1']()) is False


def test_pump_storm_parity_00204():
    # sdk_MovedPermanently_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_1']())


def test_pump_admission_parity_00205():
    # sdk_MovedPermanently_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_bare_0']()) is False


def test_pump_storm_parity_00205():
    # sdk_MovedPermanently_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MovedPermanently_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MovedPermanently_bare_0']())


def test_pump_admission_parity_00206():
    # sdk_MovedPermanently_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_0']()) is True


def test_pump_storm_parity_00206():
    # sdk_MovedPermanently_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_0']())


def test_pump_admission_parity_00207():
    # sdk_MovedPermanently_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_0']()) is True


def test_pump_storm_parity_00207():
    # sdk_MovedPermanently_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_0']())


def test_pump_admission_parity_00208():
    # sdk_MovedPermanently_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_0']()) is False


def test_pump_storm_parity_00208():
    # sdk_MovedPermanently_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_0']())


def test_pump_admission_parity_00209():
    # sdk_MovedPermanently_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_0']()) is False


def test_pump_storm_parity_00209():
    # sdk_MovedPermanently_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_0']())


def test_pump_admission_parity_00210():
    # sdk_NotFound_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_bare_1']()) is False


def test_pump_storm_parity_00210():
    # sdk_NotFound_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_NotFound_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_NotFound_bare_1']())


def test_pump_admission_parity_00211():
    # sdk_NotFound_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_cause_aborted_1']()) is True


def test_pump_storm_parity_00211():
    # sdk_NotFound_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_NotFound_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_NotFound_cause_aborted_1']())


def test_pump_admission_parity_00212():
    # sdk_NotFound_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_cause_expired_1']()) is True


def test_pump_storm_parity_00212():
    # sdk_NotFound_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_NotFound_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_NotFound_cause_expired_1']())


def test_pump_admission_parity_00213():
    # sdk_NotFound_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_cause_timeout_1']()) is False


def test_pump_storm_parity_00213():
    # sdk_NotFound_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_NotFound_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_NotFound_cause_timeout_1']())


def test_pump_admission_parity_00214():
    # sdk_NotFound_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_cause_value_1']()) is False


def test_pump_storm_parity_00214():
    # sdk_NotFound_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_NotFound_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_NotFound_cause_value_1']())


def test_pump_admission_parity_00215():
    # sdk_NotFound_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_bare_0']()) is False


def test_pump_storm_parity_00215():
    # sdk_NotFound_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_NotFound_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_NotFound_bare_0']())


def test_pump_admission_parity_00216():
    # sdk_NotFound_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_cause_aborted_0']()) is True


def test_pump_storm_parity_00216():
    # sdk_NotFound_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_NotFound_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_NotFound_cause_aborted_0']())


def test_pump_admission_parity_00217():
    # sdk_NotFound_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_cause_expired_0']()) is True


def test_pump_storm_parity_00217():
    # sdk_NotFound_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_NotFound_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_NotFound_cause_expired_0']())


def test_pump_admission_parity_00218():
    # sdk_NotFound_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_cause_timeout_0']()) is False


def test_pump_storm_parity_00218():
    # sdk_NotFound_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_NotFound_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_NotFound_cause_timeout_0']())


def test_pump_admission_parity_00219():
    # sdk_NotFound_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_cause_value_0']()) is False


def test_pump_storm_parity_00219():
    # sdk_NotFound_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_NotFound_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_NotFound_cause_value_0']())


def test_pump_admission_parity_00220():
    # sdk_NotModified_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_bare_1']()) is False


def test_pump_storm_parity_00220():
    # sdk_NotModified_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_NotModified_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_NotModified_bare_1']())


def test_pump_admission_parity_00221():
    # sdk_NotModified_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_cause_aborted_1']()) is True


def test_pump_storm_parity_00221():
    # sdk_NotModified_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_NotModified_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_NotModified_cause_aborted_1']())


def test_pump_admission_parity_00222():
    # sdk_NotModified_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_cause_expired_1']()) is True


def test_pump_storm_parity_00222():
    # sdk_NotModified_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_NotModified_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_NotModified_cause_expired_1']())


def test_pump_admission_parity_00223():
    # sdk_NotModified_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_cause_timeout_1']()) is False


def test_pump_storm_parity_00223():
    # sdk_NotModified_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_NotModified_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_NotModified_cause_timeout_1']())


def test_pump_admission_parity_00224():
    # sdk_NotModified_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_cause_value_1']()) is False


def test_pump_storm_parity_00224():
    # sdk_NotModified_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_NotModified_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_NotModified_cause_value_1']())


def test_pump_admission_parity_00225():
    # sdk_NotModified_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_bare_0']()) is False


def test_pump_storm_parity_00225():
    # sdk_NotModified_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_NotModified_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_NotModified_bare_0']())


def test_pump_admission_parity_00226():
    # sdk_NotModified_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_cause_aborted_0']()) is True


def test_pump_storm_parity_00226():
    # sdk_NotModified_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_NotModified_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_NotModified_cause_aborted_0']())


def test_pump_admission_parity_00227():
    # sdk_NotModified_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_cause_expired_0']()) is True


def test_pump_storm_parity_00227():
    # sdk_NotModified_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_NotModified_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_NotModified_cause_expired_0']())


def test_pump_admission_parity_00228():
    # sdk_NotModified_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_cause_timeout_0']()) is False


def test_pump_storm_parity_00228():
    # sdk_NotModified_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_NotModified_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_NotModified_cause_timeout_0']())


def test_pump_admission_parity_00229():
    # sdk_NotModified_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_cause_value_0']()) is False


def test_pump_storm_parity_00229():
    # sdk_NotModified_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_NotModified_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_NotModified_cause_value_0']())


def test_pump_admission_parity_00230():
    # sdk_OutOfRange_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_bare_1']()) is False


def test_pump_storm_parity_00230():
    # sdk_OutOfRange_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_OutOfRange_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_OutOfRange_bare_1']())


def test_pump_admission_parity_00231():
    # sdk_OutOfRange_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_1']()) is True


def test_pump_storm_parity_00231():
    # sdk_OutOfRange_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_1']())


def test_pump_admission_parity_00232():
    # sdk_OutOfRange_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_1']()) is True


def test_pump_storm_parity_00232():
    # sdk_OutOfRange_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_1']())


def test_pump_admission_parity_00233():
    # sdk_OutOfRange_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_1']()) is False


def test_pump_storm_parity_00233():
    # sdk_OutOfRange_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_1']())


def test_pump_admission_parity_00234():
    # sdk_OutOfRange_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_cause_value_1']()) is False


def test_pump_storm_parity_00234():
    # sdk_OutOfRange_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_OutOfRange_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_OutOfRange_cause_value_1']())


def test_pump_admission_parity_00235():
    # sdk_OutOfRange_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_bare_0']()) is False


def test_pump_storm_parity_00235():
    # sdk_OutOfRange_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_OutOfRange_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_OutOfRange_bare_0']())


def test_pump_admission_parity_00236():
    # sdk_OutOfRange_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_0']()) is True


def test_pump_storm_parity_00236():
    # sdk_OutOfRange_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_0']())


def test_pump_admission_parity_00237():
    # sdk_OutOfRange_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_0']()) is True


def test_pump_storm_parity_00237():
    # sdk_OutOfRange_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_0']())


def test_pump_admission_parity_00238():
    # sdk_OutOfRange_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_0']()) is False


def test_pump_storm_parity_00238():
    # sdk_OutOfRange_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_0']())


def test_pump_admission_parity_00239():
    # sdk_OutOfRange_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_cause_value_0']()) is False


def test_pump_storm_parity_00239():
    # sdk_OutOfRange_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_OutOfRange_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_OutOfRange_cause_value_0']())


def test_pump_admission_parity_00240():
    # sdk_PermissionDenied_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_bare_1']()) is False


def test_pump_storm_parity_00240():
    # sdk_PermissionDenied_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_PermissionDenied_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_PermissionDenied_bare_1']())


def test_pump_admission_parity_00241():
    # sdk_PermissionDenied_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_1']()) is True


def test_pump_storm_parity_00241():
    # sdk_PermissionDenied_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_1']())


def test_pump_admission_parity_00242():
    # sdk_PermissionDenied_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_1']()) is True


def test_pump_storm_parity_00242():
    # sdk_PermissionDenied_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_1']())


def test_pump_admission_parity_00243():
    # sdk_PermissionDenied_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_1']()) is False


def test_pump_storm_parity_00243():
    # sdk_PermissionDenied_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_1']())


def test_pump_admission_parity_00244():
    # sdk_PermissionDenied_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_1']()) is False


def test_pump_storm_parity_00244():
    # sdk_PermissionDenied_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_1']())


def test_pump_admission_parity_00245():
    # sdk_PermissionDenied_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_bare_0']()) is False


def test_pump_storm_parity_00245():
    # sdk_PermissionDenied_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_PermissionDenied_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_PermissionDenied_bare_0']())


def test_pump_admission_parity_00246():
    # sdk_PermissionDenied_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_0']()) is True


def test_pump_storm_parity_00246():
    # sdk_PermissionDenied_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_0']())


def test_pump_admission_parity_00247():
    # sdk_PermissionDenied_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_0']()) is True


def test_pump_storm_parity_00247():
    # sdk_PermissionDenied_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_0']())


def test_pump_admission_parity_00248():
    # sdk_PermissionDenied_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_0']()) is False


def test_pump_storm_parity_00248():
    # sdk_PermissionDenied_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_0']())


def test_pump_admission_parity_00249():
    # sdk_PermissionDenied_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_0']()) is False


def test_pump_storm_parity_00249():
    # sdk_PermissionDenied_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_0']())


def test_pump_admission_parity_00250():
    # sdk_PreconditionFailed_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_bare_1']()) is False


def test_pump_storm_parity_00250():
    # sdk_PreconditionFailed_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_PreconditionFailed_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_PreconditionFailed_bare_1']())


def test_pump_admission_parity_00251():
    # sdk_PreconditionFailed_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_1']()) is True


def test_pump_storm_parity_00251():
    # sdk_PreconditionFailed_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_1']())


def test_pump_admission_parity_00252():
    # sdk_PreconditionFailed_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_1']()) is True


def test_pump_storm_parity_00252():
    # sdk_PreconditionFailed_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_1']())


def test_pump_admission_parity_00253():
    # sdk_PreconditionFailed_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_1']()) is False


def test_pump_storm_parity_00253():
    # sdk_PreconditionFailed_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_1']())


def test_pump_admission_parity_00254():
    # sdk_PreconditionFailed_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_1']()) is False


def test_pump_storm_parity_00254():
    # sdk_PreconditionFailed_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_1']())


def test_pump_admission_parity_00255():
    # sdk_PreconditionFailed_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_bare_0']()) is False


def test_pump_storm_parity_00255():
    # sdk_PreconditionFailed_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_PreconditionFailed_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_PreconditionFailed_bare_0']())


def test_pump_admission_parity_00256():
    # sdk_PreconditionFailed_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_0']()) is True


def test_pump_storm_parity_00256():
    # sdk_PreconditionFailed_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_0']())


def test_pump_admission_parity_00257():
    # sdk_PreconditionFailed_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_0']()) is True


def test_pump_storm_parity_00257():
    # sdk_PreconditionFailed_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_0']())


def test_pump_admission_parity_00258():
    # sdk_PreconditionFailed_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_0']()) is False


def test_pump_storm_parity_00258():
    # sdk_PreconditionFailed_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_0']())


def test_pump_admission_parity_00259():
    # sdk_PreconditionFailed_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_0']()) is False


def test_pump_storm_parity_00259():
    # sdk_PreconditionFailed_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_0']())


def test_pump_admission_parity_00260():
    # sdk_Redirection_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_bare_1']()) is False


def test_pump_storm_parity_00260():
    # sdk_Redirection_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Redirection_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Redirection_bare_1']())


def test_pump_admission_parity_00261():
    # sdk_Redirection_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_cause_aborted_1']()) is True


def test_pump_storm_parity_00261():
    # sdk_Redirection_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Redirection_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Redirection_cause_aborted_1']())


def test_pump_admission_parity_00262():
    # sdk_Redirection_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_cause_expired_1']()) is True


def test_pump_storm_parity_00262():
    # sdk_Redirection_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Redirection_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Redirection_cause_expired_1']())


def test_pump_admission_parity_00263():
    # sdk_Redirection_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_cause_timeout_1']()) is False


def test_pump_storm_parity_00263():
    # sdk_Redirection_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Redirection_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Redirection_cause_timeout_1']())


def test_pump_admission_parity_00264():
    # sdk_Redirection_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_cause_value_1']()) is False


def test_pump_storm_parity_00264():
    # sdk_Redirection_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Redirection_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Redirection_cause_value_1']())


def test_pump_admission_parity_00265():
    # sdk_Redirection_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_bare_0']()) is False


def test_pump_storm_parity_00265():
    # sdk_Redirection_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Redirection_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Redirection_bare_0']())


def test_pump_admission_parity_00266():
    # sdk_Redirection_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_cause_aborted_0']()) is True


def test_pump_storm_parity_00266():
    # sdk_Redirection_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Redirection_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Redirection_cause_aborted_0']())


def test_pump_admission_parity_00267():
    # sdk_Redirection_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_cause_expired_0']()) is True


def test_pump_storm_parity_00267():
    # sdk_Redirection_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Redirection_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Redirection_cause_expired_0']())


def test_pump_admission_parity_00268():
    # sdk_Redirection_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_cause_timeout_0']()) is False


def test_pump_storm_parity_00268():
    # sdk_Redirection_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Redirection_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Redirection_cause_timeout_0']())


def test_pump_admission_parity_00269():
    # sdk_Redirection_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_cause_value_0']()) is False


def test_pump_storm_parity_00269():
    # sdk_Redirection_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Redirection_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Redirection_cause_value_0']())


def test_pump_admission_parity_00270():
    # sdk_RequestRangeNotSatisfiable_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_1']()) is False


def test_pump_storm_parity_00270():
    # sdk_RequestRangeNotSatisfiable_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_1']())


def test_pump_admission_parity_00271():
    # sdk_RequestRangeNotSatisfiable_cause_aborted_1
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_1']())
        is True
    )


def test_pump_storm_parity_00271():
    # sdk_RequestRangeNotSatisfiable_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_1']())


def test_pump_admission_parity_00272():
    # sdk_RequestRangeNotSatisfiable_cause_expired_1
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_1']())
        is True
    )


def test_pump_storm_parity_00272():
    # sdk_RequestRangeNotSatisfiable_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_1']())


def test_pump_admission_parity_00273():
    # sdk_RequestRangeNotSatisfiable_cause_timeout_1
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_1']())
        is False
    )


def test_pump_storm_parity_00273():
    # sdk_RequestRangeNotSatisfiable_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_1']())


def test_pump_admission_parity_00274():
    # sdk_RequestRangeNotSatisfiable_cause_value_1
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_1']())
        is False
    )


def test_pump_storm_parity_00274():
    # sdk_RequestRangeNotSatisfiable_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_1']())


def test_pump_admission_parity_00275():
    # sdk_RequestRangeNotSatisfiable_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_0']()) is False


def test_pump_storm_parity_00275():
    # sdk_RequestRangeNotSatisfiable_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_0']())


def test_pump_admission_parity_00276():
    # sdk_RequestRangeNotSatisfiable_cause_aborted_0
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_0']())
        is True
    )


def test_pump_storm_parity_00276():
    # sdk_RequestRangeNotSatisfiable_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_0']())


def test_pump_admission_parity_00277():
    # sdk_RequestRangeNotSatisfiable_cause_expired_0
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_0']())
        is True
    )


def test_pump_storm_parity_00277():
    # sdk_RequestRangeNotSatisfiable_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_0']())


def test_pump_admission_parity_00278():
    # sdk_RequestRangeNotSatisfiable_cause_timeout_0
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_0']())
        is False
    )


def test_pump_storm_parity_00278():
    # sdk_RequestRangeNotSatisfiable_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_0']())


def test_pump_admission_parity_00279():
    # sdk_RequestRangeNotSatisfiable_cause_value_0
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_0']())
        is False
    )


def test_pump_storm_parity_00279():
    # sdk_RequestRangeNotSatisfiable_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_0']())


def test_pump_admission_parity_00280():
    # sdk_ResourceExhausted_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_bare_1']()) is False


def test_pump_storm_parity_00280():
    # sdk_ResourceExhausted_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ResourceExhausted_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ResourceExhausted_bare_1']())


def test_pump_admission_parity_00281():
    # sdk_ResourceExhausted_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_1']()) is True


def test_pump_storm_parity_00281():
    # sdk_ResourceExhausted_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_1']())


def test_pump_admission_parity_00282():
    # sdk_ResourceExhausted_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_1']()) is True


def test_pump_storm_parity_00282():
    # sdk_ResourceExhausted_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_1']())


def test_pump_admission_parity_00283():
    # sdk_ResourceExhausted_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_1']()) is False


def test_pump_storm_parity_00283():
    # sdk_ResourceExhausted_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_1']())


def test_pump_admission_parity_00284():
    # sdk_ResourceExhausted_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_1']()) is False


def test_pump_storm_parity_00284():
    # sdk_ResourceExhausted_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_1']())


def test_pump_admission_parity_00285():
    # sdk_ResourceExhausted_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_bare_0']()) is False


def test_pump_storm_parity_00285():
    # sdk_ResourceExhausted_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ResourceExhausted_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ResourceExhausted_bare_0']())


def test_pump_admission_parity_00286():
    # sdk_ResourceExhausted_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_0']()) is True


def test_pump_storm_parity_00286():
    # sdk_ResourceExhausted_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_0']())


def test_pump_admission_parity_00287():
    # sdk_ResourceExhausted_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_0']()) is True


def test_pump_storm_parity_00287():
    # sdk_ResourceExhausted_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_0']())


def test_pump_admission_parity_00288():
    # sdk_ResourceExhausted_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_0']()) is False


def test_pump_storm_parity_00288():
    # sdk_ResourceExhausted_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_0']())


def test_pump_admission_parity_00289():
    # sdk_ResourceExhausted_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_0']()) is False


def test_pump_storm_parity_00289():
    # sdk_ResourceExhausted_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_0']())


def test_pump_admission_parity_00290():
    # sdk_ResumeIncomplete_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_1']()) is False


def test_pump_storm_parity_00290():
    # sdk_ResumeIncomplete_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_1']())


def test_pump_admission_parity_00291():
    # sdk_ResumeIncomplete_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_1']()) is True


def test_pump_storm_parity_00291():
    # sdk_ResumeIncomplete_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_1']())


def test_pump_admission_parity_00292():
    # sdk_ResumeIncomplete_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_1']()) is True


def test_pump_storm_parity_00292():
    # sdk_ResumeIncomplete_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_1']())


def test_pump_admission_parity_00293():
    # sdk_ResumeIncomplete_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_1']()) is False


def test_pump_storm_parity_00293():
    # sdk_ResumeIncomplete_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_1']())


def test_pump_admission_parity_00294():
    # sdk_ResumeIncomplete_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_1']()) is False


def test_pump_storm_parity_00294():
    # sdk_ResumeIncomplete_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_1']())


def test_pump_admission_parity_00295():
    # sdk_ResumeIncomplete_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_0']()) is False


def test_pump_storm_parity_00295():
    # sdk_ResumeIncomplete_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_0']())


def test_pump_admission_parity_00296():
    # sdk_ResumeIncomplete_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_0']()) is True


def test_pump_storm_parity_00296():
    # sdk_ResumeIncomplete_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_0']())


def test_pump_admission_parity_00297():
    # sdk_ResumeIncomplete_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_0']()) is True


def test_pump_storm_parity_00297():
    # sdk_ResumeIncomplete_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_0']())


def test_pump_admission_parity_00298():
    # sdk_ResumeIncomplete_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_0']()) is False


def test_pump_storm_parity_00298():
    # sdk_ResumeIncomplete_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_0']())


def test_pump_admission_parity_00299():
    # sdk_ResumeIncomplete_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_0']()) is False


def test_pump_storm_parity_00299():
    # sdk_ResumeIncomplete_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_0']())


def test_pump_admission_parity_00300():
    # sdk_ServerError_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_bare_1']()) is False


def test_pump_storm_parity_00300():
    # sdk_ServerError_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ServerError_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ServerError_bare_1']())


def test_pump_admission_parity_00301():
    # sdk_ServerError_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_cause_aborted_1']()) is True


def test_pump_storm_parity_00301():
    # sdk_ServerError_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ServerError_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ServerError_cause_aborted_1']())


def test_pump_admission_parity_00302():
    # sdk_ServerError_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_cause_expired_1']()) is True


def test_pump_storm_parity_00302():
    # sdk_ServerError_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ServerError_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ServerError_cause_expired_1']())


def test_pump_admission_parity_00303():
    # sdk_ServerError_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_cause_timeout_1']()) is False


def test_pump_storm_parity_00303():
    # sdk_ServerError_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ServerError_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ServerError_cause_timeout_1']())


def test_pump_admission_parity_00304():
    # sdk_ServerError_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_cause_value_1']()) is False


def test_pump_storm_parity_00304():
    # sdk_ServerError_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ServerError_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ServerError_cause_value_1']())


def test_pump_admission_parity_00305():
    # sdk_ServerError_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_bare_0']()) is False


def test_pump_storm_parity_00305():
    # sdk_ServerError_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ServerError_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ServerError_bare_0']())


def test_pump_admission_parity_00306():
    # sdk_ServerError_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_cause_aborted_0']()) is True


def test_pump_storm_parity_00306():
    # sdk_ServerError_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ServerError_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ServerError_cause_aborted_0']())


def test_pump_admission_parity_00307():
    # sdk_ServerError_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_cause_expired_0']()) is True


def test_pump_storm_parity_00307():
    # sdk_ServerError_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ServerError_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ServerError_cause_expired_0']())


def test_pump_admission_parity_00308():
    # sdk_ServerError_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_cause_timeout_0']()) is False


def test_pump_storm_parity_00308():
    # sdk_ServerError_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ServerError_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ServerError_cause_timeout_0']())


def test_pump_admission_parity_00309():
    # sdk_ServerError_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_cause_value_0']()) is False


def test_pump_storm_parity_00309():
    # sdk_ServerError_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ServerError_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ServerError_cause_value_0']())


def test_pump_admission_parity_00310():
    # sdk_ServiceUnavailable_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_1']()) is False


def test_pump_storm_parity_00310():
    # sdk_ServiceUnavailable_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_1']())


def test_pump_admission_parity_00311():
    # sdk_ServiceUnavailable_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_1']()) is True


def test_pump_storm_parity_00311():
    # sdk_ServiceUnavailable_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_1']())


def test_pump_admission_parity_00312():
    # sdk_ServiceUnavailable_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_1']()) is True


def test_pump_storm_parity_00312():
    # sdk_ServiceUnavailable_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_1']())


def test_pump_admission_parity_00313():
    # sdk_ServiceUnavailable_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_1']()) is False


def test_pump_storm_parity_00313():
    # sdk_ServiceUnavailable_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_1']())


def test_pump_admission_parity_00314():
    # sdk_ServiceUnavailable_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_1']()) is False


def test_pump_storm_parity_00314():
    # sdk_ServiceUnavailable_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_1']())


def test_pump_admission_parity_00315():
    # sdk_ServiceUnavailable_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_0']()) is False


def test_pump_storm_parity_00315():
    # sdk_ServiceUnavailable_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_0']())


def test_pump_admission_parity_00316():
    # sdk_ServiceUnavailable_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_0']()) is True


def test_pump_storm_parity_00316():
    # sdk_ServiceUnavailable_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_0']())


def test_pump_admission_parity_00317():
    # sdk_ServiceUnavailable_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_0']()) is True


def test_pump_storm_parity_00317():
    # sdk_ServiceUnavailable_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_0']())


def test_pump_admission_parity_00318():
    # sdk_ServiceUnavailable_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_0']()) is False


def test_pump_storm_parity_00318():
    # sdk_ServiceUnavailable_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_0']())


def test_pump_admission_parity_00319():
    # sdk_ServiceUnavailable_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_0']()) is False


def test_pump_storm_parity_00319():
    # sdk_ServiceUnavailable_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_0']())


def test_pump_admission_parity_00320():
    # sdk_TemporaryRedirect_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_1']()) is False


def test_pump_storm_parity_00320():
    # sdk_TemporaryRedirect_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_1']())


def test_pump_admission_parity_00321():
    # sdk_TemporaryRedirect_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_1']()) is True


def test_pump_storm_parity_00321():
    # sdk_TemporaryRedirect_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_1']())


def test_pump_admission_parity_00322():
    # sdk_TemporaryRedirect_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_1']()) is True


def test_pump_storm_parity_00322():
    # sdk_TemporaryRedirect_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_1']())


def test_pump_admission_parity_00323():
    # sdk_TemporaryRedirect_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_1']()) is False


def test_pump_storm_parity_00323():
    # sdk_TemporaryRedirect_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_1']())


def test_pump_admission_parity_00324():
    # sdk_TemporaryRedirect_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_1']()) is False


def test_pump_storm_parity_00324():
    # sdk_TemporaryRedirect_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_1']())


def test_pump_admission_parity_00325():
    # sdk_TemporaryRedirect_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_0']()) is False


def test_pump_storm_parity_00325():
    # sdk_TemporaryRedirect_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_0']())


def test_pump_admission_parity_00326():
    # sdk_TemporaryRedirect_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_0']()) is True


def test_pump_storm_parity_00326():
    # sdk_TemporaryRedirect_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_0']())


def test_pump_admission_parity_00327():
    # sdk_TemporaryRedirect_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_0']()) is True


def test_pump_storm_parity_00327():
    # sdk_TemporaryRedirect_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_0']())


def test_pump_admission_parity_00328():
    # sdk_TemporaryRedirect_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_0']()) is False


def test_pump_storm_parity_00328():
    # sdk_TemporaryRedirect_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_0']())


def test_pump_admission_parity_00329():
    # sdk_TemporaryRedirect_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_0']()) is False


def test_pump_storm_parity_00329():
    # sdk_TemporaryRedirect_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_0']())


def test_pump_admission_parity_00330():
    # sdk_TooManyRequests_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_bare_1']()) is False


def test_pump_storm_parity_00330():
    # sdk_TooManyRequests_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_TooManyRequests_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_TooManyRequests_bare_1']())


def test_pump_admission_parity_00331():
    # sdk_TooManyRequests_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_1']()) is True


def test_pump_storm_parity_00331():
    # sdk_TooManyRequests_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_1']())


def test_pump_admission_parity_00332():
    # sdk_TooManyRequests_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_1']()) is True


def test_pump_storm_parity_00332():
    # sdk_TooManyRequests_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_1']())


def test_pump_admission_parity_00333():
    # sdk_TooManyRequests_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_1']()) is False


def test_pump_storm_parity_00333():
    # sdk_TooManyRequests_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_1']())


def test_pump_admission_parity_00334():
    # sdk_TooManyRequests_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_1']()) is False


def test_pump_storm_parity_00334():
    # sdk_TooManyRequests_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_1']())


def test_pump_admission_parity_00335():
    # sdk_TooManyRequests_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_bare_0']()) is False


def test_pump_storm_parity_00335():
    # sdk_TooManyRequests_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_TooManyRequests_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_TooManyRequests_bare_0']())


def test_pump_admission_parity_00336():
    # sdk_TooManyRequests_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_0']()) is True


def test_pump_storm_parity_00336():
    # sdk_TooManyRequests_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_0']())


def test_pump_admission_parity_00337():
    # sdk_TooManyRequests_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_0']()) is True


def test_pump_storm_parity_00337():
    # sdk_TooManyRequests_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_0']())


def test_pump_admission_parity_00338():
    # sdk_TooManyRequests_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_0']()) is False


def test_pump_storm_parity_00338():
    # sdk_TooManyRequests_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_0']())


def test_pump_admission_parity_00339():
    # sdk_TooManyRequests_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_0']()) is False


def test_pump_storm_parity_00339():
    # sdk_TooManyRequests_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_0']())


def test_pump_admission_parity_00340():
    # sdk_Unauthenticated_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_bare_1']()) is False


def test_pump_storm_parity_00340():
    # sdk_Unauthenticated_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unauthenticated_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unauthenticated_bare_1']())


def test_pump_admission_parity_00341():
    # sdk_Unauthenticated_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_1']()) is True


def test_pump_storm_parity_00341():
    # sdk_Unauthenticated_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_1']())


def test_pump_admission_parity_00342():
    # sdk_Unauthenticated_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_1']()) is True


def test_pump_storm_parity_00342():
    # sdk_Unauthenticated_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_1']())


def test_pump_admission_parity_00343():
    # sdk_Unauthenticated_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_1']()) is False


def test_pump_storm_parity_00343():
    # sdk_Unauthenticated_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_1']())


def test_pump_admission_parity_00344():
    # sdk_Unauthenticated_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_1']()) is False


def test_pump_storm_parity_00344():
    # sdk_Unauthenticated_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_1']())


def test_pump_admission_parity_00345():
    # sdk_Unauthenticated_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_bare_0']()) is False


def test_pump_storm_parity_00345():
    # sdk_Unauthenticated_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unauthenticated_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unauthenticated_bare_0']())


def test_pump_admission_parity_00346():
    # sdk_Unauthenticated_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_0']()) is True


def test_pump_storm_parity_00346():
    # sdk_Unauthenticated_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_0']())


def test_pump_admission_parity_00347():
    # sdk_Unauthenticated_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_0']()) is True


def test_pump_storm_parity_00347():
    # sdk_Unauthenticated_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_0']())


def test_pump_admission_parity_00348():
    # sdk_Unauthenticated_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_0']()) is False


def test_pump_storm_parity_00348():
    # sdk_Unauthenticated_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_0']())


def test_pump_admission_parity_00349():
    # sdk_Unauthenticated_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_0']()) is False


def test_pump_storm_parity_00349():
    # sdk_Unauthenticated_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_0']())


def test_pump_admission_parity_00350():
    # sdk_Unauthorized_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_bare_1']()) is False


def test_pump_storm_parity_00350():
    # sdk_Unauthorized_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unauthorized_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unauthorized_bare_1']())


def test_pump_admission_parity_00351():
    # sdk_Unauthorized_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_1']()) is True


def test_pump_storm_parity_00351():
    # sdk_Unauthorized_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_1']())


def test_pump_admission_parity_00352():
    # sdk_Unauthorized_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_1']()) is True


def test_pump_storm_parity_00352():
    # sdk_Unauthorized_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_1']())


def test_pump_admission_parity_00353():
    # sdk_Unauthorized_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_1']()) is False


def test_pump_storm_parity_00353():
    # sdk_Unauthorized_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_1']())


def test_pump_admission_parity_00354():
    # sdk_Unauthorized_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_cause_value_1']()) is False


def test_pump_storm_parity_00354():
    # sdk_Unauthorized_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unauthorized_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unauthorized_cause_value_1']())


def test_pump_admission_parity_00355():
    # sdk_Unauthorized_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_bare_0']()) is False


def test_pump_storm_parity_00355():
    # sdk_Unauthorized_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unauthorized_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unauthorized_bare_0']())


def test_pump_admission_parity_00356():
    # sdk_Unauthorized_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_0']()) is True


def test_pump_storm_parity_00356():
    # sdk_Unauthorized_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_0']())


def test_pump_admission_parity_00357():
    # sdk_Unauthorized_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_0']()) is True


def test_pump_storm_parity_00357():
    # sdk_Unauthorized_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_0']())


def test_pump_admission_parity_00358():
    # sdk_Unauthorized_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_0']()) is False


def test_pump_storm_parity_00358():
    # sdk_Unauthorized_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_0']())


def test_pump_admission_parity_00359():
    # sdk_Unauthorized_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_cause_value_0']()) is False


def test_pump_storm_parity_00359():
    # sdk_Unauthorized_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unauthorized_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unauthorized_cause_value_0']())


def test_pump_admission_parity_00360():
    # sdk_Unknown_bare_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_bare_1']()) is False


def test_pump_storm_parity_00360():
    # sdk_Unknown_bare_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unknown_bare_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unknown_bare_1']())


def test_pump_admission_parity_00361():
    # sdk_Unknown_cause_aborted_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_cause_aborted_1']()) is True


def test_pump_storm_parity_00361():
    # sdk_Unknown_cause_aborted_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unknown_cause_aborted_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unknown_cause_aborted_1']())


def test_pump_admission_parity_00362():
    # sdk_Unknown_cause_expired_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_cause_expired_1']()) is True


def test_pump_storm_parity_00362():
    # sdk_Unknown_cause_expired_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unknown_cause_expired_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unknown_cause_expired_1']())


def test_pump_admission_parity_00363():
    # sdk_Unknown_cause_timeout_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_cause_timeout_1']()) is False


def test_pump_storm_parity_00363():
    # sdk_Unknown_cause_timeout_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unknown_cause_timeout_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unknown_cause_timeout_1']())


def test_pump_admission_parity_00364():
    # sdk_Unknown_cause_value_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_cause_value_1']()) is False


def test_pump_storm_parity_00364():
    # sdk_Unknown_cause_value_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unknown_cause_value_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unknown_cause_value_1']())


def test_pump_admission_parity_00365():
    # sdk_Unknown_bare_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_bare_0']()) is False


def test_pump_storm_parity_00365():
    # sdk_Unknown_bare_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unknown_bare_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unknown_bare_0']())


def test_pump_admission_parity_00366():
    # sdk_Unknown_cause_aborted_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_cause_aborted_0']()) is True


def test_pump_storm_parity_00366():
    # sdk_Unknown_cause_aborted_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unknown_cause_aborted_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unknown_cause_aborted_0']())


def test_pump_admission_parity_00367():
    # sdk_Unknown_cause_expired_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_cause_expired_0']()) is True


def test_pump_storm_parity_00367():
    # sdk_Unknown_cause_expired_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unknown_cause_expired_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unknown_cause_expired_0']())


def test_pump_admission_parity_00368():
    # sdk_Unknown_cause_timeout_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_cause_timeout_0']()) is False


def test_pump_storm_parity_00368():
    # sdk_Unknown_cause_timeout_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unknown_cause_timeout_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unknown_cause_timeout_0']())


def test_pump_admission_parity_00369():
    # sdk_Unknown_cause_value_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_cause_value_0']()) is False


def test_pump_storm_parity_00369():
    # sdk_Unknown_cause_value_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['sdk_Unknown_cause_value_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['sdk_Unknown_cause_value_0']())


def test_pump_admission_parity_00370():
    # custody_staged_audio
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_staged_audio']()) is False


def test_pump_storm_parity_00370():
    # custody_staged_audio
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_staged_audio']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_staged_audio']())


def test_pump_admission_parity_00371():
    # custody_staged_audio_cause_aborted
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_staged_audio_cause_aborted']()) is True


def test_pump_storm_parity_00371():
    # custody_staged_audio_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_staged_audio_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_staged_audio_cause_aborted']())


def test_pump_admission_parity_00372():
    # custody_staged_artifact
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_staged_artifact']()) is False


def test_pump_storm_parity_00372():
    # custody_staged_artifact
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_staged_artifact']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_staged_artifact']())


def test_pump_admission_parity_00373():
    # custody_staged_artifact_cause_aborted
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_staged_artifact_cause_aborted']()) is True


def test_pump_storm_parity_00373():
    # custody_staged_artifact_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_staged_artifact_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_staged_artifact_cause_aborted']())


def test_pump_admission_parity_00374():
    # custody_retained_audio
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_retained_audio']()) is False


def test_pump_storm_parity_00374():
    # custody_retained_audio
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_retained_audio']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_retained_audio']())


def test_pump_admission_parity_00375():
    # custody_retained_audio_cause_aborted
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_retained_audio_cause_aborted']()) is True


def test_pump_storm_parity_00375():
    # custody_retained_audio_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_retained_audio_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_retained_audio_cause_aborted']())


def test_pump_admission_parity_00376():
    # custody_retained_manifest
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_retained_manifest']()) is False


def test_pump_storm_parity_00376():
    # custody_retained_manifest
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_retained_manifest']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_retained_manifest']())


def test_pump_admission_parity_00377():
    # custody_retained_manifest_cause_aborted
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_retained_manifest_cause_aborted']()) is True


def test_pump_storm_parity_00377():
    # custody_retained_manifest_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_retained_manifest_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_retained_manifest_cause_aborted']())


def test_pump_admission_parity_00378():
    # custody_decoded_mismatch
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_decoded_mismatch']()) is False


def test_pump_storm_parity_00378():
    # custody_decoded_mismatch
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_decoded_mismatch']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_decoded_mismatch']())


def test_pump_admission_parity_00379():
    # custody_decoded_mismatch_cause_aborted
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_decoded_mismatch_cause_aborted']()) is True


def test_pump_storm_parity_00379():
    # custody_decoded_mismatch_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_decoded_mismatch_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_decoded_mismatch_cause_aborted']())


def test_pump_admission_parity_00380():
    # custody_permission
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_permission']()) is False


def test_pump_storm_parity_00380():
    # custody_permission
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_permission']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_permission']())


def test_pump_admission_parity_00381():
    # custody_permission_cause_aborted
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_permission_cause_aborted']()) is True


def test_pump_storm_parity_00381():
    # custody_permission_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_permission_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_permission_cause_aborted']())


def test_pump_admission_parity_00382():
    # custody_os_error
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_os_error']()) is False


def test_pump_storm_parity_00382():
    # custody_os_error
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_os_error']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_os_error']())


def test_pump_admission_parity_00383():
    # custody_os_error_cause_aborted
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_os_error_cause_aborted']()) is True


def test_pump_storm_parity_00383():
    # custody_os_error_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_os_error_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_os_error_cause_aborted']())


def test_pump_admission_parity_00384():
    # custody_runtime
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_runtime']()) is False


def test_pump_storm_parity_00384():
    # custody_runtime
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_runtime']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_runtime']())


def test_pump_admission_parity_00385():
    # custody_runtime_cause_aborted
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_runtime_cause_aborted']()) is True


def test_pump_storm_parity_00385():
    # custody_runtime_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_runtime_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_runtime_cause_aborted']())


def test_pump_admission_parity_00386():
    # custody_value_error
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_value_error']()) is False


def test_pump_storm_parity_00386():
    # custody_value_error
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_value_error']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_value_error']())


def test_pump_admission_parity_00387():
    # custody_value_error_cause_aborted
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_value_error_cause_aborted']()) is True


def test_pump_storm_parity_00387():
    # custody_value_error_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_value_error_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_value_error_cause_aborted']())


def test_pump_admission_parity_00388():
    # custody_key_error
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_key_error']()) is False


def test_pump_storm_parity_00388():
    # custody_key_error
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_key_error']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_key_error']())


def test_pump_admission_parity_00389():
    # custody_key_error_cause_aborted
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_key_error_cause_aborted']()) is True


def test_pump_storm_parity_00389():
    # custody_key_error_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_key_error_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_key_error_cause_aborted']())


def test_pump_admission_parity_00390():
    # custody_type_error
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_type_error']()) is False


def test_pump_storm_parity_00390():
    # custody_type_error
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_type_error']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_type_error']())


def test_pump_admission_parity_00391():
    # custody_type_error_cause_aborted
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_type_error_cause_aborted']()) is True


def test_pump_storm_parity_00391():
    # custody_type_error_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_type_error_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_type_error_cause_aborted']())


def test_pump_admission_parity_00392():
    # custody_index_error
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_index_error']()) is False


def test_pump_storm_parity_00392():
    # custody_index_error
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_index_error']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_index_error']())


def test_pump_admission_parity_00393():
    # custody_index_error_cause_aborted
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_index_error_cause_aborted']()) is True


def test_pump_storm_parity_00393():
    # custody_index_error_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_index_error_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_index_error_cause_aborted']())


def test_pump_admission_parity_00394():
    # custody_zero_div
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_zero_div']()) is False


def test_pump_storm_parity_00394():
    # custody_zero_div
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_zero_div']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_zero_div']())


def test_pump_admission_parity_00395():
    # custody_zero_div_cause_aborted
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_zero_div_cause_aborted']()) is True


def test_pump_storm_parity_00395():
    # custody_zero_div_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_zero_div_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_zero_div_cause_aborted']())


def test_pump_admission_parity_00396():
    # custody_arith
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_arith']()) is False


def test_pump_storm_parity_00396():
    # custody_arith
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_arith']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_arith']())


def test_pump_admission_parity_00397():
    # custody_arith_cause_aborted
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_arith_cause_aborted']()) is True


def test_pump_storm_parity_00397():
    # custody_arith_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_arith_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_arith_cause_aborted']())


def test_pump_admission_parity_00398():
    # custody_lookup
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_lookup']()) is False


def test_pump_storm_parity_00398():
    # custody_lookup
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_lookup']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_lookup']())


def test_pump_admission_parity_00399():
    # custody_lookup_cause_aborted
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_lookup_cause_aborted']()) is True


def test_pump_storm_parity_00399():
    # custody_lookup_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_lookup_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_lookup_cause_aborted']())


def test_pump_admission_parity_00400():
    # custody_notimpl
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_notimpl']()) is False


def test_pump_storm_parity_00400():
    # custody_notimpl
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_notimpl']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_notimpl']())


def test_pump_admission_parity_00401():
    # custody_notimpl_cause_aborted
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_notimpl_cause_aborted']()) is True


def test_pump_storm_parity_00401():
    # custody_notimpl_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_notimpl_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_notimpl_cause_aborted']())


def test_pump_admission_parity_00402():
    # custody_recursion
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_recursion']()) is False


def test_pump_storm_parity_00402():
    # custody_recursion
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_recursion']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_recursion']())


def test_pump_admission_parity_00403():
    # custody_recursion_cause_aborted
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_recursion_cause_aborted']()) is True


def test_pump_storm_parity_00403():
    # custody_recursion_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_recursion_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_recursion_cause_aborted']())


def test_pump_admission_parity_00404():
    # custody_eof
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_eof']()) is False


def test_pump_storm_parity_00404():
    # custody_eof
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_eof']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_eof']())


def test_pump_admission_parity_00405():
    # custody_eof_cause_aborted
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_eof_cause_aborted']()) is True


def test_pump_storm_parity_00405():
    # custody_eof_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_eof_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_eof_cause_aborted']())


def test_pump_admission_parity_00406():
    # custody_batch_validation_unsupported_language
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_unsupported_language']())
        is False
    )


def test_pump_storm_parity_00406():
    # custody_batch_validation_unsupported_language
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_batch_validation_unsupported_language']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_batch_validation_unsupported_language']())


def test_pump_admission_parity_00407():
    # custody_batch_validation_unsupported_language_cause_aborted
    assert (
        pump_mod.publication_loss_is_contention(
            _SHAPE_BUILDERS['custody_batch_validation_unsupported_language_cause_aborted']()
        )
        is True
    )


def test_pump_storm_parity_00407():
    # custody_batch_validation_unsupported_language_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_batch_validation_unsupported_language_cause_aborted']()
    ) == bp.persist_restrike_storm_after(
        _SHAPE_BUILDERS['custody_batch_validation_unsupported_language_cause_aborted']()
    )


def test_pump_admission_parity_00408():
    # custody_batch_validation_word_shape
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_word_shape']()) is False


def test_pump_storm_parity_00408():
    # custody_batch_validation_word_shape
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_batch_validation_word_shape']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_batch_validation_word_shape']())


def test_pump_admission_parity_00409():
    # custody_batch_validation_word_shape_cause_aborted
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_word_shape_cause_aborted']())
        is True
    )


def test_pump_storm_parity_00409():
    # custody_batch_validation_word_shape_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_batch_validation_word_shape_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_batch_validation_word_shape_cause_aborted']())


def test_pump_admission_parity_00410():
    # custody_batch_validation_word_clock
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_word_clock']()) is False


def test_pump_storm_parity_00410():
    # custody_batch_validation_word_clock
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_batch_validation_word_clock']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_batch_validation_word_clock']())


def test_pump_admission_parity_00411():
    # custody_batch_validation_word_clock_cause_aborted
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_word_clock_cause_aborted']())
        is True
    )


def test_pump_storm_parity_00411():
    # custody_batch_validation_word_clock_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_batch_validation_word_clock_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_batch_validation_word_clock_cause_aborted']())


def test_pump_admission_parity_00412():
    # custody_batch_validation_word_sequence
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_word_sequence']()) is False


def test_pump_storm_parity_00412():
    # custody_batch_validation_word_sequence
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_batch_validation_word_sequence']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_batch_validation_word_sequence']())


def test_pump_admission_parity_00413():
    # custody_batch_validation_word_sequence_cause_aborted
    assert (
        pump_mod.publication_loss_is_contention(
            _SHAPE_BUILDERS['custody_batch_validation_word_sequence_cause_aborted']()
        )
        is True
    )


def test_pump_storm_parity_00413():
    # custody_batch_validation_word_sequence_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_batch_validation_word_sequence_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_batch_validation_word_sequence_cause_aborted']())


def test_pump_admission_parity_00414():
    # custody_batch_validation_vad_nonfinite
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite']()) is False


def test_pump_storm_parity_00414():
    # custody_batch_validation_vad_nonfinite
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite']())


def test_pump_admission_parity_00415():
    # custody_batch_validation_vad_nonfinite_cause_aborted
    assert (
        pump_mod.publication_loss_is_contention(
            _SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite_cause_aborted']()
        )
        is True
    )


def test_pump_storm_parity_00415():
    # custody_batch_validation_vad_nonfinite_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite_cause_aborted']())


def test_pump_admission_parity_00416():
    # custody_batch_validation_vad_order
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_vad_order']()) is False


def test_pump_storm_parity_00416():
    # custody_batch_validation_vad_order
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_batch_validation_vad_order']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_batch_validation_vad_order']())


def test_pump_admission_parity_00417():
    # custody_batch_validation_vad_order_cause_aborted
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_vad_order_cause_aborted']())
        is True
    )


def test_pump_storm_parity_00417():
    # custody_batch_validation_vad_order_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_batch_validation_vad_order_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_batch_validation_vad_order_cause_aborted']())


def test_pump_admission_parity_00418():
    # custody_batch_validation_vad_bounds
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_vad_bounds']()) is False


def test_pump_storm_parity_00418():
    # custody_batch_validation_vad_bounds
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_batch_validation_vad_bounds']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_batch_validation_vad_bounds']())


def test_pump_admission_parity_00419():
    # custody_batch_validation_vad_bounds_cause_aborted
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_vad_bounds_cause_aborted']())
        is True
    )


def test_pump_storm_parity_00419():
    # custody_batch_validation_vad_bounds_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_batch_validation_vad_bounds_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_batch_validation_vad_bounds_cause_aborted']())


def test_pump_admission_parity_00420():
    # custody_batch_validation_empty_asr
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_empty_asr']()) is False


def test_pump_storm_parity_00420():
    # custody_batch_validation_empty_asr
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_batch_validation_empty_asr']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_batch_validation_empty_asr']())


def test_pump_admission_parity_00421():
    # custody_batch_validation_empty_asr_cause_aborted
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_empty_asr_cause_aborted']())
        is True
    )


def test_pump_storm_parity_00421():
    # custody_batch_validation_empty_asr_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_batch_validation_empty_asr_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_batch_validation_empty_asr_cause_aborted']())


def test_pump_admission_parity_00422():
    # custody_batch_validation_no_owned_words
    assert (
        pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_no_owned_words']()) is False
    )


def test_pump_storm_parity_00422():
    # custody_batch_validation_no_owned_words
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_batch_validation_no_owned_words']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_batch_validation_no_owned_words']())


def test_pump_admission_parity_00423():
    # custody_batch_validation_no_owned_words_cause_aborted
    assert (
        pump_mod.publication_loss_is_contention(
            _SHAPE_BUILDERS['custody_batch_validation_no_owned_words_cause_aborted']()
        )
        is True
    )


def test_pump_storm_parity_00423():
    # custody_batch_validation_no_owned_words_cause_aborted
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['custody_batch_validation_no_owned_words_cause_aborted']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['custody_batch_validation_no_owned_words_cause_aborted']())


def test_pump_admission_parity_00424():
    # timeout_family_6456
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['timeout_family_6456']()) is False


def test_pump_storm_parity_00424():
    # timeout_family_6456
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['timeout_family_6456']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['timeout_family_6456']())


def test_pump_admission_parity_00425():
    # timeout_family_9792
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['timeout_family_9792']()) is False


def test_pump_storm_parity_00425():
    # timeout_family_9792
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['timeout_family_9792']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['timeout_family_9792']())


def test_pump_admission_parity_00426():
    # timeout_family_400
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['timeout_family_400']()) is False


def test_pump_storm_parity_00426():
    # timeout_family_400
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['timeout_family_400']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['timeout_family_400']())


def test_pump_admission_parity_00427():
    # wrapper_attempts_exhausted_0_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_0_0']()) is True


def test_pump_storm_parity_00427():
    # wrapper_attempts_exhausted_0_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_attempts_exhausted_0_0']())


def test_pump_admission_parity_00428():
    # wrapper_attempts_exhausted_0_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_0_1']()) is True


def test_pump_storm_parity_00428():
    # wrapper_attempts_exhausted_0_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_attempts_exhausted_0_1']())


def test_pump_admission_parity_00429():
    # wrapper_attempts_exhausted_0_25
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_0_25']()) is True


def test_pump_storm_parity_00429():
    # wrapper_attempts_exhausted_0_25
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_25']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_attempts_exhausted_0_25']())


def test_pump_admission_parity_00430():
    # wrapper_attempts_exhausted_0_5
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_0_5']()) is True


def test_pump_storm_parity_00430():
    # wrapper_attempts_exhausted_0_5
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_5']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_attempts_exhausted_0_5']())


def test_pump_admission_parity_00431():
    # wrapper_attempts_exhausted_1_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_1_0']()) is True


def test_pump_storm_parity_00431():
    # wrapper_attempts_exhausted_1_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_attempts_exhausted_1_0']())


def test_pump_admission_parity_00432():
    # wrapper_attempts_exhausted_1_5
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_1_5']()) is True


def test_pump_storm_parity_00432():
    # wrapper_attempts_exhausted_1_5
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_5']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_attempts_exhausted_1_5']())


def test_pump_admission_parity_00433():
    # wrapper_attempts_exhausted_2_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_2_0']()) is True


def test_pump_storm_parity_00433():
    # wrapper_attempts_exhausted_2_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_attempts_exhausted_2_0']())


def test_pump_admission_parity_00434():
    # wrapper_attempts_exhausted_2_5
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_2_5']()) is True


def test_pump_storm_parity_00434():
    # wrapper_attempts_exhausted_2_5
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_5']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_attempts_exhausted_2_5']())


def test_pump_admission_parity_00435():
    # wrapper_attempts_exhausted_3_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_3_0']()) is True


def test_pump_storm_parity_00435():
    # wrapper_attempts_exhausted_3_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_attempts_exhausted_3_0']())


def test_pump_admission_parity_00436():
    # wrapper_attempts_exhausted_3_9
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_3_9']()) is True


def test_pump_storm_parity_00436():
    # wrapper_attempts_exhausted_3_9
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_9']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_attempts_exhausted_3_9']())


def test_pump_admission_parity_00437():
    # wrapper_attempts_exhausted_4_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_4_0']()) is True


def test_pump_storm_parity_00437():
    # wrapper_attempts_exhausted_4_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_attempts_exhausted_4_0']())


def test_pump_admission_parity_00438():
    # wrapper_attempts_exhausted_4_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_4_1']()) is True


def test_pump_storm_parity_00438():
    # wrapper_attempts_exhausted_4_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_attempts_exhausted_4_1']())


def test_pump_admission_parity_00439():
    # wrapper_attempts_exhausted_8_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_8_0']()) is True


def test_pump_storm_parity_00439():
    # wrapper_attempts_exhausted_8_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_attempts_exhausted_8_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_attempts_exhausted_8_0']())


def test_pump_admission_parity_00440():
    # wrapper_attempts_exhausted_50_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_50_0']()) is True


def test_pump_storm_parity_00440():
    # wrapper_attempts_exhausted_50_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_attempts_exhausted_50_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_attempts_exhausted_50_0']())


def test_pump_admission_parity_00441():
    # wrapper_attempts_exhausted_1000000000_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_1000000000_0']()) is True


def test_pump_storm_parity_00441():
    # wrapper_attempts_exhausted_1000000000_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_attempts_exhausted_1000000000_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_attempts_exhausted_1000000000_0']())


def test_pump_admission_parity_00442():
    # wrapper_deadline_exhausted_0_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_0_0']()) is True


def test_pump_storm_parity_00442():
    # wrapper_deadline_exhausted_0_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_deadline_exhausted_0_0']())


def test_pump_admission_parity_00443():
    # wrapper_deadline_exhausted_0_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_0_1']()) is True


def test_pump_storm_parity_00443():
    # wrapper_deadline_exhausted_0_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_deadline_exhausted_0_1']())


def test_pump_admission_parity_00444():
    # wrapper_deadline_exhausted_0_25
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_0_25']()) is True


def test_pump_storm_parity_00444():
    # wrapper_deadline_exhausted_0_25
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_25']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_deadline_exhausted_0_25']())


def test_pump_admission_parity_00445():
    # wrapper_deadline_exhausted_0_5
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_0_5']()) is True


def test_pump_storm_parity_00445():
    # wrapper_deadline_exhausted_0_5
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_5']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_deadline_exhausted_0_5']())


def test_pump_admission_parity_00446():
    # wrapper_deadline_exhausted_1_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_1_0']()) is True


def test_pump_storm_parity_00446():
    # wrapper_deadline_exhausted_1_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_deadline_exhausted_1_0']())


def test_pump_admission_parity_00447():
    # wrapper_deadline_exhausted_1_5
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_1_5']()) is True


def test_pump_storm_parity_00447():
    # wrapper_deadline_exhausted_1_5
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_5']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_deadline_exhausted_1_5']())


def test_pump_admission_parity_00448():
    # wrapper_deadline_exhausted_2_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_2_0']()) is True


def test_pump_storm_parity_00448():
    # wrapper_deadline_exhausted_2_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_deadline_exhausted_2_0']())


def test_pump_admission_parity_00449():
    # wrapper_deadline_exhausted_2_5
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_2_5']()) is True


def test_pump_storm_parity_00449():
    # wrapper_deadline_exhausted_2_5
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_5']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_deadline_exhausted_2_5']())


def test_pump_admission_parity_00450():
    # wrapper_deadline_exhausted_3_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_3_0']()) is True


def test_pump_storm_parity_00450():
    # wrapper_deadline_exhausted_3_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_deadline_exhausted_3_0']())


def test_pump_admission_parity_00451():
    # wrapper_deadline_exhausted_3_9
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_3_9']()) is True


def test_pump_storm_parity_00451():
    # wrapper_deadline_exhausted_3_9
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_9']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_deadline_exhausted_3_9']())


def test_pump_admission_parity_00452():
    # wrapper_deadline_exhausted_4_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_4_0']()) is True


def test_pump_storm_parity_00452():
    # wrapper_deadline_exhausted_4_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_deadline_exhausted_4_0']())


def test_pump_admission_parity_00453():
    # wrapper_deadline_exhausted_4_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_4_1']()) is True


def test_pump_storm_parity_00453():
    # wrapper_deadline_exhausted_4_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_deadline_exhausted_4_1']())


def test_pump_admission_parity_00454():
    # wrapper_deadline_exhausted_8_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_8_0']()) is True


def test_pump_storm_parity_00454():
    # wrapper_deadline_exhausted_8_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_deadline_exhausted_8_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_deadline_exhausted_8_0']())


def test_pump_admission_parity_00455():
    # wrapper_deadline_exhausted_50_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_50_0']()) is True


def test_pump_storm_parity_00455():
    # wrapper_deadline_exhausted_50_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_deadline_exhausted_50_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_deadline_exhausted_50_0']())


def test_pump_admission_parity_00456():
    # wrapper_deadline_exhausted_1000000000_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_1000000000_0']()) is True


def test_pump_storm_parity_00456():
    # wrapper_deadline_exhausted_1000000000_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['wrapper_deadline_exhausted_1000000000_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['wrapper_deadline_exhausted_1000000000_0']())


def test_pump_admission_parity_00457():
    # carrier_ns_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_0']()) is False


def test_pump_storm_parity_00457():
    # carrier_ns_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_ns_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_ns_0']())


def test_pump_admission_parity_00458():
    # carrier_err_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_err_0']()) is False


def test_pump_storm_parity_00458():
    # carrier_err_0
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_err_0']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_err_0']())


def test_pump_admission_parity_00459():
    # carrier_ns_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_1']()) is False


def test_pump_storm_parity_00459():
    # carrier_ns_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_ns_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_ns_1']())


def test_pump_admission_parity_00460():
    # carrier_err_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_err_1']()) is False


def test_pump_storm_parity_00460():
    # carrier_err_1
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_err_1']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_err_1']())


def test_pump_admission_parity_00461():
    # carrier_ns_2
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_2']()) is False


def test_pump_storm_parity_00461():
    # carrier_ns_2
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_ns_2']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_ns_2']())


def test_pump_admission_parity_00462():
    # carrier_err_2
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_err_2']()) is False


def test_pump_storm_parity_00462():
    # carrier_err_2
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_err_2']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_err_2']())


def test_pump_admission_parity_00463():
    # carrier_ns_3
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_3']()) is False


def test_pump_storm_parity_00463():
    # carrier_ns_3
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_ns_3']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_ns_3']())


def test_pump_admission_parity_00464():
    # carrier_err_3
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_err_3']()) is False


def test_pump_storm_parity_00464():
    # carrier_err_3
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_err_3']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_err_3']())


def test_pump_admission_parity_00465():
    # carrier_ns_4
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_4']()) is False


def test_pump_storm_parity_00465():
    # carrier_ns_4
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_ns_4']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_ns_4']())


def test_pump_admission_parity_00466():
    # carrier_err_4
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_err_4']()) is False


def test_pump_storm_parity_00466():
    # carrier_err_4
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_err_4']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_err_4']())


def test_pump_admission_parity_00467():
    # carrier_ns_5
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_5']()) is False


def test_pump_storm_parity_00467():
    # carrier_ns_5
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_ns_5']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_ns_5']())


def test_pump_admission_parity_00468():
    # carrier_err_5
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_err_5']()) is False


def test_pump_storm_parity_00468():
    # carrier_err_5
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_err_5']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_err_5']())


def test_pump_admission_parity_00469():
    # carrier_ns_6
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_6']()) is False


def test_pump_storm_parity_00469():
    # carrier_ns_6
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_ns_6']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_ns_6']())


def test_pump_admission_parity_00470():
    # carrier_err_6
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_err_6']()) is False


def test_pump_storm_parity_00470():
    # carrier_err_6
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_err_6']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_err_6']())


def test_pump_admission_parity_00471():
    # carrier_ns_7
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_7']()) is False


def test_pump_storm_parity_00471():
    # carrier_ns_7
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_ns_7']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_ns_7']())


def test_pump_admission_parity_00472():
    # carrier_err_7
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_err_7']()) is False


def test_pump_storm_parity_00472():
    # carrier_err_7
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_err_7']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_err_7']())


def test_pump_admission_parity_00473():
    # carrier_ns_8
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_8']()) is False


def test_pump_storm_parity_00473():
    # carrier_ns_8
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_ns_8']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_ns_8']())


def test_pump_admission_parity_00474():
    # carrier_err_8
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_err_8']()) is False


def test_pump_storm_parity_00474():
    # carrier_err_8
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_err_8']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_err_8']())


def test_pump_admission_parity_00475():
    # carrier_ns_9
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_9']()) is False


def test_pump_storm_parity_00475():
    # carrier_ns_9
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_ns_9']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_ns_9']())


def test_pump_admission_parity_00476():
    # carrier_err_9
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_err_9']()) is False


def test_pump_storm_parity_00476():
    # carrier_err_9
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_err_9']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_err_9']())


def test_pump_admission_parity_00477():
    # carrier_ns_10
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_10']()) is False


def test_pump_storm_parity_00477():
    # carrier_ns_10
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_ns_10']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_ns_10']())


def test_pump_admission_parity_00478():
    # carrier_err_10
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_err_10']()) is False


def test_pump_storm_parity_00478():
    # carrier_err_10
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_err_10']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_err_10']())


def test_pump_admission_parity_00479():
    # carrier_ns_11
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_11']()) is False


def test_pump_storm_parity_00479():
    # carrier_ns_11
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_ns_11']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_ns_11']())


def test_pump_admission_parity_00480():
    # carrier_err_11
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_err_11']()) is False


def test_pump_storm_parity_00480():
    # carrier_err_11
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_err_11']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_err_11']())


def test_pump_admission_parity_00481():
    # carrier_ns_12
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_12']()) is False


def test_pump_storm_parity_00481():
    # carrier_ns_12
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_ns_12']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_ns_12']())


def test_pump_admission_parity_00482():
    # carrier_err_12
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_err_12']()) is False


def test_pump_storm_parity_00482():
    # carrier_err_12
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_err_12']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_err_12']())


def test_pump_admission_parity_00483():
    # carrier_ns_13
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_13']()) is False


def test_pump_storm_parity_00483():
    # carrier_ns_13
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_ns_13']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_ns_13']())


def test_pump_admission_parity_00484():
    # carrier_err_13
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_err_13']()) is False


def test_pump_storm_parity_00484():
    # carrier_err_13
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_err_13']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_err_13']())


def test_pump_admission_parity_00485():
    # carrier_ns_14
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_14']()) is False


def test_pump_storm_parity_00485():
    # carrier_ns_14
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_ns_14']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_ns_14']())


def test_pump_admission_parity_00486():
    # carrier_err_14
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_err_14']()) is False


def test_pump_storm_parity_00486():
    # carrier_err_14
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_err_14']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_err_14']())


def test_pump_admission_parity_00487():
    # carrier_ns_15
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_15']()) is False


def test_pump_storm_parity_00487():
    # carrier_ns_15
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_ns_15']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_ns_15']())


def test_pump_admission_parity_00488():
    # carrier_err_15
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_err_15']()) is False


def test_pump_storm_parity_00488():
    # carrier_err_15
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_err_15']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_err_15']())


def test_pump_admission_parity_00489():
    # carrier_ns_16
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_16']()) is False


def test_pump_storm_parity_00489():
    # carrier_ns_16
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_ns_16']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_ns_16']())


def test_pump_admission_parity_00490():
    # carrier_err_16
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_err_16']()) is False


def test_pump_storm_parity_00490():
    # carrier_err_16
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_err_16']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_err_16']())


def test_pump_admission_parity_00491():
    # carrier_ns_17
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_17']()) is False


def test_pump_storm_parity_00491():
    # carrier_ns_17
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_ns_17']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_ns_17']())


def test_pump_admission_parity_00492():
    # carrier_err_17
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_err_17']()) is False


def test_pump_storm_parity_00492():
    # carrier_err_17
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_err_17']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_err_17']())


def test_pump_admission_parity_00493():
    # carrier_ns_18
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_18']()) is False


def test_pump_storm_parity_00493():
    # carrier_ns_18
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_ns_18']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_ns_18']())


def test_pump_admission_parity_00494():
    # carrier_err_18
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_err_18']()) is False


def test_pump_storm_parity_00494():
    # carrier_err_18
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_err_18']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_err_18']())


def test_pump_admission_parity_00495():
    # carrier_ns_19
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_19']()) is False


def test_pump_storm_parity_00495():
    # carrier_ns_19
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_ns_19']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_ns_19']())


def test_pump_admission_parity_00496():
    # carrier_err_19
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_err_19']()) is False


def test_pump_storm_parity_00496():
    # carrier_err_19
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_err_19']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_err_19']())


def test_pump_admission_parity_00497():
    # carrier_ns_20
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_20']()) is False


def test_pump_storm_parity_00497():
    # carrier_ns_20
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_ns_20']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_ns_20']())


def test_pump_admission_parity_00498():
    # carrier_err_20
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['carrier_err_20']()) is False


def test_pump_storm_parity_00498():
    # carrier_err_20
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['carrier_err_20']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['carrier_err_20']())


def test_pump_admission_parity_00499():
    # hostile_0
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['hostile_0']()) is False


def test_pump_storm_parity_00499():
    # hostile_0
    assert pump_mod.publication_restrike_storm_after(_SHAPE_BUILDERS['hostile_0']()) == bp.persist_restrike_storm_after(
        _SHAPE_BUILDERS['hostile_0']()
    )


def test_pump_admission_parity_00500():
    # hostile_1
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['hostile_1']()) is False


def test_pump_storm_parity_00500():
    # hostile_1
    assert pump_mod.publication_restrike_storm_after(_SHAPE_BUILDERS['hostile_1']()) == bp.persist_restrike_storm_after(
        _SHAPE_BUILDERS['hostile_1']()
    )


def test_pump_admission_parity_00501():
    # hostile_2
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['hostile_2']()) is False


def test_pump_storm_parity_00501():
    # hostile_2
    assert pump_mod.publication_restrike_storm_after(_SHAPE_BUILDERS['hostile_2']()) == bp.persist_restrike_storm_after(
        _SHAPE_BUILDERS['hostile_2']()
    )


def test_pump_admission_parity_00502():
    # hostile_3
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['hostile_3']()) is False


def test_pump_storm_parity_00502():
    # hostile_3
    assert pump_mod.publication_restrike_storm_after(_SHAPE_BUILDERS['hostile_3']()) == bp.persist_restrike_storm_after(
        _SHAPE_BUILDERS['hostile_3']()
    )


def test_pump_admission_parity_00503():
    # hostile_4
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['hostile_4']()) is False


def test_pump_storm_parity_00503():
    # hostile_4
    assert pump_mod.publication_restrike_storm_after(_SHAPE_BUILDERS['hostile_4']()) == bp.persist_restrike_storm_after(
        _SHAPE_BUILDERS['hostile_4']()
    )


def test_pump_admission_parity_00504():
    # hostile_5
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['hostile_5']()) is False


def test_pump_storm_parity_00504():
    # hostile_5
    assert pump_mod.publication_restrike_storm_after(_SHAPE_BUILDERS['hostile_5']()) == bp.persist_restrike_storm_after(
        _SHAPE_BUILDERS['hostile_5']()
    )


def test_pump_admission_parity_00505():
    # hostile_6
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['hostile_6']()) is False


def test_pump_storm_parity_00505():
    # hostile_6
    assert pump_mod.publication_restrike_storm_after(_SHAPE_BUILDERS['hostile_6']()) == bp.persist_restrike_storm_after(
        _SHAPE_BUILDERS['hostile_6']()
    )


def test_pump_admission_parity_00506():
    # hostile_7
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['hostile_7']()) is False


def test_pump_storm_parity_00506():
    # hostile_7
    assert pump_mod.publication_restrike_storm_after(_SHAPE_BUILDERS['hostile_7']()) == bp.persist_restrike_storm_after(
        _SHAPE_BUILDERS['hostile_7']()
    )


def test_pump_admission_parity_00507():
    # hostile_8
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['hostile_8']()) is False


def test_pump_storm_parity_00507():
    # hostile_8
    assert pump_mod.publication_restrike_storm_after(_SHAPE_BUILDERS['hostile_8']()) == bp.persist_restrike_storm_after(
        _SHAPE_BUILDERS['hostile_8']()
    )


def test_pump_admission_parity_00508():
    # hostile_9
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['hostile_9']()) is False


def test_pump_storm_parity_00508():
    # hostile_9
    assert pump_mod.publication_restrike_storm_after(_SHAPE_BUILDERS['hostile_9']()) == bp.persist_restrike_storm_after(
        _SHAPE_BUILDERS['hostile_9']()
    )


def test_pump_admission_parity_00509():
    # hostile_10
    assert pump_mod.publication_loss_is_contention(_SHAPE_BUILDERS['hostile_10']()) is False


def test_pump_storm_parity_00509():
    # hostile_10
    assert pump_mod.publication_restrike_storm_after(
        _SHAPE_BUILDERS['hostile_10']()
    ) == bp.persist_restrike_storm_after(_SHAPE_BUILDERS['hostile_10']())
