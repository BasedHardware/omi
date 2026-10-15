import asyncio
import io
import re
import wave
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple, cast

import av
import numpy as np

from database import conversations as conversations_db
from database import speaker_learning as speaker_learning_db
from database import users as users_db
from database import voice_profiles as voice_profiles_db
from utils.audio_timeline import (
    chunk_span_bounds,
    coverage_outcome,
    is_audio_timeline_v2,
)
from utils.conversations.audio_placement import (
    CAPTURE_RETRY_MIN_SHIFT_SECONDS,
    capture_shift,
    capture_window,
    locate,
    provisional_window,
)
from utils.conversations.teaching_placement import OMI_SPEAKER_CAPTURE_RETRY_TOTAL, recover_teaching_clip
from utils.executors import db_executor, storage_executor, sync_executor, run_blocking
from utils.metrics import OMI_AUDIO_TIMELINE_COVERAGE_TOTAL, OMI_PERSON_VOICE_LEARNING_TOTAL
from utils.speaker_learning_policy import (
    PooledClipPlan,
    TEACHING_MIN_TOTAL_SECONDS,
    authorized_teaching_segments,
    learning_state_for_outcome,
    plan_pooled_intervals,
    segment_group,
    union_seconds,
)
from utils.other.storage import (
    download_audio_chunks_and_merge,
    upload_person_speech_sample_from_bytes,
)
from utils.speaker_sample import verify_and_transcribe_sample, delete_sample_from_storage
from utils.speaker_audio import legacy_speaker_clip_pcm
from utils.other.audio_chunks import AudioChunkReadSession
from utils.speaker_tag_prompts.clips import v2_relevant_timestamps
from utils.stt.speaker_embedding import extract_embedding_from_bytes
import logging

logger = logging.getLogger(__name__)


def _pcm_to_wav_bytes(pcm_data: bytes, sample_rate: int) -> bytes:
    """
    Convert PCM16 mono audio to WAV format bytes.

    Args:
        pcm_data: Raw PCM16 mono audio bytes
        sample_rate: Audio sample rate in Hz

    Returns:
        WAV format bytes
    """
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    return wav_buffer.getvalue()


def _trim_pcm_audio(pcm_data: bytes, sample_rate: int, start_sec: float, end_sec: float) -> bytes:
    """
    Trim PCM16 mono audio using av for sample-accurate cutting.

    Args:
        pcm_data: Raw PCM16 mono audio bytes
        sample_rate: Audio sample rate in Hz
        start_sec: Start time in seconds (relative to pcm_data start)
        end_sec: End time in seconds (relative to pcm_data start)

    Returns:
        Trimmed PCM16 mono audio bytes
    """
    # Create WAV container for av to read
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    wav_buffer.seek(0)

    # Use av to extract trimmed audio with sample-accurate boundaries
    trimmed_samples: List[Any] = []
    with av.open(wav_buffer, mode='r') as container:
        stream = container.streams.audio[0]

        for frame in container.decode(stream):
            if frame.pts is None:
                continue

            frame_time = float(frame.pts * cast(Any, stream.time_base))
            frame_duration = frame.samples / sample_rate
            frame_end_time = frame_time + frame_duration

            # Skip frames entirely before our start
            if frame_end_time <= start_sec:
                continue
            # Stop once we're past the end
            if frame_time >= end_sec:
                break

            # Convert frame to numpy array
            arr = frame.to_ndarray()
            # For mono pcm_s16le, arr shape is (1, samples)
            if arr.ndim == 2:
                arr = arr[0]

            # Calculate which samples from this frame to include
            frame_start_sample = 0
            frame_end_sample = len(arr)

            if frame_time < start_sec:
                # Trim beginning of frame
                skip_samples = int(round((start_sec - frame_time) * sample_rate))
                frame_start_sample = skip_samples

            if frame_end_time > end_sec:
                # Trim end of frame
                keep_duration = end_sec - max(frame_time, start_sec)
                frame_end_sample = frame_start_sample + int(round(keep_duration * sample_rate))

            if frame_start_sample < frame_end_sample:
                trimmed_samples.append(arr[frame_start_sample:frame_end_sample])

    if not trimmed_samples:
        return b''

    return np.concatenate(trimmed_samples).astype(np.int16).tobytes()


