#!/usr/bin/env python3
"""Frozen strikeability verdicts for the persist re-strike classifier.

Each cell freezes one verdict of ``persist_loss_is_restrikeable``: every Google API exception class the deployment can raise, the bare builtin transport-timeout family with its ``socket.timeout`` alias and subclass depths, every custody class, the message-independence cross, cause chains whose verdict comes from the raise site alone, and hostile inputs. A failing cell means the classifier drifted from the documented two-family verdict.

Failure-Class: FC-persist-socket-transport-loss-discards-completed-gpu-results
"""

import socket

import pytest

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.firestore_transaction_retry import FirestoreContentionExhausted
from diarizer import batch_pipeline as bp
from diarizer.batch_pipeline import persist_loss_is_restrikeable
from google.api_core import exceptions as gax
from google.api_core.exceptions import GoogleAPIError
from utils.batch_pipeline.audio import StagedAudioInvalid
from utils.batch_pipeline.artifacts import StagedArtifactInvalid
from utils.batch_pipeline.source_audio import InvalidRetainedManifest, RetainedAudioInvalid


class _Depth1(TimeoutError):
    """A transport timeout one subclass deep."""


class _Depth2(_Depth1):
    """A transport timeout two subclasses deep."""


class _TimeoutValueError(TimeoutError, ValueError):
    """A hybrid the MRO resolves through TimeoutError first."""


class _ValueErrorTimeout(ValueError, TimeoutError):
    """A hybrid the MRO resolves through ValueError first."""


class _TimeoutRuntime(TimeoutError, RuntimeError):
    """A timeout hybrid over the wrapper family."""


class _UploadDeadline(TimeoutError):
    """The production stream-deadline fault's own shape."""


def _chained(outer, inner):
    """Raise ``outer`` from a caught ``inner``: a real cause chain."""
    try:
        raise inner
    except Exception as cause:
        raise outer from cause


def _fault_of(maker):
    """Capture the exception ``maker`` raises so cells hold the fault itself."""
    try:
        maker()
    except BaseException as error:
        return error
    raise AssertionError('maker did not raise')


def test_cell_0000():
    assert persist_loss_is_restrikeable(gax.Aborted('grid')) is True


def test_cell_0001():
    assert issubclass(gax.Aborted, GoogleAPIError) is True


def test_cell_0002():
    assert persist_loss_is_restrikeable(gax.AlreadyExists('grid')) is True


def test_cell_0003():
    assert issubclass(gax.AlreadyExists, GoogleAPIError) is True


def test_cell_0004():
    assert persist_loss_is_restrikeable(gax.BadGateway('grid')) is True


def test_cell_0005():
    assert issubclass(gax.BadGateway, GoogleAPIError) is True


def test_cell_0006():
    assert persist_loss_is_restrikeable(gax.BadRequest('grid')) is True


def test_cell_0007():
    assert issubclass(gax.BadRequest, GoogleAPIError) is True


def test_cell_0008():
    assert persist_loss_is_restrikeable(gax.Cancelled('grid')) is True


def test_cell_0009():
    assert issubclass(gax.Cancelled, GoogleAPIError) is True


def test_cell_0010():
    assert persist_loss_is_restrikeable(gax.ClientError('grid')) is True


def test_cell_0011():
    assert issubclass(gax.ClientError, GoogleAPIError) is True


def test_cell_0012():
    assert persist_loss_is_restrikeable(gax.Conflict('grid')) is True


def test_cell_0013():
    assert issubclass(gax.Conflict, GoogleAPIError) is True


def test_cell_0014():
    assert persist_loss_is_restrikeable(gax.DataLoss('grid')) is True


def test_cell_0015():
    assert issubclass(gax.DataLoss, GoogleAPIError) is True


def test_cell_0016():
    assert persist_loss_is_restrikeable(gax.DeadlineExceeded('grid')) is True


def test_cell_0017():
    assert issubclass(gax.DeadlineExceeded, GoogleAPIError) is True


def test_cell_0018():
    assert persist_loss_is_restrikeable(gax.DuplicateCredentialArgs('grid')) is True


