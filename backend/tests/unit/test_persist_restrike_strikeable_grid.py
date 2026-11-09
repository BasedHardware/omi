#!/usr/bin/env python3
"""Strikeable-loss classification grid for the worker persist re-strike lane.

Only the Google API transport family classifies as a re-strikeable persist loss; every
typed custody fault, privacy fence, policy refusal, upload deadline, programmer fault and
the register contention wrapper stays non-strikeable so replaying it can never paper over
a real refusal. This grid pins the classifier class by class.

Failure-Class: FC-persist-transport-loss-discards-completed-gpu-results
"""

import logging
from contextlib import nullcontext
from dataclasses import replace

import pytest
from google.api_core.exceptions import (
    Aborted,
    BadRequest,
    Cancelled,
    Conflict,
    DeadlineExceeded,
    FailedPrecondition,
    Forbidden,
    GoogleAPIError,
    InternalServerError,
    InvalidArgument,
    NotFound,
    PreconditionFailed,
    ResourceExhausted,
    RetryError,
    ServiceUnavailable,
    Unauthenticated,
    Unknown,
)
from config.batch_pipeline import Priority
from diarizer import batch_pipeline as bp
from diarizer.batch_pipeline import PipelineWorker
from utils.batch_pipeline.contracts import FailedWork, WorkItem, WorkResult
from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason

try:
    from diarizer.batch_pipeline import (
        PERSIST_RESTRIKE_BASE_SECONDS,
        PERSIST_RESTRIKE_MAX_ATTEMPTS,
        PERSIST_RESTRIKE_MAX_SECONDS,
        persist_loss_is_restrikeable,
        persist_restrike_delay,
    )
except ImportError:  # the lane is this suite's subject; the parent fails at runtime (the RED half)
    pass


from utils.batch_pipeline.audio import StagedAudioInvalid
from utils.batch_pipeline.artifacts import StagedArtifactInvalid
from utils.batch_pipeline.source_audio import InvalidRetainedManifest, RetainedAudioInvalid
from database.firestore_transaction_retry import FirestoreContentionExhausted

GOOGLE_INSTANCES = (
    InvalidArgument('transport'),
    BadRequest('transport'),
    ServiceUnavailable('transport'),
    InternalServerError('transport'),
    DeadlineExceeded('transport'),
    ResourceExhausted('transport'),
    NotFound('transport'),
    Conflict('transport'),
    Aborted('transport'),
    Cancelled('transport'),
    FailedPrecondition('transport'),
    Forbidden('transport'),
    PreconditionFailed('transport'),
    Unauthenticated('transport'),
    Unknown('transport'),
    RetryError('transport', None),
)


class CustomGoogleFault(GoogleAPIError):
    """A deployment-local Google API subclass: the family decides, not the name."""


class CustomGoogleGrandchild(CustomGoogleFault):
    pass


class NonGoogleLookalike(ValueError):
    """A ValueError that merely carries a Google-ish message is still custody."""


CUSTODY_EXCEPTIONS = (
    StagedAudioInvalid('pinned bytes'),
    StagedArtifactInvalid('pinned bytes'),
    RetainedAudioInvalid('pinned bytes'),
    InvalidRetainedManifest('pinned bytes'),
    bp.DecodedDurationMismatch('decoded duration differs from admitted capture'),
    BatchValidationError(ValidationReason.VAD_BOUNDS),
    BatchValidationError(ValidationReason.UNSUPPORTED_LANGUAGE),
    ValueError('bounded artifact identity required'),
    TimeoutError('batch artifact upload deadline exceeded'),
    PermissionError('batch artifact policy changed during IO'),
    FirestoreContentionExhausted('register contention exhausted'),
    OSError('disk'),
    RuntimeError('worker'),
    KeyError('missing'),
    TypeError('bad shape'),
)


def test_aborted_joins_the_google_transport_family():
    assert issubclass(Aborted, GoogleAPIError) is True


def test_aborted_instance_is_restrikeable():
    assert persist_loss_is_restrikeable(Aborted('transport')) is True


def test_badrequest_joins_the_google_transport_family():
    assert issubclass(BadRequest, GoogleAPIError) is True


