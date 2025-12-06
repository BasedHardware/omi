"""
Speaker Identification Module for Omi Backend

This module provides two distinct speaker identification functions:

1. detect_speaker_from_text() - REGEX-based self-identification detection
   Detects when someone states their own name (e.g., "I am Alice", "My name is Bob")
   Uses multi-language regex patterns. Fast, no model required.

2. identify_speaker_from_transcript() - LLM-based addressee detection
   Detects who the user is TALKING TO (e.g., "Hey Alice, can you help?")
   Uses Qwen2.5-1.5B-Instruct GGUF model. Requires model file.

Fix for: https://github.com/BasedHardware/omi/issues/3039
"""

import contextlib
import io
import json
import logging
import os
import re
import threading
from typing import Optional

# ============================================================================
# Configuration
# ============================================================================
MODEL_PATH = os.environ.get(
    "SPEAKER_MODEL_PATH",
    os.path.join(os.path.dirname(__file__), "qwen_1.5b_speaker.gguf")
)
CONTEXT_WINDOW = 1024
GPU_LAYERS = -1  # Full GPU offload (Metal/CUDA)

logger = logging.getLogger(__name__)

# Thread-safe singleton for LLM
_model_instance = None
_model_lock = threading.Lock()

# ============================================================================
# PART 1: REGEX-BASED SELF-IDENTIFICATION (Original Functionality)
# ============================================================================
# Multi-language patterns for detecting self-introductions like "I am Alice"
# The name is expected to be the last capture group.

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

# Pre-compile all patterns for performance
_compiled_patterns = []
for lang_patterns in SPEAKER_IDENTIFICATION_PATTERNS.values():
    _compiled_patterns.extend(lang_patterns)


def detect_speaker_from_text(text: str) -> Optional[str]:
    """
    Detect the speaker's OWN NAME from self-identification phrases.
    
    This is the ORIGINAL function that uses regex patterns to detect
    when someone states their own name (e.g., "I am Alice", "My name is Bob").
    
    Args:
        text: The transcript text to analyze.
    
    Returns:
        The speaker's name if self-identification is detected, else None.
        
    Examples:
        >>> detect_speaker_from_text("Hi, I am Alice")
        'Alice'
        >>> detect_speaker_from_text("My name is Bob")
        'Bob'
        >>> detect_speaker_from_text("Hey Alice, help me")
        None  # This is addressing, not self-identification
    """
    for pattern in _compiled_patterns:
        match = re.search(pattern, text)
        if match:
            name = match.groups()[-1]
            if name and len(name) >= 2:
                return name.capitalize()
    return None


# ============================================================================
# PART 2: LLM-BASED ADDRESSEE DETECTION (New Functionality - Fix #3039)
# ============================================================================

SYSTEM_PROMPT = """You identify WHO is being directly SPOKEN TO (addressees) in a transcript.

ADDRESSED (return their names):
- "Hey Alice, can you help?" → ["Alice"]
- "Alice can you help me" → ["Alice"] (no comma, still addressed)
- "John, Bob, come here!" → ["John", "Bob"]
- "Hey Alice and Bob, listen up" → ["Alice", "Bob"]
- "What do you think, Jennifer?" → ["Jennifer"]
- "Listen Marcus, this matters" → ["Marcus"]

NOT ADDRESSED (return null):
- "I told Alice to stop" → null (talked ABOUT Alice)
- "Bob said he would come" → null (Bob is subject)
- "Did you hear what Sarah did?" → null (talking ABOUT Sarah)
- "Can you pass the salt?" → null (no name)

RULES:
1. Return names ONLY if someone is directly spoken TO
2. Names with comma separation = addressed
3. Names followed by imperative/question = addressed (even without comma)
4. Names as subject/object = NOT addressed
5. Multiple addressees → return all names
6. No addressee → return null

Respond with JSON: {"speakers": ["Name1", "Name2"]} or {"speakers": null}"""


def get_model():
    """
    Get the LLM model singleton, loading if necessary.
    Thread-safe with suppressed initialization noise.
    """
    global _model_instance
    
    if _model_instance is not None:
        return _model_instance
    
    with _model_lock:
        if _model_instance is not None:
            return _model_instance
        
        _model_instance = _load_model_silent()
        _warmup()
        
        return _model_instance


def _load_model_silent():
    """Load model with suppressed stderr noise."""
    if not os.path.exists(MODEL_PATH):
        logger.error(f"Speaker ID model not found: {MODEL_PATH}")
        raise FileNotFoundError(
            f"Speaker ID model not found at {MODEL_PATH}. "
            "Download: curl -L -o qwen_1.5b_speaker.gguf "
            "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"
        )
    
    try:
        from llama_cpp import Llama
    except ImportError as e:
        raise ImportError("pip install llama-cpp-python") from e
    
    logger.info(f"Loading speaker ID model: {MODEL_PATH}")
    
    # Suppress Metal/CUDA initialization spam
    stderr_capture = io.StringIO()
    with contextlib.redirect_stderr(stderr_capture):
        model = Llama(
            model_path=MODEL_PATH,
            n_ctx=CONTEXT_WINDOW,
            n_gpu_layers=GPU_LAYERS,
            verbose=False,
            chat_format="chatml",
        )
    
    logger.info("Speaker ID model loaded successfully")
    return model


def _warmup():
    """Warmup inference to eliminate cold-start penalty."""
    try:
        identify_speaker_from_transcript("warmup", _warmup=True)
    except Exception as e:
        logger.warning(f"Speaker ID model warmup failed: {e}")


def identify_speaker_from_transcript(
    transcript: str,
    _warmup: bool = False
) -> Optional[list[str]]:
    """
    Identify who the user is TALKING TO in the given transcript.
    
    Uses a self-hosted LLM to distinguish between:
    - ADDRESSED: "Hey Alice, can you help?" → ["Alice"]
    - MENTIONED: "I told Alice about it" → None
    
    Args:
        transcript: The text to analyze.
        _warmup: Internal flag for warmup calls (do not use).
    
    Returns:
        List of addressed speaker names (e.g., ["Alice", "Bob"]),
        or None if no one is being directly addressed.
        
    Examples:
        >>> identify_speaker_from_transcript("Hey Alice, can you help?")
        ['Alice']
        >>> identify_speaker_from_transcript("Alice and Bob, come here!")
        ['Alice', 'Bob']
        >>> identify_speaker_from_transcript("I told Alice about it")
        None
    """
    model = get_model()
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f'Transcript: "{transcript}"'}
    ]
    
    try:
        # Suppress inference noise
        stderr_capture = io.StringIO()
        with contextlib.redirect_stderr(stderr_capture):
            response = model.create_chat_completion(
                messages=messages,
                response_format={"type": "json_object"},
                max_tokens=100,
                temperature=0.0,
            )
        
        content = response["choices"][0]["message"]["content"]
        result = json.loads(content)
        speakers = result.get("speakers")
        
        # Normalize
        if speakers is None or speakers == [] or speakers == "null":
            return None
        
        if isinstance(speakers, list):
            cleaned = [str(s).strip() for s in speakers if s]
            return cleaned if cleaned else None
        
        if isinstance(speakers, str) and speakers.lower() != "null":
            return [speakers.strip()]
        
        return None
        
    except json.JSONDecodeError as e:
        if not _warmup:
            logger.warning(f"JSON parse error in speaker ID: {e}")
        return None
    except Exception as e:
        if not _warmup:
            logger.error(f"Speaker ID inference error: {e}")
        return None
