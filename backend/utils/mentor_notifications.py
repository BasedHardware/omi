"""
Mentor notification system for providing real-time mentorship during conversations.

This module buffers conversation segments and determines when enough context
has accumulated to evaluate a proactive notification.
"""

import time
import threading
import logging
from typing import List, Dict, Any

from database.notifications import get_mentor_notification_frequency

logger = logging.getLogger(__name__)

# Maximum messages to keep in buffer (prevents unbounded growth in long conversations)
MAX_BUFFER_MESSAGES = 50

# Minimum NEW segments needed since last evaluation before triggering another
MIN_NEW_SEGMENTS_FOR_ANALYSIS = 10


class MessageBuffer:
    """Manages conversation buffers for mentor notification analysis."""

    def __init__(self):
        self.buffers: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.cleanup_interval = 600  # 10 minutes
        self.last_cleanup = time.time()
        self.silence_threshold = 120  # 2 minutes silence threshold
        self.min_words_after_silence = 5  # minimum words needed after silence

    def get_buffer(self, session_id: str) -> Dict[str, Any]:
        """Get or create buffer for a session."""
        current_time = time.time()

        # Cleanup old sessions periodically
        if current_time - self.last_cleanup > self.cleanup_interval:
            self.cleanup_old_sessions()

        with self.lock:
            if session_id not in self.buffers:
                self.buffers[session_id] = {
                    'messages': [],
                    'last_analysis_time': time.time(),
                    'last_activity': current_time,
                    'words_after_silence': 0,
                    'silence_detected': False,
                    'messages_at_last_analysis': 0,
                }
            else:
                # Check for silence period
                time_since_activity = current_time - self.buffers[session_id]['last_activity']
                if time_since_activity > self.silence_threshold:
                    self.buffers[session_id]['silence_detected'] = True
                    self.buffers[session_id]['words_after_silence'] = 0
                    self.buffers[session_id]['messages'] = []  # Clear old messages after silence
                    self.buffers[session_id]['messages_at_last_analysis'] = 0

                self.buffers[session_id]['last_activity'] = current_time

        return self.buffers[session_id]

    def cleanup_old_sessions(self):
        """Remove sessions older than 1 hour."""
        current_time = time.time()
        with self.lock:
            expired_sessions = [
                session_id
                for session_id, data in self.buffers.items()
                if current_time - data['last_activity'] > 3600  # Remove sessions older than 1 hour
            ]
            for session_id in expired_sessions:
                del self.buffers[session_id]
            self.last_cleanup = current_time
            if expired_sessions:
                logger.warning(f"Cleaned up {len(expired_sessions)} expired mentor notification sessions")


# Global message buffer
message_buffer = MessageBuffer()


def process_mentor_notification(uid: str, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]] | None:
    """
    Process segments for mentor notification.

    Buffers incoming segments and returns the full accumulated conversation
    when enough new context has been gathered since last evaluation.
    Buffer accumulates across evaluations (not cleared) so the LLM sees
    the full conversation. Only clears on silence (2 min gap).

    Args:
        uid: User ID
        segments: List of conversation segments

    Returns:
        List of conversation message dicts if ready for evaluation, None otherwise.
        Each message dict has 'text', 'timestamp', and 'is_user' keys.
    """
    # Check if mentor notifications are enabled for this user
    frequency = get_mentor_notification_frequency(uid)
    if frequency == 0:
        return None

    current_time = time.time()
    buffer_data = message_buffer.get_buffer(uid)

    # Process new messages
    for segment in segments:
        if not segment.get('text'):
            continue

        text = segment['text'].strip()
        if text:
            timestamp = segment.get('start', 0) or current_time
            is_user = segment.get('is_user', False)

            # Count words after silence
            if buffer_data['silence_detected']:
                words_in_segment = len(text.split())
                buffer_data['words_after_silence'] += words_in_segment

                # If we have enough words, start fresh conversation
                if buffer_data['words_after_silence'] >= message_buffer.min_words_after_silence:
                    buffer_data['silence_detected'] = False
                    buffer_data['last_analysis_time'] = current_time  # Reset analysis timer
                    logger.info(f"Silence period ended for user {uid}, starting fresh conversation")

            can_append = (
                buffer_data['messages']
                and abs(buffer_data['messages'][-1]['timestamp'] - timestamp) < 2.0
                and buffer_data['messages'][-1].get('is_user') == is_user
            )

            if can_append:
                buffer_data['messages'][-1]['text'] += ' ' + text
            else:
                buffer_data['messages'].append({'text': text, 'timestamp': timestamp, 'is_user': is_user})

    # Trim buffer if it exceeds max size (keep most recent messages)
    if len(buffer_data['messages']) > MAX_BUFFER_MESSAGES:
        excess = len(buffer_data['messages']) - MAX_BUFFER_MESSAGES
        buffer_data['messages'] = buffer_data['messages'][excess:]
        buffer_data['messages_at_last_analysis'] = max(0, buffer_data['messages_at_last_analysis'] - excess)

    # Check if enough NEW messages since last evaluation
    new_message_count = len(buffer_data['messages']) - buffer_data.get('messages_at_last_analysis', 0)

    if new_message_count >= MIN_NEW_SEGMENTS_FOR_ANALYSIS and not buffer_data['silence_detected']:
        # Return ALL accumulated messages (not just new ones) for full context
        sorted_messages = sorted(buffer_data['messages'], key=lambda x: x['timestamp'])

        buffer_data['last_analysis_time'] = current_time
        buffer_data['messages_at_last_analysis'] = len(buffer_data['messages'])

        logger.info(
            f"Mentor notification ready for user {uid} "
            f"(total_messages={len(sorted_messages)}, new={new_message_count})"
        )
        return sorted_messages

    return None