def test_cell_0019():
    assert issubclass(gax.DuplicateCredentialArgs, GoogleAPIError) is True


def test_cell_0020():
    assert persist_loss_is_restrikeable(gax.FailedPrecondition('grid')) is True


def test_cell_0021():
    assert issubclass(gax.FailedPrecondition, GoogleAPIError) is True


def test_cell_0022():
    assert persist_loss_is_restrikeable(gax.Forbidden('grid')) is True


def test_cell_0023():
    assert issubclass(gax.Forbidden, GoogleAPIError) is True


def test_cell_0024():
    assert persist_loss_is_restrikeable(gax.GatewayTimeout('grid')) is True


def test_cell_0025():
    assert issubclass(gax.GatewayTimeout, GoogleAPIError) is True


def test_cell_0026():
    assert persist_loss_is_restrikeable(gax.GoogleAPICallError('grid')) is True


def test_cell_0027():
    assert issubclass(gax.GoogleAPICallError, GoogleAPIError) is True


def test_cell_0028():
    assert persist_loss_is_restrikeable(gax.InternalServerError('grid')) is True


def test_cell_0029():
    assert issubclass(gax.InternalServerError, GoogleAPIError) is True


def test_cell_0030():
    assert persist_loss_is_restrikeable(gax.InvalidArgument('grid')) is True


def test_cell_0031():
    assert issubclass(gax.InvalidArgument, GoogleAPIError) is True


def test_cell_0032():
    assert persist_loss_is_restrikeable(gax.LengthRequired('grid')) is True


def test_cell_0033():
    assert issubclass(gax.LengthRequired, GoogleAPIError) is True


def test_cell_0034():
    assert persist_loss_is_restrikeable(gax.MethodNotAllowed('grid')) is True


def test_cell_0035():
    assert issubclass(gax.MethodNotAllowed, GoogleAPIError) is True


def test_cell_0036():
    assert persist_loss_is_restrikeable(gax.MethodNotImplemented('grid')) is True


def test_cell_0037():
    assert issubclass(gax.MethodNotImplemented, GoogleAPIError) is True


def test_cell_0038():
    assert persist_loss_is_restrikeable(gax.MovedPermanently('grid')) is True


def test_cell_0039():
    assert issubclass(gax.MovedPermanently, GoogleAPIError) is True


def test_cell_0040():
    assert persist_loss_is_restrikeable(gax.NotFound('grid')) is True


def test_cell_0041():
    assert issubclass(gax.NotFound, GoogleAPIError) is True


def test_cell_0042():
    assert persist_loss_is_restrikeable(gax.NotModified('grid')) is True


def test_cell_0043():
    assert issubclass(gax.NotModified, GoogleAPIError) is True


def test_cell_0044():
    assert persist_loss_is_restrikeable(gax.OutOfRange('grid')) is True


def test_cell_0045():
    assert issubclass(gax.OutOfRange, GoogleAPIError) is True


def test_cell_0046():
    assert persist_loss_is_restrikeable(gax.PermissionDenied('grid')) is True


def test_cell_0047():
    assert issubclass(gax.PermissionDenied, GoogleAPIError) is True


def test_cell_0048():
    assert persist_loss_is_restrikeable(gax.PreconditionFailed('grid')) is True


def test_cell_0049():
    assert issubclass(gax.PreconditionFailed, GoogleAPIError) is True


def test_cell_0050():
    assert persist_loss_is_restrikeable(gax.Redirection('grid')) is True


def test_cell_0051():
    assert issubclass(gax.Redirection, GoogleAPIError) is True


def test_cell_0052():
    assert persist_loss_is_restrikeable(gax.RequestRangeNotSatisfiable('grid')) is True


def test_cell_0053():
    assert issubclass(gax.RequestRangeNotSatisfiable, GoogleAPIError) is True


def test_cell_0054():
    assert persist_loss_is_restrikeable(gax.ResourceExhausted('grid')) is True