# Language-specific patterns for speaker identification from text
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
        r"(我的名字是|我叫)\s*([\u4e00-\u9fa5]{2,5}?)(?:[，。！？、,.!?\s]|$)",
        r"(我是)\s*([\u4e00-\u9fa5]{2,4}?)(?:[，。！？、,.!?\s]|$)",
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
        r"(私の名前は|わたしのなまえは)\s*([\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]{2,6}?)(?:です|だ|でーす|だよ|と申します|ともうします|と言います|といいます|[、。，．！？!?\s]|$)",
        r"(私は|わたしは)\s*([\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]{2,6}?)(?:です|だ|でーす|だよ|と申します|ともうします|と言います|といいます|[、。，．！？!?\s]|$)",
    ],
    'ko': [  # Korean
        r"(저는|제\s*이름은)\s*([\uac00-\ud7a3]{2,5}?)(?:입니다|이에요|예요|이라고\s*합니다|라고\s*합니다|이야|야|[.,!?\s]|$)",
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

# Check all (multi lang)
patterns_to_check: List[str] = []
PATTERN_TO_LANG: Dict[str, str] = {}
for lang, lang_patterns in SPEAKER_IDENTIFICATION_PATTERNS.items():
    patterns_to_check.extend(lang_patterns)
    for pat in lang_patterns:
        PATTERN_TO_LANG[pat] = lang

# Lead-ins above that are a bare copula — "I am <something>" — rather than a
# self-introduction. They match a nationality, a mood, a brand or a sentence-cased
# filler just as readily as a name ("I'm Chinese", "I'm Googling it", 我是因为…),
# so a hit is a *hint* only: good enough to reuse a person the user already has,
# never good enough to mint a new one. The explicit forms in the same alternation
# ("My name is", 我叫, Je m'appelle, …) do carry that authority.
#
# Compared case-insensitively against capture group 1, so only one case variant
# of each lead-in is listed.
COPULAR_SELF_REFERENCE_LEAD_INS = frozenset(
    {
        'аз съм',  # bg
        'sóc',  # ca
        '我是',  # zh
        'jsem',  # cs
        'jeg er',  # da, no
        'ich bin',  # de
        'είμαι',  # el
        'i am',  # en
        "i'm",  # en
        'soy',  # es
        'ma olen',  # et
        'olen',  # fi
        'je suis',  # fr
        'मैं हूँ',  # hi
        'én vagyok',  # hu
        'saya',  # id, ms
        'sono',  # it
        '私は',  # ja
        'わたしは',  # ja
        '저는',  # ko
        'aš esu',  # lt
        'es esmu',  # lv
        'ik ben',  # nl
        'jestem',  # pl
        'eu sou',  # pt
        'sunt',  # ro
        'я',  # ru, uk
        'som',  # sk
        'jag är',  # sv
        'ผมคือ',  # th
        'ฉันคือ',  # th
        'tôi là',  # vi
    }
)

# Name-first patterns capture the name in group 1, so there is no lead-in to
# classify. Only Hungarian "<Name> vagyok" is a bare copula; "<Name> is my name"
# and "<Name> es mi nombre" are explicit introductions.
_NAME_FIRST_COPULAR_PATTERNS = frozenset({r"\b([A-Z][a-zA-Z]*)\s+vagyok\b"})

# CJK stopwords and grammatical elements to avoid false-positive speaker creation
# from ordinary conversational sentences (#12900).
JA_NAME_STOPWORDS = frozenset(
    {
        'そう',
        'これ',
        'それ',
        'あれ',
        'どれ',
        'ここ',
        'そこ',
        'あそこ',
        'どこ',
        '私',
        'わたし',
        'わたくし',
        '僕',
        'ぼく',
        '俺',
        'おれ',
        '自分',
        'じぶん',
        '日本人',
        '外国人',
        '学生',
        '大学生',
        '高校生',
        '中学生',
        '小学生',
        '留学生',
        '大学院生',
        '生徒',
        '先生',
        '医者',
        '医師',
        '看護師',
        '弁護士',
        '会社員',
        '公務員',
        '研究員',
        '店員',
        '店長',
        '社長',
        '部長',
        '課長',
        '社員',
        '主婦',
        '無職',
        '友達',
        '人間',
        '大人',
        '子供',
        '大丈夫',
        'ちょっと',
        'お腹',
        '元気',
        '誰',
        'だれ',
        '何',
        'なに',
        'なん',
        '本当',
        'ほんとう',
        '無理',
        'むり',
        '好き',
        'すき',
        '嫌い',
        'きらい',
        '思う',
        'おもう',
        '行く',
        'いく',
        '来る',
        'くる',
        '見る',
        'みる',
        '食べる',
        '飲む',
        '知る',
        'わかる',
        '今日',
        'きょう',
        '明日',
        'あした',
        '今',
        'いま',
        '日本',
        '東京',
        '会社',
        '仕事',
        '学校',
        'そう思う',
    }
)

JA_PARTICLES_AND_VERB_ENDINGS = (
    'が',
    'を',
    'に',
    'へ',
    'で',
    'から',
    'より',
    'まで',
    'ます',
    'ました',
    'ません',
    'でした',
    'たい',
    'たく',
    'ている',
    'てます',
    'てる',
    'すいた',
    'すいて',
    '思う',
    'おもう',
    '思って',
    '言う',
    'いう',
    '言って',
    '疲れた',
)

ZH_NAME_STOPWORDS = frozenset(
    {
        '这个',
        '那个',
        '这些',
        '那些',
        '这里',
        '那里',
        '我们',
        '你们',
        '他们',
        '她们',
        '它们',
        '大家',
        '自己',
        '别人',
        '什么',
        '谁',
        '哪',
        '哪个',
        '哪里',
        '怎么',
        '怎样',
        '一个',
        '不是',
        '就是',
        '也是',
        '都是',
        '只是',
        '还是',
        '真的',
        '觉得',
        '认为',
        '以为',
        '知道',
        '不知道',
        '想',
        '要',
        '可以',
        '应该',
        '能够',
        '没有',
        '不行',
        '中国人',
        '外国人',
        '学生',
        '老师',
        '医生',
        '朋友',
        '同事',
        '老板',
        '大人',
        '小孩',
        '孩子',
        '男人',
        '女人',
        '人类',
        '新人',
        '成员',
        '今天',
        '明天',
        '现在',
        '中国',
        '北京',
        '公司',
        '工作',
        '学校',
        '我们的这个',
    }
)

ZH_INVALID_CHARS = frozenset('的了着得地')

KO_NAME_STOPWORDS = frozenset(
    {
        '학생',
        '선생님',
        '한국인',
        '외국인',
        '친구',
        '사람',
        '사람들',
        '이것',
        '그것',
        '저것',
        '여기',
        '거기',
        '저기',
        '우리',
        '저희',
        '누구',
        '무엇',
        '생각',
        '진짜',
        '정말',
        '오늘',
        '내일',
        '지금',
        '회사',
        '학교',
        '일',
    }
)

KO_VERB_ENDINGS = (
    '합니다',
    '입니다',
    '갑니다',
    '옵니다',
    '습니다',
    'ㅂ니다',
    '있습니다',
    '없습니다',
    '해요',
    '가요',
    '와요',
)

# Pronouns and filler words the introduction patterns can capture from run-on
# transcripts (e.g. "I'm It was great", "I'm You know...") — never real names (#5223).
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
        'because',
        'googling',
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
    | JA_NAME_STOPWORDS
    | ZH_NAME_STOPWORDS
    | KO_NAME_STOPWORDS
)


