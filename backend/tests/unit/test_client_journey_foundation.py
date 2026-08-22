import asyncio
import gc
from unittest.mock import MagicMock

import pytest
from starlette.requests import ClientDisconnect

from utils import metrics
from utils.journey_metrics_contract import (
    CLIENT_JOURNEY_ISSUE_CLASSES,
    CLIENT_JOURNEY_OUTCOMES,
    CLIENT_JOURNEYS,
    CLIENT_KINDS,
    _bounded,
    bounded_client_journey,
    bounded_client_journey_issue_class,
    bounded_client_journey_outcome,
    bounded_client_kind,
    resolve_client_kind,
    resolve_client_kind_from_headers,
)
from utils.observability import journeys


def _install_client_journey_metrics(monkeypatch):
    accepted = MagicMock()
    terminal = MagicMock()
    issues = MagicMock()
    duration = MagicMock()
    for metric in (accepted, terminal, issues, duration):
        metric.labels.return_value = MagicMock()
    monkeypatch.setattr(journeys, 'OMI_CLIENT_JOURNEY_ACCEPTED_TOTAL', accepted)
    monkeypatch.setattr(journeys, 'OMI_CLIENT_JOURNEY_TERMINAL_TOTAL', terminal)
    monkeypatch.setattr(journeys, 'OMI_CLIENT_JOURNEY_ISSUES_TOTAL', issues)
    monkeypatch.setattr(journeys, 'OMI_CLIENT_JOURNEY_DURATION_SECONDS', duration)
    return accepted, terminal, issues, duration


def _sample_label_sets(metric, sample_name):
    return {
        tuple(sorted(sample.labels.items()))
        for family in metric.collect()
        for sample in family.samples
        if sample.name == sample_name
    }


def test_label_coercion_collapses_unbounded_values_to_unknown():
    raw = 'USER PROVIDED ' + ('x' * 10_000)

    assert len(_bounded(raw)) == 128
    assert bounded_client_journey(raw) == 'unknown'
    assert bounded_client_journey_outcome(raw) == 'unknown'
    assert bounded_client_journey_issue_class(raw) == 'unknown'
    assert bounded_client_kind(raw) == 'unknown'


@pytest.mark.parametrize(
    ('platform', 'expected'),
    [
        ('android', 'mobile_android'),
        ('ios', 'mobile_ios'),
        ('macos', 'desktop_macos'),
        ('windows', 'desktop_windows'),
        ('linux', 'desktop_linux'),
        ('web', 'web'),
    ],
)
def test_client_kind_prefers_known_platform_header(platform, expected):
    assert resolve_client_kind(x_app_platform=platform, user_agent='OpenAI/JS 6.26.0') == expected


def test_client_kind_maps_known_headerless_populations_without_inventing_pi_mono_os():
    assert (
        resolve_client_kind(
            x_app_platform=None,
            user_agent='Omi/1.0 CFNetwork/1568.200.51 Darwin/24.1.0',
        )
        == 'desktop_macos'
    )
    assert (
        resolve_client_kind(
            x_app_platform=None,
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128 Electron/32.0.0',
        )
        == 'desktop_windows'
    )
    assert resolve_client_kind(x_app_platform=None, user_agent='Dart/3.8 (dart:io)') == 'dart_mobile_unknown_os'

    pi_mono_user_agent = 'OpenAI/JS 6.26.0'
    for platform, platform_kind in (('macos', 'desktop_macos'), ('windows', 'desktop_windows')):
        assert resolve_client_kind(x_app_platform=platform, user_agent=pi_mono_user_agent) == platform_kind
        assert resolve_client_kind(x_app_platform=None, user_agent=pi_mono_user_agent) == 'pi_mono_unknown_os'


def test_client_kind_unknown_header_does_not_fall_through_to_user_agent():
    assert (
        resolve_client_kind_from_headers({'X-App-Platform': 'new-unbounded-client', 'User-Agent': 'OpenAI/JS 6.26.0'})
        == 'unknown'
    )


def test_client_kind_non_string_header_collapses_to_unknown():
    assert resolve_client_kind(x_app_platform=object(), user_agent='OpenAI/JS 6.26.0') == 'unknown'


