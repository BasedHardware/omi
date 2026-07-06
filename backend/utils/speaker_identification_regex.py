import re
from typing import Optional

# Language-specific patterns for speaker identification from text.
# Each pattern should have a capture group for the name.
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
        r"\b(I am|I'm|i am|i'm|My name is|my name is)\s+([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*){0,2})\b",
        r"\b([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*){0,2})\s+is my name\b",
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

_COMPILED_PATTERNS = [
    re.compile(pattern) for lang_patterns in SPEAKER_IDENTIFICATION_PATTERNS.values() for pattern in lang_patterns
]

# Pronouns and filler words the introduction patterns can capture from run-on
# transcripts (e.g. "I'm It was great", "I'm You know...") - never real names (#5223).
SPEAKER_NAME_STOPWORDS = frozenset(
    {
        'it',
        'you',
        'they',
        'them',
        'he',
        'she',
        'we',
        'us',
        'me',
        'him',
        'her',
        'his',
        'hers',
        'its',
        'my',
        'mine',
        'your',
        'yours',
        'our',
        'ours',
        'their',
        'theirs',
        'this',
        'that',
        'these',
        'those',
        'here',
        'there',
        'what',
        'who',
        'when',
        'where',
        'why',
        'how',
        'which',
        'the',
        'and',
        'but',
        'not',
        'yes',
        'no',
        'okay',
        'ok',
        'yeah',
        'just',
        'like',
        'so',
        'very',
        'really',
        'now',
        'then',
        'well',
        'still',
        'also',
        'too',
        'gonna',
        'going',
        'sure',
        'sorry',
        'good',
        'fine',
        'right',
        'everyone',
        'everybody',
        'someone',
        'somebody',
        'nobody',
        'anyone',
        'anybody',
        'something',
        'nothing',
        'one',
        'all',
        'some',
    }
)


def _normalize_speaker_name(name: str) -> Optional[str]:
    words = name.split()
    if any(word.lower() in SPEAKER_NAME_STOPWORDS for word in words):
        return None
    return " ".join(word.capitalize() if word.isupper() else word for word in words)


def detect_speaker_from_text(text: str) -> Optional[str]:
    if not text:
        return None

    for pattern in _COMPILED_PATTERNS:
        match = pattern.search(text)
        if match:
            name = match.groups()[-1]
            if name and len(name) >= 2:
                return _normalize_speaker_name(name)
    return None
