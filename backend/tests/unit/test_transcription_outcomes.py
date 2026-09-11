from unittest.mock import MagicMock, patch

import httpx

from config.prerecorded_stt import PrerecordedSTTConfigurationError
from utils.observability.transcription import (
    LiveSTTAttempt,
    TranscriptionAttempt,
    record_live_stt_audio_seconds,
    record_live_stt_failure,
)
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


@patch('utils.observability.transcription.OMI_LIVE_STT_TERMINAL_TOTAL')
@patch('utils.observability.transcription.OMI_LIVE_STT_ACCEPTED_TOTAL')
def test_live_stt_attempt_records_one_bounded_acceptance_and_terminal(mock_accepted, mock_terminal, monkeypatch):
    accepted_child = MagicMock()
    terminal_child = MagicMock()
    mock_accepted.labels.return_value = accepted_child
    mock_terminal.labels.return_value = terminal_child
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('K_REVISION', 'unbounded-revision-value')
    monkeypatch.setenv('OMI_DEPLOYMENT_VERSION', 'another-unbounded-value')

    attempt = LiveSTTAttempt(provider='deepgram', platform='ios')
    attempt.finish('failure', phase='send')
    attempt.finish('cancelled', phase='teardown')

    assert mock_accepted.labels.call_args.kwargs == {
        'provider': 'deepgram',
        'client_platform': 'ios',
        'deployment_environment': 'dev',
    }
    assert mock_terminal.labels.call_args.kwargs == {
        'provider': 'deepgram',
        'outcome': 'failure',
        'client_platform': 'ios',
        'deployment_environment': 'dev',
        'phase': 'send',
    }
    accepted_child.inc.assert_called_once_with()
    terminal_child.inc.assert_called_once_with()


@patch('utils.observability.transcription.OMI_LIVE_STT_TERMINAL_TOTAL')
@patch('utils.observability.transcription.OMI_LIVE_STT_ACCEPTED_TOTAL')
def test_live_stt_attempt_emits_joinable_product_lifecycle(mock_accepted, mock_terminal):
    mock_accepted.labels.return_value = MagicMock()
    mock_terminal.labels.return_value = MagicMock()
    emitted = []
    times = iter([100.0, 101.25])

    attempt = LiveSTTAttempt(
        provider='deepgram',
        platform='ios',
        uid='user-1',
        recording_id='recording-1',
        conversation_id='conversation-1',
        source='phone',
        model='nova-3',
        language='en',
        emitter=lambda **event: emitted.append(event),
        clock=lambda: next(times),
    )
    attempt.finish('success', phase='transcript_delivery')
    attempt.finish('failure', phase='teardown')

    assert [event['event'] for event in emitted] == ['Transcript Started', 'Transcript Completed']
    assert emitted[0] == {
        'uid': 'user-1',
        'event': 'Transcript Started',
        'properties': {
            'recording_id': 'recording-1',
            'conversation_id': 'conversation-1',
            'transcription_source': 'phone',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
            'transcript_language': 'en',
            'app_platform': 'ios',
        },
    }
    assert emitted[1]['properties']['duration_seconds'] == 1.25
    assert emitted[1]['properties']['phase'] == 'transcript_delivery'


@patch('utils.observability.transcription.OMI_LIVE_STT_TERMINAL_TOTAL')
@patch('utils.observability.transcription.OMI_LIVE_STT_ACCEPTED_TOTAL')
def test_live_stt_product_telemetry_failure_is_fail_open(mock_accepted, mock_terminal):
    mock_accepted.labels.return_value = MagicMock()
    mock_terminal.labels.return_value = MagicMock()
    attempt = LiveSTTAttempt(
        provider='deepgram',
        platform='ios',
        uid='user-1',
        emitter=lambda **_: (_ for _ in ()).throw(RuntimeError('analytics unavailable')),
    )

    attempt.finish('failure', phase='send')

    mock_terminal.labels.return_value.inc.assert_called_once_with()


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
        'deployment_environment': 'unknown',
        'phase': 'unknown',
    }
    child.inc.assert_called_once_with()


@patch('utils.observability.transcription.OMI_TRANSCRIPTION_LATENCY_SECONDS')
@patch('utils.observability.transcription.OMI_TRANSCRIPTION_COMPLETED_TOTAL')
@patch('utils.observability.transcription.OMI_TRANSCRIPTION_ACCEPTED_TOTAL')
@patch('utils.observability.transcription.OMI_TRANSCRIPTION_AUDIO_SECONDS_TOTAL')
def test_attempt_records_measured_audio_seconds_on_finish(mock_audio, mock_accepted, mock_completed, mock_latency):
    audio_child = MagicMock()
    latency_child = MagicMock()
    mock_audio.labels.return_value = audio_child
    mock_latency.labels.return_value = latency_child

    attempt = TranscriptionAttempt(route='voice_rest_pcm', provider='parakeet', platform='desktop', audio_seconds=12.5)
    attempt.finish(TranscriptionOutcome.SUCCESS)

    assert mock_audio.labels.call_args.kwargs == {
        'route': 'voice_rest_pcm',
        'provider': 'parakeet',
        'outcome': 'success',
        'client_platform': 'desktop',
    }
    audio_child.inc.assert_called_once_with(12.5)
    # Wall-clock latency stays a separate signal on the same terminal.
    latency_child.observe.assert_called_once()


