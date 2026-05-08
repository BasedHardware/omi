import os
from collections import defaultdict
from io import BytesIO
from typing import List, Optional, Sequence, Tuple, Union

import fal_client
from deepgram import DeepgramClient, DeepgramClientOptions

from models.transcript_segment import TranscriptSegment
from utils.byok import get_byok_key
from utils.other.endpoints import timeit
import logging

logger = logging.getLogger(__name__)

# Initialize Deepgram client for pre-recorded transcription
# WARN: the pre-recorded transcription is available on deepgram cloud
_deepgram_options = DeepgramClientOptions(options={"keepalive": "true"})
_deepgram_client = DeepgramClient(os.getenv('DEEPGRAM_API_KEY'), _deepgram_options)


def _deepgram_client_for_request() -> DeepgramClient:
    """Route to BYOK Deepgram key when set; otherwise use the process-wide client."""
    byok = get_byok_key('deepgram')
    if byok:
        return DeepgramClient(byok, _deepgram_options)
    return _deepgram_client


# Languages supported by nova-3
_deepgram_nova3_languages = {
    "ar",
    "ar-AE",
    "ar-SA",
    "ar-QA",
    "ar-KW",
    "ar-SY",
    "ar-LB",
    "ar-PS",
    "ar-JO",
    "ar-EG",
    "ar-SD",
    "ar-TD",
    "ar-MA",
    "ar-DZ",
    "ar-TN",
    "ar-IQ",
    "ar-IR",
    "be",
    "bg",
    "bn",
    "bs",
    "ca",
    "cs",
    "da",
    "da-DK",
    "de",
    "de-CH",
    "el",
    "en",
    "en-US",
    "en-AU",
    "en-GB",
    "en-IN",
    "en-NZ",
    "es",
    "es-419",
    "et",
    "fa",
    "fi",
    "fr",
    "fr-CA",
    "he",
    "hi",
    "hr",
    "hu",
    "id",
    "it",
    "ja",
    "kn",
    "ko",
    "ko-KR",
    "lt",
    "lv",
    "mk",
    "mr",
    "ms",
    "nl",
    "nl-BE",
    "no",
    "pl",
    "pt",
    "pt-BR",
    "pt-PT",
    "ro",
    "ru",
    "sk",
    "sl",
    "sr",
    "sv",
    "sv-SE",
    "ta",
    "te",
    "th",
    "th-TH",
    "tl",
    "tr",
    "uk",
    "ur",
    "vi",
    "zh",
    "zh-CN",
    "zh-Hans",
    "zh-HK",
    "zh-Hant",
    "zh-TW",
}


def get_deepgram_model_for_language(language: str) -> Tuple[str, str]:
    """
    Determine the appropriate Deepgram model and language for pre-recorded transcription.

    Args:
        language: The requested language code or 'multi' for auto-detection

    Returns:
        Tuple of (language_to_use, model_name)
    """
    # For multi-language mode
    if language == 'multi':
        return 'multi', 'nova-3'

    # Languages supported by nova-3
    if language in _deepgram_nova3_languages:
        return language, 'nova-3'

    # Unsupported language - fall back to multi for auto-detection
    return 'multi', 'nova-3'


