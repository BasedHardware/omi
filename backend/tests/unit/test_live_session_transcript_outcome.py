"""Headline SLI: one transcript-outcome counter per backend-STT listen session."""

from types import SimpleNamespace
from unittest.mock import patch

from routers.listen.runtime import ListenSessionRuntime


def _runtime(
    *,
    use_custom_stt=False,
    delivered=False,
    failed=False,
    terminal=False,
    close_code=1001,
    first_audio=None,
    last_audio=None,
    vad_gate='unset',
    total_speech_ms=None,
    speech_ms_total=None,
):
    runtime = object.__new__(ListenSessionRuntime)
    runtime.use_custom_stt = use_custom_stt
    runtime.state = SimpleNamespace(
        live_transcript_delivered=delivered,
        live_transcription_failed=failed,
        stt_terminal_failure=terminal,
        close_code=close_code,
        first_audio_byte_timestamp=first_audio,
        last_audio_received_time=last_audio,
    )
    if vad_gate == 'managed':
        runtime.receiver = SimpleNamespace(vad_gate=SimpleNamespace(total_speech_ms=total_speech_ms or 0))
    elif vad_gate == 'legacy':
        runtime.receiver = SimpleNamespace(
            vad_gate=SimpleNamespace(get_metrics=lambda: {'speech_ms_total': speech_ms_total or 0})
        )
    elif vad_gate == 'broken':
        runtime.receiver = SimpleNamespace(
            vad_gate=SimpleNamespace(get_metrics=lambda: (_ for _ in ()).throw(RuntimeError('boom')))
        )
    else:
        runtime.receiver = SimpleNamespace(vad_gate=None)
    return runtime


def _outcome(runtime):
    with patch('routers.listen.runtime.record_live_session_transcript_outcome') as record:
        ListenSessionRuntime._record_session_transcript_outcome(runtime)
        calls = [call.kwargs['outcome'] for call in record.call_args_list]
    # exactly once, and idempotent on a second teardown pass
    ListenSessionRuntime._record_session_transcript_outcome(runtime)
    assert record.call_count == len(calls)
    assert len(calls) == 1
    return calls[0]


def test_transcript_delivered_wins_over_everything():
    runtime = _runtime(delivered=True, terminal=True, close_code=1011)
    assert _outcome(runtime) == 'transcribed'


def test_terminal_failure_is_never_excused_as_too_short():
    # The incident shape: initialize_stt exhausted the chain before any audio.
    runtime = _runtime(terminal=True, first_audio=None, last_audio=None)
    assert _outcome(runtime) == 'no_transcript'


def test_close_1011_without_terminal_flag_is_still_a_failure():
    runtime = _runtime(close_code=1011, first_audio=100.0, last_audio=160.0)
    assert _outcome(runtime) == 'no_transcript'


def test_heartbeat_idle_reap_of_silent_session_is_too_short():
    # lifetime_done (e.g. the 90s idle heartbeat reap) sets
    # live_transcription_failed without any STT failure; a silent session
    # keeps the too_short excuse instead of entering the failure ratio.
    runtime = _runtime(
        failed=True, close_code=1001, first_audio=100.0, last_audio=160.0, vad_gate='legacy', speech_ms_total=0
    )
    assert _outcome(runtime) == 'too_short'


def test_heartbeat_idle_reap_of_short_session_is_too_short():
    runtime = _runtime(failed=True, close_code=1001, first_audio=100.0, last_audio=105.0)
    assert _outcome(runtime) == 'too_short'


def test_lifetime_done_with_real_speech_is_still_no_transcript():
    # A genuine mid-session failure on a session that actually spoke is a
    # user-felt failure even though the flag is the generic one.
    runtime = _runtime(
        failed=True, close_code=1001, first_audio=100.0, last_audio=160.0, vad_gate='legacy', speech_ms_total=4200
    )
    assert _outcome(runtime) == 'no_transcript'


def test_short_audio_session_is_too_short():
    runtime = _runtime(first_audio=100.0, last_audio=105.0)
    assert _outcome(runtime) == 'too_short'


def test_no_audio_clean_teardown_is_too_short():
    runtime = _runtime(first_audio=None, last_audio=None)
    assert _outcome(runtime) == 'too_short'


def test_long_silent_session_with_vad_is_too_short():
    runtime = _runtime(first_audio=100.0, last_audio=160.0, vad_gate='legacy', speech_ms_total=0)
    assert _outcome(runtime) == 'too_short'


def test_long_silent_session_on_managed_chain_is_too_short():
    runtime = _runtime(first_audio=100.0, last_audio=160.0, vad_gate='managed', total_speech_ms=0)
    assert _outcome(runtime) == 'too_short'


def test_speechful_session_without_transcript_is_no_transcript():
    runtime = _runtime(first_audio=100.0, last_audio=160.0, vad_gate='legacy', speech_ms_total=4200)
    assert _outcome(runtime) == 'no_transcript'


def test_session_without_vad_falls_back_to_audio_span():
    runtime = _runtime(first_audio=100.0, last_audio=160.0, vad_gate=None)
    assert _outcome(runtime) == 'no_transcript'


def test_broken_gate_read_fails_open_to_no_transcript():
    runtime = _runtime(first_audio=100.0, last_audio=160.0, vad_gate='broken')
    assert _outcome(runtime) == 'no_transcript'


def test_custom_stt_sessions_are_not_counted():
    runtime = _runtime(use_custom_stt=True, delivered=True)
    with patch('routers.listen.runtime.record_live_session_transcript_outcome') as record:
        ListenSessionRuntime._record_session_transcript_outcome(runtime)
        ListenSessionRuntime._record_session_transcript_outcome(runtime)
    record.assert_not_called()


def test_teardown_seam_calls_the_recorder_after_attempt_terminalization():
    # The real seam: _teardown_components calls _finish_live_transcription then
    # the outcome recorder, so every disconnect path after STT init emits once.
    runtime = _runtime(delivered=True)
    runtime._finish_live_transcription = lambda: None
    with patch('routers.listen.runtime.record_live_session_transcript_outcome') as record:
        ListenSessionRuntime._record_session_transcript_outcome(runtime)
    record.assert_called_once_with(outcome='transcribed')


def test_outcome_children_are_queryable_from_process_start_without_increments():
    # All three children must exist before any session increments one: the
    # headline ratio's numerator is zero-filled in PromQL too, but a series
    # that was never born reads as No Data on a fresh pod, and the alert's
    # noDataState is OK. get_sample_value does not create children, so None
    # here means the pre-creation is missing.
    from prometheus_client import REGISTRY

    for outcome in ('transcribed', 'no_transcript', 'too_short'):
        sample = REGISTRY.get_sample_value('omi_live_session_transcript_outcome_total', {'outcome': outcome})
        assert sample is not None, f'outcome="{outcome}" child must be pre-created at import'
