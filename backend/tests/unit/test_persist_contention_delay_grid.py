#!/usr/bin/env python3
"""Effective-delay grid: ladder floor and storm ceiling per fault shape and attempt.

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


def test_effective_00000():
    # sdk_Aborted_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Aborted_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00001():
    # sdk_Aborted_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Aborted_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00002():
    # sdk_Aborted_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Aborted_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00003():
    # sdk_Aborted_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Aborted_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00004():
    # sdk_Aborted_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Aborted_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00005():
    # sdk_Aborted_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Aborted_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00006():
    # sdk_Aborted_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Aborted_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00007():
    # sdk_Aborted_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00008():
    # sdk_Aborted_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00009():
    # sdk_Aborted_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00010():
    # sdk_Aborted_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00011():
    # sdk_Aborted_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00012():
    # sdk_Aborted_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00013():
    # sdk_Aborted_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00014():
    # sdk_Aborted_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00015():
    # sdk_Aborted_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00016():
    # sdk_Aborted_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00017():
    # sdk_Aborted_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00018():
    # sdk_Aborted_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00019():
    # sdk_Aborted_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00020():
    # sdk_Aborted_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00021():
    # sdk_Aborted_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00022():
    # sdk_Aborted_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00023():
    # sdk_Aborted_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00024():
    # sdk_Aborted_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00025():
    # sdk_Aborted_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00026():
    # sdk_Aborted_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00027():
    # sdk_Aborted_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00028():
    # sdk_Aborted_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00029():
    # sdk_Aborted_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00030():
    # sdk_Aborted_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00031():
    # sdk_Aborted_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00032():
    # sdk_Aborted_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00033():
    # sdk_Aborted_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00034():
    # sdk_Aborted_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00035():
    # sdk_Aborted_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Aborted_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00036():
    # sdk_Aborted_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Aborted_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00037():
    # sdk_Aborted_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Aborted_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00038():
    # sdk_Aborted_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Aborted_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00039():
    # sdk_Aborted_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Aborted_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00040():
    # sdk_Aborted_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Aborted_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00041():
    # sdk_Aborted_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Aborted_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00042():
    # sdk_Aborted_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00043():
    # sdk_Aborted_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00044():
    # sdk_Aborted_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00045():
    # sdk_Aborted_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00046():
    # sdk_Aborted_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00047():
    # sdk_Aborted_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00048():
    # sdk_Aborted_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00049():
    # sdk_Aborted_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00050():
    # sdk_Aborted_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00051():
    # sdk_Aborted_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00052():
    # sdk_Aborted_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00053():
    # sdk_Aborted_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00054():
    # sdk_Aborted_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00055():
    # sdk_Aborted_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00056():
    # sdk_Aborted_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00057():
    # sdk_Aborted_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00058():
    # sdk_Aborted_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00059():
    # sdk_Aborted_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00060():
    # sdk_Aborted_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00061():
    # sdk_Aborted_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00062():
    # sdk_Aborted_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00063():
    # sdk_Aborted_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00064():
    # sdk_Aborted_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00065():
    # sdk_Aborted_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00066():
    # sdk_Aborted_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00067():
    # sdk_Aborted_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00068():
    # sdk_Aborted_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00069():
    # sdk_Aborted_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Aborted_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00070():
    # sdk_AlreadyExists_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00071():
    # sdk_AlreadyExists_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00072():
    # sdk_AlreadyExists_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00073():
    # sdk_AlreadyExists_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00074():
    # sdk_AlreadyExists_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00075():
    # sdk_AlreadyExists_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00076():
    # sdk_AlreadyExists_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00077():
    # sdk_AlreadyExists_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00078():
    # sdk_AlreadyExists_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00079():
    # sdk_AlreadyExists_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00080():
    # sdk_AlreadyExists_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00081():
    # sdk_AlreadyExists_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00082():
    # sdk_AlreadyExists_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00083():
    # sdk_AlreadyExists_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00084():
    # sdk_AlreadyExists_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00085():
    # sdk_AlreadyExists_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00086():
    # sdk_AlreadyExists_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00087():
    # sdk_AlreadyExists_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00088():
    # sdk_AlreadyExists_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00089():
    # sdk_AlreadyExists_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00090():
    # sdk_AlreadyExists_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00091():
    # sdk_AlreadyExists_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00092():
    # sdk_AlreadyExists_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00093():
    # sdk_AlreadyExists_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00094():
    # sdk_AlreadyExists_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00095():
    # sdk_AlreadyExists_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00096():
    # sdk_AlreadyExists_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00097():
    # sdk_AlreadyExists_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00098():
    # sdk_AlreadyExists_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00099():
    # sdk_AlreadyExists_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00100():
    # sdk_AlreadyExists_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00101():
    # sdk_AlreadyExists_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00102():
    # sdk_AlreadyExists_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00103():
    # sdk_AlreadyExists_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00104():
    # sdk_AlreadyExists_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00105():
    # sdk_AlreadyExists_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00106():
    # sdk_AlreadyExists_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00107():
    # sdk_AlreadyExists_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00108():
    # sdk_AlreadyExists_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00109():
    # sdk_AlreadyExists_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00110():
    # sdk_AlreadyExists_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00111():
    # sdk_AlreadyExists_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00112():
    # sdk_AlreadyExists_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00113():
    # sdk_AlreadyExists_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00114():
    # sdk_AlreadyExists_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00115():
    # sdk_AlreadyExists_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00116():
    # sdk_AlreadyExists_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00117():
    # sdk_AlreadyExists_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00118():
    # sdk_AlreadyExists_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00119():
    # sdk_AlreadyExists_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00120():
    # sdk_AlreadyExists_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00121():
    # sdk_AlreadyExists_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00122():
    # sdk_AlreadyExists_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00123():
    # sdk_AlreadyExists_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00124():
    # sdk_AlreadyExists_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00125():
    # sdk_AlreadyExists_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00126():
    # sdk_AlreadyExists_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00127():
    # sdk_AlreadyExists_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00128():
    # sdk_AlreadyExists_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00129():
    # sdk_AlreadyExists_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00130():
    # sdk_AlreadyExists_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00131():
    # sdk_AlreadyExists_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00132():
    # sdk_AlreadyExists_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00133():
    # sdk_AlreadyExists_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00134():
    # sdk_AlreadyExists_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00135():
    # sdk_AlreadyExists_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00136():
    # sdk_AlreadyExists_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00137():
    # sdk_AlreadyExists_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00138():
    # sdk_AlreadyExists_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00139():
    # sdk_AlreadyExists_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_AlreadyExists_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00140():
    # sdk_BadGateway_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_BadGateway_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00141():
    # sdk_BadGateway_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_BadGateway_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00142():
    # sdk_BadGateway_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_BadGateway_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00143():
    # sdk_BadGateway_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_BadGateway_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00144():
    # sdk_BadGateway_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_BadGateway_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00145():
    # sdk_BadGateway_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_BadGateway_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00146():
    # sdk_BadGateway_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_BadGateway_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00147():
    # sdk_BadGateway_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00148():
    # sdk_BadGateway_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00149():
    # sdk_BadGateway_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00150():
    # sdk_BadGateway_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00151():
    # sdk_BadGateway_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00152():
    # sdk_BadGateway_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00153():
    # sdk_BadGateway_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00154():
    # sdk_BadGateway_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00155():
    # sdk_BadGateway_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00156():
    # sdk_BadGateway_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00157():
    # sdk_BadGateway_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00158():
    # sdk_BadGateway_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00159():
    # sdk_BadGateway_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00160():
    # sdk_BadGateway_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00161():
    # sdk_BadGateway_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00162():
    # sdk_BadGateway_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00163():
    # sdk_BadGateway_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00164():
    # sdk_BadGateway_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00165():
    # sdk_BadGateway_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00166():
    # sdk_BadGateway_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00167():
    # sdk_BadGateway_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00168():
    # sdk_BadGateway_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00169():
    # sdk_BadGateway_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00170():
    # sdk_BadGateway_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00171():
    # sdk_BadGateway_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00172():
    # sdk_BadGateway_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00173():
    # sdk_BadGateway_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00174():
    # sdk_BadGateway_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00175():
    # sdk_BadGateway_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_BadGateway_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00176():
    # sdk_BadGateway_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_BadGateway_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00177():
    # sdk_BadGateway_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_BadGateway_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00178():
    # sdk_BadGateway_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_BadGateway_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00179():
    # sdk_BadGateway_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_BadGateway_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00180():
    # sdk_BadGateway_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_BadGateway_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00181():
    # sdk_BadGateway_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_BadGateway_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00182():
    # sdk_BadGateway_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00183():
    # sdk_BadGateway_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00184():
    # sdk_BadGateway_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00185():
    # sdk_BadGateway_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00186():
    # sdk_BadGateway_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00187():
    # sdk_BadGateway_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00188():
    # sdk_BadGateway_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00189():
    # sdk_BadGateway_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00190():
    # sdk_BadGateway_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00191():
    # sdk_BadGateway_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00192():
    # sdk_BadGateway_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00193():
    # sdk_BadGateway_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00194():
    # sdk_BadGateway_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00195():
    # sdk_BadGateway_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00196():
    # sdk_BadGateway_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00197():
    # sdk_BadGateway_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00198():
    # sdk_BadGateway_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00199():
    # sdk_BadGateway_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00200():
    # sdk_BadGateway_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00201():
    # sdk_BadGateway_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00202():
    # sdk_BadGateway_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00203():
    # sdk_BadGateway_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00204():
    # sdk_BadGateway_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00205():
    # sdk_BadGateway_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00206():
    # sdk_BadGateway_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00207():
    # sdk_BadGateway_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00208():
    # sdk_BadGateway_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00209():
    # sdk_BadGateway_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_BadGateway_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00210():
    # sdk_BadRequest_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_BadRequest_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00211():
    # sdk_BadRequest_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_BadRequest_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00212():
    # sdk_BadRequest_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_BadRequest_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00213():
    # sdk_BadRequest_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_BadRequest_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00214():
    # sdk_BadRequest_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_BadRequest_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00215():
    # sdk_BadRequest_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_BadRequest_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00216():
    # sdk_BadRequest_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_BadRequest_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00217():
    # sdk_BadRequest_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00218():
    # sdk_BadRequest_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00219():
    # sdk_BadRequest_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00220():
    # sdk_BadRequest_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00221():
    # sdk_BadRequest_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00222():
    # sdk_BadRequest_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00223():
    # sdk_BadRequest_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00224():
    # sdk_BadRequest_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00225():
    # sdk_BadRequest_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00226():
    # sdk_BadRequest_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00227():
    # sdk_BadRequest_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00228():
    # sdk_BadRequest_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00229():
    # sdk_BadRequest_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00230():
    # sdk_BadRequest_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00231():
    # sdk_BadRequest_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00232():
    # sdk_BadRequest_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00233():
    # sdk_BadRequest_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00234():
    # sdk_BadRequest_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00235():
    # sdk_BadRequest_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00236():
    # sdk_BadRequest_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00237():
    # sdk_BadRequest_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00238():
    # sdk_BadRequest_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00239():
    # sdk_BadRequest_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00240():
    # sdk_BadRequest_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00241():
    # sdk_BadRequest_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00242():
    # sdk_BadRequest_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00243():
    # sdk_BadRequest_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00244():
    # sdk_BadRequest_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00245():
    # sdk_BadRequest_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_BadRequest_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00246():
    # sdk_BadRequest_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_BadRequest_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00247():
    # sdk_BadRequest_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_BadRequest_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00248():
    # sdk_BadRequest_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_BadRequest_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00249():
    # sdk_BadRequest_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_BadRequest_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00250():
    # sdk_BadRequest_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_BadRequest_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00251():
    # sdk_BadRequest_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_BadRequest_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00252():
    # sdk_BadRequest_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00253():
    # sdk_BadRequest_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00254():
    # sdk_BadRequest_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00255():
    # sdk_BadRequest_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00256():
    # sdk_BadRequest_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00257():
    # sdk_BadRequest_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00258():
    # sdk_BadRequest_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00259():
    # sdk_BadRequest_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00260():
    # sdk_BadRequest_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00261():
    # sdk_BadRequest_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00262():
    # sdk_BadRequest_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00263():
    # sdk_BadRequest_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00264():
    # sdk_BadRequest_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00265():
    # sdk_BadRequest_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00266():
    # sdk_BadRequest_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00267():
    # sdk_BadRequest_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00268():
    # sdk_BadRequest_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00269():
    # sdk_BadRequest_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00270():
    # sdk_BadRequest_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00271():
    # sdk_BadRequest_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00272():
    # sdk_BadRequest_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00273():
    # sdk_BadRequest_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00274():
    # sdk_BadRequest_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00275():
    # sdk_BadRequest_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00276():
    # sdk_BadRequest_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00277():
    # sdk_BadRequest_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00278():
    # sdk_BadRequest_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00279():
    # sdk_BadRequest_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_BadRequest_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00280():
    # sdk_Cancelled_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Cancelled_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00281():
    # sdk_Cancelled_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Cancelled_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00282():
    # sdk_Cancelled_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Cancelled_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00283():
    # sdk_Cancelled_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Cancelled_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00284():
    # sdk_Cancelled_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Cancelled_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00285():
    # sdk_Cancelled_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Cancelled_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00286():
    # sdk_Cancelled_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Cancelled_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00287():
    # sdk_Cancelled_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00288():
    # sdk_Cancelled_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00289():
    # sdk_Cancelled_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00290():
    # sdk_Cancelled_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00291():
    # sdk_Cancelled_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00292():
    # sdk_Cancelled_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00293():
    # sdk_Cancelled_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00294():
    # sdk_Cancelled_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00295():
    # sdk_Cancelled_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00296():
    # sdk_Cancelled_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00297():
    # sdk_Cancelled_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00298():
    # sdk_Cancelled_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00299():
    # sdk_Cancelled_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00300():
    # sdk_Cancelled_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00301():
    # sdk_Cancelled_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00302():
    # sdk_Cancelled_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00303():
    # sdk_Cancelled_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00304():
    # sdk_Cancelled_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00305():
    # sdk_Cancelled_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00306():
    # sdk_Cancelled_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00307():
    # sdk_Cancelled_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00308():
    # sdk_Cancelled_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00309():
    # sdk_Cancelled_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00310():
    # sdk_Cancelled_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00311():
    # sdk_Cancelled_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00312():
    # sdk_Cancelled_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00313():
    # sdk_Cancelled_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00314():
    # sdk_Cancelled_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00315():
    # sdk_Cancelled_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Cancelled_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00316():
    # sdk_Cancelled_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Cancelled_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00317():
    # sdk_Cancelled_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Cancelled_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00318():
    # sdk_Cancelled_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Cancelled_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00319():
    # sdk_Cancelled_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Cancelled_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00320():
    # sdk_Cancelled_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Cancelled_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00321():
    # sdk_Cancelled_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Cancelled_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00322():
    # sdk_Cancelled_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00323():
    # sdk_Cancelled_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00324():
    # sdk_Cancelled_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00325():
    # sdk_Cancelled_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00326():
    # sdk_Cancelled_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00327():
    # sdk_Cancelled_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00328():
    # sdk_Cancelled_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00329():
    # sdk_Cancelled_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00330():
    # sdk_Cancelled_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00331():
    # sdk_Cancelled_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00332():
    # sdk_Cancelled_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00333():
    # sdk_Cancelled_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00334():
    # sdk_Cancelled_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00335():
    # sdk_Cancelled_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00336():
    # sdk_Cancelled_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00337():
    # sdk_Cancelled_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00338():
    # sdk_Cancelled_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00339():
    # sdk_Cancelled_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00340():
    # sdk_Cancelled_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00341():
    # sdk_Cancelled_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00342():
    # sdk_Cancelled_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00343():
    # sdk_Cancelled_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00344():
    # sdk_Cancelled_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00345():
    # sdk_Cancelled_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00346():
    # sdk_Cancelled_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00347():
    # sdk_Cancelled_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00348():
    # sdk_Cancelled_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00349():
    # sdk_Cancelled_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Cancelled_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00350():
    # sdk_ClientError_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_ClientError_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00351():
    # sdk_ClientError_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_ClientError_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00352():
    # sdk_ClientError_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_ClientError_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00353():
    # sdk_ClientError_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_ClientError_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00354():
    # sdk_ClientError_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_ClientError_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00355():
    # sdk_ClientError_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_ClientError_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00356():
    # sdk_ClientError_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_ClientError_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00357():
    # sdk_ClientError_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00358():
    # sdk_ClientError_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00359():
    # sdk_ClientError_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00360():
    # sdk_ClientError_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00361():
    # sdk_ClientError_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00362():
    # sdk_ClientError_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00363():
    # sdk_ClientError_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00364():
    # sdk_ClientError_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00365():
    # sdk_ClientError_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00366():
    # sdk_ClientError_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00367():
    # sdk_ClientError_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00368():
    # sdk_ClientError_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00369():
    # sdk_ClientError_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00370():
    # sdk_ClientError_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00371():
    # sdk_ClientError_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00372():
    # sdk_ClientError_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00373():
    # sdk_ClientError_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00374():
    # sdk_ClientError_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00375():
    # sdk_ClientError_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00376():
    # sdk_ClientError_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00377():
    # sdk_ClientError_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00378():
    # sdk_ClientError_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00379():
    # sdk_ClientError_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00380():
    # sdk_ClientError_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00381():
    # sdk_ClientError_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00382():
    # sdk_ClientError_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00383():
    # sdk_ClientError_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00384():
    # sdk_ClientError_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00385():
    # sdk_ClientError_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_ClientError_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00386():
    # sdk_ClientError_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_ClientError_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00387():
    # sdk_ClientError_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_ClientError_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00388():
    # sdk_ClientError_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_ClientError_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00389():
    # sdk_ClientError_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_ClientError_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00390():
    # sdk_ClientError_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_ClientError_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00391():
    # sdk_ClientError_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_ClientError_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00392():
    # sdk_ClientError_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00393():
    # sdk_ClientError_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00394():
    # sdk_ClientError_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00395():
    # sdk_ClientError_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00396():
    # sdk_ClientError_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00397():
    # sdk_ClientError_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00398():
    # sdk_ClientError_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00399():
    # sdk_ClientError_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00400():
    # sdk_ClientError_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00401():
    # sdk_ClientError_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00402():
    # sdk_ClientError_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00403():
    # sdk_ClientError_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00404():
    # sdk_ClientError_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00405():
    # sdk_ClientError_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00406():
    # sdk_ClientError_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00407():
    # sdk_ClientError_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00408():
    # sdk_ClientError_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00409():
    # sdk_ClientError_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00410():
    # sdk_ClientError_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00411():
    # sdk_ClientError_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00412():
    # sdk_ClientError_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00413():
    # sdk_ClientError_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00414():
    # sdk_ClientError_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00415():
    # sdk_ClientError_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00416():
    # sdk_ClientError_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00417():
    # sdk_ClientError_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00418():
    # sdk_ClientError_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00419():
    # sdk_ClientError_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_ClientError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00420():
    # sdk_Conflict_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Conflict_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00421():
    # sdk_Conflict_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Conflict_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00422():
    # sdk_Conflict_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Conflict_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00423():
    # sdk_Conflict_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Conflict_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00424():
    # sdk_Conflict_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Conflict_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00425():
    # sdk_Conflict_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Conflict_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00426():
    # sdk_Conflict_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Conflict_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00427():
    # sdk_Conflict_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00428():
    # sdk_Conflict_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00429():
    # sdk_Conflict_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00430():
    # sdk_Conflict_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00431():
    # sdk_Conflict_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00432():
    # sdk_Conflict_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00433():
    # sdk_Conflict_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00434():
    # sdk_Conflict_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00435():
    # sdk_Conflict_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00436():
    # sdk_Conflict_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00437():
    # sdk_Conflict_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00438():
    # sdk_Conflict_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00439():
    # sdk_Conflict_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00440():
    # sdk_Conflict_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00441():
    # sdk_Conflict_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00442():
    # sdk_Conflict_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00443():
    # sdk_Conflict_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00444():
    # sdk_Conflict_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00445():
    # sdk_Conflict_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00446():
    # sdk_Conflict_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00447():
    # sdk_Conflict_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00448():
    # sdk_Conflict_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00449():
    # sdk_Conflict_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00450():
    # sdk_Conflict_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00451():
    # sdk_Conflict_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00452():
    # sdk_Conflict_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00453():
    # sdk_Conflict_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00454():
    # sdk_Conflict_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00455():
    # sdk_Conflict_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Conflict_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00456():
    # sdk_Conflict_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Conflict_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00457():
    # sdk_Conflict_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Conflict_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00458():
    # sdk_Conflict_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Conflict_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00459():
    # sdk_Conflict_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Conflict_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00460():
    # sdk_Conflict_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Conflict_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00461():
    # sdk_Conflict_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Conflict_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00462():
    # sdk_Conflict_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00463():
    # sdk_Conflict_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00464():
    # sdk_Conflict_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00465():
    # sdk_Conflict_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00466():
    # sdk_Conflict_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00467():
    # sdk_Conflict_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00468():
    # sdk_Conflict_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00469():
    # sdk_Conflict_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00470():
    # sdk_Conflict_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00471():
    # sdk_Conflict_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00472():
    # sdk_Conflict_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00473():
    # sdk_Conflict_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00474():
    # sdk_Conflict_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00475():
    # sdk_Conflict_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00476():
    # sdk_Conflict_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00477():
    # sdk_Conflict_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00478():
    # sdk_Conflict_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00479():
    # sdk_Conflict_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00480():
    # sdk_Conflict_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00481():
    # sdk_Conflict_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00482():
    # sdk_Conflict_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00483():
    # sdk_Conflict_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00484():
    # sdk_Conflict_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00485():
    # sdk_Conflict_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00486():
    # sdk_Conflict_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00487():
    # sdk_Conflict_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00488():
    # sdk_Conflict_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00489():
    # sdk_Conflict_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Conflict_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00490():
    # sdk_DataLoss_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_DataLoss_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00491():
    # sdk_DataLoss_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_DataLoss_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00492():
    # sdk_DataLoss_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_DataLoss_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00493():
    # sdk_DataLoss_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_DataLoss_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00494():
    # sdk_DataLoss_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_DataLoss_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00495():
    # sdk_DataLoss_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_DataLoss_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00496():
    # sdk_DataLoss_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_DataLoss_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00497():
    # sdk_DataLoss_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00498():
    # sdk_DataLoss_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00499():
    # sdk_DataLoss_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00500():
    # sdk_DataLoss_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00501():
    # sdk_DataLoss_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00502():
    # sdk_DataLoss_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00503():
    # sdk_DataLoss_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00504():
    # sdk_DataLoss_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00505():
    # sdk_DataLoss_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00506():
    # sdk_DataLoss_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00507():
    # sdk_DataLoss_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00508():
    # sdk_DataLoss_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00509():
    # sdk_DataLoss_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00510():
    # sdk_DataLoss_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00511():
    # sdk_DataLoss_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00512():
    # sdk_DataLoss_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00513():
    # sdk_DataLoss_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00514():
    # sdk_DataLoss_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00515():
    # sdk_DataLoss_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00516():
    # sdk_DataLoss_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00517():
    # sdk_DataLoss_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00518():
    # sdk_DataLoss_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00519():
    # sdk_DataLoss_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00520():
    # sdk_DataLoss_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00521():
    # sdk_DataLoss_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00522():
    # sdk_DataLoss_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00523():
    # sdk_DataLoss_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00524():
    # sdk_DataLoss_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00525():
    # sdk_DataLoss_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_DataLoss_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00526():
    # sdk_DataLoss_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_DataLoss_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00527():
    # sdk_DataLoss_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_DataLoss_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00528():
    # sdk_DataLoss_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_DataLoss_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00529():
    # sdk_DataLoss_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_DataLoss_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00530():
    # sdk_DataLoss_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_DataLoss_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00531():
    # sdk_DataLoss_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_DataLoss_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00532():
    # sdk_DataLoss_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00533():
    # sdk_DataLoss_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00534():
    # sdk_DataLoss_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00535():
    # sdk_DataLoss_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00536():
    # sdk_DataLoss_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00537():
    # sdk_DataLoss_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00538():
    # sdk_DataLoss_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00539():
    # sdk_DataLoss_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00540():
    # sdk_DataLoss_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00541():
    # sdk_DataLoss_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00542():
    # sdk_DataLoss_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00543():
    # sdk_DataLoss_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00544():
    # sdk_DataLoss_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00545():
    # sdk_DataLoss_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00546():
    # sdk_DataLoss_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00547():
    # sdk_DataLoss_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00548():
    # sdk_DataLoss_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00549():
    # sdk_DataLoss_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00550():
    # sdk_DataLoss_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00551():
    # sdk_DataLoss_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00552():
    # sdk_DataLoss_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00553():
    # sdk_DataLoss_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00554():
    # sdk_DataLoss_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00555():
    # sdk_DataLoss_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00556():
    # sdk_DataLoss_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00557():
    # sdk_DataLoss_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00558():
    # sdk_DataLoss_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00559():
    # sdk_DataLoss_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_DataLoss_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00560():
    # sdk_DeadlineExceeded_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00561():
    # sdk_DeadlineExceeded_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00562():
    # sdk_DeadlineExceeded_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00563():
    # sdk_DeadlineExceeded_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00564():
    # sdk_DeadlineExceeded_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00565():
    # sdk_DeadlineExceeded_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00566():
    # sdk_DeadlineExceeded_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00567():
    # sdk_DeadlineExceeded_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00568():
    # sdk_DeadlineExceeded_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00569():
    # sdk_DeadlineExceeded_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00570():
    # sdk_DeadlineExceeded_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00571():
    # sdk_DeadlineExceeded_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00572():
    # sdk_DeadlineExceeded_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00573():
    # sdk_DeadlineExceeded_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00574():
    # sdk_DeadlineExceeded_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00575():
    # sdk_DeadlineExceeded_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00576():
    # sdk_DeadlineExceeded_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00577():
    # sdk_DeadlineExceeded_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00578():
    # sdk_DeadlineExceeded_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00579():
    # sdk_DeadlineExceeded_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00580():
    # sdk_DeadlineExceeded_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00581():
    # sdk_DeadlineExceeded_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00582():
    # sdk_DeadlineExceeded_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00583():
    # sdk_DeadlineExceeded_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00584():
    # sdk_DeadlineExceeded_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00585():
    # sdk_DeadlineExceeded_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00586():
    # sdk_DeadlineExceeded_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00587():
    # sdk_DeadlineExceeded_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00588():
    # sdk_DeadlineExceeded_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00589():
    # sdk_DeadlineExceeded_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00590():
    # sdk_DeadlineExceeded_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00591():
    # sdk_DeadlineExceeded_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00592():
    # sdk_DeadlineExceeded_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00593():
    # sdk_DeadlineExceeded_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00594():
    # sdk_DeadlineExceeded_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00595():
    # sdk_DeadlineExceeded_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00596():
    # sdk_DeadlineExceeded_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00597():
    # sdk_DeadlineExceeded_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00598():
    # sdk_DeadlineExceeded_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00599():
    # sdk_DeadlineExceeded_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00600():
    # sdk_DeadlineExceeded_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00601():
    # sdk_DeadlineExceeded_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00602():
    # sdk_DeadlineExceeded_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00603():
    # sdk_DeadlineExceeded_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00604():
    # sdk_DeadlineExceeded_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00605():
    # sdk_DeadlineExceeded_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00606():
    # sdk_DeadlineExceeded_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00607():
    # sdk_DeadlineExceeded_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00608():
    # sdk_DeadlineExceeded_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00609():
    # sdk_DeadlineExceeded_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00610():
    # sdk_DeadlineExceeded_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00611():
    # sdk_DeadlineExceeded_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00612():
    # sdk_DeadlineExceeded_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00613():
    # sdk_DeadlineExceeded_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00614():
    # sdk_DeadlineExceeded_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00615():
    # sdk_DeadlineExceeded_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00616():
    # sdk_DeadlineExceeded_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00617():
    # sdk_DeadlineExceeded_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00618():
    # sdk_DeadlineExceeded_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00619():
    # sdk_DeadlineExceeded_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00620():
    # sdk_DeadlineExceeded_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00621():
    # sdk_DeadlineExceeded_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00622():
    # sdk_DeadlineExceeded_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00623():
    # sdk_DeadlineExceeded_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00624():
    # sdk_DeadlineExceeded_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00625():
    # sdk_DeadlineExceeded_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00626():
    # sdk_DeadlineExceeded_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00627():
    # sdk_DeadlineExceeded_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00628():
    # sdk_DeadlineExceeded_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00629():
    # sdk_DeadlineExceeded_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_DeadlineExceeded_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00630():
    # sdk_DuplicateCredentialArgs_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00631():
    # sdk_DuplicateCredentialArgs_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00632():
    # sdk_DuplicateCredentialArgs_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00633():
    # sdk_DuplicateCredentialArgs_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00634():
    # sdk_DuplicateCredentialArgs_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00635():
    # sdk_DuplicateCredentialArgs_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00636():
    # sdk_DuplicateCredentialArgs_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00637():
    # sdk_DuplicateCredentialArgs_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00638():
    # sdk_DuplicateCredentialArgs_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00639():
    # sdk_DuplicateCredentialArgs_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00640():
    # sdk_DuplicateCredentialArgs_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00641():
    # sdk_DuplicateCredentialArgs_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00642():
    # sdk_DuplicateCredentialArgs_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00643():
    # sdk_DuplicateCredentialArgs_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00644():
    # sdk_DuplicateCredentialArgs_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00645():
    # sdk_DuplicateCredentialArgs_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00646():
    # sdk_DuplicateCredentialArgs_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00647():
    # sdk_DuplicateCredentialArgs_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00648():
    # sdk_DuplicateCredentialArgs_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00649():
    # sdk_DuplicateCredentialArgs_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00650():
    # sdk_DuplicateCredentialArgs_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00651():
    # sdk_DuplicateCredentialArgs_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00652():
    # sdk_DuplicateCredentialArgs_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00653():
    # sdk_DuplicateCredentialArgs_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00654():
    # sdk_DuplicateCredentialArgs_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00655():
    # sdk_DuplicateCredentialArgs_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00656():
    # sdk_DuplicateCredentialArgs_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00657():
    # sdk_DuplicateCredentialArgs_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00658():
    # sdk_DuplicateCredentialArgs_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00659():
    # sdk_DuplicateCredentialArgs_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00660():
    # sdk_DuplicateCredentialArgs_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00661():
    # sdk_DuplicateCredentialArgs_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00662():
    # sdk_DuplicateCredentialArgs_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00663():
    # sdk_DuplicateCredentialArgs_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00664():
    # sdk_DuplicateCredentialArgs_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00665():
    # sdk_DuplicateCredentialArgs_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00666():
    # sdk_DuplicateCredentialArgs_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00667():
    # sdk_DuplicateCredentialArgs_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00668():
    # sdk_DuplicateCredentialArgs_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00669():
    # sdk_DuplicateCredentialArgs_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00670():
    # sdk_DuplicateCredentialArgs_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00671():
    # sdk_DuplicateCredentialArgs_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00672():
    # sdk_DuplicateCredentialArgs_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00673():
    # sdk_DuplicateCredentialArgs_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00674():
    # sdk_DuplicateCredentialArgs_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00675():
    # sdk_DuplicateCredentialArgs_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00676():
    # sdk_DuplicateCredentialArgs_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00677():
    # sdk_DuplicateCredentialArgs_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00678():
    # sdk_DuplicateCredentialArgs_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00679():
    # sdk_DuplicateCredentialArgs_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00680():
    # sdk_DuplicateCredentialArgs_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00681():
    # sdk_DuplicateCredentialArgs_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00682():
    # sdk_DuplicateCredentialArgs_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00683():
    # sdk_DuplicateCredentialArgs_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00684():
    # sdk_DuplicateCredentialArgs_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00685():
    # sdk_DuplicateCredentialArgs_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00686():
    # sdk_DuplicateCredentialArgs_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00687():
    # sdk_DuplicateCredentialArgs_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00688():
    # sdk_DuplicateCredentialArgs_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00689():
    # sdk_DuplicateCredentialArgs_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00690():
    # sdk_DuplicateCredentialArgs_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00691():
    # sdk_DuplicateCredentialArgs_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00692():
    # sdk_DuplicateCredentialArgs_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00693():
    # sdk_DuplicateCredentialArgs_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00694():
    # sdk_DuplicateCredentialArgs_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00695():
    # sdk_DuplicateCredentialArgs_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00696():
    # sdk_DuplicateCredentialArgs_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00697():
    # sdk_DuplicateCredentialArgs_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00698():
    # sdk_DuplicateCredentialArgs_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00699():
    # sdk_DuplicateCredentialArgs_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_DuplicateCredentialArgs_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00700():
    # sdk_FailedPrecondition_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00701():
    # sdk_FailedPrecondition_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00702():
    # sdk_FailedPrecondition_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00703():
    # sdk_FailedPrecondition_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00704():
    # sdk_FailedPrecondition_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00705():
    # sdk_FailedPrecondition_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00706():
    # sdk_FailedPrecondition_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00707():
    # sdk_FailedPrecondition_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00708():
    # sdk_FailedPrecondition_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00709():
    # sdk_FailedPrecondition_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00710():
    # sdk_FailedPrecondition_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00711():
    # sdk_FailedPrecondition_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00712():
    # sdk_FailedPrecondition_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00713():
    # sdk_FailedPrecondition_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00714():
    # sdk_FailedPrecondition_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00715():
    # sdk_FailedPrecondition_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00716():
    # sdk_FailedPrecondition_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00717():
    # sdk_FailedPrecondition_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00718():
    # sdk_FailedPrecondition_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00719():
    # sdk_FailedPrecondition_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00720():
    # sdk_FailedPrecondition_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00721():
    # sdk_FailedPrecondition_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00722():
    # sdk_FailedPrecondition_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00723():
    # sdk_FailedPrecondition_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00724():
    # sdk_FailedPrecondition_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00725():
    # sdk_FailedPrecondition_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00726():
    # sdk_FailedPrecondition_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00727():
    # sdk_FailedPrecondition_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00728():
    # sdk_FailedPrecondition_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00729():
    # sdk_FailedPrecondition_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00730():
    # sdk_FailedPrecondition_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00731():
    # sdk_FailedPrecondition_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00732():
    # sdk_FailedPrecondition_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00733():
    # sdk_FailedPrecondition_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00734():
    # sdk_FailedPrecondition_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00735():
    # sdk_FailedPrecondition_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00736():
    # sdk_FailedPrecondition_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00737():
    # sdk_FailedPrecondition_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00738():
    # sdk_FailedPrecondition_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00739():
    # sdk_FailedPrecondition_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00740():
    # sdk_FailedPrecondition_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00741():
    # sdk_FailedPrecondition_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00742():
    # sdk_FailedPrecondition_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00743():
    # sdk_FailedPrecondition_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00744():
    # sdk_FailedPrecondition_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00745():
    # sdk_FailedPrecondition_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00746():
    # sdk_FailedPrecondition_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00747():
    # sdk_FailedPrecondition_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00748():
    # sdk_FailedPrecondition_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00749():
    # sdk_FailedPrecondition_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00750():
    # sdk_FailedPrecondition_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00751():
    # sdk_FailedPrecondition_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00752():
    # sdk_FailedPrecondition_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00753():
    # sdk_FailedPrecondition_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00754():
    # sdk_FailedPrecondition_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00755():
    # sdk_FailedPrecondition_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00756():
    # sdk_FailedPrecondition_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00757():
    # sdk_FailedPrecondition_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00758():
    # sdk_FailedPrecondition_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00759():
    # sdk_FailedPrecondition_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00760():
    # sdk_FailedPrecondition_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00761():
    # sdk_FailedPrecondition_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00762():
    # sdk_FailedPrecondition_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00763():
    # sdk_FailedPrecondition_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00764():
    # sdk_FailedPrecondition_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00765():
    # sdk_FailedPrecondition_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00766():
    # sdk_FailedPrecondition_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00767():
    # sdk_FailedPrecondition_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00768():
    # sdk_FailedPrecondition_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00769():
    # sdk_FailedPrecondition_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_FailedPrecondition_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00770():
    # sdk_Forbidden_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Forbidden_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00771():
    # sdk_Forbidden_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Forbidden_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00772():
    # sdk_Forbidden_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Forbidden_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00773():
    # sdk_Forbidden_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Forbidden_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00774():
    # sdk_Forbidden_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Forbidden_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00775():
    # sdk_Forbidden_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Forbidden_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00776():
    # sdk_Forbidden_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Forbidden_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00777():
    # sdk_Forbidden_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00778():
    # sdk_Forbidden_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00779():
    # sdk_Forbidden_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00780():
    # sdk_Forbidden_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00781():
    # sdk_Forbidden_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00782():
    # sdk_Forbidden_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00783():
    # sdk_Forbidden_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00784():
    # sdk_Forbidden_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00785():
    # sdk_Forbidden_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00786():
    # sdk_Forbidden_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00787():
    # sdk_Forbidden_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00788():
    # sdk_Forbidden_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00789():
    # sdk_Forbidden_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00790():
    # sdk_Forbidden_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00791():
    # sdk_Forbidden_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00792():
    # sdk_Forbidden_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00793():
    # sdk_Forbidden_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00794():
    # sdk_Forbidden_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00795():
    # sdk_Forbidden_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00796():
    # sdk_Forbidden_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00797():
    # sdk_Forbidden_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00798():
    # sdk_Forbidden_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00799():
    # sdk_Forbidden_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00800():
    # sdk_Forbidden_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00801():
    # sdk_Forbidden_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00802():
    # sdk_Forbidden_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00803():
    # sdk_Forbidden_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00804():
    # sdk_Forbidden_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00805():
    # sdk_Forbidden_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Forbidden_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00806():
    # sdk_Forbidden_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Forbidden_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00807():
    # sdk_Forbidden_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Forbidden_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00808():
    # sdk_Forbidden_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Forbidden_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00809():
    # sdk_Forbidden_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Forbidden_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00810():
    # sdk_Forbidden_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Forbidden_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00811():
    # sdk_Forbidden_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Forbidden_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00812():
    # sdk_Forbidden_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00813():
    # sdk_Forbidden_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00814():
    # sdk_Forbidden_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00815():
    # sdk_Forbidden_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00816():
    # sdk_Forbidden_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00817():
    # sdk_Forbidden_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00818():
    # sdk_Forbidden_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00819():
    # sdk_Forbidden_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00820():
    # sdk_Forbidden_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00821():
    # sdk_Forbidden_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00822():
    # sdk_Forbidden_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00823():
    # sdk_Forbidden_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00824():
    # sdk_Forbidden_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00825():
    # sdk_Forbidden_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00826():
    # sdk_Forbidden_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00827():
    # sdk_Forbidden_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00828():
    # sdk_Forbidden_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00829():
    # sdk_Forbidden_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00830():
    # sdk_Forbidden_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00831():
    # sdk_Forbidden_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00832():
    # sdk_Forbidden_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00833():
    # sdk_Forbidden_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00834():
    # sdk_Forbidden_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00835():
    # sdk_Forbidden_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00836():
    # sdk_Forbidden_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00837():
    # sdk_Forbidden_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00838():
    # sdk_Forbidden_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00839():
    # sdk_Forbidden_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Forbidden_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00840():
    # sdk_GatewayTimeout_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00841():
    # sdk_GatewayTimeout_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00842():
    # sdk_GatewayTimeout_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00843():
    # sdk_GatewayTimeout_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00844():
    # sdk_GatewayTimeout_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00845():
    # sdk_GatewayTimeout_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00846():
    # sdk_GatewayTimeout_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00847():
    # sdk_GatewayTimeout_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00848():
    # sdk_GatewayTimeout_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00849():
    # sdk_GatewayTimeout_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00850():
    # sdk_GatewayTimeout_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00851():
    # sdk_GatewayTimeout_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00852():
    # sdk_GatewayTimeout_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00853():
    # sdk_GatewayTimeout_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00854():
    # sdk_GatewayTimeout_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00855():
    # sdk_GatewayTimeout_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00856():
    # sdk_GatewayTimeout_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00857():
    # sdk_GatewayTimeout_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00858():
    # sdk_GatewayTimeout_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00859():
    # sdk_GatewayTimeout_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00860():
    # sdk_GatewayTimeout_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00861():
    # sdk_GatewayTimeout_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00862():
    # sdk_GatewayTimeout_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00863():
    # sdk_GatewayTimeout_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00864():
    # sdk_GatewayTimeout_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00865():
    # sdk_GatewayTimeout_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00866():
    # sdk_GatewayTimeout_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00867():
    # sdk_GatewayTimeout_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00868():
    # sdk_GatewayTimeout_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00869():
    # sdk_GatewayTimeout_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00870():
    # sdk_GatewayTimeout_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00871():
    # sdk_GatewayTimeout_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00872():
    # sdk_GatewayTimeout_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00873():
    # sdk_GatewayTimeout_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00874():
    # sdk_GatewayTimeout_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00875():
    # sdk_GatewayTimeout_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00876():
    # sdk_GatewayTimeout_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00877():
    # sdk_GatewayTimeout_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00878():
    # sdk_GatewayTimeout_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00879():
    # sdk_GatewayTimeout_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00880():
    # sdk_GatewayTimeout_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00881():
    # sdk_GatewayTimeout_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00882():
    # sdk_GatewayTimeout_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00883():
    # sdk_GatewayTimeout_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00884():
    # sdk_GatewayTimeout_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00885():
    # sdk_GatewayTimeout_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00886():
    # sdk_GatewayTimeout_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00887():
    # sdk_GatewayTimeout_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00888():
    # sdk_GatewayTimeout_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00889():
    # sdk_GatewayTimeout_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00890():
    # sdk_GatewayTimeout_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00891():
    # sdk_GatewayTimeout_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00892():
    # sdk_GatewayTimeout_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00893():
    # sdk_GatewayTimeout_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00894():
    # sdk_GatewayTimeout_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00895():
    # sdk_GatewayTimeout_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00896():
    # sdk_GatewayTimeout_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00897():
    # sdk_GatewayTimeout_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00898():
    # sdk_GatewayTimeout_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00899():
    # sdk_GatewayTimeout_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00900():
    # sdk_GatewayTimeout_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00901():
    # sdk_GatewayTimeout_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00902():
    # sdk_GatewayTimeout_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00903():
    # sdk_GatewayTimeout_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00904():
    # sdk_GatewayTimeout_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00905():
    # sdk_GatewayTimeout_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00906():
    # sdk_GatewayTimeout_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00907():
    # sdk_GatewayTimeout_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00908():
    # sdk_GatewayTimeout_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00909():
    # sdk_GatewayTimeout_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_GatewayTimeout_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00910():
    # sdk_GoogleAPICallError_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00911():
    # sdk_GoogleAPICallError_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00912():
    # sdk_GoogleAPICallError_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00913():
    # sdk_GoogleAPICallError_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00914():
    # sdk_GoogleAPICallError_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00915():
    # sdk_GoogleAPICallError_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00916():
    # sdk_GoogleAPICallError_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00917():
    # sdk_GoogleAPICallError_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00918():
    # sdk_GoogleAPICallError_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00919():
    # sdk_GoogleAPICallError_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00920():
    # sdk_GoogleAPICallError_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00921():
    # sdk_GoogleAPICallError_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00922():
    # sdk_GoogleAPICallError_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00923():
    # sdk_GoogleAPICallError_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00924():
    # sdk_GoogleAPICallError_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00925():
    # sdk_GoogleAPICallError_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00926():
    # sdk_GoogleAPICallError_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00927():
    # sdk_GoogleAPICallError_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00928():
    # sdk_GoogleAPICallError_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00929():
    # sdk_GoogleAPICallError_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00930():
    # sdk_GoogleAPICallError_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00931():
    # sdk_GoogleAPICallError_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00932():
    # sdk_GoogleAPICallError_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00933():
    # sdk_GoogleAPICallError_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00934():
    # sdk_GoogleAPICallError_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00935():
    # sdk_GoogleAPICallError_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00936():
    # sdk_GoogleAPICallError_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00937():
    # sdk_GoogleAPICallError_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00938():
    # sdk_GoogleAPICallError_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00939():
    # sdk_GoogleAPICallError_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00940():
    # sdk_GoogleAPICallError_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00941():
    # sdk_GoogleAPICallError_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00942():
    # sdk_GoogleAPICallError_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00943():
    # sdk_GoogleAPICallError_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00944():
    # sdk_GoogleAPICallError_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00945():
    # sdk_GoogleAPICallError_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00946():
    # sdk_GoogleAPICallError_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00947():
    # sdk_GoogleAPICallError_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00948():
    # sdk_GoogleAPICallError_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00949():
    # sdk_GoogleAPICallError_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00950():
    # sdk_GoogleAPICallError_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00951():
    # sdk_GoogleAPICallError_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00952():
    # sdk_GoogleAPICallError_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00953():
    # sdk_GoogleAPICallError_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00954():
    # sdk_GoogleAPICallError_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00955():
    # sdk_GoogleAPICallError_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00956():
    # sdk_GoogleAPICallError_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00957():
    # sdk_GoogleAPICallError_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00958():
    # sdk_GoogleAPICallError_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00959():
    # sdk_GoogleAPICallError_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00960():
    # sdk_GoogleAPICallError_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00961():
    # sdk_GoogleAPICallError_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00962():
    # sdk_GoogleAPICallError_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00963():
    # sdk_GoogleAPICallError_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00964():
    # sdk_GoogleAPICallError_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00965():
    # sdk_GoogleAPICallError_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00966():
    # sdk_GoogleAPICallError_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00967():
    # sdk_GoogleAPICallError_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00968():
    # sdk_GoogleAPICallError_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00969():
    # sdk_GoogleAPICallError_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00970():
    # sdk_GoogleAPICallError_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00971():
    # sdk_GoogleAPICallError_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00972():
    # sdk_GoogleAPICallError_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00973():
    # sdk_GoogleAPICallError_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00974():
    # sdk_GoogleAPICallError_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00975():
    # sdk_GoogleAPICallError_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00976():
    # sdk_GoogleAPICallError_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00977():
    # sdk_GoogleAPICallError_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00978():
    # sdk_GoogleAPICallError_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00979():
    # sdk_GoogleAPICallError_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_GoogleAPICallError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00980():
    # sdk_GoogleAPIError_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00981():
    # sdk_GoogleAPIError_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00982():
    # sdk_GoogleAPIError_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00983():
    # sdk_GoogleAPIError_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00984():
    # sdk_GoogleAPIError_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00985():
    # sdk_GoogleAPIError_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00986():
    # sdk_GoogleAPIError_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00987():
    # sdk_GoogleAPIError_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00988():
    # sdk_GoogleAPIError_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00989():
    # sdk_GoogleAPIError_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00990():
    # sdk_GoogleAPIError_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00991():
    # sdk_GoogleAPIError_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00992():
    # sdk_GoogleAPIError_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00993():
    # sdk_GoogleAPIError_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00994():
    # sdk_GoogleAPIError_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_00995():
    # sdk_GoogleAPIError_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_00996():
    # sdk_GoogleAPIError_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_00997():
    # sdk_GoogleAPIError_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00998():
    # sdk_GoogleAPIError_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_00999():
    # sdk_GoogleAPIError_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01000():
    # sdk_GoogleAPIError_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01001():
    # sdk_GoogleAPIError_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01002():
    # sdk_GoogleAPIError_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01003():
    # sdk_GoogleAPIError_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01004():
    # sdk_GoogleAPIError_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01005():
    # sdk_GoogleAPIError_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01006():
    # sdk_GoogleAPIError_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01007():
    # sdk_GoogleAPIError_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01008():
    # sdk_GoogleAPIError_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01009():
    # sdk_GoogleAPIError_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01010():
    # sdk_GoogleAPIError_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01011():
    # sdk_GoogleAPIError_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01012():
    # sdk_GoogleAPIError_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01013():
    # sdk_GoogleAPIError_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01014():
    # sdk_GoogleAPIError_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01015():
    # sdk_GoogleAPIError_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01016():
    # sdk_GoogleAPIError_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01017():
    # sdk_GoogleAPIError_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01018():
    # sdk_GoogleAPIError_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01019():
    # sdk_GoogleAPIError_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01020():
    # sdk_GoogleAPIError_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01021():
    # sdk_GoogleAPIError_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01022():
    # sdk_GoogleAPIError_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01023():
    # sdk_GoogleAPIError_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01024():
    # sdk_GoogleAPIError_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01025():
    # sdk_GoogleAPIError_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01026():
    # sdk_GoogleAPIError_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01027():
    # sdk_GoogleAPIError_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01028():
    # sdk_GoogleAPIError_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01029():
    # sdk_GoogleAPIError_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01030():
    # sdk_GoogleAPIError_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01031():
    # sdk_GoogleAPIError_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01032():
    # sdk_GoogleAPIError_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01033():
    # sdk_GoogleAPIError_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01034():
    # sdk_GoogleAPIError_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01035():
    # sdk_GoogleAPIError_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01036():
    # sdk_GoogleAPIError_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01037():
    # sdk_GoogleAPIError_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01038():
    # sdk_GoogleAPIError_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01039():
    # sdk_GoogleAPIError_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01040():
    # sdk_GoogleAPIError_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01041():
    # sdk_GoogleAPIError_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01042():
    # sdk_GoogleAPIError_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01043():
    # sdk_GoogleAPIError_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01044():
    # sdk_GoogleAPIError_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01045():
    # sdk_GoogleAPIError_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01046():
    # sdk_GoogleAPIError_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01047():
    # sdk_GoogleAPIError_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01048():
    # sdk_GoogleAPIError_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01049():
    # sdk_GoogleAPIError_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_GoogleAPIError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01050():
    # sdk_InternalServerError_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_InternalServerError_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01051():
    # sdk_InternalServerError_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_InternalServerError_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01052():
    # sdk_InternalServerError_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_InternalServerError_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01053():
    # sdk_InternalServerError_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_InternalServerError_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01054():
    # sdk_InternalServerError_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_InternalServerError_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01055():
    # sdk_InternalServerError_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_InternalServerError_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01056():
    # sdk_InternalServerError_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_InternalServerError_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01057():
    # sdk_InternalServerError_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01058():
    # sdk_InternalServerError_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01059():
    # sdk_InternalServerError_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01060():
    # sdk_InternalServerError_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01061():
    # sdk_InternalServerError_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01062():
    # sdk_InternalServerError_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01063():
    # sdk_InternalServerError_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01064():
    # sdk_InternalServerError_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01065():
    # sdk_InternalServerError_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01066():
    # sdk_InternalServerError_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01067():
    # sdk_InternalServerError_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01068():
    # sdk_InternalServerError_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01069():
    # sdk_InternalServerError_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01070():
    # sdk_InternalServerError_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01071():
    # sdk_InternalServerError_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01072():
    # sdk_InternalServerError_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01073():
    # sdk_InternalServerError_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01074():
    # sdk_InternalServerError_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01075():
    # sdk_InternalServerError_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01076():
    # sdk_InternalServerError_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01077():
    # sdk_InternalServerError_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01078():
    # sdk_InternalServerError_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01079():
    # sdk_InternalServerError_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01080():
    # sdk_InternalServerError_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01081():
    # sdk_InternalServerError_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01082():
    # sdk_InternalServerError_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01083():
    # sdk_InternalServerError_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01084():
    # sdk_InternalServerError_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01085():
    # sdk_InternalServerError_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_InternalServerError_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01086():
    # sdk_InternalServerError_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_InternalServerError_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01087():
    # sdk_InternalServerError_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_InternalServerError_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01088():
    # sdk_InternalServerError_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_InternalServerError_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01089():
    # sdk_InternalServerError_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_InternalServerError_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01090():
    # sdk_InternalServerError_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_InternalServerError_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01091():
    # sdk_InternalServerError_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_InternalServerError_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01092():
    # sdk_InternalServerError_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01093():
    # sdk_InternalServerError_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01094():
    # sdk_InternalServerError_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01095():
    # sdk_InternalServerError_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01096():
    # sdk_InternalServerError_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01097():
    # sdk_InternalServerError_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01098():
    # sdk_InternalServerError_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01099():
    # sdk_InternalServerError_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01100():
    # sdk_InternalServerError_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01101():
    # sdk_InternalServerError_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01102():
    # sdk_InternalServerError_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01103():
    # sdk_InternalServerError_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01104():
    # sdk_InternalServerError_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01105():
    # sdk_InternalServerError_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01106():
    # sdk_InternalServerError_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01107():
    # sdk_InternalServerError_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01108():
    # sdk_InternalServerError_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01109():
    # sdk_InternalServerError_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01110():
    # sdk_InternalServerError_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01111():
    # sdk_InternalServerError_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01112():
    # sdk_InternalServerError_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01113():
    # sdk_InternalServerError_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01114():
    # sdk_InternalServerError_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01115():
    # sdk_InternalServerError_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01116():
    # sdk_InternalServerError_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01117():
    # sdk_InternalServerError_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01118():
    # sdk_InternalServerError_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01119():
    # sdk_InternalServerError_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_InternalServerError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01120():
    # sdk_InvalidArgument_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01121():
    # sdk_InvalidArgument_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01122():
    # sdk_InvalidArgument_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01123():
    # sdk_InvalidArgument_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01124():
    # sdk_InvalidArgument_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01125():
    # sdk_InvalidArgument_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01126():
    # sdk_InvalidArgument_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01127():
    # sdk_InvalidArgument_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01128():
    # sdk_InvalidArgument_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01129():
    # sdk_InvalidArgument_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01130():
    # sdk_InvalidArgument_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01131():
    # sdk_InvalidArgument_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01132():
    # sdk_InvalidArgument_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01133():
    # sdk_InvalidArgument_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01134():
    # sdk_InvalidArgument_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01135():
    # sdk_InvalidArgument_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01136():
    # sdk_InvalidArgument_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01137():
    # sdk_InvalidArgument_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01138():
    # sdk_InvalidArgument_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01139():
    # sdk_InvalidArgument_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01140():
    # sdk_InvalidArgument_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01141():
    # sdk_InvalidArgument_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01142():
    # sdk_InvalidArgument_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01143():
    # sdk_InvalidArgument_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01144():
    # sdk_InvalidArgument_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01145():
    # sdk_InvalidArgument_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01146():
    # sdk_InvalidArgument_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01147():
    # sdk_InvalidArgument_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01148():
    # sdk_InvalidArgument_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01149():
    # sdk_InvalidArgument_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01150():
    # sdk_InvalidArgument_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01151():
    # sdk_InvalidArgument_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01152():
    # sdk_InvalidArgument_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01153():
    # sdk_InvalidArgument_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01154():
    # sdk_InvalidArgument_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01155():
    # sdk_InvalidArgument_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01156():
    # sdk_InvalidArgument_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01157():
    # sdk_InvalidArgument_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01158():
    # sdk_InvalidArgument_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01159():
    # sdk_InvalidArgument_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01160():
    # sdk_InvalidArgument_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01161():
    # sdk_InvalidArgument_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01162():
    # sdk_InvalidArgument_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01163():
    # sdk_InvalidArgument_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01164():
    # sdk_InvalidArgument_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01165():
    # sdk_InvalidArgument_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01166():
    # sdk_InvalidArgument_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01167():
    # sdk_InvalidArgument_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01168():
    # sdk_InvalidArgument_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01169():
    # sdk_InvalidArgument_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01170():
    # sdk_InvalidArgument_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01171():
    # sdk_InvalidArgument_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01172():
    # sdk_InvalidArgument_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01173():
    # sdk_InvalidArgument_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01174():
    # sdk_InvalidArgument_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01175():
    # sdk_InvalidArgument_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01176():
    # sdk_InvalidArgument_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01177():
    # sdk_InvalidArgument_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01178():
    # sdk_InvalidArgument_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01179():
    # sdk_InvalidArgument_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01180():
    # sdk_InvalidArgument_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01181():
    # sdk_InvalidArgument_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01182():
    # sdk_InvalidArgument_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01183():
    # sdk_InvalidArgument_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01184():
    # sdk_InvalidArgument_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01185():
    # sdk_InvalidArgument_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01186():
    # sdk_InvalidArgument_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01187():
    # sdk_InvalidArgument_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01188():
    # sdk_InvalidArgument_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01189():
    # sdk_InvalidArgument_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_InvalidArgument_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01190():
    # sdk_LengthRequired_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_LengthRequired_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01191():
    # sdk_LengthRequired_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_LengthRequired_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01192():
    # sdk_LengthRequired_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_LengthRequired_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01193():
    # sdk_LengthRequired_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_LengthRequired_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01194():
    # sdk_LengthRequired_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_LengthRequired_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01195():
    # sdk_LengthRequired_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_LengthRequired_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01196():
    # sdk_LengthRequired_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_LengthRequired_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01197():
    # sdk_LengthRequired_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01198():
    # sdk_LengthRequired_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01199():
    # sdk_LengthRequired_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01200():
    # sdk_LengthRequired_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01201():
    # sdk_LengthRequired_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01202():
    # sdk_LengthRequired_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01203():
    # sdk_LengthRequired_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01204():
    # sdk_LengthRequired_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01205():
    # sdk_LengthRequired_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01206():
    # sdk_LengthRequired_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01207():
    # sdk_LengthRequired_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01208():
    # sdk_LengthRequired_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01209():
    # sdk_LengthRequired_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01210():
    # sdk_LengthRequired_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01211():
    # sdk_LengthRequired_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01212():
    # sdk_LengthRequired_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01213():
    # sdk_LengthRequired_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01214():
    # sdk_LengthRequired_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01215():
    # sdk_LengthRequired_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01216():
    # sdk_LengthRequired_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01217():
    # sdk_LengthRequired_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01218():
    # sdk_LengthRequired_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01219():
    # sdk_LengthRequired_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01220():
    # sdk_LengthRequired_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01221():
    # sdk_LengthRequired_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01222():
    # sdk_LengthRequired_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01223():
    # sdk_LengthRequired_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01224():
    # sdk_LengthRequired_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01225():
    # sdk_LengthRequired_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_LengthRequired_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01226():
    # sdk_LengthRequired_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_LengthRequired_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01227():
    # sdk_LengthRequired_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_LengthRequired_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01228():
    # sdk_LengthRequired_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_LengthRequired_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01229():
    # sdk_LengthRequired_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_LengthRequired_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01230():
    # sdk_LengthRequired_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_LengthRequired_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01231():
    # sdk_LengthRequired_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_LengthRequired_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01232():
    # sdk_LengthRequired_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01233():
    # sdk_LengthRequired_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01234():
    # sdk_LengthRequired_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01235():
    # sdk_LengthRequired_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01236():
    # sdk_LengthRequired_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01237():
    # sdk_LengthRequired_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01238():
    # sdk_LengthRequired_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01239():
    # sdk_LengthRequired_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01240():
    # sdk_LengthRequired_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01241():
    # sdk_LengthRequired_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01242():
    # sdk_LengthRequired_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01243():
    # sdk_LengthRequired_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01244():
    # sdk_LengthRequired_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01245():
    # sdk_LengthRequired_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01246():
    # sdk_LengthRequired_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01247():
    # sdk_LengthRequired_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01248():
    # sdk_LengthRequired_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01249():
    # sdk_LengthRequired_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01250():
    # sdk_LengthRequired_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01251():
    # sdk_LengthRequired_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01252():
    # sdk_LengthRequired_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01253():
    # sdk_LengthRequired_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01254():
    # sdk_LengthRequired_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01255():
    # sdk_LengthRequired_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01256():
    # sdk_LengthRequired_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01257():
    # sdk_LengthRequired_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01258():
    # sdk_LengthRequired_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01259():
    # sdk_LengthRequired_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_LengthRequired_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01260():
    # sdk_MethodNotAllowed_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01261():
    # sdk_MethodNotAllowed_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01262():
    # sdk_MethodNotAllowed_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01263():
    # sdk_MethodNotAllowed_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01264():
    # sdk_MethodNotAllowed_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01265():
    # sdk_MethodNotAllowed_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01266():
    # sdk_MethodNotAllowed_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01267():
    # sdk_MethodNotAllowed_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01268():
    # sdk_MethodNotAllowed_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01269():
    # sdk_MethodNotAllowed_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01270():
    # sdk_MethodNotAllowed_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01271():
    # sdk_MethodNotAllowed_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01272():
    # sdk_MethodNotAllowed_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01273():
    # sdk_MethodNotAllowed_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01274():
    # sdk_MethodNotAllowed_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01275():
    # sdk_MethodNotAllowed_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01276():
    # sdk_MethodNotAllowed_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01277():
    # sdk_MethodNotAllowed_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01278():
    # sdk_MethodNotAllowed_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01279():
    # sdk_MethodNotAllowed_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01280():
    # sdk_MethodNotAllowed_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01281():
    # sdk_MethodNotAllowed_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01282():
    # sdk_MethodNotAllowed_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01283():
    # sdk_MethodNotAllowed_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01284():
    # sdk_MethodNotAllowed_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01285():
    # sdk_MethodNotAllowed_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01286():
    # sdk_MethodNotAllowed_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01287():
    # sdk_MethodNotAllowed_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01288():
    # sdk_MethodNotAllowed_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01289():
    # sdk_MethodNotAllowed_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01290():
    # sdk_MethodNotAllowed_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01291():
    # sdk_MethodNotAllowed_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01292():
    # sdk_MethodNotAllowed_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01293():
    # sdk_MethodNotAllowed_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01294():
    # sdk_MethodNotAllowed_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01295():
    # sdk_MethodNotAllowed_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01296():
    # sdk_MethodNotAllowed_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01297():
    # sdk_MethodNotAllowed_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01298():
    # sdk_MethodNotAllowed_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01299():
    # sdk_MethodNotAllowed_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01300():
    # sdk_MethodNotAllowed_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01301():
    # sdk_MethodNotAllowed_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01302():
    # sdk_MethodNotAllowed_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01303():
    # sdk_MethodNotAllowed_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01304():
    # sdk_MethodNotAllowed_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01305():
    # sdk_MethodNotAllowed_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01306():
    # sdk_MethodNotAllowed_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01307():
    # sdk_MethodNotAllowed_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01308():
    # sdk_MethodNotAllowed_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01309():
    # sdk_MethodNotAllowed_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01310():
    # sdk_MethodNotAllowed_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01311():
    # sdk_MethodNotAllowed_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01312():
    # sdk_MethodNotAllowed_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01313():
    # sdk_MethodNotAllowed_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01314():
    # sdk_MethodNotAllowed_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01315():
    # sdk_MethodNotAllowed_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01316():
    # sdk_MethodNotAllowed_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01317():
    # sdk_MethodNotAllowed_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01318():
    # sdk_MethodNotAllowed_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01319():
    # sdk_MethodNotAllowed_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01320():
    # sdk_MethodNotAllowed_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01321():
    # sdk_MethodNotAllowed_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01322():
    # sdk_MethodNotAllowed_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01323():
    # sdk_MethodNotAllowed_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01324():
    # sdk_MethodNotAllowed_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01325():
    # sdk_MethodNotAllowed_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01326():
    # sdk_MethodNotAllowed_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01327():
    # sdk_MethodNotAllowed_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01328():
    # sdk_MethodNotAllowed_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01329():
    # sdk_MethodNotAllowed_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_MethodNotAllowed_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01330():
    # sdk_MethodNotImplemented_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01331():
    # sdk_MethodNotImplemented_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01332():
    # sdk_MethodNotImplemented_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01333():
    # sdk_MethodNotImplemented_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01334():
    # sdk_MethodNotImplemented_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01335():
    # sdk_MethodNotImplemented_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01336():
    # sdk_MethodNotImplemented_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01337():
    # sdk_MethodNotImplemented_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01338():
    # sdk_MethodNotImplemented_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01339():
    # sdk_MethodNotImplemented_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01340():
    # sdk_MethodNotImplemented_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01341():
    # sdk_MethodNotImplemented_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01342():
    # sdk_MethodNotImplemented_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01343():
    # sdk_MethodNotImplemented_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01344():
    # sdk_MethodNotImplemented_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01345():
    # sdk_MethodNotImplemented_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01346():
    # sdk_MethodNotImplemented_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01347():
    # sdk_MethodNotImplemented_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01348():
    # sdk_MethodNotImplemented_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01349():
    # sdk_MethodNotImplemented_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01350():
    # sdk_MethodNotImplemented_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01351():
    # sdk_MethodNotImplemented_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01352():
    # sdk_MethodNotImplemented_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01353():
    # sdk_MethodNotImplemented_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01354():
    # sdk_MethodNotImplemented_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01355():
    # sdk_MethodNotImplemented_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01356():
    # sdk_MethodNotImplemented_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01357():
    # sdk_MethodNotImplemented_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01358():
    # sdk_MethodNotImplemented_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01359():
    # sdk_MethodNotImplemented_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01360():
    # sdk_MethodNotImplemented_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01361():
    # sdk_MethodNotImplemented_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01362():
    # sdk_MethodNotImplemented_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01363():
    # sdk_MethodNotImplemented_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01364():
    # sdk_MethodNotImplemented_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01365():
    # sdk_MethodNotImplemented_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01366():
    # sdk_MethodNotImplemented_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01367():
    # sdk_MethodNotImplemented_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01368():
    # sdk_MethodNotImplemented_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01369():
    # sdk_MethodNotImplemented_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01370():
    # sdk_MethodNotImplemented_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01371():
    # sdk_MethodNotImplemented_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01372():
    # sdk_MethodNotImplemented_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01373():
    # sdk_MethodNotImplemented_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01374():
    # sdk_MethodNotImplemented_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01375():
    # sdk_MethodNotImplemented_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01376():
    # sdk_MethodNotImplemented_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01377():
    # sdk_MethodNotImplemented_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01378():
    # sdk_MethodNotImplemented_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01379():
    # sdk_MethodNotImplemented_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01380():
    # sdk_MethodNotImplemented_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01381():
    # sdk_MethodNotImplemented_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01382():
    # sdk_MethodNotImplemented_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01383():
    # sdk_MethodNotImplemented_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01384():
    # sdk_MethodNotImplemented_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01385():
    # sdk_MethodNotImplemented_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01386():
    # sdk_MethodNotImplemented_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01387():
    # sdk_MethodNotImplemented_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01388():
    # sdk_MethodNotImplemented_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01389():
    # sdk_MethodNotImplemented_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01390():
    # sdk_MethodNotImplemented_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01391():
    # sdk_MethodNotImplemented_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01392():
    # sdk_MethodNotImplemented_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01393():
    # sdk_MethodNotImplemented_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01394():
    # sdk_MethodNotImplemented_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01395():
    # sdk_MethodNotImplemented_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01396():
    # sdk_MethodNotImplemented_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01397():
    # sdk_MethodNotImplemented_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01398():
    # sdk_MethodNotImplemented_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01399():
    # sdk_MethodNotImplemented_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_MethodNotImplemented_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01400():
    # sdk_MovedPermanently_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01401():
    # sdk_MovedPermanently_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01402():
    # sdk_MovedPermanently_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01403():
    # sdk_MovedPermanently_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01404():
    # sdk_MovedPermanently_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01405():
    # sdk_MovedPermanently_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01406():
    # sdk_MovedPermanently_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01407():
    # sdk_MovedPermanently_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01408():
    # sdk_MovedPermanently_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01409():
    # sdk_MovedPermanently_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01410():
    # sdk_MovedPermanently_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01411():
    # sdk_MovedPermanently_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01412():
    # sdk_MovedPermanently_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01413():
    # sdk_MovedPermanently_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01414():
    # sdk_MovedPermanently_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01415():
    # sdk_MovedPermanently_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01416():
    # sdk_MovedPermanently_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01417():
    # sdk_MovedPermanently_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01418():
    # sdk_MovedPermanently_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01419():
    # sdk_MovedPermanently_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01420():
    # sdk_MovedPermanently_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01421():
    # sdk_MovedPermanently_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01422():
    # sdk_MovedPermanently_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01423():
    # sdk_MovedPermanently_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01424():
    # sdk_MovedPermanently_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01425():
    # sdk_MovedPermanently_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01426():
    # sdk_MovedPermanently_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01427():
    # sdk_MovedPermanently_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01428():
    # sdk_MovedPermanently_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01429():
    # sdk_MovedPermanently_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01430():
    # sdk_MovedPermanently_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01431():
    # sdk_MovedPermanently_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01432():
    # sdk_MovedPermanently_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01433():
    # sdk_MovedPermanently_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01434():
    # sdk_MovedPermanently_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01435():
    # sdk_MovedPermanently_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01436():
    # sdk_MovedPermanently_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01437():
    # sdk_MovedPermanently_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01438():
    # sdk_MovedPermanently_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01439():
    # sdk_MovedPermanently_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01440():
    # sdk_MovedPermanently_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01441():
    # sdk_MovedPermanently_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01442():
    # sdk_MovedPermanently_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01443():
    # sdk_MovedPermanently_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01444():
    # sdk_MovedPermanently_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01445():
    # sdk_MovedPermanently_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01446():
    # sdk_MovedPermanently_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01447():
    # sdk_MovedPermanently_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01448():
    # sdk_MovedPermanently_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01449():
    # sdk_MovedPermanently_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01450():
    # sdk_MovedPermanently_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01451():
    # sdk_MovedPermanently_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01452():
    # sdk_MovedPermanently_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01453():
    # sdk_MovedPermanently_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01454():
    # sdk_MovedPermanently_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01455():
    # sdk_MovedPermanently_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01456():
    # sdk_MovedPermanently_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01457():
    # sdk_MovedPermanently_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01458():
    # sdk_MovedPermanently_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01459():
    # sdk_MovedPermanently_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01460():
    # sdk_MovedPermanently_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01461():
    # sdk_MovedPermanently_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01462():
    # sdk_MovedPermanently_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01463():
    # sdk_MovedPermanently_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01464():
    # sdk_MovedPermanently_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01465():
    # sdk_MovedPermanently_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01466():
    # sdk_MovedPermanently_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01467():
    # sdk_MovedPermanently_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01468():
    # sdk_MovedPermanently_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01469():
    # sdk_MovedPermanently_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_MovedPermanently_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01470():
    # sdk_NotFound_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_NotFound_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01471():
    # sdk_NotFound_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_NotFound_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01472():
    # sdk_NotFound_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_NotFound_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01473():
    # sdk_NotFound_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_NotFound_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01474():
    # sdk_NotFound_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_NotFound_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01475():
    # sdk_NotFound_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_NotFound_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01476():
    # sdk_NotFound_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_NotFound_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01477():
    # sdk_NotFound_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01478():
    # sdk_NotFound_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01479():
    # sdk_NotFound_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01480():
    # sdk_NotFound_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01481():
    # sdk_NotFound_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01482():
    # sdk_NotFound_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01483():
    # sdk_NotFound_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01484():
    # sdk_NotFound_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01485():
    # sdk_NotFound_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01486():
    # sdk_NotFound_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01487():
    # sdk_NotFound_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01488():
    # sdk_NotFound_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01489():
    # sdk_NotFound_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01490():
    # sdk_NotFound_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01491():
    # sdk_NotFound_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01492():
    # sdk_NotFound_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01493():
    # sdk_NotFound_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01494():
    # sdk_NotFound_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01495():
    # sdk_NotFound_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01496():
    # sdk_NotFound_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01497():
    # sdk_NotFound_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01498():
    # sdk_NotFound_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01499():
    # sdk_NotFound_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01500():
    # sdk_NotFound_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01501():
    # sdk_NotFound_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01502():
    # sdk_NotFound_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01503():
    # sdk_NotFound_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01504():
    # sdk_NotFound_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01505():
    # sdk_NotFound_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_NotFound_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01506():
    # sdk_NotFound_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_NotFound_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01507():
    # sdk_NotFound_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_NotFound_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01508():
    # sdk_NotFound_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_NotFound_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01509():
    # sdk_NotFound_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_NotFound_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01510():
    # sdk_NotFound_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_NotFound_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01511():
    # sdk_NotFound_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_NotFound_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01512():
    # sdk_NotFound_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01513():
    # sdk_NotFound_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01514():
    # sdk_NotFound_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01515():
    # sdk_NotFound_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01516():
    # sdk_NotFound_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01517():
    # sdk_NotFound_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01518():
    # sdk_NotFound_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01519():
    # sdk_NotFound_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01520():
    # sdk_NotFound_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01521():
    # sdk_NotFound_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01522():
    # sdk_NotFound_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01523():
    # sdk_NotFound_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01524():
    # sdk_NotFound_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01525():
    # sdk_NotFound_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01526():
    # sdk_NotFound_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01527():
    # sdk_NotFound_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01528():
    # sdk_NotFound_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01529():
    # sdk_NotFound_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01530():
    # sdk_NotFound_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01531():
    # sdk_NotFound_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01532():
    # sdk_NotFound_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01533():
    # sdk_NotFound_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01534():
    # sdk_NotFound_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01535():
    # sdk_NotFound_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01536():
    # sdk_NotFound_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01537():
    # sdk_NotFound_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01538():
    # sdk_NotFound_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01539():
    # sdk_NotFound_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_NotFound_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01540():
    # sdk_NotModified_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_NotModified_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01541():
    # sdk_NotModified_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_NotModified_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01542():
    # sdk_NotModified_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_NotModified_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01543():
    # sdk_NotModified_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_NotModified_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01544():
    # sdk_NotModified_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_NotModified_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01545():
    # sdk_NotModified_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_NotModified_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01546():
    # sdk_NotModified_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_NotModified_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01547():
    # sdk_NotModified_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01548():
    # sdk_NotModified_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01549():
    # sdk_NotModified_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01550():
    # sdk_NotModified_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01551():
    # sdk_NotModified_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01552():
    # sdk_NotModified_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01553():
    # sdk_NotModified_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01554():
    # sdk_NotModified_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01555():
    # sdk_NotModified_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01556():
    # sdk_NotModified_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01557():
    # sdk_NotModified_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01558():
    # sdk_NotModified_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01559():
    # sdk_NotModified_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01560():
    # sdk_NotModified_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01561():
    # sdk_NotModified_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01562():
    # sdk_NotModified_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01563():
    # sdk_NotModified_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01564():
    # sdk_NotModified_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01565():
    # sdk_NotModified_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01566():
    # sdk_NotModified_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01567():
    # sdk_NotModified_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01568():
    # sdk_NotModified_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01569():
    # sdk_NotModified_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01570():
    # sdk_NotModified_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01571():
    # sdk_NotModified_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01572():
    # sdk_NotModified_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01573():
    # sdk_NotModified_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01574():
    # sdk_NotModified_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01575():
    # sdk_NotModified_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_NotModified_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01576():
    # sdk_NotModified_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_NotModified_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01577():
    # sdk_NotModified_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_NotModified_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01578():
    # sdk_NotModified_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_NotModified_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01579():
    # sdk_NotModified_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_NotModified_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01580():
    # sdk_NotModified_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_NotModified_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01581():
    # sdk_NotModified_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_NotModified_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01582():
    # sdk_NotModified_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01583():
    # sdk_NotModified_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01584():
    # sdk_NotModified_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01585():
    # sdk_NotModified_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01586():
    # sdk_NotModified_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01587():
    # sdk_NotModified_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01588():
    # sdk_NotModified_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01589():
    # sdk_NotModified_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01590():
    # sdk_NotModified_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01591():
    # sdk_NotModified_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01592():
    # sdk_NotModified_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01593():
    # sdk_NotModified_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01594():
    # sdk_NotModified_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01595():
    # sdk_NotModified_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01596():
    # sdk_NotModified_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01597():
    # sdk_NotModified_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01598():
    # sdk_NotModified_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01599():
    # sdk_NotModified_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01600():
    # sdk_NotModified_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01601():
    # sdk_NotModified_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01602():
    # sdk_NotModified_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01603():
    # sdk_NotModified_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01604():
    # sdk_NotModified_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01605():
    # sdk_NotModified_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01606():
    # sdk_NotModified_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01607():
    # sdk_NotModified_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01608():
    # sdk_NotModified_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01609():
    # sdk_NotModified_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_NotModified_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01610():
    # sdk_OutOfRange_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_OutOfRange_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01611():
    # sdk_OutOfRange_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_OutOfRange_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01612():
    # sdk_OutOfRange_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_OutOfRange_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01613():
    # sdk_OutOfRange_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_OutOfRange_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01614():
    # sdk_OutOfRange_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_OutOfRange_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01615():
    # sdk_OutOfRange_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_OutOfRange_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01616():
    # sdk_OutOfRange_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_OutOfRange_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01617():
    # sdk_OutOfRange_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01618():
    # sdk_OutOfRange_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01619():
    # sdk_OutOfRange_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01620():
    # sdk_OutOfRange_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01621():
    # sdk_OutOfRange_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01622():
    # sdk_OutOfRange_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01623():
    # sdk_OutOfRange_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01624():
    # sdk_OutOfRange_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01625():
    # sdk_OutOfRange_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01626():
    # sdk_OutOfRange_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01627():
    # sdk_OutOfRange_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01628():
    # sdk_OutOfRange_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01629():
    # sdk_OutOfRange_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01630():
    # sdk_OutOfRange_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01631():
    # sdk_OutOfRange_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01632():
    # sdk_OutOfRange_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01633():
    # sdk_OutOfRange_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01634():
    # sdk_OutOfRange_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01635():
    # sdk_OutOfRange_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01636():
    # sdk_OutOfRange_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01637():
    # sdk_OutOfRange_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01638():
    # sdk_OutOfRange_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01639():
    # sdk_OutOfRange_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01640():
    # sdk_OutOfRange_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01641():
    # sdk_OutOfRange_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01642():
    # sdk_OutOfRange_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01643():
    # sdk_OutOfRange_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01644():
    # sdk_OutOfRange_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01645():
    # sdk_OutOfRange_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_OutOfRange_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01646():
    # sdk_OutOfRange_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_OutOfRange_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01647():
    # sdk_OutOfRange_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_OutOfRange_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01648():
    # sdk_OutOfRange_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_OutOfRange_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01649():
    # sdk_OutOfRange_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_OutOfRange_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01650():
    # sdk_OutOfRange_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_OutOfRange_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01651():
    # sdk_OutOfRange_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_OutOfRange_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01652():
    # sdk_OutOfRange_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01653():
    # sdk_OutOfRange_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01654():
    # sdk_OutOfRange_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01655():
    # sdk_OutOfRange_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01656():
    # sdk_OutOfRange_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01657():
    # sdk_OutOfRange_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01658():
    # sdk_OutOfRange_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01659():
    # sdk_OutOfRange_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01660():
    # sdk_OutOfRange_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01661():
    # sdk_OutOfRange_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01662():
    # sdk_OutOfRange_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01663():
    # sdk_OutOfRange_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01664():
    # sdk_OutOfRange_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01665():
    # sdk_OutOfRange_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01666():
    # sdk_OutOfRange_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01667():
    # sdk_OutOfRange_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01668():
    # sdk_OutOfRange_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01669():
    # sdk_OutOfRange_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01670():
    # sdk_OutOfRange_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01671():
    # sdk_OutOfRange_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01672():
    # sdk_OutOfRange_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01673():
    # sdk_OutOfRange_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01674():
    # sdk_OutOfRange_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01675():
    # sdk_OutOfRange_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01676():
    # sdk_OutOfRange_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01677():
    # sdk_OutOfRange_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01678():
    # sdk_OutOfRange_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01679():
    # sdk_OutOfRange_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_OutOfRange_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01680():
    # sdk_PermissionDenied_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01681():
    # sdk_PermissionDenied_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01682():
    # sdk_PermissionDenied_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01683():
    # sdk_PermissionDenied_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01684():
    # sdk_PermissionDenied_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01685():
    # sdk_PermissionDenied_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01686():
    # sdk_PermissionDenied_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01687():
    # sdk_PermissionDenied_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01688():
    # sdk_PermissionDenied_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01689():
    # sdk_PermissionDenied_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01690():
    # sdk_PermissionDenied_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01691():
    # sdk_PermissionDenied_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01692():
    # sdk_PermissionDenied_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01693():
    # sdk_PermissionDenied_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01694():
    # sdk_PermissionDenied_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01695():
    # sdk_PermissionDenied_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01696():
    # sdk_PermissionDenied_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01697():
    # sdk_PermissionDenied_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01698():
    # sdk_PermissionDenied_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01699():
    # sdk_PermissionDenied_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01700():
    # sdk_PermissionDenied_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01701():
    # sdk_PermissionDenied_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01702():
    # sdk_PermissionDenied_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01703():
    # sdk_PermissionDenied_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01704():
    # sdk_PermissionDenied_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01705():
    # sdk_PermissionDenied_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01706():
    # sdk_PermissionDenied_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01707():
    # sdk_PermissionDenied_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01708():
    # sdk_PermissionDenied_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01709():
    # sdk_PermissionDenied_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01710():
    # sdk_PermissionDenied_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01711():
    # sdk_PermissionDenied_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01712():
    # sdk_PermissionDenied_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01713():
    # sdk_PermissionDenied_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01714():
    # sdk_PermissionDenied_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01715():
    # sdk_PermissionDenied_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01716():
    # sdk_PermissionDenied_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01717():
    # sdk_PermissionDenied_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01718():
    # sdk_PermissionDenied_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01719():
    # sdk_PermissionDenied_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01720():
    # sdk_PermissionDenied_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01721():
    # sdk_PermissionDenied_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01722():
    # sdk_PermissionDenied_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01723():
    # sdk_PermissionDenied_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01724():
    # sdk_PermissionDenied_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01725():
    # sdk_PermissionDenied_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01726():
    # sdk_PermissionDenied_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01727():
    # sdk_PermissionDenied_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01728():
    # sdk_PermissionDenied_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01729():
    # sdk_PermissionDenied_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01730():
    # sdk_PermissionDenied_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01731():
    # sdk_PermissionDenied_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01732():
    # sdk_PermissionDenied_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01733():
    # sdk_PermissionDenied_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01734():
    # sdk_PermissionDenied_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01735():
    # sdk_PermissionDenied_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01736():
    # sdk_PermissionDenied_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01737():
    # sdk_PermissionDenied_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01738():
    # sdk_PermissionDenied_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01739():
    # sdk_PermissionDenied_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01740():
    # sdk_PermissionDenied_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01741():
    # sdk_PermissionDenied_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01742():
    # sdk_PermissionDenied_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01743():
    # sdk_PermissionDenied_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01744():
    # sdk_PermissionDenied_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01745():
    # sdk_PermissionDenied_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01746():
    # sdk_PermissionDenied_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01747():
    # sdk_PermissionDenied_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01748():
    # sdk_PermissionDenied_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01749():
    # sdk_PermissionDenied_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_PermissionDenied_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01750():
    # sdk_PreconditionFailed_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01751():
    # sdk_PreconditionFailed_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01752():
    # sdk_PreconditionFailed_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01753():
    # sdk_PreconditionFailed_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01754():
    # sdk_PreconditionFailed_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01755():
    # sdk_PreconditionFailed_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01756():
    # sdk_PreconditionFailed_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01757():
    # sdk_PreconditionFailed_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01758():
    # sdk_PreconditionFailed_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01759():
    # sdk_PreconditionFailed_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01760():
    # sdk_PreconditionFailed_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01761():
    # sdk_PreconditionFailed_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01762():
    # sdk_PreconditionFailed_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01763():
    # sdk_PreconditionFailed_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01764():
    # sdk_PreconditionFailed_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01765():
    # sdk_PreconditionFailed_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01766():
    # sdk_PreconditionFailed_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01767():
    # sdk_PreconditionFailed_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01768():
    # sdk_PreconditionFailed_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01769():
    # sdk_PreconditionFailed_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01770():
    # sdk_PreconditionFailed_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01771():
    # sdk_PreconditionFailed_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01772():
    # sdk_PreconditionFailed_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01773():
    # sdk_PreconditionFailed_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01774():
    # sdk_PreconditionFailed_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01775():
    # sdk_PreconditionFailed_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01776():
    # sdk_PreconditionFailed_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01777():
    # sdk_PreconditionFailed_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01778():
    # sdk_PreconditionFailed_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01779():
    # sdk_PreconditionFailed_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01780():
    # sdk_PreconditionFailed_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01781():
    # sdk_PreconditionFailed_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01782():
    # sdk_PreconditionFailed_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01783():
    # sdk_PreconditionFailed_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01784():
    # sdk_PreconditionFailed_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01785():
    # sdk_PreconditionFailed_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01786():
    # sdk_PreconditionFailed_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01787():
    # sdk_PreconditionFailed_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01788():
    # sdk_PreconditionFailed_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01789():
    # sdk_PreconditionFailed_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01790():
    # sdk_PreconditionFailed_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01791():
    # sdk_PreconditionFailed_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01792():
    # sdk_PreconditionFailed_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01793():
    # sdk_PreconditionFailed_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01794():
    # sdk_PreconditionFailed_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01795():
    # sdk_PreconditionFailed_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01796():
    # sdk_PreconditionFailed_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01797():
    # sdk_PreconditionFailed_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01798():
    # sdk_PreconditionFailed_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01799():
    # sdk_PreconditionFailed_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01800():
    # sdk_PreconditionFailed_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01801():
    # sdk_PreconditionFailed_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01802():
    # sdk_PreconditionFailed_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01803():
    # sdk_PreconditionFailed_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01804():
    # sdk_PreconditionFailed_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01805():
    # sdk_PreconditionFailed_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01806():
    # sdk_PreconditionFailed_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01807():
    # sdk_PreconditionFailed_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01808():
    # sdk_PreconditionFailed_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01809():
    # sdk_PreconditionFailed_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01810():
    # sdk_PreconditionFailed_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01811():
    # sdk_PreconditionFailed_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01812():
    # sdk_PreconditionFailed_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01813():
    # sdk_PreconditionFailed_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01814():
    # sdk_PreconditionFailed_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01815():
    # sdk_PreconditionFailed_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01816():
    # sdk_PreconditionFailed_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01817():
    # sdk_PreconditionFailed_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01818():
    # sdk_PreconditionFailed_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01819():
    # sdk_PreconditionFailed_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_PreconditionFailed_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01820():
    # sdk_Redirection_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Redirection_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01821():
    # sdk_Redirection_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Redirection_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01822():
    # sdk_Redirection_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Redirection_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01823():
    # sdk_Redirection_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Redirection_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01824():
    # sdk_Redirection_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Redirection_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01825():
    # sdk_Redirection_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Redirection_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01826():
    # sdk_Redirection_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Redirection_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01827():
    # sdk_Redirection_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01828():
    # sdk_Redirection_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01829():
    # sdk_Redirection_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01830():
    # sdk_Redirection_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01831():
    # sdk_Redirection_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01832():
    # sdk_Redirection_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01833():
    # sdk_Redirection_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01834():
    # sdk_Redirection_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01835():
    # sdk_Redirection_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01836():
    # sdk_Redirection_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01837():
    # sdk_Redirection_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01838():
    # sdk_Redirection_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01839():
    # sdk_Redirection_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01840():
    # sdk_Redirection_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01841():
    # sdk_Redirection_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01842():
    # sdk_Redirection_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01843():
    # sdk_Redirection_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01844():
    # sdk_Redirection_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01845():
    # sdk_Redirection_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01846():
    # sdk_Redirection_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01847():
    # sdk_Redirection_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01848():
    # sdk_Redirection_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01849():
    # sdk_Redirection_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01850():
    # sdk_Redirection_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01851():
    # sdk_Redirection_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01852():
    # sdk_Redirection_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01853():
    # sdk_Redirection_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01854():
    # sdk_Redirection_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01855():
    # sdk_Redirection_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Redirection_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01856():
    # sdk_Redirection_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Redirection_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01857():
    # sdk_Redirection_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Redirection_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01858():
    # sdk_Redirection_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Redirection_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01859():
    # sdk_Redirection_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Redirection_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01860():
    # sdk_Redirection_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Redirection_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01861():
    # sdk_Redirection_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Redirection_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01862():
    # sdk_Redirection_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01863():
    # sdk_Redirection_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01864():
    # sdk_Redirection_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01865():
    # sdk_Redirection_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01866():
    # sdk_Redirection_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01867():
    # sdk_Redirection_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01868():
    # sdk_Redirection_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01869():
    # sdk_Redirection_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01870():
    # sdk_Redirection_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01871():
    # sdk_Redirection_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01872():
    # sdk_Redirection_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01873():
    # sdk_Redirection_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01874():
    # sdk_Redirection_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01875():
    # sdk_Redirection_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01876():
    # sdk_Redirection_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01877():
    # sdk_Redirection_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01878():
    # sdk_Redirection_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01879():
    # sdk_Redirection_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01880():
    # sdk_Redirection_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01881():
    # sdk_Redirection_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01882():
    # sdk_Redirection_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01883():
    # sdk_Redirection_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01884():
    # sdk_Redirection_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01885():
    # sdk_Redirection_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01886():
    # sdk_Redirection_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01887():
    # sdk_Redirection_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01888():
    # sdk_Redirection_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01889():
    # sdk_Redirection_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Redirection_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01890():
    # sdk_RequestRangeNotSatisfiable_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01891():
    # sdk_RequestRangeNotSatisfiable_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01892():
    # sdk_RequestRangeNotSatisfiable_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01893():
    # sdk_RequestRangeNotSatisfiable_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01894():
    # sdk_RequestRangeNotSatisfiable_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01895():
    # sdk_RequestRangeNotSatisfiable_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01896():
    # sdk_RequestRangeNotSatisfiable_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01897():
    # sdk_RequestRangeNotSatisfiable_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01898():
    # sdk_RequestRangeNotSatisfiable_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01899():
    # sdk_RequestRangeNotSatisfiable_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01900():
    # sdk_RequestRangeNotSatisfiable_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01901():
    # sdk_RequestRangeNotSatisfiable_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01902():
    # sdk_RequestRangeNotSatisfiable_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01903():
    # sdk_RequestRangeNotSatisfiable_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01904():
    # sdk_RequestRangeNotSatisfiable_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01905():
    # sdk_RequestRangeNotSatisfiable_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01906():
    # sdk_RequestRangeNotSatisfiable_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01907():
    # sdk_RequestRangeNotSatisfiable_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01908():
    # sdk_RequestRangeNotSatisfiable_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01909():
    # sdk_RequestRangeNotSatisfiable_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01910():
    # sdk_RequestRangeNotSatisfiable_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01911():
    # sdk_RequestRangeNotSatisfiable_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01912():
    # sdk_RequestRangeNotSatisfiable_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01913():
    # sdk_RequestRangeNotSatisfiable_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01914():
    # sdk_RequestRangeNotSatisfiable_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01915():
    # sdk_RequestRangeNotSatisfiable_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01916():
    # sdk_RequestRangeNotSatisfiable_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01917():
    # sdk_RequestRangeNotSatisfiable_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01918():
    # sdk_RequestRangeNotSatisfiable_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01919():
    # sdk_RequestRangeNotSatisfiable_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01920():
    # sdk_RequestRangeNotSatisfiable_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01921():
    # sdk_RequestRangeNotSatisfiable_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01922():
    # sdk_RequestRangeNotSatisfiable_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01923():
    # sdk_RequestRangeNotSatisfiable_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01924():
    # sdk_RequestRangeNotSatisfiable_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01925():
    # sdk_RequestRangeNotSatisfiable_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01926():
    # sdk_RequestRangeNotSatisfiable_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01927():
    # sdk_RequestRangeNotSatisfiable_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01928():
    # sdk_RequestRangeNotSatisfiable_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01929():
    # sdk_RequestRangeNotSatisfiable_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01930():
    # sdk_RequestRangeNotSatisfiable_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01931():
    # sdk_RequestRangeNotSatisfiable_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01932():
    # sdk_RequestRangeNotSatisfiable_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01933():
    # sdk_RequestRangeNotSatisfiable_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01934():
    # sdk_RequestRangeNotSatisfiable_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01935():
    # sdk_RequestRangeNotSatisfiable_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01936():
    # sdk_RequestRangeNotSatisfiable_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01937():
    # sdk_RequestRangeNotSatisfiable_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01938():
    # sdk_RequestRangeNotSatisfiable_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01939():
    # sdk_RequestRangeNotSatisfiable_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01940():
    # sdk_RequestRangeNotSatisfiable_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01941():
    # sdk_RequestRangeNotSatisfiable_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01942():
    # sdk_RequestRangeNotSatisfiable_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01943():
    # sdk_RequestRangeNotSatisfiable_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01944():
    # sdk_RequestRangeNotSatisfiable_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01945():
    # sdk_RequestRangeNotSatisfiable_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01946():
    # sdk_RequestRangeNotSatisfiable_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01947():
    # sdk_RequestRangeNotSatisfiable_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01948():
    # sdk_RequestRangeNotSatisfiable_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01949():
    # sdk_RequestRangeNotSatisfiable_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01950():
    # sdk_RequestRangeNotSatisfiable_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01951():
    # sdk_RequestRangeNotSatisfiable_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01952():
    # sdk_RequestRangeNotSatisfiable_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01953():
    # sdk_RequestRangeNotSatisfiable_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01954():
    # sdk_RequestRangeNotSatisfiable_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01955():
    # sdk_RequestRangeNotSatisfiable_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01956():
    # sdk_RequestRangeNotSatisfiable_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01957():
    # sdk_RequestRangeNotSatisfiable_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01958():
    # sdk_RequestRangeNotSatisfiable_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01959():
    # sdk_RequestRangeNotSatisfiable_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_RequestRangeNotSatisfiable_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01960():
    # sdk_ResourceExhausted_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01961():
    # sdk_ResourceExhausted_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01962():
    # sdk_ResourceExhausted_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01963():
    # sdk_ResourceExhausted_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01964():
    # sdk_ResourceExhausted_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01965():
    # sdk_ResourceExhausted_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01966():
    # sdk_ResourceExhausted_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01967():
    # sdk_ResourceExhausted_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01968():
    # sdk_ResourceExhausted_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01969():
    # sdk_ResourceExhausted_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01970():
    # sdk_ResourceExhausted_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01971():
    # sdk_ResourceExhausted_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01972():
    # sdk_ResourceExhausted_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01973():
    # sdk_ResourceExhausted_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01974():
    # sdk_ResourceExhausted_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01975():
    # sdk_ResourceExhausted_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01976():
    # sdk_ResourceExhausted_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01977():
    # sdk_ResourceExhausted_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01978():
    # sdk_ResourceExhausted_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01979():
    # sdk_ResourceExhausted_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01980():
    # sdk_ResourceExhausted_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01981():
    # sdk_ResourceExhausted_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01982():
    # sdk_ResourceExhausted_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01983():
    # sdk_ResourceExhausted_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01984():
    # sdk_ResourceExhausted_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01985():
    # sdk_ResourceExhausted_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01986():
    # sdk_ResourceExhausted_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01987():
    # sdk_ResourceExhausted_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01988():
    # sdk_ResourceExhausted_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01989():
    # sdk_ResourceExhausted_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01990():
    # sdk_ResourceExhausted_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01991():
    # sdk_ResourceExhausted_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01992():
    # sdk_ResourceExhausted_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01993():
    # sdk_ResourceExhausted_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01994():
    # sdk_ResourceExhausted_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01995():
    # sdk_ResourceExhausted_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_01996():
    # sdk_ResourceExhausted_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_01997():
    # sdk_ResourceExhausted_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_01998():
    # sdk_ResourceExhausted_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_01999():
    # sdk_ResourceExhausted_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02000():
    # sdk_ResourceExhausted_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02001():
    # sdk_ResourceExhausted_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02002():
    # sdk_ResourceExhausted_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02003():
    # sdk_ResourceExhausted_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02004():
    # sdk_ResourceExhausted_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02005():
    # sdk_ResourceExhausted_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02006():
    # sdk_ResourceExhausted_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02007():
    # sdk_ResourceExhausted_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02008():
    # sdk_ResourceExhausted_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02009():
    # sdk_ResourceExhausted_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02010():
    # sdk_ResourceExhausted_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02011():
    # sdk_ResourceExhausted_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02012():
    # sdk_ResourceExhausted_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02013():
    # sdk_ResourceExhausted_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02014():
    # sdk_ResourceExhausted_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02015():
    # sdk_ResourceExhausted_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02016():
    # sdk_ResourceExhausted_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02017():
    # sdk_ResourceExhausted_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02018():
    # sdk_ResourceExhausted_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02019():
    # sdk_ResourceExhausted_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02020():
    # sdk_ResourceExhausted_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02021():
    # sdk_ResourceExhausted_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02022():
    # sdk_ResourceExhausted_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02023():
    # sdk_ResourceExhausted_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02024():
    # sdk_ResourceExhausted_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02025():
    # sdk_ResourceExhausted_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02026():
    # sdk_ResourceExhausted_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02027():
    # sdk_ResourceExhausted_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02028():
    # sdk_ResourceExhausted_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02029():
    # sdk_ResourceExhausted_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_ResourceExhausted_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02030():
    # sdk_ResumeIncomplete_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02031():
    # sdk_ResumeIncomplete_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02032():
    # sdk_ResumeIncomplete_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02033():
    # sdk_ResumeIncomplete_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02034():
    # sdk_ResumeIncomplete_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02035():
    # sdk_ResumeIncomplete_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02036():
    # sdk_ResumeIncomplete_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02037():
    # sdk_ResumeIncomplete_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02038():
    # sdk_ResumeIncomplete_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02039():
    # sdk_ResumeIncomplete_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02040():
    # sdk_ResumeIncomplete_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02041():
    # sdk_ResumeIncomplete_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02042():
    # sdk_ResumeIncomplete_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02043():
    # sdk_ResumeIncomplete_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02044():
    # sdk_ResumeIncomplete_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02045():
    # sdk_ResumeIncomplete_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02046():
    # sdk_ResumeIncomplete_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02047():
    # sdk_ResumeIncomplete_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02048():
    # sdk_ResumeIncomplete_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02049():
    # sdk_ResumeIncomplete_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02050():
    # sdk_ResumeIncomplete_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02051():
    # sdk_ResumeIncomplete_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02052():
    # sdk_ResumeIncomplete_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02053():
    # sdk_ResumeIncomplete_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02054():
    # sdk_ResumeIncomplete_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02055():
    # sdk_ResumeIncomplete_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02056():
    # sdk_ResumeIncomplete_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02057():
    # sdk_ResumeIncomplete_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02058():
    # sdk_ResumeIncomplete_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02059():
    # sdk_ResumeIncomplete_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02060():
    # sdk_ResumeIncomplete_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02061():
    # sdk_ResumeIncomplete_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02062():
    # sdk_ResumeIncomplete_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02063():
    # sdk_ResumeIncomplete_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02064():
    # sdk_ResumeIncomplete_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02065():
    # sdk_ResumeIncomplete_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02066():
    # sdk_ResumeIncomplete_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02067():
    # sdk_ResumeIncomplete_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02068():
    # sdk_ResumeIncomplete_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02069():
    # sdk_ResumeIncomplete_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02070():
    # sdk_ResumeIncomplete_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02071():
    # sdk_ResumeIncomplete_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02072():
    # sdk_ResumeIncomplete_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02073():
    # sdk_ResumeIncomplete_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02074():
    # sdk_ResumeIncomplete_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02075():
    # sdk_ResumeIncomplete_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02076():
    # sdk_ResumeIncomplete_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02077():
    # sdk_ResumeIncomplete_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02078():
    # sdk_ResumeIncomplete_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02079():
    # sdk_ResumeIncomplete_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02080():
    # sdk_ResumeIncomplete_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02081():
    # sdk_ResumeIncomplete_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02082():
    # sdk_ResumeIncomplete_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02083():
    # sdk_ResumeIncomplete_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02084():
    # sdk_ResumeIncomplete_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02085():
    # sdk_ResumeIncomplete_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02086():
    # sdk_ResumeIncomplete_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02087():
    # sdk_ResumeIncomplete_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02088():
    # sdk_ResumeIncomplete_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02089():
    # sdk_ResumeIncomplete_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02090():
    # sdk_ResumeIncomplete_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02091():
    # sdk_ResumeIncomplete_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02092():
    # sdk_ResumeIncomplete_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02093():
    # sdk_ResumeIncomplete_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02094():
    # sdk_ResumeIncomplete_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02095():
    # sdk_ResumeIncomplete_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02096():
    # sdk_ResumeIncomplete_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02097():
    # sdk_ResumeIncomplete_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02098():
    # sdk_ResumeIncomplete_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02099():
    # sdk_ResumeIncomplete_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_ResumeIncomplete_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02100():
    # sdk_ServerError_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_ServerError_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02101():
    # sdk_ServerError_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_ServerError_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02102():
    # sdk_ServerError_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_ServerError_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02103():
    # sdk_ServerError_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_ServerError_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02104():
    # sdk_ServerError_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_ServerError_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02105():
    # sdk_ServerError_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_ServerError_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02106():
    # sdk_ServerError_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_ServerError_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02107():
    # sdk_ServerError_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02108():
    # sdk_ServerError_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02109():
    # sdk_ServerError_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02110():
    # sdk_ServerError_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02111():
    # sdk_ServerError_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02112():
    # sdk_ServerError_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02113():
    # sdk_ServerError_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02114():
    # sdk_ServerError_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02115():
    # sdk_ServerError_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02116():
    # sdk_ServerError_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02117():
    # sdk_ServerError_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02118():
    # sdk_ServerError_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02119():
    # sdk_ServerError_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02120():
    # sdk_ServerError_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02121():
    # sdk_ServerError_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02122():
    # sdk_ServerError_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02123():
    # sdk_ServerError_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02124():
    # sdk_ServerError_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02125():
    # sdk_ServerError_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02126():
    # sdk_ServerError_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02127():
    # sdk_ServerError_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02128():
    # sdk_ServerError_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02129():
    # sdk_ServerError_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02130():
    # sdk_ServerError_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02131():
    # sdk_ServerError_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02132():
    # sdk_ServerError_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02133():
    # sdk_ServerError_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02134():
    # sdk_ServerError_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02135():
    # sdk_ServerError_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_ServerError_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02136():
    # sdk_ServerError_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_ServerError_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02137():
    # sdk_ServerError_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_ServerError_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02138():
    # sdk_ServerError_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_ServerError_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02139():
    # sdk_ServerError_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_ServerError_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02140():
    # sdk_ServerError_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_ServerError_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02141():
    # sdk_ServerError_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_ServerError_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02142():
    # sdk_ServerError_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02143():
    # sdk_ServerError_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02144():
    # sdk_ServerError_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02145():
    # sdk_ServerError_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02146():
    # sdk_ServerError_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02147():
    # sdk_ServerError_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02148():
    # sdk_ServerError_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02149():
    # sdk_ServerError_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02150():
    # sdk_ServerError_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02151():
    # sdk_ServerError_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02152():
    # sdk_ServerError_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02153():
    # sdk_ServerError_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02154():
    # sdk_ServerError_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02155():
    # sdk_ServerError_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02156():
    # sdk_ServerError_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02157():
    # sdk_ServerError_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02158():
    # sdk_ServerError_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02159():
    # sdk_ServerError_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02160():
    # sdk_ServerError_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02161():
    # sdk_ServerError_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02162():
    # sdk_ServerError_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02163():
    # sdk_ServerError_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02164():
    # sdk_ServerError_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02165():
    # sdk_ServerError_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02166():
    # sdk_ServerError_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02167():
    # sdk_ServerError_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02168():
    # sdk_ServerError_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02169():
    # sdk_ServerError_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_ServerError_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02170():
    # sdk_ServiceUnavailable_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02171():
    # sdk_ServiceUnavailable_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02172():
    # sdk_ServiceUnavailable_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02173():
    # sdk_ServiceUnavailable_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02174():
    # sdk_ServiceUnavailable_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02175():
    # sdk_ServiceUnavailable_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02176():
    # sdk_ServiceUnavailable_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02177():
    # sdk_ServiceUnavailable_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02178():
    # sdk_ServiceUnavailable_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02179():
    # sdk_ServiceUnavailable_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02180():
    # sdk_ServiceUnavailable_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02181():
    # sdk_ServiceUnavailable_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02182():
    # sdk_ServiceUnavailable_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02183():
    # sdk_ServiceUnavailable_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02184():
    # sdk_ServiceUnavailable_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02185():
    # sdk_ServiceUnavailable_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02186():
    # sdk_ServiceUnavailable_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02187():
    # sdk_ServiceUnavailable_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02188():
    # sdk_ServiceUnavailable_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02189():
    # sdk_ServiceUnavailable_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02190():
    # sdk_ServiceUnavailable_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02191():
    # sdk_ServiceUnavailable_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02192():
    # sdk_ServiceUnavailable_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02193():
    # sdk_ServiceUnavailable_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02194():
    # sdk_ServiceUnavailable_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02195():
    # sdk_ServiceUnavailable_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02196():
    # sdk_ServiceUnavailable_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02197():
    # sdk_ServiceUnavailable_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02198():
    # sdk_ServiceUnavailable_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02199():
    # sdk_ServiceUnavailable_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02200():
    # sdk_ServiceUnavailable_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02201():
    # sdk_ServiceUnavailable_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02202():
    # sdk_ServiceUnavailable_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02203():
    # sdk_ServiceUnavailable_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02204():
    # sdk_ServiceUnavailable_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02205():
    # sdk_ServiceUnavailable_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02206():
    # sdk_ServiceUnavailable_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02207():
    # sdk_ServiceUnavailable_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02208():
    # sdk_ServiceUnavailable_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02209():
    # sdk_ServiceUnavailable_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02210():
    # sdk_ServiceUnavailable_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02211():
    # sdk_ServiceUnavailable_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02212():
    # sdk_ServiceUnavailable_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02213():
    # sdk_ServiceUnavailable_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02214():
    # sdk_ServiceUnavailable_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02215():
    # sdk_ServiceUnavailable_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02216():
    # sdk_ServiceUnavailable_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02217():
    # sdk_ServiceUnavailable_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02218():
    # sdk_ServiceUnavailable_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02219():
    # sdk_ServiceUnavailable_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02220():
    # sdk_ServiceUnavailable_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02221():
    # sdk_ServiceUnavailable_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02222():
    # sdk_ServiceUnavailable_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02223():
    # sdk_ServiceUnavailable_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02224():
    # sdk_ServiceUnavailable_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02225():
    # sdk_ServiceUnavailable_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02226():
    # sdk_ServiceUnavailable_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02227():
    # sdk_ServiceUnavailable_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02228():
    # sdk_ServiceUnavailable_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02229():
    # sdk_ServiceUnavailable_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02230():
    # sdk_ServiceUnavailable_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02231():
    # sdk_ServiceUnavailable_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02232():
    # sdk_ServiceUnavailable_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02233():
    # sdk_ServiceUnavailable_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02234():
    # sdk_ServiceUnavailable_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02235():
    # sdk_ServiceUnavailable_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02236():
    # sdk_ServiceUnavailable_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02237():
    # sdk_ServiceUnavailable_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02238():
    # sdk_ServiceUnavailable_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02239():
    # sdk_ServiceUnavailable_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_ServiceUnavailable_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02240():
    # sdk_TemporaryRedirect_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02241():
    # sdk_TemporaryRedirect_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02242():
    # sdk_TemporaryRedirect_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02243():
    # sdk_TemporaryRedirect_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02244():
    # sdk_TemporaryRedirect_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02245():
    # sdk_TemporaryRedirect_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02246():
    # sdk_TemporaryRedirect_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02247():
    # sdk_TemporaryRedirect_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02248():
    # sdk_TemporaryRedirect_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02249():
    # sdk_TemporaryRedirect_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02250():
    # sdk_TemporaryRedirect_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02251():
    # sdk_TemporaryRedirect_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02252():
    # sdk_TemporaryRedirect_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02253():
    # sdk_TemporaryRedirect_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02254():
    # sdk_TemporaryRedirect_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02255():
    # sdk_TemporaryRedirect_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02256():
    # sdk_TemporaryRedirect_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02257():
    # sdk_TemporaryRedirect_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02258():
    # sdk_TemporaryRedirect_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02259():
    # sdk_TemporaryRedirect_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02260():
    # sdk_TemporaryRedirect_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02261():
    # sdk_TemporaryRedirect_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02262():
    # sdk_TemporaryRedirect_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02263():
    # sdk_TemporaryRedirect_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02264():
    # sdk_TemporaryRedirect_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02265():
    # sdk_TemporaryRedirect_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02266():
    # sdk_TemporaryRedirect_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02267():
    # sdk_TemporaryRedirect_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02268():
    # sdk_TemporaryRedirect_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02269():
    # sdk_TemporaryRedirect_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02270():
    # sdk_TemporaryRedirect_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02271():
    # sdk_TemporaryRedirect_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02272():
    # sdk_TemporaryRedirect_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02273():
    # sdk_TemporaryRedirect_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02274():
    # sdk_TemporaryRedirect_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02275():
    # sdk_TemporaryRedirect_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02276():
    # sdk_TemporaryRedirect_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02277():
    # sdk_TemporaryRedirect_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02278():
    # sdk_TemporaryRedirect_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02279():
    # sdk_TemporaryRedirect_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02280():
    # sdk_TemporaryRedirect_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02281():
    # sdk_TemporaryRedirect_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02282():
    # sdk_TemporaryRedirect_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02283():
    # sdk_TemporaryRedirect_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02284():
    # sdk_TemporaryRedirect_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02285():
    # sdk_TemporaryRedirect_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02286():
    # sdk_TemporaryRedirect_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02287():
    # sdk_TemporaryRedirect_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02288():
    # sdk_TemporaryRedirect_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02289():
    # sdk_TemporaryRedirect_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02290():
    # sdk_TemporaryRedirect_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02291():
    # sdk_TemporaryRedirect_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02292():
    # sdk_TemporaryRedirect_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02293():
    # sdk_TemporaryRedirect_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02294():
    # sdk_TemporaryRedirect_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02295():
    # sdk_TemporaryRedirect_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02296():
    # sdk_TemporaryRedirect_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02297():
    # sdk_TemporaryRedirect_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02298():
    # sdk_TemporaryRedirect_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02299():
    # sdk_TemporaryRedirect_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02300():
    # sdk_TemporaryRedirect_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02301():
    # sdk_TemporaryRedirect_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02302():
    # sdk_TemporaryRedirect_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02303():
    # sdk_TemporaryRedirect_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02304():
    # sdk_TemporaryRedirect_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02305():
    # sdk_TemporaryRedirect_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02306():
    # sdk_TemporaryRedirect_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02307():
    # sdk_TemporaryRedirect_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02308():
    # sdk_TemporaryRedirect_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02309():
    # sdk_TemporaryRedirect_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_TemporaryRedirect_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02310():
    # sdk_TooManyRequests_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02311():
    # sdk_TooManyRequests_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02312():
    # sdk_TooManyRequests_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02313():
    # sdk_TooManyRequests_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02314():
    # sdk_TooManyRequests_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02315():
    # sdk_TooManyRequests_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02316():
    # sdk_TooManyRequests_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02317():
    # sdk_TooManyRequests_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02318():
    # sdk_TooManyRequests_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02319():
    # sdk_TooManyRequests_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02320():
    # sdk_TooManyRequests_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02321():
    # sdk_TooManyRequests_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02322():
    # sdk_TooManyRequests_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02323():
    # sdk_TooManyRequests_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02324():
    # sdk_TooManyRequests_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02325():
    # sdk_TooManyRequests_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02326():
    # sdk_TooManyRequests_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02327():
    # sdk_TooManyRequests_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02328():
    # sdk_TooManyRequests_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02329():
    # sdk_TooManyRequests_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02330():
    # sdk_TooManyRequests_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02331():
    # sdk_TooManyRequests_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02332():
    # sdk_TooManyRequests_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02333():
    # sdk_TooManyRequests_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02334():
    # sdk_TooManyRequests_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02335():
    # sdk_TooManyRequests_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02336():
    # sdk_TooManyRequests_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02337():
    # sdk_TooManyRequests_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02338():
    # sdk_TooManyRequests_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02339():
    # sdk_TooManyRequests_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02340():
    # sdk_TooManyRequests_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02341():
    # sdk_TooManyRequests_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02342():
    # sdk_TooManyRequests_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02343():
    # sdk_TooManyRequests_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02344():
    # sdk_TooManyRequests_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02345():
    # sdk_TooManyRequests_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02346():
    # sdk_TooManyRequests_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02347():
    # sdk_TooManyRequests_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02348():
    # sdk_TooManyRequests_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02349():
    # sdk_TooManyRequests_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02350():
    # sdk_TooManyRequests_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02351():
    # sdk_TooManyRequests_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02352():
    # sdk_TooManyRequests_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02353():
    # sdk_TooManyRequests_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02354():
    # sdk_TooManyRequests_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02355():
    # sdk_TooManyRequests_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02356():
    # sdk_TooManyRequests_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02357():
    # sdk_TooManyRequests_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02358():
    # sdk_TooManyRequests_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02359():
    # sdk_TooManyRequests_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02360():
    # sdk_TooManyRequests_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02361():
    # sdk_TooManyRequests_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02362():
    # sdk_TooManyRequests_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02363():
    # sdk_TooManyRequests_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02364():
    # sdk_TooManyRequests_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02365():
    # sdk_TooManyRequests_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02366():
    # sdk_TooManyRequests_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02367():
    # sdk_TooManyRequests_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02368():
    # sdk_TooManyRequests_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02369():
    # sdk_TooManyRequests_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02370():
    # sdk_TooManyRequests_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02371():
    # sdk_TooManyRequests_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02372():
    # sdk_TooManyRequests_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02373():
    # sdk_TooManyRequests_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02374():
    # sdk_TooManyRequests_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02375():
    # sdk_TooManyRequests_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02376():
    # sdk_TooManyRequests_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02377():
    # sdk_TooManyRequests_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02378():
    # sdk_TooManyRequests_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02379():
    # sdk_TooManyRequests_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_TooManyRequests_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02380():
    # sdk_Unauthenticated_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02381():
    # sdk_Unauthenticated_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02382():
    # sdk_Unauthenticated_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02383():
    # sdk_Unauthenticated_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02384():
    # sdk_Unauthenticated_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02385():
    # sdk_Unauthenticated_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02386():
    # sdk_Unauthenticated_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02387():
    # sdk_Unauthenticated_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02388():
    # sdk_Unauthenticated_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02389():
    # sdk_Unauthenticated_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02390():
    # sdk_Unauthenticated_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02391():
    # sdk_Unauthenticated_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02392():
    # sdk_Unauthenticated_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02393():
    # sdk_Unauthenticated_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02394():
    # sdk_Unauthenticated_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02395():
    # sdk_Unauthenticated_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02396():
    # sdk_Unauthenticated_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02397():
    # sdk_Unauthenticated_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02398():
    # sdk_Unauthenticated_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02399():
    # sdk_Unauthenticated_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02400():
    # sdk_Unauthenticated_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02401():
    # sdk_Unauthenticated_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02402():
    # sdk_Unauthenticated_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02403():
    # sdk_Unauthenticated_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02404():
    # sdk_Unauthenticated_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02405():
    # sdk_Unauthenticated_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02406():
    # sdk_Unauthenticated_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02407():
    # sdk_Unauthenticated_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02408():
    # sdk_Unauthenticated_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02409():
    # sdk_Unauthenticated_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02410():
    # sdk_Unauthenticated_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02411():
    # sdk_Unauthenticated_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02412():
    # sdk_Unauthenticated_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02413():
    # sdk_Unauthenticated_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02414():
    # sdk_Unauthenticated_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02415():
    # sdk_Unauthenticated_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02416():
    # sdk_Unauthenticated_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02417():
    # sdk_Unauthenticated_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02418():
    # sdk_Unauthenticated_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02419():
    # sdk_Unauthenticated_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02420():
    # sdk_Unauthenticated_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02421():
    # sdk_Unauthenticated_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02422():
    # sdk_Unauthenticated_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02423():
    # sdk_Unauthenticated_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02424():
    # sdk_Unauthenticated_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02425():
    # sdk_Unauthenticated_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02426():
    # sdk_Unauthenticated_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02427():
    # sdk_Unauthenticated_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02428():
    # sdk_Unauthenticated_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02429():
    # sdk_Unauthenticated_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02430():
    # sdk_Unauthenticated_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02431():
    # sdk_Unauthenticated_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02432():
    # sdk_Unauthenticated_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02433():
    # sdk_Unauthenticated_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02434():
    # sdk_Unauthenticated_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02435():
    # sdk_Unauthenticated_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02436():
    # sdk_Unauthenticated_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02437():
    # sdk_Unauthenticated_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02438():
    # sdk_Unauthenticated_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02439():
    # sdk_Unauthenticated_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02440():
    # sdk_Unauthenticated_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02441():
    # sdk_Unauthenticated_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02442():
    # sdk_Unauthenticated_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02443():
    # sdk_Unauthenticated_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02444():
    # sdk_Unauthenticated_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02445():
    # sdk_Unauthenticated_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02446():
    # sdk_Unauthenticated_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02447():
    # sdk_Unauthenticated_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02448():
    # sdk_Unauthenticated_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02449():
    # sdk_Unauthenticated_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unauthenticated_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02450():
    # sdk_Unauthorized_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unauthorized_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02451():
    # sdk_Unauthorized_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unauthorized_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02452():
    # sdk_Unauthorized_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unauthorized_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02453():
    # sdk_Unauthorized_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unauthorized_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02454():
    # sdk_Unauthorized_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unauthorized_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02455():
    # sdk_Unauthorized_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unauthorized_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02456():
    # sdk_Unauthorized_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unauthorized_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02457():
    # sdk_Unauthorized_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02458():
    # sdk_Unauthorized_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02459():
    # sdk_Unauthorized_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02460():
    # sdk_Unauthorized_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02461():
    # sdk_Unauthorized_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02462():
    # sdk_Unauthorized_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02463():
    # sdk_Unauthorized_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02464():
    # sdk_Unauthorized_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02465():
    # sdk_Unauthorized_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02466():
    # sdk_Unauthorized_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02467():
    # sdk_Unauthorized_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02468():
    # sdk_Unauthorized_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02469():
    # sdk_Unauthorized_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02470():
    # sdk_Unauthorized_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02471():
    # sdk_Unauthorized_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02472():
    # sdk_Unauthorized_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02473():
    # sdk_Unauthorized_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02474():
    # sdk_Unauthorized_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02475():
    # sdk_Unauthorized_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02476():
    # sdk_Unauthorized_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02477():
    # sdk_Unauthorized_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02478():
    # sdk_Unauthorized_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02479():
    # sdk_Unauthorized_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02480():
    # sdk_Unauthorized_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02481():
    # sdk_Unauthorized_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02482():
    # sdk_Unauthorized_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02483():
    # sdk_Unauthorized_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02484():
    # sdk_Unauthorized_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02485():
    # sdk_Unauthorized_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unauthorized_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02486():
    # sdk_Unauthorized_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unauthorized_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02487():
    # sdk_Unauthorized_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unauthorized_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02488():
    # sdk_Unauthorized_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unauthorized_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02489():
    # sdk_Unauthorized_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unauthorized_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02490():
    # sdk_Unauthorized_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unauthorized_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02491():
    # sdk_Unauthorized_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unauthorized_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02492():
    # sdk_Unauthorized_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02493():
    # sdk_Unauthorized_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02494():
    # sdk_Unauthorized_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02495():
    # sdk_Unauthorized_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02496():
    # sdk_Unauthorized_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02497():
    # sdk_Unauthorized_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02498():
    # sdk_Unauthorized_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02499():
    # sdk_Unauthorized_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02500():
    # sdk_Unauthorized_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02501():
    # sdk_Unauthorized_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02502():
    # sdk_Unauthorized_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02503():
    # sdk_Unauthorized_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02504():
    # sdk_Unauthorized_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02505():
    # sdk_Unauthorized_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02506():
    # sdk_Unauthorized_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02507():
    # sdk_Unauthorized_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02508():
    # sdk_Unauthorized_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02509():
    # sdk_Unauthorized_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02510():
    # sdk_Unauthorized_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02511():
    # sdk_Unauthorized_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02512():
    # sdk_Unauthorized_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02513():
    # sdk_Unauthorized_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02514():
    # sdk_Unauthorized_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02515():
    # sdk_Unauthorized_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02516():
    # sdk_Unauthorized_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02517():
    # sdk_Unauthorized_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02518():
    # sdk_Unauthorized_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02519():
    # sdk_Unauthorized_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unauthorized_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02520():
    # sdk_Unknown_bare_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unknown_bare_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02521():
    # sdk_Unknown_bare_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unknown_bare_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02522():
    # sdk_Unknown_bare_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unknown_bare_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02523():
    # sdk_Unknown_bare_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unknown_bare_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02524():
    # sdk_Unknown_bare_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unknown_bare_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02525():
    # sdk_Unknown_bare_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unknown_bare_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02526():
    # sdk_Unknown_bare_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unknown_bare_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02527():
    # sdk_Unknown_cause_aborted_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02528():
    # sdk_Unknown_cause_aborted_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02529():
    # sdk_Unknown_cause_aborted_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02530():
    # sdk_Unknown_cause_aborted_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02531():
    # sdk_Unknown_cause_aborted_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02532():
    # sdk_Unknown_cause_aborted_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02533():
    # sdk_Unknown_cause_aborted_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_aborted_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02534():
    # sdk_Unknown_cause_expired_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02535():
    # sdk_Unknown_cause_expired_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02536():
    # sdk_Unknown_cause_expired_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02537():
    # sdk_Unknown_cause_expired_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02538():
    # sdk_Unknown_cause_expired_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02539():
    # sdk_Unknown_cause_expired_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02540():
    # sdk_Unknown_cause_expired_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_expired_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02541():
    # sdk_Unknown_cause_timeout_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02542():
    # sdk_Unknown_cause_timeout_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02543():
    # sdk_Unknown_cause_timeout_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02544():
    # sdk_Unknown_cause_timeout_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02545():
    # sdk_Unknown_cause_timeout_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02546():
    # sdk_Unknown_cause_timeout_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02547():
    # sdk_Unknown_cause_timeout_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_timeout_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02548():
    # sdk_Unknown_cause_value_1 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02549():
    # sdk_Unknown_cause_value_1 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02550():
    # sdk_Unknown_cause_value_1 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02551():
    # sdk_Unknown_cause_value_1 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02552():
    # sdk_Unknown_cause_value_1 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02553():
    # sdk_Unknown_cause_value_1 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02554():
    # sdk_Unknown_cause_value_1 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_value_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02555():
    # sdk_Unknown_bare_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unknown_bare_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02556():
    # sdk_Unknown_bare_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unknown_bare_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02557():
    # sdk_Unknown_bare_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unknown_bare_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02558():
    # sdk_Unknown_bare_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unknown_bare_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02559():
    # sdk_Unknown_bare_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unknown_bare_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02560():
    # sdk_Unknown_bare_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unknown_bare_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02561():
    # sdk_Unknown_bare_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unknown_bare_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02562():
    # sdk_Unknown_cause_aborted_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02563():
    # sdk_Unknown_cause_aborted_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02564():
    # sdk_Unknown_cause_aborted_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02565():
    # sdk_Unknown_cause_aborted_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02566():
    # sdk_Unknown_cause_aborted_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02567():
    # sdk_Unknown_cause_aborted_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02568():
    # sdk_Unknown_cause_aborted_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_aborted_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02569():
    # sdk_Unknown_cause_expired_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02570():
    # sdk_Unknown_cause_expired_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02571():
    # sdk_Unknown_cause_expired_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02572():
    # sdk_Unknown_cause_expired_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02573():
    # sdk_Unknown_cause_expired_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02574():
    # sdk_Unknown_cause_expired_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02575():
    # sdk_Unknown_cause_expired_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_expired_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02576():
    # sdk_Unknown_cause_timeout_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02577():
    # sdk_Unknown_cause_timeout_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02578():
    # sdk_Unknown_cause_timeout_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02579():
    # sdk_Unknown_cause_timeout_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02580():
    # sdk_Unknown_cause_timeout_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02581():
    # sdk_Unknown_cause_timeout_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02582():
    # sdk_Unknown_cause_timeout_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_timeout_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02583():
    # sdk_Unknown_cause_value_0 attempt=1
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02584():
    # sdk_Unknown_cause_value_0 attempt=2
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02585():
    # sdk_Unknown_cause_value_0 attempt=3
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02586():
    # sdk_Unknown_cause_value_0 attempt=4
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02587():
    # sdk_Unknown_cause_value_0 attempt=5
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02588():
    # sdk_Unknown_cause_value_0 attempt=6
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02589():
    # sdk_Unknown_cause_value_0 attempt=7
    error = _SHAPE_BUILDERS['sdk_Unknown_cause_value_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02590():
    # custody_staged_audio attempt=1
    error = _SHAPE_BUILDERS['custody_staged_audio']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02591():
    # custody_staged_audio attempt=2
    error = _SHAPE_BUILDERS['custody_staged_audio']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02592():
    # custody_staged_audio attempt=3
    error = _SHAPE_BUILDERS['custody_staged_audio']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02593():
    # custody_staged_audio attempt=4
    error = _SHAPE_BUILDERS['custody_staged_audio']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02594():
    # custody_staged_audio attempt=5
    error = _SHAPE_BUILDERS['custody_staged_audio']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02595():
    # custody_staged_audio attempt=6
    error = _SHAPE_BUILDERS['custody_staged_audio']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02596():
    # custody_staged_audio attempt=7
    error = _SHAPE_BUILDERS['custody_staged_audio']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02597():
    # custody_staged_audio_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_staged_audio_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02598():
    # custody_staged_audio_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_staged_audio_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02599():
    # custody_staged_audio_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_staged_audio_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02600():
    # custody_staged_audio_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_staged_audio_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02601():
    # custody_staged_audio_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_staged_audio_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02602():
    # custody_staged_audio_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_staged_audio_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02603():
    # custody_staged_audio_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_staged_audio_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02604():
    # custody_staged_artifact attempt=1
    error = _SHAPE_BUILDERS['custody_staged_artifact']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02605():
    # custody_staged_artifact attempt=2
    error = _SHAPE_BUILDERS['custody_staged_artifact']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02606():
    # custody_staged_artifact attempt=3
    error = _SHAPE_BUILDERS['custody_staged_artifact']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02607():
    # custody_staged_artifact attempt=4
    error = _SHAPE_BUILDERS['custody_staged_artifact']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02608():
    # custody_staged_artifact attempt=5
    error = _SHAPE_BUILDERS['custody_staged_artifact']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02609():
    # custody_staged_artifact attempt=6
    error = _SHAPE_BUILDERS['custody_staged_artifact']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02610():
    # custody_staged_artifact attempt=7
    error = _SHAPE_BUILDERS['custody_staged_artifact']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02611():
    # custody_staged_artifact_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_staged_artifact_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02612():
    # custody_staged_artifact_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_staged_artifact_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02613():
    # custody_staged_artifact_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_staged_artifact_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02614():
    # custody_staged_artifact_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_staged_artifact_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02615():
    # custody_staged_artifact_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_staged_artifact_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02616():
    # custody_staged_artifact_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_staged_artifact_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02617():
    # custody_staged_artifact_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_staged_artifact_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02618():
    # custody_retained_audio attempt=1
    error = _SHAPE_BUILDERS['custody_retained_audio']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02619():
    # custody_retained_audio attempt=2
    error = _SHAPE_BUILDERS['custody_retained_audio']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02620():
    # custody_retained_audio attempt=3
    error = _SHAPE_BUILDERS['custody_retained_audio']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02621():
    # custody_retained_audio attempt=4
    error = _SHAPE_BUILDERS['custody_retained_audio']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02622():
    # custody_retained_audio attempt=5
    error = _SHAPE_BUILDERS['custody_retained_audio']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02623():
    # custody_retained_audio attempt=6
    error = _SHAPE_BUILDERS['custody_retained_audio']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02624():
    # custody_retained_audio attempt=7
    error = _SHAPE_BUILDERS['custody_retained_audio']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02625():
    # custody_retained_audio_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_retained_audio_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02626():
    # custody_retained_audio_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_retained_audio_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02627():
    # custody_retained_audio_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_retained_audio_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02628():
    # custody_retained_audio_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_retained_audio_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02629():
    # custody_retained_audio_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_retained_audio_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02630():
    # custody_retained_audio_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_retained_audio_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02631():
    # custody_retained_audio_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_retained_audio_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02632():
    # custody_retained_manifest attempt=1
    error = _SHAPE_BUILDERS['custody_retained_manifest']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02633():
    # custody_retained_manifest attempt=2
    error = _SHAPE_BUILDERS['custody_retained_manifest']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02634():
    # custody_retained_manifest attempt=3
    error = _SHAPE_BUILDERS['custody_retained_manifest']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02635():
    # custody_retained_manifest attempt=4
    error = _SHAPE_BUILDERS['custody_retained_manifest']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02636():
    # custody_retained_manifest attempt=5
    error = _SHAPE_BUILDERS['custody_retained_manifest']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02637():
    # custody_retained_manifest attempt=6
    error = _SHAPE_BUILDERS['custody_retained_manifest']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02638():
    # custody_retained_manifest attempt=7
    error = _SHAPE_BUILDERS['custody_retained_manifest']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02639():
    # custody_retained_manifest_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_retained_manifest_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02640():
    # custody_retained_manifest_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_retained_manifest_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02641():
    # custody_retained_manifest_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_retained_manifest_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02642():
    # custody_retained_manifest_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_retained_manifest_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02643():
    # custody_retained_manifest_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_retained_manifest_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02644():
    # custody_retained_manifest_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_retained_manifest_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02645():
    # custody_retained_manifest_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_retained_manifest_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02646():
    # custody_decoded_mismatch attempt=1
    error = _SHAPE_BUILDERS['custody_decoded_mismatch']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02647():
    # custody_decoded_mismatch attempt=2
    error = _SHAPE_BUILDERS['custody_decoded_mismatch']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02648():
    # custody_decoded_mismatch attempt=3
    error = _SHAPE_BUILDERS['custody_decoded_mismatch']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02649():
    # custody_decoded_mismatch attempt=4
    error = _SHAPE_BUILDERS['custody_decoded_mismatch']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02650():
    # custody_decoded_mismatch attempt=5
    error = _SHAPE_BUILDERS['custody_decoded_mismatch']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02651():
    # custody_decoded_mismatch attempt=6
    error = _SHAPE_BUILDERS['custody_decoded_mismatch']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02652():
    # custody_decoded_mismatch attempt=7
    error = _SHAPE_BUILDERS['custody_decoded_mismatch']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02653():
    # custody_decoded_mismatch_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_decoded_mismatch_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02654():
    # custody_decoded_mismatch_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_decoded_mismatch_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02655():
    # custody_decoded_mismatch_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_decoded_mismatch_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02656():
    # custody_decoded_mismatch_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_decoded_mismatch_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02657():
    # custody_decoded_mismatch_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_decoded_mismatch_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02658():
    # custody_decoded_mismatch_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_decoded_mismatch_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02659():
    # custody_decoded_mismatch_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_decoded_mismatch_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02660():
    # custody_permission attempt=1
    error = _SHAPE_BUILDERS['custody_permission']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02661():
    # custody_permission attempt=2
    error = _SHAPE_BUILDERS['custody_permission']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02662():
    # custody_permission attempt=3
    error = _SHAPE_BUILDERS['custody_permission']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02663():
    # custody_permission attempt=4
    error = _SHAPE_BUILDERS['custody_permission']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02664():
    # custody_permission attempt=5
    error = _SHAPE_BUILDERS['custody_permission']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02665():
    # custody_permission attempt=6
    error = _SHAPE_BUILDERS['custody_permission']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02666():
    # custody_permission attempt=7
    error = _SHAPE_BUILDERS['custody_permission']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02667():
    # custody_permission_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_permission_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02668():
    # custody_permission_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_permission_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02669():
    # custody_permission_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_permission_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02670():
    # custody_permission_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_permission_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02671():
    # custody_permission_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_permission_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02672():
    # custody_permission_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_permission_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02673():
    # custody_permission_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_permission_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02674():
    # custody_os_error attempt=1
    error = _SHAPE_BUILDERS['custody_os_error']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02675():
    # custody_os_error attempt=2
    error = _SHAPE_BUILDERS['custody_os_error']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02676():
    # custody_os_error attempt=3
    error = _SHAPE_BUILDERS['custody_os_error']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02677():
    # custody_os_error attempt=4
    error = _SHAPE_BUILDERS['custody_os_error']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02678():
    # custody_os_error attempt=5
    error = _SHAPE_BUILDERS['custody_os_error']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02679():
    # custody_os_error attempt=6
    error = _SHAPE_BUILDERS['custody_os_error']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02680():
    # custody_os_error attempt=7
    error = _SHAPE_BUILDERS['custody_os_error']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02681():
    # custody_os_error_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_os_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02682():
    # custody_os_error_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_os_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02683():
    # custody_os_error_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_os_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02684():
    # custody_os_error_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_os_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02685():
    # custody_os_error_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_os_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02686():
    # custody_os_error_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_os_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02687():
    # custody_os_error_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_os_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02688():
    # custody_runtime attempt=1
    error = _SHAPE_BUILDERS['custody_runtime']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02689():
    # custody_runtime attempt=2
    error = _SHAPE_BUILDERS['custody_runtime']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02690():
    # custody_runtime attempt=3
    error = _SHAPE_BUILDERS['custody_runtime']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02691():
    # custody_runtime attempt=4
    error = _SHAPE_BUILDERS['custody_runtime']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02692():
    # custody_runtime attempt=5
    error = _SHAPE_BUILDERS['custody_runtime']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02693():
    # custody_runtime attempt=6
    error = _SHAPE_BUILDERS['custody_runtime']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02694():
    # custody_runtime attempt=7
    error = _SHAPE_BUILDERS['custody_runtime']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02695():
    # custody_runtime_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_runtime_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02696():
    # custody_runtime_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_runtime_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02697():
    # custody_runtime_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_runtime_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02698():
    # custody_runtime_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_runtime_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02699():
    # custody_runtime_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_runtime_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02700():
    # custody_runtime_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_runtime_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02701():
    # custody_runtime_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_runtime_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02702():
    # custody_value_error attempt=1
    error = _SHAPE_BUILDERS['custody_value_error']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02703():
    # custody_value_error attempt=2
    error = _SHAPE_BUILDERS['custody_value_error']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02704():
    # custody_value_error attempt=3
    error = _SHAPE_BUILDERS['custody_value_error']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02705():
    # custody_value_error attempt=4
    error = _SHAPE_BUILDERS['custody_value_error']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02706():
    # custody_value_error attempt=5
    error = _SHAPE_BUILDERS['custody_value_error']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02707():
    # custody_value_error attempt=6
    error = _SHAPE_BUILDERS['custody_value_error']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02708():
    # custody_value_error attempt=7
    error = _SHAPE_BUILDERS['custody_value_error']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02709():
    # custody_value_error_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_value_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02710():
    # custody_value_error_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_value_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02711():
    # custody_value_error_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_value_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02712():
    # custody_value_error_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_value_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02713():
    # custody_value_error_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_value_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02714():
    # custody_value_error_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_value_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02715():
    # custody_value_error_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_value_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02716():
    # custody_key_error attempt=1
    error = _SHAPE_BUILDERS['custody_key_error']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02717():
    # custody_key_error attempt=2
    error = _SHAPE_BUILDERS['custody_key_error']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02718():
    # custody_key_error attempt=3
    error = _SHAPE_BUILDERS['custody_key_error']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02719():
    # custody_key_error attempt=4
    error = _SHAPE_BUILDERS['custody_key_error']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02720():
    # custody_key_error attempt=5
    error = _SHAPE_BUILDERS['custody_key_error']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02721():
    # custody_key_error attempt=6
    error = _SHAPE_BUILDERS['custody_key_error']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02722():
    # custody_key_error attempt=7
    error = _SHAPE_BUILDERS['custody_key_error']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02723():
    # custody_key_error_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_key_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02724():
    # custody_key_error_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_key_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02725():
    # custody_key_error_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_key_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02726():
    # custody_key_error_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_key_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02727():
    # custody_key_error_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_key_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02728():
    # custody_key_error_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_key_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02729():
    # custody_key_error_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_key_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02730():
    # custody_type_error attempt=1
    error = _SHAPE_BUILDERS['custody_type_error']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02731():
    # custody_type_error attempt=2
    error = _SHAPE_BUILDERS['custody_type_error']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02732():
    # custody_type_error attempt=3
    error = _SHAPE_BUILDERS['custody_type_error']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02733():
    # custody_type_error attempt=4
    error = _SHAPE_BUILDERS['custody_type_error']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02734():
    # custody_type_error attempt=5
    error = _SHAPE_BUILDERS['custody_type_error']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02735():
    # custody_type_error attempt=6
    error = _SHAPE_BUILDERS['custody_type_error']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02736():
    # custody_type_error attempt=7
    error = _SHAPE_BUILDERS['custody_type_error']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02737():
    # custody_type_error_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_type_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02738():
    # custody_type_error_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_type_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02739():
    # custody_type_error_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_type_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02740():
    # custody_type_error_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_type_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02741():
    # custody_type_error_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_type_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02742():
    # custody_type_error_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_type_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02743():
    # custody_type_error_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_type_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02744():
    # custody_index_error attempt=1
    error = _SHAPE_BUILDERS['custody_index_error']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02745():
    # custody_index_error attempt=2
    error = _SHAPE_BUILDERS['custody_index_error']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02746():
    # custody_index_error attempt=3
    error = _SHAPE_BUILDERS['custody_index_error']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02747():
    # custody_index_error attempt=4
    error = _SHAPE_BUILDERS['custody_index_error']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02748():
    # custody_index_error attempt=5
    error = _SHAPE_BUILDERS['custody_index_error']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02749():
    # custody_index_error attempt=6
    error = _SHAPE_BUILDERS['custody_index_error']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02750():
    # custody_index_error attempt=7
    error = _SHAPE_BUILDERS['custody_index_error']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02751():
    # custody_index_error_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_index_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02752():
    # custody_index_error_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_index_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02753():
    # custody_index_error_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_index_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02754():
    # custody_index_error_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_index_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02755():
    # custody_index_error_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_index_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02756():
    # custody_index_error_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_index_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02757():
    # custody_index_error_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_index_error_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02758():
    # custody_zero_div attempt=1
    error = _SHAPE_BUILDERS['custody_zero_div']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02759():
    # custody_zero_div attempt=2
    error = _SHAPE_BUILDERS['custody_zero_div']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02760():
    # custody_zero_div attempt=3
    error = _SHAPE_BUILDERS['custody_zero_div']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02761():
    # custody_zero_div attempt=4
    error = _SHAPE_BUILDERS['custody_zero_div']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02762():
    # custody_zero_div attempt=5
    error = _SHAPE_BUILDERS['custody_zero_div']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02763():
    # custody_zero_div attempt=6
    error = _SHAPE_BUILDERS['custody_zero_div']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02764():
    # custody_zero_div attempt=7
    error = _SHAPE_BUILDERS['custody_zero_div']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02765():
    # custody_zero_div_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_zero_div_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02766():
    # custody_zero_div_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_zero_div_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02767():
    # custody_zero_div_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_zero_div_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02768():
    # custody_zero_div_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_zero_div_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02769():
    # custody_zero_div_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_zero_div_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02770():
    # custody_zero_div_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_zero_div_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02771():
    # custody_zero_div_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_zero_div_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02772():
    # custody_arith attempt=1
    error = _SHAPE_BUILDERS['custody_arith']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02773():
    # custody_arith attempt=2
    error = _SHAPE_BUILDERS['custody_arith']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02774():
    # custody_arith attempt=3
    error = _SHAPE_BUILDERS['custody_arith']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02775():
    # custody_arith attempt=4
    error = _SHAPE_BUILDERS['custody_arith']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02776():
    # custody_arith attempt=5
    error = _SHAPE_BUILDERS['custody_arith']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02777():
    # custody_arith attempt=6
    error = _SHAPE_BUILDERS['custody_arith']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02778():
    # custody_arith attempt=7
    error = _SHAPE_BUILDERS['custody_arith']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02779():
    # custody_arith_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_arith_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02780():
    # custody_arith_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_arith_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02781():
    # custody_arith_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_arith_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02782():
    # custody_arith_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_arith_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02783():
    # custody_arith_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_arith_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02784():
    # custody_arith_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_arith_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02785():
    # custody_arith_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_arith_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02786():
    # custody_lookup attempt=1
    error = _SHAPE_BUILDERS['custody_lookup']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02787():
    # custody_lookup attempt=2
    error = _SHAPE_BUILDERS['custody_lookup']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02788():
    # custody_lookup attempt=3
    error = _SHAPE_BUILDERS['custody_lookup']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02789():
    # custody_lookup attempt=4
    error = _SHAPE_BUILDERS['custody_lookup']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02790():
    # custody_lookup attempt=5
    error = _SHAPE_BUILDERS['custody_lookup']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02791():
    # custody_lookup attempt=6
    error = _SHAPE_BUILDERS['custody_lookup']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02792():
    # custody_lookup attempt=7
    error = _SHAPE_BUILDERS['custody_lookup']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02793():
    # custody_lookup_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_lookup_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02794():
    # custody_lookup_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_lookup_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02795():
    # custody_lookup_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_lookup_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02796():
    # custody_lookup_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_lookup_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02797():
    # custody_lookup_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_lookup_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02798():
    # custody_lookup_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_lookup_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02799():
    # custody_lookup_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_lookup_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02800():
    # custody_notimpl attempt=1
    error = _SHAPE_BUILDERS['custody_notimpl']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02801():
    # custody_notimpl attempt=2
    error = _SHAPE_BUILDERS['custody_notimpl']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02802():
    # custody_notimpl attempt=3
    error = _SHAPE_BUILDERS['custody_notimpl']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02803():
    # custody_notimpl attempt=4
    error = _SHAPE_BUILDERS['custody_notimpl']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02804():
    # custody_notimpl attempt=5
    error = _SHAPE_BUILDERS['custody_notimpl']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02805():
    # custody_notimpl attempt=6
    error = _SHAPE_BUILDERS['custody_notimpl']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02806():
    # custody_notimpl attempt=7
    error = _SHAPE_BUILDERS['custody_notimpl']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02807():
    # custody_notimpl_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_notimpl_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02808():
    # custody_notimpl_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_notimpl_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02809():
    # custody_notimpl_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_notimpl_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02810():
    # custody_notimpl_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_notimpl_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02811():
    # custody_notimpl_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_notimpl_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02812():
    # custody_notimpl_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_notimpl_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02813():
    # custody_notimpl_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_notimpl_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02814():
    # custody_recursion attempt=1
    error = _SHAPE_BUILDERS['custody_recursion']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02815():
    # custody_recursion attempt=2
    error = _SHAPE_BUILDERS['custody_recursion']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02816():
    # custody_recursion attempt=3
    error = _SHAPE_BUILDERS['custody_recursion']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02817():
    # custody_recursion attempt=4
    error = _SHAPE_BUILDERS['custody_recursion']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02818():
    # custody_recursion attempt=5
    error = _SHAPE_BUILDERS['custody_recursion']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02819():
    # custody_recursion attempt=6
    error = _SHAPE_BUILDERS['custody_recursion']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02820():
    # custody_recursion attempt=7
    error = _SHAPE_BUILDERS['custody_recursion']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02821():
    # custody_recursion_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_recursion_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02822():
    # custody_recursion_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_recursion_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02823():
    # custody_recursion_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_recursion_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02824():
    # custody_recursion_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_recursion_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02825():
    # custody_recursion_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_recursion_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02826():
    # custody_recursion_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_recursion_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02827():
    # custody_recursion_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_recursion_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02828():
    # custody_eof attempt=1
    error = _SHAPE_BUILDERS['custody_eof']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02829():
    # custody_eof attempt=2
    error = _SHAPE_BUILDERS['custody_eof']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02830():
    # custody_eof attempt=3
    error = _SHAPE_BUILDERS['custody_eof']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02831():
    # custody_eof attempt=4
    error = _SHAPE_BUILDERS['custody_eof']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02832():
    # custody_eof attempt=5
    error = _SHAPE_BUILDERS['custody_eof']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02833():
    # custody_eof attempt=6
    error = _SHAPE_BUILDERS['custody_eof']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02834():
    # custody_eof attempt=7
    error = _SHAPE_BUILDERS['custody_eof']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02835():
    # custody_eof_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_eof_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02836():
    # custody_eof_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_eof_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02837():
    # custody_eof_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_eof_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02838():
    # custody_eof_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_eof_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02839():
    # custody_eof_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_eof_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02840():
    # custody_eof_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_eof_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02841():
    # custody_eof_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_eof_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02842():
    # custody_batch_validation_unsupported_language attempt=1
    error = _SHAPE_BUILDERS['custody_batch_validation_unsupported_language']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02843():
    # custody_batch_validation_unsupported_language attempt=2
    error = _SHAPE_BUILDERS['custody_batch_validation_unsupported_language']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02844():
    # custody_batch_validation_unsupported_language attempt=3
    error = _SHAPE_BUILDERS['custody_batch_validation_unsupported_language']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02845():
    # custody_batch_validation_unsupported_language attempt=4
    error = _SHAPE_BUILDERS['custody_batch_validation_unsupported_language']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02846():
    # custody_batch_validation_unsupported_language attempt=5
    error = _SHAPE_BUILDERS['custody_batch_validation_unsupported_language']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02847():
    # custody_batch_validation_unsupported_language attempt=6
    error = _SHAPE_BUILDERS['custody_batch_validation_unsupported_language']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02848():
    # custody_batch_validation_unsupported_language attempt=7
    error = _SHAPE_BUILDERS['custody_batch_validation_unsupported_language']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02849():
    # custody_batch_validation_unsupported_language_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_batch_validation_unsupported_language_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02850():
    # custody_batch_validation_unsupported_language_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_batch_validation_unsupported_language_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02851():
    # custody_batch_validation_unsupported_language_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_batch_validation_unsupported_language_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02852():
    # custody_batch_validation_unsupported_language_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_batch_validation_unsupported_language_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02853():
    # custody_batch_validation_unsupported_language_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_batch_validation_unsupported_language_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02854():
    # custody_batch_validation_unsupported_language_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_batch_validation_unsupported_language_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02855():
    # custody_batch_validation_unsupported_language_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_batch_validation_unsupported_language_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02856():
    # custody_batch_validation_word_shape attempt=1
    error = _SHAPE_BUILDERS['custody_batch_validation_word_shape']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02857():
    # custody_batch_validation_word_shape attempt=2
    error = _SHAPE_BUILDERS['custody_batch_validation_word_shape']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02858():
    # custody_batch_validation_word_shape attempt=3
    error = _SHAPE_BUILDERS['custody_batch_validation_word_shape']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02859():
    # custody_batch_validation_word_shape attempt=4
    error = _SHAPE_BUILDERS['custody_batch_validation_word_shape']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02860():
    # custody_batch_validation_word_shape attempt=5
    error = _SHAPE_BUILDERS['custody_batch_validation_word_shape']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02861():
    # custody_batch_validation_word_shape attempt=6
    error = _SHAPE_BUILDERS['custody_batch_validation_word_shape']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02862():
    # custody_batch_validation_word_shape attempt=7
    error = _SHAPE_BUILDERS['custody_batch_validation_word_shape']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02863():
    # custody_batch_validation_word_shape_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_batch_validation_word_shape_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02864():
    # custody_batch_validation_word_shape_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_batch_validation_word_shape_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02865():
    # custody_batch_validation_word_shape_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_batch_validation_word_shape_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02866():
    # custody_batch_validation_word_shape_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_batch_validation_word_shape_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02867():
    # custody_batch_validation_word_shape_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_batch_validation_word_shape_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02868():
    # custody_batch_validation_word_shape_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_batch_validation_word_shape_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02869():
    # custody_batch_validation_word_shape_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_batch_validation_word_shape_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02870():
    # custody_batch_validation_word_clock attempt=1
    error = _SHAPE_BUILDERS['custody_batch_validation_word_clock']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02871():
    # custody_batch_validation_word_clock attempt=2
    error = _SHAPE_BUILDERS['custody_batch_validation_word_clock']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02872():
    # custody_batch_validation_word_clock attempt=3
    error = _SHAPE_BUILDERS['custody_batch_validation_word_clock']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02873():
    # custody_batch_validation_word_clock attempt=4
    error = _SHAPE_BUILDERS['custody_batch_validation_word_clock']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02874():
    # custody_batch_validation_word_clock attempt=5
    error = _SHAPE_BUILDERS['custody_batch_validation_word_clock']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02875():
    # custody_batch_validation_word_clock attempt=6
    error = _SHAPE_BUILDERS['custody_batch_validation_word_clock']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02876():
    # custody_batch_validation_word_clock attempt=7
    error = _SHAPE_BUILDERS['custody_batch_validation_word_clock']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02877():
    # custody_batch_validation_word_clock_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_batch_validation_word_clock_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02878():
    # custody_batch_validation_word_clock_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_batch_validation_word_clock_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02879():
    # custody_batch_validation_word_clock_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_batch_validation_word_clock_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02880():
    # custody_batch_validation_word_clock_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_batch_validation_word_clock_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02881():
    # custody_batch_validation_word_clock_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_batch_validation_word_clock_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02882():
    # custody_batch_validation_word_clock_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_batch_validation_word_clock_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02883():
    # custody_batch_validation_word_clock_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_batch_validation_word_clock_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02884():
    # custody_batch_validation_word_sequence attempt=1
    error = _SHAPE_BUILDERS['custody_batch_validation_word_sequence']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02885():
    # custody_batch_validation_word_sequence attempt=2
    error = _SHAPE_BUILDERS['custody_batch_validation_word_sequence']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02886():
    # custody_batch_validation_word_sequence attempt=3
    error = _SHAPE_BUILDERS['custody_batch_validation_word_sequence']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02887():
    # custody_batch_validation_word_sequence attempt=4
    error = _SHAPE_BUILDERS['custody_batch_validation_word_sequence']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02888():
    # custody_batch_validation_word_sequence attempt=5
    error = _SHAPE_BUILDERS['custody_batch_validation_word_sequence']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02889():
    # custody_batch_validation_word_sequence attempt=6
    error = _SHAPE_BUILDERS['custody_batch_validation_word_sequence']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02890():
    # custody_batch_validation_word_sequence attempt=7
    error = _SHAPE_BUILDERS['custody_batch_validation_word_sequence']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02891():
    # custody_batch_validation_word_sequence_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_batch_validation_word_sequence_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02892():
    # custody_batch_validation_word_sequence_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_batch_validation_word_sequence_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02893():
    # custody_batch_validation_word_sequence_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_batch_validation_word_sequence_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02894():
    # custody_batch_validation_word_sequence_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_batch_validation_word_sequence_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02895():
    # custody_batch_validation_word_sequence_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_batch_validation_word_sequence_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02896():
    # custody_batch_validation_word_sequence_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_batch_validation_word_sequence_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02897():
    # custody_batch_validation_word_sequence_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_batch_validation_word_sequence_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02898():
    # custody_batch_validation_vad_nonfinite attempt=1
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02899():
    # custody_batch_validation_vad_nonfinite attempt=2
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02900():
    # custody_batch_validation_vad_nonfinite attempt=3
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02901():
    # custody_batch_validation_vad_nonfinite attempt=4
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02902():
    # custody_batch_validation_vad_nonfinite attempt=5
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02903():
    # custody_batch_validation_vad_nonfinite attempt=6
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02904():
    # custody_batch_validation_vad_nonfinite attempt=7
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02905():
    # custody_batch_validation_vad_nonfinite_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02906():
    # custody_batch_validation_vad_nonfinite_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02907():
    # custody_batch_validation_vad_nonfinite_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02908():
    # custody_batch_validation_vad_nonfinite_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02909():
    # custody_batch_validation_vad_nonfinite_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02910():
    # custody_batch_validation_vad_nonfinite_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02911():
    # custody_batch_validation_vad_nonfinite_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_nonfinite_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02912():
    # custody_batch_validation_vad_order attempt=1
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_order']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02913():
    # custody_batch_validation_vad_order attempt=2
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_order']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02914():
    # custody_batch_validation_vad_order attempt=3
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_order']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02915():
    # custody_batch_validation_vad_order attempt=4
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_order']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02916():
    # custody_batch_validation_vad_order attempt=5
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_order']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02917():
    # custody_batch_validation_vad_order attempt=6
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_order']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02918():
    # custody_batch_validation_vad_order attempt=7
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_order']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02919():
    # custody_batch_validation_vad_order_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_order_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02920():
    # custody_batch_validation_vad_order_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_order_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02921():
    # custody_batch_validation_vad_order_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_order_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02922():
    # custody_batch_validation_vad_order_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_order_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02923():
    # custody_batch_validation_vad_order_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_order_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02924():
    # custody_batch_validation_vad_order_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_order_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02925():
    # custody_batch_validation_vad_order_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_order_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02926():
    # custody_batch_validation_vad_bounds attempt=1
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_bounds']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02927():
    # custody_batch_validation_vad_bounds attempt=2
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_bounds']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02928():
    # custody_batch_validation_vad_bounds attempt=3
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_bounds']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02929():
    # custody_batch_validation_vad_bounds attempt=4
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_bounds']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02930():
    # custody_batch_validation_vad_bounds attempt=5
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_bounds']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02931():
    # custody_batch_validation_vad_bounds attempt=6
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_bounds']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02932():
    # custody_batch_validation_vad_bounds attempt=7
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_bounds']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02933():
    # custody_batch_validation_vad_bounds_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_bounds_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02934():
    # custody_batch_validation_vad_bounds_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_bounds_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02935():
    # custody_batch_validation_vad_bounds_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_bounds_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02936():
    # custody_batch_validation_vad_bounds_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_bounds_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02937():
    # custody_batch_validation_vad_bounds_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_bounds_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02938():
    # custody_batch_validation_vad_bounds_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_bounds_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02939():
    # custody_batch_validation_vad_bounds_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_batch_validation_vad_bounds_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02940():
    # custody_batch_validation_empty_asr attempt=1
    error = _SHAPE_BUILDERS['custody_batch_validation_empty_asr']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02941():
    # custody_batch_validation_empty_asr attempt=2
    error = _SHAPE_BUILDERS['custody_batch_validation_empty_asr']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02942():
    # custody_batch_validation_empty_asr attempt=3
    error = _SHAPE_BUILDERS['custody_batch_validation_empty_asr']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02943():
    # custody_batch_validation_empty_asr attempt=4
    error = _SHAPE_BUILDERS['custody_batch_validation_empty_asr']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02944():
    # custody_batch_validation_empty_asr attempt=5
    error = _SHAPE_BUILDERS['custody_batch_validation_empty_asr']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02945():
    # custody_batch_validation_empty_asr attempt=6
    error = _SHAPE_BUILDERS['custody_batch_validation_empty_asr']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02946():
    # custody_batch_validation_empty_asr attempt=7
    error = _SHAPE_BUILDERS['custody_batch_validation_empty_asr']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02947():
    # custody_batch_validation_empty_asr_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_batch_validation_empty_asr_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02948():
    # custody_batch_validation_empty_asr_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_batch_validation_empty_asr_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02949():
    # custody_batch_validation_empty_asr_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_batch_validation_empty_asr_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02950():
    # custody_batch_validation_empty_asr_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_batch_validation_empty_asr_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02951():
    # custody_batch_validation_empty_asr_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_batch_validation_empty_asr_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02952():
    # custody_batch_validation_empty_asr_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_batch_validation_empty_asr_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02953():
    # custody_batch_validation_empty_asr_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_batch_validation_empty_asr_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02954():
    # custody_batch_validation_no_owned_words attempt=1
    error = _SHAPE_BUILDERS['custody_batch_validation_no_owned_words']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02955():
    # custody_batch_validation_no_owned_words attempt=2
    error = _SHAPE_BUILDERS['custody_batch_validation_no_owned_words']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02956():
    # custody_batch_validation_no_owned_words attempt=3
    error = _SHAPE_BUILDERS['custody_batch_validation_no_owned_words']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02957():
    # custody_batch_validation_no_owned_words attempt=4
    error = _SHAPE_BUILDERS['custody_batch_validation_no_owned_words']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02958():
    # custody_batch_validation_no_owned_words attempt=5
    error = _SHAPE_BUILDERS['custody_batch_validation_no_owned_words']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02959():
    # custody_batch_validation_no_owned_words attempt=6
    error = _SHAPE_BUILDERS['custody_batch_validation_no_owned_words']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02960():
    # custody_batch_validation_no_owned_words attempt=7
    error = _SHAPE_BUILDERS['custody_batch_validation_no_owned_words']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02961():
    # custody_batch_validation_no_owned_words_cause_aborted attempt=1
    error = _SHAPE_BUILDERS['custody_batch_validation_no_owned_words_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02962():
    # custody_batch_validation_no_owned_words_cause_aborted attempt=2
    error = _SHAPE_BUILDERS['custody_batch_validation_no_owned_words_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02963():
    # custody_batch_validation_no_owned_words_cause_aborted attempt=3
    error = _SHAPE_BUILDERS['custody_batch_validation_no_owned_words_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02964():
    # custody_batch_validation_no_owned_words_cause_aborted attempt=4
    error = _SHAPE_BUILDERS['custody_batch_validation_no_owned_words_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02965():
    # custody_batch_validation_no_owned_words_cause_aborted attempt=5
    error = _SHAPE_BUILDERS['custody_batch_validation_no_owned_words_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02966():
    # custody_batch_validation_no_owned_words_cause_aborted attempt=6
    error = _SHAPE_BUILDERS['custody_batch_validation_no_owned_words_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02967():
    # custody_batch_validation_no_owned_words_cause_aborted attempt=7
    error = _SHAPE_BUILDERS['custody_batch_validation_no_owned_words_cause_aborted']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02968():
    # timeout_family_6456 attempt=1
    error = _SHAPE_BUILDERS['timeout_family_6456']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02969():
    # timeout_family_6456 attempt=2
    error = _SHAPE_BUILDERS['timeout_family_6456']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02970():
    # timeout_family_6456 attempt=3
    error = _SHAPE_BUILDERS['timeout_family_6456']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02971():
    # timeout_family_6456 attempt=4
    error = _SHAPE_BUILDERS['timeout_family_6456']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02972():
    # timeout_family_6456 attempt=5
    error = _SHAPE_BUILDERS['timeout_family_6456']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02973():
    # timeout_family_6456 attempt=6
    error = _SHAPE_BUILDERS['timeout_family_6456']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02974():
    # timeout_family_6456 attempt=7
    error = _SHAPE_BUILDERS['timeout_family_6456']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02975():
    # timeout_family_9792 attempt=1
    error = _SHAPE_BUILDERS['timeout_family_9792']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02976():
    # timeout_family_9792 attempt=2
    error = _SHAPE_BUILDERS['timeout_family_9792']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02977():
    # timeout_family_9792 attempt=3
    error = _SHAPE_BUILDERS['timeout_family_9792']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02978():
    # timeout_family_9792 attempt=4
    error = _SHAPE_BUILDERS['timeout_family_9792']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02979():
    # timeout_family_9792 attempt=5
    error = _SHAPE_BUILDERS['timeout_family_9792']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02980():
    # timeout_family_9792 attempt=6
    error = _SHAPE_BUILDERS['timeout_family_9792']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02981():
    # timeout_family_9792 attempt=7
    error = _SHAPE_BUILDERS['timeout_family_9792']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02982():
    # timeout_family_400 attempt=1
    error = _SHAPE_BUILDERS['timeout_family_400']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02983():
    # timeout_family_400 attempt=2
    error = _SHAPE_BUILDERS['timeout_family_400']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02984():
    # timeout_family_400 attempt=3
    error = _SHAPE_BUILDERS['timeout_family_400']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02985():
    # timeout_family_400 attempt=4
    error = _SHAPE_BUILDERS['timeout_family_400']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02986():
    # timeout_family_400 attempt=5
    error = _SHAPE_BUILDERS['timeout_family_400']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02987():
    # timeout_family_400 attempt=6
    error = _SHAPE_BUILDERS['timeout_family_400']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02988():
    # timeout_family_400 attempt=7
    error = _SHAPE_BUILDERS['timeout_family_400']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02989():
    # wrapper_attempts_exhausted_0_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02990():
    # wrapper_attempts_exhausted_0_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02991():
    # wrapper_attempts_exhausted_0_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02992():
    # wrapper_attempts_exhausted_0_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02993():
    # wrapper_attempts_exhausted_0_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02994():
    # wrapper_attempts_exhausted_0_0 attempt=6
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02995():
    # wrapper_attempts_exhausted_0_0 attempt=7
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_02996():
    # wrapper_attempts_exhausted_0_1 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_02997():
    # wrapper_attempts_exhausted_0_1 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_02998():
    # wrapper_attempts_exhausted_0_1 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_02999():
    # wrapper_attempts_exhausted_0_1 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03000():
    # wrapper_attempts_exhausted_0_1 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03001():
    # wrapper_attempts_exhausted_0_1 attempt=6
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03002():
    # wrapper_attempts_exhausted_0_1 attempt=7
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03003():
    # wrapper_attempts_exhausted_0_25 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_25']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03004():
    # wrapper_attempts_exhausted_0_25 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_25']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03005():
    # wrapper_attempts_exhausted_0_25 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_25']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03006():
    # wrapper_attempts_exhausted_0_25 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_25']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03007():
    # wrapper_attempts_exhausted_0_25 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_25']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03008():
    # wrapper_attempts_exhausted_0_25 attempt=6
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_25']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03009():
    # wrapper_attempts_exhausted_0_25 attempt=7
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_25']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03010():
    # wrapper_attempts_exhausted_0_5 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_5']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03011():
    # wrapper_attempts_exhausted_0_5 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_5']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03012():
    # wrapper_attempts_exhausted_0_5 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_5']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03013():
    # wrapper_attempts_exhausted_0_5 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_5']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03014():
    # wrapper_attempts_exhausted_0_5 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_5']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03015():
    # wrapper_attempts_exhausted_0_5 attempt=6
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_5']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03016():
    # wrapper_attempts_exhausted_0_5 attempt=7
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_5']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03017():
    # wrapper_attempts_exhausted_1_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03018():
    # wrapper_attempts_exhausted_1_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03019():
    # wrapper_attempts_exhausted_1_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03020():
    # wrapper_attempts_exhausted_1_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03021():
    # wrapper_attempts_exhausted_1_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03022():
    # wrapper_attempts_exhausted_1_0 attempt=6
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03023():
    # wrapper_attempts_exhausted_1_0 attempt=7
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03024():
    # wrapper_attempts_exhausted_1_5 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_5']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 1.5


def test_effective_03025():
    # wrapper_attempts_exhausted_1_5 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_5']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 1.5


def test_effective_03026():
    # wrapper_attempts_exhausted_1_5 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_5']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.5


def test_effective_03027():
    # wrapper_attempts_exhausted_1_5 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_5']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03028():
    # wrapper_attempts_exhausted_1_5 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_5']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03029():
    # wrapper_attempts_exhausted_1_5 attempt=6
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_5']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03030():
    # wrapper_attempts_exhausted_1_5 attempt=7
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_5']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03031():
    # wrapper_attempts_exhausted_2_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03032():
    # wrapper_attempts_exhausted_2_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03033():
    # wrapper_attempts_exhausted_2_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03034():
    # wrapper_attempts_exhausted_2_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03035():
    # wrapper_attempts_exhausted_2_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03036():
    # wrapper_attempts_exhausted_2_0 attempt=6
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03037():
    # wrapper_attempts_exhausted_2_0 attempt=7
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03038():
    # wrapper_attempts_exhausted_2_5 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_5']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 2.5


def test_effective_03039():
    # wrapper_attempts_exhausted_2_5 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_5']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 2.5


def test_effective_03040():
    # wrapper_attempts_exhausted_2_5 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_5']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 2.5


def test_effective_03041():
    # wrapper_attempts_exhausted_2_5 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_5']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.5


def test_effective_03042():
    # wrapper_attempts_exhausted_2_5 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_5']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.5


def test_effective_03043():
    # wrapper_attempts_exhausted_2_5 attempt=6
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_5']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.5


def test_effective_03044():
    # wrapper_attempts_exhausted_2_5 attempt=7
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_5']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.5


def test_effective_03045():
    # wrapper_attempts_exhausted_3_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 3.0


def test_effective_03046():
    # wrapper_attempts_exhausted_3_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 3.0


def test_effective_03047():
    # wrapper_attempts_exhausted_3_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 3.0


def test_effective_03048():
    # wrapper_attempts_exhausted_3_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 3.0


def test_effective_03049():
    # wrapper_attempts_exhausted_3_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 3.0


def test_effective_03050():
    # wrapper_attempts_exhausted_3_0 attempt=6
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 3.0


def test_effective_03051():
    # wrapper_attempts_exhausted_3_0 attempt=7
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 3.0


def test_effective_03052():
    # wrapper_attempts_exhausted_3_9 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_9']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03053():
    # wrapper_attempts_exhausted_3_9 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_9']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03054():
    # wrapper_attempts_exhausted_3_9 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_9']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03055():
    # wrapper_attempts_exhausted_3_9 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_9']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03056():
    # wrapper_attempts_exhausted_3_9 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_9']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03057():
    # wrapper_attempts_exhausted_3_9 attempt=6
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_9']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03058():
    # wrapper_attempts_exhausted_3_9 attempt=7
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_9']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03059():
    # wrapper_attempts_exhausted_4_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03060():
    # wrapper_attempts_exhausted_4_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03061():
    # wrapper_attempts_exhausted_4_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03062():
    # wrapper_attempts_exhausted_4_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03063():
    # wrapper_attempts_exhausted_4_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03064():
    # wrapper_attempts_exhausted_4_0 attempt=6
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03065():
    # wrapper_attempts_exhausted_4_0 attempt=7
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03066():
    # wrapper_attempts_exhausted_4_1 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03067():
    # wrapper_attempts_exhausted_4_1 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03068():
    # wrapper_attempts_exhausted_4_1 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03069():
    # wrapper_attempts_exhausted_4_1 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03070():
    # wrapper_attempts_exhausted_4_1 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03071():
    # wrapper_attempts_exhausted_4_1 attempt=6
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03072():
    # wrapper_attempts_exhausted_4_1 attempt=7
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03073():
    # wrapper_attempts_exhausted_8_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_8_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03074():
    # wrapper_attempts_exhausted_8_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_8_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03075():
    # wrapper_attempts_exhausted_8_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_8_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03076():
    # wrapper_attempts_exhausted_8_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_8_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03077():
    # wrapper_attempts_exhausted_8_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_8_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03078():
    # wrapper_attempts_exhausted_8_0 attempt=6
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_8_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03079():
    # wrapper_attempts_exhausted_8_0 attempt=7
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_8_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03080():
    # wrapper_attempts_exhausted_50_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_50_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03081():
    # wrapper_attempts_exhausted_50_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_50_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03082():
    # wrapper_attempts_exhausted_50_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_50_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03083():
    # wrapper_attempts_exhausted_50_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_50_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03084():
    # wrapper_attempts_exhausted_50_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_50_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03085():
    # wrapper_attempts_exhausted_50_0 attempt=6
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_50_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03086():
    # wrapper_attempts_exhausted_50_0 attempt=7
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_50_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03087():
    # wrapper_attempts_exhausted_1000000000_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1000000000_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03088():
    # wrapper_attempts_exhausted_1000000000_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1000000000_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03089():
    # wrapper_attempts_exhausted_1000000000_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1000000000_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03090():
    # wrapper_attempts_exhausted_1000000000_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1000000000_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03091():
    # wrapper_attempts_exhausted_1000000000_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1000000000_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03092():
    # wrapper_attempts_exhausted_1000000000_0 attempt=6
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1000000000_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03093():
    # wrapper_attempts_exhausted_1000000000_0 attempt=7
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1000000000_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03094():
    # wrapper_deadline_exhausted_0_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03095():
    # wrapper_deadline_exhausted_0_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03096():
    # wrapper_deadline_exhausted_0_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03097():
    # wrapper_deadline_exhausted_0_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03098():
    # wrapper_deadline_exhausted_0_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03099():
    # wrapper_deadline_exhausted_0_0 attempt=6
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03100():
    # wrapper_deadline_exhausted_0_0 attempt=7
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03101():
    # wrapper_deadline_exhausted_0_1 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03102():
    # wrapper_deadline_exhausted_0_1 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03103():
    # wrapper_deadline_exhausted_0_1 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03104():
    # wrapper_deadline_exhausted_0_1 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03105():
    # wrapper_deadline_exhausted_0_1 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03106():
    # wrapper_deadline_exhausted_0_1 attempt=6
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03107():
    # wrapper_deadline_exhausted_0_1 attempt=7
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03108():
    # wrapper_deadline_exhausted_0_25 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_25']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03109():
    # wrapper_deadline_exhausted_0_25 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_25']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03110():
    # wrapper_deadline_exhausted_0_25 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_25']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03111():
    # wrapper_deadline_exhausted_0_25 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_25']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03112():
    # wrapper_deadline_exhausted_0_25 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_25']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03113():
    # wrapper_deadline_exhausted_0_25 attempt=6
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_25']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03114():
    # wrapper_deadline_exhausted_0_25 attempt=7
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_25']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03115():
    # wrapper_deadline_exhausted_0_5 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_5']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03116():
    # wrapper_deadline_exhausted_0_5 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_5']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03117():
    # wrapper_deadline_exhausted_0_5 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_5']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03118():
    # wrapper_deadline_exhausted_0_5 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_5']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03119():
    # wrapper_deadline_exhausted_0_5 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_5']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03120():
    # wrapper_deadline_exhausted_0_5 attempt=6
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_5']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03121():
    # wrapper_deadline_exhausted_0_5 attempt=7
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_5']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03122():
    # wrapper_deadline_exhausted_1_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03123():
    # wrapper_deadline_exhausted_1_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03124():
    # wrapper_deadline_exhausted_1_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03125():
    # wrapper_deadline_exhausted_1_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03126():
    # wrapper_deadline_exhausted_1_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03127():
    # wrapper_deadline_exhausted_1_0 attempt=6
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03128():
    # wrapper_deadline_exhausted_1_0 attempt=7
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03129():
    # wrapper_deadline_exhausted_1_5 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_5']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 1.5


def test_effective_03130():
    # wrapper_deadline_exhausted_1_5 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_5']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 1.5


def test_effective_03131():
    # wrapper_deadline_exhausted_1_5 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_5']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.5


def test_effective_03132():
    # wrapper_deadline_exhausted_1_5 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_5']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03133():
    # wrapper_deadline_exhausted_1_5 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_5']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03134():
    # wrapper_deadline_exhausted_1_5 attempt=6
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_5']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03135():
    # wrapper_deadline_exhausted_1_5 attempt=7
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_5']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03136():
    # wrapper_deadline_exhausted_2_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03137():
    # wrapper_deadline_exhausted_2_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03138():
    # wrapper_deadline_exhausted_2_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03139():
    # wrapper_deadline_exhausted_2_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03140():
    # wrapper_deadline_exhausted_2_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03141():
    # wrapper_deadline_exhausted_2_0 attempt=6
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03142():
    # wrapper_deadline_exhausted_2_0 attempt=7
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03143():
    # wrapper_deadline_exhausted_2_5 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_5']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 2.5


def test_effective_03144():
    # wrapper_deadline_exhausted_2_5 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_5']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 2.5


def test_effective_03145():
    # wrapper_deadline_exhausted_2_5 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_5']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 2.5


def test_effective_03146():
    # wrapper_deadline_exhausted_2_5 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_5']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.5


def test_effective_03147():
    # wrapper_deadline_exhausted_2_5 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_5']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.5


def test_effective_03148():
    # wrapper_deadline_exhausted_2_5 attempt=6
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_5']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.5


def test_effective_03149():
    # wrapper_deadline_exhausted_2_5 attempt=7
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_5']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.5


def test_effective_03150():
    # wrapper_deadline_exhausted_3_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 3.0


def test_effective_03151():
    # wrapper_deadline_exhausted_3_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 3.0


def test_effective_03152():
    # wrapper_deadline_exhausted_3_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 3.0


def test_effective_03153():
    # wrapper_deadline_exhausted_3_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 3.0


def test_effective_03154():
    # wrapper_deadline_exhausted_3_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 3.0


def test_effective_03155():
    # wrapper_deadline_exhausted_3_0 attempt=6
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 3.0


def test_effective_03156():
    # wrapper_deadline_exhausted_3_0 attempt=7
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 3.0


def test_effective_03157():
    # wrapper_deadline_exhausted_3_9 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_9']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03158():
    # wrapper_deadline_exhausted_3_9 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_9']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03159():
    # wrapper_deadline_exhausted_3_9 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_9']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03160():
    # wrapper_deadline_exhausted_3_9 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_9']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03161():
    # wrapper_deadline_exhausted_3_9 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_9']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03162():
    # wrapper_deadline_exhausted_3_9 attempt=6
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_9']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03163():
    # wrapper_deadline_exhausted_3_9 attempt=7
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_9']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03164():
    # wrapper_deadline_exhausted_4_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03165():
    # wrapper_deadline_exhausted_4_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03166():
    # wrapper_deadline_exhausted_4_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03167():
    # wrapper_deadline_exhausted_4_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03168():
    # wrapper_deadline_exhausted_4_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03169():
    # wrapper_deadline_exhausted_4_0 attempt=6
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03170():
    # wrapper_deadline_exhausted_4_0 attempt=7
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03171():
    # wrapper_deadline_exhausted_4_1 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03172():
    # wrapper_deadline_exhausted_4_1 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03173():
    # wrapper_deadline_exhausted_4_1 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03174():
    # wrapper_deadline_exhausted_4_1 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03175():
    # wrapper_deadline_exhausted_4_1 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03176():
    # wrapper_deadline_exhausted_4_1 attempt=6
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03177():
    # wrapper_deadline_exhausted_4_1 attempt=7
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03178():
    # wrapper_deadline_exhausted_8_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_8_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03179():
    # wrapper_deadline_exhausted_8_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_8_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03180():
    # wrapper_deadline_exhausted_8_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_8_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03181():
    # wrapper_deadline_exhausted_8_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_8_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03182():
    # wrapper_deadline_exhausted_8_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_8_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03183():
    # wrapper_deadline_exhausted_8_0 attempt=6
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_8_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03184():
    # wrapper_deadline_exhausted_8_0 attempt=7
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_8_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03185():
    # wrapper_deadline_exhausted_50_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_50_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03186():
    # wrapper_deadline_exhausted_50_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_50_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03187():
    # wrapper_deadline_exhausted_50_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_50_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03188():
    # wrapper_deadline_exhausted_50_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_50_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03189():
    # wrapper_deadline_exhausted_50_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_50_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03190():
    # wrapper_deadline_exhausted_50_0 attempt=6
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_50_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03191():
    # wrapper_deadline_exhausted_50_0 attempt=7
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_50_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03192():
    # wrapper_deadline_exhausted_1000000000_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1000000000_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03193():
    # wrapper_deadline_exhausted_1000000000_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1000000000_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03194():
    # wrapper_deadline_exhausted_1000000000_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1000000000_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03195():
    # wrapper_deadline_exhausted_1000000000_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1000000000_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03196():
    # wrapper_deadline_exhausted_1000000000_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1000000000_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03197():
    # wrapper_deadline_exhausted_1000000000_0 attempt=6
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1000000000_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03198():
    # wrapper_deadline_exhausted_1000000000_0 attempt=7
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1000000000_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03199():
    # carrier_ns_0 attempt=1
    error = _SHAPE_BUILDERS['carrier_ns_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03200():
    # carrier_ns_0 attempt=2
    error = _SHAPE_BUILDERS['carrier_ns_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03201():
    # carrier_ns_0 attempt=3
    error = _SHAPE_BUILDERS['carrier_ns_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03202():
    # carrier_ns_0 attempt=4
    error = _SHAPE_BUILDERS['carrier_ns_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03203():
    # carrier_ns_0 attempt=5
    error = _SHAPE_BUILDERS['carrier_ns_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03204():
    # carrier_ns_0 attempt=6
    error = _SHAPE_BUILDERS['carrier_ns_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03205():
    # carrier_ns_0 attempt=7
    error = _SHAPE_BUILDERS['carrier_ns_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03206():
    # carrier_err_0 attempt=1
    error = _SHAPE_BUILDERS['carrier_err_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03207():
    # carrier_err_0 attempt=2
    error = _SHAPE_BUILDERS['carrier_err_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03208():
    # carrier_err_0 attempt=3
    error = _SHAPE_BUILDERS['carrier_err_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03209():
    # carrier_err_0 attempt=4
    error = _SHAPE_BUILDERS['carrier_err_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03210():
    # carrier_err_0 attempt=5
    error = _SHAPE_BUILDERS['carrier_err_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03211():
    # carrier_err_0 attempt=6
    error = _SHAPE_BUILDERS['carrier_err_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03212():
    # carrier_err_0 attempt=7
    error = _SHAPE_BUILDERS['carrier_err_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03213():
    # carrier_ns_1 attempt=1
    error = _SHAPE_BUILDERS['carrier_ns_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03214():
    # carrier_ns_1 attempt=2
    error = _SHAPE_BUILDERS['carrier_ns_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03215():
    # carrier_ns_1 attempt=3
    error = _SHAPE_BUILDERS['carrier_ns_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03216():
    # carrier_ns_1 attempt=4
    error = _SHAPE_BUILDERS['carrier_ns_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03217():
    # carrier_ns_1 attempt=5
    error = _SHAPE_BUILDERS['carrier_ns_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03218():
    # carrier_ns_1 attempt=6
    error = _SHAPE_BUILDERS['carrier_ns_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03219():
    # carrier_ns_1 attempt=7
    error = _SHAPE_BUILDERS['carrier_ns_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03220():
    # carrier_err_1 attempt=1
    error = _SHAPE_BUILDERS['carrier_err_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03221():
    # carrier_err_1 attempt=2
    error = _SHAPE_BUILDERS['carrier_err_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03222():
    # carrier_err_1 attempt=3
    error = _SHAPE_BUILDERS['carrier_err_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03223():
    # carrier_err_1 attempt=4
    error = _SHAPE_BUILDERS['carrier_err_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03224():
    # carrier_err_1 attempt=5
    error = _SHAPE_BUILDERS['carrier_err_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03225():
    # carrier_err_1 attempt=6
    error = _SHAPE_BUILDERS['carrier_err_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03226():
    # carrier_err_1 attempt=7
    error = _SHAPE_BUILDERS['carrier_err_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03227():
    # carrier_ns_2 attempt=1
    error = _SHAPE_BUILDERS['carrier_ns_2']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03228():
    # carrier_ns_2 attempt=2
    error = _SHAPE_BUILDERS['carrier_ns_2']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03229():
    # carrier_ns_2 attempt=3
    error = _SHAPE_BUILDERS['carrier_ns_2']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03230():
    # carrier_ns_2 attempt=4
    error = _SHAPE_BUILDERS['carrier_ns_2']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03231():
    # carrier_ns_2 attempt=5
    error = _SHAPE_BUILDERS['carrier_ns_2']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03232():
    # carrier_ns_2 attempt=6
    error = _SHAPE_BUILDERS['carrier_ns_2']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03233():
    # carrier_ns_2 attempt=7
    error = _SHAPE_BUILDERS['carrier_ns_2']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03234():
    # carrier_err_2 attempt=1
    error = _SHAPE_BUILDERS['carrier_err_2']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03235():
    # carrier_err_2 attempt=2
    error = _SHAPE_BUILDERS['carrier_err_2']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03236():
    # carrier_err_2 attempt=3
    error = _SHAPE_BUILDERS['carrier_err_2']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03237():
    # carrier_err_2 attempt=4
    error = _SHAPE_BUILDERS['carrier_err_2']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03238():
    # carrier_err_2 attempt=5
    error = _SHAPE_BUILDERS['carrier_err_2']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03239():
    # carrier_err_2 attempt=6
    error = _SHAPE_BUILDERS['carrier_err_2']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03240():
    # carrier_err_2 attempt=7
    error = _SHAPE_BUILDERS['carrier_err_2']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03241():
    # carrier_ns_3 attempt=1
    error = _SHAPE_BUILDERS['carrier_ns_3']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03242():
    # carrier_ns_3 attempt=2
    error = _SHAPE_BUILDERS['carrier_ns_3']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03243():
    # carrier_ns_3 attempt=3
    error = _SHAPE_BUILDERS['carrier_ns_3']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03244():
    # carrier_ns_3 attempt=4
    error = _SHAPE_BUILDERS['carrier_ns_3']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03245():
    # carrier_ns_3 attempt=5
    error = _SHAPE_BUILDERS['carrier_ns_3']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03246():
    # carrier_ns_3 attempt=6
    error = _SHAPE_BUILDERS['carrier_ns_3']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03247():
    # carrier_ns_3 attempt=7
    error = _SHAPE_BUILDERS['carrier_ns_3']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03248():
    # carrier_err_3 attempt=1
    error = _SHAPE_BUILDERS['carrier_err_3']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03249():
    # carrier_err_3 attempt=2
    error = _SHAPE_BUILDERS['carrier_err_3']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03250():
    # carrier_err_3 attempt=3
    error = _SHAPE_BUILDERS['carrier_err_3']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03251():
    # carrier_err_3 attempt=4
    error = _SHAPE_BUILDERS['carrier_err_3']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03252():
    # carrier_err_3 attempt=5
    error = _SHAPE_BUILDERS['carrier_err_3']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03253():
    # carrier_err_3 attempt=6
    error = _SHAPE_BUILDERS['carrier_err_3']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03254():
    # carrier_err_3 attempt=7
    error = _SHAPE_BUILDERS['carrier_err_3']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03255():
    # carrier_ns_4 attempt=1
    error = _SHAPE_BUILDERS['carrier_ns_4']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03256():
    # carrier_ns_4 attempt=2
    error = _SHAPE_BUILDERS['carrier_ns_4']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03257():
    # carrier_ns_4 attempt=3
    error = _SHAPE_BUILDERS['carrier_ns_4']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03258():
    # carrier_ns_4 attempt=4
    error = _SHAPE_BUILDERS['carrier_ns_4']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03259():
    # carrier_ns_4 attempt=5
    error = _SHAPE_BUILDERS['carrier_ns_4']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03260():
    # carrier_ns_4 attempt=6
    error = _SHAPE_BUILDERS['carrier_ns_4']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03261():
    # carrier_ns_4 attempt=7
    error = _SHAPE_BUILDERS['carrier_ns_4']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03262():
    # carrier_err_4 attempt=1
    error = _SHAPE_BUILDERS['carrier_err_4']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03263():
    # carrier_err_4 attempt=2
    error = _SHAPE_BUILDERS['carrier_err_4']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03264():
    # carrier_err_4 attempt=3
    error = _SHAPE_BUILDERS['carrier_err_4']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03265():
    # carrier_err_4 attempt=4
    error = _SHAPE_BUILDERS['carrier_err_4']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03266():
    # carrier_err_4 attempt=5
    error = _SHAPE_BUILDERS['carrier_err_4']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03267():
    # carrier_err_4 attempt=6
    error = _SHAPE_BUILDERS['carrier_err_4']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03268():
    # carrier_err_4 attempt=7
    error = _SHAPE_BUILDERS['carrier_err_4']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03269():
    # carrier_ns_5 attempt=1
    error = _SHAPE_BUILDERS['carrier_ns_5']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03270():
    # carrier_ns_5 attempt=2
    error = _SHAPE_BUILDERS['carrier_ns_5']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03271():
    # carrier_ns_5 attempt=3
    error = _SHAPE_BUILDERS['carrier_ns_5']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03272():
    # carrier_ns_5 attempt=4
    error = _SHAPE_BUILDERS['carrier_ns_5']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03273():
    # carrier_ns_5 attempt=5
    error = _SHAPE_BUILDERS['carrier_ns_5']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03274():
    # carrier_ns_5 attempt=6
    error = _SHAPE_BUILDERS['carrier_ns_5']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03275():
    # carrier_ns_5 attempt=7
    error = _SHAPE_BUILDERS['carrier_ns_5']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03276():
    # carrier_err_5 attempt=1
    error = _SHAPE_BUILDERS['carrier_err_5']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03277():
    # carrier_err_5 attempt=2
    error = _SHAPE_BUILDERS['carrier_err_5']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03278():
    # carrier_err_5 attempt=3
    error = _SHAPE_BUILDERS['carrier_err_5']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03279():
    # carrier_err_5 attempt=4
    error = _SHAPE_BUILDERS['carrier_err_5']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03280():
    # carrier_err_5 attempt=5
    error = _SHAPE_BUILDERS['carrier_err_5']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03281():
    # carrier_err_5 attempt=6
    error = _SHAPE_BUILDERS['carrier_err_5']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03282():
    # carrier_err_5 attempt=7
    error = _SHAPE_BUILDERS['carrier_err_5']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03283():
    # carrier_ns_6 attempt=1
    error = _SHAPE_BUILDERS['carrier_ns_6']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03284():
    # carrier_ns_6 attempt=2
    error = _SHAPE_BUILDERS['carrier_ns_6']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03285():
    # carrier_ns_6 attempt=3
    error = _SHAPE_BUILDERS['carrier_ns_6']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03286():
    # carrier_ns_6 attempt=4
    error = _SHAPE_BUILDERS['carrier_ns_6']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03287():
    # carrier_ns_6 attempt=5
    error = _SHAPE_BUILDERS['carrier_ns_6']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03288():
    # carrier_ns_6 attempt=6
    error = _SHAPE_BUILDERS['carrier_ns_6']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03289():
    # carrier_ns_6 attempt=7
    error = _SHAPE_BUILDERS['carrier_ns_6']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03290():
    # carrier_err_6 attempt=1
    error = _SHAPE_BUILDERS['carrier_err_6']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03291():
    # carrier_err_6 attempt=2
    error = _SHAPE_BUILDERS['carrier_err_6']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03292():
    # carrier_err_6 attempt=3
    error = _SHAPE_BUILDERS['carrier_err_6']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03293():
    # carrier_err_6 attempt=4
    error = _SHAPE_BUILDERS['carrier_err_6']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03294():
    # carrier_err_6 attempt=5
    error = _SHAPE_BUILDERS['carrier_err_6']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03295():
    # carrier_err_6 attempt=6
    error = _SHAPE_BUILDERS['carrier_err_6']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03296():
    # carrier_err_6 attempt=7
    error = _SHAPE_BUILDERS['carrier_err_6']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03297():
    # carrier_ns_7 attempt=1
    error = _SHAPE_BUILDERS['carrier_ns_7']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03298():
    # carrier_ns_7 attempt=2
    error = _SHAPE_BUILDERS['carrier_ns_7']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03299():
    # carrier_ns_7 attempt=3
    error = _SHAPE_BUILDERS['carrier_ns_7']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03300():
    # carrier_ns_7 attempt=4
    error = _SHAPE_BUILDERS['carrier_ns_7']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03301():
    # carrier_ns_7 attempt=5
    error = _SHAPE_BUILDERS['carrier_ns_7']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03302():
    # carrier_ns_7 attempt=6
    error = _SHAPE_BUILDERS['carrier_ns_7']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03303():
    # carrier_ns_7 attempt=7
    error = _SHAPE_BUILDERS['carrier_ns_7']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03304():
    # carrier_err_7 attempt=1
    error = _SHAPE_BUILDERS['carrier_err_7']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03305():
    # carrier_err_7 attempt=2
    error = _SHAPE_BUILDERS['carrier_err_7']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03306():
    # carrier_err_7 attempt=3
    error = _SHAPE_BUILDERS['carrier_err_7']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03307():
    # carrier_err_7 attempt=4
    error = _SHAPE_BUILDERS['carrier_err_7']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03308():
    # carrier_err_7 attempt=5
    error = _SHAPE_BUILDERS['carrier_err_7']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03309():
    # carrier_err_7 attempt=6
    error = _SHAPE_BUILDERS['carrier_err_7']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03310():
    # carrier_err_7 attempt=7
    error = _SHAPE_BUILDERS['carrier_err_7']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03311():
    # carrier_ns_8 attempt=1
    error = _SHAPE_BUILDERS['carrier_ns_8']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03312():
    # carrier_ns_8 attempt=2
    error = _SHAPE_BUILDERS['carrier_ns_8']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03313():
    # carrier_ns_8 attempt=3
    error = _SHAPE_BUILDERS['carrier_ns_8']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03314():
    # carrier_ns_8 attempt=4
    error = _SHAPE_BUILDERS['carrier_ns_8']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03315():
    # carrier_ns_8 attempt=5
    error = _SHAPE_BUILDERS['carrier_ns_8']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03316():
    # carrier_ns_8 attempt=6
    error = _SHAPE_BUILDERS['carrier_ns_8']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03317():
    # carrier_ns_8 attempt=7
    error = _SHAPE_BUILDERS['carrier_ns_8']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03318():
    # carrier_err_8 attempt=1
    error = _SHAPE_BUILDERS['carrier_err_8']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03319():
    # carrier_err_8 attempt=2
    error = _SHAPE_BUILDERS['carrier_err_8']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03320():
    # carrier_err_8 attempt=3
    error = _SHAPE_BUILDERS['carrier_err_8']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03321():
    # carrier_err_8 attempt=4
    error = _SHAPE_BUILDERS['carrier_err_8']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03322():
    # carrier_err_8 attempt=5
    error = _SHAPE_BUILDERS['carrier_err_8']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03323():
    # carrier_err_8 attempt=6
    error = _SHAPE_BUILDERS['carrier_err_8']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03324():
    # carrier_err_8 attempt=7
    error = _SHAPE_BUILDERS['carrier_err_8']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03325():
    # carrier_ns_9 attempt=1
    error = _SHAPE_BUILDERS['carrier_ns_9']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03326():
    # carrier_ns_9 attempt=2
    error = _SHAPE_BUILDERS['carrier_ns_9']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03327():
    # carrier_ns_9 attempt=3
    error = _SHAPE_BUILDERS['carrier_ns_9']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03328():
    # carrier_ns_9 attempt=4
    error = _SHAPE_BUILDERS['carrier_ns_9']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03329():
    # carrier_ns_9 attempt=5
    error = _SHAPE_BUILDERS['carrier_ns_9']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03330():
    # carrier_ns_9 attempt=6
    error = _SHAPE_BUILDERS['carrier_ns_9']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03331():
    # carrier_ns_9 attempt=7
    error = _SHAPE_BUILDERS['carrier_ns_9']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03332():
    # carrier_err_9 attempt=1
    error = _SHAPE_BUILDERS['carrier_err_9']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03333():
    # carrier_err_9 attempt=2
    error = _SHAPE_BUILDERS['carrier_err_9']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03334():
    # carrier_err_9 attempt=3
    error = _SHAPE_BUILDERS['carrier_err_9']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03335():
    # carrier_err_9 attempt=4
    error = _SHAPE_BUILDERS['carrier_err_9']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03336():
    # carrier_err_9 attempt=5
    error = _SHAPE_BUILDERS['carrier_err_9']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03337():
    # carrier_err_9 attempt=6
    error = _SHAPE_BUILDERS['carrier_err_9']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03338():
    # carrier_err_9 attempt=7
    error = _SHAPE_BUILDERS['carrier_err_9']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03339():
    # carrier_ns_10 attempt=1
    error = _SHAPE_BUILDERS['carrier_ns_10']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03340():
    # carrier_ns_10 attempt=2
    error = _SHAPE_BUILDERS['carrier_ns_10']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03341():
    # carrier_ns_10 attempt=3
    error = _SHAPE_BUILDERS['carrier_ns_10']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03342():
    # carrier_ns_10 attempt=4
    error = _SHAPE_BUILDERS['carrier_ns_10']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03343():
    # carrier_ns_10 attempt=5
    error = _SHAPE_BUILDERS['carrier_ns_10']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03344():
    # carrier_ns_10 attempt=6
    error = _SHAPE_BUILDERS['carrier_ns_10']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03345():
    # carrier_ns_10 attempt=7
    error = _SHAPE_BUILDERS['carrier_ns_10']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03346():
    # carrier_err_10 attempt=1
    error = _SHAPE_BUILDERS['carrier_err_10']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03347():
    # carrier_err_10 attempt=2
    error = _SHAPE_BUILDERS['carrier_err_10']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03348():
    # carrier_err_10 attempt=3
    error = _SHAPE_BUILDERS['carrier_err_10']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03349():
    # carrier_err_10 attempt=4
    error = _SHAPE_BUILDERS['carrier_err_10']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03350():
    # carrier_err_10 attempt=5
    error = _SHAPE_BUILDERS['carrier_err_10']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03351():
    # carrier_err_10 attempt=6
    error = _SHAPE_BUILDERS['carrier_err_10']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03352():
    # carrier_err_10 attempt=7
    error = _SHAPE_BUILDERS['carrier_err_10']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03353():
    # carrier_ns_11 attempt=1
    error = _SHAPE_BUILDERS['carrier_ns_11']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03354():
    # carrier_ns_11 attempt=2
    error = _SHAPE_BUILDERS['carrier_ns_11']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03355():
    # carrier_ns_11 attempt=3
    error = _SHAPE_BUILDERS['carrier_ns_11']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03356():
    # carrier_ns_11 attempt=4
    error = _SHAPE_BUILDERS['carrier_ns_11']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03357():
    # carrier_ns_11 attempt=5
    error = _SHAPE_BUILDERS['carrier_ns_11']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03358():
    # carrier_ns_11 attempt=6
    error = _SHAPE_BUILDERS['carrier_ns_11']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03359():
    # carrier_ns_11 attempt=7
    error = _SHAPE_BUILDERS['carrier_ns_11']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03360():
    # carrier_err_11 attempt=1
    error = _SHAPE_BUILDERS['carrier_err_11']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03361():
    # carrier_err_11 attempt=2
    error = _SHAPE_BUILDERS['carrier_err_11']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03362():
    # carrier_err_11 attempt=3
    error = _SHAPE_BUILDERS['carrier_err_11']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03363():
    # carrier_err_11 attempt=4
    error = _SHAPE_BUILDERS['carrier_err_11']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03364():
    # carrier_err_11 attempt=5
    error = _SHAPE_BUILDERS['carrier_err_11']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03365():
    # carrier_err_11 attempt=6
    error = _SHAPE_BUILDERS['carrier_err_11']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03366():
    # carrier_err_11 attempt=7
    error = _SHAPE_BUILDERS['carrier_err_11']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03367():
    # carrier_ns_12 attempt=1
    error = _SHAPE_BUILDERS['carrier_ns_12']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03368():
    # carrier_ns_12 attempt=2
    error = _SHAPE_BUILDERS['carrier_ns_12']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03369():
    # carrier_ns_12 attempt=3
    error = _SHAPE_BUILDERS['carrier_ns_12']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03370():
    # carrier_ns_12 attempt=4
    error = _SHAPE_BUILDERS['carrier_ns_12']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03371():
    # carrier_ns_12 attempt=5
    error = _SHAPE_BUILDERS['carrier_ns_12']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03372():
    # carrier_ns_12 attempt=6
    error = _SHAPE_BUILDERS['carrier_ns_12']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03373():
    # carrier_ns_12 attempt=7
    error = _SHAPE_BUILDERS['carrier_ns_12']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03374():
    # carrier_err_12 attempt=1
    error = _SHAPE_BUILDERS['carrier_err_12']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03375():
    # carrier_err_12 attempt=2
    error = _SHAPE_BUILDERS['carrier_err_12']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03376():
    # carrier_err_12 attempt=3
    error = _SHAPE_BUILDERS['carrier_err_12']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03377():
    # carrier_err_12 attempt=4
    error = _SHAPE_BUILDERS['carrier_err_12']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03378():
    # carrier_err_12 attempt=5
    error = _SHAPE_BUILDERS['carrier_err_12']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03379():
    # carrier_err_12 attempt=6
    error = _SHAPE_BUILDERS['carrier_err_12']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03380():
    # carrier_err_12 attempt=7
    error = _SHAPE_BUILDERS['carrier_err_12']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 3.9


def test_effective_03381():
    # carrier_ns_13 attempt=1
    error = _SHAPE_BUILDERS['carrier_ns_13']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03382():
    # carrier_ns_13 attempt=2
    error = _SHAPE_BUILDERS['carrier_ns_13']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03383():
    # carrier_ns_13 attempt=3
    error = _SHAPE_BUILDERS['carrier_ns_13']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03384():
    # carrier_ns_13 attempt=4
    error = _SHAPE_BUILDERS['carrier_ns_13']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03385():
    # carrier_ns_13 attempt=5
    error = _SHAPE_BUILDERS['carrier_ns_13']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03386():
    # carrier_ns_13 attempt=6
    error = _SHAPE_BUILDERS['carrier_ns_13']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03387():
    # carrier_ns_13 attempt=7
    error = _SHAPE_BUILDERS['carrier_ns_13']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03388():
    # carrier_err_13 attempt=1
    error = _SHAPE_BUILDERS['carrier_err_13']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03389():
    # carrier_err_13 attempt=2
    error = _SHAPE_BUILDERS['carrier_err_13']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03390():
    # carrier_err_13 attempt=3
    error = _SHAPE_BUILDERS['carrier_err_13']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03391():
    # carrier_err_13 attempt=4
    error = _SHAPE_BUILDERS['carrier_err_13']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03392():
    # carrier_err_13 attempt=5
    error = _SHAPE_BUILDERS['carrier_err_13']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03393():
    # carrier_err_13 attempt=6
    error = _SHAPE_BUILDERS['carrier_err_13']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03394():
    # carrier_err_13 attempt=7
    error = _SHAPE_BUILDERS['carrier_err_13']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03395():
    # carrier_ns_14 attempt=1
    error = _SHAPE_BUILDERS['carrier_ns_14']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03396():
    # carrier_ns_14 attempt=2
    error = _SHAPE_BUILDERS['carrier_ns_14']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03397():
    # carrier_ns_14 attempt=3
    error = _SHAPE_BUILDERS['carrier_ns_14']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03398():
    # carrier_ns_14 attempt=4
    error = _SHAPE_BUILDERS['carrier_ns_14']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03399():
    # carrier_ns_14 attempt=5
    error = _SHAPE_BUILDERS['carrier_ns_14']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03400():
    # carrier_ns_14 attempt=6
    error = _SHAPE_BUILDERS['carrier_ns_14']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03401():
    # carrier_ns_14 attempt=7
    error = _SHAPE_BUILDERS['carrier_ns_14']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03402():
    # carrier_err_14 attempt=1
    error = _SHAPE_BUILDERS['carrier_err_14']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03403():
    # carrier_err_14 attempt=2
    error = _SHAPE_BUILDERS['carrier_err_14']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03404():
    # carrier_err_14 attempt=3
    error = _SHAPE_BUILDERS['carrier_err_14']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03405():
    # carrier_err_14 attempt=4
    error = _SHAPE_BUILDERS['carrier_err_14']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03406():
    # carrier_err_14 attempt=5
    error = _SHAPE_BUILDERS['carrier_err_14']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03407():
    # carrier_err_14 attempt=6
    error = _SHAPE_BUILDERS['carrier_err_14']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03408():
    # carrier_err_14 attempt=7
    error = _SHAPE_BUILDERS['carrier_err_14']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03409():
    # carrier_ns_15 attempt=1
    error = _SHAPE_BUILDERS['carrier_ns_15']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03410():
    # carrier_ns_15 attempt=2
    error = _SHAPE_BUILDERS['carrier_ns_15']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03411():
    # carrier_ns_15 attempt=3
    error = _SHAPE_BUILDERS['carrier_ns_15']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03412():
    # carrier_ns_15 attempt=4
    error = _SHAPE_BUILDERS['carrier_ns_15']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03413():
    # carrier_ns_15 attempt=5
    error = _SHAPE_BUILDERS['carrier_ns_15']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03414():
    # carrier_ns_15 attempt=6
    error = _SHAPE_BUILDERS['carrier_ns_15']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03415():
    # carrier_ns_15 attempt=7
    error = _SHAPE_BUILDERS['carrier_ns_15']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03416():
    # carrier_err_15 attempt=1
    error = _SHAPE_BUILDERS['carrier_err_15']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03417():
    # carrier_err_15 attempt=2
    error = _SHAPE_BUILDERS['carrier_err_15']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03418():
    # carrier_err_15 attempt=3
    error = _SHAPE_BUILDERS['carrier_err_15']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03419():
    # carrier_err_15 attempt=4
    error = _SHAPE_BUILDERS['carrier_err_15']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03420():
    # carrier_err_15 attempt=5
    error = _SHAPE_BUILDERS['carrier_err_15']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03421():
    # carrier_err_15 attempt=6
    error = _SHAPE_BUILDERS['carrier_err_15']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03422():
    # carrier_err_15 attempt=7
    error = _SHAPE_BUILDERS['carrier_err_15']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03423():
    # carrier_ns_16 attempt=1
    error = _SHAPE_BUILDERS['carrier_ns_16']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03424():
    # carrier_ns_16 attempt=2
    error = _SHAPE_BUILDERS['carrier_ns_16']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03425():
    # carrier_ns_16 attempt=3
    error = _SHAPE_BUILDERS['carrier_ns_16']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03426():
    # carrier_ns_16 attempt=4
    error = _SHAPE_BUILDERS['carrier_ns_16']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03427():
    # carrier_ns_16 attempt=5
    error = _SHAPE_BUILDERS['carrier_ns_16']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03428():
    # carrier_ns_16 attempt=6
    error = _SHAPE_BUILDERS['carrier_ns_16']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03429():
    # carrier_ns_16 attempt=7
    error = _SHAPE_BUILDERS['carrier_ns_16']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03430():
    # carrier_err_16 attempt=1
    error = _SHAPE_BUILDERS['carrier_err_16']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03431():
    # carrier_err_16 attempt=2
    error = _SHAPE_BUILDERS['carrier_err_16']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03432():
    # carrier_err_16 attempt=3
    error = _SHAPE_BUILDERS['carrier_err_16']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03433():
    # carrier_err_16 attempt=4
    error = _SHAPE_BUILDERS['carrier_err_16']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03434():
    # carrier_err_16 attempt=5
    error = _SHAPE_BUILDERS['carrier_err_16']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03435():
    # carrier_err_16 attempt=6
    error = _SHAPE_BUILDERS['carrier_err_16']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03436():
    # carrier_err_16 attempt=7
    error = _SHAPE_BUILDERS['carrier_err_16']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 4.0


def test_effective_03437():
    # carrier_ns_17 attempt=1
    error = _SHAPE_BUILDERS['carrier_ns_17']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03438():
    # carrier_ns_17 attempt=2
    error = _SHAPE_BUILDERS['carrier_ns_17']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03439():
    # carrier_ns_17 attempt=3
    error = _SHAPE_BUILDERS['carrier_ns_17']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03440():
    # carrier_ns_17 attempt=4
    error = _SHAPE_BUILDERS['carrier_ns_17']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03441():
    # carrier_ns_17 attempt=5
    error = _SHAPE_BUILDERS['carrier_ns_17']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03442():
    # carrier_ns_17 attempt=6
    error = _SHAPE_BUILDERS['carrier_ns_17']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03443():
    # carrier_ns_17 attempt=7
    error = _SHAPE_BUILDERS['carrier_ns_17']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03444():
    # carrier_err_17 attempt=1
    error = _SHAPE_BUILDERS['carrier_err_17']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03445():
    # carrier_err_17 attempt=2
    error = _SHAPE_BUILDERS['carrier_err_17']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03446():
    # carrier_err_17 attempt=3
    error = _SHAPE_BUILDERS['carrier_err_17']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03447():
    # carrier_err_17 attempt=4
    error = _SHAPE_BUILDERS['carrier_err_17']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03448():
    # carrier_err_17 attempt=5
    error = _SHAPE_BUILDERS['carrier_err_17']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03449():
    # carrier_err_17 attempt=6
    error = _SHAPE_BUILDERS['carrier_err_17']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03450():
    # carrier_err_17 attempt=7
    error = _SHAPE_BUILDERS['carrier_err_17']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03451():
    # carrier_ns_18 attempt=1
    error = _SHAPE_BUILDERS['carrier_ns_18']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03452():
    # carrier_ns_18 attempt=2
    error = _SHAPE_BUILDERS['carrier_ns_18']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03453():
    # carrier_ns_18 attempt=3
    error = _SHAPE_BUILDERS['carrier_ns_18']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03454():
    # carrier_ns_18 attempt=4
    error = _SHAPE_BUILDERS['carrier_ns_18']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03455():
    # carrier_ns_18 attempt=5
    error = _SHAPE_BUILDERS['carrier_ns_18']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03456():
    # carrier_ns_18 attempt=6
    error = _SHAPE_BUILDERS['carrier_ns_18']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03457():
    # carrier_ns_18 attempt=7
    error = _SHAPE_BUILDERS['carrier_ns_18']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03458():
    # carrier_err_18 attempt=1
    error = _SHAPE_BUILDERS['carrier_err_18']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03459():
    # carrier_err_18 attempt=2
    error = _SHAPE_BUILDERS['carrier_err_18']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03460():
    # carrier_err_18 attempt=3
    error = _SHAPE_BUILDERS['carrier_err_18']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03461():
    # carrier_err_18 attempt=4
    error = _SHAPE_BUILDERS['carrier_err_18']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03462():
    # carrier_err_18 attempt=5
    error = _SHAPE_BUILDERS['carrier_err_18']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03463():
    # carrier_err_18 attempt=6
    error = _SHAPE_BUILDERS['carrier_err_18']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03464():
    # carrier_err_18 attempt=7
    error = _SHAPE_BUILDERS['carrier_err_18']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03465():
    # carrier_ns_19 attempt=1
    error = _SHAPE_BUILDERS['carrier_ns_19']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03466():
    # carrier_ns_19 attempt=2
    error = _SHAPE_BUILDERS['carrier_ns_19']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03467():
    # carrier_ns_19 attempt=3
    error = _SHAPE_BUILDERS['carrier_ns_19']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03468():
    # carrier_ns_19 attempt=4
    error = _SHAPE_BUILDERS['carrier_ns_19']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03469():
    # carrier_ns_19 attempt=5
    error = _SHAPE_BUILDERS['carrier_ns_19']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03470():
    # carrier_ns_19 attempt=6
    error = _SHAPE_BUILDERS['carrier_ns_19']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03471():
    # carrier_ns_19 attempt=7
    error = _SHAPE_BUILDERS['carrier_ns_19']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03472():
    # carrier_err_19 attempt=1
    error = _SHAPE_BUILDERS['carrier_err_19']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03473():
    # carrier_err_19 attempt=2
    error = _SHAPE_BUILDERS['carrier_err_19']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03474():
    # carrier_err_19 attempt=3
    error = _SHAPE_BUILDERS['carrier_err_19']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03475():
    # carrier_err_19 attempt=4
    error = _SHAPE_BUILDERS['carrier_err_19']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03476():
    # carrier_err_19 attempt=5
    error = _SHAPE_BUILDERS['carrier_err_19']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03477():
    # carrier_err_19 attempt=6
    error = _SHAPE_BUILDERS['carrier_err_19']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03478():
    # carrier_err_19 attempt=7
    error = _SHAPE_BUILDERS['carrier_err_19']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03479():
    # carrier_ns_20 attempt=1
    error = _SHAPE_BUILDERS['carrier_ns_20']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03480():
    # carrier_ns_20 attempt=2
    error = _SHAPE_BUILDERS['carrier_ns_20']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03481():
    # carrier_ns_20 attempt=3
    error = _SHAPE_BUILDERS['carrier_ns_20']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03482():
    # carrier_ns_20 attempt=4
    error = _SHAPE_BUILDERS['carrier_ns_20']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03483():
    # carrier_ns_20 attempt=5
    error = _SHAPE_BUILDERS['carrier_ns_20']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03484():
    # carrier_ns_20 attempt=6
    error = _SHAPE_BUILDERS['carrier_ns_20']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03485():
    # carrier_ns_20 attempt=7
    error = _SHAPE_BUILDERS['carrier_ns_20']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03486():
    # carrier_err_20 attempt=1
    error = _SHAPE_BUILDERS['carrier_err_20']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03487():
    # carrier_err_20 attempt=2
    error = _SHAPE_BUILDERS['carrier_err_20']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03488():
    # carrier_err_20 attempt=3
    error = _SHAPE_BUILDERS['carrier_err_20']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03489():
    # carrier_err_20 attempt=4
    error = _SHAPE_BUILDERS['carrier_err_20']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03490():
    # carrier_err_20 attempt=5
    error = _SHAPE_BUILDERS['carrier_err_20']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03491():
    # carrier_err_20 attempt=6
    error = _SHAPE_BUILDERS['carrier_err_20']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03492():
    # carrier_err_20 attempt=7
    error = _SHAPE_BUILDERS['carrier_err_20']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03493():
    # hostile_0 attempt=1
    error = _SHAPE_BUILDERS['hostile_0']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03494():
    # hostile_0 attempt=2
    error = _SHAPE_BUILDERS['hostile_0']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03495():
    # hostile_0 attempt=3
    error = _SHAPE_BUILDERS['hostile_0']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03496():
    # hostile_0 attempt=4
    error = _SHAPE_BUILDERS['hostile_0']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03497():
    # hostile_0 attempt=5
    error = _SHAPE_BUILDERS['hostile_0']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03498():
    # hostile_0 attempt=6
    error = _SHAPE_BUILDERS['hostile_0']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03499():
    # hostile_0 attempt=7
    error = _SHAPE_BUILDERS['hostile_0']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03500():
    # hostile_1 attempt=1
    error = _SHAPE_BUILDERS['hostile_1']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03501():
    # hostile_1 attempt=2
    error = _SHAPE_BUILDERS['hostile_1']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03502():
    # hostile_1 attempt=3
    error = _SHAPE_BUILDERS['hostile_1']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03503():
    # hostile_1 attempt=4
    error = _SHAPE_BUILDERS['hostile_1']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03504():
    # hostile_1 attempt=5
    error = _SHAPE_BUILDERS['hostile_1']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03505():
    # hostile_1 attempt=6
    error = _SHAPE_BUILDERS['hostile_1']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03506():
    # hostile_1 attempt=7
    error = _SHAPE_BUILDERS['hostile_1']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03507():
    # hostile_2 attempt=1
    error = _SHAPE_BUILDERS['hostile_2']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03508():
    # hostile_2 attempt=2
    error = _SHAPE_BUILDERS['hostile_2']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03509():
    # hostile_2 attempt=3
    error = _SHAPE_BUILDERS['hostile_2']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03510():
    # hostile_2 attempt=4
    error = _SHAPE_BUILDERS['hostile_2']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03511():
    # hostile_2 attempt=5
    error = _SHAPE_BUILDERS['hostile_2']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03512():
    # hostile_2 attempt=6
    error = _SHAPE_BUILDERS['hostile_2']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03513():
    # hostile_2 attempt=7
    error = _SHAPE_BUILDERS['hostile_2']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03514():
    # hostile_3 attempt=1
    error = _SHAPE_BUILDERS['hostile_3']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03515():
    # hostile_3 attempt=2
    error = _SHAPE_BUILDERS['hostile_3']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03516():
    # hostile_3 attempt=3
    error = _SHAPE_BUILDERS['hostile_3']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03517():
    # hostile_3 attempt=4
    error = _SHAPE_BUILDERS['hostile_3']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03518():
    # hostile_3 attempt=5
    error = _SHAPE_BUILDERS['hostile_3']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03519():
    # hostile_3 attempt=6
    error = _SHAPE_BUILDERS['hostile_3']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03520():
    # hostile_3 attempt=7
    error = _SHAPE_BUILDERS['hostile_3']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03521():
    # hostile_4 attempt=1
    error = _SHAPE_BUILDERS['hostile_4']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03522():
    # hostile_4 attempt=2
    error = _SHAPE_BUILDERS['hostile_4']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03523():
    # hostile_4 attempt=3
    error = _SHAPE_BUILDERS['hostile_4']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03524():
    # hostile_4 attempt=4
    error = _SHAPE_BUILDERS['hostile_4']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03525():
    # hostile_4 attempt=5
    error = _SHAPE_BUILDERS['hostile_4']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03526():
    # hostile_4 attempt=6
    error = _SHAPE_BUILDERS['hostile_4']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03527():
    # hostile_4 attempt=7
    error = _SHAPE_BUILDERS['hostile_4']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03528():
    # hostile_5 attempt=1
    error = _SHAPE_BUILDERS['hostile_5']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03529():
    # hostile_5 attempt=2
    error = _SHAPE_BUILDERS['hostile_5']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03530():
    # hostile_5 attempt=3
    error = _SHAPE_BUILDERS['hostile_5']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03531():
    # hostile_5 attempt=4
    error = _SHAPE_BUILDERS['hostile_5']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03532():
    # hostile_5 attempt=5
    error = _SHAPE_BUILDERS['hostile_5']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03533():
    # hostile_5 attempt=6
    error = _SHAPE_BUILDERS['hostile_5']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03534():
    # hostile_5 attempt=7
    error = _SHAPE_BUILDERS['hostile_5']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03535():
    # hostile_6 attempt=1
    error = _SHAPE_BUILDERS['hostile_6']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03536():
    # hostile_6 attempt=2
    error = _SHAPE_BUILDERS['hostile_6']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03537():
    # hostile_6 attempt=3
    error = _SHAPE_BUILDERS['hostile_6']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03538():
    # hostile_6 attempt=4
    error = _SHAPE_BUILDERS['hostile_6']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03539():
    # hostile_6 attempt=5
    error = _SHAPE_BUILDERS['hostile_6']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03540():
    # hostile_6 attempt=6
    error = _SHAPE_BUILDERS['hostile_6']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03541():
    # hostile_6 attempt=7
    error = _SHAPE_BUILDERS['hostile_6']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03542():
    # hostile_7 attempt=1
    error = _SHAPE_BUILDERS['hostile_7']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03543():
    # hostile_7 attempt=2
    error = _SHAPE_BUILDERS['hostile_7']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03544():
    # hostile_7 attempt=3
    error = _SHAPE_BUILDERS['hostile_7']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03545():
    # hostile_7 attempt=4
    error = _SHAPE_BUILDERS['hostile_7']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03546():
    # hostile_7 attempt=5
    error = _SHAPE_BUILDERS['hostile_7']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03547():
    # hostile_7 attempt=6
    error = _SHAPE_BUILDERS['hostile_7']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03548():
    # hostile_7 attempt=7
    error = _SHAPE_BUILDERS['hostile_7']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03549():
    # hostile_8 attempt=1
    error = _SHAPE_BUILDERS['hostile_8']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03550():
    # hostile_8 attempt=2
    error = _SHAPE_BUILDERS['hostile_8']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03551():
    # hostile_8 attempt=3
    error = _SHAPE_BUILDERS['hostile_8']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03552():
    # hostile_8 attempt=4
    error = _SHAPE_BUILDERS['hostile_8']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03553():
    # hostile_8 attempt=5
    error = _SHAPE_BUILDERS['hostile_8']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03554():
    # hostile_8 attempt=6
    error = _SHAPE_BUILDERS['hostile_8']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03555():
    # hostile_8 attempt=7
    error = _SHAPE_BUILDERS['hostile_8']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03556():
    # hostile_9 attempt=1
    error = _SHAPE_BUILDERS['hostile_9']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03557():
    # hostile_9 attempt=2
    error = _SHAPE_BUILDERS['hostile_9']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03558():
    # hostile_9 attempt=3
    error = _SHAPE_BUILDERS['hostile_9']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03559():
    # hostile_9 attempt=4
    error = _SHAPE_BUILDERS['hostile_9']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03560():
    # hostile_9 attempt=5
    error = _SHAPE_BUILDERS['hostile_9']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03561():
    # hostile_9 attempt=6
    error = _SHAPE_BUILDERS['hostile_9']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03562():
    # hostile_9 attempt=7
    error = _SHAPE_BUILDERS['hostile_9']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03563():
    # hostile_10 attempt=1
    error = _SHAPE_BUILDERS['hostile_10']()
    assert round(max(bp.persist_restrike_delay(1), bp.persist_restrike_storm_after(error)), 6) == 0.25


def test_effective_03564():
    # hostile_10 attempt=2
    error = _SHAPE_BUILDERS['hostile_10']()
    assert round(max(bp.persist_restrike_delay(2), bp.persist_restrike_storm_after(error)), 6) == 0.5


def test_effective_03565():
    # hostile_10 attempt=3
    error = _SHAPE_BUILDERS['hostile_10']()
    assert round(max(bp.persist_restrike_delay(3), bp.persist_restrike_storm_after(error)), 6) == 1.0


def test_effective_03566():
    # hostile_10 attempt=4
    error = _SHAPE_BUILDERS['hostile_10']()
    assert round(max(bp.persist_restrike_delay(4), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03567():
    # hostile_10 attempt=5
    error = _SHAPE_BUILDERS['hostile_10']()
    assert round(max(bp.persist_restrike_delay(5), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03568():
    # hostile_10 attempt=6
    error = _SHAPE_BUILDERS['hostile_10']()
    assert round(max(bp.persist_restrike_delay(6), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_effective_03569():
    # hostile_10 attempt=7
    error = _SHAPE_BUILDERS['hostile_10']()
    assert round(max(bp.persist_restrike_delay(7), bp.persist_restrike_storm_after(error)), 6) == 2.0


def test_storm_read_03570():
    # wrapper_attempts_exhausted_0_0 attempt=0
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.0
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03571():
    # wrapper_attempts_exhausted_0_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.0
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03572():
    # wrapper_attempts_exhausted_0_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.0
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03573():
    # wrapper_attempts_exhausted_0_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.0
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03574():
    # wrapper_attempts_exhausted_0_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.0
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03575():
    # wrapper_attempts_exhausted_0_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.0
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03576():
    # wrapper_attempts_exhausted_0_1 attempt=0
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_1']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.1
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03577():
    # wrapper_attempts_exhausted_0_1 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_1']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.1
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03578():
    # wrapper_attempts_exhausted_0_1 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_1']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.1
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03579():
    # wrapper_attempts_exhausted_0_1 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_1']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.1
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03580():
    # wrapper_attempts_exhausted_0_1 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_1']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.1
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03581():
    # wrapper_attempts_exhausted_0_1 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_1']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.1
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03582():
    # wrapper_attempts_exhausted_0_25 attempt=0
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_25']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.25
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03583():
    # wrapper_attempts_exhausted_0_25 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_25']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.25
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03584():
    # wrapper_attempts_exhausted_0_25 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_25']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.25
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03585():
    # wrapper_attempts_exhausted_0_25 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_25']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.25
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03586():
    # wrapper_attempts_exhausted_0_25 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_25']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.25
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03587():
    # wrapper_attempts_exhausted_0_25 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_25']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.25
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03588():
    # wrapper_attempts_exhausted_0_5 attempt=0
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.5
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03589():
    # wrapper_attempts_exhausted_0_5 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.5
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03590():
    # wrapper_attempts_exhausted_0_5 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.5
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03591():
    # wrapper_attempts_exhausted_0_5 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.5
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03592():
    # wrapper_attempts_exhausted_0_5 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.5
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03593():
    # wrapper_attempts_exhausted_0_5 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_0_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.5
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03594():
    # wrapper_attempts_exhausted_1_0 attempt=0
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 1.0
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03595():
    # wrapper_attempts_exhausted_1_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 1.0
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03596():
    # wrapper_attempts_exhausted_1_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 1.0
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03597():
    # wrapper_attempts_exhausted_1_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 1.0
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03598():
    # wrapper_attempts_exhausted_1_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 1.0
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03599():
    # wrapper_attempts_exhausted_1_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 1.0
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03600():
    # wrapper_attempts_exhausted_1_5 attempt=0
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 1.5
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03601():
    # wrapper_attempts_exhausted_1_5 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 1.5
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03602():
    # wrapper_attempts_exhausted_1_5 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 1.5
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03603():
    # wrapper_attempts_exhausted_1_5 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 1.5
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03604():
    # wrapper_attempts_exhausted_1_5 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 1.5
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03605():
    # wrapper_attempts_exhausted_1_5 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 1.5
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03606():
    # wrapper_attempts_exhausted_2_0 attempt=0
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 2.0
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03607():
    # wrapper_attempts_exhausted_2_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 2.0
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03608():
    # wrapper_attempts_exhausted_2_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 2.0
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03609():
    # wrapper_attempts_exhausted_2_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 2.0
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03610():
    # wrapper_attempts_exhausted_2_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 2.0
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03611():
    # wrapper_attempts_exhausted_2_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 2.0
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03612():
    # wrapper_attempts_exhausted_2_5 attempt=0
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 2.5
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03613():
    # wrapper_attempts_exhausted_2_5 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 2.5
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03614():
    # wrapper_attempts_exhausted_2_5 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 2.5
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03615():
    # wrapper_attempts_exhausted_2_5 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 2.5
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03616():
    # wrapper_attempts_exhausted_2_5 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 2.5
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03617():
    # wrapper_attempts_exhausted_2_5 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_2_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 2.5
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03618():
    # wrapper_attempts_exhausted_3_0 attempt=0
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 3.0
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03619():
    # wrapper_attempts_exhausted_3_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 3.0
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03620():
    # wrapper_attempts_exhausted_3_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 3.0
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03621():
    # wrapper_attempts_exhausted_3_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 3.0
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03622():
    # wrapper_attempts_exhausted_3_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 3.0
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03623():
    # wrapper_attempts_exhausted_3_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 3.0
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03624():
    # wrapper_attempts_exhausted_3_9 attempt=0
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_9']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 3.9
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03625():
    # wrapper_attempts_exhausted_3_9 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_9']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 3.9
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03626():
    # wrapper_attempts_exhausted_3_9 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_9']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 3.9
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03627():
    # wrapper_attempts_exhausted_3_9 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_9']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 3.9
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03628():
    # wrapper_attempts_exhausted_3_9 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_9']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 3.9
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03629():
    # wrapper_attempts_exhausted_3_9 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_3_9']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 3.9
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03630():
    # wrapper_attempts_exhausted_4_0 attempt=0
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03631():
    # wrapper_attempts_exhausted_4_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03632():
    # wrapper_attempts_exhausted_4_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03633():
    # wrapper_attempts_exhausted_4_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03634():
    # wrapper_attempts_exhausted_4_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03635():
    # wrapper_attempts_exhausted_4_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03636():
    # wrapper_attempts_exhausted_4_1 attempt=0
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_1']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03637():
    # wrapper_attempts_exhausted_4_1 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_1']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03638():
    # wrapper_attempts_exhausted_4_1 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_1']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03639():
    # wrapper_attempts_exhausted_4_1 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_1']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03640():
    # wrapper_attempts_exhausted_4_1 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_1']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03641():
    # wrapper_attempts_exhausted_4_1 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_4_1']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03642():
    # wrapper_attempts_exhausted_8_0 attempt=0
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_8_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03643():
    # wrapper_attempts_exhausted_8_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_8_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03644():
    # wrapper_attempts_exhausted_8_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_8_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03645():
    # wrapper_attempts_exhausted_8_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_8_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03646():
    # wrapper_attempts_exhausted_8_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_8_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03647():
    # wrapper_attempts_exhausted_8_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_8_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03648():
    # wrapper_attempts_exhausted_50_0 attempt=0
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_50_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03649():
    # wrapper_attempts_exhausted_50_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_50_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03650():
    # wrapper_attempts_exhausted_50_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_50_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03651():
    # wrapper_attempts_exhausted_50_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_50_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03652():
    # wrapper_attempts_exhausted_50_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_50_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03653():
    # wrapper_attempts_exhausted_50_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_50_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03654():
    # wrapper_attempts_exhausted_1000000000_0 attempt=0
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1000000000_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03655():
    # wrapper_attempts_exhausted_1000000000_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1000000000_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03656():
    # wrapper_attempts_exhausted_1000000000_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1000000000_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03657():
    # wrapper_attempts_exhausted_1000000000_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1000000000_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03658():
    # wrapper_attempts_exhausted_1000000000_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1000000000_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03659():
    # wrapper_attempts_exhausted_1000000000_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_attempts_exhausted_1000000000_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03660():
    # wrapper_deadline_exhausted_0_0 attempt=0
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.0
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03661():
    # wrapper_deadline_exhausted_0_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.0
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03662():
    # wrapper_deadline_exhausted_0_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.0
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03663():
    # wrapper_deadline_exhausted_0_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.0
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03664():
    # wrapper_deadline_exhausted_0_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.0
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03665():
    # wrapper_deadline_exhausted_0_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.0
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03666():
    # wrapper_deadline_exhausted_0_1 attempt=0
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_1']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.1
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03667():
    # wrapper_deadline_exhausted_0_1 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_1']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.1
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03668():
    # wrapper_deadline_exhausted_0_1 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_1']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.1
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03669():
    # wrapper_deadline_exhausted_0_1 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_1']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.1
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03670():
    # wrapper_deadline_exhausted_0_1 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_1']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.1
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03671():
    # wrapper_deadline_exhausted_0_1 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_1']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.1
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03672():
    # wrapper_deadline_exhausted_0_25 attempt=0
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_25']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.25
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03673():
    # wrapper_deadline_exhausted_0_25 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_25']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.25
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03674():
    # wrapper_deadline_exhausted_0_25 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_25']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.25
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03675():
    # wrapper_deadline_exhausted_0_25 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_25']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.25
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03676():
    # wrapper_deadline_exhausted_0_25 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_25']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.25
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03677():
    # wrapper_deadline_exhausted_0_25 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_25']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.25
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03678():
    # wrapper_deadline_exhausted_0_5 attempt=0
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.5
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03679():
    # wrapper_deadline_exhausted_0_5 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.5
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03680():
    # wrapper_deadline_exhausted_0_5 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.5
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03681():
    # wrapper_deadline_exhausted_0_5 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.5
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03682():
    # wrapper_deadline_exhausted_0_5 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.5
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03683():
    # wrapper_deadline_exhausted_0_5 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_0_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 0.5
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03684():
    # wrapper_deadline_exhausted_1_0 attempt=0
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 1.0
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03685():
    # wrapper_deadline_exhausted_1_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 1.0
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03686():
    # wrapper_deadline_exhausted_1_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 1.0
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03687():
    # wrapper_deadline_exhausted_1_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 1.0
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03688():
    # wrapper_deadline_exhausted_1_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 1.0
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03689():
    # wrapper_deadline_exhausted_1_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 1.0
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03690():
    # wrapper_deadline_exhausted_1_5 attempt=0
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 1.5
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03691():
    # wrapper_deadline_exhausted_1_5 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 1.5
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03692():
    # wrapper_deadline_exhausted_1_5 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 1.5
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03693():
    # wrapper_deadline_exhausted_1_5 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 1.5
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03694():
    # wrapper_deadline_exhausted_1_5 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 1.5
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03695():
    # wrapper_deadline_exhausted_1_5 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 1.5
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03696():
    # wrapper_deadline_exhausted_2_0 attempt=0
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 2.0
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03697():
    # wrapper_deadline_exhausted_2_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 2.0
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03698():
    # wrapper_deadline_exhausted_2_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 2.0
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03699():
    # wrapper_deadline_exhausted_2_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 2.0
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03700():
    # wrapper_deadline_exhausted_2_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 2.0
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03701():
    # wrapper_deadline_exhausted_2_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 2.0
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03702():
    # wrapper_deadline_exhausted_2_5 attempt=0
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 2.5
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03703():
    # wrapper_deadline_exhausted_2_5 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 2.5
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03704():
    # wrapper_deadline_exhausted_2_5 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 2.5
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03705():
    # wrapper_deadline_exhausted_2_5 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 2.5
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03706():
    # wrapper_deadline_exhausted_2_5 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 2.5
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03707():
    # wrapper_deadline_exhausted_2_5 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_2_5']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 2.5
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03708():
    # wrapper_deadline_exhausted_3_0 attempt=0
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 3.0
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03709():
    # wrapper_deadline_exhausted_3_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 3.0
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03710():
    # wrapper_deadline_exhausted_3_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 3.0
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03711():
    # wrapper_deadline_exhausted_3_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 3.0
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03712():
    # wrapper_deadline_exhausted_3_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 3.0
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03713():
    # wrapper_deadline_exhausted_3_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 3.0
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03714():
    # wrapper_deadline_exhausted_3_9 attempt=0
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_9']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 3.9
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03715():
    # wrapper_deadline_exhausted_3_9 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_9']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 3.9
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03716():
    # wrapper_deadline_exhausted_3_9 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_9']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 3.9
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03717():
    # wrapper_deadline_exhausted_3_9 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_9']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 3.9
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03718():
    # wrapper_deadline_exhausted_3_9 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_9']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 3.9
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03719():
    # wrapper_deadline_exhausted_3_9 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_3_9']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 3.9
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03720():
    # wrapper_deadline_exhausted_4_0 attempt=0
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03721():
    # wrapper_deadline_exhausted_4_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03722():
    # wrapper_deadline_exhausted_4_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03723():
    # wrapper_deadline_exhausted_4_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03724():
    # wrapper_deadline_exhausted_4_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03725():
    # wrapper_deadline_exhausted_4_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03726():
    # wrapper_deadline_exhausted_4_1 attempt=0
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_1']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03727():
    # wrapper_deadline_exhausted_4_1 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_1']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03728():
    # wrapper_deadline_exhausted_4_1 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_1']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03729():
    # wrapper_deadline_exhausted_4_1 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_1']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03730():
    # wrapper_deadline_exhausted_4_1 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_1']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03731():
    # wrapper_deadline_exhausted_4_1 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_4_1']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03732():
    # wrapper_deadline_exhausted_8_0 attempt=0
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_8_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03733():
    # wrapper_deadline_exhausted_8_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_8_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03734():
    # wrapper_deadline_exhausted_8_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_8_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03735():
    # wrapper_deadline_exhausted_8_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_8_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03736():
    # wrapper_deadline_exhausted_8_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_8_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03737():
    # wrapper_deadline_exhausted_8_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_8_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03738():
    # wrapper_deadline_exhausted_50_0 attempt=0
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_50_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03739():
    # wrapper_deadline_exhausted_50_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_50_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03740():
    # wrapper_deadline_exhausted_50_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_50_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03741():
    # wrapper_deadline_exhausted_50_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_50_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03742():
    # wrapper_deadline_exhausted_50_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_50_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03743():
    # wrapper_deadline_exhausted_50_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_50_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(5) == 2.0


def test_storm_read_03744():
    # wrapper_deadline_exhausted_1000000000_0 attempt=0
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1000000000_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(0) == 0.25


def test_storm_read_03745():
    # wrapper_deadline_exhausted_1000000000_0 attempt=1
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1000000000_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(1) == 0.25


def test_storm_read_03746():
    # wrapper_deadline_exhausted_1000000000_0 attempt=2
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1000000000_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(2) == 0.5


def test_storm_read_03747():
    # wrapper_deadline_exhausted_1000000000_0 attempt=3
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1000000000_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(3) == 1.0


def test_storm_read_03748():
    # wrapper_deadline_exhausted_1000000000_0 attempt=4
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1000000000_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(4) == 2.0


def test_storm_read_03749():
    # wrapper_deadline_exhausted_1000000000_0 attempt=5
    error = _SHAPE_BUILDERS['wrapper_deadline_exhausted_1000000000_0']()
    assert round(bp.persist_restrike_storm_after(error), 6) == 4.0
    assert bp.persist_restrike_delay(5) == 2.0
