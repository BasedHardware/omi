import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from openai import APIConnectionError, AsyncOpenAI

logger = logging.getLogger(__name__)

# ============================================================================
# Configuration (External vLLM)
# ============================================================================
VLLM_API_BASE = os.environ.get("VLLM_API_BASE", "http://localhost:8000/v1")
VLLM_API_KEY = os.environ.get("VLLM_API_KEY", "EMPTY")
VLLM_MODEL_NAME = os.environ.get(
    "VLLM_MODEL_NAME", "meta-llama/Meta-Llama-3.1-8B-Instruct"
)

_async_client: Optional[AsyncOpenAI] = None
_async_client_lock: Optional[asyncio.Lock] = None

# ============================================================================
# Legacy Regex Patterns (self-identification fallback)
# ============================================================================
# Kept in sync with utils/speaker_identification.py.  If you add a language
# there, add it here too.
SPEAKER_IDENTIFICATION_PATTERNS = {
    'bg': [  # Bulgarian
        r"\b(Аз съм|аз съм|Казвам се|казвам се|Името ми е|името ми е)\s+([А-Я][а-я]*)\b",
    ],
    'ca': [  # Catalan
        r"\b(Sóc|sóc|Em dic|em dic|El meu nom és|el meu nom és)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'zh': [  # Chinese
        r"(我是|我叫|我的名字是)\s*([\u4e00-\u9fa5]+)",
    ],
    'cs': [  # Czech
        r"\b(Jsem|jsem|Jmenuji se|jmenuji se)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'da': [  # Danish
        r"\b(Jeg er|jeg er|Jeg hedder|jeg hedder|Mit navn er|mit navn er)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'de': [  # German
        r"\b(ich bin|Ich bin|ich heiße|Ich heiße|mein Name ist|Mein Name ist)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'el': [  # Greek
        r"\b(Είμαι|είμαι|Με λένε|με λένε|Το όνομά μου είναι|το όνομά μου είναι)\s+([\u0370-\u03ff\u1f00-\u1fff]+)\b",
    ],
    'en': [  # English
        r"\b(I am|I'm|i am|i'm|My name is|my name is)\s+([A-Z][a-zA-Z]*)\b",
        r"\b([A-Z][a-zA-Z]*)\s+is my name\b",
    ],
    'es': [  # Spanish
        r"\b(soy|Soy|me llamo|Me llamo|mi nombre es|Mi nombre es)\s+([A-Z][a-zA-Z]*)\b",
        r"\b([A-Z][a-zA-Z]*)\s+es mi nombre\b",
    ],
    'et': [  # Estonian
        r"\b(Ma olen|ma olen|Minu nimi on|minu nimi on)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'fi': [  # Finnish
        r"\b(Olen|olen|Minun nimeni on|minun nimeni on)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'fr': [  # French
        r"\b(je suis|Je suis|je m'appelle|Je m'appelle|mon nom est|Mon nom est)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'hi': [  # Hindi
        r"(मैं हूँ|मेरा नाम है)\s+([\u0900-\u097F]+)",
    ],
    'hu': [  # Hungarian
        r"\b(Én vagyok|én vagyok|A nevem|a nevem)\s+([A-Z][a-zA-Z]*)\b",
        r"\b([A-Z][a-zA-Z]*)\s+vagyok\b",
    ],
    'id': [  # Indonesian
        r"\b(Saya|saya|Nama saya|nama saya)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'it': [  # Italian
        r"\b(Sono|sono|Mi chiamo|mi chiamo|Il mio nome è|il mio nome è)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'ja': [  # Japanese
        r"(私は|わたしは|私の名前は|わたしのなまえは)\s*([\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]+)",
    ],
    'ko': [  # Korean
        r"(저는|제 이름은)\s*([\uac00-\ud7a3]+)",
    ],
    'lt': [  # Lithuanian
        r"\b(Aš esu|aš esu|Mano vardas yra|mano vardas yra)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'lv': [  # Latvian
        r"\b(Es esmu|es esmu|Mans vārds ir|mans vārds ir)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'ms': [  # Malay
        r"\b(Saya|saya|Nama saya|nama saya)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'nl': [  # Dutch / Flemish
        r"\b(Ik ben|ik ben|Mijn naam is|mijn naam is|Ik heet|ik heet)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'no': [  # Norwegian
        r"\b(Jeg er|jeg er|Jeg heter|jeg heter|Navnet mitt er|navnet mitt er)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'pl': [  # Polish
        r"\b(Jestem|jestem|Nazywam się|nazywam się|Mam na imię|mam na imię)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'pt': [  # Portuguese
        r"\b(Eu sou|eu sou|Chamo-me|chamo-me|O meu nome é|o meu nome é)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'ro': [  # Romanian
        r"\b(Sunt|sunt|Mă numesc|mă numesc|Numele meu este|numele meu este)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'ru': [  # Russian
        r"\b(Я|я|Меня зовут|меня зовут|Моё имя|моё имя)\s+([А-Я][а-я]*)\b",
    ],
    'sk': [  # Slovak
        r"\b(Som|som|Volám sa|volám sa)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'sl': [  # Slovenian
        r"\b(Ime mi je|ime mi je|Sem|sem)\s+([A-Z][a-z]*)\b",
    ],
    'sv': [  # Swedish
        r"\b(Jag är|jag är|Jag heter|jag heter|Mitt namn är|mitt namn är)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'th': [  # Thai
        r"(ผมชื่อ|ฉันชื่อ|ผมคือ|ฉันคือ)\s*([\u0e00-\u0e7f]+)",
    ],
    'tr': [  # Turkish
        r"\b(Benim adım|benim adım)\s+([A-Z][a-zA-Z]*)\b",
    ],
    'uk': [  # Ukrainian
        r"\b(Я|я|Мене звати|мене звати|Моє ім'я|моє ім'я)\s+([А-ЯІЇЄҐ][а-яіїєґ]*)\b",
    ],
    'vi': [  # Vietnamese
        r"\b(Tôi là|tôi là|Tên tôi là|tên tôi là)\s+([A-Z][a-zA-Z]*)\b",
    ],
}