def test_badrequest_instance_is_restrikeable():
    assert persist_loss_is_restrikeable(BadRequest('transport')) is True


def test_cancelled_joins_the_google_transport_family():
    assert issubclass(Cancelled, GoogleAPIError) is True


def test_cancelled_instance_is_restrikeable():
    assert persist_loss_is_restrikeable(Cancelled('transport')) is True


def test_conflict_joins_the_google_transport_family():
    assert issubclass(Conflict, GoogleAPIError) is True


def test_conflict_instance_is_restrikeable():
    assert persist_loss_is_restrikeable(Conflict('transport')) is True


def test_deadlineexceeded_joins_the_google_transport_family():
    assert issubclass(DeadlineExceeded, GoogleAPIError) is True


def test_deadlineexceeded_instance_is_restrikeable():
    assert persist_loss_is_restrikeable(DeadlineExceeded('transport')) is True


def test_failedprecondition_joins_the_google_transport_family():
    assert issubclass(FailedPrecondition, GoogleAPIError) is True


def test_failedprecondition_instance_is_restrikeable():
    assert persist_loss_is_restrikeable(FailedPrecondition('transport')) is True


def test_forbidden_joins_the_google_transport_family():
    assert issubclass(Forbidden, GoogleAPIError) is True


def test_forbidden_instance_is_restrikeable():
    assert persist_loss_is_restrikeable(Forbidden('transport')) is True


def test_googleapierror_joins_the_google_transport_family():
    assert issubclass(GoogleAPIError, GoogleAPIError) is True


def test_googleapierror_instance_is_restrikeable():
    assert persist_loss_is_restrikeable(GoogleAPIError('transport')) is True


def test_internalservererror_joins_the_google_transport_family():
    assert issubclass(InternalServerError, GoogleAPIError) is True


def test_internalservererror_instance_is_restrikeable():
    assert persist_loss_is_restrikeable(InternalServerError('transport')) is True


def test_invalidargument_joins_the_google_transport_family():
    assert issubclass(InvalidArgument, GoogleAPIError) is True


def test_invalidargument_instance_is_restrikeable():
    assert persist_loss_is_restrikeable(InvalidArgument('transport')) is True


def test_notfound_joins_the_google_transport_family():
    assert issubclass(NotFound, GoogleAPIError) is True


def test_notfound_instance_is_restrikeable():
    assert persist_loss_is_restrikeable(NotFound('transport')) is True


def test_preconditionfailed_joins_the_google_transport_family():
    assert issubclass(PreconditionFailed, GoogleAPIError) is True


def test_preconditionfailed_instance_is_restrikeable():
    assert persist_loss_is_restrikeable(PreconditionFailed('transport')) is True


def test_resourceexhausted_joins_the_google_transport_family():
    assert issubclass(ResourceExhausted, GoogleAPIError) is True


def test_resourceexhausted_instance_is_restrikeable():
    assert persist_loss_is_restrikeable(ResourceExhausted('transport')) is True


def test_retryerror_joins_the_google_transport_family():
    assert issubclass(RetryError, GoogleAPIError) is True


def test_retryerror_instance_is_restrikeable():
    assert persist_loss_is_restrikeable(RetryError('transport', None)) is True


def test_serviceunavailable_joins_the_google_transport_family():
    assert issubclass(ServiceUnavailable, GoogleAPIError) is True


def test_serviceunavailable_instance_is_restrikeable():
    assert persist_loss_is_restrikeable(ServiceUnavailable('transport')) is True


def test_unauthenticated_joins_the_google_transport_family():
    assert issubclass(Unauthenticated, GoogleAPIError) is True


def test_unauthenticated_instance_is_restrikeable():
    assert persist_loss_is_restrikeable(Unauthenticated('transport')) is True


def test_unknown_joins_the_google_transport_family():
    assert issubclass(Unknown, GoogleAPIError) is True


def test_unknown_instance_is_restrikeable():
    assert persist_loss_is_restrikeable(Unknown('transport')) is True


def test_custom_google_subclass_is_restrikeable():
    assert persist_loss_is_restrikeable(CustomGoogleFault('x')) is True