def test_cell_0055():
    assert issubclass(gax.ResourceExhausted, GoogleAPIError) is True


def test_cell_0056():
    assert persist_loss_is_restrikeable(gax.ResumeIncomplete('grid')) is True


def test_cell_0057():
    assert issubclass(gax.ResumeIncomplete, GoogleAPIError) is True


def test_cell_0058():
    assert persist_loss_is_restrikeable(gax.RetryError('grid', None)) is True


def test_cell_0059():
    assert issubclass(gax.RetryError, GoogleAPIError) is True


def test_cell_0060():
    assert persist_loss_is_restrikeable(gax.ServerError('grid')) is True


def test_cell_0061():
    assert issubclass(gax.ServerError, GoogleAPIError) is True


def test_cell_0062():
    assert persist_loss_is_restrikeable(gax.ServiceUnavailable('grid')) is True


def test_cell_0063():
    assert issubclass(gax.ServiceUnavailable, GoogleAPIError) is True


def test_cell_0064():
    assert persist_loss_is_restrikeable(gax.TemporaryRedirect('grid')) is True


def test_cell_0065():
    assert issubclass(gax.TemporaryRedirect, GoogleAPIError) is True


def test_cell_0066():
    assert persist_loss_is_restrikeable(gax.TooManyRequests('grid')) is True


def test_cell_0067():
    assert issubclass(gax.TooManyRequests, GoogleAPIError) is True


def test_cell_0068():
    assert persist_loss_is_restrikeable(gax.Unauthenticated('grid')) is True


def test_cell_0069():
    assert issubclass(gax.Unauthenticated, GoogleAPIError) is True


def test_cell_0070():
    assert persist_loss_is_restrikeable(gax.Unauthorized('grid')) is True


def test_cell_0071():
    assert issubclass(gax.Unauthorized, GoogleAPIError) is True


def test_cell_0072():
    assert persist_loss_is_restrikeable(gax.Unknown('grid')) is True


def test_cell_0073():
    assert issubclass(gax.Unknown, GoogleAPIError) is True


def test_cell_0074():
    assert persist_loss_is_restrikeable(TimeoutError("grid")) is True


def test_cell_0075():
    assert persist_loss_is_restrikeable(socket.timeout("grid")) is True


def test_cell_0076():
    assert persist_loss_is_restrikeable(_Depth1("grid")) is True


def test_cell_0077():
    assert persist_loss_is_restrikeable(_Depth2("grid")) is True


def test_cell_0078():
    assert persist_loss_is_restrikeable(_UploadDeadline("grid")) is True


def test_cell_0079():
    assert persist_loss_is_restrikeable(TimeoutError("batch artifact upload deadline exceeded")) is True


def test_cell_0080():
    assert persist_loss_is_restrikeable(TimeoutError("artifact registration too old to begin upload")) is True


def test_cell_0081():
    assert persist_loss_is_restrikeable(TimeoutError("")) is True


def test_cell_0082():
    assert persist_loss_is_restrikeable(_TimeoutValueError("grid")) is True


def test_cell_0083():
    assert persist_loss_is_restrikeable(_ValueErrorTimeout("grid")) is True


def test_cell_0084():
    assert persist_loss_is_restrikeable(_TimeoutRuntime("grid")) is True


def test_cell_0085():
    assert issubclass(socket.timeout, TimeoutError) is True


def test_cell_0086():
    assert issubclass(TimeoutError, OSError) is True


def test_cell_0087():
    assert persist_loss_is_restrikeable(OSError('disk')) is False


def test_cell_0088():
    assert persist_loss_is_restrikeable(ConnectionError('reset')) is False


def test_cell_0089():
    assert persist_loss_is_restrikeable(BlockingIOError('nonblocking')) is False


def test_cell_0090():
    assert persist_loss_is_restrikeable(StagedAudioInvalid('pinned bytes')) is False


def test_cell_0091():
    assert persist_loss_is_restrikeable(StagedArtifactInvalid('pinned bytes')) is False


def test_cell_0092():
    assert persist_loss_is_restrikeable(RetainedAudioInvalid('pinned bytes')) is False


