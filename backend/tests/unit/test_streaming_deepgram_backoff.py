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
async def test_connect_uses_asyncio_to_thread():
    """connect_to_deepgram is offloaded via asyncio.to_thread to avoid blocking the event loop."""
    mock_conn = MagicMock()

    async def fake_to_thread(func, *args):
        return func(*args)

    with patch('utils.stt.streaming.connect_to_deepgram', return_value=mock_conn) as mock_connect, patch(
        'utils.stt.streaming.asyncio.to_thread', side_effect=fake_to_thread
    ) as mock_to_thread:
        result = await connect_to_deepgram_with_backoff(
            on_message=MagicMock(),
            on_error=MagicMock(),
            language='en',
            sample_rate=16000,
            channels=1,
            model='nova-2-general',
        )
    assert result is mock_conn
    mock_to_thread.assert_called_once()
    # Verify connect_to_deepgram was passed as the first arg to to_thread
    call_args = mock_to_thread.call_args
    assert call_args[0][0] is mock_connect


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
async def test_process_audio_dg_returns_gated_socket_no_gate():
    """process_audio_dg always returns GatedDeepgramSocket, even without VAD gate (#6190)."""
    from utils.stt.safe_socket import SafeDeepgramSocket
    from utils.stt.vad_gate import GatedDeepgramSocket

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
    assert isinstance(result, GatedDeepgramSocket)
    assert isinstance(result._conn, SafeDeepgramSocket)
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
    """Thread safety: concurrent send() calls while keepalive thread fires (#5870).

    Verifies no exceptions AND that keepalive actually executes during contention.
    """
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

        # Advance clock past keepalive interval FIRST so keepalive fires
        with lock:
            fake_time[0] = 3.0

        import time

        time.sleep(0.1)  # Let keepalive thread fire

        # Verify keepalive actually fired during this idle window
        assert mock_conn.keep_alive.call_count >= 1, "keepalive must fire before concurrent sends start"

        # Now start sender threads while keepalive thread continues running
        mock_conn.keep_alive.reset_mock()
        threads = [threading.Thread(target=sender) for _ in range(3)]
        for t in threads:
            t.start()
        # Advance clock again so keepalive fires during contention
        with lock:
            fake_time[0] = 6.0
        time.sleep(0.1)  # Let keepalive thread fire during send contention
        for t in threads:
            t.join(timeout=5.0)

        assert not errors, f"Concurrent send/keepalive raised: {errors}"
        assert not safe.is_connection_dead
        # Keepalive must have fired at least once during the concurrent send window
        assert mock_conn.keep_alive.call_count >= 1, "keepalive must fire during concurrent sends"
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


# ---------------------------------------------------------------------------
# Death reason and close-reason logging tests
# ---------------------------------------------------------------------------


def test_death_reason_none_when_alive():
    """death_reason is None when connection is alive."""
    from utils.stt.safe_socket import KeepaliveConfig, SafeDeepgramSocket

    mock_conn = MagicMock()
    mock_conn.send.return_value = True
    cfg = KeepaliveConfig(keepalive_interval_sec=5.0, check_period_sec=999.0)
    safe = SafeDeepgramSocket(mock_conn, cfg=cfg)
    try:
        assert safe.death_reason is None
        safe.send(b'\x00' * 960)
        assert safe.death_reason is None
    finally:
        safe.finish()


def test_death_reason_on_send_false():
    """death_reason records 'send returned False' when send returns False."""
    from utils.stt.safe_socket import KeepaliveConfig, SafeDeepgramSocket

    mock_conn = MagicMock()
    mock_conn.send.return_value = False
    cfg = KeepaliveConfig(keepalive_interval_sec=5.0, check_period_sec=999.0)
    safe = SafeDeepgramSocket(mock_conn, cfg=cfg)
    try:
        safe.send(b'\x00' * 960)
        assert safe.is_connection_dead is True
        assert safe.death_reason == 'send returned False'
    finally:
        safe.finish()


