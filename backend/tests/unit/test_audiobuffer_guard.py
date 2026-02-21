"""
Tests for audiobuffer guard logic in pusher.py (PR #4826).
Verifies that audio buffers only accumulate when there's a consumer,
preventing unbounded memory growth for users without audio apps.
"""


def audiobuffer_guard(
    audio_data: bytes,
    has_audio_apps_enabled: bool,
    audio_bytes_webhook_delay_seconds,
    trigger_audiobuffer: bytearray,
    audiobuffer: bytearray,
) -> tuple:
    """
    Extracted guard logic from pusher.py websocket_endpoint (header_type == 101).
    Returns (trigger_audiobuffer, audiobuffer) after applying guards.
    """
    if has_audio_apps_enabled:
        trigger_audiobuffer.extend(audio_data)
    if audio_bytes_webhook_delay_seconds is not None:
        audiobuffer.extend(audio_data)
    return trigger_audiobuffer, audiobuffer


def webhook_send_condition(
    audio_bytes_webhook_delay_seconds,
    audiobuffer_len: int,
    sample_rate: int,
) -> bool:
    """
    Extracted send condition from pusher.py (line ~430).
    Returns True if audiobuffer should be flushed to webhook.
    """
    return (
        audio_bytes_webhook_delay_seconds is not None
        and audiobuffer_len > sample_rate * audio_bytes_webhook_delay_seconds * 2
    )


class TestAudiobufferGuard:
    """Test guard conditions that prevent unbounded buffer growth."""

    def test_no_apps_no_webhook_both_empty(self):
        """Both consumers off: buffers stay at 0."""
        trigger = bytearray()
        audio = bytearray()
        trigger, audio = audiobuffer_guard(b'\x00' * 1000, False, None, trigger, audio)
        assert len(trigger) == 0
        assert len(audio) == 0

    def test_apps_enabled_extends_trigger_only(self):
        """has_audio_apps_enabled=True, delay=None: only trigger buffer grows."""
        trigger = bytearray()
        audio = bytearray()
        data = b'\x00' * 500
        trigger, audio = audiobuffer_guard(data, True, None, trigger, audio)
        assert len(trigger) == 500
        assert len(audio) == 0

    def test_webhook_enabled_extends_audio_only(self):
        """has_audio_apps_enabled=False, delay set: only audiobuffer grows."""
        trigger = bytearray()
        audio = bytearray()
        data = b'\x00' * 500
        trigger, audio = audiobuffer_guard(data, False, 5, trigger, audio)
        assert len(trigger) == 0
        assert len(audio) == 500

    def test_both_enabled_extends_both(self):
        """Both consumers active: both buffers grow."""
        trigger = bytearray()
        audio = bytearray()
        data = b'\x00' * 500
        trigger, audio = audiobuffer_guard(data, True, 5, trigger, audio)
        assert len(trigger) == 500
        assert len(audio) == 500

    def test_delay_zero_extends_audiobuffer(self):
        """delay=0 means immediate, NOT disabled. audiobuffer must still grow."""
        trigger = bytearray()
        audio = bytearray()
        data = b'\x00' * 500
        trigger, audio = audiobuffer_guard(data, False, 0, trigger, audio)
        assert len(trigger) == 0
        assert len(audio) == 500

    def test_delay_zero_vs_none_distinction(self):
        """delay=0 (immediate) and delay=None (disabled) are different."""
        # delay=0: buffer extends
        audio_zero = bytearray()
        audiobuffer_guard(b'\x00' * 100, False, 0, bytearray(), audio_zero)
        assert len(audio_zero) == 100

        # delay=None: buffer stays empty
        audio_none = bytearray()
        audiobuffer_guard(b'\x00' * 100, False, None, bytearray(), audio_none)
        assert len(audio_none) == 0

    def test_repeated_calls_accumulate(self):
        """Multiple audio chunks accumulate in guarded buffers."""
        trigger = bytearray()
        audio = bytearray()
        for _ in range(100):
            trigger, audio = audiobuffer_guard(b'\x00' * 160, True, 5, trigger, audio)
        assert len(trigger) == 16000
        assert len(audio) == 16000

    def test_no_apps_repeated_stays_zero(self):
        """Without consumers, repeated calls keep buffers at zero."""
        trigger = bytearray()
        audio = bytearray()
        for _ in range(100):
            trigger, audio = audiobuffer_guard(b'\x00' * 160, False, None, trigger, audio)
        assert len(trigger) == 0
        assert len(audio) == 0


class TestWebhookSendCondition:
    """Test the webhook send threshold logic."""

    def test_none_delay_never_sends(self):
        """delay=None: never triggers send regardless of buffer size."""
        assert webhook_send_condition(None, 999999, 8000) is False

    def test_zero_delay_sends_immediately(self):
        """delay=0: sends when audiobuffer has any data (threshold=0)."""
        assert webhook_send_condition(0, 1, 8000) is True

    def test_zero_delay_empty_buffer_no_send(self):
        """delay=0 with empty buffer: doesn't send."""
        assert webhook_send_condition(0, 0, 8000) is False

    def test_positive_delay_under_threshold(self):
        """delay=5 at 8kHz: need >80000 bytes. Under threshold doesn't send."""
        # threshold = 8000 * 5 * 2 = 80000
        assert webhook_send_condition(5, 79999, 8000) is False

    def test_positive_delay_over_threshold(self):
        """delay=5 at 8kHz: need >80000 bytes. Over threshold sends."""
        assert webhook_send_condition(5, 80001, 8000) is True


class TestDelayZeroFullCycle:
    """Test that delay=0 results in immediate flush — no sustained buffer growth."""

    def test_delay_zero_immediate_flush_cycle(self):
        """delay=0: buffer extends momentarily then send condition triggers immediately,
        so the caller flushes. Net effect: no sustained growth."""
        audiobuffer = bytearray()
        sample_rate = 8000

        # Simulate 10 audio chunks arriving
        for _ in range(10):
            # Step 1: guard extends buffer
            _, audiobuffer = audiobuffer_guard(b'\x00' * 160, False, 0, bytearray(), audiobuffer)
            # Step 2: send condition triggers immediately (threshold=0)
            if webhook_send_condition(0, len(audiobuffer), sample_rate):
                # Step 3: caller flushes buffer (copies and clears)
                _ = audiobuffer.copy()
                audiobuffer = bytearray()

        # After 10 cycles, buffer is empty — no sustained growth
        assert len(audiobuffer) == 0

    def test_positive_delay_accumulates_before_flush(self):
        """delay=5: buffer grows until threshold, then flushes. Contrast with delay=0."""
        audiobuffer = bytearray()
        sample_rate = 8000
        threshold = sample_rate * 5 * 2  # 80000 bytes
        max_seen = 0

        for _ in range(600):  # 600 * 160 = 96000 bytes total
            _, audiobuffer = audiobuffer_guard(b'\x00' * 160, False, 5, bytearray(), audiobuffer)
            max_seen = max(max_seen, len(audiobuffer))
            if webhook_send_condition(5, len(audiobuffer), sample_rate):
                audiobuffer = bytearray()

        # Buffer accumulated to >80000 before flushing
        assert max_seen > threshold
