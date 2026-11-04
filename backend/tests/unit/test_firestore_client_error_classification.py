"""Branch-level contracts of the Firestore boundary's error classifiers.

``database._client`` hosts the predicates every persistence retry budget composes
(``is_expired_transaction_error``, ``is_document_size_limit_error``,
``is_permanent_firestore_write_rejection``, ``firestore_failure_reason``,
``is_retryable_firestore_transaction_error``, the rejected-document path/kind
extraction, and ``run_transactional`` itself) plus the utils-tree availability
classifier it re-exports. These tests pin each classifier's branch table and the
restart semantics of ``run_transactional`` directly on fakes, so a future import
or branch regression cannot silently reclassify a permanent write refusal as a
retryable transient (or vice versa) without failing here first.

Deepening of the PR #24592 review-response batch (import-surface consolidation
in ``database._client``); the classification behavior itself is unchanged.
"""

from __future__ import annotations

from typing import Any, Callable, List

from google.api_core.exceptions import (
    Aborted,
    DeadlineExceeded,
    InternalServerError,
    InvalidArgument,
    PermissionDenied,
    ResourceExhausted,
    RetryError,
    ServiceUnavailable,
)

from database import _client
from database.firestore_transaction_retry import (
    FirestoreAborted,
    FirestoreContentionExhausted,
    equal_jitter_delay,
)
from utils.firestore_transient_types import is_transient_availability_error

EXPIRED = '400 The referenced transaction has expired or is no longer valid.'
SIZE_LIMIT = 'the document exceeds the maximum allowed size'
COMMIT_EXHAUSTED = 'failed to commit transaction: too much contention'


# ---------------------------------------------------------------------------
# Expired transaction id (the InvalidArgument/Aborted dual shape).
# ---------------------------------------------------------------------------


def test_expired_invalid_argument_is_recognized():
    assert _client.is_expired_transaction_error(InvalidArgument(EXPIRED)) is True


def test_expired_abort_is_recognized():
    assert _client.is_expired_transaction_error(Aborted(f'409 {EXPIRED}')) is True


def test_expired_marker_is_case_insensitive():
    assert _client.is_expired_transaction_error(InvalidArgument('400 The Transaction HAS EXPIRED mid-flight.')) is True


def test_other_invalid_argument_is_not_expired():
    assert _client.is_expired_transaction_error(InvalidArgument('bad filter')) is False


def test_wrong_type_with_expired_marker_is_not_expired():
    assert _client.is_expired_transaction_error(ServiceUnavailable(EXPIRED)) is False


# ---------------------------------------------------------------------------
# Document size limit (the permanent volume refusal).
# ---------------------------------------------------------------------------


def test_document_size_limit_is_recognized():
    assert _client.is_document_size_limit_error(InvalidArgument(SIZE_LIMIT)) is True


def test_document_size_marker_is_case_insensitive():
    assert _client.is_document_size_limit_error(InvalidArgument('EXCEEDS THE MAXIMUM ALLOWED SIZE')) is True


def test_other_invalid_argument_is_not_a_size_limit():
    assert _client.is_document_size_limit_error(InvalidArgument('bad path')) is False


def test_abort_is_not_a_size_limit():
    assert _client.is_document_size_limit_error(Aborted('contention')) is False


# ---------------------------------------------------------------------------
# Permanent write rejections (retry can never fix these).
# ---------------------------------------------------------------------------


def test_size_limit_is_permanent():
    assert _client.is_permanent_firestore_write_rejection(InvalidArgument(SIZE_LIMIT)) is True


def test_permission_denied_message_is_permanent():
    assert _client.is_permanent_firestore_write_rejection(InvalidArgument('permission denied on row')) is True


def test_request_must_be_modified_is_permanent():
    assert _client.is_permanent_firestore_write_rejection(InvalidArgument('the request must be modified')) is True


def test_caller_permission_message_is_permanent():
    assert _client.is_permanent_firestore_write_rejection(InvalidArgument('caller does not have permission')) is True


def test_forbidden_for_message_is_permanent():
    assert _client.is_permanent_firestore_write_rejection(InvalidArgument('writes forbidden for policy')) is True


def test_contention_abort_is_not_permanent():
    assert _client.is_permanent_firestore_write_rejection(Aborted('contention on users/u1')) is False