def test_death_reason_on_send_exception():
    """death_reason captures exception type and message on send failure."""
    from utils.stt.safe_socket import KeepaliveConfig, SafeDeepgramSocket

    mock_conn = MagicMock()
    mock_conn.send.side_effect = ConnectionResetError('Connection reset by peer')
    cfg = KeepaliveConfig(keepalive_interval_sec=5.0, check_period_sec=999.0)
    safe = SafeDeepgramSocket(mock_conn, cfg=cfg)
    try:
        safe.send(b'\x00' * 960)
        assert safe.is_connection_dead is True
        assert 'ConnectionResetError' in safe.death_reason
        assert 'Connection reset by peer' in safe.death_reason
    finally:
        safe.finish()


def test_death_reason_on_keepalive_false():
    """death_reason records keepalive failure when keep_alive returns False."""
    import time as _time
    from utils.stt.safe_socket import KeepaliveConfig, SafeDeepgramSocket

    mock_conn = MagicMock()
    mock_conn.send.return_value = True
    mock_conn.keep_alive.return_value = False

    fake_time = [0.0]
    cfg = KeepaliveConfig(keepalive_interval_sec=5.0, check_period_sec=0.01)
    safe = SafeDeepgramSocket(mock_conn, cfg=cfg, clock=lambda: fake_time[0])
    try:
        safe.send(b'\x00' * 960)
        fake_time[0] = 6.0
        _time.sleep(0.1)
        assert safe.is_connection_dead is True
        assert safe.death_reason == 'keep_alive returned False'
    finally:
        safe.finish()


def test_death_reason_on_keepalive_exception():
    """death_reason captures exception on keepalive failure."""
    import time as _time
    from utils.stt.safe_socket import KeepaliveConfig, SafeDeepgramSocket

    mock_conn = MagicMock()
    mock_conn.send.return_value = True
    mock_conn.keep_alive.side_effect = TimeoutError('timed out')

    fake_time = [0.0]
    cfg = KeepaliveConfig(keepalive_interval_sec=5.0, check_period_sec=0.01)
    safe = SafeDeepgramSocket(mock_conn, cfg=cfg, clock=lambda: fake_time[0])
    try:
        safe.send(b'\x00' * 960)
        fake_time[0] = 6.0
        _time.sleep(0.1)
        assert safe.is_connection_dead is True
        assert 'TimeoutError' in safe.death_reason
        assert 'timed out' in safe.death_reason
    finally:
        safe.finish()


def test_set_close_reason_stores_first_reason():
    """set_close_reason stores only the first reason (root cause)."""
    from utils.stt.safe_socket import KeepaliveConfig, SafeDeepgramSocket

    mock_conn = MagicMock()
    cfg = KeepaliveConfig(keepalive_interval_sec=5.0, check_period_sec=999.0)
    safe = SafeDeepgramSocket(mock_conn, cfg=cfg)
    try:
        assert safe.death_reason is None
        safe.set_close_reason('DG close event: code=1006')
        assert safe.death_reason == 'DG close event: code=1006'
        # Second call is a no-op
        safe.set_close_reason('DG error event: something else')
        assert safe.death_reason == 'DG close event: code=1006'
    finally:
        safe.finish()


def test_set_close_reason_does_not_override_send_death():
    """If send fails first, set_close_reason doesn't override the death reason."""
    from utils.stt.safe_socket import KeepaliveConfig, SafeDeepgramSocket

    mock_conn = MagicMock()
    mock_conn.send.side_effect = BrokenPipeError('Broken pipe')
    cfg = KeepaliveConfig(keepalive_interval_sec=5.0, check_period_sec=999.0)
    safe = SafeDeepgramSocket(mock_conn, cfg=cfg)
    try:
        safe.send(b'\x00' * 960)
        assert 'BrokenPipeError' in safe.death_reason
        # External close reason arrives after send death — should not override
        safe.set_close_reason('DG close event: code=1006')
        assert 'BrokenPipeError' in safe.death_reason
    finally:
        safe.finish()