def _is_valid_cjk_speaker_name(name: str, pattern_lang: Optional[str] = None) -> bool:
    """Validate that candidate CJK name is plausible and not a full sentence or clause."""
    has_cjk = bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF\uAC00-\uD7A3]', name))
    if not has_cjk:
        return True

    # CJK names are typically 2-4 characters, rarely 5-6 (compound or transliterated names)
    if len(name) > 6:
        return False

    is_all_kanji_or_han = bool(re.search(r'^[\u4E00-\u9FAF]+$', name))
    has_kana = bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF]', name))
    has_hangul = bool(re.search(r'[\uAC00-\uD7A3]', name))

    # Japanese validation: applied when matched by Japanese pattern, or contains kana,
    # or is all-kanji without specific non-ja language hint
    if pattern_lang == 'ja' or has_kana or (is_all_kanji_or_han and pattern_lang != 'zh'):
        for ending in JA_PARTICLES_AND_VERB_ENDINGS:
            if ending in name:
                return False
        if name in JA_NAME_STOPWORDS:
            return False

    # Chinese Han characters validation: applied when matched by Chinese pattern,
    # or is Han characters without specific non-zh language hint
    if pattern_lang == 'zh' or (is_all_kanji_or_han and pattern_lang != 'ja'):
        if len(name) > 5:
            return False
        if name in ZH_NAME_STOPWORDS:
            return False
        for char in ZH_INVALID_CHARS:
            if char in name:
                return False

    # Korean Hangul validation: applied when matched by Korean pattern or contains Hangul
    if pattern_lang == 'ko' or has_hangul:
        if len(name) > 5:
            return False
        if name in KO_NAME_STOPWORDS:
            return False
        for ending in KO_VERB_ENDINGS:
            if name.endswith(ending):
                return False

    return True


