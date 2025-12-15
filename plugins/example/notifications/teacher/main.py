"""
Teacher Plugin for OMI - Instant Question Answering

Receives transcription, detects questions, and answers them in <2 seconds.
Uses Groq for fastest responses (~200ms), falls back to OpenAI.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import logging
import time
import os
import re
from collections import defaultdict
import threading
import httpx

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create router instead of app
router = APIRouter()

# API Keys - Groq is fastest, fallback to OpenAI
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Determine which provider to use (Groq is ~5x faster)
USE_GROQ = bool(GROQ_API_KEY)
openai_client = None

if USE_GROQ:
    logger.info("Teacher: Using Groq API (fast mode)")
elif OPENAI_API_KEY:
    logger.info("Teacher: Using OpenAI API")
    from openai import OpenAI
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
else:
    logger.warning("Teacher: No API keys set (GROQ_API_KEY or OPENAI_API_KEY) - will fail on requests")


# Session transcript buffer - stores recent text per session
class TranscriptBuffer:
    def __init__(self):
        self.buffers: Dict[str, List[Dict]] = defaultdict(list)
        self.lock = threading.Lock()
        self.max_segments = 15  # Keep last 15 segments
        self.max_age = 60  # Max age in seconds
    
    def add_segment(self, session_id: str, text: str, timestamp: float = None):
        """Add a segment to the buffer."""
        if not text.strip():
            return
        
        timestamp = timestamp or time.time()
        
        with self.lock:
            self.buffers[session_id].append({
                'text': text.strip(),
                'timestamp': timestamp
            })
            # Keep only recent segments
            self._cleanup_session(session_id)
    
    def get_recent_text(self, session_id: str, max_segments: int = 10) -> str:
        """Get recent text from the buffer, combined."""
        with self.lock:
            self._cleanup_session(session_id)
            segments = self.buffers.get(session_id, [])[-max_segments:]
            return ' '.join(seg['text'] for seg in segments)
    
    def _cleanup_session(self, session_id: str):
        """Remove old segments from a session."""
        current_time = time.time()
        self.buffers[session_id] = [
            seg for seg in self.buffers[session_id]
            if current_time - seg['timestamp'] < self.max_age
        ][-self.max_segments:]
    
    def clear_session(self, session_id: str):
        """Clear buffer for a session after answering."""
        with self.lock:
            self.buffers[session_id] = []


# Initialize buffer
transcript_buffer = TranscriptBuffer()

# Cooldown tracking to avoid duplicate answers
answer_cooldowns: Dict[str, float] = defaultdict(float)
ANSWER_COOLDOWN = 8  # seconds between answers for same session

# Recent questions cache to avoid re-answering
recent_questions: Dict[str, float] = {}
QUESTION_CACHE_TTL = 30  # seconds

# Track uptime
start_time = time.time()


class WebhookRequest(BaseModel):
    session_id: str
    segments: List[Dict[str, Any]] = []
    uid: Optional[str] = None


def has_question_mark(text: str) -> bool:
    """Check if text ends with or contains a question mark."""
    return '?' in text


def extract_question_from_buffer(session_id: str) -> str:
    """
    Extract the full question from the buffer.
    Combines recent segments and finds the complete question.
    """
    recent_text = transcript_buffer.get_recent_text(session_id, max_segments=10)
    logger.info(f"Teacher buffer content: '{recent_text}'")
    
    if not recent_text.strip():
        return "?"
    
    # Question words that typically start a question
    question_words = ['what', 'who', 'where', 'when', 'why', 'how', 'which', 'whose', 'whom',
                     'is', 'are', 'was', 'were', 'will', 'would', 'could', 'should', 'can', 
                     'do', 'does', 'did', 'have', 'has', 'had', 'tell', 'explain']
    
    text_lower = recent_text.lower()
    
    # Find the earliest question word in the text
    question_start = -1
    for word in question_words:
        pattern = r'\b' + word + r'\b'
        match = re.search(pattern, text_lower)
        if match:
            if question_start == -1 or match.start() < question_start:
                question_start = match.start()
    
    # Extract from question word to end
    if question_start >= 0:
        question = recent_text[question_start:].strip()
    else:
        # No question word found, use all recent text
        question = recent_text.strip()
    
    # Ensure it ends with ?
    if not question.endswith('?'):
        question = question.rstrip('.!,') + '?'
    
    logger.info(f"Teacher extracted question: '{question}'")
    return question


async def get_fast_answer_groq(question: str) -> str:
    """
    Get answer using Groq API - extremely fast (~200ms).
    Uses Llama 3.1 8B for speed.
    """
    try:
        start_time = time.time()
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.1-8b-instant",  # Fastest model
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a helpful teacher assistant. "
                                "Answer questions concisely and accurately. "
                                "Keep responses under 50 words. "
                                "Be direct and informative. "
                                "Don't say 'great question' or similar filler."
                            )
                        },
                        {"role": "user", "content": question}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 100,
                },
                timeout=5.0
            )
            
            response.raise_for_status()
            data = response.json()
            answer = data['choices'][0]['message']['content'].strip()
            
            elapsed = time.time() - start_time
            logger.info(f"Teacher Groq answer in {elapsed:.2f}s: {answer[:50]}...")
            
            return answer
            
    except Exception as e:
        logger.error(f"Teacher Groq error: {str(e)}")
        return "Sorry, I couldn't process that question."


def get_fast_answer_openai(question: str) -> str:
    """
    Get answer using OpenAI API - fallback option.
    """
    if not openai_client:
        return "Sorry, OpenAI not configured."
    
    try:
        start_time_local = time.time()
        
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful teacher assistant. "
                        "Answer questions concisely and accurately. "
                        "Keep responses under 50 words. "
                        "Be direct and informative."
                    )
                },
                {"role": "user", "content": question}
            ],
            temperature=0.3,
            max_tokens=100,
            timeout=5
        )
        
        answer = response.choices[0].message.content.strip()
        elapsed = time.time() - start_time_local
        logger.info(f"Teacher OpenAI answer in {elapsed:.2f}s: {answer[:50]}...")
        
        return answer
        
    except Exception as e:
        logger.error(f"Teacher OpenAI error: {str(e)}")
        return "Sorry, I couldn't process that question."


async def get_fast_answer(question: str) -> str:
    """Get answer using the fastest available provider."""
    if USE_GROQ:
        return await get_fast_answer_groq(question)
    elif OPENAI_API_KEY:
        return get_fast_answer_openai(question)
    else:
        return "Sorry, no API configured."


def should_answer(session_id: str, question: str) -> bool:
    """
    Check if we should answer this question (cooldown and dedup).
    """
    current_time = time.time()
    
    # Check cooldown
    time_since_last = current_time - answer_cooldowns.get(session_id, 0)
    if time_since_last < ANSWER_COOLDOWN:
        logger.info(f"Teacher cooldown active for session {session_id}, {ANSWER_COOLDOWN - time_since_last:.1f}s remaining")
        return False
    
    # Check if we already answered similar question recently
    # Use first few words as key to catch duplicates
    question_key = ' '.join(question.lower().split()[:5])
    cache_key = f"{session_id}:{question_key}"
    
    if cache_key in recent_questions:
        cache_time = recent_questions[cache_key]
        if current_time - cache_time < QUESTION_CACHE_TTL:
            logger.info(f"Teacher: Similar question answered recently: {question[:30]}...")
            return False
    
    return True


def cleanup_old_cache():
    """Remove expired entries from recent_questions cache."""
    current_time = time.time()
    expired_keys = [
        key for key, timestamp in recent_questions.items()
        if current_time - timestamp > QUESTION_CACHE_TTL
    ]
    for key in expired_keys:
        del recent_questions[key]


@router.post('/notification/teacher/webhook')
async def webhook(request: WebhookRequest):
    """
    Main webhook endpoint for receiving transcription segments.
    Detects questions and returns answers immediately.
    
    Strategy: Only answer when we see a question mark (?), then look back
    at the buffer to get the full question context.
    """
    session_id = request.session_id
    segments = request.segments
    uid = request.uid or session_id
    
    logger.info(f"Teacher received webhook: session={session_id}, segments={len(segments)}")
    
    if not segments:
        return JSONResponse(content={}, status_code=200)
    
    # Cleanup old cache entries periodically
    cleanup_old_cache()
    
    # First, add all segments to buffer (always use current time for buffer age)
    current_time = time.time()
    for segment in segments:
        text = segment.get('text', '').strip()
        if text:
            transcript_buffer.add_segment(session_id, text, current_time)
    
    # Check if any segment contains a question mark (signals end of question)
    has_question = False
    for segment in segments:
        text = segment.get('text', '').strip()
        if text and has_question_mark(text):
            has_question = True
            break
    
    if not has_question:
        # No question mark seen, just buffer and wait
        return JSONResponse(content={}, status_code=200)
    
    # Question mark detected! Extract full question from buffer
    full_question = extract_question_from_buffer(session_id)
    logger.info(f"Teacher question detected: {full_question}")
    
    # Check if we should answer
    if not should_answer(session_id, full_question):
        return JSONResponse(content={}, status_code=200)
    
    # Get fast answer
    answer = await get_fast_answer(full_question)
    
    # Update cooldown and cache
    answer_cooldowns[session_id] = time.time()
    question_key = ' '.join(full_question.lower().split()[:5])
    cache_key = f"{session_id}:{question_key}"
    recent_questions[cache_key] = time.time()
    
    # Clear buffer after answering
    transcript_buffer.clear_session(session_id)
    
    logger.info(f"Teacher returning answer for session {session_id}")
    
    # Return the answer directly in the response
    return JSONResponse(
        content={"message": answer},
        status_code=200
    )


@router.get('/notification/teacher/webhook/setup-status')
async def setup_status():
    """Setup status endpoint required by OMI."""
    return {"is_setup_completed": True}


@router.get('/notification/teacher/status')
async def status():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "provider": "groq" if USE_GROQ else ("openai" if OPENAI_API_KEY else "none"),
        "active_sessions": len(answer_cooldowns),
        "buffered_sessions": len(transcript_buffer.buffers),
        "uptime": time.time() - start_time
    }

