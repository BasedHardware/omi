from unittest.mock import MagicMock, patch

import httpx

from config.prerecorded_stt import PrerecordedSTTConfigurationError
from utils.observability.transcription import TranscriptionAttempt, record_live_stt_failure
from utils.stt.outcomes import (
    TranscriptionFailure,
    TranscriptionOutcome,
    failure_from_exception,
)


def test_outcome_vocabulary_is_closed_and_complete():
    assert {outcome.value for outcome in TranscriptionOutcome} == {
        'success',
        'expected_silence',
        'empty_unexpected',
        'timeout',
        'upstream_error',
        'config_error',
        'invalid_input',
    }


def test_wrapped_configuration_error_preserves_provider_without_env_leak():
    configuration_error = PrerecordedSTTConfigurationError('parakeet', 'SECRET_PARAKAET_URL')
    try:
        raise RuntimeError('raw wrapper') from configuration_error
    except RuntimeError as error:
        failure = failure_from_exception(error, provider='deepgram')

    assert failure.outcome == TranscriptionOutcome.CONFIG_ERROR
    assert failure.provider == 'parakeet'
    assert failure.status_code == 503
    assert failure.retryable is False
    assert 'SECRET_PARAKAET_URL' not in str(failure.as_detail())
    assert 'raw wrapper' not in str(failure.as_detail())


def test_wrapped_timeout_is_safe_and_retryable():
    timeout = httpx.ReadTimeout('raw response body')
    try:
        raise RuntimeError('provider wrapper') from timeout
    except RuntimeError as error:
        failure = failure_from_exception(error, provider='deepgram')

    assert failure.outcome == TranscriptionOutcome.TIMEOUT
    assert failure.status_code == 504
    assert failure.retryable is True
    assert 'raw response body' not in str(failure.as_detail())


def test_unknown_provider_is_bounded_in_public_failure():
    failure = TranscriptionFailure(TranscriptionOutcome.UPSTREAM_ERROR, provider='user-supplied-provider')
    assert failure.provider == 'unknown'
    assert failure.as_detail()['provider'] == 'unknown'


@patch('utils.observability.transcription.OMI_TRANSCRIPTION_LATENCY_SECONDS')
@patch('utils.observability.transcription.OMI_TRANSCRIPTION_COMPLETED_TOTAL')
@patch('utils.observability.transcription.OMI_TRANSCRIPTION_ACCEPTED_TOTAL')
def test_attempt_records_one_accepted_and_exactly_one_terminal(mock_accepted, mock_completed, mock_latency):
    accepted_child = MagicMock()
    completed_child = MagicMock()
    latency_child = MagicMock()
    mock_accepted.labels.return_value = accepted_child
    mock_completed.labels.return_value = completed_child
    mock_latency.labels.return_value = latency_child

    attempt = TranscriptionAttempt(route='voice_rest_pcm', provider='deepgram', platform='ios')
    attempt.finish(TranscriptionOutcome.SUCCESS)
    attempt.finish(TranscriptionOutcome.UPSTREAM_ERROR)

    accepted_child.inc.assert_called_once_with()
    completed_child.inc.assert_called_once_with()
    latency_child.observe.assert_called_once()
    assert mock_completed.labels.call_args.kwargs['outcome'] == 'success'


@patch('utils.observability.transcription.OMI_LIVE_STT_TERMINAL_FAILURES_TOTAL')
def test_live_failure_labels_are_bounded(mock_counter):
    child = MagicMock()
    mock_counter.labels.return_value = child

    record_live_stt_failure(
        provider='untrusted-provider',
        platform='untrusted-platform',
        outcome=TranscriptionOutcome.UPSTREAM_ERROR,
        phase='untrusted-phase',
    )

    assert mock_counter.labels.call_args.kwargs == {
        'provider': 'unknown',
        'outcome': 'upstream_error',
        'client_platform': 'unknown',
        'deployment_version': 'unknown',
        'phase': 'unknown',
    }
    child.inc.assert_called_once_with()
