import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from openai import APIConnectionError, AsyncOpenAI

# Configure logging
logger = logging.getLogger(__name__)

# ============================================================================
# Configuration (External vLLM)
# ============================================================================
VLLM_API_BASE = os.environ.get("VLLM_API_BASE", "http://localhost:8000/v1")
VLLM_API_KEY = os.environ.get("VLLM_API_KEY", "EMPTY")
VLLM_MODEL_NAME = os.environ.get("VLLM_MODEL_NAME", "meta-llama/Meta-Llama-3.1-8B-Instruct")

_async_client: Optional[AsyncOpenAI] = None
_async_client_lock: Optional[asyncio.Lock] = None

# Legacy Regex Patterns (for self-identification fallback)
SPEAKER_IDENTIFICATION_PATTERNS = {
    'bg': [  # Bulgarian
        r"\b(Аз съм|аз съм|Казвам се|казвам се|Името ми е|името ми е)\s+([А-Я][а-я]*)\b",
    ],
    'cs': [  # Czech
        r"\b(Jmenuji se|jmenuji se|Jsem|jsem)\s+([A-Z][a-z]*)\b",
    ],
    'da': [  # Danish
        r"\b(Jeg hedder|jeg hedder|Mit navn er|mit navn er)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'de': [  # German
        r"\b(Ich heiße|ich heiße|Mein Name ist|mein Name ist|Ich bin|ich bin)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'el': [  # Greek
        r"\b(Με λένε|με λένε|Το όνομά μου είναι|το όνομά μου είναι|Είμαι ο|είμαι ο|Είμαι η|είμαι η)\s+([A-ZΑ-Ω][a-zcS-ω]*)\b",
    ],
    'en': [  # English
        r"\b(I am|I'm|i am|i'm|My name is|my name is)\s+([A-Z][a-zA-Z]*)\b",
        r"\b([A-Z][a-zA-Z]*)\s+is my name\b",
    ],
    'es': [  # Spanish
        r"\b(Me llamo|me llamo|Mi nombre es|mi nombre es|Soy|soy)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'et': [  # Estonian
        r"\b(Minu nimi on|minu nimi on|Ma olen|ma olen)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'fi': [  # Finnish
        r"\b(Minun nimeni on|minun nimeni on|Olen|olen)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'fr': [  # French
        r"\b(Je m'appelle|je m'appelle|Mon nom est|mon nom est|Je suis|je suis)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'hu': [  # Hungarian
        r"\b(A nevem|a nevem|Vagyok|vagyok)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'id': [  # Indonesian
        r"\b(Nama saya|nama saya|Saya|saya|Aku|aku)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'it': [  # Italian
        r"\b(Mi chiamo|mi chiamo|Il mio nome è|il mio nome è|Sono|sono)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'ja': [  # Japanese
        r"\b(私は|わたしは)\s*([A-Z][a-zA-Z]*)\s*(です)?\b",
        r"\b(私の名前は|わたしのなまえは)\s*([A-Z][a-zA-Z]*)\s*(です)?\b",
    ],
    'ko': [  # Korean
        r"\b(제 이름은|내 이름은)\s*([A-Z][a-zA-Z]*)\s*(입니다|이에요|예요)?\b",
        r"\b(저는|나는)\s*([A-Z][a-zA-Z]*)\s*(입니다|이에요|예요)?\b",
    ],
    'lt': [  # Lithuanian
        r"\b(Mano vardas|mano vardas|Aš esu|aš esu)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'lv': [  # Latvian
        r"\b(Mans vārds ir|mans vārds ir|Es esmu|es esmu)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'nb': [  # Norwegian Bokmål
        r"\b(Jeg heter|jeg heter|Mitt navn er|mitt navn er)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'nl': [  # Dutch
        r"\b(Ik heet|ik heet|Mijn naam is|mijn naam is|Ik ben|ik ben)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'pl': [  # Polish
        r"\b(Nazywam się|nazywam się|Mam na imię|mam na imię|Jestem|jestem)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'pt': [  # Portuguese
        r"\b(Eu me chamo|eu me chamo|O meu nome é|o meu nome é|Sou|sou)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'ro': [  # Romanian
        r"\b(Mă numesc|mă numesc|Numele meu este|numele meu este|Sunt|sunt)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'ru': [  # Russian
        r"\b(Меня зовут|меня зовут|Мое имя|мое имя|Я|я)\s+([А-Я][а-я]*)\b",
    ],
    'sk': [  # Slovak
        r"\b(Volám sa|volám sa|Moje meno je|moje meno je|Som|som)\s+([A-Z][a-z]*)\b",
    ],
    'sl': [  # Slovenian
        r"\b(Ime mi je|ime mi je|Sem|sem)\s+([A-Z][a-z]*)\b",
    ],
    'sv': [  # Swedish
        r"\b(Jag heter|jag heter|Mitt namn är|mitt namn är)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'tr': [  # Turkish
        r"\b(Adım|adım|Benim adım|benim adım|Ben|ben)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'uk': [  # Ukrainian
        r"\b(Мене звати|мене звати|Моє ім'я|моє ім'я|Я|я)\s+([А-Я][а-я]*)\b",
    ],
    'zh': [  # Chinese (Simplified)
        r"\b(我叫|我的名字是|我是)\s*([A-Z][a-zA-Z]*)\b",
    ],
}

