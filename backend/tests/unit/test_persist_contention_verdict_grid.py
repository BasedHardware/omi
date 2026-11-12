#!/usr/bin/env python3
"""Per-shape classification verdict grid for the persist boundary loss arms.

Every cell freezes one verdict of the persist boundary loss lanes over one
inventoried fault shape. Expected values are literals cross-verified at emit
time against an independent transcription of the lane doctrine; a failing
cell means the boundary verdict drifted from the documented family contract.

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


def test_contention_00000():
    # sdk_Aborted_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_bare_1']()) is True


def test_transport_00000():
    # sdk_Aborted_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Aborted_bare_1']()) is True


def test_admitted_00000():
    # sdk_Aborted_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Aborted_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_bare_1']())
    ) is True


def test_contention_00001():
    # sdk_Aborted_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_cause_aborted_1']()) is True


def test_transport_00001():
    # sdk_Aborted_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Aborted_cause_aborted_1']()) is True


def test_admitted_00001():
    # sdk_Aborted_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Aborted_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_cause_aborted_1']())
    ) is True


def test_contention_00002():
    # sdk_Aborted_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_cause_expired_1']()) is True


def test_transport_00002():
    # sdk_Aborted_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Aborted_cause_expired_1']()) is True


def test_admitted_00002():
    # sdk_Aborted_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Aborted_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_cause_expired_1']())
    ) is True


def test_contention_00003():
    # sdk_Aborted_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_cause_timeout_1']()) is True


def test_transport_00003():
    # sdk_Aborted_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Aborted_cause_timeout_1']()) is True


def test_admitted_00003():
    # sdk_Aborted_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Aborted_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_cause_timeout_1']())
    ) is True


def test_contention_00004():
    # sdk_Aborted_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_cause_value_1']()) is True


def test_transport_00004():
    # sdk_Aborted_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Aborted_cause_value_1']()) is True


def test_admitted_00004():
    # sdk_Aborted_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Aborted_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_cause_value_1']())
    ) is True


def test_contention_00005():
    # sdk_Aborted_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_bare_0']()) is True


def test_transport_00005():
    # sdk_Aborted_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Aborted_bare_0']()) is True


def test_admitted_00005():
    # sdk_Aborted_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Aborted_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_bare_0']())
    ) is True


def test_contention_00006():
    # sdk_Aborted_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_cause_aborted_0']()) is True


def test_transport_00006():
    # sdk_Aborted_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Aborted_cause_aborted_0']()) is True


def test_admitted_00006():
    # sdk_Aborted_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Aborted_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_cause_aborted_0']())
    ) is True


def test_contention_00007():
    # sdk_Aborted_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_cause_expired_0']()) is True


def test_transport_00007():
    # sdk_Aborted_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Aborted_cause_expired_0']()) is True


def test_admitted_00007():
    # sdk_Aborted_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Aborted_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_cause_expired_0']())
    ) is True


def test_contention_00008():
    # sdk_Aborted_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_cause_timeout_0']()) is True


def test_transport_00008():
    # sdk_Aborted_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Aborted_cause_timeout_0']()) is True


def test_admitted_00008():
    # sdk_Aborted_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Aborted_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_cause_timeout_0']())
    ) is True


def test_contention_00009():
    # sdk_Aborted_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_cause_value_0']()) is True


def test_transport_00009():
    # sdk_Aborted_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Aborted_cause_value_0']()) is True


def test_admitted_00009():
    # sdk_Aborted_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Aborted_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Aborted_cause_value_0']())
    ) is True


def test_contention_00010():
    # sdk_AlreadyExists_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_bare_1']()) is False


def test_transport_00010():
    # sdk_AlreadyExists_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_AlreadyExists_bare_1']()) is True


def test_admitted_00010():
    # sdk_AlreadyExists_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_AlreadyExists_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_bare_1']())
    ) is True


def test_contention_00011():
    # sdk_AlreadyExists_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_1']()) is True


def test_transport_00011():
    # sdk_AlreadyExists_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_1']()) is True


def test_admitted_00011():
    # sdk_AlreadyExists_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_1']())
    ) is True


def test_contention_00012():
    # sdk_AlreadyExists_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_1']()) is True


def test_transport_00012():
    # sdk_AlreadyExists_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_1']()) is True


def test_admitted_00012():
    # sdk_AlreadyExists_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_1']())
    ) is True


def test_contention_00013():
    # sdk_AlreadyExists_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_1']()) is False


def test_transport_00013():
    # sdk_AlreadyExists_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_1']()) is True


def test_admitted_00013():
    # sdk_AlreadyExists_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_1']())
    ) is True


def test_contention_00014():
    # sdk_AlreadyExists_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_1']()) is False


def test_transport_00014():
    # sdk_AlreadyExists_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_1']()) is True


def test_admitted_00014():
    # sdk_AlreadyExists_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_1']())
    ) is True


def test_contention_00015():
    # sdk_AlreadyExists_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_bare_0']()) is False


def test_transport_00015():
    # sdk_AlreadyExists_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_AlreadyExists_bare_0']()) is True


def test_admitted_00015():
    # sdk_AlreadyExists_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_AlreadyExists_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_bare_0']())
    ) is True


def test_contention_00016():
    # sdk_AlreadyExists_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_0']()) is True


def test_transport_00016():
    # sdk_AlreadyExists_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_0']()) is True


def test_admitted_00016():
    # sdk_AlreadyExists_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_0']())
    ) is True


def test_contention_00017():
    # sdk_AlreadyExists_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_0']()) is True


def test_transport_00017():
    # sdk_AlreadyExists_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_0']()) is True


def test_admitted_00017():
    # sdk_AlreadyExists_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_0']())
    ) is True


def test_contention_00018():
    # sdk_AlreadyExists_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_0']()) is False


def test_transport_00018():
    # sdk_AlreadyExists_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_0']()) is True


def test_admitted_00018():
    # sdk_AlreadyExists_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_0']())
    ) is True


def test_contention_00019():
    # sdk_AlreadyExists_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_0']()) is False


def test_transport_00019():
    # sdk_AlreadyExists_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_0']()) is True


def test_admitted_00019():
    # sdk_AlreadyExists_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_0']())
    ) is True


def test_contention_00020():
    # sdk_BadGateway_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_bare_1']()) is False


def test_transport_00020():
    # sdk_BadGateway_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadGateway_bare_1']()) is True


def test_admitted_00020():
    # sdk_BadGateway_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadGateway_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_bare_1']())
    ) is True


def test_contention_00021():
    # sdk_BadGateway_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_1']()) is True


def test_transport_00021():
    # sdk_BadGateway_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_1']()) is True


def test_admitted_00021():
    # sdk_BadGateway_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_1']())
    ) is True


def test_contention_00022():
    # sdk_BadGateway_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_cause_expired_1']()) is True


def test_transport_00022():
    # sdk_BadGateway_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadGateway_cause_expired_1']()) is True


def test_admitted_00022():
    # sdk_BadGateway_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadGateway_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_cause_expired_1']())
    ) is True


def test_contention_00023():
    # sdk_BadGateway_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_1']()) is False


def test_transport_00023():
    # sdk_BadGateway_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_1']()) is True


def test_admitted_00023():
    # sdk_BadGateway_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_1']())
    ) is True


def test_contention_00024():
    # sdk_BadGateway_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_cause_value_1']()) is False


def test_transport_00024():
    # sdk_BadGateway_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadGateway_cause_value_1']()) is True


def test_admitted_00024():
    # sdk_BadGateway_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadGateway_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_cause_value_1']())
    ) is True


def test_contention_00025():
    # sdk_BadGateway_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_bare_0']()) is False


def test_transport_00025():
    # sdk_BadGateway_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadGateway_bare_0']()) is True


def test_admitted_00025():
    # sdk_BadGateway_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadGateway_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_bare_0']())
    ) is True


def test_contention_00026():
    # sdk_BadGateway_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_0']()) is True


def test_transport_00026():
    # sdk_BadGateway_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_0']()) is True


def test_admitted_00026():
    # sdk_BadGateway_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_0']())
    ) is True


def test_contention_00027():
    # sdk_BadGateway_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_cause_expired_0']()) is True


def test_transport_00027():
    # sdk_BadGateway_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadGateway_cause_expired_0']()) is True


def test_admitted_00027():
    # sdk_BadGateway_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadGateway_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_cause_expired_0']())
    ) is True


def test_contention_00028():
    # sdk_BadGateway_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_0']()) is False


def test_transport_00028():
    # sdk_BadGateway_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_0']()) is True


def test_admitted_00028():
    # sdk_BadGateway_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_0']())
    ) is True


def test_contention_00029():
    # sdk_BadGateway_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_cause_value_0']()) is False


def test_transport_00029():
    # sdk_BadGateway_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadGateway_cause_value_0']()) is True


def test_admitted_00029():
    # sdk_BadGateway_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadGateway_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadGateway_cause_value_0']())
    ) is True


def test_contention_00030():
    # sdk_BadRequest_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_bare_1']()) is False


def test_transport_00030():
    # sdk_BadRequest_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadRequest_bare_1']()) is True


def test_admitted_00030():
    # sdk_BadRequest_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadRequest_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_bare_1']())
    ) is True


def test_contention_00031():
    # sdk_BadRequest_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_1']()) is True


def test_transport_00031():
    # sdk_BadRequest_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_1']()) is True


def test_admitted_00031():
    # sdk_BadRequest_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_1']())
    ) is True


def test_contention_00032():
    # sdk_BadRequest_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_cause_expired_1']()) is True


def test_transport_00032():
    # sdk_BadRequest_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadRequest_cause_expired_1']()) is True


def test_admitted_00032():
    # sdk_BadRequest_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadRequest_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_cause_expired_1']())
    ) is True


def test_contention_00033():
    # sdk_BadRequest_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_1']()) is False


def test_transport_00033():
    # sdk_BadRequest_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_1']()) is True


def test_admitted_00033():
    # sdk_BadRequest_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_1']())
    ) is True


def test_contention_00034():
    # sdk_BadRequest_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_cause_value_1']()) is False


def test_transport_00034():
    # sdk_BadRequest_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadRequest_cause_value_1']()) is True


def test_admitted_00034():
    # sdk_BadRequest_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadRequest_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_cause_value_1']())
    ) is True


def test_contention_00035():
    # sdk_BadRequest_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_bare_0']()) is False


def test_transport_00035():
    # sdk_BadRequest_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadRequest_bare_0']()) is True


def test_admitted_00035():
    # sdk_BadRequest_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadRequest_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_bare_0']())
    ) is True


def test_contention_00036():
    # sdk_BadRequest_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_0']()) is True


def test_transport_00036():
    # sdk_BadRequest_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_0']()) is True


def test_admitted_00036():
    # sdk_BadRequest_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_0']())
    ) is True


def test_contention_00037():
    # sdk_BadRequest_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_cause_expired_0']()) is True


def test_transport_00037():
    # sdk_BadRequest_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadRequest_cause_expired_0']()) is True


def test_admitted_00037():
    # sdk_BadRequest_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadRequest_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_cause_expired_0']())
    ) is True


def test_contention_00038():
    # sdk_BadRequest_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_0']()) is False


def test_transport_00038():
    # sdk_BadRequest_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_0']()) is True


def test_admitted_00038():
    # sdk_BadRequest_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_0']())
    ) is True


def test_contention_00039():
    # sdk_BadRequest_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_cause_value_0']()) is False


def test_transport_00039():
    # sdk_BadRequest_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadRequest_cause_value_0']()) is True


def test_admitted_00039():
    # sdk_BadRequest_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_BadRequest_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_BadRequest_cause_value_0']())
    ) is True


def test_contention_00040():
    # sdk_Cancelled_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_bare_1']()) is False


def test_transport_00040():
    # sdk_Cancelled_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Cancelled_bare_1']()) is True


def test_admitted_00040():
    # sdk_Cancelled_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Cancelled_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_bare_1']())
    ) is True


def test_contention_00041():
    # sdk_Cancelled_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_1']()) is True


def test_transport_00041():
    # sdk_Cancelled_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_1']()) is True


def test_admitted_00041():
    # sdk_Cancelled_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_1']())
    ) is True


def test_contention_00042():
    # sdk_Cancelled_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_cause_expired_1']()) is True


def test_transport_00042():
    # sdk_Cancelled_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Cancelled_cause_expired_1']()) is True


def test_admitted_00042():
    # sdk_Cancelled_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Cancelled_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_cause_expired_1']())
    ) is True


def test_contention_00043():
    # sdk_Cancelled_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_1']()) is False


def test_transport_00043():
    # sdk_Cancelled_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_1']()) is True


def test_admitted_00043():
    # sdk_Cancelled_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_1']())
    ) is True


def test_contention_00044():
    # sdk_Cancelled_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_cause_value_1']()) is False


def test_transport_00044():
    # sdk_Cancelled_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Cancelled_cause_value_1']()) is True


def test_admitted_00044():
    # sdk_Cancelled_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Cancelled_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_cause_value_1']())
    ) is True


def test_contention_00045():
    # sdk_Cancelled_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_bare_0']()) is False


def test_transport_00045():
    # sdk_Cancelled_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Cancelled_bare_0']()) is True


def test_admitted_00045():
    # sdk_Cancelled_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Cancelled_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_bare_0']())
    ) is True


def test_contention_00046():
    # sdk_Cancelled_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_0']()) is True


def test_transport_00046():
    # sdk_Cancelled_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_0']()) is True


def test_admitted_00046():
    # sdk_Cancelled_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_0']())
    ) is True


def test_contention_00047():
    # sdk_Cancelled_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_cause_expired_0']()) is True


def test_transport_00047():
    # sdk_Cancelled_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Cancelled_cause_expired_0']()) is True


def test_admitted_00047():
    # sdk_Cancelled_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Cancelled_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_cause_expired_0']())
    ) is True


def test_contention_00048():
    # sdk_Cancelled_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_0']()) is False


def test_transport_00048():
    # sdk_Cancelled_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_0']()) is True


def test_admitted_00048():
    # sdk_Cancelled_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_0']())
    ) is True


def test_contention_00049():
    # sdk_Cancelled_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_cause_value_0']()) is False


def test_transport_00049():
    # sdk_Cancelled_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Cancelled_cause_value_0']()) is True


def test_admitted_00049():
    # sdk_Cancelled_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Cancelled_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Cancelled_cause_value_0']())
    ) is True


def test_contention_00050():
    # sdk_ClientError_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_bare_1']()) is False


def test_transport_00050():
    # sdk_ClientError_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ClientError_bare_1']()) is True


def test_admitted_00050():
    # sdk_ClientError_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ClientError_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_bare_1']())
    ) is True


def test_contention_00051():
    # sdk_ClientError_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_cause_aborted_1']()) is True


def test_transport_00051():
    # sdk_ClientError_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ClientError_cause_aborted_1']()) is True


def test_admitted_00051():
    # sdk_ClientError_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ClientError_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_cause_aborted_1']())
    ) is True


def test_contention_00052():
    # sdk_ClientError_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_cause_expired_1']()) is True


def test_transport_00052():
    # sdk_ClientError_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ClientError_cause_expired_1']()) is True


def test_admitted_00052():
    # sdk_ClientError_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ClientError_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_cause_expired_1']())
    ) is True


def test_contention_00053():
    # sdk_ClientError_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_cause_timeout_1']()) is False


def test_transport_00053():
    # sdk_ClientError_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ClientError_cause_timeout_1']()) is True


def test_admitted_00053():
    # sdk_ClientError_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ClientError_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_cause_timeout_1']())
    ) is True


def test_contention_00054():
    # sdk_ClientError_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_cause_value_1']()) is False


def test_transport_00054():
    # sdk_ClientError_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ClientError_cause_value_1']()) is True


def test_admitted_00054():
    # sdk_ClientError_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ClientError_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_cause_value_1']())
    ) is True


def test_contention_00055():
    # sdk_ClientError_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_bare_0']()) is False


def test_transport_00055():
    # sdk_ClientError_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ClientError_bare_0']()) is True


def test_admitted_00055():
    # sdk_ClientError_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ClientError_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_bare_0']())
    ) is True


def test_contention_00056():
    # sdk_ClientError_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_cause_aborted_0']()) is True


def test_transport_00056():
    # sdk_ClientError_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ClientError_cause_aborted_0']()) is True


def test_admitted_00056():
    # sdk_ClientError_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ClientError_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_cause_aborted_0']())
    ) is True


def test_contention_00057():
    # sdk_ClientError_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_cause_expired_0']()) is True


def test_transport_00057():
    # sdk_ClientError_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ClientError_cause_expired_0']()) is True


def test_admitted_00057():
    # sdk_ClientError_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ClientError_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_cause_expired_0']())
    ) is True


def test_contention_00058():
    # sdk_ClientError_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_cause_timeout_0']()) is False


def test_transport_00058():
    # sdk_ClientError_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ClientError_cause_timeout_0']()) is True


def test_admitted_00058():
    # sdk_ClientError_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ClientError_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_cause_timeout_0']())
    ) is True


def test_contention_00059():
    # sdk_ClientError_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_cause_value_0']()) is False


def test_transport_00059():
    # sdk_ClientError_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ClientError_cause_value_0']()) is True


def test_admitted_00059():
    # sdk_ClientError_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ClientError_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ClientError_cause_value_0']())
    ) is True


def test_contention_00060():
    # sdk_Conflict_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_bare_1']()) is False


def test_transport_00060():
    # sdk_Conflict_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Conflict_bare_1']()) is True


def test_admitted_00060():
    # sdk_Conflict_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Conflict_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_bare_1']())
    ) is True


def test_contention_00061():
    # sdk_Conflict_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_cause_aborted_1']()) is True


def test_transport_00061():
    # sdk_Conflict_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Conflict_cause_aborted_1']()) is True


def test_admitted_00061():
    # sdk_Conflict_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Conflict_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_cause_aborted_1']())
    ) is True


def test_contention_00062():
    # sdk_Conflict_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_cause_expired_1']()) is True


def test_transport_00062():
    # sdk_Conflict_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Conflict_cause_expired_1']()) is True


def test_admitted_00062():
    # sdk_Conflict_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Conflict_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_cause_expired_1']())
    ) is True


def test_contention_00063():
    # sdk_Conflict_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_cause_timeout_1']()) is False


def test_transport_00063():
    # sdk_Conflict_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Conflict_cause_timeout_1']()) is True


def test_admitted_00063():
    # sdk_Conflict_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Conflict_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_cause_timeout_1']())
    ) is True


def test_contention_00064():
    # sdk_Conflict_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_cause_value_1']()) is False


def test_transport_00064():
    # sdk_Conflict_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Conflict_cause_value_1']()) is True


def test_admitted_00064():
    # sdk_Conflict_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Conflict_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_cause_value_1']())
    ) is True


def test_contention_00065():
    # sdk_Conflict_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_bare_0']()) is False


def test_transport_00065():
    # sdk_Conflict_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Conflict_bare_0']()) is True


def test_admitted_00065():
    # sdk_Conflict_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Conflict_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_bare_0']())
    ) is True


def test_contention_00066():
    # sdk_Conflict_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_cause_aborted_0']()) is True


def test_transport_00066():
    # sdk_Conflict_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Conflict_cause_aborted_0']()) is True


def test_admitted_00066():
    # sdk_Conflict_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Conflict_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_cause_aborted_0']())
    ) is True


def test_contention_00067():
    # sdk_Conflict_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_cause_expired_0']()) is True


def test_transport_00067():
    # sdk_Conflict_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Conflict_cause_expired_0']()) is True


def test_admitted_00067():
    # sdk_Conflict_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Conflict_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_cause_expired_0']())
    ) is True


def test_contention_00068():
    # sdk_Conflict_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_cause_timeout_0']()) is False


def test_transport_00068():
    # sdk_Conflict_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Conflict_cause_timeout_0']()) is True


def test_admitted_00068():
    # sdk_Conflict_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Conflict_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_cause_timeout_0']())
    ) is True


def test_contention_00069():
    # sdk_Conflict_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_cause_value_0']()) is False


def test_transport_00069():
    # sdk_Conflict_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Conflict_cause_value_0']()) is True


def test_admitted_00069():
    # sdk_Conflict_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Conflict_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Conflict_cause_value_0']())
    ) is True


def test_contention_00070():
    # sdk_DataLoss_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_bare_1']()) is False


def test_transport_00070():
    # sdk_DataLoss_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DataLoss_bare_1']()) is True


def test_admitted_00070():
    # sdk_DataLoss_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DataLoss_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_bare_1']())
    ) is True


def test_contention_00071():
    # sdk_DataLoss_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_1']()) is True


def test_transport_00071():
    # sdk_DataLoss_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_1']()) is True


def test_admitted_00071():
    # sdk_DataLoss_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_1']())
    ) is True


def test_contention_00072():
    # sdk_DataLoss_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_cause_expired_1']()) is True


def test_transport_00072():
    # sdk_DataLoss_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DataLoss_cause_expired_1']()) is True


def test_admitted_00072():
    # sdk_DataLoss_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DataLoss_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_cause_expired_1']())
    ) is True


def test_contention_00073():
    # sdk_DataLoss_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_1']()) is False


def test_transport_00073():
    # sdk_DataLoss_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_1']()) is True


def test_admitted_00073():
    # sdk_DataLoss_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_1']())
    ) is True


def test_contention_00074():
    # sdk_DataLoss_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_cause_value_1']()) is False


def test_transport_00074():
    # sdk_DataLoss_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DataLoss_cause_value_1']()) is True


def test_admitted_00074():
    # sdk_DataLoss_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DataLoss_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_cause_value_1']())
    ) is True


def test_contention_00075():
    # sdk_DataLoss_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_bare_0']()) is False


def test_transport_00075():
    # sdk_DataLoss_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DataLoss_bare_0']()) is True


def test_admitted_00075():
    # sdk_DataLoss_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DataLoss_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_bare_0']())
    ) is True


def test_contention_00076():
    # sdk_DataLoss_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_0']()) is True


def test_transport_00076():
    # sdk_DataLoss_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_0']()) is True


def test_admitted_00076():
    # sdk_DataLoss_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_0']())
    ) is True


def test_contention_00077():
    # sdk_DataLoss_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_cause_expired_0']()) is True


def test_transport_00077():
    # sdk_DataLoss_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DataLoss_cause_expired_0']()) is True


def test_admitted_00077():
    # sdk_DataLoss_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DataLoss_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_cause_expired_0']())
    ) is True


def test_contention_00078():
    # sdk_DataLoss_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_0']()) is False


def test_transport_00078():
    # sdk_DataLoss_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_0']()) is True


def test_admitted_00078():
    # sdk_DataLoss_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_0']())
    ) is True


def test_contention_00079():
    # sdk_DataLoss_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_cause_value_0']()) is False


def test_transport_00079():
    # sdk_DataLoss_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DataLoss_cause_value_0']()) is True


def test_admitted_00079():
    # sdk_DataLoss_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DataLoss_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DataLoss_cause_value_0']())
    ) is True


def test_contention_00080():
    # sdk_DeadlineExceeded_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_1']()) is False


def test_transport_00080():
    # sdk_DeadlineExceeded_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_1']()) is True


def test_admitted_00080():
    # sdk_DeadlineExceeded_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_1']())
    ) is True


def test_contention_00081():
    # sdk_DeadlineExceeded_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_1']()) is True


def test_transport_00081():
    # sdk_DeadlineExceeded_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_1']()) is True


def test_admitted_00081():
    # sdk_DeadlineExceeded_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_1']())
    ) is True


def test_contention_00082():
    # sdk_DeadlineExceeded_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_1']()) is True


def test_transport_00082():
    # sdk_DeadlineExceeded_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_1']()) is True


def test_admitted_00082():
    # sdk_DeadlineExceeded_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_1']())
    ) is True


def test_contention_00083():
    # sdk_DeadlineExceeded_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_1']()) is False


def test_transport_00083():
    # sdk_DeadlineExceeded_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_1']()) is True


def test_admitted_00083():
    # sdk_DeadlineExceeded_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_1']())
    ) is True


def test_contention_00084():
    # sdk_DeadlineExceeded_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_1']()) is False


def test_transport_00084():
    # sdk_DeadlineExceeded_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_1']()) is True


def test_admitted_00084():
    # sdk_DeadlineExceeded_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_1']())
    ) is True


def test_contention_00085():
    # sdk_DeadlineExceeded_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_0']()) is False


def test_transport_00085():
    # sdk_DeadlineExceeded_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_0']()) is True


def test_admitted_00085():
    # sdk_DeadlineExceeded_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_0']())
    ) is True


def test_contention_00086():
    # sdk_DeadlineExceeded_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_0']()) is True


def test_transport_00086():
    # sdk_DeadlineExceeded_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_0']()) is True


def test_admitted_00086():
    # sdk_DeadlineExceeded_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_0']())
    ) is True


def test_contention_00087():
    # sdk_DeadlineExceeded_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_0']()) is True


def test_transport_00087():
    # sdk_DeadlineExceeded_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_0']()) is True


def test_admitted_00087():
    # sdk_DeadlineExceeded_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_0']())
    ) is True


def test_contention_00088():
    # sdk_DeadlineExceeded_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_0']()) is False


def test_transport_00088():
    # sdk_DeadlineExceeded_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_0']()) is True


def test_admitted_00088():
    # sdk_DeadlineExceeded_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_0']())
    ) is True


def test_contention_00089():
    # sdk_DeadlineExceeded_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_0']()) is False


def test_transport_00089():
    # sdk_DeadlineExceeded_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_0']()) is True


def test_admitted_00089():
    # sdk_DeadlineExceeded_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_0']())
    ) is True


def test_contention_00090():
    # sdk_DuplicateCredentialArgs_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_1']()) is False


def test_transport_00090():
    # sdk_DuplicateCredentialArgs_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_1']()) is True


def test_admitted_00090():
    # sdk_DuplicateCredentialArgs_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_1']())
    ) is True


def test_contention_00091():
    # sdk_DuplicateCredentialArgs_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_1']()) is True


def test_transport_00091():
    # sdk_DuplicateCredentialArgs_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_1']()) is True


def test_admitted_00091():
    # sdk_DuplicateCredentialArgs_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_1']())
    ) is True


def test_contention_00092():
    # sdk_DuplicateCredentialArgs_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_1']()) is True


def test_transport_00092():
    # sdk_DuplicateCredentialArgs_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_1']()) is True


def test_admitted_00092():
    # sdk_DuplicateCredentialArgs_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_1']())
    ) is True


def test_contention_00093():
    # sdk_DuplicateCredentialArgs_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_1']()) is False


def test_transport_00093():
    # sdk_DuplicateCredentialArgs_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_1']()) is True


def test_admitted_00093():
    # sdk_DuplicateCredentialArgs_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_1']())
    ) is True


def test_contention_00094():
    # sdk_DuplicateCredentialArgs_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_1']()) is False


def test_transport_00094():
    # sdk_DuplicateCredentialArgs_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_1']()) is True


def test_admitted_00094():
    # sdk_DuplicateCredentialArgs_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_1']())
    ) is True


def test_contention_00095():
    # sdk_DuplicateCredentialArgs_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_0']()) is False


def test_transport_00095():
    # sdk_DuplicateCredentialArgs_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_0']()) is True


def test_admitted_00095():
    # sdk_DuplicateCredentialArgs_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_0']())
    ) is True


def test_contention_00096():
    # sdk_DuplicateCredentialArgs_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_0']()) is True


def test_transport_00096():
    # sdk_DuplicateCredentialArgs_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_0']()) is True


def test_admitted_00096():
    # sdk_DuplicateCredentialArgs_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_0']())
    ) is True


def test_contention_00097():
    # sdk_DuplicateCredentialArgs_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_0']()) is True


def test_transport_00097():
    # sdk_DuplicateCredentialArgs_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_0']()) is True


def test_admitted_00097():
    # sdk_DuplicateCredentialArgs_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_0']())
    ) is True


def test_contention_00098():
    # sdk_DuplicateCredentialArgs_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_0']()) is False


def test_transport_00098():
    # sdk_DuplicateCredentialArgs_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_0']()) is True


def test_admitted_00098():
    # sdk_DuplicateCredentialArgs_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_0']())
    ) is True


def test_contention_00099():
    # sdk_DuplicateCredentialArgs_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_0']()) is False


def test_transport_00099():
    # sdk_DuplicateCredentialArgs_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_0']()) is True


def test_admitted_00099():
    # sdk_DuplicateCredentialArgs_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_0']())
    ) is True


def test_contention_00100():
    # sdk_FailedPrecondition_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_bare_1']()) is False


def test_transport_00100():
    # sdk_FailedPrecondition_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_FailedPrecondition_bare_1']()) is True


def test_admitted_00100():
    # sdk_FailedPrecondition_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_FailedPrecondition_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_bare_1']())
    ) is True


def test_contention_00101():
    # sdk_FailedPrecondition_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_1']()) is True


def test_transport_00101():
    # sdk_FailedPrecondition_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_1']()) is True


def test_admitted_00101():
    # sdk_FailedPrecondition_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_1']())
    ) is True


def test_contention_00102():
    # sdk_FailedPrecondition_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_1']()) is True


def test_transport_00102():
    # sdk_FailedPrecondition_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_1']()) is True


def test_admitted_00102():
    # sdk_FailedPrecondition_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_1']())
    ) is True


def test_contention_00103():
    # sdk_FailedPrecondition_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_1']()) is False


def test_transport_00103():
    # sdk_FailedPrecondition_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_1']()) is True


def test_admitted_00103():
    # sdk_FailedPrecondition_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_1']())
    ) is True


def test_contention_00104():
    # sdk_FailedPrecondition_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_1']()) is False


def test_transport_00104():
    # sdk_FailedPrecondition_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_1']()) is True


def test_admitted_00104():
    # sdk_FailedPrecondition_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_1']())
    ) is True


def test_contention_00105():
    # sdk_FailedPrecondition_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_bare_0']()) is False


def test_transport_00105():
    # sdk_FailedPrecondition_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_FailedPrecondition_bare_0']()) is True


def test_admitted_00105():
    # sdk_FailedPrecondition_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_FailedPrecondition_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_bare_0']())
    ) is True


def test_contention_00106():
    # sdk_FailedPrecondition_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_0']()) is True


def test_transport_00106():
    # sdk_FailedPrecondition_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_0']()) is True


def test_admitted_00106():
    # sdk_FailedPrecondition_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_0']())
    ) is True


def test_contention_00107():
    # sdk_FailedPrecondition_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_0']()) is True


def test_transport_00107():
    # sdk_FailedPrecondition_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_0']()) is True


def test_admitted_00107():
    # sdk_FailedPrecondition_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_0']())
    ) is True


def test_contention_00108():
    # sdk_FailedPrecondition_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_0']()) is False


def test_transport_00108():
    # sdk_FailedPrecondition_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_0']()) is True


def test_admitted_00108():
    # sdk_FailedPrecondition_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_0']())
    ) is True


def test_contention_00109():
    # sdk_FailedPrecondition_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_0']()) is False


def test_transport_00109():
    # sdk_FailedPrecondition_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_0']()) is True


def test_admitted_00109():
    # sdk_FailedPrecondition_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_0']())
    ) is True


def test_contention_00110():
    # sdk_Forbidden_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_bare_1']()) is False


def test_transport_00110():
    # sdk_Forbidden_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Forbidden_bare_1']()) is True


def test_admitted_00110():
    # sdk_Forbidden_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Forbidden_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_bare_1']())
    ) is True


def test_contention_00111():
    # sdk_Forbidden_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_1']()) is True


def test_transport_00111():
    # sdk_Forbidden_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_1']()) is True


def test_admitted_00111():
    # sdk_Forbidden_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_1']())
    ) is True


def test_contention_00112():
    # sdk_Forbidden_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_cause_expired_1']()) is True


def test_transport_00112():
    # sdk_Forbidden_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Forbidden_cause_expired_1']()) is True


def test_admitted_00112():
    # sdk_Forbidden_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Forbidden_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_cause_expired_1']())
    ) is True


def test_contention_00113():
    # sdk_Forbidden_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_1']()) is False


def test_transport_00113():
    # sdk_Forbidden_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_1']()) is True


def test_admitted_00113():
    # sdk_Forbidden_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_1']())
    ) is True


def test_contention_00114():
    # sdk_Forbidden_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_cause_value_1']()) is False


def test_transport_00114():
    # sdk_Forbidden_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Forbidden_cause_value_1']()) is True


def test_admitted_00114():
    # sdk_Forbidden_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Forbidden_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_cause_value_1']())
    ) is True


def test_contention_00115():
    # sdk_Forbidden_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_bare_0']()) is False


def test_transport_00115():
    # sdk_Forbidden_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Forbidden_bare_0']()) is True


def test_admitted_00115():
    # sdk_Forbidden_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Forbidden_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_bare_0']())
    ) is True


def test_contention_00116():
    # sdk_Forbidden_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_0']()) is True


def test_transport_00116():
    # sdk_Forbidden_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_0']()) is True


def test_admitted_00116():
    # sdk_Forbidden_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_0']())
    ) is True


def test_contention_00117():
    # sdk_Forbidden_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_cause_expired_0']()) is True


def test_transport_00117():
    # sdk_Forbidden_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Forbidden_cause_expired_0']()) is True


def test_admitted_00117():
    # sdk_Forbidden_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Forbidden_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_cause_expired_0']())
    ) is True


def test_contention_00118():
    # sdk_Forbidden_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_0']()) is False


def test_transport_00118():
    # sdk_Forbidden_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_0']()) is True


def test_admitted_00118():
    # sdk_Forbidden_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_0']())
    ) is True


def test_contention_00119():
    # sdk_Forbidden_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_cause_value_0']()) is False


def test_transport_00119():
    # sdk_Forbidden_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Forbidden_cause_value_0']()) is True


def test_admitted_00119():
    # sdk_Forbidden_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Forbidden_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Forbidden_cause_value_0']())
    ) is True


def test_contention_00120():
    # sdk_GatewayTimeout_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_bare_1']()) is False


def test_transport_00120():
    # sdk_GatewayTimeout_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GatewayTimeout_bare_1']()) is True


def test_admitted_00120():
    # sdk_GatewayTimeout_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GatewayTimeout_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_bare_1']())
    ) is True


def test_contention_00121():
    # sdk_GatewayTimeout_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_1']()) is True


def test_transport_00121():
    # sdk_GatewayTimeout_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_1']()) is True


def test_admitted_00121():
    # sdk_GatewayTimeout_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_1']())
    ) is True


def test_contention_00122():
    # sdk_GatewayTimeout_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_1']()) is True


def test_transport_00122():
    # sdk_GatewayTimeout_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_1']()) is True


def test_admitted_00122():
    # sdk_GatewayTimeout_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_1']())
    ) is True


def test_contention_00123():
    # sdk_GatewayTimeout_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_1']()) is False


def test_transport_00123():
    # sdk_GatewayTimeout_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_1']()) is True


def test_admitted_00123():
    # sdk_GatewayTimeout_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_1']())
    ) is True


def test_contention_00124():
    # sdk_GatewayTimeout_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_1']()) is False


def test_transport_00124():
    # sdk_GatewayTimeout_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_1']()) is True


def test_admitted_00124():
    # sdk_GatewayTimeout_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_1']())
    ) is True


def test_contention_00125():
    # sdk_GatewayTimeout_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_bare_0']()) is False


def test_transport_00125():
    # sdk_GatewayTimeout_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GatewayTimeout_bare_0']()) is True


def test_admitted_00125():
    # sdk_GatewayTimeout_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GatewayTimeout_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_bare_0']())
    ) is True


def test_contention_00126():
    # sdk_GatewayTimeout_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_0']()) is True


def test_transport_00126():
    # sdk_GatewayTimeout_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_0']()) is True


def test_admitted_00126():
    # sdk_GatewayTimeout_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_0']())
    ) is True


def test_contention_00127():
    # sdk_GatewayTimeout_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_0']()) is True


def test_transport_00127():
    # sdk_GatewayTimeout_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_0']()) is True


def test_admitted_00127():
    # sdk_GatewayTimeout_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_0']())
    ) is True


def test_contention_00128():
    # sdk_GatewayTimeout_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_0']()) is False


def test_transport_00128():
    # sdk_GatewayTimeout_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_0']()) is True


def test_admitted_00128():
    # sdk_GatewayTimeout_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_0']())
    ) is True


def test_contention_00129():
    # sdk_GatewayTimeout_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_0']()) is False


def test_transport_00129():
    # sdk_GatewayTimeout_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_0']()) is True


def test_admitted_00129():
    # sdk_GatewayTimeout_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_0']())
    ) is True


def test_contention_00130():
    # sdk_GoogleAPICallError_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_1']()) is False


def test_transport_00130():
    # sdk_GoogleAPICallError_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_1']()) is True


def test_admitted_00130():
    # sdk_GoogleAPICallError_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_1']())
    ) is True


def test_contention_00131():
    # sdk_GoogleAPICallError_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_1']()) is True


def test_transport_00131():
    # sdk_GoogleAPICallError_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_1']()) is True


def test_admitted_00131():
    # sdk_GoogleAPICallError_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_1']())
    ) is True


def test_contention_00132():
    # sdk_GoogleAPICallError_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_1']()) is True


def test_transport_00132():
    # sdk_GoogleAPICallError_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_1']()) is True


def test_admitted_00132():
    # sdk_GoogleAPICallError_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_1']())
    ) is True


def test_contention_00133():
    # sdk_GoogleAPICallError_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_1']()) is False


def test_transport_00133():
    # sdk_GoogleAPICallError_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_1']()) is True


def test_admitted_00133():
    # sdk_GoogleAPICallError_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_1']())
    ) is True


def test_contention_00134():
    # sdk_GoogleAPICallError_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_1']()) is False


def test_transport_00134():
    # sdk_GoogleAPICallError_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_1']()) is True


def test_admitted_00134():
    # sdk_GoogleAPICallError_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_1']())
    ) is True


def test_contention_00135():
    # sdk_GoogleAPICallError_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_0']()) is False


def test_transport_00135():
    # sdk_GoogleAPICallError_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_0']()) is True


def test_admitted_00135():
    # sdk_GoogleAPICallError_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_0']())
    ) is True


def test_contention_00136():
    # sdk_GoogleAPICallError_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_0']()) is True


def test_transport_00136():
    # sdk_GoogleAPICallError_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_0']()) is True


def test_admitted_00136():
    # sdk_GoogleAPICallError_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_0']())
    ) is True


def test_contention_00137():
    # sdk_GoogleAPICallError_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_0']()) is True


def test_transport_00137():
    # sdk_GoogleAPICallError_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_0']()) is True


def test_admitted_00137():
    # sdk_GoogleAPICallError_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_0']())
    ) is True


def test_contention_00138():
    # sdk_GoogleAPICallError_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_0']()) is False


def test_transport_00138():
    # sdk_GoogleAPICallError_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_0']()) is True


def test_admitted_00138():
    # sdk_GoogleAPICallError_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_0']())
    ) is True


def test_contention_00139():
    # sdk_GoogleAPICallError_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_0']()) is False


def test_transport_00139():
    # sdk_GoogleAPICallError_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_0']()) is True


def test_admitted_00139():
    # sdk_GoogleAPICallError_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_0']())
    ) is True


def test_contention_00140():
    # sdk_GoogleAPIError_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_bare_1']()) is False


def test_transport_00140():
    # sdk_GoogleAPIError_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPIError_bare_1']()) is True


def test_admitted_00140():
    # sdk_GoogleAPIError_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPIError_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_bare_1']())
    ) is True


def test_contention_00141():
    # sdk_GoogleAPIError_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_1']()) is True


def test_transport_00141():
    # sdk_GoogleAPIError_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_1']()) is True


def test_admitted_00141():
    # sdk_GoogleAPIError_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_1']())
    ) is True


def test_contention_00142():
    # sdk_GoogleAPIError_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_1']()) is True


def test_transport_00142():
    # sdk_GoogleAPIError_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_1']()) is True


def test_admitted_00142():
    # sdk_GoogleAPIError_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_1']())
    ) is True


def test_contention_00143():
    # sdk_GoogleAPIError_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_1']()) is False


def test_transport_00143():
    # sdk_GoogleAPIError_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_1']()) is True


def test_admitted_00143():
    # sdk_GoogleAPIError_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_1']())
    ) is True


def test_contention_00144():
    # sdk_GoogleAPIError_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_1']()) is False


def test_transport_00144():
    # sdk_GoogleAPIError_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_1']()) is True


def test_admitted_00144():
    # sdk_GoogleAPIError_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_1']())
    ) is True


def test_contention_00145():
    # sdk_GoogleAPIError_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_bare_0']()) is False


def test_transport_00145():
    # sdk_GoogleAPIError_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPIError_bare_0']()) is True


def test_admitted_00145():
    # sdk_GoogleAPIError_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPIError_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_bare_0']())
    ) is True


def test_contention_00146():
    # sdk_GoogleAPIError_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_0']()) is True


def test_transport_00146():
    # sdk_GoogleAPIError_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_0']()) is True


def test_admitted_00146():
    # sdk_GoogleAPIError_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_0']())
    ) is True


def test_contention_00147():
    # sdk_GoogleAPIError_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_0']()) is True


def test_transport_00147():
    # sdk_GoogleAPIError_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_0']()) is True


def test_admitted_00147():
    # sdk_GoogleAPIError_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_0']())
    ) is True


def test_contention_00148():
    # sdk_GoogleAPIError_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_0']()) is False


def test_transport_00148():
    # sdk_GoogleAPIError_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_0']()) is True


def test_admitted_00148():
    # sdk_GoogleAPIError_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_0']())
    ) is True


def test_contention_00149():
    # sdk_GoogleAPIError_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_0']()) is False


def test_transport_00149():
    # sdk_GoogleAPIError_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_0']()) is True


def test_admitted_00149():
    # sdk_GoogleAPIError_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_0']())
    ) is True


def test_contention_00150():
    # sdk_InternalServerError_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_bare_1']()) is False


def test_transport_00150():
    # sdk_InternalServerError_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InternalServerError_bare_1']()) is True


def test_admitted_00150():
    # sdk_InternalServerError_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InternalServerError_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_bare_1']())
    ) is True


def test_contention_00151():
    # sdk_InternalServerError_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_1']()) is True


def test_transport_00151():
    # sdk_InternalServerError_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_1']()) is True


def test_admitted_00151():
    # sdk_InternalServerError_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_1']())
    ) is True


def test_contention_00152():
    # sdk_InternalServerError_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_1']()) is True


def test_transport_00152():
    # sdk_InternalServerError_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_1']()) is True


def test_admitted_00152():
    # sdk_InternalServerError_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_1']())
    ) is True


def test_contention_00153():
    # sdk_InternalServerError_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_1']()) is False


def test_transport_00153():
    # sdk_InternalServerError_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_1']()) is True


def test_admitted_00153():
    # sdk_InternalServerError_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_1']())
    ) is True


def test_contention_00154():
    # sdk_InternalServerError_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_cause_value_1']()) is False


def test_transport_00154():
    # sdk_InternalServerError_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InternalServerError_cause_value_1']()) is True


def test_admitted_00154():
    # sdk_InternalServerError_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InternalServerError_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_cause_value_1']())
    ) is True


def test_contention_00155():
    # sdk_InternalServerError_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_bare_0']()) is False


def test_transport_00155():
    # sdk_InternalServerError_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InternalServerError_bare_0']()) is True


def test_admitted_00155():
    # sdk_InternalServerError_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InternalServerError_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_bare_0']())
    ) is True


def test_contention_00156():
    # sdk_InternalServerError_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_0']()) is True


def test_transport_00156():
    # sdk_InternalServerError_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_0']()) is True


def test_admitted_00156():
    # sdk_InternalServerError_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_0']())
    ) is True


def test_contention_00157():
    # sdk_InternalServerError_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_0']()) is True


def test_transport_00157():
    # sdk_InternalServerError_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_0']()) is True


def test_admitted_00157():
    # sdk_InternalServerError_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_0']())
    ) is True


def test_contention_00158():
    # sdk_InternalServerError_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_0']()) is False


def test_transport_00158():
    # sdk_InternalServerError_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_0']()) is True


def test_admitted_00158():
    # sdk_InternalServerError_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_0']())
    ) is True


def test_contention_00159():
    # sdk_InternalServerError_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_cause_value_0']()) is False


def test_transport_00159():
    # sdk_InternalServerError_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InternalServerError_cause_value_0']()) is True


def test_admitted_00159():
    # sdk_InternalServerError_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InternalServerError_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InternalServerError_cause_value_0']())
    ) is True


def test_contention_00160():
    # sdk_InvalidArgument_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_bare_1']()) is False


def test_transport_00160():
    # sdk_InvalidArgument_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InvalidArgument_bare_1']()) is True


def test_admitted_00160():
    # sdk_InvalidArgument_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InvalidArgument_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_bare_1']())
    ) is True


def test_contention_00161():
    # sdk_InvalidArgument_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_1']()) is True


def test_transport_00161():
    # sdk_InvalidArgument_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_1']()) is True


def test_admitted_00161():
    # sdk_InvalidArgument_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_1']())
    ) is True


def test_contention_00162():
    # sdk_InvalidArgument_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_1']()) is True


def test_transport_00162():
    # sdk_InvalidArgument_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_1']()) is True


def test_admitted_00162():
    # sdk_InvalidArgument_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_1']())
    ) is True


def test_contention_00163():
    # sdk_InvalidArgument_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_1']()) is False


def test_transport_00163():
    # sdk_InvalidArgument_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_1']()) is True


def test_admitted_00163():
    # sdk_InvalidArgument_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_1']())
    ) is True


def test_contention_00164():
    # sdk_InvalidArgument_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_1']()) is False


def test_transport_00164():
    # sdk_InvalidArgument_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_1']()) is True


def test_admitted_00164():
    # sdk_InvalidArgument_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_1']())
    ) is True


def test_contention_00165():
    # sdk_InvalidArgument_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_bare_0']()) is False


def test_transport_00165():
    # sdk_InvalidArgument_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InvalidArgument_bare_0']()) is True


def test_admitted_00165():
    # sdk_InvalidArgument_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InvalidArgument_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_bare_0']())
    ) is True


def test_contention_00166():
    # sdk_InvalidArgument_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_0']()) is True


def test_transport_00166():
    # sdk_InvalidArgument_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_0']()) is True


def test_admitted_00166():
    # sdk_InvalidArgument_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_0']())
    ) is True


def test_contention_00167():
    # sdk_InvalidArgument_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_0']()) is True


def test_transport_00167():
    # sdk_InvalidArgument_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_0']()) is True


def test_admitted_00167():
    # sdk_InvalidArgument_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_0']())
    ) is True


def test_contention_00168():
    # sdk_InvalidArgument_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_0']()) is False


def test_transport_00168():
    # sdk_InvalidArgument_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_0']()) is True


def test_admitted_00168():
    # sdk_InvalidArgument_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_0']())
    ) is True


def test_contention_00169():
    # sdk_InvalidArgument_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_0']()) is False


def test_transport_00169():
    # sdk_InvalidArgument_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_0']()) is True


def test_admitted_00169():
    # sdk_InvalidArgument_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_0']())
    ) is True


def test_contention_00170():
    # sdk_LengthRequired_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_bare_1']()) is False


def test_transport_00170():
    # sdk_LengthRequired_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_LengthRequired_bare_1']()) is True


def test_admitted_00170():
    # sdk_LengthRequired_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_LengthRequired_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_bare_1']())
    ) is True


def test_contention_00171():
    # sdk_LengthRequired_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_1']()) is True


def test_transport_00171():
    # sdk_LengthRequired_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_1']()) is True


def test_admitted_00171():
    # sdk_LengthRequired_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_1']())
    ) is True


def test_contention_00172():
    # sdk_LengthRequired_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_1']()) is True


def test_transport_00172():
    # sdk_LengthRequired_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_1']()) is True


def test_admitted_00172():
    # sdk_LengthRequired_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_1']())
    ) is True


def test_contention_00173():
    # sdk_LengthRequired_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_1']()) is False


def test_transport_00173():
    # sdk_LengthRequired_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_1']()) is True


def test_admitted_00173():
    # sdk_LengthRequired_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_1']())
    ) is True


def test_contention_00174():
    # sdk_LengthRequired_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_cause_value_1']()) is False


def test_transport_00174():
    # sdk_LengthRequired_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_LengthRequired_cause_value_1']()) is True


def test_admitted_00174():
    # sdk_LengthRequired_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_LengthRequired_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_cause_value_1']())
    ) is True


def test_contention_00175():
    # sdk_LengthRequired_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_bare_0']()) is False


def test_transport_00175():
    # sdk_LengthRequired_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_LengthRequired_bare_0']()) is True


def test_admitted_00175():
    # sdk_LengthRequired_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_LengthRequired_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_bare_0']())
    ) is True


def test_contention_00176():
    # sdk_LengthRequired_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_0']()) is True


def test_transport_00176():
    # sdk_LengthRequired_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_0']()) is True


def test_admitted_00176():
    # sdk_LengthRequired_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_0']())
    ) is True


def test_contention_00177():
    # sdk_LengthRequired_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_0']()) is True


def test_transport_00177():
    # sdk_LengthRequired_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_0']()) is True


def test_admitted_00177():
    # sdk_LengthRequired_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_0']())
    ) is True


def test_contention_00178():
    # sdk_LengthRequired_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_0']()) is False


def test_transport_00178():
    # sdk_LengthRequired_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_0']()) is True


def test_admitted_00178():
    # sdk_LengthRequired_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_0']())
    ) is True


def test_contention_00179():
    # sdk_LengthRequired_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_cause_value_0']()) is False


def test_transport_00179():
    # sdk_LengthRequired_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_LengthRequired_cause_value_0']()) is True


def test_admitted_00179():
    # sdk_LengthRequired_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_LengthRequired_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_LengthRequired_cause_value_0']())
    ) is True


def test_contention_00180():
    # sdk_MethodNotAllowed_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_1']()) is False


def test_transport_00180():
    # sdk_MethodNotAllowed_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_1']()) is True


def test_admitted_00180():
    # sdk_MethodNotAllowed_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_1']())
    ) is True


def test_contention_00181():
    # sdk_MethodNotAllowed_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_1']()) is True


def test_transport_00181():
    # sdk_MethodNotAllowed_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_1']()) is True


def test_admitted_00181():
    # sdk_MethodNotAllowed_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_1']())
    ) is True


def test_contention_00182():
    # sdk_MethodNotAllowed_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_1']()) is True


def test_transport_00182():
    # sdk_MethodNotAllowed_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_1']()) is True


def test_admitted_00182():
    # sdk_MethodNotAllowed_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_1']())
    ) is True


def test_contention_00183():
    # sdk_MethodNotAllowed_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_1']()) is False


def test_transport_00183():
    # sdk_MethodNotAllowed_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_1']()) is True


def test_admitted_00183():
    # sdk_MethodNotAllowed_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_1']())
    ) is True


def test_contention_00184():
    # sdk_MethodNotAllowed_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_1']()) is False


def test_transport_00184():
    # sdk_MethodNotAllowed_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_1']()) is True


def test_admitted_00184():
    # sdk_MethodNotAllowed_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_1']())
    ) is True


def test_contention_00185():
    # sdk_MethodNotAllowed_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_0']()) is False


def test_transport_00185():
    # sdk_MethodNotAllowed_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_0']()) is True


def test_admitted_00185():
    # sdk_MethodNotAllowed_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_0']())
    ) is True


def test_contention_00186():
    # sdk_MethodNotAllowed_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_0']()) is True


def test_transport_00186():
    # sdk_MethodNotAllowed_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_0']()) is True


def test_admitted_00186():
    # sdk_MethodNotAllowed_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_0']())
    ) is True


def test_contention_00187():
    # sdk_MethodNotAllowed_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_0']()) is True


def test_transport_00187():
    # sdk_MethodNotAllowed_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_0']()) is True


def test_admitted_00187():
    # sdk_MethodNotAllowed_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_0']())
    ) is True


def test_contention_00188():
    # sdk_MethodNotAllowed_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_0']()) is False


def test_transport_00188():
    # sdk_MethodNotAllowed_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_0']()) is True


def test_admitted_00188():
    # sdk_MethodNotAllowed_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_0']())
    ) is True


def test_contention_00189():
    # sdk_MethodNotAllowed_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_0']()) is False


def test_transport_00189():
    # sdk_MethodNotAllowed_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_0']()) is True


def test_admitted_00189():
    # sdk_MethodNotAllowed_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_0']())
    ) is True


def test_contention_00190():
    # sdk_MethodNotImplemented_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_1']()) is False


def test_transport_00190():
    # sdk_MethodNotImplemented_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_1']()) is True


def test_admitted_00190():
    # sdk_MethodNotImplemented_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_1']())
    ) is True


def test_contention_00191():
    # sdk_MethodNotImplemented_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_1']()) is True


def test_transport_00191():
    # sdk_MethodNotImplemented_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_1']()) is True


def test_admitted_00191():
    # sdk_MethodNotImplemented_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_1']())
    ) is True


def test_contention_00192():
    # sdk_MethodNotImplemented_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_1']()) is True


def test_transport_00192():
    # sdk_MethodNotImplemented_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_1']()) is True


def test_admitted_00192():
    # sdk_MethodNotImplemented_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_1']())
    ) is True


def test_contention_00193():
    # sdk_MethodNotImplemented_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_1']()) is False


def test_transport_00193():
    # sdk_MethodNotImplemented_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_1']()) is True


def test_admitted_00193():
    # sdk_MethodNotImplemented_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_1']())
    ) is True


def test_contention_00194():
    # sdk_MethodNotImplemented_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_1']()) is False


def test_transport_00194():
    # sdk_MethodNotImplemented_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_1']()) is True


def test_admitted_00194():
    # sdk_MethodNotImplemented_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_1']())
    ) is True


def test_contention_00195():
    # sdk_MethodNotImplemented_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_0']()) is False


def test_transport_00195():
    # sdk_MethodNotImplemented_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_0']()) is True


def test_admitted_00195():
    # sdk_MethodNotImplemented_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_0']())
    ) is True


def test_contention_00196():
    # sdk_MethodNotImplemented_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_0']()) is True


def test_transport_00196():
    # sdk_MethodNotImplemented_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_0']()) is True


def test_admitted_00196():
    # sdk_MethodNotImplemented_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_0']())
    ) is True


def test_contention_00197():
    # sdk_MethodNotImplemented_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_0']()) is True


def test_transport_00197():
    # sdk_MethodNotImplemented_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_0']()) is True


def test_admitted_00197():
    # sdk_MethodNotImplemented_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_0']())
    ) is True


def test_contention_00198():
    # sdk_MethodNotImplemented_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_0']()) is False


def test_transport_00198():
    # sdk_MethodNotImplemented_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_0']()) is True


def test_admitted_00198():
    # sdk_MethodNotImplemented_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_0']())
    ) is True


def test_contention_00199():
    # sdk_MethodNotImplemented_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_0']()) is False


def test_transport_00199():
    # sdk_MethodNotImplemented_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_0']()) is True


def test_admitted_00199():
    # sdk_MethodNotImplemented_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_0']())
    ) is True


def test_contention_00200():
    # sdk_MovedPermanently_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_bare_1']()) is False


def test_transport_00200():
    # sdk_MovedPermanently_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MovedPermanently_bare_1']()) is True


def test_admitted_00200():
    # sdk_MovedPermanently_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MovedPermanently_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_bare_1']())
    ) is True


def test_contention_00201():
    # sdk_MovedPermanently_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_1']()) is True


def test_transport_00201():
    # sdk_MovedPermanently_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_1']()) is True


def test_admitted_00201():
    # sdk_MovedPermanently_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_1']())
    ) is True


def test_contention_00202():
    # sdk_MovedPermanently_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_1']()) is True


def test_transport_00202():
    # sdk_MovedPermanently_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_1']()) is True


def test_admitted_00202():
    # sdk_MovedPermanently_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_1']())
    ) is True


def test_contention_00203():
    # sdk_MovedPermanently_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_1']()) is False


def test_transport_00203():
    # sdk_MovedPermanently_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_1']()) is True


def test_admitted_00203():
    # sdk_MovedPermanently_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_1']())
    ) is True


def test_contention_00204():
    # sdk_MovedPermanently_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_1']()) is False


def test_transport_00204():
    # sdk_MovedPermanently_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_1']()) is True


def test_admitted_00204():
    # sdk_MovedPermanently_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_1']())
    ) is True


def test_contention_00205():
    # sdk_MovedPermanently_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_bare_0']()) is False


def test_transport_00205():
    # sdk_MovedPermanently_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MovedPermanently_bare_0']()) is True


def test_admitted_00205():
    # sdk_MovedPermanently_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MovedPermanently_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_bare_0']())
    ) is True


def test_contention_00206():
    # sdk_MovedPermanently_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_0']()) is True


def test_transport_00206():
    # sdk_MovedPermanently_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_0']()) is True


def test_admitted_00206():
    # sdk_MovedPermanently_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_0']())
    ) is True


def test_contention_00207():
    # sdk_MovedPermanently_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_0']()) is True


def test_transport_00207():
    # sdk_MovedPermanently_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_0']()) is True


def test_admitted_00207():
    # sdk_MovedPermanently_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_0']())
    ) is True


def test_contention_00208():
    # sdk_MovedPermanently_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_0']()) is False


def test_transport_00208():
    # sdk_MovedPermanently_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_0']()) is True


def test_admitted_00208():
    # sdk_MovedPermanently_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_0']())
    ) is True


def test_contention_00209():
    # sdk_MovedPermanently_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_0']()) is False


def test_transport_00209():
    # sdk_MovedPermanently_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_0']()) is True


def test_admitted_00209():
    # sdk_MovedPermanently_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_0']())
    ) is True


def test_contention_00210():
    # sdk_NotFound_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_bare_1']()) is False


def test_transport_00210():
    # sdk_NotFound_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotFound_bare_1']()) is True


def test_admitted_00210():
    # sdk_NotFound_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotFound_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_bare_1']())
    ) is True


def test_contention_00211():
    # sdk_NotFound_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_cause_aborted_1']()) is True


def test_transport_00211():
    # sdk_NotFound_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotFound_cause_aborted_1']()) is True


def test_admitted_00211():
    # sdk_NotFound_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotFound_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_cause_aborted_1']())
    ) is True


def test_contention_00212():
    # sdk_NotFound_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_cause_expired_1']()) is True


def test_transport_00212():
    # sdk_NotFound_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotFound_cause_expired_1']()) is True


def test_admitted_00212():
    # sdk_NotFound_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotFound_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_cause_expired_1']())
    ) is True


def test_contention_00213():
    # sdk_NotFound_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_cause_timeout_1']()) is False


def test_transport_00213():
    # sdk_NotFound_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotFound_cause_timeout_1']()) is True


def test_admitted_00213():
    # sdk_NotFound_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotFound_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_cause_timeout_1']())
    ) is True


def test_contention_00214():
    # sdk_NotFound_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_cause_value_1']()) is False


def test_transport_00214():
    # sdk_NotFound_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotFound_cause_value_1']()) is True


def test_admitted_00214():
    # sdk_NotFound_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotFound_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_cause_value_1']())
    ) is True


def test_contention_00215():
    # sdk_NotFound_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_bare_0']()) is False


def test_transport_00215():
    # sdk_NotFound_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotFound_bare_0']()) is True


def test_admitted_00215():
    # sdk_NotFound_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotFound_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_bare_0']())
    ) is True


def test_contention_00216():
    # sdk_NotFound_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_cause_aborted_0']()) is True


def test_transport_00216():
    # sdk_NotFound_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotFound_cause_aborted_0']()) is True


def test_admitted_00216():
    # sdk_NotFound_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotFound_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_cause_aborted_0']())
    ) is True


def test_contention_00217():
    # sdk_NotFound_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_cause_expired_0']()) is True


def test_transport_00217():
    # sdk_NotFound_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotFound_cause_expired_0']()) is True


def test_admitted_00217():
    # sdk_NotFound_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotFound_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_cause_expired_0']())
    ) is True


def test_contention_00218():
    # sdk_NotFound_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_cause_timeout_0']()) is False


def test_transport_00218():
    # sdk_NotFound_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotFound_cause_timeout_0']()) is True


def test_admitted_00218():
    # sdk_NotFound_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotFound_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_cause_timeout_0']())
    ) is True


def test_contention_00219():
    # sdk_NotFound_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_cause_value_0']()) is False


def test_transport_00219():
    # sdk_NotFound_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotFound_cause_value_0']()) is True


def test_admitted_00219():
    # sdk_NotFound_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotFound_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotFound_cause_value_0']())
    ) is True


def test_contention_00220():
    # sdk_NotModified_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_bare_1']()) is False


def test_transport_00220():
    # sdk_NotModified_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotModified_bare_1']()) is True


def test_admitted_00220():
    # sdk_NotModified_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotModified_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_bare_1']())
    ) is True


def test_contention_00221():
    # sdk_NotModified_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_cause_aborted_1']()) is True


def test_transport_00221():
    # sdk_NotModified_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotModified_cause_aborted_1']()) is True


def test_admitted_00221():
    # sdk_NotModified_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotModified_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_cause_aborted_1']())
    ) is True


def test_contention_00222():
    # sdk_NotModified_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_cause_expired_1']()) is True


def test_transport_00222():
    # sdk_NotModified_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotModified_cause_expired_1']()) is True


def test_admitted_00222():
    # sdk_NotModified_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotModified_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_cause_expired_1']())
    ) is True


def test_contention_00223():
    # sdk_NotModified_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_cause_timeout_1']()) is False


def test_transport_00223():
    # sdk_NotModified_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotModified_cause_timeout_1']()) is True


def test_admitted_00223():
    # sdk_NotModified_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotModified_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_cause_timeout_1']())
    ) is True


def test_contention_00224():
    # sdk_NotModified_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_cause_value_1']()) is False


def test_transport_00224():
    # sdk_NotModified_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotModified_cause_value_1']()) is True


def test_admitted_00224():
    # sdk_NotModified_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotModified_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_cause_value_1']())
    ) is True


def test_contention_00225():
    # sdk_NotModified_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_bare_0']()) is False


def test_transport_00225():
    # sdk_NotModified_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotModified_bare_0']()) is True


def test_admitted_00225():
    # sdk_NotModified_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotModified_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_bare_0']())
    ) is True


def test_contention_00226():
    # sdk_NotModified_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_cause_aborted_0']()) is True


def test_transport_00226():
    # sdk_NotModified_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotModified_cause_aborted_0']()) is True


def test_admitted_00226():
    # sdk_NotModified_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotModified_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_cause_aborted_0']())
    ) is True


def test_contention_00227():
    # sdk_NotModified_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_cause_expired_0']()) is True


def test_transport_00227():
    # sdk_NotModified_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotModified_cause_expired_0']()) is True


def test_admitted_00227():
    # sdk_NotModified_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotModified_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_cause_expired_0']())
    ) is True


def test_contention_00228():
    # sdk_NotModified_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_cause_timeout_0']()) is False


def test_transport_00228():
    # sdk_NotModified_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotModified_cause_timeout_0']()) is True


def test_admitted_00228():
    # sdk_NotModified_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotModified_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_cause_timeout_0']())
    ) is True


def test_contention_00229():
    # sdk_NotModified_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_cause_value_0']()) is False


def test_transport_00229():
    # sdk_NotModified_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotModified_cause_value_0']()) is True


def test_admitted_00229():
    # sdk_NotModified_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_NotModified_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_NotModified_cause_value_0']())
    ) is True


def test_contention_00230():
    # sdk_OutOfRange_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_bare_1']()) is False


def test_transport_00230():
    # sdk_OutOfRange_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_OutOfRange_bare_1']()) is True


def test_admitted_00230():
    # sdk_OutOfRange_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_OutOfRange_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_bare_1']())
    ) is True


def test_contention_00231():
    # sdk_OutOfRange_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_1']()) is True


def test_transport_00231():
    # sdk_OutOfRange_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_1']()) is True


def test_admitted_00231():
    # sdk_OutOfRange_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_1']())
    ) is True


def test_contention_00232():
    # sdk_OutOfRange_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_1']()) is True


def test_transport_00232():
    # sdk_OutOfRange_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_1']()) is True


def test_admitted_00232():
    # sdk_OutOfRange_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_1']())
    ) is True


def test_contention_00233():
    # sdk_OutOfRange_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_1']()) is False


def test_transport_00233():
    # sdk_OutOfRange_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_1']()) is True


def test_admitted_00233():
    # sdk_OutOfRange_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_1']())
    ) is True


def test_contention_00234():
    # sdk_OutOfRange_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_cause_value_1']()) is False


def test_transport_00234():
    # sdk_OutOfRange_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_OutOfRange_cause_value_1']()) is True


def test_admitted_00234():
    # sdk_OutOfRange_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_OutOfRange_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_cause_value_1']())
    ) is True


def test_contention_00235():
    # sdk_OutOfRange_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_bare_0']()) is False


def test_transport_00235():
    # sdk_OutOfRange_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_OutOfRange_bare_0']()) is True


def test_admitted_00235():
    # sdk_OutOfRange_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_OutOfRange_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_bare_0']())
    ) is True


def test_contention_00236():
    # sdk_OutOfRange_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_0']()) is True


def test_transport_00236():
    # sdk_OutOfRange_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_0']()) is True


def test_admitted_00236():
    # sdk_OutOfRange_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_0']())
    ) is True


def test_contention_00237():
    # sdk_OutOfRange_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_0']()) is True


def test_transport_00237():
    # sdk_OutOfRange_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_0']()) is True


def test_admitted_00237():
    # sdk_OutOfRange_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_0']())
    ) is True


def test_contention_00238():
    # sdk_OutOfRange_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_0']()) is False


def test_transport_00238():
    # sdk_OutOfRange_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_0']()) is True


def test_admitted_00238():
    # sdk_OutOfRange_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_0']())
    ) is True


def test_contention_00239():
    # sdk_OutOfRange_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_cause_value_0']()) is False


def test_transport_00239():
    # sdk_OutOfRange_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_OutOfRange_cause_value_0']()) is True


def test_admitted_00239():
    # sdk_OutOfRange_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_OutOfRange_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_OutOfRange_cause_value_0']())
    ) is True


def test_contention_00240():
    # sdk_PermissionDenied_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_bare_1']()) is False


def test_transport_00240():
    # sdk_PermissionDenied_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PermissionDenied_bare_1']()) is True


def test_admitted_00240():
    # sdk_PermissionDenied_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PermissionDenied_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_bare_1']())
    ) is True


def test_contention_00241():
    # sdk_PermissionDenied_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_1']()) is True


def test_transport_00241():
    # sdk_PermissionDenied_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_1']()) is True


def test_admitted_00241():
    # sdk_PermissionDenied_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_1']())
    ) is True


def test_contention_00242():
    # sdk_PermissionDenied_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_1']()) is True


def test_transport_00242():
    # sdk_PermissionDenied_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_1']()) is True


def test_admitted_00242():
    # sdk_PermissionDenied_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_1']())
    ) is True


def test_contention_00243():
    # sdk_PermissionDenied_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_1']()) is False


def test_transport_00243():
    # sdk_PermissionDenied_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_1']()) is True


def test_admitted_00243():
    # sdk_PermissionDenied_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_1']())
    ) is True


def test_contention_00244():
    # sdk_PermissionDenied_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_1']()) is False


def test_transport_00244():
    # sdk_PermissionDenied_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_1']()) is True


def test_admitted_00244():
    # sdk_PermissionDenied_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_1']())
    ) is True


def test_contention_00245():
    # sdk_PermissionDenied_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_bare_0']()) is False


def test_transport_00245():
    # sdk_PermissionDenied_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PermissionDenied_bare_0']()) is True


def test_admitted_00245():
    # sdk_PermissionDenied_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PermissionDenied_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_bare_0']())
    ) is True


def test_contention_00246():
    # sdk_PermissionDenied_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_0']()) is True


def test_transport_00246():
    # sdk_PermissionDenied_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_0']()) is True


def test_admitted_00246():
    # sdk_PermissionDenied_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_0']())
    ) is True


def test_contention_00247():
    # sdk_PermissionDenied_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_0']()) is True


def test_transport_00247():
    # sdk_PermissionDenied_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_0']()) is True


def test_admitted_00247():
    # sdk_PermissionDenied_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_0']())
    ) is True


def test_contention_00248():
    # sdk_PermissionDenied_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_0']()) is False


def test_transport_00248():
    # sdk_PermissionDenied_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_0']()) is True


def test_admitted_00248():
    # sdk_PermissionDenied_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_0']())
    ) is True


def test_contention_00249():
    # sdk_PermissionDenied_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_0']()) is False


def test_transport_00249():
    # sdk_PermissionDenied_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_0']()) is True


def test_admitted_00249():
    # sdk_PermissionDenied_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_0']())
    ) is True


def test_contention_00250():
    # sdk_PreconditionFailed_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_bare_1']()) is False


def test_transport_00250():
    # sdk_PreconditionFailed_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PreconditionFailed_bare_1']()) is True


def test_admitted_00250():
    # sdk_PreconditionFailed_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PreconditionFailed_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_bare_1']())
    ) is True


def test_contention_00251():
    # sdk_PreconditionFailed_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_1']()) is True


def test_transport_00251():
    # sdk_PreconditionFailed_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_1']()) is True


def test_admitted_00251():
    # sdk_PreconditionFailed_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_1']())
    ) is True


def test_contention_00252():
    # sdk_PreconditionFailed_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_1']()) is True


def test_transport_00252():
    # sdk_PreconditionFailed_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_1']()) is True


def test_admitted_00252():
    # sdk_PreconditionFailed_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_1']())
    ) is True


def test_contention_00253():
    # sdk_PreconditionFailed_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_1']()) is False


def test_transport_00253():
    # sdk_PreconditionFailed_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_1']()) is True


def test_admitted_00253():
    # sdk_PreconditionFailed_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_1']())
    ) is True


def test_contention_00254():
    # sdk_PreconditionFailed_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_1']()) is False


def test_transport_00254():
    # sdk_PreconditionFailed_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_1']()) is True


def test_admitted_00254():
    # sdk_PreconditionFailed_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_1']())
    ) is True


def test_contention_00255():
    # sdk_PreconditionFailed_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_bare_0']()) is False


def test_transport_00255():
    # sdk_PreconditionFailed_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PreconditionFailed_bare_0']()) is True


def test_admitted_00255():
    # sdk_PreconditionFailed_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PreconditionFailed_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_bare_0']())
    ) is True


def test_contention_00256():
    # sdk_PreconditionFailed_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_0']()) is True


def test_transport_00256():
    # sdk_PreconditionFailed_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_0']()) is True


def test_admitted_00256():
    # sdk_PreconditionFailed_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_0']())
    ) is True


def test_contention_00257():
    # sdk_PreconditionFailed_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_0']()) is True


def test_transport_00257():
    # sdk_PreconditionFailed_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_0']()) is True


def test_admitted_00257():
    # sdk_PreconditionFailed_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_0']())
    ) is True


def test_contention_00258():
    # sdk_PreconditionFailed_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_0']()) is False


def test_transport_00258():
    # sdk_PreconditionFailed_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_0']()) is True


def test_admitted_00258():
    # sdk_PreconditionFailed_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_0']())
    ) is True


def test_contention_00259():
    # sdk_PreconditionFailed_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_0']()) is False


def test_transport_00259():
    # sdk_PreconditionFailed_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_0']()) is True


def test_admitted_00259():
    # sdk_PreconditionFailed_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_0']())
    ) is True


def test_contention_00260():
    # sdk_Redirection_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_bare_1']()) is False


def test_transport_00260():
    # sdk_Redirection_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Redirection_bare_1']()) is True


def test_admitted_00260():
    # sdk_Redirection_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Redirection_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_bare_1']())
    ) is True


def test_contention_00261():
    # sdk_Redirection_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_cause_aborted_1']()) is True


def test_transport_00261():
    # sdk_Redirection_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Redirection_cause_aborted_1']()) is True


def test_admitted_00261():
    # sdk_Redirection_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Redirection_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_cause_aborted_1']())
    ) is True


def test_contention_00262():
    # sdk_Redirection_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_cause_expired_1']()) is True


def test_transport_00262():
    # sdk_Redirection_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Redirection_cause_expired_1']()) is True


def test_admitted_00262():
    # sdk_Redirection_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Redirection_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_cause_expired_1']())
    ) is True


def test_contention_00263():
    # sdk_Redirection_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_cause_timeout_1']()) is False


def test_transport_00263():
    # sdk_Redirection_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Redirection_cause_timeout_1']()) is True


def test_admitted_00263():
    # sdk_Redirection_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Redirection_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_cause_timeout_1']())
    ) is True


def test_contention_00264():
    # sdk_Redirection_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_cause_value_1']()) is False


def test_transport_00264():
    # sdk_Redirection_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Redirection_cause_value_1']()) is True


def test_admitted_00264():
    # sdk_Redirection_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Redirection_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_cause_value_1']())
    ) is True


def test_contention_00265():
    # sdk_Redirection_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_bare_0']()) is False


def test_transport_00265():
    # sdk_Redirection_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Redirection_bare_0']()) is True


def test_admitted_00265():
    # sdk_Redirection_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Redirection_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_bare_0']())
    ) is True


def test_contention_00266():
    # sdk_Redirection_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_cause_aborted_0']()) is True


def test_transport_00266():
    # sdk_Redirection_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Redirection_cause_aborted_0']()) is True


def test_admitted_00266():
    # sdk_Redirection_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Redirection_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_cause_aborted_0']())
    ) is True


def test_contention_00267():
    # sdk_Redirection_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_cause_expired_0']()) is True


def test_transport_00267():
    # sdk_Redirection_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Redirection_cause_expired_0']()) is True


def test_admitted_00267():
    # sdk_Redirection_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Redirection_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_cause_expired_0']())
    ) is True


def test_contention_00268():
    # sdk_Redirection_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_cause_timeout_0']()) is False


def test_transport_00268():
    # sdk_Redirection_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Redirection_cause_timeout_0']()) is True


def test_admitted_00268():
    # sdk_Redirection_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Redirection_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_cause_timeout_0']())
    ) is True


def test_contention_00269():
    # sdk_Redirection_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_cause_value_0']()) is False


def test_transport_00269():
    # sdk_Redirection_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Redirection_cause_value_0']()) is True


def test_admitted_00269():
    # sdk_Redirection_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Redirection_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Redirection_cause_value_0']())
    ) is True


def test_contention_00270():
    # sdk_RequestRangeNotSatisfiable_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_1']()) is False


def test_transport_00270():
    # sdk_RequestRangeNotSatisfiable_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_1']()) is True


def test_admitted_00270():
    # sdk_RequestRangeNotSatisfiable_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_1']())
    ) is True


def test_contention_00271():
    # sdk_RequestRangeNotSatisfiable_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_1']()) is True


def test_transport_00271():
    # sdk_RequestRangeNotSatisfiable_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_1']()) is True


def test_admitted_00271():
    # sdk_RequestRangeNotSatisfiable_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_1']())
    ) is True


def test_contention_00272():
    # sdk_RequestRangeNotSatisfiable_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_1']()) is True


def test_transport_00272():
    # sdk_RequestRangeNotSatisfiable_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_1']()) is True


def test_admitted_00272():
    # sdk_RequestRangeNotSatisfiable_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_1']())
    ) is True


def test_contention_00273():
    # sdk_RequestRangeNotSatisfiable_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_1']()) is False


def test_transport_00273():
    # sdk_RequestRangeNotSatisfiable_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_1']()) is True


def test_admitted_00273():
    # sdk_RequestRangeNotSatisfiable_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_1']())
    ) is True


def test_contention_00274():
    # sdk_RequestRangeNotSatisfiable_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_1']()) is False


def test_transport_00274():
    # sdk_RequestRangeNotSatisfiable_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_1']()) is True


def test_admitted_00274():
    # sdk_RequestRangeNotSatisfiable_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_1']())
    ) is True


def test_contention_00275():
    # sdk_RequestRangeNotSatisfiable_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_0']()) is False


def test_transport_00275():
    # sdk_RequestRangeNotSatisfiable_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_0']()) is True


def test_admitted_00275():
    # sdk_RequestRangeNotSatisfiable_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_0']())
    ) is True


def test_contention_00276():
    # sdk_RequestRangeNotSatisfiable_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_0']()) is True


def test_transport_00276():
    # sdk_RequestRangeNotSatisfiable_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_0']()) is True


def test_admitted_00276():
    # sdk_RequestRangeNotSatisfiable_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_0']())
    ) is True


def test_contention_00277():
    # sdk_RequestRangeNotSatisfiable_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_0']()) is True


def test_transport_00277():
    # sdk_RequestRangeNotSatisfiable_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_0']()) is True


def test_admitted_00277():
    # sdk_RequestRangeNotSatisfiable_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_0']())
    ) is True


def test_contention_00278():
    # sdk_RequestRangeNotSatisfiable_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_0']()) is False


def test_transport_00278():
    # sdk_RequestRangeNotSatisfiable_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_0']()) is True


def test_admitted_00278():
    # sdk_RequestRangeNotSatisfiable_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_0']())
    ) is True


def test_contention_00279():
    # sdk_RequestRangeNotSatisfiable_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_0']()) is False


def test_transport_00279():
    # sdk_RequestRangeNotSatisfiable_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_0']()) is True


def test_admitted_00279():
    # sdk_RequestRangeNotSatisfiable_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_0']())
    ) is True


def test_contention_00280():
    # sdk_ResourceExhausted_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_bare_1']()) is False


def test_transport_00280():
    # sdk_ResourceExhausted_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResourceExhausted_bare_1']()) is True


def test_admitted_00280():
    # sdk_ResourceExhausted_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResourceExhausted_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_bare_1']())
    ) is True


def test_contention_00281():
    # sdk_ResourceExhausted_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_1']()) is True


def test_transport_00281():
    # sdk_ResourceExhausted_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_1']()) is True


def test_admitted_00281():
    # sdk_ResourceExhausted_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_1']())
    ) is True


def test_contention_00282():
    # sdk_ResourceExhausted_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_1']()) is True


def test_transport_00282():
    # sdk_ResourceExhausted_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_1']()) is True


def test_admitted_00282():
    # sdk_ResourceExhausted_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_1']())
    ) is True


def test_contention_00283():
    # sdk_ResourceExhausted_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_1']()) is False


def test_transport_00283():
    # sdk_ResourceExhausted_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_1']()) is True


def test_admitted_00283():
    # sdk_ResourceExhausted_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_1']())
    ) is True


def test_contention_00284():
    # sdk_ResourceExhausted_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_1']()) is False


def test_transport_00284():
    # sdk_ResourceExhausted_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_1']()) is True


def test_admitted_00284():
    # sdk_ResourceExhausted_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_1']())
    ) is True


def test_contention_00285():
    # sdk_ResourceExhausted_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_bare_0']()) is False


def test_transport_00285():
    # sdk_ResourceExhausted_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResourceExhausted_bare_0']()) is True


def test_admitted_00285():
    # sdk_ResourceExhausted_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResourceExhausted_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_bare_0']())
    ) is True


def test_contention_00286():
    # sdk_ResourceExhausted_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_0']()) is True


def test_transport_00286():
    # sdk_ResourceExhausted_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_0']()) is True


def test_admitted_00286():
    # sdk_ResourceExhausted_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_0']())
    ) is True


def test_contention_00287():
    # sdk_ResourceExhausted_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_0']()) is True


def test_transport_00287():
    # sdk_ResourceExhausted_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_0']()) is True


def test_admitted_00287():
    # sdk_ResourceExhausted_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_0']())
    ) is True


def test_contention_00288():
    # sdk_ResourceExhausted_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_0']()) is False


def test_transport_00288():
    # sdk_ResourceExhausted_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_0']()) is True


def test_admitted_00288():
    # sdk_ResourceExhausted_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_0']())
    ) is True


def test_contention_00289():
    # sdk_ResourceExhausted_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_0']()) is False


def test_transport_00289():
    # sdk_ResourceExhausted_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_0']()) is True


def test_admitted_00289():
    # sdk_ResourceExhausted_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_0']())
    ) is True


def test_contention_00290():
    # sdk_ResumeIncomplete_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_1']()) is False


def test_transport_00290():
    # sdk_ResumeIncomplete_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_1']()) is True


def test_admitted_00290():
    # sdk_ResumeIncomplete_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_1']())
    ) is True


def test_contention_00291():
    # sdk_ResumeIncomplete_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_1']()) is True


def test_transport_00291():
    # sdk_ResumeIncomplete_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_1']()) is True


def test_admitted_00291():
    # sdk_ResumeIncomplete_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_1']())
    ) is True


def test_contention_00292():
    # sdk_ResumeIncomplete_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_1']()) is True


def test_transport_00292():
    # sdk_ResumeIncomplete_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_1']()) is True


def test_admitted_00292():
    # sdk_ResumeIncomplete_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_1']())
    ) is True


def test_contention_00293():
    # sdk_ResumeIncomplete_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_1']()) is False


def test_transport_00293():
    # sdk_ResumeIncomplete_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_1']()) is True


def test_admitted_00293():
    # sdk_ResumeIncomplete_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_1']())
    ) is True


def test_contention_00294():
    # sdk_ResumeIncomplete_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_1']()) is False


def test_transport_00294():
    # sdk_ResumeIncomplete_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_1']()) is True


def test_admitted_00294():
    # sdk_ResumeIncomplete_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_1']())
    ) is True


def test_contention_00295():
    # sdk_ResumeIncomplete_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_0']()) is False


def test_transport_00295():
    # sdk_ResumeIncomplete_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_0']()) is True


def test_admitted_00295():
    # sdk_ResumeIncomplete_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_0']())
    ) is True


def test_contention_00296():
    # sdk_ResumeIncomplete_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_0']()) is True


def test_transport_00296():
    # sdk_ResumeIncomplete_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_0']()) is True


def test_admitted_00296():
    # sdk_ResumeIncomplete_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_0']())
    ) is True


def test_contention_00297():
    # sdk_ResumeIncomplete_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_0']()) is True


def test_transport_00297():
    # sdk_ResumeIncomplete_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_0']()) is True


def test_admitted_00297():
    # sdk_ResumeIncomplete_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_0']())
    ) is True


def test_contention_00298():
    # sdk_ResumeIncomplete_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_0']()) is False


def test_transport_00298():
    # sdk_ResumeIncomplete_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_0']()) is True


def test_admitted_00298():
    # sdk_ResumeIncomplete_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_0']())
    ) is True


def test_contention_00299():
    # sdk_ResumeIncomplete_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_0']()) is False


def test_transport_00299():
    # sdk_ResumeIncomplete_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_0']()) is True


def test_admitted_00299():
    # sdk_ResumeIncomplete_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_0']())
    ) is True


def test_contention_00300():
    # sdk_ServerError_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_bare_1']()) is False


def test_transport_00300():
    # sdk_ServerError_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServerError_bare_1']()) is True


def test_admitted_00300():
    # sdk_ServerError_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServerError_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_bare_1']())
    ) is True


def test_contention_00301():
    # sdk_ServerError_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_cause_aborted_1']()) is True


def test_transport_00301():
    # sdk_ServerError_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServerError_cause_aborted_1']()) is True


def test_admitted_00301():
    # sdk_ServerError_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServerError_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_cause_aborted_1']())
    ) is True


def test_contention_00302():
    # sdk_ServerError_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_cause_expired_1']()) is True


def test_transport_00302():
    # sdk_ServerError_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServerError_cause_expired_1']()) is True


def test_admitted_00302():
    # sdk_ServerError_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServerError_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_cause_expired_1']())
    ) is True


def test_contention_00303():
    # sdk_ServerError_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_cause_timeout_1']()) is False


def test_transport_00303():
    # sdk_ServerError_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServerError_cause_timeout_1']()) is True


def test_admitted_00303():
    # sdk_ServerError_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServerError_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_cause_timeout_1']())
    ) is True


def test_contention_00304():
    # sdk_ServerError_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_cause_value_1']()) is False


def test_transport_00304():
    # sdk_ServerError_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServerError_cause_value_1']()) is True


def test_admitted_00304():
    # sdk_ServerError_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServerError_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_cause_value_1']())
    ) is True


def test_contention_00305():
    # sdk_ServerError_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_bare_0']()) is False


def test_transport_00305():
    # sdk_ServerError_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServerError_bare_0']()) is True


def test_admitted_00305():
    # sdk_ServerError_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServerError_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_bare_0']())
    ) is True


def test_contention_00306():
    # sdk_ServerError_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_cause_aborted_0']()) is True


def test_transport_00306():
    # sdk_ServerError_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServerError_cause_aborted_0']()) is True


def test_admitted_00306():
    # sdk_ServerError_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServerError_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_cause_aborted_0']())
    ) is True


def test_contention_00307():
    # sdk_ServerError_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_cause_expired_0']()) is True


def test_transport_00307():
    # sdk_ServerError_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServerError_cause_expired_0']()) is True


def test_admitted_00307():
    # sdk_ServerError_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServerError_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_cause_expired_0']())
    ) is True


def test_contention_00308():
    # sdk_ServerError_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_cause_timeout_0']()) is False


def test_transport_00308():
    # sdk_ServerError_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServerError_cause_timeout_0']()) is True


def test_admitted_00308():
    # sdk_ServerError_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServerError_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_cause_timeout_0']())
    ) is True


def test_contention_00309():
    # sdk_ServerError_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_cause_value_0']()) is False


def test_transport_00309():
    # sdk_ServerError_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServerError_cause_value_0']()) is True


def test_admitted_00309():
    # sdk_ServerError_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServerError_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServerError_cause_value_0']())
    ) is True


def test_contention_00310():
    # sdk_ServiceUnavailable_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_1']()) is False


def test_transport_00310():
    # sdk_ServiceUnavailable_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_1']()) is True


def test_admitted_00310():
    # sdk_ServiceUnavailable_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_1']())
    ) is True


def test_contention_00311():
    # sdk_ServiceUnavailable_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_1']()) is True


def test_transport_00311():
    # sdk_ServiceUnavailable_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_1']()) is True


def test_admitted_00311():
    # sdk_ServiceUnavailable_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_1']())
    ) is True


def test_contention_00312():
    # sdk_ServiceUnavailable_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_1']()) is True


def test_transport_00312():
    # sdk_ServiceUnavailable_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_1']()) is True


def test_admitted_00312():
    # sdk_ServiceUnavailable_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_1']())
    ) is True


def test_contention_00313():
    # sdk_ServiceUnavailable_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_1']()) is False


def test_transport_00313():
    # sdk_ServiceUnavailable_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_1']()) is True


def test_admitted_00313():
    # sdk_ServiceUnavailable_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_1']())
    ) is True


def test_contention_00314():
    # sdk_ServiceUnavailable_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_1']()) is False


def test_transport_00314():
    # sdk_ServiceUnavailable_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_1']()) is True


def test_admitted_00314():
    # sdk_ServiceUnavailable_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_1']())
    ) is True


def test_contention_00315():
    # sdk_ServiceUnavailable_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_0']()) is False


def test_transport_00315():
    # sdk_ServiceUnavailable_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_0']()) is True


def test_admitted_00315():
    # sdk_ServiceUnavailable_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_0']())
    ) is True


def test_contention_00316():
    # sdk_ServiceUnavailable_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_0']()) is True


def test_transport_00316():
    # sdk_ServiceUnavailable_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_0']()) is True


def test_admitted_00316():
    # sdk_ServiceUnavailable_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_0']())
    ) is True


def test_contention_00317():
    # sdk_ServiceUnavailable_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_0']()) is True


def test_transport_00317():
    # sdk_ServiceUnavailable_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_0']()) is True


def test_admitted_00317():
    # sdk_ServiceUnavailable_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_0']())
    ) is True


def test_contention_00318():
    # sdk_ServiceUnavailable_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_0']()) is False


def test_transport_00318():
    # sdk_ServiceUnavailable_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_0']()) is True


def test_admitted_00318():
    # sdk_ServiceUnavailable_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_0']())
    ) is True


def test_contention_00319():
    # sdk_ServiceUnavailable_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_0']()) is False


def test_transport_00319():
    # sdk_ServiceUnavailable_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_0']()) is True


def test_admitted_00319():
    # sdk_ServiceUnavailable_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_0']())
    ) is True


def test_contention_00320():
    # sdk_TemporaryRedirect_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_1']()) is False


def test_transport_00320():
    # sdk_TemporaryRedirect_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_1']()) is True


def test_admitted_00320():
    # sdk_TemporaryRedirect_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_1']())
    ) is True


def test_contention_00321():
    # sdk_TemporaryRedirect_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_1']()) is True


def test_transport_00321():
    # sdk_TemporaryRedirect_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_1']()) is True


def test_admitted_00321():
    # sdk_TemporaryRedirect_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_1']())
    ) is True


def test_contention_00322():
    # sdk_TemporaryRedirect_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_1']()) is True


def test_transport_00322():
    # sdk_TemporaryRedirect_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_1']()) is True


def test_admitted_00322():
    # sdk_TemporaryRedirect_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_1']())
    ) is True


def test_contention_00323():
    # sdk_TemporaryRedirect_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_1']()) is False


def test_transport_00323():
    # sdk_TemporaryRedirect_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_1']()) is True


def test_admitted_00323():
    # sdk_TemporaryRedirect_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_1']())
    ) is True


def test_contention_00324():
    # sdk_TemporaryRedirect_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_1']()) is False


def test_transport_00324():
    # sdk_TemporaryRedirect_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_1']()) is True


def test_admitted_00324():
    # sdk_TemporaryRedirect_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_1']())
    ) is True


def test_contention_00325():
    # sdk_TemporaryRedirect_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_0']()) is False


def test_transport_00325():
    # sdk_TemporaryRedirect_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_0']()) is True


def test_admitted_00325():
    # sdk_TemporaryRedirect_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_0']())
    ) is True


def test_contention_00326():
    # sdk_TemporaryRedirect_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_0']()) is True


def test_transport_00326():
    # sdk_TemporaryRedirect_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_0']()) is True


def test_admitted_00326():
    # sdk_TemporaryRedirect_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_0']())
    ) is True


def test_contention_00327():
    # sdk_TemporaryRedirect_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_0']()) is True


def test_transport_00327():
    # sdk_TemporaryRedirect_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_0']()) is True


def test_admitted_00327():
    # sdk_TemporaryRedirect_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_0']())
    ) is True


def test_contention_00328():
    # sdk_TemporaryRedirect_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_0']()) is False


def test_transport_00328():
    # sdk_TemporaryRedirect_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_0']()) is True


def test_admitted_00328():
    # sdk_TemporaryRedirect_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_0']())
    ) is True


def test_contention_00329():
    # sdk_TemporaryRedirect_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_0']()) is False


def test_transport_00329():
    # sdk_TemporaryRedirect_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_0']()) is True


def test_admitted_00329():
    # sdk_TemporaryRedirect_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_0']())
    ) is True


def test_contention_00330():
    # sdk_TooManyRequests_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_bare_1']()) is False


def test_transport_00330():
    # sdk_TooManyRequests_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TooManyRequests_bare_1']()) is True


def test_admitted_00330():
    # sdk_TooManyRequests_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TooManyRequests_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_bare_1']())
    ) is True


def test_contention_00331():
    # sdk_TooManyRequests_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_1']()) is True


def test_transport_00331():
    # sdk_TooManyRequests_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_1']()) is True


def test_admitted_00331():
    # sdk_TooManyRequests_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_1']())
    ) is True


def test_contention_00332():
    # sdk_TooManyRequests_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_1']()) is True


def test_transport_00332():
    # sdk_TooManyRequests_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_1']()) is True


def test_admitted_00332():
    # sdk_TooManyRequests_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_1']())
    ) is True


def test_contention_00333():
    # sdk_TooManyRequests_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_1']()) is False


def test_transport_00333():
    # sdk_TooManyRequests_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_1']()) is True


def test_admitted_00333():
    # sdk_TooManyRequests_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_1']())
    ) is True


def test_contention_00334():
    # sdk_TooManyRequests_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_1']()) is False


def test_transport_00334():
    # sdk_TooManyRequests_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_1']()) is True


def test_admitted_00334():
    # sdk_TooManyRequests_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_1']())
    ) is True


def test_contention_00335():
    # sdk_TooManyRequests_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_bare_0']()) is False


def test_transport_00335():
    # sdk_TooManyRequests_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TooManyRequests_bare_0']()) is True


def test_admitted_00335():
    # sdk_TooManyRequests_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TooManyRequests_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_bare_0']())
    ) is True


def test_contention_00336():
    # sdk_TooManyRequests_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_0']()) is True


def test_transport_00336():
    # sdk_TooManyRequests_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_0']()) is True


def test_admitted_00336():
    # sdk_TooManyRequests_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_0']())
    ) is True


def test_contention_00337():
    # sdk_TooManyRequests_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_0']()) is True


def test_transport_00337():
    # sdk_TooManyRequests_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_0']()) is True


def test_admitted_00337():
    # sdk_TooManyRequests_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_0']())
    ) is True


def test_contention_00338():
    # sdk_TooManyRequests_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_0']()) is False


def test_transport_00338():
    # sdk_TooManyRequests_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_0']()) is True


def test_admitted_00338():
    # sdk_TooManyRequests_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_0']())
    ) is True


def test_contention_00339():
    # sdk_TooManyRequests_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_0']()) is False


def test_transport_00339():
    # sdk_TooManyRequests_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_0']()) is True


def test_admitted_00339():
    # sdk_TooManyRequests_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_0']())
    ) is True


def test_contention_00340():
    # sdk_Unauthenticated_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_bare_1']()) is False


def test_transport_00340():
    # sdk_Unauthenticated_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthenticated_bare_1']()) is True


def test_admitted_00340():
    # sdk_Unauthenticated_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthenticated_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_bare_1']())
    ) is True


def test_contention_00341():
    # sdk_Unauthenticated_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_1']()) is True


def test_transport_00341():
    # sdk_Unauthenticated_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_1']()) is True


def test_admitted_00341():
    # sdk_Unauthenticated_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_1']())
    ) is True


def test_contention_00342():
    # sdk_Unauthenticated_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_1']()) is True


def test_transport_00342():
    # sdk_Unauthenticated_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_1']()) is True


def test_admitted_00342():
    # sdk_Unauthenticated_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_1']())
    ) is True


def test_contention_00343():
    # sdk_Unauthenticated_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_1']()) is False


def test_transport_00343():
    # sdk_Unauthenticated_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_1']()) is True


def test_admitted_00343():
    # sdk_Unauthenticated_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_1']())
    ) is True


def test_contention_00344():
    # sdk_Unauthenticated_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_1']()) is False


def test_transport_00344():
    # sdk_Unauthenticated_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_1']()) is True


def test_admitted_00344():
    # sdk_Unauthenticated_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_1']())
    ) is True


def test_contention_00345():
    # sdk_Unauthenticated_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_bare_0']()) is False


def test_transport_00345():
    # sdk_Unauthenticated_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthenticated_bare_0']()) is True


def test_admitted_00345():
    # sdk_Unauthenticated_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthenticated_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_bare_0']())
    ) is True


def test_contention_00346():
    # sdk_Unauthenticated_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_0']()) is True


def test_transport_00346():
    # sdk_Unauthenticated_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_0']()) is True


def test_admitted_00346():
    # sdk_Unauthenticated_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_0']())
    ) is True


def test_contention_00347():
    # sdk_Unauthenticated_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_0']()) is True


def test_transport_00347():
    # sdk_Unauthenticated_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_0']()) is True


def test_admitted_00347():
    # sdk_Unauthenticated_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_0']())
    ) is True


def test_contention_00348():
    # sdk_Unauthenticated_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_0']()) is False


def test_transport_00348():
    # sdk_Unauthenticated_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_0']()) is True


def test_admitted_00348():
    # sdk_Unauthenticated_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_0']())
    ) is True


def test_contention_00349():
    # sdk_Unauthenticated_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_0']()) is False


def test_transport_00349():
    # sdk_Unauthenticated_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_0']()) is True


def test_admitted_00349():
    # sdk_Unauthenticated_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_0']())
    ) is True


def test_contention_00350():
    # sdk_Unauthorized_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_bare_1']()) is False


def test_transport_00350():
    # sdk_Unauthorized_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthorized_bare_1']()) is True


def test_admitted_00350():
    # sdk_Unauthorized_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthorized_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_bare_1']())
    ) is True


def test_contention_00351():
    # sdk_Unauthorized_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_1']()) is True


def test_transport_00351():
    # sdk_Unauthorized_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_1']()) is True


def test_admitted_00351():
    # sdk_Unauthorized_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_1']())
    ) is True


def test_contention_00352():
    # sdk_Unauthorized_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_1']()) is True


def test_transport_00352():
    # sdk_Unauthorized_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_1']()) is True


def test_admitted_00352():
    # sdk_Unauthorized_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_1']())
    ) is True


def test_contention_00353():
    # sdk_Unauthorized_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_1']()) is False


def test_transport_00353():
    # sdk_Unauthorized_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_1']()) is True


def test_admitted_00353():
    # sdk_Unauthorized_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_1']())
    ) is True


def test_contention_00354():
    # sdk_Unauthorized_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_cause_value_1']()) is False


def test_transport_00354():
    # sdk_Unauthorized_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthorized_cause_value_1']()) is True


def test_admitted_00354():
    # sdk_Unauthorized_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthorized_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_cause_value_1']())
    ) is True


def test_contention_00355():
    # sdk_Unauthorized_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_bare_0']()) is False


def test_transport_00355():
    # sdk_Unauthorized_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthorized_bare_0']()) is True


def test_admitted_00355():
    # sdk_Unauthorized_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthorized_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_bare_0']())
    ) is True


def test_contention_00356():
    # sdk_Unauthorized_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_0']()) is True


def test_transport_00356():
    # sdk_Unauthorized_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_0']()) is True


def test_admitted_00356():
    # sdk_Unauthorized_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_0']())
    ) is True


def test_contention_00357():
    # sdk_Unauthorized_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_0']()) is True


def test_transport_00357():
    # sdk_Unauthorized_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_0']()) is True


def test_admitted_00357():
    # sdk_Unauthorized_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_0']())
    ) is True


def test_contention_00358():
    # sdk_Unauthorized_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_0']()) is False


def test_transport_00358():
    # sdk_Unauthorized_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_0']()) is True


def test_admitted_00358():
    # sdk_Unauthorized_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_0']())
    ) is True


def test_contention_00359():
    # sdk_Unauthorized_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_cause_value_0']()) is False


def test_transport_00359():
    # sdk_Unauthorized_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthorized_cause_value_0']()) is True


def test_admitted_00359():
    # sdk_Unauthorized_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unauthorized_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unauthorized_cause_value_0']())
    ) is True


def test_contention_00360():
    # sdk_Unknown_bare_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_bare_1']()) is False


def test_transport_00360():
    # sdk_Unknown_bare_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unknown_bare_1']()) is True


def test_admitted_00360():
    # sdk_Unknown_bare_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unknown_bare_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_bare_1']())
    ) is True


def test_contention_00361():
    # sdk_Unknown_cause_aborted_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_cause_aborted_1']()) is True


def test_transport_00361():
    # sdk_Unknown_cause_aborted_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unknown_cause_aborted_1']()) is True


def test_admitted_00361():
    # sdk_Unknown_cause_aborted_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unknown_cause_aborted_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_cause_aborted_1']())
    ) is True


def test_contention_00362():
    # sdk_Unknown_cause_expired_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_cause_expired_1']()) is True


def test_transport_00362():
    # sdk_Unknown_cause_expired_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unknown_cause_expired_1']()) is True


def test_admitted_00362():
    # sdk_Unknown_cause_expired_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unknown_cause_expired_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_cause_expired_1']())
    ) is True


def test_contention_00363():
    # sdk_Unknown_cause_timeout_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_cause_timeout_1']()) is False


def test_transport_00363():
    # sdk_Unknown_cause_timeout_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unknown_cause_timeout_1']()) is True


def test_admitted_00363():
    # sdk_Unknown_cause_timeout_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unknown_cause_timeout_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_cause_timeout_1']())
    ) is True


def test_contention_00364():
    # sdk_Unknown_cause_value_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_cause_value_1']()) is False


def test_transport_00364():
    # sdk_Unknown_cause_value_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unknown_cause_value_1']()) is True


def test_admitted_00364():
    # sdk_Unknown_cause_value_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unknown_cause_value_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_cause_value_1']())
    ) is True


def test_contention_00365():
    # sdk_Unknown_bare_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_bare_0']()) is False


def test_transport_00365():
    # sdk_Unknown_bare_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unknown_bare_0']()) is True


def test_admitted_00365():
    # sdk_Unknown_bare_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unknown_bare_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_bare_0']())
    ) is True


def test_contention_00366():
    # sdk_Unknown_cause_aborted_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_cause_aborted_0']()) is True


def test_transport_00366():
    # sdk_Unknown_cause_aborted_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unknown_cause_aborted_0']()) is True


def test_admitted_00366():
    # sdk_Unknown_cause_aborted_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unknown_cause_aborted_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_cause_aborted_0']())
    ) is True


def test_contention_00367():
    # sdk_Unknown_cause_expired_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_cause_expired_0']()) is True


def test_transport_00367():
    # sdk_Unknown_cause_expired_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unknown_cause_expired_0']()) is True


def test_admitted_00367():
    # sdk_Unknown_cause_expired_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unknown_cause_expired_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_cause_expired_0']())
    ) is True


def test_contention_00368():
    # sdk_Unknown_cause_timeout_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_cause_timeout_0']()) is False


def test_transport_00368():
    # sdk_Unknown_cause_timeout_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unknown_cause_timeout_0']()) is True


def test_admitted_00368():
    # sdk_Unknown_cause_timeout_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unknown_cause_timeout_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_cause_timeout_0']())
    ) is True


def test_contention_00369():
    # sdk_Unknown_cause_value_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_cause_value_0']()) is False


def test_transport_00369():
    # sdk_Unknown_cause_value_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unknown_cause_value_0']()) is True


def test_admitted_00369():
    # sdk_Unknown_cause_value_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['sdk_Unknown_cause_value_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['sdk_Unknown_cause_value_0']())
    ) is True


def test_contention_00370():
    # custody_staged_audio
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_staged_audio']()) is False


def test_transport_00370():
    # custody_staged_audio
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_staged_audio']()) is False


def test_admitted_00370():
    # custody_staged_audio
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_staged_audio']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_staged_audio']())
    ) is False


def test_contention_00371():
    # custody_staged_audio_cause_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_staged_audio_cause_aborted']()) is True


def test_transport_00371():
    # custody_staged_audio_cause_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_staged_audio_cause_aborted']()) is False


def test_admitted_00371():
    # custody_staged_audio_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_staged_audio_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_staged_audio_cause_aborted']())
    ) is True


def test_contention_00372():
    # custody_staged_artifact
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_staged_artifact']()) is False


def test_transport_00372():
    # custody_staged_artifact
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_staged_artifact']()) is False


def test_admitted_00372():
    # custody_staged_artifact
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_staged_artifact']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_staged_artifact']())
    ) is False


def test_contention_00373():
    # custody_staged_artifact_cause_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_staged_artifact_cause_aborted']()) is True


def test_transport_00373():
    # custody_staged_artifact_cause_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_staged_artifact_cause_aborted']()) is False


def test_admitted_00373():
    # custody_staged_artifact_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_staged_artifact_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_staged_artifact_cause_aborted']())
    ) is True


def test_contention_00374():
    # custody_retained_audio
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_retained_audio']()) is False


def test_transport_00374():
    # custody_retained_audio
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_retained_audio']()) is False


def test_admitted_00374():
    # custody_retained_audio
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_retained_audio']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_retained_audio']())
    ) is False


def test_contention_00375():
    # custody_retained_audio_cause_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_retained_audio_cause_aborted']()) is True


def test_transport_00375():
    # custody_retained_audio_cause_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_retained_audio_cause_aborted']()) is False


def test_admitted_00375():
    # custody_retained_audio_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_retained_audio_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_retained_audio_cause_aborted']())
    ) is True


def test_contention_00376():
    # custody_retained_manifest
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_retained_manifest']()) is False


def test_transport_00376():
    # custody_retained_manifest
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_retained_manifest']()) is False


def test_admitted_00376():
    # custody_retained_manifest
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_retained_manifest']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_retained_manifest']())
    ) is False


def test_contention_00377():
    # custody_retained_manifest_cause_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_retained_manifest_cause_aborted']()) is True


def test_transport_00377():
    # custody_retained_manifest_cause_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_retained_manifest_cause_aborted']()) is False


def test_admitted_00377():
    # custody_retained_manifest_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_retained_manifest_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_retained_manifest_cause_aborted']())
    ) is True


def test_contention_00378():
    # custody_decoded_mismatch
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_decoded_mismatch']()) is False


def test_transport_00378():
    # custody_decoded_mismatch
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_decoded_mismatch']()) is False


def test_admitted_00378():
    # custody_decoded_mismatch
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_decoded_mismatch']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_decoded_mismatch']())
    ) is False


def test_contention_00379():
    # custody_decoded_mismatch_cause_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_decoded_mismatch_cause_aborted']()) is True


def test_transport_00379():
    # custody_decoded_mismatch_cause_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_decoded_mismatch_cause_aborted']()) is False


def test_admitted_00379():
    # custody_decoded_mismatch_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_decoded_mismatch_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_decoded_mismatch_cause_aborted']())
    ) is True


def test_contention_00380():
    # custody_permission
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_permission']()) is False


def test_transport_00380():
    # custody_permission
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_permission']()) is False


def test_admitted_00380():
    # custody_permission
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_permission']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_permission']())
    ) is False


def test_contention_00381():
    # custody_permission_cause_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_permission_cause_aborted']()) is True


def test_transport_00381():
    # custody_permission_cause_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_permission_cause_aborted']()) is False


def test_admitted_00381():
    # custody_permission_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_permission_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_permission_cause_aborted']())
    ) is True


def test_contention_00382():
    # custody_os_error
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_os_error']()) is False


def test_transport_00382():
    # custody_os_error
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_os_error']()) is False


def test_admitted_00382():
    # custody_os_error
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_os_error']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_os_error']())
    ) is False


def test_contention_00383():
    # custody_os_error_cause_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_os_error_cause_aborted']()) is True


def test_transport_00383():
    # custody_os_error_cause_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_os_error_cause_aborted']()) is False


def test_admitted_00383():
    # custody_os_error_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_os_error_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_os_error_cause_aborted']())
    ) is True


def test_contention_00384():
    # custody_runtime
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_runtime']()) is False


def test_transport_00384():
    # custody_runtime
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_runtime']()) is False


def test_admitted_00384():
    # custody_runtime
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_runtime']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_runtime']())
    ) is False


def test_contention_00385():
    # custody_runtime_cause_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_runtime_cause_aborted']()) is True


def test_transport_00385():
    # custody_runtime_cause_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_runtime_cause_aborted']()) is False


def test_admitted_00385():
    # custody_runtime_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_runtime_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_runtime_cause_aborted']())
    ) is True


def test_contention_00386():
    # custody_value_error
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_value_error']()) is False


def test_transport_00386():
    # custody_value_error
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_value_error']()) is False


def test_admitted_00386():
    # custody_value_error
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_value_error']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_value_error']())
    ) is False


def test_contention_00387():
    # custody_value_error_cause_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_value_error_cause_aborted']()) is True


def test_transport_00387():
    # custody_value_error_cause_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_value_error_cause_aborted']()) is False


def test_admitted_00387():
    # custody_value_error_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_value_error_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_value_error_cause_aborted']())
    ) is True


def test_contention_00388():
    # custody_key_error
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_key_error']()) is False


def test_transport_00388():
    # custody_key_error
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_key_error']()) is False


def test_admitted_00388():
    # custody_key_error
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_key_error']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_key_error']())
    ) is False


def test_contention_00389():
    # custody_key_error_cause_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_key_error_cause_aborted']()) is True


def test_transport_00389():
    # custody_key_error_cause_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_key_error_cause_aborted']()) is False


def test_admitted_00389():
    # custody_key_error_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_key_error_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_key_error_cause_aborted']())
    ) is True


def test_contention_00390():
    # custody_type_error
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_type_error']()) is False


def test_transport_00390():
    # custody_type_error
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_type_error']()) is False


def test_admitted_00390():
    # custody_type_error
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_type_error']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_type_error']())
    ) is False


def test_contention_00391():
    # custody_type_error_cause_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_type_error_cause_aborted']()) is True


def test_transport_00391():
    # custody_type_error_cause_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_type_error_cause_aborted']()) is False


def test_admitted_00391():
    # custody_type_error_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_type_error_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_type_error_cause_aborted']())
    ) is True


def test_contention_00392():
    # custody_index_error
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_index_error']()) is False


def test_transport_00392():
    # custody_index_error
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_index_error']()) is False


def test_admitted_00392():
    # custody_index_error
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_index_error']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_index_error']())
    ) is False


def test_contention_00393():
    # custody_index_error_cause_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_index_error_cause_aborted']()) is True


def test_transport_00393():
    # custody_index_error_cause_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_index_error_cause_aborted']()) is False


def test_admitted_00393():
    # custody_index_error_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_index_error_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_index_error_cause_aborted']())
    ) is True


def test_contention_00394():
    # custody_zero_div
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_zero_div']()) is False


def test_transport_00394():
    # custody_zero_div
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_zero_div']()) is False


def test_admitted_00394():
    # custody_zero_div
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_zero_div']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_zero_div']())
    ) is False


def test_contention_00395():
    # custody_zero_div_cause_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_zero_div_cause_aborted']()) is True


def test_transport_00395():
    # custody_zero_div_cause_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_zero_div_cause_aborted']()) is False


def test_admitted_00395():
    # custody_zero_div_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_zero_div_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_zero_div_cause_aborted']())
    ) is True


def test_contention_00396():
    # custody_arith
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_arith']()) is False


def test_transport_00396():
    # custody_arith
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_arith']()) is False


def test_admitted_00396():
    # custody_arith
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_arith']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_arith']())
    ) is False


def test_contention_00397():
    # custody_arith_cause_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_arith_cause_aborted']()) is True


def test_transport_00397():
    # custody_arith_cause_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_arith_cause_aborted']()) is False


def test_admitted_00397():
    # custody_arith_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_arith_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_arith_cause_aborted']())
    ) is True


def test_contention_00398():
    # custody_lookup
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_lookup']()) is False


def test_transport_00398():
    # custody_lookup
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_lookup']()) is False


def test_admitted_00398():
    # custody_lookup
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_lookup']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_lookup']())
    ) is False


def test_contention_00399():
    # custody_lookup_cause_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_lookup_cause_aborted']()) is True


def test_transport_00399():
    # custody_lookup_cause_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_lookup_cause_aborted']()) is False


def test_admitted_00399():
    # custody_lookup_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_lookup_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_lookup_cause_aborted']())
    ) is True


def test_contention_00400():
    # custody_notimpl
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_notimpl']()) is False


def test_transport_00400():
    # custody_notimpl
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_notimpl']()) is False


def test_admitted_00400():
    # custody_notimpl
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_notimpl']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_notimpl']())
    ) is False


def test_contention_00401():
    # custody_notimpl_cause_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_notimpl_cause_aborted']()) is True


def test_transport_00401():
    # custody_notimpl_cause_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_notimpl_cause_aborted']()) is False


def test_admitted_00401():
    # custody_notimpl_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_notimpl_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_notimpl_cause_aborted']())
    ) is True


def test_contention_00402():
    # custody_recursion
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_recursion']()) is False


def test_transport_00402():
    # custody_recursion
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_recursion']()) is False


def test_admitted_00402():
    # custody_recursion
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_recursion']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_recursion']())
    ) is False


def test_contention_00403():
    # custody_recursion_cause_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_recursion_cause_aborted']()) is True


def test_transport_00403():
    # custody_recursion_cause_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_recursion_cause_aborted']()) is False


def test_admitted_00403():
    # custody_recursion_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_recursion_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_recursion_cause_aborted']())
    ) is True


def test_contention_00404():
    # custody_eof
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_eof']()) is False


def test_transport_00404():
    # custody_eof
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_eof']()) is False


def test_admitted_00404():
    # custody_eof
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_eof']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_eof']())
    ) is False


def test_contention_00405():
    # custody_eof_cause_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_eof_cause_aborted']()) is True


def test_transport_00405():
    # custody_eof_cause_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_eof_cause_aborted']()) is False


def test_admitted_00405():
    # custody_eof_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_eof_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_eof_cause_aborted']())
    ) is True


def test_contention_00406():
    # custody_batch_validation_unsupported_language
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_unsupported_language']()) is False


def test_transport_00406():
    # custody_batch_validation_unsupported_language
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_unsupported_language']()) is False


def test_admitted_00406():
    # custody_batch_validation_unsupported_language
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_unsupported_language']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_unsupported_language']())
    ) is False


def test_contention_00407():
    # custody_batch_validation_unsupported_language_cause_aborted
    assert (
        bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_unsupported_language_cause_aborted']())
        is True
    )


def test_transport_00407():
    # custody_batch_validation_unsupported_language_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(
            _SHAPE_BUILDERS['custody_batch_validation_unsupported_language_cause_aborted']()
        )
        is False
    )


def test_admitted_00407():
    # custody_batch_validation_unsupported_language_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(
            _SHAPE_BUILDERS['custody_batch_validation_unsupported_language_cause_aborted']()
        )
        or bp.persist_loss_is_contention(
            _SHAPE_BUILDERS['custody_batch_validation_unsupported_language_cause_aborted']()
        )
    ) is True


def test_contention_00408():
    # custody_batch_validation_word_shape
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_word_shape']()) is False


def test_transport_00408():
    # custody_batch_validation_word_shape
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_word_shape']()) is False


def test_admitted_00408():
    # custody_batch_validation_word_shape
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_word_shape']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_word_shape']())
    ) is False


def test_contention_00409():
    # custody_batch_validation_word_shape_cause_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_word_shape_cause_aborted']()) is True


def test_transport_00409():
    # custody_batch_validation_word_shape_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_word_shape_cause_aborted']()) is False
    )


def test_admitted_00409():
    # custody_batch_validation_word_shape_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_word_shape_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_word_shape_cause_aborted']())
    ) is True


def test_contention_00410():
    # custody_batch_validation_word_clock
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_word_clock']()) is False


def test_transport_00410():
    # custody_batch_validation_word_clock
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_word_clock']()) is False


def test_admitted_00410():
    # custody_batch_validation_word_clock
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_word_clock']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_word_clock']())
    ) is False


def test_contention_00411():
    # custody_batch_validation_word_clock_cause_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_word_clock_cause_aborted']()) is True


def test_transport_00411():
    # custody_batch_validation_word_clock_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_word_clock_cause_aborted']()) is False
    )


def test_admitted_00411():
    # custody_batch_validation_word_clock_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_word_clock_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_word_clock_cause_aborted']())
    ) is True


def test_contention_00412():
    # custody_batch_validation_word_sequence
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_word_sequence']()) is False


def test_transport_00412():
    # custody_batch_validation_word_sequence
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_word_sequence']()) is False


def test_admitted_00412():
    # custody_batch_validation_word_sequence
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_word_sequence']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_word_sequence']())
    ) is False


def test_contention_00413():
    # custody_batch_validation_word_sequence_cause_aborted
    assert (
        bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_word_sequence_cause_aborted']()) is True
    )


def test_transport_00413():
    # custody_batch_validation_word_sequence_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_word_sequence_cause_aborted']())
        is False
    )


def test_admitted_00413():
    # custody_batch_validation_word_sequence_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_word_sequence_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_word_sequence_cause_aborted']())
    ) is True


def test_contention_00414():
    # custody_batch_validation_vad_nonfinite
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite']()) is False


def test_transport_00414():
    # custody_batch_validation_vad_nonfinite
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite']()) is False


def test_admitted_00414():
    # custody_batch_validation_vad_nonfinite
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite']())
    ) is False


def test_contention_00415():
    # custody_batch_validation_vad_nonfinite_cause_aborted
    assert (
        bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite_cause_aborted']()) is True
    )


def test_transport_00415():
    # custody_batch_validation_vad_nonfinite_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite_cause_aborted']())
        is False
    )


def test_admitted_00415():
    # custody_batch_validation_vad_nonfinite_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite_cause_aborted']())
    ) is True


def test_contention_00416():
    # custody_batch_validation_vad_order
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_vad_order']()) is False


def test_transport_00416():
    # custody_batch_validation_vad_order
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_vad_order']()) is False


def test_admitted_00416():
    # custody_batch_validation_vad_order
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_vad_order']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_vad_order']())
    ) is False


def test_contention_00417():
    # custody_batch_validation_vad_order_cause_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_vad_order_cause_aborted']()) is True


def test_transport_00417():
    # custody_batch_validation_vad_order_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_vad_order_cause_aborted']()) is False
    )


def test_admitted_00417():
    # custody_batch_validation_vad_order_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_vad_order_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_vad_order_cause_aborted']())
    ) is True


def test_contention_00418():
    # custody_batch_validation_vad_bounds
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_vad_bounds']()) is False


def test_transport_00418():
    # custody_batch_validation_vad_bounds
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_vad_bounds']()) is False


def test_admitted_00418():
    # custody_batch_validation_vad_bounds
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_vad_bounds']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_vad_bounds']())
    ) is False


def test_contention_00419():
    # custody_batch_validation_vad_bounds_cause_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_vad_bounds_cause_aborted']()) is True


def test_transport_00419():
    # custody_batch_validation_vad_bounds_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_vad_bounds_cause_aborted']()) is False
    )


def test_admitted_00419():
    # custody_batch_validation_vad_bounds_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_vad_bounds_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_vad_bounds_cause_aborted']())
    ) is True


def test_contention_00420():
    # custody_batch_validation_empty_asr
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_empty_asr']()) is False


def test_transport_00420():
    # custody_batch_validation_empty_asr
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_empty_asr']()) is False


def test_admitted_00420():
    # custody_batch_validation_empty_asr
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_empty_asr']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_empty_asr']())
    ) is False


def test_contention_00421():
    # custody_batch_validation_empty_asr_cause_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_empty_asr_cause_aborted']()) is True


def test_transport_00421():
    # custody_batch_validation_empty_asr_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_empty_asr_cause_aborted']()) is False
    )


def test_admitted_00421():
    # custody_batch_validation_empty_asr_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_empty_asr_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_empty_asr_cause_aborted']())
    ) is True


def test_contention_00422():
    # custody_batch_validation_no_owned_words
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_no_owned_words']()) is False


def test_transport_00422():
    # custody_batch_validation_no_owned_words
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_no_owned_words']()) is False


def test_admitted_00422():
    # custody_batch_validation_no_owned_words
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_no_owned_words']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_no_owned_words']())
    ) is False


def test_contention_00423():
    # custody_batch_validation_no_owned_words_cause_aborted
    assert (
        bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_no_owned_words_cause_aborted']())
        is True
    )


def test_transport_00423():
    # custody_batch_validation_no_owned_words_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_no_owned_words_cause_aborted']())
        is False
    )


def test_admitted_00423():
    # custody_batch_validation_no_owned_words_cause_aborted
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['custody_batch_validation_no_owned_words_cause_aborted']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['custody_batch_validation_no_owned_words_cause_aborted']())
    ) is True


def test_contention_00424():
    # timeout_family_6456
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['timeout_family_6456']()) is False


def test_transport_00424():
    # timeout_family_6456
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['timeout_family_6456']()) is True


def test_admitted_00424():
    # timeout_family_6456
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['timeout_family_6456']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['timeout_family_6456']())
    ) is True


def test_contention_00425():
    # timeout_family_9792
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['timeout_family_9792']()) is False


def test_transport_00425():
    # timeout_family_9792
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['timeout_family_9792']()) is True


def test_admitted_00425():
    # timeout_family_9792
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['timeout_family_9792']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['timeout_family_9792']())
    ) is True


def test_contention_00426():
    # timeout_family_400
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['timeout_family_400']()) is False


def test_transport_00426():
    # timeout_family_400
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['timeout_family_400']()) is True


def test_admitted_00426():
    # timeout_family_400
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['timeout_family_400']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['timeout_family_400']())
    ) is True


def test_contention_00427():
    # wrapper_attempts_exhausted_0_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_0_0']()) is True


def test_transport_00427():
    # wrapper_attempts_exhausted_0_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_0_0']()) is False


def test_admitted_00427():
    # wrapper_attempts_exhausted_0_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_0_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_0_0']())
    ) is True


def test_contention_00428():
    # wrapper_attempts_exhausted_0_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_0_1']()) is True


def test_transport_00428():
    # wrapper_attempts_exhausted_0_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_0_1']()) is False


def test_admitted_00428():
    # wrapper_attempts_exhausted_0_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_0_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_0_1']())
    ) is True


def test_contention_00429():
    # wrapper_attempts_exhausted_0_25
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_0_25']()) is True


def test_transport_00429():
    # wrapper_attempts_exhausted_0_25
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_0_25']()) is False


def test_admitted_00429():
    # wrapper_attempts_exhausted_0_25
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_0_25']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_0_25']())
    ) is True


def test_contention_00430():
    # wrapper_attempts_exhausted_0_5
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_0_5']()) is True


def test_transport_00430():
    # wrapper_attempts_exhausted_0_5
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_0_5']()) is False


def test_admitted_00430():
    # wrapper_attempts_exhausted_0_5
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_0_5']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_0_5']())
    ) is True


def test_contention_00431():
    # wrapper_attempts_exhausted_1_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_1_0']()) is True


def test_transport_00431():
    # wrapper_attempts_exhausted_1_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_1_0']()) is False


def test_admitted_00431():
    # wrapper_attempts_exhausted_1_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_1_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_1_0']())
    ) is True


def test_contention_00432():
    # wrapper_attempts_exhausted_1_5
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_1_5']()) is True


def test_transport_00432():
    # wrapper_attempts_exhausted_1_5
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_1_5']()) is False


def test_admitted_00432():
    # wrapper_attempts_exhausted_1_5
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_1_5']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_1_5']())
    ) is True


def test_contention_00433():
    # wrapper_attempts_exhausted_2_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_2_0']()) is True


def test_transport_00433():
    # wrapper_attempts_exhausted_2_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_2_0']()) is False


def test_admitted_00433():
    # wrapper_attempts_exhausted_2_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_2_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_2_0']())
    ) is True


def test_contention_00434():
    # wrapper_attempts_exhausted_2_5
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_2_5']()) is True


def test_transport_00434():
    # wrapper_attempts_exhausted_2_5
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_2_5']()) is False


def test_admitted_00434():
    # wrapper_attempts_exhausted_2_5
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_2_5']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_2_5']())
    ) is True


def test_contention_00435():
    # wrapper_attempts_exhausted_3_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_3_0']()) is True


def test_transport_00435():
    # wrapper_attempts_exhausted_3_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_3_0']()) is False


def test_admitted_00435():
    # wrapper_attempts_exhausted_3_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_3_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_3_0']())
    ) is True


def test_contention_00436():
    # wrapper_attempts_exhausted_3_9
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_3_9']()) is True


def test_transport_00436():
    # wrapper_attempts_exhausted_3_9
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_3_9']()) is False


def test_admitted_00436():
    # wrapper_attempts_exhausted_3_9
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_3_9']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_3_9']())
    ) is True


def test_contention_00437():
    # wrapper_attempts_exhausted_4_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_4_0']()) is True


def test_transport_00437():
    # wrapper_attempts_exhausted_4_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_4_0']()) is False


def test_admitted_00437():
    # wrapper_attempts_exhausted_4_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_4_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_4_0']())
    ) is True


def test_contention_00438():
    # wrapper_attempts_exhausted_4_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_4_1']()) is True


def test_transport_00438():
    # wrapper_attempts_exhausted_4_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_4_1']()) is False


def test_admitted_00438():
    # wrapper_attempts_exhausted_4_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_4_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_4_1']())
    ) is True


def test_contention_00439():
    # wrapper_attempts_exhausted_8_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_8_0']()) is True


def test_transport_00439():
    # wrapper_attempts_exhausted_8_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_8_0']()) is False


def test_admitted_00439():
    # wrapper_attempts_exhausted_8_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_8_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_8_0']())
    ) is True


def test_contention_00440():
    # wrapper_attempts_exhausted_50_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_50_0']()) is True


def test_transport_00440():
    # wrapper_attempts_exhausted_50_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_50_0']()) is False


def test_admitted_00440():
    # wrapper_attempts_exhausted_50_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_50_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_50_0']())
    ) is True


def test_contention_00441():
    # wrapper_attempts_exhausted_1000000000_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_1000000000_0']()) is True


def test_transport_00441():
    # wrapper_attempts_exhausted_1000000000_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_1000000000_0']()) is False


def test_admitted_00441():
    # wrapper_attempts_exhausted_1000000000_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_attempts_exhausted_1000000000_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_attempts_exhausted_1000000000_0']())
    ) is True


def test_contention_00442():
    # wrapper_deadline_exhausted_0_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_0_0']()) is True


def test_transport_00442():
    # wrapper_deadline_exhausted_0_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_0_0']()) is False


def test_admitted_00442():
    # wrapper_deadline_exhausted_0_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_0_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_0_0']())
    ) is True


def test_contention_00443():
    # wrapper_deadline_exhausted_0_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_0_1']()) is True


def test_transport_00443():
    # wrapper_deadline_exhausted_0_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_0_1']()) is False


def test_admitted_00443():
    # wrapper_deadline_exhausted_0_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_0_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_0_1']())
    ) is True


def test_contention_00444():
    # wrapper_deadline_exhausted_0_25
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_0_25']()) is True


def test_transport_00444():
    # wrapper_deadline_exhausted_0_25
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_0_25']()) is False


def test_admitted_00444():
    # wrapper_deadline_exhausted_0_25
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_0_25']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_0_25']())
    ) is True


def test_contention_00445():
    # wrapper_deadline_exhausted_0_5
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_0_5']()) is True


def test_transport_00445():
    # wrapper_deadline_exhausted_0_5
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_0_5']()) is False


def test_admitted_00445():
    # wrapper_deadline_exhausted_0_5
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_0_5']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_0_5']())
    ) is True


def test_contention_00446():
    # wrapper_deadline_exhausted_1_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_1_0']()) is True


def test_transport_00446():
    # wrapper_deadline_exhausted_1_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_1_0']()) is False


def test_admitted_00446():
    # wrapper_deadline_exhausted_1_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_1_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_1_0']())
    ) is True


def test_contention_00447():
    # wrapper_deadline_exhausted_1_5
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_1_5']()) is True


def test_transport_00447():
    # wrapper_deadline_exhausted_1_5
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_1_5']()) is False


def test_admitted_00447():
    # wrapper_deadline_exhausted_1_5
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_1_5']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_1_5']())
    ) is True


def test_contention_00448():
    # wrapper_deadline_exhausted_2_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_2_0']()) is True


def test_transport_00448():
    # wrapper_deadline_exhausted_2_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_2_0']()) is False


def test_admitted_00448():
    # wrapper_deadline_exhausted_2_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_2_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_2_0']())
    ) is True


def test_contention_00449():
    # wrapper_deadline_exhausted_2_5
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_2_5']()) is True


def test_transport_00449():
    # wrapper_deadline_exhausted_2_5
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_2_5']()) is False


def test_admitted_00449():
    # wrapper_deadline_exhausted_2_5
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_2_5']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_2_5']())
    ) is True


def test_contention_00450():
    # wrapper_deadline_exhausted_3_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_3_0']()) is True


def test_transport_00450():
    # wrapper_deadline_exhausted_3_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_3_0']()) is False


def test_admitted_00450():
    # wrapper_deadline_exhausted_3_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_3_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_3_0']())
    ) is True


def test_contention_00451():
    # wrapper_deadline_exhausted_3_9
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_3_9']()) is True


def test_transport_00451():
    # wrapper_deadline_exhausted_3_9
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_3_9']()) is False


def test_admitted_00451():
    # wrapper_deadline_exhausted_3_9
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_3_9']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_3_9']())
    ) is True


def test_contention_00452():
    # wrapper_deadline_exhausted_4_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_4_0']()) is True


def test_transport_00452():
    # wrapper_deadline_exhausted_4_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_4_0']()) is False


def test_admitted_00452():
    # wrapper_deadline_exhausted_4_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_4_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_4_0']())
    ) is True


def test_contention_00453():
    # wrapper_deadline_exhausted_4_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_4_1']()) is True


def test_transport_00453():
    # wrapper_deadline_exhausted_4_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_4_1']()) is False


def test_admitted_00453():
    # wrapper_deadline_exhausted_4_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_4_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_4_1']())
    ) is True


def test_contention_00454():
    # wrapper_deadline_exhausted_8_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_8_0']()) is True


def test_transport_00454():
    # wrapper_deadline_exhausted_8_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_8_0']()) is False


def test_admitted_00454():
    # wrapper_deadline_exhausted_8_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_8_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_8_0']())
    ) is True


def test_contention_00455():
    # wrapper_deadline_exhausted_50_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_50_0']()) is True


def test_transport_00455():
    # wrapper_deadline_exhausted_50_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_50_0']()) is False


def test_admitted_00455():
    # wrapper_deadline_exhausted_50_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_50_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_50_0']())
    ) is True


def test_contention_00456():
    # wrapper_deadline_exhausted_1000000000_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_1000000000_0']()) is True


def test_transport_00456():
    # wrapper_deadline_exhausted_1000000000_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_1000000000_0']()) is False


def test_admitted_00456():
    # wrapper_deadline_exhausted_1000000000_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['wrapper_deadline_exhausted_1000000000_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['wrapper_deadline_exhausted_1000000000_0']())
    ) is True


def test_contention_00457():
    # carrier_ns_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_0']()) is False


def test_transport_00457():
    # carrier_ns_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_0']()) is False


def test_admitted_00457():
    # carrier_ns_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_0']())
    ) is False


def test_contention_00458():
    # carrier_err_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_0']()) is False


def test_transport_00458():
    # carrier_err_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_0']()) is False


def test_admitted_00458():
    # carrier_err_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_0']())
    ) is False


def test_contention_00459():
    # carrier_ns_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_1']()) is False


def test_transport_00459():
    # carrier_ns_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_1']()) is False


def test_admitted_00459():
    # carrier_ns_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_1']())
    ) is False


def test_contention_00460():
    # carrier_err_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_1']()) is False


def test_transport_00460():
    # carrier_err_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_1']()) is False


def test_admitted_00460():
    # carrier_err_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_1']())
    ) is False


def test_contention_00461():
    # carrier_ns_2
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_2']()) is False


def test_transport_00461():
    # carrier_ns_2
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_2']()) is False


def test_admitted_00461():
    # carrier_ns_2
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_2']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_2']())
    ) is False


def test_contention_00462():
    # carrier_err_2
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_2']()) is False


def test_transport_00462():
    # carrier_err_2
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_2']()) is False


def test_admitted_00462():
    # carrier_err_2
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_2']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_2']())
    ) is False


def test_contention_00463():
    # carrier_ns_3
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_3']()) is False


def test_transport_00463():
    # carrier_ns_3
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_3']()) is False


def test_admitted_00463():
    # carrier_ns_3
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_3']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_3']())
    ) is False


def test_contention_00464():
    # carrier_err_3
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_3']()) is False


def test_transport_00464():
    # carrier_err_3
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_3']()) is False


def test_admitted_00464():
    # carrier_err_3
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_3']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_3']())
    ) is False


def test_contention_00465():
    # carrier_ns_4
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_4']()) is False


def test_transport_00465():
    # carrier_ns_4
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_4']()) is False


def test_admitted_00465():
    # carrier_ns_4
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_4']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_4']())
    ) is False


def test_contention_00466():
    # carrier_err_4
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_4']()) is False


def test_transport_00466():
    # carrier_err_4
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_4']()) is False


def test_admitted_00466():
    # carrier_err_4
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_4']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_4']())
    ) is False


def test_contention_00467():
    # carrier_ns_5
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_5']()) is False


def test_transport_00467():
    # carrier_ns_5
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_5']()) is False


def test_admitted_00467():
    # carrier_ns_5
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_5']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_5']())
    ) is False


def test_contention_00468():
    # carrier_err_5
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_5']()) is False


def test_transport_00468():
    # carrier_err_5
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_5']()) is False


def test_admitted_00468():
    # carrier_err_5
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_5']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_5']())
    ) is False


def test_contention_00469():
    # carrier_ns_6
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_6']()) is False


def test_transport_00469():
    # carrier_ns_6
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_6']()) is False


def test_admitted_00469():
    # carrier_ns_6
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_6']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_6']())
    ) is False


def test_contention_00470():
    # carrier_err_6
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_6']()) is False


def test_transport_00470():
    # carrier_err_6
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_6']()) is False


def test_admitted_00470():
    # carrier_err_6
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_6']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_6']())
    ) is False


def test_contention_00471():
    # carrier_ns_7
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_7']()) is False


def test_transport_00471():
    # carrier_ns_7
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_7']()) is False


def test_admitted_00471():
    # carrier_ns_7
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_7']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_7']())
    ) is False


def test_contention_00472():
    # carrier_err_7
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_7']()) is False


def test_transport_00472():
    # carrier_err_7
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_7']()) is False


def test_admitted_00472():
    # carrier_err_7
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_7']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_7']())
    ) is False


def test_contention_00473():
    # carrier_ns_8
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_8']()) is False


def test_transport_00473():
    # carrier_ns_8
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_8']()) is False


def test_admitted_00473():
    # carrier_ns_8
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_8']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_8']())
    ) is False


def test_contention_00474():
    # carrier_err_8
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_8']()) is False


def test_transport_00474():
    # carrier_err_8
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_8']()) is False


def test_admitted_00474():
    # carrier_err_8
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_8']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_8']())
    ) is False


def test_contention_00475():
    # carrier_ns_9
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_9']()) is False


def test_transport_00475():
    # carrier_ns_9
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_9']()) is False


def test_admitted_00475():
    # carrier_ns_9
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_9']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_9']())
    ) is False


def test_contention_00476():
    # carrier_err_9
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_9']()) is False


def test_transport_00476():
    # carrier_err_9
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_9']()) is False


def test_admitted_00476():
    # carrier_err_9
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_9']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_9']())
    ) is False


def test_contention_00477():
    # carrier_ns_10
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_10']()) is False


def test_transport_00477():
    # carrier_ns_10
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_10']()) is False


def test_admitted_00477():
    # carrier_ns_10
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_10']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_10']())
    ) is False


def test_contention_00478():
    # carrier_err_10
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_10']()) is False


def test_transport_00478():
    # carrier_err_10
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_10']()) is False


def test_admitted_00478():
    # carrier_err_10
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_10']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_10']())
    ) is False


def test_contention_00479():
    # carrier_ns_11
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_11']()) is False


def test_transport_00479():
    # carrier_ns_11
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_11']()) is False


def test_admitted_00479():
    # carrier_ns_11
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_11']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_11']())
    ) is False


def test_contention_00480():
    # carrier_err_11
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_11']()) is False


def test_transport_00480():
    # carrier_err_11
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_11']()) is False


def test_admitted_00480():
    # carrier_err_11
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_11']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_11']())
    ) is False


def test_contention_00481():
    # carrier_ns_12
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_12']()) is False


def test_transport_00481():
    # carrier_ns_12
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_12']()) is False


def test_admitted_00481():
    # carrier_ns_12
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_12']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_12']())
    ) is False


def test_contention_00482():
    # carrier_err_12
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_12']()) is False


def test_transport_00482():
    # carrier_err_12
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_12']()) is False


def test_admitted_00482():
    # carrier_err_12
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_12']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_12']())
    ) is False


def test_contention_00483():
    # carrier_ns_13
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_13']()) is False


def test_transport_00483():
    # carrier_ns_13
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_13']()) is False


def test_admitted_00483():
    # carrier_ns_13
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_13']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_13']())
    ) is False


def test_contention_00484():
    # carrier_err_13
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_13']()) is False


def test_transport_00484():
    # carrier_err_13
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_13']()) is False


def test_admitted_00484():
    # carrier_err_13
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_13']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_13']())
    ) is False


def test_contention_00485():
    # carrier_ns_14
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_14']()) is False


def test_transport_00485():
    # carrier_ns_14
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_14']()) is False


def test_admitted_00485():
    # carrier_ns_14
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_14']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_14']())
    ) is False


def test_contention_00486():
    # carrier_err_14
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_14']()) is False


def test_transport_00486():
    # carrier_err_14
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_14']()) is False


def test_admitted_00486():
    # carrier_err_14
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_14']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_14']())
    ) is False


def test_contention_00487():
    # carrier_ns_15
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_15']()) is False


def test_transport_00487():
    # carrier_ns_15
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_15']()) is False


def test_admitted_00487():
    # carrier_ns_15
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_15']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_15']())
    ) is False


def test_contention_00488():
    # carrier_err_15
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_15']()) is False


def test_transport_00488():
    # carrier_err_15
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_15']()) is False


def test_admitted_00488():
    # carrier_err_15
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_15']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_15']())
    ) is False


def test_contention_00489():
    # carrier_ns_16
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_16']()) is False


def test_transport_00489():
    # carrier_ns_16
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_16']()) is False


def test_admitted_00489():
    # carrier_ns_16
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_16']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_16']())
    ) is False


def test_contention_00490():
    # carrier_err_16
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_16']()) is False


def test_transport_00490():
    # carrier_err_16
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_16']()) is False


def test_admitted_00490():
    # carrier_err_16
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_16']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_16']())
    ) is False


def test_contention_00491():
    # carrier_ns_17
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_17']()) is False


def test_transport_00491():
    # carrier_ns_17
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_17']()) is False


def test_admitted_00491():
    # carrier_ns_17
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_17']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_17']())
    ) is False


def test_contention_00492():
    # carrier_err_17
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_17']()) is False


def test_transport_00492():
    # carrier_err_17
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_17']()) is False


def test_admitted_00492():
    # carrier_err_17
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_17']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_17']())
    ) is False


def test_contention_00493():
    # carrier_ns_18
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_18']()) is False


def test_transport_00493():
    # carrier_ns_18
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_18']()) is False


def test_admitted_00493():
    # carrier_ns_18
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_18']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_18']())
    ) is False


def test_contention_00494():
    # carrier_err_18
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_18']()) is False


def test_transport_00494():
    # carrier_err_18
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_18']()) is False


def test_admitted_00494():
    # carrier_err_18
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_18']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_18']())
    ) is False


def test_contention_00495():
    # carrier_ns_19
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_19']()) is False


def test_transport_00495():
    # carrier_ns_19
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_19']()) is False


def test_admitted_00495():
    # carrier_ns_19
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_19']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_19']())
    ) is False


def test_contention_00496():
    # carrier_err_19
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_19']()) is False


def test_transport_00496():
    # carrier_err_19
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_19']()) is False


def test_admitted_00496():
    # carrier_err_19
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_19']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_19']())
    ) is False


def test_contention_00497():
    # carrier_ns_20
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_20']()) is False


def test_transport_00497():
    # carrier_ns_20
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_20']()) is False


def test_admitted_00497():
    # carrier_ns_20
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_ns_20']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_ns_20']())
    ) is False


def test_contention_00498():
    # carrier_err_20
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_20']()) is False


def test_transport_00498():
    # carrier_err_20
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_20']()) is False


def test_admitted_00498():
    # carrier_err_20
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['carrier_err_20']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['carrier_err_20']())
    ) is False


def test_contention_00499():
    # hostile_0
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['hostile_0']()) is False


def test_transport_00499():
    # hostile_0
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['hostile_0']()) is False


def test_admitted_00499():
    # hostile_0
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['hostile_0']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['hostile_0']())
    ) is False


def test_contention_00500():
    # hostile_1
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['hostile_1']()) is False


def test_transport_00500():
    # hostile_1
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['hostile_1']()) is False


def test_admitted_00500():
    # hostile_1
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['hostile_1']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['hostile_1']())
    ) is False


def test_contention_00501():
    # hostile_2
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['hostile_2']()) is False


def test_transport_00501():
    # hostile_2
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['hostile_2']()) is False


def test_admitted_00501():
    # hostile_2
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['hostile_2']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['hostile_2']())
    ) is False


def test_contention_00502():
    # hostile_3
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['hostile_3']()) is False


def test_transport_00502():
    # hostile_3
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['hostile_3']()) is False


def test_admitted_00502():
    # hostile_3
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['hostile_3']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['hostile_3']())
    ) is False


def test_contention_00503():
    # hostile_4
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['hostile_4']()) is False


def test_transport_00503():
    # hostile_4
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['hostile_4']()) is False


def test_admitted_00503():
    # hostile_4
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['hostile_4']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['hostile_4']())
    ) is False


def test_contention_00504():
    # hostile_5
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['hostile_5']()) is False


def test_transport_00504():
    # hostile_5
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['hostile_5']()) is False


def test_admitted_00504():
    # hostile_5
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['hostile_5']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['hostile_5']())
    ) is False


def test_contention_00505():
    # hostile_6
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['hostile_6']()) is False


def test_transport_00505():
    # hostile_6
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['hostile_6']()) is False


def test_admitted_00505():
    # hostile_6
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['hostile_6']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['hostile_6']())
    ) is False


def test_contention_00506():
    # hostile_7
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['hostile_7']()) is False


def test_transport_00506():
    # hostile_7
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['hostile_7']()) is False


def test_admitted_00506():
    # hostile_7
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['hostile_7']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['hostile_7']())
    ) is False


def test_contention_00507():
    # hostile_8
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['hostile_8']()) is False


def test_transport_00507():
    # hostile_8
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['hostile_8']()) is False


def test_admitted_00507():
    # hostile_8
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['hostile_8']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['hostile_8']())
    ) is False


def test_contention_00508():
    # hostile_9
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['hostile_9']()) is False


def test_transport_00508():
    # hostile_9
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['hostile_9']()) is False


def test_admitted_00508():
    # hostile_9
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['hostile_9']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['hostile_9']())
    ) is False


def test_contention_00509():
    # hostile_10
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['hostile_10']()) is False


def test_transport_00509():
    # hostile_10
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['hostile_10']()) is False


def test_admitted_00509():
    # hostile_10
    assert (
        bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['hostile_10']())
        or bp.persist_loss_is_contention(_SHAPE_BUILDERS['hostile_10']())
    ) is False