@timeit
def deepgram_prerecorded(
    audio_url: str,
    speakers_count: int = None,
    attempts: int = 0,
    return_language: bool = False,
    diarize: bool = True,
    language: Optional[str] = None,
    model: str = "nova-3",
    keywords: Optional[Sequence[str]] = None,
) -> Union[List[dict], Tuple[List[dict], str]]:
    """
    Transcribe audio using Deepgram's pre-recorded API.
    Returns words in same format as fal_whisperx for compatibility with existing postprocessing.

    Args:
        audio_url: URL to the audio file
        speakers_count: Hint for number of speakers (not used by Deepgram, kept for API compatibility)
        attempts: Current retry attempt number
        return_language: If True, returns (words, language) tuple
        language: Language code to force, or 'multi' for multilingual auto-detection
        diarize: If True, enable speaker diarization
        keywords: Custom vocabulary words to boost transcription accuracy

    Returns:
        List of word dicts with format: {'timestamp': [start, end], 'speaker': 'SPEAKER_XX', 'text': 'word'}
        Or tuple of (words, language) if return_language=True
    """
    logger.info(f'deepgram_prerecorded {audio_url} {speakers_count} {attempts}')

    try:
        # 'multi' language means auto-detection
        is_multi = language == 'multi'
        should_detect_language = return_language or is_multi
        options = {
            "model": model,
            "smart_format": True,
            "punctuate": True,
            "diarize": diarize,
            "detect_language": should_detect_language,
            "utterances": True,
        }
        if language and not is_multi:
            options["language"] = language

        if keywords:
            if model in ('nova-3',):
                options["keyterm"] = list(keywords)
            else:
                options["keywords"] = list(keywords)

        response = _deepgram_client_for_request().listen.rest.v("1").transcribe_url({"url": audio_url}, options)

        # Extract words from response
        result = response.to_dict()
        channels = result.get('results', {}).get('channels', [])
        if not channels:
            raise Exception('No channels found in response')

        alternatives = channels[0].get('alternatives', [])
        if not alternatives:
            raise Exception('No alternatives found in response')

        dg_words = alternatives[0].get('words', [])
        if not dg_words:
            if return_language:
                detected_lang = channels[0].get('detected_language', 'en')
                if detected_lang and '-' in detected_lang:
                    detected_lang = detected_lang.split('-')[0]
                return [], detected_lang or 'en'
            return []

        # Convert Deepgram format to fal_whisperx compatible format
        # Deepgram: {word, start, end, confidence, punctuated_word, speaker (int)}
        # Expected: {timestamp: [start, end], speaker: 'SPEAKER_XX', text: 'word'}
        words = []
        for w in dg_words:
            speaker_id = w.get('speaker', 0)
            words.append(
                {
                    'timestamp': [w['start'], w['end']],
                    'speaker': f"SPEAKER_{speaker_id:02d}" if speaker_id is not None else None,
                    'text': w.get('punctuated_word', w['word']),
                }
            )

        if return_language:
            # Deepgram returns detected_language in the channel
            detected_lang = channels[0].get('detected_language', 'en')
            # Normalize language code (Deepgram might return 'en-US', we want 'en')
            if detected_lang and '-' in detected_lang:
                detected_lang = detected_lang.split('-')[0]
            return words, detected_lang or 'en'

        return words

    except Exception as e:
        logger.error(f'Deepgram prerecorded error: {e}')
        if attempts < 2:
            return deepgram_prerecorded(
                audio_url,
                speakers_count,
                attempts + 1,
                return_language,
                diarize,
                language,
                model,
                keywords,
            )
        raise RuntimeError(f'Deepgram transcription failed after {attempts + 1} attempts: {e}')


