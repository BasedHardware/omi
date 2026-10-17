"""Sync/WAL adapter for the shared triage, diarizer and assignment seam."""

import io
import logging
import time
import math
import os
import threading
from datetime import datetime, timezone

from database.redis_db import create_bounded_redis_client

from pydub import AudioSegment

from utils.conversations.final_pass_pyannote import run_final_pass, OUTCOMES
from utils.observability.fallback import record_fallback
from utils.stt.conversation_speakers import resolve_conversation_speakers
from utils.stt.speaker_embedding import extract_embedding_from_bytes, speaker_embedding_configured
from utils.stt.sync_speaker_evidence import collect_speaker_audio

logger = logging.getLogger(__name__)

# Cloud Run runs one Python worker per instance. Refuse rather than queue;
# the shared hourly reservation additionally bounds a horizontally scaled fleet.
_slots = threading.BoundedSemaphore(1)
_RESERVE_SCRIPT = """
local audio = tonumber(redis.call('hget', KEYS[1], 'audio_ms') or '0')
local calls = tonumber(redis.call('hget', KEYS[1], 'calls') or '0')
if audio + tonumber(ARGV[1]) > tonumber(ARGV[2]) or calls >= tonumber(ARGV[3]) then return 0 end
redis.call('hincrby', KEYS[1], 'audio_ms', ARGV[1])
redis.call('hincrby', KEYS[1], 'calls', 1)
redis.call('expire', KEYS[1], 7200)
return 1
"""


def _reserve_budget(seconds):
    """Charge every attempt before embeddings/GPU work; retries never bypass it."""
    try:
        hours = float(os.getenv('TRANSCRIPTION_SYNC_FINAL_PASS_HOURLY_AUDIO_HOURS', '10'))
        calls = int(os.getenv('TRANSCRIPTION_SYNC_FINAL_PASS_HOURLY_REQUESTS', '1000'))
        if not math.isfinite(hours) or hours <= 0 or calls <= 0:
            return False
        hour = datetime.now(timezone.utc).strftime('%Y%m%d%H')
        # One bounded client per reservation; close it even after socket timeout.
        with create_bounded_redis_client(0.5) as client:
            return (
                client.eval(
                    _RESERVE_SCRIPT,
                    1,
                    f'transcription-sync-final-pass:budget:{hour}',
                    max(1, math.ceil(seconds * 1000)),
                    math.floor(hours * 3600 * 1000),
                    calls,
                )
                == 1
            )
    except Exception:
        # Infrastructure failure must retain legacy attribution, not remove the cap.
        return False


def _skipped_budget():
    OUTCOMES.labels(outcome='skipped_budget').inc()
    record_fallback(
        component='stt_selection',
        from_mode='sync_final_pass',
        to_mode='legacy_speaker_matching',
        reason='other',
        outcome='degraded',
    )
    return None, {'outcome': 'skipped_budget'}


def run_sync_final_pass(uid, audio, words, segments, cache, *, scope, owner_reserved):
    if not _slots.acquire(blocking=False):
        return _skipped_budget()
    try:
        return _run_sync_final_pass(uid, audio, words, segments, cache, scope=scope, owner_reserved=owner_reserved)
    finally:
        _slots.release()


def _run_sync_final_pass(uid, audio, words, segments, cache, *, scope, owner_reserved):
    """Reuse the one matching/storage WAV download; do not fetch another URL."""
    try:
        waveform = AudioSegment.from_wav(io.BytesIO(audio)).set_channels(1).set_frame_rate(16000).set_sample_width(2)
        if len(waveform) > 7200 * 1000:
            raise ValueError('audio too long')
        if not _reserve_budget(len(waveform) / 1000):
            return _skipped_budget()
        first_word = round(float(words[0]['timestamp'][0]), 2) if words else 0
        evidence_segments = [s.model_copy(deep=True) for s in segments]
        for segment in evidence_segments:
            segment.start += first_word
            segment.end += first_word
        vectors = {}
        # Bound triage's embedding calls. Incomplete coverage fails open to full
        # diarization, never to a guessed single-speaker result.
        if speaker_embedding_configured():
            for segment in sorted(evidence_segments, key=lambda s: s.end - s.start, reverse=True)[:32]:
                evidence = collect_speaker_audio(audio, [(segment.start, segment.end)])
                if evidence.clips and segment.id:
                    vectors[segment.id] = extract_embedding_from_bytes(evidence.clips[0][0])
        resolution = (
            resolve_conversation_speakers(evidence_segments, vectors, manual_speakers={}, voiceprints={})
            if vectors
            else None
        )
        passed, outcome = run_final_pass(
            waveform.raw_data,
            words,
            resolution,
            cache,
            deadline=time.monotonic() + 600,
            conversation_id=scope,
            segments=evidence_segments,
            vectors=vectors,
            owner_reserved=owner_reserved,
        )
        # The diarizer sees absolute WAV clocks. Persist the legacy sync clock,
        # whose origin is the first ASR word (also used for upload end time).
        for segment in passed or []:
            segment.start = round(round(segment.start, 2) - first_word, 2)
            segment.end = round(round(segment.end, 2) - first_word, 2)
        return passed, outcome
    except Exception as exc:
        logger.warning('Sync final pass failed exception_type=%s', type(exc).__name__)
        OUTCOMES.labels(outcome='failed:sync_audio').inc()
        record_fallback(
            component='stt_selection',
            from_mode='sync_final_pass',
            to_mode='legacy_speaker_matching',
            reason='other',
            outcome='degraded',
        )
        return None, {'outcome': 'failed:sync_audio'}
