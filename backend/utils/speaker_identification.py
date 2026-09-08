import io
import re
import wave
from typing import Any, Dict, List, Optional, cast

import av
import numpy as np

from database import conversations as conversations_db
from database import users as users_db
from utils.executors import db_executor, storage_executor, sync_executor, run_blocking
from utils.observability.fallback import record_fallback
from utils.other.storage import (
    download_audio_chunks_and_merge,
    upload_person_speech_sample_from_bytes,
)
from utils.speaker_sample import verify_and_transcribe_sample
from utils.speaker_sample_migration import maybe_migrate_person_samples
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
                skip_samples = int((start_sec - frame_time) * sample_rate)
                frame_start_sample = skip_samples

            if frame_end_time > end_sec:
                # Trim end of frame
                keep_duration = end_sec - max(frame_time, start_sec)
                frame_end_sample = frame_start_sample + int(keep_duration * sample_rate)

            if frame_start_sample < frame_end_sample:
                trimmed_samples.append(arr[frame_start_sample:frame_end_sample])

    if not trimmed_samples:
        return b''

    return np.concatenate(trimmed_samples).astype(np.int16).tobytes()


# Constants for speaker sample extraction
SPEAKER_SAMPLE_MIN_SEGMENT_DURATION = 10.0
SPEAKER_SAMPLE_WINDOW_HALF = SPEAKER_SAMPLE_MIN_SEGMENT_DURATION / 2

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


def detect_speaker_from_text(text: str, language: Optional[str] = None) -> Optional[str]:
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

            return (
                name
                if re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF\uAC00-\uD7A3]', name)
                else name.capitalize()
            )
    return None