def test_unavailable_is_not_permanent():
    assert _client.is_permanent_firestore_write_rejection(ServiceUnavailable('503')) is False


def test_expired_transaction_is_not_permanent():
    assert _client.is_permanent_firestore_write_rejection(InvalidArgument(EXPIRED)) is False


def test_plain_invalid_argument_is_not_permanent():
    assert _client.is_permanent_firestore_write_rejection(InvalidArgument('bad argument')) is False


# ---------------------------------------------------------------------------
# firestore_failure_reason's branch table.
# ---------------------------------------------------------------------------


def test_reason_for_document_size_limit():
    assert _client.firestore_failure_reason(InvalidArgument(SIZE_LIMIT)) == 'document_size_limit'


def test_reason_for_expired_transaction():
    assert _client.firestore_failure_reason(InvalidArgument(EXPIRED)) == 'expired_transaction'


def test_reason_for_wrapped_contention_abort():
    assert _client.firestore_failure_reason(FirestoreAborted('contention')) == 'contention'


def test_reason_for_contention_exhaustion():
    assert _client.firestore_failure_reason(FirestoreContentionExhausted('attempts_exhausted')) == 'contention'


def test_reason_for_sdk_commit_exhausted_value_error():
    assert _client.firestore_failure_reason(ValueError(COMMIT_EXHAUSTED)) == 'contention'


def test_reason_for_deadline_exceeded():
    assert _client.firestore_failure_reason(DeadlineExceeded('504')) == 'deadline_exceeded'


def test_reason_for_unavailable():
    assert _client.firestore_failure_reason(ServiceUnavailable('503')) == 'unavailable'


def test_reason_for_resource_exhausted():
    assert _client.firestore_failure_reason(ResourceExhausted('429')) == 'resource_exhausted'


def test_reason_for_raw_google_abort_is_contention():
    # ``FirestoreAborted`` aliases google's Aborted, so the reason table claims
    # the raw read-path abort as contention; the outer contention budget is
    # what replays it.
    assert _client.firestore_failure_reason(Aborted('contention')) == 'contention'


def test_reason_for_unknown_error_is_other():
    assert _client.firestore_failure_reason(RuntimeError('boom')) == 'other'


def test_document_size_takes_precedence_over_expired_marker():
    both = InvalidArgument(f'{SIZE_LIMIT}; {EXPIRED}')
    assert _client.firestore_failure_reason(both) == 'document_size_limit'


# ---------------------------------------------------------------------------
# is_retryable_firestore_transaction_error (composes both, walks the cause).
# ---------------------------------------------------------------------------


def test_expired_transaction_is_retryable():
    assert _client.is_retryable_firestore_transaction_error(InvalidArgument(EXPIRED)) is True


def test_unavailable_is_retryable():
    assert _client.is_retryable_firestore_transaction_error(ServiceUnavailable('503')) is True


def test_deadline_exceeded_is_retryable():
    assert _client.is_retryable_firestore_transaction_error(DeadlineExceeded('504')) is True


def test_resource_exhausted_is_retryable():
    assert _client.is_retryable_firestore_transaction_error(ResourceExhausted('429')) is True


def test_contention_exhaustion_is_retryable():
    assert _client.is_retryable_firestore_transaction_error(FirestoreContentionExhausted('attempts_exhausted')) is True


def test_sdk_commit_exhausted_value_error_is_retryable():
    assert _client.is_retryable_firestore_transaction_error(ValueError(COMMIT_EXHAUSTED)) is True


def test_transient_cause_is_reached_through_the_chain():
    wrapper = RuntimeError('commit envelope')
    wrapper.__cause__ = ServiceUnavailable('503')
    assert _client.is_retryable_firestore_transaction_error(wrapper) is True


def test_expired_cause_two_levels_deep_is_retryable():
    inner = Aborted(EXPIRED)
    middle = RuntimeError('wrapped')
    middle.__cause__ = inner
    outer = RuntimeError('envelope')
    outer.__cause__ = middle
    assert _client.is_retryable_firestore_transaction_error(outer) is True