@timeit
def deepgram_prerecorded_from_bytes(
    audio_bytes: bytes,
    sample_rate: int = 16000,
    diarize: bool = True,
    attempts: int = 0,
    encoding: Optional[str] = None,
    channels: int = 1,
    language: Optional[str] = None,
    model: str = "nova-3",
    return_language: bool = False,
    keywords: Optional[Sequence[str]] = None,
) -> Union[List[dict], Tuple[List[dict], str]]:
    """
    Transcribe audio bytes using Deepgram's pre-recorded API.
    Returns words with speaker labels when diarize=True.

    Supports both WAV format (default) and raw PCM audio.
    For raw PCM, pass encoding='linear16' with appropriate sample_rate and channels.

    Args:
        audio_bytes: Audio bytes (WAV format or raw PCM)
        sample_rate: Audio sample rate in Hz (required for raw PCM, ignored for WAV)
        diarize: If True, enable speaker diarization
        attempts: Current retry attempt number
        encoding: Audio encoding format (e.g. 'linear16' for raw PCM). None for WAV.
        channels: Number of audio channels (default 1 for mono)
        language: Language code for transcription, or None for auto-detect
        model: Deepgram model name (default 'nova-3')
        return_language: If True, returns (words, language) tuple
        keywords: Custom vocabulary words to boost transcription accuracy

    Returns:
        List of word dicts with format: {'timestamp': [start, end], 'speaker': 'SPEAKER_XX', 'text': 'word'}
        Or tuple of (words, language) if return_language=True
    """
    logger.info(
        f'deepgram_prerecorded_from_bytes bytes_len={len(audio_bytes)} {sample_rate} {diarize} {attempts} encoding={encoding} language={language} model={model}'
    )

    try:
        is_multi = language == 'multi'
        should_detect_language = return_language or is_multi
        options = {
            "model": model,
            "smart_format": True,
            "punctuate": True,
            "diarize": diarize,
            "utterances": True,
            "detect_language": should_detect_language,
        }
        if language and not is_multi:
            options["language"] = language

        if keywords:
            if str(model).startswith("nova-3"):
                options["keyterm"] = list(keywords)
            else:
                options["keywords"] = list(keywords)

        # For raw PCM, Deepgram needs encoding + sample_rate to interpret the bytes
        if encoding:
            options["encoding"] = encoding
            options["sample_rate"] = sample_rate
            options["channels"] = channels

        # Wrap bytes in BytesIO for Deepgram client
        audio_buffer = BytesIO(audio_bytes)
        mimetype = "audio/raw" if encoding else "audio/wav"
        source = {"buffer": audio_buffer, "mimetype": mimetype}

        response = _deepgram_client_for_request().listen.rest.v("1").transcribe_file(source, options)

        # Extract words from response
        result = response.to_dict()
        result_channels = result.get('results', {}).get('channels', [])
        if not result_channels:
            raise Exception('No channels found in response')

        alternatives = result_channels[0].get('alternatives', [])
        if not alternatives:
            raise Exception('No alternatives found in response')

        dg_words = alternatives[0].get('words', [])
        if not dg_words:
            if return_language:
                detected_lang = result_channels[0].get('detected_language', 'en')
                if detected_lang and '-' in detected_lang:
                    detected_lang = detected_lang.split('-')[0]
                return [], detected_lang or 'en'
            return []

        # Convert Deepgram format to standard format
        # Deepgram: {word, start, end, confidence, punctuated_word, speaker (int)}
        # Expected: {timestamp: [start, end], speaker: 'SPEAKER_XX', text: 'word'}
        words = []
        for w in dg_words:
            speaker_id = w.get('speaker', 0)
            words.append(
                {
                    'timestamp': [w['start'], w['end']],
                    'speaker': f"SPEAKER_{speaker_id:02d}" if speaker_id is not None else None,
                    'text': w.get('punctuated_word', w['word']),
                }
            )

        if return_language:
            detected_lang = result_channels[0].get('detected_language', 'en')
            if detected_lang and '-' in detected_lang:
                detected_lang = detected_lang.split('-')[0]
            return words, detected_lang or 'en'

        return words

    except Exception as e:
        logger.error(f'Deepgram prerecorded from bytes error: {e}')
        if attempts < 2:
            return deepgram_prerecorded_from_bytes(
                audio_bytes,
                sample_rate,
                diarize,
                attempts + 1,
                encoding,
                channels,
                language,
                model,
                return_language,
                keywords,
            )
        raise RuntimeError(f'Deepgram transcription failed after {attempts + 1} attempts: {e}')


@timeit
def fal_whisperx(
    audio_url: str,
    speakers_count: int = None,
    attempts: int = 0,
    return_language: bool = False,
    diarize: bool = True,
    chunk_level: str = 'word',
) -> List[dict]:
    logger.info(f'fal_whisperx {audio_url} {speakers_count} {attempts}')

    try:
        handler = fal_client.submit(
            "fal-ai/whisper",
            arguments={
                "audio_url": audio_url,
                'task': 'transcribe',
                'diarize': diarize,
                'chunk_level': chunk_level,
                'version': '3',
                'batch_size': 64,
                'num_speakers': speakers_count,
            },
        )
        result = handler.get()
        # print(result)
        words = result.get('chunks', [])
        if not words:
            raise Exception('No chunks found')
        if return_language:
            languages = result.get('inferred_languages', ['en'])
            language = languages[0] if languages else 'en'
            return words, language
        return words
    except Exception as e:
        logger.error(e)
        if attempts < 2:
            return fal_whisperx(audio_url, speakers_count, attempts + 1, return_language)
        if return_language:
            return [], 'en'
        return []


