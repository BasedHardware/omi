"""Teaching-only bounded recovery when stored times miss the audio.

When a teaching clip cut at the provisional position fails transcript
verification with ``text_mismatch``, the labeled words may still exist in the
stored audio at a shifted position. This module searches a bounded
neighbourhood around the provisional window — at most
``TEXT_SEARCH_PAD_SECONDS`` on each side, never more than
``TEXT_SEARCH_MAX_SECONDS`` of audio — with one extra transcription, anchors
the expected words by their word-level timestamps, re-cuts there, and re-runs
the unchanged verification gate (0.9 containment, dominant speaker) once.

This is recovery of *placement* only: it grants no acoustic or speaker
authority. Disabled by default behind ``SPEAKER_TEACHING_TEXT_PLACEMENT``
because a locally cached-word proxy is not deployed STT evidence; the runtime
setting is documentation-level, no deploy config changes.

Outcome accounting: ``omi_speaker_placement_search_total{outcome}`` uses the
bounded labels disabled/not_eligible/no_audio/transcription_failed/
unsupported_word_times/text_anchor_missing/ambiguous_text_anchor/
rejected_quality/recovered; the seconds counter measures audio actually
submitted to the STT calls. No ids or text enter logs or labels.
"""

import logging
import math
import os
import time
from typing import Any, Mapping, Optional, Tuple

from prometheus_client import Counter

from utils import speaker_sample
from utils.conversations.audio_placement import (
    TEXT_ANCHOR_MAX_WORDS,
    TEXT_SEARCH_MAX_SECONDS,
    TEXT_SEARCH_PAD_SECONDS,
    locate_in_verified_words,
    provisional_window,
)
from utils.executors import run_blocking, sync_executor
from utils.observability.fallback import record_fallback
from utils.other.audio_chunks import AudioChunkReadSession
from utils.speaker_audio import legacy_speaker_clip_pcm
from utils.speaker_tag_prompts.clips import pcm_to_wav, trim_pcm16

logger = logging.getLogger(__name__)

OMI_SPEAKER_PLACEMENT_SEARCH_TOTAL = Counter(
    'omi_speaker_placement_search_total',
    'Bounded teaching text placement attempts.',
    ['outcome'],
)
OMI_SPEAKER_CAPTURE_RETRY_TOTAL = Counter(
    'omi_speaker_capture_retry_total',
    'Teaching attempts retried at the receiver capture window after the legacy position failed.',
    ['target', 'outcome'],
)
OMI_SPEAKER_PLACEMENT_SEARCH_AUDIO_SECONDS = Counter(
    'omi_speaker_placement_search_audio_seconds_total',
    'Additional audio submitted for teaching placement.',
)

_FEATURE_FLAG = 'SPEAKER_TEACHING_TEXT_PLACEMENT'
_MAX_PIECE_SECONDS = 12.0


