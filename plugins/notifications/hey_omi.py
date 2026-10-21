from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
import logging
import re
import time
import os
import requests
from collections import defaultdict
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from pathlib import Path
from datetime import datetime, timedelta
import threading
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Start time tracking for uptime reporting
start_time = time.time()

# Proxy configuration
if os.getenv('HTTPS_PROXY'):
    os.environ['OPENAI_PROXY'] = os.getenv('HTTPS_PROXY')

# Default credentials and client state
api_key = os.getenv('OPENAI_API_KEY', '')
omi_app_id = os.getenv('HEY_OMI_APP_ID', '')
omi_app_secret = os.getenv('HEY_OMI_APP_SECRET', '')
client = None
if api_key:
    try:
        client = OpenAI(api_key=api_key)
    except Exception:
        client = None


def get_openai_api_key() -> str:
    """Retrieve OpenAI API key dynamically from environment or fallback."""
    return os.getenv('OPENAI_API_KEY', api_key or '').strip()


def get_openai_client() -> Optional[Any]:
    """Retrieve or initialize OpenAI client lazily without failing on import."""
    global client
    if client is not None:
        return client
    current_key = get_openai_api_key()
    if not current_key:
        return None
    try:
        client = OpenAI(api_key=current_key)
        return client
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI client: {type(e).__name__}")
        return None


def get_omi_credentials() -> tuple:
    """Retrieve OMI app credentials dynamically as (app_id, app_secret)."""
    current_id = os.getenv('HEY_OMI_APP_ID', omi_app_id or '').strip()
    current_secret = os.getenv('HEY_OMI_APP_SECRET', omi_app_secret or '').strip()
    return current_id, current_secret


router = APIRouter(prefix="/notifications", tags=["notifications"])

# Modify trigger phrases and add buffer for partial triggers
TRIGGER_PHRASES = ["hey omi", "hey, omi"]  # Base triggers
PARTIAL_FIRST = ["hey", "hey,"]  # First part of trigger
PARTIAL_SECOND = ["omi"]  # Second part of trigger
QUESTION_AGGREGATION_TIME = 10  # seconds to wait for collecting the question
FALLBACK_OPENAI_RESPONSE = "I'm sorry, I encountered an error processing your request."


def question_after_trigger(text: str) -> str:
    """Return the words following the 'omi' trigger word in a lowercased
    segment, or '' when nothing follows it."""
    match = re.search(r'hey[ ,]+omi\b', text) or re.search(r'\bomi\b', text)
    return text[match.end():].strip(' \t\n\r,') if match else ''


# Global cooldown tracking dictionary maintained for backwards compatibility
notification_cooldowns = defaultdict(float)
NOTIFICATION_COOLDOWN = 15  # 15 seconds cooldown between notifications for each session


class MessageBuffer:
    def __init__(self):
        self.buffers = {}
        self.lock = threading.Lock()
        self.cleanup_interval = 300  # 5 minutes
        self.last_cleanup = time.time()

    def get_buffer(self, session_id):
        current_time = time.time()

        # Cleanup old sessions periodically
        if current_time - self.last_cleanup > self.cleanup_interval:
            self.cleanup_old_sessions()

        with self.lock:
            if session_id not in self.buffers:
                self.buffers[session_id] = {
                    'messages': [],
                    'trigger_detected': False,
                    'trigger_time': 0,
                    'collected_question': [],
                    'response_sent': False,
                    'partial_trigger': False,
                    'partial_trigger_time': 0,
                    'last_activity': current_time,
                }
            else:
                self.buffers[session_id]['last_activity'] = current_time

        return self.buffers[session_id]

    def cleanup_old_sessions(self):
        current_time = time.time()
        with self.lock:
            expired_sessions = [
                session_id
                for session_id, data in self.buffers.items()
                if current_time - data.get('last_activity', 0) > 3600  # Remove sessions older than 1 hour
            ]
            for session_id in expired_sessions:
                self.buffers.pop(session_id, None)
                notification_cooldowns.pop(session_id, None)

            # Sweep any orphaned cooldown timestamps older than 1 hour to prevent memory leaks
            expired_cooldowns = [
                session_id
                for session_id, ts in list(notification_cooldowns.items())
                if current_time - ts > 3600
            ]
            for session_id in expired_cooldowns:
                notification_cooldowns.pop(session_id, None)

            self.last_cleanup = current_time


message_buffer = MessageBuffer()


class WebhookRequest(BaseModel):
    session_id: str
    segments: List[Dict[str, Any]] = []
    uid: str = None


