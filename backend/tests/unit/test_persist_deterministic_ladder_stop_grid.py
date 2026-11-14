#!/usr/bin/env python3
"""The persist boundary's classification matrix, cell by cell.

Every fault class the persist boundary can raise, against both re-strike
gate states, with the full booking tuple (persist calls, sleeps, result
shape, evidence) asserted per cell — so a new fault class cannot silently
rejoin the ladder or silently lose its lane. The disposition verdict
matrix re-derives every closed (stage, reason) pair's channel from an
independent expected-verdict table, so the demotion arms cannot drift from
the vocabulary that feeds them.

Failure-Class: FC-deterministic-persist-refusal-walks-gpu-retry-ladder-as-unclassified-invalidargument
"""

import pytest
from google.api_core.exceptions import (
    Aborted,
    BadRequest,
    Conflict,
    DeadlineExceeded,
    Forbidden,
    InternalServerError,
    InvalidArgument,
    NotFound,
    PreconditionFailed,
    ServiceUnavailable,
)

from database.firestore_transaction_retry import FirestoreContentionExhausted
from diarizer import batch_pipeline as bp
from utils.batch_pipeline.errors import (
    WORKER_VALIDATION_REASONS,
    WORKER_VALIDATION_STAGES,
    validation_disposition_failure,
)
from utils.observability.reasons import WorkerValidationReason, WorkerValidationStage, reason_values
from tests.unit.persist_lane_harness import (
    PerSegmentPersist,
    ScriptedPersist,
    run_lane,
    run_two_units,
)

FC = 'FC-deterministic-persist-refusal-walks-gpu-retry-ladder-as-unclassified-invalidargument'

EXPIRY = '400 The referenced transaction has expired or is no longer valid'


def _classes():
    return {
        'invalid_argument': InvalidArgument,
        'invalid_argument_expiry': lambda message: InvalidArgument(EXPIRY),
        'bad_request': BadRequest,
        'conflict': Conflict,
        'deadline_exceeded': DeadlineExceeded,
        'forbidden': Forbidden,
        'internal_server': InternalServerError,
        'not_found': NotFound,
        'precondition_failed': PreconditionFailed,
        'service_unavailable': ServiceUnavailable,
        'aborted': Aborted,
        'timeout': TimeoutError,
        'contention_exhausted': lambda message: FirestoreContentionExhausted(message),
        'os_error': OSError,
        'value_error': ValueError,
    }


EXPECTED_EXHAUST_BOOKING = {
    # The deterministic refusal: typed custody handoff, chain ends here.
    'invalid_argument': 'ValidationFailureWork',
    # The expired-chain shape and the transport/contention families keep the
    # legacy retryable booking (FailedWork under the safety net).
    'invalid_argument_expiry': 'FailedWork',
    'bad_request': 'FailedWork',
    'conflict': 'FailedWork',
    'deadline_exceeded': 'FailedWork',
    'forbidden': 'FailedWork',
    'internal_server': 'FailedWork',
    'not_found': 'FailedWork',
    'precondition_failed': 'FailedWork',
    'service_unavailable': 'FailedWork',
    'aborted': 'FailedWork',
    'timeout': 'FailedWork',
    'contention_exhausted': 'FailedWork',
    'os_error': 'FailedWork',
    'value_error': 'FailedWork',
}


@pytest.mark.parametrize('label', sorted(_classes()))
@pytest.mark.parametrize('gate', ['true', 'false'])
def test_exhaust_booking_matrix(label, gate, monkeypatch):
    fault_class = _classes()[label]
    build = (
        fault_class
        if label == 'invalid_argument_expiry' or label == 'contention_exhausted'
        else lambda message: fault_class(message)
    )
    run = run_lane(
        monkeypatch, ScriptedPersist([build('burst')] * 3, default=build('burst')), gate=gate, safety_net='true'
    )
    expected = EXPECTED_EXHAUST_BOOKING[label]
    assert [type(r).__name__ for r in run['results']] == [expected]
    if expected == 'ValidationFailureWork':
        assert run['results'][0].stage == 'persist'
        assert run['results'][0].reason == 'persist_payload_invalid'
    else:
        assert run['results'][0].worker_failure == {'stage': 'persist', 'reason': 'unknown'}
    assert run['meta']['failures'] and run['meta']['failures'][0][0] == 'a'


@pytest.mark.parametrize('label', sorted(_classes()))
def test_first_call_economics_with_the_gate_off(label, monkeypatch):
    fault_class = _classes()[label]
    build = (
        fault_class
        if label in ('invalid_argument_expiry', 'contention_exhausted')
        else lambda message: fault_class(message)
    )
    run = run_lane(
        monkeypatch, ScriptedPersist([build('burst')], default=build('burst')), gate='false', safety_net='true'
    )
    # The gate off means one persist call and no sleeps for every class;
    # the booking then follows the same deterministic/legacy split.
    assert len(run['persist'].calls) == 1 and run['sleeps'].delays == []
    expected = EXPECTED_EXHAUST_BOOKING[label]
    assert [type(r).__name__ for r in run['results']] == [expected]


@pytest.mark.parametrize(
    'label', ['invalid_argument', 'invalid_argument_expiry', 'timeout', 'internal_server', 'contention_exhausted']
)
def test_single_strike_recovery_commits_for_every_replayable_family(label, monkeypatch):
    fault_class = _classes()[label]
    build = (
        fault_class
        if label in ('invalid_argument_expiry', 'contention_exhausted')
        else lambda message: fault_class(message)
    )
    run = run_lane(monkeypatch, ScriptedPersist([build('burst')], default='OK'))
    assert [type(r).__name__ for r in run['results']] == ['WorkResult']
    assert len(run['sleeps'].delays) == 1


