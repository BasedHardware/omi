"""Unit tests for connect_to_deepgram_with_backoff (Issue #5577).

Verifies:
- async sleep instead of blocking time.sleep
- is_active callback aborts retries on client disconnect
- normal retry and raise-on-exhaustion behavior preserved
"""

import asyncio
import sys
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

# Mock heavy dependencies before importing streaming module
_mock_modules = {}
for mod_name in [
    'database',
    'database._client',
    'database.users',
    'utils.other.storage',
    'utils.stt.soniox_util',
    'deepgram',
    'deepgram.clients',
    'deepgram.clients.live',
    'deepgram.clients.live.v1',
    'websockets',
    'websockets.exceptions',
]:
    if mod_name not in sys.modules:
        _mock_modules[mod_name] = MagicMock()
        sys.modules[mod_name] = _mock_modules[mod_name]

# Provide expected attributes for type-annotation imports
sys.modules['deepgram'].DeepgramClient = MagicMock
sys.modules['deepgram'].DeepgramClientOptions = MagicMock
sys.modules['deepgram'].LiveTranscriptionEvents = MagicMock()
sys.modules['deepgram.clients.live.v1'].LiveOptions = MagicMock

from utils.stt.streaming import connect_to_deepgram_with_backoff, process_audio_dg  # noqa: E402
from utils.stt.streaming import deepgram_options, deepgram_cloud_options  # noqa: E402


@pytest.mark.asyncio
async def test_returns_connection_on_first_success():
    """First successful connect_to_deepgram call returns immediately, no sleep."""
    mock_conn = MagicMock()
    with patch('utils.stt.streaming.connect_to_deepgram', return_value=mock_conn):
        result = await connect_to_deepgram_with_backoff(
            on_message=MagicMock(),
            on_error=MagicMock(),
            language='en',
            sample_rate=16000,
            channels=1,
            model='nova-2-general',
        )
    assert result is mock_conn