# Pre-compile all patterns at module load for performance
_compiled_patterns = []
for _lang_patterns in SPEAKER_IDENTIFICATION_PATTERNS.values():
    _compiled_patterns.extend(re.compile(p) for p in _lang_patterns)

# ============================================================================
# LLM SYSTEM PROMPT
# ============================================================================
SYSTEM_PROMPT = """You are an expert transcriber and conversation analyst.
Your task is to:
1. Identify who is being ADDRESSED (spoken TO directly) in the transcript.
2. CLEAN the transcript by removing filler words and fixing basic grammar.

RULES for Speaker Identification:
- ADDRESSED means the person is the DIRECT RECIPIENT of the current speech (vocative use).
- A name is ADDRESSED only when it appears as a direct call-out to someone present:
  EXAMPLES of ADDRESSING (return the name):
  - "Hey Alice, can you help?" -> ["Alice"]
  - "Bob, come here." -> ["Bob"]
  - "Alice and Bob, listen up." -> ["Alice", "Bob"]
  - "Listen Sarah, this is important." -> ["Sarah"]
  - "Could you pass that, John?" -> ["John"]
- A name is MENTIONED (NOT addressed) when it appears as the object of a verb,
  a preposition, or in a narrative about a past/separate event:
  EXAMPLES of MENTIONING (return null):
  - "I told Alice about it." -> null (talking ABOUT Alice to someone else)
  - "I saw Bob yesterday." -> null (narrating a past event)
  - "I was talking to Mike about the project." -> null (recounting a past conversation)
  - "I called Sarah earlier." -> null (describing a past action)
  - "Alice said she's coming." -> null (reporting what Alice said)
  - "I met John at the store." -> null (narrating a past encounter)
  - "We need to ask Mike about this." -> null (planning, not calling out to Mike)
  - "She told Bob the news." -> null (third-person narrative)
- If no one is directly addressed in the current speech, return null.
- When in doubt, return null. Only return a name when the speaker is clearly
  calling out to that person as the intended listener.

RULES for Transcript Cleaning:
- Remove filler words: um, uh, you know, like, er, ah, hmm.
- Fix stuttering: "the the" -> "the".
- Fix capitalization: "alice went to paris" -> "Alice went to Paris".
- Do NOT change the meaning or remove important information.

OUTPUT FORMAT (valid JSON):
{
  "speakers": ["Name1", "Name2"] or null,
  "cleaned_transcript": "The cleaned text here"
}
"""


def detect_speaker_from_text(text: str) -> Optional[str]:
    """
    LEGACY: Identifies the speaker from the text content itself (self-identification).
    Example: "I am Alice" -> returns "Alice"
    """
    if not text:
        return None

    for pattern in _compiled_patterns:
        match = pattern.search(text)
        if match:
            name = match.groups()[-1]
            if name and len(name) >= 2:
                return name
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


async def identify_speaker_and_clean_transcript(
    transcript: str,
) -> Dict[str, Any]:
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
                {"role": "user", "content": f'Transcript: "{transcript}"'},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            max_tokens=256,
        )

        content = response.choices[0].message.content
        data = json.loads(content)

        # Normalize: ensure expected keys exist regardless of LLM output shape
        return {
            "speakers": data.get("speakers"),
            "cleaned_transcript": data.get("cleaned_transcript", transcript),
        }

    except APIConnectionError:
        logger.error("LLM Speaker ID connection error", exc_info=True)
        return {"speakers": None, "cleaned_transcript": transcript}
    except Exception:
        logger.error("LLM Speaker ID error", exc_info=True)
        return {"speakers": None, "cleaned_transcript": transcript}


async def identify_speaker_from_transcript(
    transcript: str,
) -> Optional[List[str]]:
    """
    Wrapper for backward compatibility if just speaker ID is needed.
    Tries fast regex first, falls back to LLM.
    """
    legacy_name = detect_speaker_from_text(transcript)
    if legacy_name:
        return [legacy_name]

    result = await identify_speaker_and_clean_transcript(transcript)
    return result.get("speakers")