@dataclass(frozen=True)
class SpeakerNameDetection:
    """A name read out of transcript text, and how much authority the phrasing carries.

    ``explicit`` is true only for a self-introduction ("My name is Ada", 私の名前は…).
    A bare copula ("I'm Ada") sets it false: the same phrasing produces "I'm Chinese"
    and "I'm Googling it", so the name may be reused to resolve a person the user
    already has, but must not create one (#15247 fallout — auto-created people).
    """

    name: str
    explicit: bool


def _is_explicit_introduction(pattern: str, match: 're.Match[str]') -> bool:
    groups = match.groups()
    if len(groups) < 2:
        return pattern not in _NAME_FIRST_COPULAR_PATTERNS
    lead_in = groups[0]
    if not lead_in:
        return False
    return lead_in.strip().lower() not in COPULAR_SELF_REFERENCE_LEAD_INS


def detect_speaker_from_text(text: str, language: Optional[str] = None) -> Optional[str]:
    """Back-compatible name-only view of :func:`detect_speaker_introduction`.

    Callers that only *resolve* an existing person keep using this; anything that
    can create a person must read ``explicit`` from the detection instead.
    """
    detection = detect_speaker_introduction(text, language=language)
    return detection.name if detection else None


def detect_speaker_introduction(text: str, language: Optional[str] = None) -> Optional[SpeakerNameDetection]:
    if language and language in SPEAKER_IDENTIFICATION_PATTERNS:
        seen = set()
        patterns = []
        for p in SPEAKER_IDENTIFICATION_PATTERNS[language]:
            if p not in seen:
                seen.add(p)
                patterns.append(p)
        if language != 'en' and 'en' in SPEAKER_IDENTIFICATION_PATTERNS:
            for p in SPEAKER_IDENTIFICATION_PATTERNS['en']:
                if p not in seen:
                    seen.add(p)
                    patterns.append(p)
        for p in patterns_to_check:
            if p not in seen:
                seen.add(p)
                patterns.append(p)
    else:
        patterns = patterns_to_check

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            name = match.groups()[-1]
            if not name:
                continue

            matched_lang = PATTERN_TO_LANG.get(pattern)

            # Strip trailing Japanese copulas if captured
            if re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', name):
                name = re.sub(r'(?:です|だ|でーす|だよ)$', '', name).strip()
            # Strip trailing Korean copulas if captured
            if re.search(r'[\uAC00-\uD7A3]', name):
                name = re.sub(r'(?:입니다|이에요|예요|이야|야)$', '', name).strip()

            name = name.strip(' \t\r\n、。，．！？!?.,')

            if len(name) < 2:
                continue

            if name.lower() in SPEAKER_NAME_STOPWORDS:
                continue

            if not _is_valid_cjk_speaker_name(name, pattern_lang=matched_lang):
                continue

            normalized = (
                name
                if re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF\uAC00-\uD7A3]', name)
                else name.capitalize()
            )
            return SpeakerNameDetection(name=normalized, explicit=_is_explicit_introduction(pattern, match))
    return None