async def _store_person_speaker_embedding(uid: str, person_id: str, wav_bytes: bytes, conversation_id: str) -> bool:
    """Store the speaker embedding for a person we just collected a sample for. Returns whether it landed.

    The person twin of the enrolment path in routers/speech_profile.py: the sample is saved either way, so
    the failure is not fatal, but without the embedding this person can never be matched in a future
    conversation. Same silent, permanent, per-principal loss of a capability (BACKLOG L20).
    """
    try:
        embedding = await run_blocking(sync_executor, extract_embedding_from_bytes, wav_bytes, "sample.wav")
        # Convert numpy array to list for Firestore storage
        embedding_list = embedding.flatten().tolist()
        await run_blocking(db_executor, users_db.set_person_speaker_embedding, uid, person_id, embedding_list)
        logger.info(
            f"Stored speaker embedding for person {person_id} (dim={len(embedding_list)}) {uid} {conversation_id}"
        )
        return True
    except Exception as emb_err:
        logger.error(f"Failed to extract/store speaker embedding: {emb_err} {uid} {conversation_id}")
        record_fallback(
            component='speaker',
            from_mode='enrolled',
            to_mode='no_embedding',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        return False


async def extract_speaker_samples(
    uid: str,
    person_id: str,
    conversation_id: str,
    segment_ids: List[str],
    sample_rate: int = 16000,
):
    """
    Extract speech samples from segments and store as speaker profiles.
    Fetches conversation from DB to get started_at and segment details.
    Processes each segment one by one, stops when sample limit reached.
    """
    try:
        # Run lazy migration for samples before checking count
        # (migration may drop invalid samples, freeing up space)
        person = await run_blocking(db_executor, users_db.get_person, uid, person_id)
        if person:
            person = await maybe_migrate_person_samples(uid, person)

        # Check sample count after migration
        sample_count = await run_blocking(db_executor, users_db.get_person_speech_samples_count, uid, person_id)
        if sample_count >= 1:
            logger.warning(f"Person {person_id} already has {sample_count} samples, skipping {uid} {conversation_id}")
            return

        # Fetch conversation to get started_at and segment details
        conversation = await run_blocking(db_executor, conversations_db.get_conversation, uid, conversation_id)
        if not conversation:
            logger.warning(f"Conversation {conversation_id} not found {uid}")
            return

        # Sample extraction runs live, while the conversation is still processing, so
        # conversation['language'] (only resolved at finalization) is normally empty here.
        # Fall back to the user's app-level language preference, same as chat/memories/
        # process_conversation, instead of silently defaulting to English downstream.
        sample_language = conversation.get('language') or await run_blocking(
            db_executor, users_db.get_user_language_preference, uid
        )

        started_at = conversation.get('started_at')
        if not started_at:
            logger.info(f"Conversation {conversation_id} has no started_at {uid}")
            return

        started_at_ts = started_at.timestamp() if hasattr(started_at, 'timestamp') else float(started_at)

        # Build segment lookup from conversation's transcript_segments
        conv_segments = conversation.get('transcript_segments', [])
        segment_map = {s.get('id'): s for s in conv_segments if s.get('id')}

        # Get chunks from audio_files instead of storage listing
        audio_files = conversation.get('audio_files', [])
        if not audio_files:
            logger.warning(f"No audio files found for {conversation_id}, skipping speaker sample extraction {uid}")
            return

        # Collect all chunk timestamps from audio files
        all_timestamps: List[Any] = []
        for af in audio_files:
            timestamps = af.get('chunk_timestamps', [])
            all_timestamps.extend(timestamps)

        if not all_timestamps:
            logger.warning(f"No chunk timestamps found for {conversation_id}, skipping speaker sample extraction {uid}")
            return

        # Build chunks list in expected format
        chunks: List[Dict[str, Any]] = [{'timestamp': ts} for ts in sorted(set(all_timestamps))]

        samples_added = 0
        max_samples_to_add = 1 - sample_count

        # Build ordered list with index lookup for expansion
        ordered_segments = [s for s in conv_segments if s.get('id')]
        segment_index_map = {s.get('id'): i for i, s in enumerate(ordered_segments)}

        for seg_id in segment_ids:
            if samples_added >= max_samples_to_add:
                break

            seg = segment_map.get(seg_id)
            if not seg:
                logger.warning(f"Segment {seg_id} not found in conversation {uid} {conversation_id}")
                continue

            segment_start = seg.get('start')
            segment_end = seg.get('end')
            if segment_start is None or segment_end is None:
                continue

            seg_duration = segment_end - segment_start
            speaker_id = seg.get('speaker_id')

            # If segment is too short, try expanding to adjacent segments with same speaker
            if seg_duration < SPEAKER_SAMPLE_MIN_SEGMENT_DURATION and speaker_id is not None:
                seg_idx = segment_index_map.get(seg_id)
                if seg_idx is not None:
                    i = seg_idx - 1
                    while i >= 0:
                        prev_seg = ordered_segments[i]
                        if prev_seg.get('speaker_id') != speaker_id:
                            break
                        prev_start = prev_seg.get('start')
                        if prev_start is not None:
                            segment_start = min(segment_start, prev_start)
                            seg_duration = segment_end - segment_start
                        if seg_duration >= SPEAKER_SAMPLE_MIN_SEGMENT_DURATION:
                            logger.info(
                                f"Expanded segment to {seg_duration:.1f}s by including adjacent segments {uid} {conversation_id}"
                            )
                            break
                        i -= 1

            if seg_duration < SPEAKER_SAMPLE_MIN_SEGMENT_DURATION:
                logger.info(
                    f"Segment too short ({seg_duration:.1f}s) even after expansion, skipping {uid} {conversation_id}"
                )
                continue

            # Extract centered sample window (10 seconds max from center of segment)
            seg_center = (segment_start + segment_end) / 2
            sample_start = max(segment_start, seg_center - SPEAKER_SAMPLE_WINDOW_HALF)
            sample_end = min(segment_end, seg_center + SPEAKER_SAMPLE_WINDOW_HALF)

            # Calculate absolute timestamps using the sample window
            abs_start = started_at_ts + sample_start
            abs_end = started_at_ts + sample_end

            # Find relevant chunks
            sorted_chunks = sorted(chunks, key=lambda c: c['timestamp'])

            # Find first chunk that starts at or before abs_start
            first_idx = 0
            for i, chunk in enumerate(sorted_chunks):
                if chunk['timestamp'] <= abs_start:
                    first_idx = i
                else:
                    break

            # Collect from first_idx up to abs_end
            relevant_timestamps: List[Any] = []
            for chunk in sorted_chunks[first_idx:]:
                if chunk['timestamp'] <= abs_end:
                    relevant_timestamps.append(chunk['timestamp'])
                else:
                    break

            if not relevant_timestamps:
                logger.info(
                    f"No relevant chunks for segment {segment_start:.1f}-{segment_end:.1f}s {uid} {conversation_id}"
                )
                continue

            # Download, merge, and extract (sync_executor avoids parent-child deadlock on storage_executor, #7387)
            merged = await run_blocking(
                sync_executor,
                download_audio_chunks_and_merge,
                uid,
                conversation_id,
                relevant_timestamps,
                fill_gaps=True,
                sample_rate=sample_rate,
            )
            buffer_start = min(relevant_timestamps)

            # Use av for sample-accurate trimming
            trim_start = abs_start - buffer_start
            trim_end = abs_end - buffer_start
            sample_audio = _trim_pcm_audio(merged, sample_rate, trim_start, trim_end)

            # Ensure minimum sample length (8 seconds)
            min_sample_seconds = 8.0
            min_sample_bytes = int(sample_rate * min_sample_seconds * 2)
            if len(sample_audio) < min_sample_bytes:
                actual_seconds = len(sample_audio) / (sample_rate * 2)
                logger.info(
                    f"Sample too short ({actual_seconds:.1f}s), need {min_sample_seconds}s, skipping {uid} {conversation_id}"
                )
                continue

            # Get expected text from segment for comparison
            expected_text = seg.get('text', '')

            # Convert PCM to WAV for Deepgram
            wav_bytes = _pcm_to_wav_bytes(sample_audio, sample_rate)

            # Verify sample quality and get transcript using centralized function
            transcript, is_valid, reason = await verify_and_transcribe_sample(
                wav_bytes, sample_rate, expected_text, language=sample_language
            )
            if not is_valid:
                logger.error(f"Sample failed quality check: {reason} {uid} {conversation_id}")
                continue  # Try next segment

            # Upload and store
            path = await run_blocking(
                storage_executor, upload_person_speech_sample_from_bytes, sample_audio, uid, person_id, sample_rate
            )

            success = await run_blocking(
                db_executor, users_db.add_person_speech_sample, uid, person_id, path, transcript=transcript
            )
            if success:
                samples_added += 1
                seg_text = seg.get('text', '')[:100]  # Truncate to 100 chars
                logger.info(
                    f"Stored speech sample {samples_added} for person {person_id}: segment_id={seg_id}, file={path}, text={seg_text} {uid} {conversation_id}"
                )

                # Extract and store speaker embedding (reuse wav_bytes from verification)
                await _store_person_speaker_embedding(uid, person_id, wav_bytes, conversation_id)
            else:
                logger.error(f"Failed to add speech sample for person {person_id} {uid} {conversation_id}")
                break  # Likely hit limit

    except Exception as e:
        logger.error(f"Error extracting speaker samples: {e} {uid} {conversation_id}")