# Pre-compile patterns
_compiled_patterns = []
for lang_patterns in SPEAKER_IDENTIFICATION_PATTERNS.values():
    _compiled_patterns.extend([re.compile(p) for p in lang_patterns])

# ============================================================================
# LLM SYSTEM PROMPT
# ============================================================================
SYSTEM_PROMPT = """You are an expert transcriber and conversation analyst.
Your task is to:
1. Identify who is being ADDRESSED (spoken TO) in the transcript.
2. CLEAN the transcript by removing filler words and fixing basic grammar.

RULES for Speaker Identification:
- Identify names of people explicitly addressed (e.g., "Hey Alice" -> ["Alice"]).
- If multiple people are addressed, list them all (e.g., "Alice, Bob, come here" -> ["Alice", "Bob"]).
- Distinguish between ADDRESSING and MENTIONING.
  - "I told Alice about it" -> Alice is MENTIONED, not addressed. Return null.
  - "I saw Bob yesterday" -> Bob is MENTIONED. Return null.
- If no one is addressed, return null.

RULES for Transcript Cleaning:
- Remove filler words: um, uh, you know, like, er, ah, hmm.
- Fix stuttering: "the the" -> "the".
- Fix capitalization: "alice went to paris" -> "Alice went to Paris".
- Do NOT change the meaning or remove important information.

OUTPUT FORMAT MUST BE EXACTLY (You must return valid JSON output):
{
  "speakers": ["Name1", "Name2"] or null,
  "cleaned_transcript": "The cleaned text here"
}
"""

def detect_speaker_from_text(text: str) -> Optional[str]:
    """
    LEGACY: Identifies the speaker from the text content itself (Self-Identification).
    Example: "I am Alice" -> returns "Alice"
    """
    if not text:
        return None
        
    for pattern in _compiled_patterns:
        match = pattern.search(text)
        if match:
            # The name is usually the last captured group
            name = match.groups()[-1]
            if name and len(name) >= 2:
                return name.capitalize()
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
                timeout=5.0,
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


async def identify_speaker_and_clean_transcript(transcript: str) -> Dict[str, Any]:
    """
    Uses vLLM (Llama 8B) to:
    1. Identify addressed speakers.
    2. Clean the transcript.
    
    Returns:
       dict: {"speakers": List[str] | None, "cleaned_transcript": str}
    """
    if not transcript or not transcript.strip():
        return {"speakers": None, "cleaned_transcript": transcript}

    try:
        client = await get_async_client()
        
        response = await client.chat.completions.create(
            model=VLLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f'Transcript: "{transcript}"'}
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            max_tokens=1024
        )
        
        content = response.choices[0].message.content
        data = json.loads(content)
        return data

    except APIConnectionError as e:
        logger.error(f"LLM Speaker ID Connection Error: {e}")
        return {"speakers": None, "cleaned_transcript": transcript}
    except Exception as e:
        logger.error(f"LLM Speaker ID Error: {e}")
        # Fallback: Return raw transcript and no speakers
        return {"speakers": None, "cleaned_transcript": transcript}

async def identify_speaker_from_transcript(transcript: str) -> Optional[List[str]]:
    """
    Wrapper for backward compatibility if just speaker ID is needed.
    """
    legacy_name = detect_speaker_from_text(transcript)
    if legacy_name:
        return [legacy_name]

    result = await identify_speaker_and_clean_transcript(transcript)
    return result.get("speakers")