_VERIFY_OUTCOMES = frozenset({'transcription_failed', 'insufficient_words', 'multi_speaker', 'text_mismatch'})


def _verify_outcome(reason: str) -> str:
    outcome = reason.split(':', 1)[0].strip()
    return outcome if outcome in _VERIFY_OUTCOMES else 'error'


async def extract_speaker_samples(
    uid: str,
    person_id: str,
    conversation_id: str,
    segment_ids: List[str],
    sample_rate: int = 16000,
) -> str:
    """
    Extract a pooled speech sample for ``person_id`` and store it as their voice profile.

    Candidate segments come from the winning manual receipt decision when a
    receipt exists (pooled across the requested anchors' voice groups, resolving
    stale ids to the current receipt), or are restricted to the explicitly
    passed ids when it does not. Exactly one bounded outcome is recorded per
    invocation via ``omi_person_voice_learning_total`` plus the C2 fields.
    """
    outcome = 'error'
    person: Optional[Dict[str, Any]] = None
    clean_seconds = 0.0
    try:
        # The user can turn off saving other people's voices; this is the one choke
        # point every teaching path (tag sheet, tag prompts, live socket) reaches.
        settings = await run_blocking(db_executor, voice_profiles_db.get_voice_profile_settings, uid)
        if not settings['save_other_voice_profiles']:
            outcome = 'disabled'
            person = await run_blocking(db_executor, users_db.get_person, uid, person_id)
            return outcome

        # Snapshot the person before slow audio work. Publishing compares this version
        # so a correction, deletion or replacement cannot resurrect stale teaching.
        person = await run_blocking(db_executor, users_db.get_person, uid, person_id)
        if not person:
            outcome = 'person_missing'
            return outcome

        # Fetch conversation to get started_at and segment details
        conversation = await run_blocking(db_executor, conversations_db.get_conversation, uid, conversation_id)
        if not conversation:
            outcome = 'conversation_missing'
            return outcome

        # Sample extraction runs live, while the conversation is still processing, so
        # conversation['language'] (only resolved at finalization) is normally empty here.
        # Fall back to the user's app-level language preference, same as chat/memories/
        # process_conversation, instead of silently defaulting to English downstream.
        sample_language = conversation.get('language') or await run_blocking(
            db_executor, users_db.get_user_language_preference, uid
        )

        started_at = conversation.get('started_at')
        if not started_at:
            outcome = 'no_audio'
            return outcome

        # Build segment lookup from conversation's transcript_segments
        conv_segments = conversation.get('transcript_segments', [])

        # Get chunks from audio_files instead of storage listing
        audio_files = conversation.get('audio_files', [])
        if not audio_files:
            outcome = 'no_audio'
            return outcome

        # Collect all chunk timestamps from audio files
        all_timestamps: List[Any] = []
        for af in audio_files:
            all_timestamps.extend(af.get('chunk_timestamps', []))
        if not all_timestamps:
            outcome = 'no_chunks'
            return outcome

        requested_ids = {sid for sid in (segment_ids or []) if sid}
        receipt = conversation.get('manual_speaker_assignments') or {}
        if receipt.get('segments') or receipt.get('speakers'):
            authorized = authorized_teaching_segments(conversation, person_id)
            anchor_groups = {segment_group(s) for s in authorized if s.get('id') in requested_ids}
            if not anchor_groups:
                anchor_groups = {segment_group(s) for s in authorized}
            candidates = [s for s in authorized if segment_group(s) in anchor_groups]
            authorized_ids = {s.get('id') for s in authorized}
        else:
            candidates = [
                s
                for s in conv_segments
                if s.get('id') in requested_ids and s.get('person_id') == person_id and not s.get('is_user')
            ]
            authorized_ids = {s.get('id') for s in candidates}
        if not candidates:
            still_present = any(s.get('id') in requested_ids for s in conv_segments)
            outcome = 'stale_assignment' if still_present else 'no_authorized_segments'
            return outcome

        plan = plan_pooled_intervals(candidates, conv_segments, allowed_source_ids=authorized_ids)
        clean_seconds = plan.total_seconds

        coverage_conversation: Any = conversation
        origin_window = provisional_window(conversation, 0.0, 1.0)
        if origin_window is not None:
            coverage_conversation = {**conversation, 'started_at': origin_window[0]}

        if is_audio_timeline_v2(conversation):
            # v2: extract only from validated coverage; an uncovered
            # window is unavailable, never an embedding of other audio.
            kept_intervals: List[Any] = []
            kept_contributors: List[Any] = []
            uncovered = False
            for interval, contributors in zip(plan.intervals, plan.contributors):
                coverage = coverage_outcome(coverage_conversation, interval[0], interval[1])
                OMI_AUDIO_TIMELINE_COVERAGE_TOTAL.labels(mode='v2', outcome=coverage).inc()
                if coverage == 'covered':
                    kept_intervals.append(interval)
                    kept_contributors.append(contributors)
                else:
                    uncovered = True
            plan = PooledClipPlan(kept_intervals, kept_contributors, union_seconds(kept_intervals), plan.contaminated)
            clean_seconds = plan.total_seconds
            if uncovered and plan.total_seconds < TEACHING_MIN_TOTAL_SECONDS:
                outcome = 'uncovered_audio'
                return outcome

        if plan.total_seconds < TEACHING_MIN_TOTAL_SECONDS:
            outcome = 'contaminated' if plan.contaminated else 'insufficient_speech'
            return outcome

        timeline_v2 = is_audio_timeline_v2(conversation)
        read_session = AudioChunkReadSession(uid, conversation_id, sample_rate)
        use_capture = False
        legacy_outcome: Optional[str] = None

        def capture_retry(failed: str) -> bool:
            # The legacy position failed to yield verified speech. Live text and stored audio run on
            # different clocks, so try once more where the receiver recorded hearing these segments.
            # If that fails too, the attempt reports what the legacy position found.
            nonlocal use_capture, legacy_outcome
            if use_capture or timeline_v2:
                return False
            shifts = [
                capture_shift(conversation, start, end, segments=contributors)
                for (start, end), contributors in zip(plan.intervals, plan.contributors)
            ]
            if not any(shift is not None and abs(shift) >= CAPTURE_RETRY_MIN_SHIFT_SECONDS for shift in shifts):
                return False
            use_capture = True
            legacy_outcome = failed
            OMI_SPEAKER_CAPTURE_RETRY_TOTAL.labels(target='person', outcome='attempted').inc()
            return True

        while True:
            clips: List[bytes] = []
            kept_contributors = []
            fully_decoded: List[Tuple[float, float, List[Mapping[str, Any]]]] = []
            unavailable_window = False
            decoded_seconds = 0.0
            covered_end: Optional[float] = None
            for (start, end), contributors in zip(plan.intervals, plan.contributors):
                clip_start = start if covered_end is None else max(start, covered_end)
                if clip_start >= end:
                    continue
                covered_end = end
                placement = locate(conversation, clip_start, end, segments=contributors)
                if placement.reason in ('unplaced', 'invalid_window', 'missing_origin'):
                    continue
                if not timeline_v2:
                    window = (
                        placement.window
                        or (
                            capture_window(conversation, clip_start, end, segments=contributors)
                            if use_capture
                            else None
                        )
                        or provisional_window(conversation, clip_start, end)
                    )
                    if window is None:
                        continue
                    clip = await run_blocking(
                        sync_executor,
                        legacy_speaker_clip_pcm,
                        uid,
                        conversation_id,
                        window[0],
                        window[1],
                        sample_rate,
                        session=read_session,
                        timestamps=all_timestamps,
                        caller='teaching',
                    )
                    if clip is None:
                        unavailable_window = True
                        continue
                    clips.append(clip)
                    kept_contributors.extend(contributors)
                    decoded_seconds += len(clip) / (sample_rate * 2)
                    needed_bytes = (round(end * sample_rate) - round(clip_start * sample_rate)) * 2
                    if len(clip) == needed_bytes:
                        fully_decoded.append((clip_start, end, contributors))
                    continue
                if placement.reason != 'v2' or placement.window is None:
                    continue
                abs_start, abs_end = placement.window
                relevant_timestamps = v2_relevant_timestamps(conversation, abs_start, abs_end)
                span_starts = [
                    bounds[0]
                    for audio_file in audio_files
                    for span in audio_file.get('chunk_spans') or []
                    if (bounds := chunk_span_bounds(span)) is not None and bounds[0] < abs_end and bounds[1] > abs_start
                ]
                if not relevant_timestamps or not span_starts:
                    continue
                buffer_start = min(span_starts)
                # Download, merge, and extract (sync_executor avoids parent-child deadlock on storage_executor, #7387)
                try:
                    merged = await run_blocking(
                        sync_executor,
                        download_audio_chunks_and_merge,
                        uid,
                        conversation_id,
                        relevant_timestamps,
                        fill_gaps=True,
                        sample_rate=sample_rate,
                    )
                except FileNotFoundError:
                    continue
                # Use av for sample-accurate trimming
                clip = _trim_pcm_audio(merged or b'', sample_rate, abs_start - buffer_start, abs_end - buffer_start)
                clip = clip[: int(round((end - clip_start) * sample_rate)) * 2]
                if clip:
                    clips.append(clip)
                    kept_contributors.extend(contributors)
                    decoded_seconds += len(clip) / (sample_rate * 2)
                    needed_bytes = (round(end * sample_rate) - round(clip_start * sample_rate)) * 2
                    if len(clip) == needed_bytes:
                        fully_decoded.append((clip_start, end, contributors))

            if not clips:
                failed = 'uncovered_audio' if unavailable_window else 'no_chunks'
                if capture_retry(failed):
                    continue
                clean_seconds = 0.0
                outcome = legacy_outcome or failed
                return outcome
            sample_audio = b''.join(clips)
            clean_seconds = min(plan.total_seconds, decoded_seconds)
            if decoded_seconds < TEACHING_MIN_TOTAL_SECONDS:
                failed = 'uncovered_audio' if unavailable_window else 'insufficient_speech'
                if capture_retry(failed):
                    continue
                outcome = legacy_outcome or failed
                return outcome

            # Missing intervals must not abort later usable speech or contribute
            # transcript text to the verification of audio we did not include.
            contributing = {seg['id']: seg for seg in kept_contributors if seg.get('id')}
            ordered_contributors = sorted(
                contributing.values(), key=lambda seg: (float(seg.get('start') or 0.0), str(seg.get('id')))
            )
            expected_text = ' '.join(str(seg.get('text') or '').strip() for seg in ordered_contributors)
            contributing_ids = [seg['id'] for seg in ordered_contributors if seg['id'] in authorized_ids]

            wav_bytes = _pcm_to_wav_bytes(sample_audio, sample_rate)

            transcript, is_valid, reason = await verify_and_transcribe_sample(
                wav_bytes, sample_rate, expected_text, language=sample_language
            )
            if not is_valid or transcript is None:
                # Bounded text search belongs to the legacy cut and runs before the capture retry.
                if (
                    not use_capture
                    and reason.startswith('text_mismatch')
                    and len(plan.intervals) == len(clips) == len(fully_decoded) == 1
                ):
                    rec_start, rec_end, rec_contributors = fully_decoded[0]
                    ordered_rec = sorted(
                        (seg for seg in rec_contributors if seg.get('id')),
                        key=lambda seg: (float(seg.get('start') or 0.0), str(seg.get('id'))),
                    )
                    if (
                        rec_end - rec_start >= TEACHING_MIN_TOTAL_SECONDS
                        and ordered_rec
                        and len({segment_group(seg) for seg in ordered_rec}) == 1
                    ):
                        rec_text = ' '.join(str(seg.get('text') or '').strip() for seg in ordered_rec)
                        recovered = await recover_teaching_clip(
                            uid,
                            conversation,
                            rec_start,
                            rec_end,
                            rec_text,
                            sample_language,
                            sample_rate,
                            session=read_session,
                            anchor_offset=rec_start - float(ordered_rec[0].get('start') or 0.0),
                        )
                        if recovered is not None:
                            sample_audio, transcript = recovered
                            wav_bytes = _pcm_to_wav_bytes(sample_audio, sample_rate)
                            is_valid = True
                if not is_valid or transcript is None:
                    failed = _verify_outcome(reason)
                    if not reason.startswith('transcription_failed') and capture_retry(failed):
                        continue
                    outcome = legacy_outcome or failed
                    return outcome
            break

        # Complete embedding work before replacing anything. A failed provider
        # call leaves the prior profile intact and allows a later retry.
        try:
            embedding = await run_blocking(sync_executor, extract_embedding_from_bytes, wav_bytes, "sample.wav")
        except Exception:
            outcome = 'embedding_failed'
            return outcome
        embedding_list = embedding.flatten().tolist()
        if not embedding_list or not np.isfinite(embedding).all() or not np.any(embedding):
            outcome = 'embedding_failed'
            return outcome
        path = await run_blocking(
            storage_executor, upload_person_speech_sample_from_bytes, sample_audio, uid, person_id, sample_rate
        )
        old_samples = await run_blocking(
            db_executor,
            users_db.replace_person_speech_profile,
            uid,
            person_id,
            person.get('updated_at'),
            path,
            transcript,
            embedding_list,
            conversation_id,
            contributing_ids,
            speech_seconds=clean_seconds,
            expected_receipt_generation=receipt.get('generation', 0),
        )
        if old_samples is None:
            await run_blocking(storage_executor, delete_sample_from_storage, path)
            outcome = 'stale_assignment'
            return outcome
        outcome = 'stored'
        if use_capture:
            OMI_SPEAKER_CAPTURE_RETRY_TOTAL.labels(target='person', outcome='stored').inc()
        try:
            for old_path in old_samples:
                if old_path != path:
                    await run_blocking(storage_executor, delete_sample_from_storage, old_path)
        except Exception as error:
            logger.warning(
                'speaker_voice_learning cleanup failed conversation=%s exception_type=%s',
                conversation_id,
                type(error).__name__,
            )
        return outcome
    except asyncio.CancelledError:
        outcome = 'timeout'
        raise
    except TimeoutError:
        outcome = 'timeout'
    except Exception as error:
        outcome = 'error'
        logger.warning(
            'speaker_voice_learning failed conversation=%s exception_type=%s', conversation_id, type(error).__name__
        )
    finally:
        OMI_PERSON_VOICE_LEARNING_TOTAL.labels(outcome=outcome).inc()
        try:
            if person is not None and outcome != 'stored':
                state = learning_state_for_outcome(outcome)
                needed_seconds = (
                    max(0.0, TEACHING_MIN_TOTAL_SECONDS - clean_seconds) if state == 'needs_more_speech' else None
                )
                await run_blocking(
                    db_executor,
                    speaker_learning_db.update_person_voice_learning,
                    uid,
                    person_id,
                    person.get('updated_at'),
                    outcome=outcome,
                    state=state,
                    speech_seconds=clean_seconds or None,
                    needed_seconds=needed_seconds,
                )
        except BaseException:
            pass
        logger.info('speaker_voice_learning outcome=%s conversation=%s', outcome, conversation_id)
    return outcome