def _words_cleaning(words: List[dict]):
    words_cleaned: List[dict] = []
    for i, w in enumerate(words):
        # if w['timestamp'][0] == w['timestamp'][1]:
        #     continue
        words_cleaned.append(
            {
                'start': round(w['timestamp'][0], 2),
                'end': round(w['timestamp'][1] or w['timestamp'][0] + 1, 2),
                'speaker': w['speaker'],
                'text': str(w['text']).strip(),
                'is_user': False,
                'person_id': None,
            }
        )

    for i, word in enumerate(words_cleaned):
        speaker = word['speaker']
        if not speaker:
            prev_chunk = words_cleaned[i - 1] if i > 0 else None
            next_chunk = words_cleaned[i + 1] if i < len(words_cleaned) - 1 else None
            prev_speaker = prev_chunk['speaker'] if prev_chunk else None
            next_speaker = next_chunk['speaker'] if next_chunk else None

            if prev_speaker and next_speaker:
                if prev_speaker == next_speaker:
                    speaker = prev_chunk['speaker']
                else:
                    secs_from_prev = word['start'] - prev_chunk['end'] if prev_chunk else 0
                    secs_to_next = next_chunk['start'] - word['end'] if next_chunk else 0
                    speaker = prev_speaker if secs_from_prev < secs_to_next else next_speaker
            elif prev_speaker:
                speaker = prev_speaker
            elif next_speaker:
                speaker = next_speaker
            else:
                speaker = 'SPEAKER_00'

            words_cleaned[i]['speaker'] = speaker

    # for chunk in words_cleaned:
    #     print(chunk)
    return words_cleaned


def _retrieve_user_speaker_id(words: list, skip_n_seconds: int):
    if not skip_n_seconds:
        return None

    user_speaker_id = defaultdict(int)
    for word in words:
        if word['start'] >= skip_n_seconds:
            break
        if not word['speaker']:
            continue
        user_speaker_id[word['speaker']] += 1

    user_speaker_id = max(user_speaker_id, key=user_speaker_id.get) if user_speaker_id else None
    return user_speaker_id


def _merge_segments(words: List[dict], skip_n_seconds: int, user_speaker_id: str):
    segments = []
    for word in words:
        if word['start'] < skip_n_seconds:
            continue
        word['is_user'] = word['speaker'] == user_speaker_id if word['speaker'] else False

        same_prev_speaker = word['speaker'] == segments[-1]['speaker'] if segments else False
        seconds_from_prev = word['start'] - segments[-1]['end'] if segments else 0

        # TODO: consider having a max segment size too
        if segments and same_prev_speaker and seconds_from_prev < 30:
            segments[-1]['end'] = word['end']
            segments[-1]['text'] += ' ' + word['text']
        else:
            segments.append(word)
    return segments


def _segments_as_objects(segments: List[dict]) -> List[TranscriptSegment]:
    if not segments:
        return []
    starts_at = segments[0]['start']
    return [
        TranscriptSegment(
            text=str(segment['text']).strip().capitalize(),
            speaker=segment['speaker'],
            is_user=segment['is_user'],
            person_id=None,
            start=round(segment['start'] - starts_at, 2),
            end=round(segment['end'] - starts_at, 2),
        )
        for segment in segments
    ]


def postprocess_words(
    words: List[dict], duration: int, skip_n_seconds: int = 0  # , merge_segments: bool = True
) -> List[TranscriptSegment]:
    words: List[dict] = _words_cleaning(words)
    user_speaker_id = _retrieve_user_speaker_id(words, skip_n_seconds)
    segments = _merge_segments(words, skip_n_seconds, user_speaker_id)
    segments = _segments_as_objects(segments)
    return segments