def test_set_close_reason_does_not_override_keepalive_death():
    """If keepalive fails first, set_close_reason doesn't override the death reason."""
    import time as _time
    from utils.stt.safe_socket import KeepaliveConfig, SafeDeepgramSocket

    mock_conn = MagicMock()
    mock_conn.send.return_value = True
    mock_conn.keep_alive.side_effect = TimeoutError('timed out')

    fake_time = [0.0]
    cfg = KeepaliveConfig(keepalive_interval_sec=5.0, check_period_sec=0.01)
    safe = SafeDeepgramSocket(mock_conn, cfg=cfg, clock=lambda: fake_time[0])
    try:
        safe.send(b'\x00' * 960)
        fake_time[0] = 6.0
        _time.sleep(0.1)
        assert safe.is_connection_dead is True
        assert 'TimeoutError' in safe.death_reason
        # External close reason arrives after keepalive death — should not override
        safe.set_close_reason('DG close event: code=1006')
        assert 'TimeoutError' in safe.death_reason
    finally:
        safe.finish()


def test_close_reason_preserved_when_send_fails_after():
    """If close reason is set first, subsequent send failure does not override it (#6036)."""
    from utils.stt.safe_socket import KeepaliveConfig, SafeDeepgramSocket

    mock_conn = MagicMock()
    mock_conn.send.return_value = False
    cfg = KeepaliveConfig(keepalive_interval_sec=5.0, check_period_sec=999.0)
    safe = SafeDeepgramSocket(mock_conn, cfg=cfg)
    try:
        # DG callback fires close reason first
        safe.set_close_reason('DG close event: code=1006')
        assert safe.death_reason == 'DG close event: code=1006'
        # Then send detects death — reason must not change
        safe.send(b'\x00' * 960)
        assert safe.is_connection_dead is True
        assert safe.death_reason == 'DG close event: code=1006'
    finally:
        safe.finish()


def test_close_reason_preserved_when_keepalive_fails_after():
    """If close reason is set first, subsequent keepalive failure does not override it (#6036)."""
    import time as _time
    from utils.stt.safe_socket import KeepaliveConfig, SafeDeepgramSocket

    mock_conn = MagicMock()
    mock_conn.send.return_value = True
    mock_conn.keep_alive.return_value = False

    fake_time = [0.0]
    cfg = KeepaliveConfig(keepalive_interval_sec=5.0, check_period_sec=0.01)
    safe = SafeDeepgramSocket(mock_conn, cfg=cfg, clock=lambda: fake_time[0])
    try:
        # DG callback fires close reason first
        safe.set_close_reason('DG error event: server_error')
        # Trigger keepalive failure
        safe.send(b'\x00' * 960)
        fake_time[0] = 6.0
        _time.sleep(0.1)
        assert safe.is_connection_dead is True
        # Close reason from DG callback must be preserved
        assert safe.death_reason == 'DG error event: server_error'
    finally:
        safe.finish()


def test_close_reason_preserved_when_send_raises_after():
    """If close reason is set first, subsequent send exception does not override it (#6036)."""
    from utils.stt.safe_socket import KeepaliveConfig, SafeDeepgramSocket

    mock_conn = MagicMock()
    mock_conn.send.side_effect = ConnectionResetError('Connection reset by peer')
    cfg = KeepaliveConfig(keepalive_interval_sec=5.0, check_period_sec=999.0)
    safe = SafeDeepgramSocket(mock_conn, cfg=cfg)
    try:
        safe.set_close_reason('DG close event: code=1006')
        safe.send(b'\x00' * 960)
        assert safe.is_connection_dead is True
        assert safe.death_reason == 'DG close event: code=1006'
    finally:
        safe.finish()


