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
    'utils.stt.vad_gate',
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
sys.modules['utils.stt.vad_gate'].GatedDeepgramSocket = MagicMock

from utils.stt.streaming import connect_to_deepgram_with_backoff, process_audio_dg  # noqa: E402


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