def test_permanent_write_wins_over_a_retryable_cause():
    error = InvalidArgument(SIZE_LIMIT)
    error.__cause__ = ServiceUnavailable('503')
    assert _client.is_retryable_firestore_transaction_error(error) is False


def test_self_referential_cause_chain_terminates():
    error = RuntimeError('loop')
    error.__cause__ = error
    assert _client.is_retryable_firestore_transaction_error(error) is False


def test_plain_runtime_error_is_not_retryable():
    assert _client.is_retryable_firestore_transaction_error(RuntimeError('boom')) is False


# ---------------------------------------------------------------------------
# Rejected-document path extraction and its log-safe kind token.
# ---------------------------------------------------------------------------


def _invalid_argument_naming(path: str) -> InvalidArgument:
    return InvalidArgument(f"Invalid document reference .../documents/{path}'.")


def test_document_path_segments_are_extracted():
    error = _invalid_argument_naming('users/uid-1/conversations/c1')
    assert _client.firestore_error_document_path(error) == ('users', 'uid-1', 'conversations', 'c1')


def test_document_path_stops_at_trailing_message_text():
    error = InvalidArgument("bad write at /documents/users/u1/conversations/c1 'and more text")
    assert _client.firestore_error_document_path(error) == ('users', 'u1', 'conversations', 'c1')


def test_message_without_documents_segment_yields_none():
    assert _client.firestore_error_document_path(InvalidArgument('no path here')) is None


def test_odd_segment_count_yields_none():
    assert _client.firestore_error_document_path(_invalid_argument_naming('users/uid-1/conversations')) is None


def test_single_segment_yields_none():
    assert _client.firestore_error_document_path(_invalid_argument_naming('users')) is None


def test_empty_segment_yields_none():
    assert _client.firestore_error_document_path(_invalid_argument_naming('users//conversations/c1')) is None


def test_non_invalid_argument_yields_none():
    assert _client.firestore_error_document_path(Aborted('/documents/users/u/c')) is None


def test_conversation_document_kind():
    error = _invalid_argument_naming('users/uid-1/conversations/c1')
    assert _client.firestore_document_kind(error) == 'conversation'


def test_sync_recent_kind():
    error = _invalid_argument_naming('users/uid-1/sync_assignment/recent')
    assert _client.firestore_document_kind(error) == 'sync_recent'


def test_sync_day_index_kind():
    error = _invalid_argument_naming('users/uid-1/sync_assignment/2026-11-04')
    assert _client.firestore_document_kind(error) == 'sync_day_index'


def test_other_collection_kind():
    error = _invalid_argument_naming('users/uid-1/goals/g1')
    assert _client.firestore_document_kind(error) == 'other'


def test_deeper_conversation_path_is_other():
    error = _invalid_argument_naming('users/uid-1/conversations/c1/segments/s1')
    assert _client.firestore_document_kind(error) == 'other'


def test_unextractable_path_kind_is_none():
    assert _client.firestore_document_kind(ServiceUnavailable('503')) == 'none'


# ---------------------------------------------------------------------------
# The explicit availability-classifier re-export.
# ---------------------------------------------------------------------------


def test_reexport_is_the_utils_classifier():
    assert _client.is_transient_availability_error is is_transient_availability_error


def test_service_unavailable_is_transient():
    assert is_transient_availability_error(ServiceUnavailable('503')) is True


def test_deadline_exceeded_is_transient():
    assert is_transient_availability_error(DeadlineExceeded('504')) is True


def test_internal_server_error_is_transient():
    assert is_transient_availability_error(InternalServerError('500')) is True


def test_retry_error_with_transient_cause_is_transient():
    assert is_transient_availability_error(RetryError('drained', ServiceUnavailable('503'))) is True


def test_retry_error_transient_cause_via_chaining_is_transient():
    # ``RetryError.cause`` wins when set; the documented chaining fallback
    # (``raise final_exc from source_exc``) is consulted only for a cause-less
    # envelope.
    error = RetryError('drained', None)
    error.__cause__ = DeadlineExceeded('504')
    assert is_transient_availability_error(error) is True


def test_retry_error_with_permanent_cause_is_not_transient():
    assert is_transient_availability_error(RetryError('drained', InvalidArgument(SIZE_LIMIT))) is False


