"""Behavioral contract for the real-traffic product-health metric slice."""

from unittest.mock import MagicMock, patch

import pytest

from utils.observability.product_health import (
    PRODUCT_JOURNEY_ACCEPTED_TOTAL,
    PRODUCT_JOURNEY_LATENCY_SECONDS,
    PRODUCT_JOURNEY_TERMINAL_TOTAL,
    ProductJourney,
    ProductJourneyAttempt,
    ProductJourneyOutcome,
    finish_pusher_session_attempt,
    record_durable_journey_terminal,
)


@patch('utils.observability.product_health.monotonic', side_effect=[10.0, 13.5])
@patch('utils.observability.product_health.PRODUCT_JOURNEY_LATENCY_SECONDS')
@patch('utils.observability.product_health.PRODUCT_JOURNEY_TERMINAL_TOTAL')
@patch('utils.observability.product_health.PRODUCT_JOURNEY_ACCEPTED_TOTAL')
def test_attempt_records_one_accepted_and_one_success_terminal(
    accepted_metric,
    terminal_metric,
    latency_metric,
    _monotonic,
):
    accepted_child = MagicMock()
    terminal_child = MagicMock()
    latency_child = MagicMock()
    accepted_metric.labels.return_value = accepted_child
    terminal_metric.labels.return_value = terminal_child
    latency_metric.labels.return_value = latency_child

    attempt = ProductJourneyAttempt.accepted(ProductJourney.chat_response)
    attempt.finish(ProductJourneyOutcome.succeeded)
    attempt.finish(ProductJourneyOutcome.failed)

    accepted_metric.labels.assert_called_once_with(journey='chat_response')
    terminal_metric.labels.assert_called_once_with(journey='chat_response', outcome='succeeded')
    latency_metric.labels.assert_called_once_with(journey='chat_response', outcome='succeeded')
    accepted_child.inc.assert_called_once_with()
    terminal_child.inc.assert_called_once_with()
    latency_child.observe.assert_called_once_with(3.5)


def test_contract_rejects_non_allowlisted_labels():
    with pytest.raises(ValueError, match='ProductJourney'):
        ProductJourneyAttempt.accepted('user-123')  # type: ignore[arg-type]

    with pytest.raises(ValueError, match='ProductJourneyOutcome'):
        record_durable_journey_terminal(
            ProductJourney.capture_finalization,
            'raw provider response',  # type: ignore[arg-type]
            accepted_at_epoch_seconds=1.0,
            now_epoch_seconds=2.0,
        )


@patch('utils.observability.product_health.PRODUCT_JOURNEY_LATENCY_SECONDS')
@patch('utils.observability.product_health.PRODUCT_JOURNEY_TERMINAL_TOTAL')
def test_durable_terminal_uses_persisted_acceptance_time_without_identity_labels(terminal_metric, latency_metric):
    terminal_child = MagicMock()
    latency_child = MagicMock()
    terminal_metric.labels.return_value = terminal_child
    latency_metric.labels.return_value = latency_child

    record_durable_journey_terminal(
        ProductJourney.capture_finalization,
        ProductJourneyOutcome.failed,
        accepted_at_epoch_seconds=100.0,
        now_epoch_seconds=121.25,
    )

    expected_labels = {'journey': 'capture_finalization', 'outcome': 'failed'}
    assert terminal_metric.labels.call_args.kwargs == expected_labels
    assert latency_metric.labels.call_args.kwargs == expected_labels
    terminal_child.inc.assert_called_once_with()
    latency_child.observe.assert_called_once_with(21.25)


def test_metric_contract_has_only_closed_journey_and_outcome_labels():
    assert PRODUCT_JOURNEY_ACCEPTED_TOTAL._labelnames == ('journey',)
    assert PRODUCT_JOURNEY_TERMINAL_TOTAL._labelnames == ('journey', 'outcome')
    assert PRODUCT_JOURNEY_LATENCY_SECONDS._labelnames == ('journey', 'outcome')
    assert {journey.value for journey in ProductJourney} == {
        'chat_response',
        'realtime_pusher_session',
        'capture_finalization',
    }


@pytest.mark.parametrize('client_disconnect_code', (1000, 1001))
def test_pusher_normal_client_disconnects_are_terminal_successes(client_disconnect_code):
    attempt = MagicMock()

    finish_pusher_session_attempt(attempt, client_disconnect_code=client_disconnect_code)

    attempt.finish.assert_called_once_with(ProductJourneyOutcome.succeeded)


@pytest.mark.parametrize('client_disconnect_code', (None, 1006, 1011))
def test_pusher_server_and_error_closes_are_terminal_failures(client_disconnect_code):
    attempt = MagicMock()

    finish_pusher_session_attempt(attempt, client_disconnect_code=client_disconnect_code)

    attempt.finish.assert_called_once_with(ProductJourneyOutcome.failed)
    assert {outcome.value for outcome in ProductJourneyOutcome} == {'succeeded', 'failed'}