def test_client_journey_metrics_zero_initialize_the_complete_bounded_contract():
    accepted = _sample_label_sets(metrics.OMI_CLIENT_JOURNEY_ACCEPTED_TOTAL, 'omi_client_journey_accepted_total')
    terminal = _sample_label_sets(metrics.OMI_CLIENT_JOURNEY_TERMINAL_TOTAL, 'omi_client_journey_terminal_total')
    issues = _sample_label_sets(metrics.OMI_CLIENT_JOURNEY_ISSUES_TOTAL, 'omi_client_journey_issues_total')
    duration = _sample_label_sets(
        metrics.OMI_CLIENT_JOURNEY_DURATION_SECONDS, 'omi_client_journey_duration_seconds_count'
    )

    assert len(accepted) == len(CLIENT_JOURNEYS) * len(CLIENT_KINDS)
    assert len(terminal) == len(CLIENT_JOURNEYS) * len(CLIENT_KINDS) * len(CLIENT_JOURNEY_OUTCOMES)
    assert len(issues) == len(CLIENT_JOURNEYS) * len(CLIENT_KINDS) * len(CLIENT_JOURNEY_ISSUE_CLASSES)
    assert len(duration) == len(CLIENT_JOURNEYS) * len(CLIENT_JOURNEY_OUTCOMES)
    assert (
        ('client_kind', 'pi_mono_unknown_os'),
        ('journey', 'desktop_chat'),
    ) in accepted
    assert (
        ('client_kind', 'desktop_macos'),
        ('journey', 'desktop_chat'),
        ('outcome', 'degraded'),
    ) in terminal


def test_streaming_attempt_records_failure_when_stream_breaks_after_success_candidate(monkeypatch):
    _accepted, terminal, issues, duration = _install_client_journey_metrics(monkeypatch)
    clock_values = iter((10.0, 12.0))
    attempt = journeys.ClientJourneyAttempt(
        'desktop_chat',
        'desktop_macos',
        clock=lambda: next(clock_values),
    )

    async def broken_stream():
        yield 'terminal-content-frame'
        raise RuntimeError('stream failed after headers')

    async def consume():
        async for _item in attempt.observe_stream(
            broken_stream(),
            success_when=lambda item: item == 'terminal-content-frame',
            failure_when=lambda _item: False,
            failure_class='provider_error',
        ):
            pass

    with pytest.raises(RuntimeError, match='after headers'):
        asyncio.run(consume())

    assert attempt.outcome == 'failure'
    terminal.labels.assert_called_once_with(
        journey='desktop_chat',
        client_kind='desktop_macos',
        outcome='failure',
    )
    issues.labels.assert_called_once_with(
        journey='desktop_chat',
        client_kind='desktop_macos',
        issue_class='provider_error',
    )
    duration.labels.assert_called_once_with(journey='desktop_chat', outcome='failure')


def test_streaming_attempt_records_success_only_after_clean_exhaustion(monkeypatch):
    _accepted, terminal, issues, _duration = _install_client_journey_metrics(monkeypatch)
    clock_values = iter((20.0, 21.0))
    attempt = journeys.ClientJourneyAttempt(
        'desktop_chat',
        'desktop_windows',
        clock=lambda: next(clock_values),
    )

    async def complete_stream():
        yield 'terminal-content-frame'

    async def consume():
        async for _item in attempt.observe_stream(
            complete_stream(),
            success_when=lambda item: item == 'terminal-content-frame',
            failure_when=lambda _item: False,
        ):
            pass

    asyncio.run(consume())

    assert attempt.outcome == 'success'
    terminal.labels.assert_called_once_with(
        journey='desktop_chat',
        client_kind='desktop_windows',
        outcome='success',
    )
    issues.labels.assert_not_called()


_DESKTOP_CHAT_ERROR_FRAME = (
    b'data: {"error":{"message":"Upstream provider error","type":"server_error","code":502}}\n\n'
)
_DESKTOP_CHAT_DONE_FRAME = b'data: [DONE]\n\n'