def test_close_reason_preserved_when_keepalive_raises_after():
    """If close reason is set first, subsequent keepalive exception does not override it (#6036)."""
    import time as _time
    from utils.stt.safe_socket import KeepaliveConfig, SafeDeepgramSocket

    mock_conn = MagicMock()
    mock_conn.send.return_value = True
    mock_conn.keep_alive.side_effect = TimeoutError('timed out')

    fake_time = [0.0]
    cfg = KeepaliveConfig(keepalive_interval_sec=5.0, check_period_sec=0.01)
    safe = SafeDeepgramSocket(mock_conn, cfg=cfg, clock=lambda: fake_time[0])
    try:
        safe.set_close_reason('DG error event: server_error')
        safe.send(b'\x00' * 960)
        fake_time[0] = 6.0
        _time.sleep(0.1)
        assert safe.is_connection_dead is True
        assert safe.death_reason == 'DG error event: server_error'
    finally:
        safe.finish()


# ---------------------------------------------------------------------------
# DG callback wiring tests (streaming.py)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_audio_dg_registers_close_error_handlers():
    """process_audio_dg registers Close and Error handlers on dg_connection (#6036)."""
    from utils.stt.vad_gate import GatedDeepgramSocket

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
    assert isinstance(result, GatedDeepgramSocket)

    # Verify .on() was called for Close and Error events
    on_calls = mock_dg_conn.on.call_args_list
    registered_events = [call[0][0] for call in on_calls]
    LiveTranscriptionEvents = sys.modules['deepgram'].LiveTranscriptionEvents
    assert LiveTranscriptionEvents.Close in registered_events
    assert LiveTranscriptionEvents.Error in registered_events

    # Invoke the close handler and verify it sets death_reason via delegation
    for call in on_calls:
        event, handler = call[0][0], call[0][1]
        if event == LiveTranscriptionEvents.Close:
            handler(None, 'CloseResponse(type=Close)')
            break
    assert result.death_reason == 'DG close event: CloseResponse(type=Close)'
    result.finish()


@pytest.mark.asyncio
async def test_process_audio_dg_error_handler_sets_death_reason():
    """process_audio_dg Error handler feeds into set_close_reason (#6036)."""
    from utils.stt.vad_gate import GatedDeepgramSocket

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
    assert isinstance(result, GatedDeepgramSocket)

    on_calls = mock_dg_conn.on.call_args_list
    LiveTranscriptionEvents = sys.modules['deepgram'].LiveTranscriptionEvents
    for call in on_calls:
        event, handler = call[0][0], call[0][1]
        if event == LiveTranscriptionEvents.Error:
            handler(None, 'ErrorResponse(message=server_error)')
            break
    assert result.death_reason == 'DG error event: ErrorResponse(message=server_error)'
    result.finish()


# ---------------------------------------------------------------------------
# stream_transcript callback contract tests (#6190)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_transcript_injects_stt_start_stt_end():
    """process_audio_dg wrapper should inject stt_start/stt_end into forwarded segments (#6190).

    Captures the on_message callback from process_audio_dg, fires it with a mock
    DG result, and verifies the original stream_transcript receives segments with
    stt_start/stt_end set to the raw DG timestamps.
    """
    received = []
    original_transcript = lambda segs: received.extend(segs)

    mock_dg_conn = MagicMock()
    captured_on_message = None

    async def capture_backoff(on_message, on_error, *args, **kwargs):
        nonlocal captured_on_message
        captured_on_message = on_message
        return mock_dg_conn

    with patch('utils.stt.streaming.connect_to_deepgram_with_backoff', new=capture_backoff):
        await process_audio_dg(
            stream_transcript=original_transcript,
            language='en',
            sample_rate=16000,
            channels=1,
        )

    assert captured_on_message is not None, "on_message should have been captured"

    # Build a mock DG result with one word
    mock_word = MagicMock()
    mock_word.speaker = 0
    mock_word.start = 1.5
    mock_word.end = 2.3
    mock_word.punctuated_word = "Hello"

    mock_result = MagicMock()
    mock_result.channel.alternatives = [MagicMock()]
    mock_result.channel.alternatives[0].transcript = "Hello"
    mock_result.channel.alternatives[0].words = [mock_word]

    # Fire the callback
    captured_on_message(None, mock_result)

    assert len(received) == 1
    seg = received[0]
    assert seg['stt_start'] == 1.5, "stt_start should equal raw DG start"
    assert seg['stt_end'] == 2.3, "stt_end should equal raw DG end"
    assert seg['start'] == 1.5, "start should be unmodified (no gate)"
    assert seg['end'] == 2.3, "end should be unmodified (no gate)"


