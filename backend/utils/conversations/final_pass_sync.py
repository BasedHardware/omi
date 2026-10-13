"""Sync/WAL adapter for the shared triage, diarizer and assignment seam."""

import io
import os
import time

from pydub import AudioSegment

from config.transcription_final_pass import enabled_for
from utils.conversations.final_pass_pyannote import run_final_pass, OUTCOMES
from utils.observability.fallback import record_fallback
from utils.stt.conversation_speakers import resolve_conversation_speakers
from utils.stt.speaker_embedding import extract_embedding_from_bytes, speaker_embedding_configured
from utils.stt.sync_speaker_evidence import collect_speaker_audio


def sync_enabled_for(uid):
    return enabled_for(uid) and os.getenv('TRANSCRIPTION_FINAL_PASS_SYNC_ENABLED', 'false').lower() == 'true'


def run_sync_final_pass(uid, audio, words, segments, cache, *, scope, owner_reserved):
    """Reuse the one matching/storage WAV download; do not fetch another URL."""
    try:
        waveform = AudioSegment.from_wav(io.BytesIO(audio)).set_channels(1).set_frame_rate(16000).set_sample_width(2)
        if len(waveform) > 7200 * 1000:
            raise ValueError('audio too long')
        first_word = min((float(w['timestamp'][0]) for w in words), default=0)
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
        return passed, outcome
    except Exception:
        OUTCOMES.labels(outcome='failed:sync_audio').inc()
        record_fallback(
            component='stt_selection',
            from_mode='sync_final_pass',
            to_mode='legacy_speaker_matching',
            reason='other',
            outcome='degraded',
        )
        return None, {'outcome': 'failed:sync_audio'}