@pytest.mark.asyncio
async def test_retries_with_async_sleep():
    """On failure, retries use asyncio.sleep (non-blocking), not time.sleep."""
    mock_conn = MagicMock()
    call_count = 0

    def fail_then_succeed(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("DG connection failed")
        return mock_conn

    sleep_calls = []

    async def fake_sleep(duration):
        sleep_calls.append(duration)

    with patch('utils.stt.streaming.connect_to_deepgram', side_effect=fail_then_succeed), patch(
        'utils.stt.streaming.asyncio.sleep', side_effect=fake_sleep
    ):
        result = await connect_to_deepgram_with_backoff(
            on_message=MagicMock(),
            on_error=MagicMock(),
            language='en',
            sample_rate=16000,
            channels=1,
            model='nova-2-general',
            retries=3,
        )

    assert result is mock_conn
    assert call_count == 3
    assert len(sleep_calls) == 2  # slept between attempt 1->2 and 2->3


@pytest.mark.asyncio
async def test_raises_after_all_retries_exhausted():
    """After all retries fail, the last exception is raised."""

    async def fake_sleep(duration):
        pass

    with patch('utils.stt.streaming.connect_to_deepgram', side_effect=Exception("DG fail")), patch(
        'utils.stt.streaming.asyncio.sleep', side_effect=fake_sleep
    ):
        with pytest.raises(Exception, match="DG fail"):
            await connect_to_deepgram_with_backoff(
                on_message=MagicMock(),
                on_error=MagicMock(),
                language='en',
                sample_rate=16000,
                channels=1,
                model='nova-2-general',
                retries=3,
            )


@pytest.mark.asyncio
async def test_aborts_before_first_attempt_when_inactive():
    """If is_active returns False before the first attempt, returns None immediately."""
    with patch('utils.stt.streaming.connect_to_deepgram') as mock_connect:
        result = await connect_to_deepgram_with_backoff(
            on_message=MagicMock(),
            on_error=MagicMock(),
            language='en',
            sample_rate=16000,
            channels=1,
            model='nova-2-general',
            is_active=lambda: False,
        )
    assert result is None
    mock_connect.assert_not_called()


@pytest.mark.asyncio
async def test_aborts_between_retries_when_inactive():
    """If is_active flips to False between retries, returns None."""
    active = [True]

    def fail_and_deactivate(*args, **kwargs):
        active[0] = False  # simulate client disconnect after first failure
        raise Exception("DG fail")

    async def fake_sleep(duration):
        pass

    with patch('utils.stt.streaming.connect_to_deepgram', side_effect=fail_and_deactivate), patch(
        'utils.stt.streaming.asyncio.sleep', side_effect=fake_sleep
    ):
        result = await connect_to_deepgram_with_backoff(
            on_message=MagicMock(),
            on_error=MagicMock(),
            language='en',
            sample_rate=16000,
            channels=1,
            model='nova-2-general',
            retries=3,
            is_active=lambda: active[0],
        )
    assert result is None


@pytest.mark.asyncio
async def test_is_active_none_skips_check():
    """When is_active is None (default), retries proceed normally without abort checks."""
    mock_conn = MagicMock()
    call_count = 0

    def fail_once(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("transient")
        return mock_conn

    async def fake_sleep(duration):
        pass

    with patch('utils.stt.streaming.connect_to_deepgram', side_effect=fail_once), patch(
        'utils.stt.streaming.asyncio.sleep', side_effect=fake_sleep
    ):
        result = await connect_to_deepgram_with_backoff(
            on_message=MagicMock(),
            on_error=MagicMock(),
            language='en',
            sample_rate=16000,
            channels=1,
            model='nova-2-general',
            retries=3,
            is_active=None,
        )
    assert result is mock_conn
    assert call_count == 2


@pytest.mark.asyncio
async def test_retries_zero_raises_immediately():
    """With retries=0, the loop body never executes and the fallback exception is raised."""
    with patch('utils.stt.streaming.connect_to_deepgram') as mock_connect:
        with pytest.raises(Exception, match="All retry attempts failed"):
            await connect_to_deepgram_with_backoff(
                on_message=MagicMock(),
                on_error=MagicMock(),
                language='en',
                sample_rate=16000,
                channels=1,
                model='nova-2-general',
                retries=0,
            )
    mock_connect.assert_not_called()


@pytest.mark.asyncio
async def test_retries_one_failure_raises_no_sleep():
    """With retries=1, a single failure raises immediately with no sleep."""
    sleep_calls = []

    async def fake_sleep(duration):
        sleep_calls.append(duration)

    with patch('utils.stt.streaming.connect_to_deepgram', side_effect=Exception("DG fail")), patch(
        'utils.stt.streaming.asyncio.sleep', side_effect=fake_sleep
    ):
        with pytest.raises(Exception, match="DG fail"):
            await connect_to_deepgram_with_backoff(
                on_message=MagicMock(),
                on_error=MagicMock(),
                language='en',
                sample_rate=16000,
                channels=1,
                model='nova-2-general',
                retries=1,
            )
    assert len(sleep_calls) == 0  # no sleep with only 1 retry


@pytest.mark.asyncio
async def test_process_audio_dg_returns_none_when_inactive():
    """process_audio_dg returns None when is_active aborts the connection."""
    with patch('utils.stt.streaming.connect_to_deepgram_with_backoff', new_callable=AsyncMock, return_value=None):
        result = await process_audio_dg(
            stream_transcript=MagicMock(),
            language='en',
            sample_rate=16000,
            channels=1,
            is_active=lambda: False,
        )
    assert result is None


@pytest.mark.asyncio
async def test_process_audio_dg_no_vad_wrap_on_none():
    """process_audio_dg does not wrap None with GatedDeepgramSocket when VAD gate is provided."""
    mock_gate = MagicMock()
    with patch('utils.stt.streaming.connect_to_deepgram_with_backoff', new_callable=AsyncMock, return_value=None):
        result = await process_audio_dg(
            stream_transcript=MagicMock(),
            language='en',
            sample_rate=16000,
            channels=1,
            vad_gate=mock_gate,
            is_active=lambda: False,
        )
    assert result is None


def test_deepgram_options_no_keepalive():
    """SDK keepalive option must not be present — it spawns a dangerous background thread (#5870)."""
    for name, opts in [('deepgram_options', deepgram_options), ('deepgram_cloud_options', deepgram_cloud_options)]:
        # DeepgramClientOptions stores options dict — keepalive key must be absent
        if hasattr(opts, 'options') and isinstance(opts.options, dict):
            assert 'keepalive' not in opts.options, f'{name} must not contain "keepalive" key'


@pytest.mark.asyncio
async def test_process_audio_dg_returns_safe_socket_no_gate():
    """process_audio_dg returns SafeDeepgramSocket when no VAD gate provided (#5870)."""
    from utils.stt.safe_socket import SafeDeepgramSocket

    mock_dg_conn = MagicMock()
    with patch(
        'utils.stt.streaming.connect_to_deepgram_with_backoff', new_callable=AsyncMock, return_value=mock_dg_conn
    ):
        result = await process_audio_dg(
            stream_transcript=MagicMock(),
            language='en',
            sample_rate=16000,
            channels=1,
        )
    assert isinstance(result, SafeDeepgramSocket)
    assert result.is_connection_dead is False
    result.finish()


@pytest.mark.asyncio
async def test_process_audio_dg_returns_gated_socket_with_gate():
    """process_audio_dg returns GatedDeepgramSocket wrapping SafeDeepgramSocket when VAD gate provided (#5870)."""
    from utils.stt.safe_socket import SafeDeepgramSocket
    from utils.stt.vad_gate import GatedDeepgramSocket, VADStreamingGate

    mock_dg_conn = MagicMock()
    mock_gate = VADStreamingGate(sample_rate=16000, channels=1, mode='active', uid='test', session_id='test')
    with patch(
        'utils.stt.streaming.connect_to_deepgram_with_backoff', new_callable=AsyncMock, return_value=mock_dg_conn
    ):
        result = await process_audio_dg(
            stream_transcript=MagicMock(),
            language='en',
            sample_rate=16000,
            channels=1,
            vad_gate=mock_gate,
        )
    assert isinstance(result, GatedDeepgramSocket)
    assert isinstance(result._conn, SafeDeepgramSocket)
    assert result.is_connection_dead is False
    result.finish()


def test_auto_keepalive_sends_during_idle():
    """SafeDeepgramSocket auto-keepalive thread sends keepalive when idle > interval (#5870).

    Uses injectable clock to simulate time passing without real sleeps.
    The background thread detects idle time and sends keepalive automatically.
    """
    from utils.stt.safe_socket import KeepaliveConfig, SafeDeepgramSocket

    mock_conn = MagicMock()
    mock_conn.keep_alive.return_value = True
    mock_conn.send.return_value = True

    # Use a fake clock that we control
    fake_time = [0.0]

    def clock():
        return fake_time[0]

    # Short check period so the thread fires quickly
    cfg = KeepaliveConfig(keepalive_interval_sec=5.0, check_period_sec=0.01)
    safe = SafeDeepgramSocket(mock_conn, cfg=cfg, clock=clock)

    try:
        # First send — resets activity timer
        safe.send(b'\x00' * 960)
        assert mock_conn.send.call_count == 1

        # Advance clock past keepalive interval
        fake_time[0] = 6.0

        # Wait for background thread to fire
        import time

        time.sleep(0.1)

        # Background thread should have sent keepalive
        assert mock_conn.keep_alive.call_count >= 1
        assert safe.keepalive_count >= 1
        assert safe.is_connection_dead is False
    finally:
        safe.finish()


def test_auto_keepalive_stops_on_dead():
    """Auto-keepalive thread stops when connection dies (#5870)."""
    from utils.stt.safe_socket import KeepaliveConfig, SafeDeepgramSocket

    mock_conn = MagicMock()
    mock_conn.keep_alive.return_value = False  # Connection dead
    mock_conn.send.return_value = True

    fake_time = [0.0]

    def clock():
        return fake_time[0]

    cfg = KeepaliveConfig(keepalive_interval_sec=5.0, check_period_sec=0.01)
    safe = SafeDeepgramSocket(mock_conn, cfg=cfg, clock=clock)

    try:
        safe.send(b'\x00' * 960)
        # Advance clock past keepalive interval
        fake_time[0] = 6.0

        import time

        time.sleep(0.1)

        # keep_alive returned False — should be dead
        assert safe.is_connection_dead is True
        # No more keepalives should be sent after death
        count_at_death = mock_conn.keep_alive.call_count
        fake_time[0] = 12.0
        time.sleep(0.1)
        assert mock_conn.keep_alive.call_count == count_at_death
    finally:
        safe.finish()


def test_auto_keepalive_resets_on_send():
    """send() resets idle timer, preventing unnecessary keepalives (#5870)."""
    from utils.stt.safe_socket import KeepaliveConfig, SafeDeepgramSocket

    mock_conn = MagicMock()
    mock_conn.keep_alive.return_value = True
    mock_conn.send.return_value = True

    fake_time = [0.0]

    def clock():
        return fake_time[0]

    cfg = KeepaliveConfig(keepalive_interval_sec=5.0, check_period_sec=0.01)
    safe = SafeDeepgramSocket(mock_conn, cfg=cfg, clock=clock)

    try:
        # Send at t=0
        safe.send(b'\x00' * 960)
        # Advance to t=4 (within interval)
        fake_time[0] = 4.0
        # Send again — resets timer
        safe.send(b'\x00' * 960)
        # Advance to t=8 (only 4s since last send, within interval)
        fake_time[0] = 8.0

        import time

        time.sleep(0.1)

        # No keepalive should have been sent (always within interval)
        assert mock_conn.keep_alive.call_count == 0
    finally:
        safe.finish()


def test_keepalive_config_validation():
    """KeepaliveConfig rejects invalid values (#5870)."""
    from utils.stt.safe_socket import KeepaliveConfig

    with pytest.raises(ValueError, match='keepalive_interval_sec must be > 0'):
        KeepaliveConfig(keepalive_interval_sec=0)

    with pytest.raises(ValueError, match='check_period_sec must be > 0'):
        KeepaliveConfig(check_period_sec=-1)


def test_concurrent_send_and_keepalive():
    """Thread safety: concurrent send() calls while keepalive thread fires (#5870)."""
    import threading
    from utils.stt.safe_socket import KeepaliveConfig, SafeDeepgramSocket

    mock_conn = MagicMock()
    mock_conn.keep_alive.return_value = True
    mock_conn.send.return_value = True

    fake_time = [0.0]
    lock = threading.Lock()

    def clock():
        with lock:
            return fake_time[0]

    cfg = KeepaliveConfig(keepalive_interval_sec=2.0, check_period_sec=0.01)
    safe = SafeDeepgramSocket(mock_conn, cfg=cfg, clock=clock)

    try:
        errors = []

        def sender():
            for i in range(50):
                try:
                    safe.send(b'\x00' * 960)
                except Exception as e:
                    errors.append(e)

        # Start sender threads while advancing clock past keepalive interval
        threads = [threading.Thread(target=sender) for _ in range(3)]
        for t in threads:
            t.start()
        with lock:
            fake_time[0] = 3.0  # trigger keepalive
        for t in threads:
            t.join(timeout=5.0)

        assert not errors, f"Concurrent send/keepalive raised: {errors}"
        assert not safe.is_connection_dead
    finally:
        safe.finish()


def test_keepalive_fires_at_exact_threshold():
    """Keepalive fires when elapsed == interval (boundary) (#5870)."""
    from utils.stt.safe_socket import KeepaliveConfig, SafeDeepgramSocket

    mock_conn = MagicMock()
    mock_conn.keep_alive.return_value = True
    mock_conn.send.return_value = True

    fake_time = [0.0]

    def clock():
        return fake_time[0]

    cfg = KeepaliveConfig(keepalive_interval_sec=5.0, check_period_sec=0.01)
    safe = SafeDeepgramSocket(mock_conn, cfg=cfg, clock=clock)

    try:
        safe.send(b'\x00' * 960)
        # Advance to exactly the threshold
        fake_time[0] = 5.0
        import time

        time.sleep(0.1)
        assert mock_conn.keep_alive.call_count >= 1
    finally:
        safe.finish()


def test_repeated_idle_sends_multiple_keepalives():
    """Repeated idle periods send multiple keepalives (#5870)."""
    from utils.stt.safe_socket import KeepaliveConfig, SafeDeepgramSocket

    mock_conn = MagicMock()
    mock_conn.keep_alive.return_value = True
    mock_conn.send.return_value = True

    # Use a list that we mutate as keepalive resets _last_activity via clock
    fake_time = [0.0]

    def clock():
        return fake_time[0]

    cfg = KeepaliveConfig(keepalive_interval_sec=5.0, check_period_sec=0.01)
    safe = SafeDeepgramSocket(mock_conn, cfg=cfg, clock=clock)

    try:
        import time

        # First keepalive at t=6
        fake_time[0] = 6.0
        time.sleep(0.1)
        first_count = mock_conn.keep_alive.call_count
        assert first_count >= 1

        # Second keepalive at t=12 (6s after keepalive reset at t=6)
        fake_time[0] = 12.0
        time.sleep(0.1)
        assert mock_conn.keep_alive.call_count > first_count
    finally:
        safe.finish()


def test_send_after_finish_is_noop():
    """send() and finalize() after finish() are silent no-ops (#5870)."""
    from utils.stt.safe_socket import KeepaliveConfig, SafeDeepgramSocket

    mock_conn = MagicMock()
    mock_conn.send.return_value = True

    cfg = KeepaliveConfig(keepalive_interval_sec=5.0, check_period_sec=999.0)
    safe = SafeDeepgramSocket(mock_conn, cfg=cfg)

    safe.finish()
    mock_conn.send.reset_mock()
    mock_conn.finalize.reset_mock()

    # These should not raise or forward to underlying connection
    safe.send(b'\x00' * 960)
    safe.finalize()
    mock_conn.send.assert_not_called()
    mock_conn.finalize.assert_not_called()


def test_profile_socket_routing_when_main_dies():
    """Profile socket continues receiving audio when main DG socket dies (#5870).

    Mimics the routing logic in transcribe.py flush_stt_buffer: when dg_socket
    is_connection_dead becomes True, profile socket should still get chunks.
    """
    from utils.stt.safe_socket import KeepaliveConfig, SafeDeepgramSocket

    # Main socket that is dead
    mock_main_conn = MagicMock()
    cfg = KeepaliveConfig(keepalive_interval_sec=5.0, check_period_sec=999.0)
    main_socket = SafeDeepgramSocket(mock_main_conn, cfg=cfg)
    main_socket._dg_dead = True  # Simulate dead connection

    # Profile socket still alive
    mock_profile_conn = MagicMock()
    profile_socket = SafeDeepgramSocket(mock_profile_conn, cfg=cfg)

    try:
        # Simulate routing logic from transcribe.py:2308-2348
        dg_socket = main_socket
        deepgram_profile_socket = profile_socket
        profile_complete = False
        chunk = b'\x00' * 960

        # Dead check (separated from routing)
        if dg_socket is not None and dg_socket.is_connection_dead:
            dg_socket = None

        # Routing
        if dg_socket is not None:
            if profile_complete or not deepgram_profile_socket:
                dg_socket.send(chunk)
            else:
                deepgram_profile_socket.send(chunk)
        elif deepgram_profile_socket and not profile_complete:
            deepgram_profile_socket.send(chunk)

        # Profile socket should have received the chunk
        mock_profile_conn.send.assert_called_once_with(chunk)
        # Main socket should NOT have received anything
        mock_main_conn.send.assert_not_called()
    finally:
        main_socket.finish()
        profile_socket.finish()
