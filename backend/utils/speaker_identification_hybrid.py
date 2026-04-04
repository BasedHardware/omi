import re
import logging
from typing import Optional, List, Dict
from pydantic import BaseModel, Field, validator
from utils.llm.clients import llm_mini

logger = logging.getLogger(__name__)

class SpeakerName(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)

    @validator('name')
    def name_must_be_valid(cls, v):
        # Basic noise filtering
        noise_words = {
            'am', 'is', 'are', 'was', 'were', 'my', 'name', 'me', 'i', 'the', 'a', 'an',
            'hello', 'hi', 'hey', 'okay', 'yes', 'no', 'thanks', 'thank', 'you',
            'friend', 'someone', 'everyone', 'nobody', 'anyone', 'app', 'ai', 'bot'
        }
        if v.lower() in noise_words:
            raise ValueError('Name is a common noise word or generic noun')
        
        # English: Must be alphabetic, start with uppercase, at least 2 chars
        if re.match(r'^[a-zA-Z]+$', v):
            if not re.match(r'^[A-Z][a-z]+$', v):
                raise ValueError('English name must start with uppercase and be lowercase thereafter')
            if len(v) < 2:
                raise ValueError('Name too short')
        # Chinese: 2-4 characters
        elif re.match(r'^[\u4e00-\u9fa5]+$', v):
            if len(v) < 2 or len(v) > 4:
                raise ValueError('Chinese name must be 2-4 characters')
        else:
            # For other languages, just ensure it starts with an uppercase/special char
            if not re.match(r'^[A-Z\u0370-\u03ff\u1f00-\u1fff\u0400-\u04ff\u0900-\u097F\uac00-\ud7a3\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', v):
                raise ValueError('Name must start with an uppercase letter or a valid language-specific character')
            
        return v

# All language patterns moved here to centralize Stage 1 detection
SPEAKER_PATTERNS = {
    'bg': [r"\b(?:Аз съм|аз съм|Казвам се|казвам се|Името ми е|името ми е)\s+([А-Я][а-я]*)\b"],
    'ca': [r"\b(?:Sóc|sóc|Em dic|em dic|El meu nom és|el meu nom és)\s+([A-Z][a-zA-Z]*)\b"],
    'cs': [r"\b(?:Jsem|jsem|Jmenuji se|jmenuji se)\s+([A-Z][a-zA-Z]*)\b"],
    'da': [r"\b(?:Jeg er|jeg er|Jeg hedder|jeg hedder|Mit navn er|mit navn er)\s+([A-Z][a-zA-Z]*)\b"],
    'de': [r"\b(?:ich bin|Ich bin|ich heiße|Ich heiße|mein Name ist|Mein Name ist)\s+([A-Z][a-zA-Z]*)\b"],
    'el': [r"\b(?:Είμαι|είμαι|Με λένε|με λένε|Το όνομά μου είναι|το όνομά μου είναι)\s+([\u0370-\u03ff\u1f00-\u1fff]+)\b"],
    'en': [
        r"\b(?:[Ii]\s+am|[Ii]'m|[Mm]y\s+name\s+is)\s+([A-Z][a-z]+)\b",
        r"\b([A-Z][a-z]+)\s+is\s+my\s+name\b",
        r"\b(?:[Cc]all\s+me|[Pp]eople\s+call\s+me|[Mm]y\s+friends\s+know\s+me\s+as)\s+([A-Z][a-z]+)\b",
        r"\b(?:[Tt]his\s+is)\s+([A-Z][a-z]+)\s+speaking\b",
        r"\b(?:[Mm]y\s+name\s+is)\s+([A-Z][a-z]+)(?:\s+and|\s+I|\s+,)\b",
    ],
    'es': [
        r"\b(?:soy|Soy|me llamo|Me llamo|mi nombre es|Mi nombre es)\s+([A-Z][a-zA-Z]*)\b",
        r"\b([A-Z][a-zA-Z]*)\s+es\s+mi\s+nombre\b",
    ],
    'et': [r"\b(?:Ma olen|ma olen|Minu nimi on|minu nimi on)\s+([A-Z][a-zA-Z]*)\b"],
    'fi': [r"\b(?:Olen|olen|Minun nimeni on|minun nimeni on)\s+([A-Z][a-zA-Z]*)\b"],
    'fr': [r"\b(?:je suis|Je suis|je m'appelle|Je m'appelle|mon nom est|Mon nom est)\s+([A-Z][a-zA-Z]*)\b"],
    'hi': [r"(?:मैं हूँ|मेरा नाम है)\s+([\u0900-\u097F]+)"],
    'hu': [
        r"\b(?:Én vagyok|én vagyok|A nevem|a nevem)\s+([A-Z][a-zA-Z]*)\b",
        r"\b([A-Z][a-zA-Z]*)\s+vagyok\b",
    ],
    'id': [r"\b(?:Saya|saya|Nama saya|nama saya)\s+([A-Z][a-zA-Z]*)\b"],
    'it': [r"\b(?:Sono|sono|Mi chiamo|mi chiamo|Il mio nome è|il mio nome è)\s+([A-Z][a-zA-Z]*)\b"],
    'ja': [r"(?:私は|わたしは|私の名前は|わたしのなまえは)\s*([\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]+)"],
    'ko': [r"(?:저는|제 이름은)\s*([\uac00-\ud7a3]+)"],
    'lt': [r"\b(?:Aš esu|aš esu|Mano vardas yra|mano vardas yra)\s+([A-Z][a-zA-Z]*)\b"],
    'lv': [r"\b(?:Es esmu|es esmu|Mans vārds ir|mans vārds ir)\s+([A-Z][a-zA-Z]*)\b"],
    'ms': [r"\b(?:Saya|saya|Nama saya|nama saya)\s+([A-Z][a-zA-Z]*)\b"],
    'nl': [r"\b(?:Ik ben|ik ben|Mijn naam is|mijn naam is|Ik heet|ik heet)\s+([A-Z][a-zA-Z]*)\b"],
    'no': [r"\b(?:Jeg er|jeg er|Jeg heter|jeg heter|Navnet mitt er|navnet mitt er)\s+([A-Z][a-zA-Z]*)\b"],
    'pl': [r"\b(?:Jestem|jestem|Nazywam się|nazywam się|Mam na imię|mam na imię)\s+([A-Z][a-zA-Z]*)\b"],
    'pt': [r"\b(?:Eu sou|eu sou|Chamo-me|chamo-me|O meu nome é|o meu nome é)\s+([A-Z][a-zA-Z]*)\b"],
    'ro': [r"\b(?:Sunt|sunt|Mă numesc|mă numesc|Numele meu este|numele meu este)\s+([A-Z][a-zA-Z]*)\b"],
    'ru': [r"\b(?:Я|я|Меня зовут|меня зовут|Моё имя|моё имя)\s+([А-Я][а-я]*)\b"],
    'sk': [r"\b(?:Som|som|Volám sa|volám sa)\s+([A-Z][a-zA-Z]*)\b"],
    'sv': [r"\b(?:Jeg er|jeg er|Jeg heter|jeg heter|Mitt navn er|mit navn er)\s+([A-Z][a-zA-Z]*)\b"],
    'th': [r"(?:ผมชื่อ|ฉันชื่อ|ผมคือ|ฉันคือ)\s*([\u0e00-\u0e7f]+)"],
    'tr': [r"\b(?:Benim adım|benim adım)\s+([A-Z][a-zA-Z]*)\b"],
    'uk': [r"\b(?:Я|я|Мене звати|мене звати|Моє ім'я|моє ім'я)\s+([А-ЯІЇЄҐ][а-яіїєґ]*)\b"],
    'vi': [r"\b(?:Tôi là|tôi là|Tên tôi là|tên tôi là)\s+([A-Z][a-zA-Z]*)\b"],
    'zh': [
        r"(?:我是|我叫|我的名字是)\s*([\u4e00-\u9fa5]{2,4})",
        r"(?:(?:叫我|可以叫我))\s*([\u4e00-\u9fa5]{2,4})(?:就行|就可以)?",
        r"我是(?:.*?)的([\u4e00-\u9fa5]{2,4})",
    ],
}