def test_cell_0093():
    assert persist_loss_is_restrikeable(InvalidRetainedManifest('pinned bytes')) is False


def test_cell_0094():
    assert persist_loss_is_restrikeable(BatchPrivacyBlocked('privacy')) is False


def test_cell_0095():
    assert persist_loss_is_restrikeable(FirestoreContentionExhausted('chain')) is False


def test_cell_0096():
    assert persist_loss_is_restrikeable(bp.DecodedDurationMismatch('mismatch')) is False


def test_cell_0097():
    assert persist_loss_is_restrikeable(ValueError('bounded payload')) is False


def test_cell_0098():
    assert persist_loss_is_restrikeable(PermissionError('policy changed')) is False


def test_cell_0099():
    assert persist_loss_is_restrikeable(KeyError('missing')) is False


def test_cell_0100():
    assert persist_loss_is_restrikeable(TypeError('shape')) is False


def test_cell_0101():
    assert persist_loss_is_restrikeable(RuntimeError('worker')) is False


def test_cell_0102():
    assert persist_loss_is_restrikeable(TimeoutError('timed out')) is True


def test_cell_0103():
    assert persist_loss_is_restrikeable(TimeoutError('transport')) is True


def test_cell_0104():
    assert persist_loss_is_restrikeable(TimeoutError('pinned bytes')) is True


def test_cell_0105():
    assert persist_loss_is_restrikeable(TimeoutError('policy changed')) is True


def test_cell_0106():
    assert persist_loss_is_restrikeable(TimeoutError('InvalidArgument')) is True


def test_cell_0107():
    assert persist_loss_is_restrikeable(TimeoutError('TimeoutError')) is True


def test_cell_0108():
    assert persist_loss_is_restrikeable(TimeoutError('')) is True


def test_cell_0109():
    assert persist_loss_is_restrikeable(gax.InternalServerError('timed out')) is True


def test_cell_0110():
    assert persist_loss_is_restrikeable(gax.InternalServerError('transport')) is True


def test_cell_0111():
    assert persist_loss_is_restrikeable(gax.InternalServerError('pinned bytes')) is True


def test_cell_0112():
    assert persist_loss_is_restrikeable(gax.InternalServerError('policy changed')) is True


def test_cell_0113():
    assert persist_loss_is_restrikeable(gax.InternalServerError('InvalidArgument')) is True


def test_cell_0114():
    assert persist_loss_is_restrikeable(gax.InternalServerError('TimeoutError')) is True


def test_cell_0115():
    assert persist_loss_is_restrikeable(gax.InternalServerError('')) is True


def test_cell_0116():
    assert persist_loss_is_restrikeable(gax.InvalidArgument('timed out')) is True


def test_cell_0117():
    assert persist_loss_is_restrikeable(gax.InvalidArgument('transport')) is True


def test_cell_0118():
    assert persist_loss_is_restrikeable(gax.InvalidArgument('pinned bytes')) is True


def test_cell_0119():
    assert persist_loss_is_restrikeable(gax.InvalidArgument('policy changed')) is True


def test_cell_0120():
    assert persist_loss_is_restrikeable(gax.InvalidArgument('InvalidArgument')) is True


def test_cell_0121():
    assert persist_loss_is_restrikeable(gax.InvalidArgument('TimeoutError')) is True


def test_cell_0122():
    assert persist_loss_is_restrikeable(gax.InvalidArgument('')) is True


def test_cell_0123():
    assert persist_loss_is_restrikeable(ValueError('timed out')) is False


def test_cell_0124():
    assert persist_loss_is_restrikeable(ValueError('transport')) is False


def test_cell_0125():
    assert persist_loss_is_restrikeable(ValueError('pinned bytes')) is False


def test_cell_0126():
    assert persist_loss_is_restrikeable(ValueError('policy changed')) is False


def test_cell_0127():
    assert persist_loss_is_restrikeable(ValueError('InvalidArgument')) is False


def test_cell_0128():
    assert persist_loss_is_restrikeable(ValueError('TimeoutError')) is False