@pytest.mark.asyncio
async def test_stream_transcript_stt_preserved_before_remap():
    """With VAD gate, stt_start/stt_end should be preserved before wall-clock remapping (#6190)."""
    from utils.stt.vad_gate import VADStreamingGate

    received = []
    original_transcript = lambda segs: received.extend(segs)

    mock_dg_conn = MagicMock()
    captured_on_message = None

    async def capture_backoff(on_message, on_error, *args, **kwargs):
        nonlocal captured_on_message
        captured_on_message = on_message
        return mock_dg_conn

    mock_gate = VADStreamingGate(sample_rate=16000, channels=1, mode='active', uid='test', session_id='test')
    # Seed mapper with offset so remap changes start/end
    mock_gate.dg_wall_mapper.on_audio_sent(chunk_duration_sec=5.0, chunk_wall_rel_sec=100.0)

    with patch('utils.stt.streaming.connect_to_deepgram_with_backoff', new=capture_backoff):
        await process_audio_dg(
            stream_transcript=original_transcript,
            language='en',
            sample_rate=16000,
            channels=1,
            vad_gate=mock_gate,
        )

    mock_word = MagicMock()
    mock_word.speaker = 0
    mock_word.start = 1.0
    mock_word.end = 2.0
    mock_word.punctuated_word = "Test"

    mock_result = MagicMock()
    mock_result.channel.alternatives = [MagicMock()]
    mock_result.channel.alternatives[0].transcript = "Test"
    mock_result.channel.alternatives[0].words = [mock_word]

    captured_on_message(None, mock_result)

    assert len(received) == 1
    seg = received[0]
    assert seg['stt_start'] == 1.0, "stt_start should preserve raw DG time"
    assert seg['stt_end'] == 2.0, "stt_end should preserve raw DG time"
    # start/end should be remapped to wall-clock
    assert seg['start'] != 1.0, "start should have been remapped by gate"


# ---------------------------------------------------------------------------
# GatedDeepgramSocket death_reason delegation tests
# ---------------------------------------------------------------------------


def test_gated_socket_death_reason_delegates_to_safe_socket():
    """GatedDeepgramSocket.death_reason returns underlying SafeDeepgramSocket reason (#6036)."""
    from utils.stt.safe_socket import KeepaliveConfig, SafeDeepgramSocket
    from utils.stt.vad_gate import GatedDeepgramSocket

    mock_conn = MagicMock()
    cfg = KeepaliveConfig(keepalive_interval_sec=5.0, check_period_sec=999.0)
    safe = SafeDeepgramSocket(mock_conn, cfg=cfg)
    gated = GatedDeepgramSocket(safe, gate=None)
    try:
        assert gated.death_reason is None
        safe.set_close_reason('DG close event: code=1006')
        assert gated.death_reason == 'DG close event: code=1006'
    finally:
        safe.finish()


def test_gated_socket_death_reason_delegates_none_when_alive():
    """GatedDeepgramSocket.death_reason returns None when SafeDeepgramSocket has no reason."""
    from utils.stt.safe_socket import KeepaliveConfig, SafeDeepgramSocket
    from utils.stt.vad_gate import GatedDeepgramSocket

    mock_conn = MagicMock()
    cfg = KeepaliveConfig(keepalive_interval_sec=5.0, check_period_sec=999.0)
    safe = SafeDeepgramSocket(mock_conn, cfg=cfg)
    gated = GatedDeepgramSocket(safe, gate=None)
    try:
        assert gated.death_reason is None
    finally:
        safe.finish()
