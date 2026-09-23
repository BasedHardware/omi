"""User-initiated STT replay for one stored conversation.

``POST /v1/conversations/{id}/reprocess`` only re-runs LLM enrichment on the
existing transcript. This helper is the missing audio→transcript step: merge
the conversation's stored chunks, run the same prerecorded STT path the sync
pipeline uses, and return replacement segments. The route then hands those
segments to ``process_conversation(..., trigger=ProcessingTrigger.USER_REPROCESS)``.
"""

from __future__ import annotations

import logging
from typing import Any, List, Sequence

from database.users import get_user_transcription_preferences
from models.transcript_segment import TranscriptSegment
from utils.log_sanitizer import sanitize
from utils.other.storage import download_audio_chunks_and_merge, list_audio_chunks
from utils.stt.pre_recorded import postprocess_words, prerecorded_from_bytes

logger = logging.getLogger(__name__)


class StoredAudioUnavailableError(Exception):
    """The conversation has no stored audio chunks to send to STT."""


class StoredAudioEmptyTranscriptError(Exception):
    """STT completed but produced no transcribable speech."""


class StoredAudioTranscriptionFailedError(Exception):
    """The prerecorded STT provider failed."""


def collect_conversation_audio_timestamps(uid: str, conversation: Any) -> List[float]:
    """Return chunk timestamps for this conversation's stored audio.

    Prefer the conversation's ``audio_files`` records (the same grouping the
    playback path uses). Fall back to listing live GCS chunks so a conversation
    that never got ``audio_files`` stamped can still be re-transcribed.
    """
    timestamps: List[float] = []
    for audio_file in getattr(conversation, 'audio_files', None) or []:
        chunk_timestamps = getattr(audio_file, 'chunk_timestamps', None)
        if chunk_timestamps is None and isinstance(audio_file, dict):
            chunk_timestamps = audio_file.get('chunk_timestamps')
        if chunk_timestamps:
            timestamps.extend(float(ts) for ts in chunk_timestamps)
    if timestamps:
        return sorted(set(timestamps))

    conversation_id = getattr(conversation, 'id', None)
    if not conversation_id:
        return []
    chunks = list_audio_chunks(uid, conversation_id)
    return sorted(float(chunk['timestamp']) for chunk in chunks if chunk.get('timestamp') is not None)


def _resolve_stt_language(uid: str, language_code: str | None, conversation: Any) -> tuple[str, bool, List[str]]:
    prefs = get_user_transcription_preferences(uid)
    user_vocab = [word for word in dict.fromkeys(prefs.get('vocabulary', [])) if word != 'Omi']
    vocabulary = ['Omi'] + user_vocab[:99]
    user_language = prefs.get('language', '') or language_code or getattr(conversation, 'language', None) or ''
    single_language_mode = bool(prefs.get('single_language_mode', False))
    req_language = user_language if (single_language_mode and user_language) else 'multi'
    return req_language, not (single_language_mode and user_language), vocabulary


def transcribe_stored_conversation_audio(
    uid: str,
    conversation: Any,
    language_code: str | None = None,
) -> List[TranscriptSegment]:
    """Run prerecorded STT on the conversation's stored audio and return segments."""
    conversation_id = getattr(conversation, 'id', '')
    timestamps = collect_conversation_audio_timestamps(uid, conversation)
    if not timestamps:
        raise StoredAudioUnavailableError('No stored audio available to retranscribe')

    try:
        pcm_bytes = download_audio_chunks_and_merge(uid, conversation_id, timestamps)
    except FileNotFoundError:
        raise StoredAudioUnavailableError('No stored audio available to retranscribe') from None
    except Exception as exc:
        logger.error(
            'event=reprocess_transcription outcome=audio_merge_failed exception_type=%s',
            type(exc).__name__,
        )
        raise StoredAudioUnavailableError('No stored audio available to retranscribe') from exc

    if not pcm_bytes:
        raise StoredAudioUnavailableError('No stored audio available to retranscribe')

    req_language, return_language, vocabulary = _resolve_stt_language(uid, language_code, conversation)
    try:
        result = prerecorded_from_bytes(
            pcm_bytes,
            sample_rate=16000,
            diarize=True,
            encoding='linear16',
            language=req_language,
            return_language=return_language,
            keywords=vocabulary,
        )
    except Exception as exc:
        logger.error(
            'event=reprocess_transcription outcome=stt_failed exception_type=%s detail=%s',
            type(exc).__name__,
            sanitize(str(exc)),
        )
        raise StoredAudioTranscriptionFailedError('Transcription provider failed') from exc
    finally:
        del pcm_bytes

    words: Sequence[dict[str, Any]]
    if isinstance(result, tuple):
        words = result[0]
    else:
        words = result
    if not words:
        raise StoredAudioEmptyTranscriptError('Transcription produced no speech')

    segments = postprocess_words(list(words), 0)
    if not segments:
        raise StoredAudioEmptyTranscriptError('Transcription produced no speech')
    return segments