def test_cause_less_retry_error_is_not_transient():
    error = RetryError('drained', PermissionDenied('drained'))
    error.__cause__ = None
    assert is_transient_availability_error(error) is False


def test_permission_denied_is_not_transient():
    assert is_transient_availability_error(PermissionDenied('403')) is False


def test_size_limit_invalid_argument_is_not_transient():
    assert is_transient_availability_error(InvalidArgument(SIZE_LIMIT)) is False


def test_plain_runtime_error_is_not_transient():
    assert is_transient_availability_error(RuntimeError('boom')) is False


# ---------------------------------------------------------------------------
# run_transactional: expired-id restarts and the transient opt-in.
# ---------------------------------------------------------------------------


class _RetryClient:
    def __init__(self) -> None:
        self.transactions = 0

    def transaction(self) -> object:
        self.transactions += 1
        return object()


def _flaky(errors: List[BaseException], result: Any = 'ok', calls: List[Any] | None = None) -> Callable[[Any], Any]:
    state = {'n': 0}

    def call(_transaction: Any) -> Any:
        if calls is not None:
            calls.append(_transaction)
        index = state['n']
        state['n'] += 1
        if index < len(errors):
            raise errors[index]
        return result

    return call


def test_expired_id_restarts_on_a_fresh_transaction():
    client = _RetryClient()
    result = _client.run_transactional(
        client, _flaky([InvalidArgument(EXPIRED)]), attempts=3, sleep=lambda _delay: None
    )
    assert result == 'ok'
    assert client.transactions == 2


def test_restart_backoff_uses_equal_jitter():
    client = _RetryClient()
    sleeps: List[float] = []
    _client.run_transactional(
        client,
        _flaky([InvalidArgument(EXPIRED)]),
        attempts=3,
        sleep=sleeps.append,
        random_value=lambda: 0.25,
    )
    assert sleeps == [equal_jitter_delay(1, lambda: 0.25)]


def test_backoff_runs_between_attempts_only():
    client = _RetryClient()
    order: List[str] = []

    def call(_transaction: Any) -> str:
        order.append('call')
        if len(order) == 1:
            raise InvalidArgument(EXPIRED)
        return 'ok'

    def sleep(_delay: float) -> None:
        order.append('sleep')

    _client.run_transactional(client, call, attempts=3, sleep=sleep, random_value=lambda: 0.5)
    assert order == ['call', 'sleep', 'call']


def test_other_invalid_argument_raises_immediately():
    client = _RetryClient()
    sleeps: List[float] = []
    try:
        _client.run_transactional(client, _flaky([InvalidArgument('bad filter')]), attempts=3, sleep=sleeps.append)
        raised = False
    except InvalidArgument:
        raised = True
    assert raised is True
    assert sleeps == []
    assert client.transactions == 1


def test_abort_with_expired_marker_restarts():
    client = _RetryClient()
    result = _client.run_transactional(client, _flaky([Aborted(EXPIRED)]), attempts=3, sleep=lambda _d: None)
    assert result == 'ok'
    assert client.transactions == 2


def test_plain_abort_raises_without_restart():
    client = _RetryClient()
    try:
        _client.run_transactional(client, _flaky([Aborted('contention')]), attempts=3, sleep=lambda _d: None)
        raised = False
    except Aborted:
        raised = True
    assert raised is True
    assert client.transactions == 1


def test_exhausted_attempts_raise_after_bounded_restarts():
    client = _RetryClient()
    sleeps: List[float] = []
    try:
        _client.run_transactional(
            client,
            _flaky([InvalidArgument(EXPIRED), InvalidArgument(EXPIRED), InvalidArgument(EXPIRED)]),
            attempts=3,
            sleep=sleeps.append,
            random_value=lambda: 0.5,
        )
        raised = False
    except InvalidArgument:
        raised = True
    assert raised is True
    assert sleeps == [
        equal_jitter_delay(1, lambda: 0.5),
        equal_jitter_delay(2, lambda: 0.5),
    ]
    assert client.transactions == 3


def test_commit_exhausted_value_error_is_not_caught_by_default():
    client = _RetryClient()
    try:
        _client.run_transactional(client, _flaky([ValueError(COMMIT_EXHAUSTED)]), attempts=3, sleep=lambda _d: None)
        raised = False
    except ValueError:
        raised = True
    assert raised is True
    assert client.transactions == 1