def test_streaming_attempt_error_frame_wins_over_later_done(monkeypatch):
    _accepted, terminal, issues, _duration = _install_client_journey_metrics(monkeypatch)
    clock_values = iter((30.0, 31.0))
    attempt = journeys.ClientJourneyAttempt(
        'desktop_chat',
        'pi_mono_unknown_os',
        clock=lambda: next(clock_values),
    )

    async def incident_stream():
        # Literal desktop_chat gateway-rejection frames, including _sse's compact JSON.
        yield _DESKTOP_CHAT_ERROR_FRAME
        yield _DESKTOP_CHAT_DONE_FRAME

    async def consume():
        return [
            item
            async for item in attempt.observe_stream(
                incident_stream(),
                success_when=lambda item: b'data: [DONE]' in item,
                failure_when=lambda item: b'"error":' in item,
                failure_class='upstream_rejected',
            )
        ]

    assert asyncio.run(consume()) == [_DESKTOP_CHAT_ERROR_FRAME, _DESKTOP_CHAT_DONE_FRAME]
    assert attempt.outcome == 'failure'
    assert attempt.issue_class == 'upstream_rejected'
    terminal.labels.assert_called_once_with(
        journey='desktop_chat',
        client_kind='pi_mono_unknown_os',
        outcome='failure',
    )
    issues.labels.assert_called_once_with(
        journey='desktop_chat',
        client_kind='pi_mono_unknown_os',
        issue_class='upstream_rejected',
    )


@pytest.mark.parametrize(
    ('frames', 'expected_issue'),
    [
        ([], 'empty_answer'),
        ([_DESKTOP_CHAT_ERROR_FRAME], 'upstream_rejected'),
    ],
)
def test_streaming_attempt_empty_and_error_only_streams_fail(monkeypatch, frames, expected_issue):
    _install_client_journey_metrics(monkeypatch)
    attempt = journeys.ClientJourneyAttempt('desktop_chat', 'desktop_macos')

    async def source():
        for frame in frames:
            yield frame

    async def consume():
        async for _item in attempt.observe_stream(
            source(),
            success_when=lambda item: b'data: [DONE]' in item,
            failure_when=lambda item: b'"error":' in item,
            failure_class='upstream_rejected',
        ):
            pass

    asyncio.run(consume())

    assert attempt.outcome == 'failure'
    assert attempt.issue_class == expected_issue


def test_context_exit_defers_to_attached_stream(monkeypatch):
    _install_client_journey_metrics(monkeypatch)
    attempt = journeys.ClientJourneyAttempt('desktop_chat', 'desktop_windows')

    async def complete_stream():
        yield _DESKTOP_CHAT_DONE_FRAME

    with attempt:
        observed = attempt.observe_stream(
            complete_stream(),
            success_when=lambda item: b'data: [DONE]' in item,
            failure_when=lambda _item: False,
        )

    assert attempt.outcome is None

    async def consume():
        async for _item in observed:
            pass

    asyncio.run(consume())
    assert attempt.outcome == 'success'


def test_context_exit_without_terminal_fails(monkeypatch):
    _install_client_journey_metrics(monkeypatch)
    attempt = journeys.ClientJourneyAttempt('desktop_chat', 'desktop_windows')

    with attempt:
        pass

    assert attempt.outcome == 'failure'
    assert attempt.issue_class == 'incomplete_attempt'


@pytest.mark.parametrize('disconnect', [asyncio.CancelledError(), ClientDisconnect(), OSError('client disconnected')])
def test_streaming_attempt_disconnects_are_cancelled(monkeypatch, disconnect):
    _install_client_journey_metrics(monkeypatch)
    attempt = journeys.ClientJourneyAttempt('desktop_chat', 'desktop_macos')

    async def disconnected_stream():
        if False:
            yield b''
        raise disconnect

    async def consume():
        async for _item in attempt.observe_stream(
            disconnected_stream(),
            success_when=lambda item: b'data: [DONE]' in item,
            failure_when=lambda _item: False,
        ):
            pass

    with pytest.raises(type(disconnect)):
        asyncio.run(consume())

    assert attempt.outcome == 'cancelled'
    assert attempt.issue_class is None


def test_never_iterated_stream_is_cancelled_when_abandoned(monkeypatch):
    _install_client_journey_metrics(monkeypatch)
    attempt = journeys.ClientJourneyAttempt('desktop_chat', 'desktop_macos')

    async def source():
        yield _DESKTOP_CHAT_DONE_FRAME

    observed = attempt.observe_stream(
        source(),
        success_when=lambda item: b'data: [DONE]' in item,
        failure_when=lambda _item: False,
    )
    del observed
    gc.collect()

    assert attempt.outcome == 'cancelled'


