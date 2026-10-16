"""Default-off, at-most-once legacy STT dispatch with durable result reconciliation."""

from dataclasses import fields
import io
import logging
import time
import wave

from utils.stt_cap_dispatch import sync_allowed, funded_allowance
from config.stt_cap_dispatch import enabled as cap_enabled
from utils.observability.stt_cap_dispatch import record_audio
from config.batch_pipeline import recovery_owners
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_quarantine_recovery import RecoveryStore, recovery_candidates, cancel_fenced_recovery
from utils.batch_pipeline.contracts import WorkItem, projection_speech_spans

logger = logging.getLogger(__name__)


def transcribe(item, binding, audio):
    """Use the sync client directly, with no whole-upload coordinator or retries."""
    from diarizer.batch_pipeline import validate_words
    from utils.stt.pre_recorded import prerecorded_from_bytes
    from utils.stt.vad import offline_pcm_speech_segments

    with wave.open(io.BytesIO(audio), 'rb') as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 16000):
            raise ValueError('canonical recovery audio required')
        duration = wav.getnframes() / 16000
        if abs(duration - item.duration_seconds) > 0.1:
            raise ValueError('recovery audio duration mismatch')
        pcm = wav.readframes(wav.getnframes())
        if len(pcm) != wav.getnframes() * 2:
            raise ValueError('truncated recovery audio')
    # Keep the authenticated intake manifest in the original artifact only;
    # third-party STT receives canonical audio without ancillary provenance.
    output = io.BytesIO()
    with wave.open(output, 'wb') as clean:
        clean.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        clean.writeframes(pcm)
    spans = [{'start': s['start'], 'end': s['end']} for s in offline_pcm_speech_segments(pcm)]
    if not spans:
        raise ValueError('quarantined recovery requires speech evidence')
    # attempts=2 disables all existing client retry branches. An uncertain call
    # must remain held, never be silently reissued by the recovery dispatcher.
    response = prerecorded_from_bytes(output.getvalue(), language=binding.language, return_language=True, attempts=2)
    if not isinstance(response, tuple):
        raise ValueError('legacy recovery requires language response')
    raw, language = response
    words = validate_words([{**word, 'word': word['text']} for word in raw], duration)
    if not words:
        raise ValueError('empty recovery STT remains held')
    # Preserve legacy speaker labels directly in build_incoming. Exclusive batch
    # diarization turns cannot represent overlapping legacy utterances.
    payload = {
        'audio_seconds': duration,
        'speech_seconds': sum(s['end'] - s['start'] for s in spans),
        'speech_spans': spans,
        'words': words,
        'diarization': {'turns': []},
        'words_provider': 'legacy_sync',
        'language': language,
        'recovery_version': 1,
    }
    projection_speech_spans(payload, duration)
    return payload


class QuarantineRecovery:
    def __init__(self, store, artifacts, *, stt=transcribe, clock=time.time):
        self.store, self.artifacts, self.stt, self.clock = store, artifacts, stt, clock
        self.protocol = RecoveryStore(store)

    def recover(self, segment_id, owner_id):
        if owner_id not in recovery_owners():
            return 'disabled'
        try:
            job = self.protocol.prepare(segment_id, owner_id, self.clock())
            if job is None:
                return 'held'
            item = WorkItem(**{field.name: job[field.name] for field in fields(WorkItem) if field.name in job})
            token = job['recovery']['token']
            if job['recovery_state'] == 'running':
                uri = self.artifacts.find_recovery_result(item, token)
                if uri:
                    return 'reconciled' if self.protocol.settle(segment_id, token, self.clock(), uri) else 'held'
                # Bound the scan dwell without allowing takeover. A very late
                # provider reply is rejected after this terminal transition.
                if self.clock() - job['recovery']['started_at'] > 900:
                    self.protocol.settle(segment_id, token, self.clock())
                return 'held'
            if not sync_allowed(owner_id, item.duration_seconds):
                return 'held'
            audio = self.artifacts.fetch_audio(item)
            # Privacy and the intent token are rechecked after download and
            # immediately before issuing the sole application-level STT call.
            if not sync_allowed(owner_id, item.duration_seconds):
                return 'held'
            if owner_id not in recovery_owners() or not self.protocol.start(segment_id, token, self.clock()):
                return 'held'
            from database.batch_pipeline_projection_protocol import normalized_binding
            from utils.observability.fallback import record_fallback

            record_fallback(
                component='stt_selection', from_mode='batch', to_mode='legacy_sync', reason='other', outcome='degraded'
            )
            try:
                payload = self.stt(item, normalized_binding(job['projection_binding']), audio)
                if cap_enabled():
                    record_audio(
                        'sync',
                        'accepted',
                        'unknown',
                        item.duration_seconds,
                        funded_allowance(owner_id).reason == 'plan_allowance_exhausted',
                    )
            except Exception:
                self.protocol.settle(segment_id, token, self.clock())
                return 'failed_held'
            # Storage/commit failures leave running intact: the deterministic
            # encrypted object can be reconciled without repeating STT.
            try:
                uri = self.artifacts.persist_recovery_result(item, payload, token)
                return 'recovered' if self.protocol.settle(segment_id, token, self.clock(), uri) else 'result_held'
            except BatchPrivacyBlocked:
                raise
            except Exception:
                return 'result_held'
        except BatchPrivacyBlocked:
            cancel_fenced_recovery(self.store, segment_id)
            return 'cancelled'
        except ProjectionBlocked:
            return 'held'

    def sweep(self):
        counts = {}
        for owner_id in recovery_owners():
            for segment_id in recovery_candidates(self.store.client, self.store.namespace, owner_id):
                try:
                    outcome = self.recover(segment_id, owner_id)
                except Exception:
                    outcome = 'held'
                counts[outcome] = counts.get(outcome, 0) + 1
                try:
                    logger.info('event=batch_quarantine_recovery outcome=%s', outcome)
                except Exception:
                    pass
                if outcome in {'recovered', 'failed_held', 'result_held', 'cancelled'}:
                    break  # At most one provider dispatch per owner per sweep.
        return counts
