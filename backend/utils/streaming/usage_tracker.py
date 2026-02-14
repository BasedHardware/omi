import asyncio
import time
from typing import Callable, Optional

import database.users as users_db
from models.message_event import FreemiumThresholdReachedEvent, FREEMIUM_ACTION_SETUP_ON_DEVICE_STT, MessageEvent
from models.users import PlanType
from utils.analytics import record_usage
from utils.notifications import send_credit_limit_notification, send_silent_user_notification
from utils.subscription import has_transcription_credits, get_remaining_transcription_seconds

FREEMIUM_THRESHOLD_SECONDS = 180  # 3 minutes remaining


class UsageTracker:
    """Tracks transcription usage and enforces credit limits during a WebSocket session."""

    def __init__(
        self,
        uid: str,
        session_id: str,
        send_message_event: Callable[[MessageEvent], None],
        is_active: Callable[[], bool],
        use_custom_stt: bool = False,
    ):
        self.uid = uid
        self.session_id = session_id
        self._send_message_event = send_message_event
        self._is_active = is_active
        self._use_custom_stt = use_custom_stt

        self.first_audio_byte_timestamp: Optional[float] = None
        self.last_usage_record_timestamp: Optional[float] = None
        self.words_transcribed_since_last_record: int = 0
        self.last_transcript_time: Optional[float] = None
        self.last_audio_received_time: Optional[float] = None
        self.user_has_credits: bool = True
        self._freemium_threshold_sent: bool = False

    def check_initial_credits(self) -> bool:
        """Check if user has credits at session start. Returns True if credits available."""
        if self._use_custom_stt:
            return True
        self.user_has_credits = has_transcription_credits(self.uid)
        return self.user_has_credits

    def on_first_audio(self, timestamp: float) -> None:
        """Called when first audio byte is received."""
        self.first_audio_byte_timestamp = timestamp
        self.last_usage_record_timestamp = timestamp

    def on_audio_received(self, timestamp: float) -> None:
        """Called on each audio packet."""
        self.last_audio_received_time = timestamp

    def on_words_transcribed(self, word_count: int) -> None:
        """Called when new transcript words arrive."""
        self.words_transcribed_since_last_record += word_count

    def on_transcript_received(self) -> None:
        """Updates last_transcript_time to now."""
        self.last_transcript_time = time.time()

    async def run(self) -> None:
        """Background task: records usage every 60s while session is active."""
        while self._is_active():
            await asyncio.sleep(60)
            if not self._is_active():
                break

            if self._use_custom_stt:
                continue

            if self.last_usage_record_timestamp:
                current_time = time.time()
                transcription_seconds = int(current_time - self.last_usage_record_timestamp)
                words_to_record = self.words_transcribed_since_last_record
                self.words_transcribed_since_last_record = 0

                if transcription_seconds > 0 or words_to_record > 0:
                    record_usage(
                        self.uid, transcription_seconds=transcription_seconds, words_transcribed=words_to_record
                    )
                self.last_usage_record_timestamp = current_time

            # Freemium: Check remaining credits and notify when threshold reached
            remaining_seconds = get_remaining_transcription_seconds(self.uid)

            if (
                remaining_seconds is not None
                and remaining_seconds <= FREEMIUM_THRESHOLD_SECONDS
                and not self._freemium_threshold_sent
            ):
                self._send_message_event(
                    FreemiumThresholdReachedEvent(
                        remaining_seconds=remaining_seconds,
                        action=FREEMIUM_ACTION_SETUP_ON_DEVICE_STT,
                    )
                )
                self._freemium_threshold_sent = True

                try:
                    await send_credit_limit_notification(self.uid)
                except Exception as e:
                    print(f"UsageTracker: error sending credit limit notification: {e}", self.uid, self.session_id)

            # Update credits state
            if remaining_seconds is not None and remaining_seconds <= 0:
                self.user_has_credits = False
            elif remaining_seconds is None or remaining_seconds > 0:
                self.user_has_credits = True
                if remaining_seconds is None or remaining_seconds > FREEMIUM_THRESHOLD_SECONDS:
                    self._freemium_threshold_sent = False

            # Silence notification for basic plan users
            user_subscription = users_db.get_user_valid_subscription(self.uid)
            if not user_subscription or user_subscription.plan == PlanType.basic:
                time_of_last_words = self.last_transcript_time or self.first_audio_byte_timestamp
                if (
                    self.last_audio_received_time
                    and time_of_last_words
                    and (self.last_audio_received_time - time_of_last_words) > 15 * 60
                ):
                    print(
                        f"UsageTracker: user {self.uid} silent for over 15 minutes, sending notification",
                        self.session_id,
                    )
                    try:
                        await send_silent_user_notification(self.uid)
                    except Exception as e:
                        print(f"UsageTracker: error sending silent user notification: {e}", self.uid, self.session_id)

    def record_final_usage(self) -> None:
        """Called in finally block to record any remaining un-flushed usage."""
        if self._use_custom_stt:
            return
        if self.last_usage_record_timestamp:
            transcription_seconds = int(time.time() - self.last_usage_record_timestamp)
            words_to_record = self.words_transcribed_since_last_record
            if transcription_seconds > 0 or words_to_record > 0:
                record_usage(self.uid, transcription_seconds=transcription_seconds, words_transcribed=words_to_record)