def test_custom_google_grandchild_is_restrikeable():
    assert persist_loss_is_restrikeable(CustomGoogleGrandchild('x')) is True


def test_nongoogle_lookalike_stays_custody():
    assert persist_loss_is_restrikeable(NonGoogleLookalike('InvalidArgument')) is False


def test_the_classifier_reads_the_class_not_the_message():
    assert persist_loss_is_restrikeable(ValueError('InvalidArgument')) is False
    assert persist_loss_is_restrikeable(InvalidArgument('ValueError')) is True


def test_a_google_cause_chain_alone_does_not_make_a_fault_strikeable():
    # Unlike the pump contention classifier, the persist classifier never walks a cause chain:
    # the raise site decides, so wrapped custody faults stay custody.
    try:
        try:
            raise InvalidArgument('cause only')
        except InvalidArgument as cause:
            raise ValueError('custody') from cause
    except ValueError as wrapped:
        assert persist_loss_is_restrikeable(wrapped) is False


def test_custody_member_00_staged_audio_invalid_stays_non_strikeable():
    assert persist_loss_is_restrikeable(CUSTODY_EXCEPTIONS[0]) is False


def test_custody_member_01_staged_artifact_invalid_stays_non_strikeable():
    assert persist_loss_is_restrikeable(CUSTODY_EXCEPTIONS[1]) is False


def test_custody_member_02_retained_audio_invalid_stays_non_strikeable():
    assert persist_loss_is_restrikeable(CUSTODY_EXCEPTIONS[2]) is False


def test_custody_member_03_invalid_retained_manifest_stays_non_strikeable():
    assert persist_loss_is_restrikeable(CUSTODY_EXCEPTIONS[3]) is False


def test_custody_member_04_decoded_duration_mismatch_stays_non_strikeable():
    assert persist_loss_is_restrikeable(CUSTODY_EXCEPTIONS[4]) is False


def test_custody_member_05_batch_validation_vad_bounds_stays_non_strikeable():
    assert persist_loss_is_restrikeable(CUSTODY_EXCEPTIONS[5]) is False


def test_custody_member_06_batch_validation_unsupported_language_stays_non_strikeable():
    assert persist_loss_is_restrikeable(CUSTODY_EXCEPTIONS[6]) is False


def test_custody_member_07_bounded_payload_value_error_stays_non_strikeable():
    assert persist_loss_is_restrikeable(CUSTODY_EXCEPTIONS[7]) is False


def test_custody_member_08_upload_deadline_timeout_stays_non_strikeable():
    assert persist_loss_is_restrikeable(CUSTODY_EXCEPTIONS[8]) is False


def test_custody_member_09_policy_changed_permission_stays_non_strikeable():
    assert persist_loss_is_restrikeable(CUSTODY_EXCEPTIONS[9]) is False


def test_custody_member_10_register_contention_exhausted_stays_non_strikeable():
    assert persist_loss_is_restrikeable(CUSTODY_EXCEPTIONS[10]) is False


def test_custody_member_11_os_error_stays_non_strikeable():
    assert persist_loss_is_restrikeable(CUSTODY_EXCEPTIONS[11]) is False


def test_custody_member_12_runtime_error_stays_non_strikeable():
    assert persist_loss_is_restrikeable(CUSTODY_EXCEPTIONS[12]) is False


def test_custody_member_13_key_error_stays_non_strikeable():
    assert persist_loss_is_restrikeable(CUSTODY_EXCEPTIONS[13]) is False


def test_custody_member_14_type_error_stays_non_strikeable():
    assert persist_loss_is_restrikeable(CUSTODY_EXCEPTIONS[14]) is False


def test_every_custody_member_is_verified_non_strikeable():
    assert len(CUSTODY_EXCEPTIONS) == 15


def test_the_google_family_is_the_whole_verdict_for_the_lane():
    # The classifier is exactly one isinstance; nothing else can flip a verdict.
    import inspect

    source = inspect.getsource(bp.persist_loss_is_restrikeable)
    assert 'isinstance(error, GoogleAPIError)' in source
    assert source.count('return') == 1