def _detect_from_regex(text: str, language: Optional[str] = None) -> Optional[str]:
    """Stage 1: Fast Regex Matching (Multi-language)"""
    if language and language in SPEAKER_PATTERNS:
        patterns = SPEAKER_PATTERNS[language]
    else:
        # Check all patterns if language is unknown or not explicitly supported
        patterns = []
        for lang_patterns in SPEAKER_PATTERNS.values():
            patterns.extend(lang_patterns)
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            groups = match.groups()
            if groups:
                # Use the last group as the name
                name = groups[-1].strip(",.!? ")
                try:
                    validated = SpeakerName(name=name)
                    # For English, ensure first char is upper, others lower
                    if re.match(r'^[a-zA-Z]+$', validated.name):
                        return validated.name.capitalize()
                    return validated.name
                except ValueError:
                    continue
    return None

async def _detect_from_ner(text: str, language: str = 'en') -> Optional[str]:
    """
    Stage 2: Named Entity Recognition (Lightweight LLM)
    """
    # Only run LLM if there's a potential introduction signal to save tokens/costs
    # This is a key requirement to prevent "am" from triggering the engine constantly.
    signal_keywords = ['name', 'call me', 'here', '我是', '我叫', '名字', 'introducing']
    if not any(keyword in text.lower() for keyword in signal_keywords):
        return None

    prompt = f"Extract the name of the speaker who is introducing themselves in this transcript: \"{text}\". If no one is introducing themselves, respond with 'None'. Only provide the name."
    try:
        response = await llm_mini.ainvoke(prompt)
        name = response.content.strip().strip(",.!?\"' ")
        if name.lower() == 'none' or not name:
            return None
        try:
            validated = SpeakerName(name=name)
            return validated.name
        except ValueError:
            return None
    except Exception as e:
        logger.error(f"Error in Stage 2 (NER) extraction: {e}")
        return None

async def detect_speaker_hybrid(text: str, language: str = 'en') -> Optional[str]:
    """
    Hybrid Speaker Identification Engine (Async)
    Stage 1: Regex (Fast, No Cost)
    Stage 2: LLM NER (Contextual, Fallback)
    """
    if not text or len(text) < 5:
        return None

    # 1. Regex Match (Includes multi-language support)
    name = _detect_from_regex(text, language)
    if name:
        return name

    # 2. NER / LLM Fallback (Mostly for EN/ZH currently)
    if language in ['en', 'zh', 'multi']:
        name = await _detect_from_ner(text, language)
        if name:
            return name

    return None