class WebhookResponse(BaseModel):
    status: str = "success"
    message: str = None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def _dispatch_openai_completion(cl: Any, text: str) -> str:
    """Execute completion call with retry on network / API failure."""
    response = cl.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": "You are Omi, a helpful AI assistant. Provide clear, concise, and friendly responses.",
            },
            {"role": "user", "content": text},
        ],
        temperature=0.7,
        max_tokens=150,
        timeout=30,
    )
    return response.choices[0].message.content.strip()


def get_openai_response(text: str) -> str:
    """Get response from OpenAI for user query, failing gracefully if unconfigured."""
    if not text or not str(text).strip():
        return FALLBACK_OPENAI_RESPONSE

    cl = get_openai_client()
    if cl is None:
        logger.warning("OpenAI client not configured, returning fallback")
        return FALLBACK_OPENAI_RESPONSE

    try:
        tlen = len(text)
        logger.info(f"Sending prompt to OpenAI ({tlen} chars)")
        answer = _dispatch_openai_completion(cl, text)
        logger.info("Received response from OpenAI")
        return answer
    except Exception as e:
        logger.error(f"Error getting OpenAI response: {type(e).__name__}")
        return FALLBACK_OPENAI_RESPONSE


def send_omi_notification(uid: str, message: str) -> bool:
    """Send notification using OMI notifications endpoint with validation and timeouts."""
    if not uid or not str(uid).strip():
        logger.warning("No uid provided for notification")
        return False

    if not message or not str(message).strip():
        logger.warning("No message provided for notification")
        return False

    app_id, app_secret = get_omi_credentials()
    if not app_id or not app_secret:
        logger.warning("OMI app credentials not configured")
        return False

    try:
        url = f"https://api.omi.me/v2/integrations/{app_id}/notification"
        headers = {"Authorization": f"Bearer {app_secret}", "Content-Type": "application/json"}
        params = {"uid": str(uid).strip(), "message": str(message).strip()}

        logger.info(f"Sending notification to OMI for uid {uid}")
        response = requests.post(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()

        logger.info(f"Successfully sent notification to OMI for uid {uid}")
        return True
    except Exception as e:
        logger.error(f"Error sending notification to OMI: {type(e).__name__}")
        return False


def _extract_segments_text(segments: List[Any]) -> List[str]:
    """Defensively extract normalized text strings from raw segment items."""
    cleaned = []
    if not isinstance(segments, list):
        return cleaned
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        raw = segment.get('text')
        if not isinstance(raw, str) or not raw.strip():
            continue
        cleaned.append(raw.lower().strip())
    return cleaned


def _handle_trigger_segment(buffer_data: Dict[str, Any], text: str, current_time: float, session_id: str) -> None:
    """Examine a single normalized text segment for trigger activation."""
    if any(trigger in text for trigger in [t.lower() for t in TRIGGER_PHRASES]) and not buffer_data['trigger_detected']:
        logger.info(f"Complete trigger phrase detected in session {session_id}")
        buffer_data['trigger_detected'] = True
        buffer_data['trigger_time'] = current_time
        buffer_data['collected_question'] = []
        buffer_data['response_sent'] = False
        buffer_data['partial_trigger'] = False

        part = question_after_trigger(text)
        if part:
            buffer_data['collected_question'].append(part)
            has_part = bool(part)
            logger.info(f"Collected question part from trigger: {has_part}")
        return

    if not buffer_data['trigger_detected']:
        if any(text.endswith(part.lower()) for part in PARTIAL_FIRST):
            logger.info(f"First part of trigger detected in session {session_id}")
            buffer_data['partial_trigger'] = True
            buffer_data['partial_trigger_time'] = current_time
            return

        if buffer_data.get('partial_trigger'):
            time_since_partial = current_time - buffer_data.get('partial_trigger_time', 0)
            if time_since_partial <= 2.0:
                if any(part.lower() in text.lower() for part in PARTIAL_SECOND):
                    logger.info(f"Complete trigger detected across segments in session {session_id}")
                    buffer_data['trigger_detected'] = True
                    buffer_data['trigger_time'] = current_time
                    buffer_data['collected_question'] = []
                    buffer_data['response_sent'] = False
                    buffer_data['partial_trigger'] = False

                    part = question_after_trigger(text)
                    if part:
                        buffer_data['collected_question'].append(part)
                        logger.info("Collected question part from second trigger part")
            else:
                buffer_data['partial_trigger'] = False


def _dispatch_collected_question(
    buffer_data: Dict[str, Any], current_time: float, uid: str, session_id: str
) -> bool:
    """Format collected question segments, query OpenAI, and notify OMI."""
    parts = buffer_data.get('collected_question', [])
    if not parts:
        return False

    assembled = ' '.join(parts).strip()
    if not assembled.endswith('?'):
        assembled += '?'

    qlen = len(assembled)
    logger.info(f"Processing complete question ({qlen} chars)")
    answer = get_openai_response(assembled)
    logger.info("Got response from OpenAI")

    if uid:
        success = send_omi_notification(uid, answer)
        if success:
            logger.info(f"Successfully sent notification for session {session_id}")
            notification_cooldowns[session_id] = current_time
        else:
            logger.error(f"Failed to send notification for session {session_id}")
    else:
        logger.error(f"No uid provided for session {session_id}, cannot send notification")

    buffer_data['trigger_detected'] = False
    buffer_data['trigger_time'] = 0
    buffer_data['collected_question'] = []
    buffer_data['response_sent'] = True
    buffer_data['partial_trigger'] = False
    return True


@router.post('/webhook')
async def webhook(request: WebhookRequest):
    logger.info("Received webhook POST request")
    logger.info("Received webhook payload")

    session_id = request.session_id
    if not session_id or not str(session_id).strip():
        logger.error("No session_id provided in request")
        raise HTTPException(status_code=400, detail="No session_id provided")

    session_id = str(session_id).strip()
    uid = str(request.uid).strip() if request.uid else session_id
    logger.info(f"Processing request for session_id: {session_id}, uid: {uid}")

    current_time = time.time()
    buffer_data = message_buffer.get_buffer(session_id)
    has_processed = False

    logger.debug(f"Current buffer state for session {session_id}: {sorted(buffer_data.keys())}")

    # Check and handle cooldown
    last_notification_time = notification_cooldowns.get(session_id, 0)
    time_since_last_notification = current_time - last_notification_time
    if time_since_last_notification >= NOTIFICATION_COOLDOWN:
        notification_cooldowns[session_id] = 0

    if (
        buffer_data['trigger_detected']
        and not buffer_data['response_sent']
        and time_since_last_notification < NOTIFICATION_COOLDOWN
    ):
        logger.info(f"Cooldown active. {NOTIFICATION_COOLDOWN - time_since_last_notification:.0f}s remaining")
        return WebhookResponse(status="success")

    cleaned_texts = _extract_segments_text(request.segments)

    for text in cleaned_texts:
        if has_processed:
            break

        was_detected_before = buffer_data['trigger_detected']
        _handle_trigger_segment(buffer_data, text, current_time, session_id)

        # Skip question aggregation on the exact step the trigger was triggered
        if not was_detected_before and buffer_data['trigger_detected']:
            continue

        if buffer_data['trigger_detected'] and not buffer_data['response_sent']:
            time_since_trigger = current_time - buffer_data['trigger_time']
            logger.info(f"Time since trigger: {time_since_trigger} seconds")

            if time_since_trigger <= QUESTION_AGGREGATION_TIME:
                buffer_data['collected_question'].append(text)
                tlen = len(text)
                logger.info(f"Collecting question part ({tlen} chars)")
                q_count = len(buffer_data['collected_question'])
                logger.info(f"Collected {q_count} question part(s)")

            should_process = (
                (time_since_trigger > QUESTION_AGGREGATION_TIME and buffer_data['collected_question'])
                or (buffer_data['collected_question'] and '?' in text)
                or (time_since_trigger > QUESTION_AGGREGATION_TIME * 1.5)
            )

            if should_process and buffer_data['collected_question']:
                _dispatch_collected_question(buffer_data, current_time, uid, session_id)
                has_processed = True
                return WebhookResponse(status="success")

    return WebhookResponse(status="success")


@router.get('/health')
async def health():
    app_id, _ = get_omi_credentials()
    return {
        "status": "healthy",
        "service": "notifications",
        "configured": bool(app_id and get_openai_api_key()),
    }


@router.get('/webhook/setup-status')
async def setup_status():
    try:
        app_id, app_secret = get_omi_credentials()
        is_configured = bool(app_id and app_secret and get_openai_api_key())
        return {"is_setup_completed": True, "configured": is_configured}
    except Exception as e:
        logger.error(f"Error checking setup status: {type(e).__name__}")
        raise HTTPException(status_code=500, detail="Internal setup error")


@router.get('/status')
async def status():
    app_id, _ = get_omi_credentials()
    return {
        "active_sessions": len(message_buffer.buffers),
        "uptime": time.time() - start_time,
        "configured": bool(app_id and get_openai_api_key()),
    }
