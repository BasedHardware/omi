"""omi_journey_failure_reason_total and the one-line chat failure log: closed reasons, no free text."""

import logging
from unittest.mock import MagicMock

import pytest

from utils import metrics
from utils.observability import journeys
from utils.observability.reasons import (
    ChatResponseFailureReason,
    chat_response_failure_reason,
    exception_class_name,
)


def _reason_samples():
    out = {}
    for family in journeys.OMI_JOURNEY_FAILURE_REASON_TOTAL.collect():
        for sample in family.samples:
            if sample.name.endswith('_total'):
                out[(sample.labels['journey'], sample.labels['reason'])] = sample.value
    return out


@pytest.mark.parametrize(
    ('staged', 'expected'),
    [
        ('idle_timeout', ChatResponseFailureReason.IDLE_TIMEOUT),
        ('setup_timeout', ChatResponseFailureReason.SETUP_TIMEOUT),
        ('empty_answer', ChatResponseFailureReason.EMPTY_ANSWER),
        ('provider_refusal', ChatResponseFailureReason.PROVIDER_REFUSAL),
        ('stream_failure', ChatResponseFailureReason.STREAM_FAILURE),
        ('TimeoutError', ChatResponseFailureReason.TIMEOUT),
        ('APITimeoutError', ChatResponseFailureReason.TIMEOUT),
        ('APIConnectionError', ChatResponseFailureReason.PROVIDER_ERROR),
        ('InternalServerError', ChatResponseFailureReason.PROVIDER_ERROR),
        ('ValueError', ChatResponseFailureReason.UNKNOWN),
        ('Sorry, the upstream said: secret text', ChatResponseFailureReason.UNKNOWN),
        ('', ChatResponseFailureReason.UNKNOWN),
        (None, ChatResponseFailureReason.UNKNOWN),
        (ValueError('boom'), ChatResponseFailureReason.UNKNOWN),
    ],
)
def test_staged_chat_errors_fold_to_closed_reasons(staged, expected):
    assert chat_response_failure_reason(staged) is expected


def test_exception_class_name_passes_only_identifiers():
    assert exception_class_name('APIError') == 'APIError'
    assert exception_class_name('idle_timeout') is None
    assert exception_class_name('has a space') is None
    assert exception_class_name('A' * 81) is None
    assert exception_class_name(None) is None


def test_every_reason_value_is_lower_snake_and_short():
    for member in ChatResponseFailureReason:
        assert len(member.value) <= 40
        assert member.value == member.value.lower()


def test_chat_failure_reason_children_are_precreated_at_zero():
    samples = _reason_samples()
    for member in ChatResponseFailureReason:
        assert ('chat_response', member.value) in samples


def test_terminal_counter_label_set_is_unchanged():
    assert metrics.OMI_JOURNEY_TERMINAL_TOTAL._labelnames == ('journey', 'outcome')


def test_failure_terminal_counts_its_reason_and_success_does_not(monkeypatch):
    reason_counter = MagicMock()
    monkeypatch.setattr(journeys, 'OMI_JOURNEY_FAILURE_REASON_TOTAL', reason_counter)
    monkeypatch.setattr(journeys, 'OMI_JOURNEY_TERMINAL_TOTAL', MagicMock())
    monkeypatch.setattr(journeys, 'OMI_JOURNEY_LATENCY_SECONDS', MagicMock())

    journeys.record_journey_terminal(
        'chat_response', 'failure', 1.0, failure_reason=ChatResponseFailureReason.EMPTY_ANSWER
    )
    reason_counter.labels.assert_called_with(journey='chat_response', reason='empty_answer')

    journeys.record_journey_terminal('chat_response', 'failure', 1.0)
    reason_counter.labels.assert_called_with(journey='chat_response', reason='unknown')

    reason_counter.reset_mock()
    journeys.record_journey_terminal('chat_response', 'success', 1.0)
    reason_counter.labels.assert_not_called()


def test_failure_finish_logs_exactly_once_with_enum_and_class_only(caplog):
    before = _reason_samples()[('chat_response', 'provider_error')]
    attempt = journeys.JourneyAttempt('chat_response')

    with caplog.at_level(logging.WARNING, logger=journeys.__name__):
        attempt.finish(
            'failure',
            failure_reason=chat_response_failure_reason('APIConnectionError'),
            error_type='APIConnectionError',
        )
        attempt.finish('failure', failure_reason=ChatResponseFailureReason.TIMEOUT, error_type='TimeoutError')

    failures = [record for record in caplog.records if 'Chat response failed' in record.getMessage()]
    assert len(failures) == 1
    assert failures[0].levelno == logging.WARNING
    assert failures[0].getMessage() == 'Chat response failed reason=provider_error error_type=APIConnectionError'
    assert _reason_samples()[('chat_response', 'provider_error')] == before + 1


def test_failure_without_reason_logs_unknown_and_none_error_type(caplog):
    attempt = journeys.JourneyAttempt('chat_response')
    with caplog.at_level(logging.WARNING, logger=journeys.__name__):
        attempt.finish('failure')
    assert [record.getMessage() for record in caplog.records if 'Chat response failed' in record.getMessage()] == [
        'Chat response failed reason=unknown error_type=none'
    ]


def test_non_chat_journeys_and_cancellations_do_not_log(caplog):
    with caplog.at_level(logging.WARNING, logger=journeys.__name__):
        journeys.JourneyAttempt('pusher_session').finish('failure')
        journeys.JourneyAttempt('chat_response').finish('cancelled')
    assert not [record for record in caplog.records if 'Chat response failed' in record.getMessage()]