# --- Classifier verdict matrix -----------------------------------------------------


@pytest.mark.parametrize(
    'label',
    [
        'invalid_argument',
        'invalid_argument_expiry',
        'invalid_argument_case_variant',
        'invalid_argument_cause_aborted',
        'bad_request',
        'conflict',
        'deadline_exceeded',
        'forbidden',
        'internal_server',
        'not_found',
        'precondition_failed',
        'service_unavailable',
        'aborted',
        'timeout',
        'contention_exhausted',
        'os_error',
        'value_error',
        'batch_validation_error',
    ],
)
def test_classifier_verdict_matrix(label):
    expiry = InvalidArgument(EXPIRY)
    case_variant = InvalidArgument('Please Transaction Has Expired Already')
    try:
        try:
            raise Aborted('row locked')
        except Aborted as cause:
            raise InvalidArgument('refused mid-flight') from cause
    except InvalidArgument as caused:
        cause_chain = caused
    faults = {
        'invalid_argument': InvalidArgument('payload refusal'),
        'invalid_argument_expiry': expiry,
        'invalid_argument_case_variant': case_variant,
        'invalid_argument_cause_aborted': cause_chain,
        'bad_request': BadRequest('bad'),
        'conflict': Conflict('conflict'),
        'deadline_exceeded': DeadlineExceeded('late'),
        'forbidden': Forbidden('no'),
        'internal_server': InternalServerError('boom'),
        'not_found': NotFound('gone'),
        'precondition_failed': PreconditionFailed('no'),
        'service_unavailable': ServiceUnavailable('later'),
        'aborted': Aborted('row locked'),
        'timeout': TimeoutError('late'),
        'contention_exhausted': FirestoreContentionExhausted('storm'),
        'os_error': OSError('socket'),
        'value_error': ValueError('bad'),
        'batch_validation_error': (
            bp.BatchValidationError(bp.ValidationReason.WORD_CLOCK)
            if hasattr(bp, 'BatchValidationError')
            else _batch_validation_error()
        ),
    }
    expected = {
        'invalid_argument': True,
        'invalid_argument_expiry': False,
        'invalid_argument_case_variant': False,
        'invalid_argument_cause_aborted': False,
    }
    verdict = bp.persist_loss_is_deterministic(faults[label])
    assert verdict is expected.get(label, False), label


def _batch_validation_error():
    from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason

    return BatchValidationError(ValidationReason.WORD_CLOCK)


@pytest.mark.parametrize('hostile', [None, 7, 'burst', True, 0.5, object()])
def test_classifier_never_raises_on_hostile_input(hostile):
    assert bp.persist_loss_is_deterministic(hostile) is False


# --- Disposition verdict matrix (independent expected table) ------------------------

STAGES = sorted(reason_values(WorkerValidationStage))
REASONS = sorted(reason_values(WorkerValidationReason))

TRIO = {'staged_audio_invalid', 'retained_audio_invalid', 'decoded_duration_mismatch'}
FLAGGED = {'vad_nonfinite', 'vad_order', 'vad_bounds', 'word_shape', 'word_clock', 'word_sequence'}


def _expected_disposition(stage, reason, disposition_enabled):
    if stage == 'fetch_decode' and reason in TRIO:
        return True
    if stage == 'persist' and reason == 'persist_payload_invalid':
        return True
    return bool(disposition_enabled) and reason in FLAGGED and stage in WORKER_VALIDATION_STAGES


@pytest.mark.parametrize('disposition_enabled', [False, True])
@pytest.mark.parametrize('reason', REASONS)
@pytest.mark.parametrize('stage', STAGES)
def test_disposition_verdict_matrix(stage, reason, disposition_enabled):
    verdict = validation_disposition_failure(
        {'stage': stage, 'reason': reason}, disposition_enabled=disposition_enabled
    )
    assert verdict is _expected_disposition(stage, reason, disposition_enabled), (stage, reason, disposition_enabled)


def test_the_matrix_axes_match_the_closed_vocabularies():
    assert len(STAGES) == len(WORKER_VALIDATION_STAGES)
    assert set(REASONS) == set(WORKER_VALIDATION_REASONS)


# --- Sibling-independence cells across the matrix -----------------------------------


@pytest.mark.parametrize('label', ['invalid_argument', 'invalid_argument_expiry', 'timeout'])
def test_an_exhausted_unit_never_poisons_its_sibling(label, monkeypatch):
    fault_class = _classes()[label]
    build = fault_class if label == 'invalid_argument_expiry' else lambda message: fault_class(message)
    routes = PerSegmentPersist(
        {'a': ScriptedPersist([build('burst')] * 3, default=build('burst')), 'b': ScriptedPersist([])}
    )
    run = run_two_units(monkeypatch, routes)
    names = [(r.segment_id, type(r).__name__) for r in run['results']]
    # The sibling always commits; the exhausted unit's booking follows the
    # deterministic/legacy split and never takes b's entry with it.
    assert names[-1] == ('b', 'WorkResult')
    if label == 'invalid_argument':
        assert names[0] == ('a', 'ValidationFailureWork')
    else:
        assert all(segment != 'a' for segment, _ in names)
    assert run['worker'].counts['items'] == 2