def test_recorders_are_fail_open_and_still_report_their_own_breakage(monkeypatch, caplog):
    """A broken recorder must not break the request, and must not be silent.

    A recorder that quietly stops writing is indistinguishable from a healthy
    path with nothing to report. That is the exact failure this metric family
    exists to expose, so it must not be reproduced inside the family itself.
    """
    _install_client_journey_metrics(monkeypatch)
    monkeypatch.setattr(journeys, '_last_recorder_warning_at', 0.0)
    for name in (
        'OMI_CLIENT_JOURNEY_ACCEPTED_TOTAL',
        'OMI_CLIENT_JOURNEY_TERMINAL_TOTAL',
        'OMI_CLIENT_JOURNEY_DURATION_SECONDS',
        'OMI_CLIENT_JOURNEY_ISSUES_TOTAL',
    ):
        broken = MagicMock()
        broken.labels.side_effect = RuntimeError('metric backend is down')
        monkeypatch.setattr(journeys, name, broken)

    with caplog.at_level('WARNING'):
        journeys.record_client_journey_accepted('desktop_chat', 'desktop_macos')
        journeys.record_client_journey_terminal(
            'desktop_chat', 'desktop_macos', 'failure', 1.0, issue_class='provider_error'
        )
        broken_job = MagicMock()
        broken_job.get.side_effect = RuntimeError('provenance lookup failed')
        journeys.record_conversation_finalization_client_terminal('success', broken_job, client_kind='mobile_ios')

    assert 'client_journey_metric_record_failed' in caplog.text


def test_a_failing_recorder_never_reaches_the_user_stream(monkeypatch):
    _install_client_journey_metrics(monkeypatch)
    broken = MagicMock()
    broken.labels.side_effect = RuntimeError('metric backend is down')
    monkeypatch.setattr(journeys, 'OMI_CLIENT_JOURNEY_TERMINAL_TOTAL', broken)
    monkeypatch.setattr(journeys, 'OMI_CLIENT_JOURNEY_ACCEPTED_TOTAL', broken)

    attempt = journeys.ClientJourneyAttempt('desktop_chat', 'desktop_macos')

    async def source():
        yield b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
        yield _DESKTOP_CHAT_DONE_FRAME

    async def drain():
        return [
            item
            async for item in attempt.observe_stream(
                source(),
                success_when=lambda item: b'data: [DONE]' in item,
                failure_when=lambda item: b'"error"' in item,
            )
        ]

    delivered = asyncio.run(drain())

    assert len(delivered) == 2


def test_client_journey_metric_collector_exceptions_fail_open(monkeypatch):
    monkeypatch.setattr(
        journeys.OMI_CLIENT_JOURNEY_ACCEPTED_TOTAL,
        'labels',
        lambda **_: (_ for _ in ()).throw(RuntimeError('accepted metric unavailable')),
    )
    attempt = journeys.ClientJourneyAttempt('desktop_chat', 'desktop_macos')

    monkeypatch.setattr(
        journeys.OMI_CLIENT_JOURNEY_TERMINAL_TOTAL,
        'labels',
        lambda **_: (_ for _ in ()).throw(RuntimeError('terminal metric unavailable')),
    )
    attempt.succeed()

    assert attempt.outcome == 'success'


def test_metric_recording_failure_does_not_break_the_streamed_request(monkeypatch):
    accepted, terminal, issues, duration = _install_client_journey_metrics(monkeypatch)
    for metric in (accepted, terminal, issues, duration):
        metric.labels.side_effect = RuntimeError('metrics backend unavailable')

    attempt = journeys.ClientJourneyAttempt('mobile_chat', 'mobile_ios')

    async def response_stream():
        yield 'done: renderable-answer'

    async def consume():
        return [
            item
            async for item in attempt.observe_stream(
                response_stream(),
                success_when=lambda item: item.startswith('done: '),
                failure_when=lambda _item: False,
            )
        ]

    assert asyncio.run(consume()) == ['done: renderable-answer']
    assert attempt.outcome == 'success'