def test_cell_0129():
    assert persist_loss_is_restrikeable(ValueError('')) is False


def test_cell_0130():
    assert persist_loss_is_restrikeable(gax.ServiceUnavailable('timed out')) is True


def test_cell_0131():
    assert persist_loss_is_restrikeable(gax.ServiceUnavailable('transport')) is True


def test_cell_0132():
    assert persist_loss_is_restrikeable(gax.ServiceUnavailable('pinned bytes')) is True


def test_cell_0133():
    assert persist_loss_is_restrikeable(gax.ServiceUnavailable('policy changed')) is True


def test_cell_0134():
    assert persist_loss_is_restrikeable(gax.ServiceUnavailable('InvalidArgument')) is True


def test_cell_0135():
    assert persist_loss_is_restrikeable(gax.ServiceUnavailable('TimeoutError')) is True


def test_cell_0136():
    assert persist_loss_is_restrikeable(gax.ServiceUnavailable('')) is True


def test_cell_0137():
    assert persist_loss_is_restrikeable(PermissionError('timed out')) is False


def test_cell_0138():
    assert persist_loss_is_restrikeable(PermissionError('transport')) is False


def test_cell_0139():
    assert persist_loss_is_restrikeable(PermissionError('pinned bytes')) is False


def test_cell_0140():
    assert persist_loss_is_restrikeable(PermissionError('policy changed')) is False


def test_cell_0141():
    assert persist_loss_is_restrikeable(PermissionError('InvalidArgument')) is False


def test_cell_0142():
    assert persist_loss_is_restrikeable(PermissionError('TimeoutError')) is False


def test_cell_0143():
    assert persist_loss_is_restrikeable(PermissionError('')) is False


def test_cell_0144():
    assert (
        persist_loss_is_restrikeable(
            _fault_of(lambda: _chained(TimeoutError("outer"), gax.InternalServerError("inner")))
        )
        is True
    )


def test_cell_0145():
    assert (
        persist_loss_is_restrikeable(
            _fault_of(lambda: _chained(gax.ServiceUnavailable("outer"), TimeoutError("inner")))
        )
        is True
    )


def test_cell_0146():
    assert (
        persist_loss_is_restrikeable(_fault_of(lambda: _chained(ValueError("custody"), TimeoutError("inner")))) is False
    )


def test_cell_0147():
    assert (
        persist_loss_is_restrikeable(_fault_of(lambda: _chained(TimeoutError("outer"), ValueError("custody")))) is True
    )


def test_cell_0148():
    assert (
        persist_loss_is_restrikeable(_fault_of(lambda: _chained(RuntimeError("wrapper"), gax.Aborted("inner"))))
        is False
    )


def test_cell_0149():
    assert (
        persist_loss_is_restrikeable(
            _fault_of(lambda: _chained(FirestoreContentionExhausted("chain"), gax.Aborted("inner")))
        )
        is False
    )


def test_cell_0150():
    assert persist_loss_is_restrikeable(None) is False


def test_cell_0151():
    assert persist_loss_is_restrikeable(True) is False


def test_cell_0152():
    assert persist_loss_is_restrikeable(False) is False


def test_cell_0153():
    assert persist_loss_is_restrikeable(7) is False


def test_cell_0154():
    assert persist_loss_is_restrikeable("TimeoutError") is False


def test_cell_0155():
    assert persist_loss_is_restrikeable(b"timeout") is False


def test_cell_0156():
    assert persist_loss_is_restrikeable([TimeoutError("grid")]) is False


def test_cell_0157():
    assert persist_loss_is_restrikeable({"e": TimeoutError("grid")}) is False


def test_cell_0158():
    assert persist_loss_is_restrikeable(object()) is False


def test_cell_0159():
    assert persist_loss_is_restrikeable(BaseException("grid")) is False


def test_cell_0160():
    assert persist_loss_is_restrikeable(Exception("grid")) is False


def test_cell_0161():
    assert persist_loss_is_restrikeable(type) is False