def test_transient_restart_on_unavailable():
    client = _RetryClient()
    result = _client.run_transactional(
        client, _flaky([ServiceUnavailable('503')]), attempts=3, transient=True, sleep=lambda _d: None
    )
    assert result == 'ok'
    assert client.transactions == 2


def test_transient_restart_on_resource_exhausted():
    client = _RetryClient()
    result = _client.run_transactional(
        client, _flaky([ResourceExhausted('429')]), attempts=3, transient=True, sleep=lambda _d: None
    )
    assert result == 'ok'
    assert client.transactions == 2


def test_transient_restart_on_deadline_exceeded():
    client = _RetryClient()
    result = _client.run_transactional(
        client, _flaky([DeadlineExceeded('504')]), attempts=3, transient=True, sleep=lambda _d: None
    )
    assert result == 'ok'
    assert client.transactions == 2


def test_transient_restart_on_commit_exhausted_value_error():
    client = _RetryClient()
    result = _client.run_transactional(
        client, _flaky([ValueError(COMMIT_EXHAUSTED)]), attempts=3, transient=True, sleep=lambda _d: None
    )
    assert result == 'ok'
    assert client.transactions == 2


def test_transient_restart_on_wrapped_contention():
    client = _RetryClient()
    result = _client.run_transactional(
        client, _flaky([FirestoreAborted('contention')]), attempts=3, transient=True, sleep=lambda _d: None
    )
    assert result == 'ok'
    assert client.transactions == 2


def test_transient_restart_on_contention_exhaustion():
    client = _RetryClient()
    result = _client.run_transactional(
        client,
        _flaky([FirestoreContentionExhausted('attempts_exhausted')]),
        attempts=3,
        transient=True,
        sleep=lambda _d: None,
    )
    assert result == 'ok'
    assert client.transactions == 2


def test_transient_walks_the_cause_chain():
    client = _RetryClient()
    wrapper = RuntimeError('commit envelope')
    wrapper.__cause__ = ServiceUnavailable('503')
    result = _client.run_transactional(client, _flaky([wrapper]), attempts=3, transient=True, sleep=lambda _d: None)
    assert result == 'ok'
    assert client.transactions == 2


def test_transient_permanent_refusal_raises_without_restart():
    client = _RetryClient()
    error = InvalidArgument(SIZE_LIMIT)
    error.__cause__ = ServiceUnavailable('503')
    try:
        _client.run_transactional(client, _flaky([error]), attempts=3, transient=True, sleep=lambda _d: None)
        raised = False
    except InvalidArgument:
        raised = True
    assert raised is True
    assert client.transactions == 1


def test_outcome_reports_retried_ok():
    client = _RetryClient()
    outcome: dict[str, str] = {}
    _client.run_transactional(
        client,
        _flaky([InvalidArgument(EXPIRED)]),
        attempts=3,
        sleep=lambda _d: None,
        outcome=outcome,
    )
    assert outcome == {'status': 'retried_ok'}


def test_outcome_reports_exhausted():
    client = _RetryClient()
    outcome: dict[str, str] = {}
    try:
        _client.run_transactional(
            client,
            _flaky([InvalidArgument(EXPIRED), InvalidArgument(EXPIRED)]),
            attempts=2,
            sleep=lambda _d: None,
            outcome=outcome,
        )
    except InvalidArgument:
        pass
    assert outcome == {'status': 'exhausted'}


def test_initial_transaction_is_used_then_replaced_on_expiry():
    client = _RetryClient()
    initial = object()
    calls: List[Any] = []
    _client.run_transactional(
        client,
        _flaky([InvalidArgument(EXPIRED)], calls=calls),
        initial_transaction=initial,
        attempts=2,
        sleep=lambda _d: None,
    )
    assert calls[0] is initial
    assert calls[1] is not initial


def test_single_attempt_budget_does_not_restart():
    client = _RetryClient()
    try:
        _client.run_transactional(client, _flaky([InvalidArgument(EXPIRED)]), attempts=1, sleep=lambda _d: None)
        raised = False
    except InvalidArgument:
        raised = True
    assert raised is True
    assert client.transactions == 1
