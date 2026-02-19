"""
Mentor notification system for providing real-time mentorship during conversations.

This module processes conversation segments and determines when to send mentor notifications
based on the user's notification frequency preference (0-5 scale).
"""

import time
import threading
import logging
from typing import List, Dict, Any
import json

from database.notifications import get_mentor_notification_frequency
from utils.llm.clients import llm_mini

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
                logger.info(f"Cleaned up {len(expired_sessions)} expired mentor notification sessions")


# Global message buffer
message_buffer = MessageBuffer()

# Minimum segments needed before analysis (real-time processing)
MIN_SEGMENTS_FOR_ANALYSIS = 3

# Minimum confidence to trigger a proactive notification
PROACTIVE_CONFIDENCE_THRESHOLD = 0.7

# Proactive trigger definitions (OpenAI function-calling format)
PROACTIVE_TRIGGERS = [
    {
        "type": "function",
        "function": {
            "name": "trigger_argument_perspective",
            "description": (
                "User is in a disagreement with someone. Offer an honest outside perspective "
                "on who might be right and why, based on what you know about the user."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "notification_text": {
                        "type": "string",
                        "description": "Push notification message (<300 chars, direct, empathetic)",
                    },
                    "other_person": {
                        "type": "string",
                        "description": "Who the user is disagreeing with",
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "rationale": {
                        "type": "string",
                        "description": "Why this notification is warranted",
                    },
                },
                "required": ["notification_text", "confidence", "rationale"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_goal_misalignment",
            "description": (
                "User is discussing plans that contradict their stored goals. "
                "Alert them to the conflict so they can course-correct."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "notification_text": {
                        "type": "string",
                        "description": "Push notification message (<300 chars, direct, empathetic)",
                    },
                    "goal_name": {
                        "type": "string",
                        "description": "Which goal is conflicted",
                    },
                    "conflict_description": {
                        "type": "string",
                        "description": "How the plan conflicts with the goal",
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["notification_text", "goal_name", "conflict_description", "confidence"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_emotional_support",
            "description": (
                "User is expressing complaints or negative emotions. "
                "Suggest a concrete, actionable step they can take right now."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "notification_text": {
                        "type": "string",
                        "description": "Push notification message (<300 chars, direct, empathetic)",
                    },
                    "detected_emotion": {
                        "type": "string",
                        "description": "Primary emotion detected (e.g. frustration, loneliness, anxiety)",
                    },
                    "suggested_action": {
                        "type": "string",
                        "description": "Concrete actionable suggestion",
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["notification_text", "detected_emotion", "confidence"],
                "additionalProperties": False,
            },
        },
    },
]


def extract_topics(discussion_text: str) -> List[str]:
    """Extract topics from the discussion using LLM."""
    try:
        prompt = (
            "You are a topic extraction specialist. Extract all relevant topics from the conversation. "
            "Return ONLY a JSON array of topic strings, nothing else. "
            'Example format: ["topic1", "topic2"]\n\n'
            f"Extract all topics from this conversation:\n{discussion_text}"
        )
        response_text = llm_mini.invoke(prompt).content.strip()
        topics = json.loads(response_text)
        logger.info(f"Extracted topics: {topics}")
        return topics
    except Exception as e:
        logger.error(f"Error extracting topics: {str(e)}")
        return []


def adjust_prompt_for_frequency(base_prompt: str, frequency: int) -> str:
    """
    Adjust the evaluation criteria based on frequency level.

    Args:
        base_prompt: The base mentor prompt
        frequency: 0-5 where 1=most selective, 5=most proactive

    Returns:
        Modified prompt with adjusted evaluation criteria
    """
    if frequency == 1:
        # Ultra selective - only intervene for critical situations
        adjustment = """
CRITICAL: Be EXTREMELY selective. Only interrupt if:
- The situation is urgent and time-sensitive
- Your advice could prevent a significant mistake or missed opportunity
- The insight is truly exceptional and game-changing
"""
    elif frequency == 2:
        # Very selective
        adjustment = """
NOTE: Be very selective. Only interrupt if:
- You have strong, actionable advice that significantly impacts the situation
- The timing is critical
"""
    elif frequency == 3:
        # Balanced (default)
        adjustment = """
NOTE: Be balanced in your interventions. Interrupt when:
- You have clear, valuable insights that impact the situation
- The advice is timely and actionable
"""
    elif frequency == 4:
        # Proactive
        adjustment = """
NOTE: Be proactive. Consider interrupting when:
- You have relevant experience or insights to share
- You can add clarity or perspective to the discussion
"""
    else:  # frequency == 5
        # Very proactive
        adjustment = """
NOTE: Be highly proactive. Look for opportunities to:
- Share relevant insights and experiences
- Offer guidance and perspective
- Help clarify thinking and decision-making
"""

    # Insert adjustment after the first paragraph
    lines = base_prompt.split('\n')
    insert_index = next((i for i, line in enumerate(lines) if line.startswith('STEP 1')), 1)
    lines.insert(insert_index, adjustment)

    return '\n'.join(lines)


def create_notification_data(messages: List[Dict[str, Any]], frequency: int) -> Dict[str, Any]:
    """
    Create notification data with prompt template adjusted for frequency level.

    Args:
        messages: List of message dicts with 'text', 'timestamp', 'is_user'
        frequency: User's notification frequency preference (1-5)

    Returns:
        Notification data dict with prompt, params, and context filters
    """
    # Format the discussion with speaker labels
    formatted_discussion = []
    for msg in messages:
        speaker = "{{user_name}}" if msg.get('is_user') else "other"
        formatted_discussion.append(f"{msg['text']} ({speaker})")

    discussion_text = "\n".join(formatted_discussion)

    # Extract topics from the discussion
    topics = extract_topics(discussion_text)

    base_system_prompt = """You are {{user_name}}'s personal AI mentor. Your FIRST task is to determine if this conversation warrants interruption.

STEP 1 - Evaluate SILENTLY if ALL these conditions are met:
1. {{user_name}} is participating in the conversation (messages marked with '({{user_name}})' must be present)
2. {{user_name}} has expressed a specific problem, challenge, goal, or question
3. You have a STRONG, CLEAR opinion that would significantly impact {{user_name}}'s situation
4. The insight is time-sensitive and worth interrupting for

If ANY condition is not met, respond with an empty string and nothing else.

STEP 2 - Only if ALL conditions are met, provide feedback following these guidelines:
- NEVER use markdown formatting (no code blocks, no backticks, no asterisks)
- Speak DIRECTLY to {{user_name}} - no analysis or third-person commentary
- Take a clear stance - no "however" or "on the other hand"
- Keep it under 300 chars
- Use simple, everyday words like you're talking to a friend
- Reference specific details from what {{user_name}} said
- Be bold and direct - {{user_name}} needs clarity, not options
- End with a specific question about implementing your advice

What we know about {{user_name}}: {{user_facts}}

Current discussion:
{text}

Previous discussions and context: {{user_context}}

Chat history: {{user_chat}}

Remember: First evaluate silently, then either respond with empty string OR give experience-backed advice.""".format(
        text=discussion_text
    )

    # Adjust prompt based on frequency level
    adjusted_prompt = adjust_prompt_for_frequency(base_system_prompt, frequency)

    return {
        "prompt": adjusted_prompt,
        "params": ["user_name", "user_facts", "user_context", "user_chat"],
        "context": {"filters": {"people": [], "entities": [], "topics": topics}},
        "triggers": PROACTIVE_TRIGGERS,
        "messages": messages,
    }


def process_mentor_notification(uid: str, segments: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    """
    Process segments for mentor notification.

    Args:
        uid: User ID
        segments: List of conversation segments

    Returns:
        Notification data dict if notification should be sent, None otherwise
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
    # Rate limiting is handled by app_integrations.py (1 notification per 300s)
    if (
        len(buffer_data['messages']) >= MIN_SEGMENTS_FOR_ANALYSIS and not buffer_data['silence_detected']
    ):  # Only analyze if not in silence period
        # Sort messages by timestamp
        sorted_messages = sorted(buffer_data['messages'], key=lambda x: x['timestamp'])

        buffer_data['last_analysis_time'] = current_time
        buffer_data['messages'] = []  # Clear buffer after analysis

        # Create notification data with prompt, tools, and conversation messages.
        # Tool calling is handled downstream by _process_proactive_notification.
        notification_data = create_notification_data(sorted_messages, frequency)

        logger.info(f"Mentor notification ready for user {uid} (frequency: {frequency})")
        return notification_data

    return None
