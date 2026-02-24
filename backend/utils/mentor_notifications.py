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
                }
            else:
                # Check for silence period
                time_since_activity = current_time - self.buffers[session_id]['last_activity']
                if time_since_activity > self.silence_threshold:
                    self.buffers[session_id]['silence_detected'] = True
                    self.buffers[session_id]['words_after_silence'] = 0
                    self.buffers[session_id]['messages'] = []  # Clear old messages after silence

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

# Minimum segments needed before analysis (real-time processing)
MIN_SEGMENTS_FOR_ANALYSIS = 3


def process_mentor_notification(uid: str, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]] | None:
    """
    Process segments for mentor notification.

    Buffers incoming segments and returns the accumulated conversation messages
    when enough context has been gathered for evaluation.

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

    # Real-time analysis: Process immediately when we have enough segments
    if len(buffer_data['messages']) >= MIN_SEGMENTS_FOR_ANALYSIS and not buffer_data['silence_detected']:
        # Sort messages by timestamp
        sorted_messages = sorted(buffer_data['messages'], key=lambda x: x['timestamp'])

        buffer_data['last_analysis_time'] = current_time
        buffer_data['messages'] = []  # Clear buffer after analysis

        logger.info(f"Mentor notification ready for user {uid}")
        return sorted_messages

    return None