@patch('utils.observability.transcription.OMI_TRANSCRIPTION_LATENCY_SECONDS')
@patch('utils.observability.transcription.OMI_TRANSCRIPTION_COMPLETED_TOTAL')
@patch('utils.observability.transcription.OMI_TRANSCRIPTION_ACCEPTED_TOTAL')
@patch('utils.observability.transcription.OMI_TRANSCRIPTION_AUDIO_SECONDS_TOTAL')
def test_finish_uses_audio_duration_not_wallclock_latency(mock_audio, mock_accepted, mock_completed, mock_latency):
    audio_child = MagicMock()
    latency_child = MagicMock()
    mock_audio.labels.return_value = audio_child
    mock_latency.labels.return_value = latency_child

    attempt = TranscriptionAttempt(
        route='voice_rest_multipart', provider='modulate', platform='ios', audio_seconds=187.5
    )
    attempt.finish(TranscriptionOutcome.UPSTREAM_ERROR)

    observed_latency = latency_child.observe.call_args.args[0]
    # Constructor-to-finish wall clock is microseconds; if finish ever wires
    # latency into the audio-seconds counter this exact-args assert fails.
    assert 0.0 <= observed_latency < 1.0
    audio_child.inc.assert_called_once_with(187.5)


@patch('utils.observability.transcription.OMI_TRANSCRIPTION_LATENCY_SECONDS')
@patch('utils.observability.transcription.OMI_TRANSCRIPTION_COMPLETED_TOTAL')
@patch('utils.observability.transcription.OMI_TRANSCRIPTION_ACCEPTED_TOTAL')
@patch('utils.observability.transcription.OMI_TRANSCRIPTION_AUDIO_SECONDS_TOTAL')
def test_attempt_without_measured_duration_records_no_audio_seconds(
    mock_audio, mock_accepted, mock_completed, mock_latency
):
    attempt = TranscriptionAttempt(route='voice_chat_sse', provider='modulate', platform=None)
    attempt.finish(TranscriptionOutcome.INVALID_INPUT)

    mock_audio.labels.assert_not_called()


@patch('utils.observability.transcription.OMI_TRANSCRIPTION_LATENCY_SECONDS')
@patch('utils.observability.transcription.OMI_TRANSCRIPTION_COMPLETED_TOTAL')
@patch('utils.observability.transcription.OMI_TRANSCRIPTION_ACCEPTED_TOTAL')
@patch('utils.observability.transcription.OMI_TRANSCRIPTION_AUDIO_SECONDS_TOTAL')
def test_audio_seconds_labels_bound_unknown_provider_route_and_platform(
    mock_audio, mock_accepted, mock_completed, mock_latency
):
    mock_audio.labels.return_value = MagicMock()

    attempt = TranscriptionAttempt(route='brand-new-route', provider='brand-new-stt', platform='Web', audio_seconds=5.0)
    attempt.finish(TranscriptionOutcome.EMPTY_UNEXPECTED)

    assert mock_audio.labels.call_args.kwargs == {
        'route': 'other',
        'provider': 'unknown',
        'outcome': 'empty_unexpected',
        'client_platform': 'web',
    }


@patch('utils.observability.transcription.OMI_TRANSCRIPTION_LATENCY_SECONDS')
@patch('utils.observability.transcription.OMI_TRANSCRIPTION_COMPLETED_TOTAL')
@patch('utils.observability.transcription.OMI_TRANSCRIPTION_ACCEPTED_TOTAL')
@patch('utils.observability.transcription.OMI_TRANSCRIPTION_AUDIO_SECONDS_TOTAL')
def test_negative_audio_seconds_emit_nothing(mock_audio, mock_accepted, mock_completed, mock_latency):
    attempt = TranscriptionAttempt(route='voice_rest_pcm', provider='deepgram', platform='ios', audio_seconds=-9.0)
    attempt.finish(TranscriptionOutcome.SUCCESS)

    mock_audio.labels.assert_not_called()


def test_bounded_provider_maps_the_stt_provider_vocabulary():
    from utils.stt.outcomes import bounded_provider

    for token in ('modulate', 'parakeet', 'deepgram', 'soniox', 'deepgram_cloud'):
        assert bounded_provider(token) == token
    assert bounded_provider('brand-new-stt') == 'unknown'
    assert bounded_provider(None) == 'unknown'


@patch('utils.observability.transcription.OMI_LIVE_STT_AUDIO_SECONDS_TOTAL')
def test_record_live_stt_audio_seconds_uses_bounded_labels(mock_audio):
    child = MagicMock()
    mock_audio.labels.return_value = child

    record_live_stt_audio_seconds(provider='soniox', platform='android', seconds=4.2)

    assert mock_audio.labels.call_args.kwargs == {
        'provider': 'soniox',
        'client_platform': 'android',
        'deployment_environment': 'unknown',
    }
    child.inc.assert_called_once_with(4.2)


@patch('utils.observability.transcription.OMI_LIVE_STT_AUDIO_SECONDS_TOTAL')
def test_record_live_stt_audio_seconds_skips_nonpositive_deltas(mock_audio):
    record_live_stt_audio_seconds(provider='deepgram', platform='ios', seconds=0)
    record_live_stt_audio_seconds(provider='deepgram', platform='ios', seconds=-3.0)

    mock_audio.labels.assert_not_called()
