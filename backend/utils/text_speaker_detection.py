import asyncio
import json
import logging
import os
import re
from typing import Any, Optional

from openai import APIConnectionError, AsyncOpenAI

from utils.speaker_identification_regex import SPEAKER_NAME_STOPWORDS, detect_speaker_from_text

logger = logging.getLogger(__name__)

# ============================================================================
# Configuration (External vLLM)
# ============================================================================
VLLM_API_BASE = os.environ.get("VLLM_API_BASE", "").strip()
VLLM_API_KEY = os.environ.get("VLLM_API_KEY", "EMPTY")
VLLM_MODEL_NAME = os.environ.get("VLLM_MODEL_NAME", "meta-llama/Meta-Llama-3.1-8B-Instruct").strip()
VLLM_TIMEOUT_SECONDS = 2.0

_async_client: Optional[AsyncOpenAI] = None
_async_client_lock: Optional[asyncio.Lock] = None

# ============================================================================
# LLM SYSTEM PROMPT
# ============================================================================
SYSTEM_PROMPT = """You are an expert conversation analyst.
Identify the CURRENT SPEAKER'S own name when the transcript explicitly says it.

RULES:
- Return a name only when the transcript identifies the person currently speaking.
- Valid speaker self-identification examples:
  - "I am Alice." -> "Alice"
  - "My name is Bob." -> "Bob"
  - "This is Sarah from support." -> "Sarah"
  - "Hey, it's Dr. Jane Smith." -> "Dr. Jane Smith"
  - "Alice speaking." -> "Alice"
  - "Call me Mike." -> "Mike"
- Names that are addressed, mentioned, requested, or reported are NOT the speaker:
  - "Hey Alice, can you help?" -> null
  - "Bob, come here." -> null
  - "Alice and Bob, listen up." -> null
  - "I told Alice about it." -> null
  - "I saw Bob yesterday." -> null
  - "I was talking to Mike about the project." -> null
  - "Alice said she's coming." -> null
  - "We need to ask Mike about this." -> null
- If the transcript does not explicitly reveal the current speaker's name, return null.
- When in doubt, return null. Never infer speaker identity from who is being spoken to.

OUTPUT FORMAT (valid JSON):
{
  "speaker": "Name" or null
}
"""


SELF_IDENTIFICATION_CUE_PATTERNS = [
    r"\b(i am|i'm|my name is|this is|it is|it's|call me)\b",
    r"\bspeaking\b",
]

_compiled_self_identification_cues = [re.compile(p, re.IGNORECASE) for p in SELF_IDENTIFICATION_CUE_PATTERNS]


def is_text_speaker_llm_configured() -> bool:
    return bool(VLLM_API_BASE and VLLM_MODEL_NAME)


def is_self_identification_candidate(text: str) -> bool:
    if not text:
        return False
    return any(pattern.search(text) for pattern in _compiled_self_identification_cues)


def _normalize_speaker(value: Any) -> Optional[str]:
    if isinstance(value, str):
        speaker = value.strip()
        if len(speaker) >= 2 and speaker.lower() not in SPEAKER_NAME_STOPWORDS:
            return speaker
        return None

    if isinstance(value, list):
        speakers = [_normalize_speaker(speaker) for speaker in value]
        speakers = [speaker for speaker in speakers if speaker]
        if len(speakers) == 1:
            return speakers[0]

    return None


async def _get_async_client_lock() -> asyncio.Lock:
    global _async_client_lock
    if _async_client_lock is None:
        _async_client_lock = asyncio.Lock()
    return _async_client_lock


async def get_async_client() -> AsyncOpenAI:
    global _async_client
    if _async_client is not None:
        return _async_client

    lock = await _get_async_client_lock()
    async with lock:
        if _async_client is None:
            _async_client = AsyncOpenAI(
                base_url=VLLM_API_BASE,
                api_key=VLLM_API_KEY,
                timeout=VLLM_TIMEOUT_SECONDS,
            )
    return _async_client


async def close_async_client() -> None:
    global _async_client
    if _async_client is None:
        return
    try:
        close_fn = getattr(_async_client, "aclose", None)
        if close_fn:
            await close_fn()
        else:
            close_result = _async_client.close()
            if asyncio.iscoroutine(close_result):
                await close_result
    except Exception:
        logger.exception("Failed to close AsyncOpenAI client")
    finally:
        _async_client = None


async def identify_speaker_with_llm(transcript: str) -> Optional[str]:
    """
    Uses a configured OpenAI-compatible vLLM endpoint to identify the current
    speaker's own name from a transcript segment.
    """
    if not transcript or not transcript.strip() or not is_text_speaker_llm_configured():
        return None

    try:
        client = await get_async_client()

        response = await client.chat.completions.create(
            model=VLLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f'Transcript: "{transcript}"'},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            max_tokens=64,
        )

        content = response.choices[0].message.content
        data = json.loads(content or "{}")

        # Accept the current singular contract and the earlier list-shaped
        # response so old demo endpoints still parse during rollout.
        return _normalize_speaker(data.get("speaker")) or _normalize_speaker(data.get("speakers"))

    except APIConnectionError:
        logger.error("LLM Speaker ID connection error", exc_info=True)
        return None
    except Exception:
        logger.error("LLM Speaker ID error", exc_info=True)
        return None


async def identify_speaker_from_transcript(transcript: str) -> Optional[str]:
    """
    Identify the current speaker from transcript text.
    Tries the zero-cost regex path first, then the configured vLLM fallback.
    """
    legacy_name = detect_speaker_from_text(transcript)
    if legacy_name:
        return legacy_name

    if not is_self_identification_candidate(transcript):
        return None

    return await identify_speaker_with_llm(transcript)