def _feature_enabled() -> bool:
    return os.getenv(_FEATURE_FLAG, '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _chunk_timestamps(conversation: Mapping[str, Any]) -> list:
    timestamps = set()
    for audio_file in conversation.get('audio_files') or []:
        if not isinstance(audio_file, Mapping):
            continue
        for ts in audio_file.get('chunk_timestamps') or []:
            if isinstance(ts, (int, float)) and not isinstance(ts, bool) and math.isfinite(ts):
                timestamps.add(float(ts))
    return sorted(timestamps)


def _has_unplaced_overlap(conversation: Mapping[str, Any], start: float, end: float) -> bool:
    for segment in conversation.get('transcript_segments') or []:
        if not isinstance(segment, Mapping):
            continue
        seg_start = segment.get('start')
        seg_end = segment.get('end')
        if (
            isinstance(seg_start, (int, float))
            and isinstance(seg_end, (int, float))
            and seg_start < end
            and seg_end > start
            and segment.get('audio_alignment') == 'unplaced'
        ):
            return True
    return False


async def recover_teaching_clip(
    uid: str,
    conversation: Mapping[str, Any],
    start: float,
    end: float,
    expected_text: str,
    language: Optional[str],
    sample_rate: int = 16000,
    *,
    session: Optional[AudioChunkReadSession] = None,
    anchor_offset: float = 0.0,
) -> Optional[Tuple[bytes, str]]:
    """Re-cut a mis-verified teaching clip where its words actually are, or None."""
    outcome = 'disabled'
    attempted = False
    try:
        if not _feature_enabled():
            return None
        outcome = 'not_eligible'
        duration = end - start
        offset_value: Any = anchor_offset
        rate_value: Any = sample_rate
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not (0 < duration <= _MAX_PIECE_SECONDS)
            or not math.isfinite(duration)
            or not expected_text.strip()
            or isinstance(rate_value, bool)
            or not isinstance(rate_value, int)
            or rate_value <= 0
            or isinstance(offset_value, bool)
            or not isinstance(offset_value, (int, float))
            or not math.isfinite(offset_value)
            or offset_value < 0
        ):
            return None
        window = provisional_window(conversation, start, end)
        if window is None:
            return None
        if _has_unplaced_overlap(conversation, start, end):
            return None
        timestamps = _chunk_timestamps(conversation)
        if not timestamps:
            outcome = 'no_audio'
            return None
        abs_start, abs_end = window
        search_start = max(abs_start - TEXT_SEARCH_PAD_SECONDS, timestamps[0])
        search_end = min(abs_end + TEXT_SEARCH_PAD_SECONDS, search_start + TEXT_SEARCH_MAX_SECONDS)
        if search_end <= search_start:
            outcome = 'no_audio'
            return None

        conversation_id = conversation.get('id')
        if not isinstance(conversation_id, str) or not conversation_id:
            return None
        attempted = True
        session = session or AudioChunkReadSession(uid, conversation_id, sample_rate)
        pcm = bytearray()
        cursor = search_start
        while cursor < search_end:
            piece_end = min(cursor + _MAX_PIECE_SECONDS, search_end)
            try:
                piece = await run_blocking(
                    sync_executor,
                    legacy_speaker_clip_pcm,
                    uid,
                    conversation_id,
                    cursor,
                    piece_end,
                    sample_rate,
                    session=session,
                    timestamps=timestamps,
                    caller='teaching',
                )
            except FileNotFoundError:
                outcome = 'no_audio'
                return None
            needed = (round(piece_end * sample_rate) - round(cursor * sample_rate)) * 2
            if piece is None or len(piece) != needed:
                outcome = 'no_audio'
                return None
            pcm.extend(piece)
            cursor = piece_end
        pcm = pcm[: int(round(TEXT_SEARCH_MAX_SECONDS * sample_rate)) * 2]
        audio_seconds = len(pcm) / (sample_rate * 2)

        stt_deadline = time.monotonic() + 30.0
        try:
            OMI_SPEAKER_PLACEMENT_SEARCH_AUDIO_SECONDS.inc(audio_seconds)
            with speaker_sample.verification_stt_deadline(stt_deadline):
                raw_words = await run_blocking(
                    sync_executor,
                    speaker_sample.deepgram_prerecorded_from_bytes,
                    pcm_to_wav(bytes(pcm), sample_rate),
                    sample_rate,
                    True,
                    language=language,
                )
        except (RuntimeError, FileNotFoundError, TimeoutError):
            outcome = 'transcription_failed'
            return None
        words_result: Any = raw_words
        if isinstance(words_result, tuple):
            words_result = words_result[0]
        if not isinstance(words_result, list) or len(words_result) > TEXT_ANCHOR_MAX_WORDS:
            outcome = 'unsupported_word_times'
            return None

        placement = locate_in_verified_words(
            expected_text,
            words_result,
            duration,
            audio_duration=audio_seconds,
            anchor_offset=anchor_offset,
        )
        if placement.reason != 'text_anchor' or placement.window is None:
            outcome = (
                placement.reason
                if placement.reason in ('unsupported_word_times', 'text_anchor_missing', 'ambiguous_text_anchor')
                else 'not_eligible'
            )
            return None
        if time.monotonic() >= stt_deadline:
            outcome = 'transcription_failed'
            return None
        first, last = placement.window
        expected_bytes = (round(last * sample_rate) - round(first * sample_rate)) * 2
        recovered_pcm = trim_pcm16(bytes(pcm), sample_rate, first, last)
        if expected_bytes <= 0 or len(recovered_pcm) != expected_bytes:
            outcome = 'no_audio'
            return None

        wav = pcm_to_wav(recovered_pcm, sample_rate)
        OMI_SPEAKER_PLACEMENT_SEARCH_AUDIO_SECONDS.inc(len(recovered_pcm) / (sample_rate * 2))
        try:
            with speaker_sample.verification_stt_deadline(stt_deadline):
                transcript, is_valid, reason = await speaker_sample.verify_and_transcribe_sample(
                    wav, sample_rate, expected_text, language=language
                )
        except TimeoutError:
            outcome = 'transcription_failed'
            return None
        if not is_valid or transcript is None:
            outcome = 'transcription_failed' if reason.startswith('transcription_failed') else 'rejected_quality'
            return None
        outcome = 'recovered'
        return recovered_pcm, transcript
    finally:
        OMI_SPEAKER_PLACEMENT_SEARCH_TOTAL.labels(outcome=outcome).inc()
        if attempted:
            record_fallback(
                component='other',
                from_mode='other',
                to_mode='other',
                reason='other',
                outcome='recovered' if outcome == 'recovered' else 'exhausted',
            )
