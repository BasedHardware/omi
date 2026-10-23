"""Low-cardinality shadow counters; owner concentration lives in hashed records/logs."""

import logging

from prometheus_client import Counter

logger = logging.getLogger(__name__)
OUTCOMES = frozenset({'recovered', 'empty', 'failed_held', 'error', 'dropped', 'paid_skipped'})
OUTCOME = Counter('omi_batch_shadow_outcome_total', 'Terminal shadow units', ['outcome', 'class'])
SPEECH = Counter('omi_batch_shadow_speech_seconds_total', 'Original VAD speech in shadow units', ['vad', 'class'])
LOSS = Counter('omi_batch_shadow_speech_loss_seconds_total', 'VAD speech without recovered words', ['vad', 'class'])
GPU = Counter('omi_batch_shadow_gpu_seconds_total', 'Shadow GPU chain wall seconds')
PAID = Counter('omi_batch_shadow_paid_calls_total', 'Reserved shadow recovery calls', ['provider'])
PAID_AUDIO = Counter('omi_batch_shadow_paid_audio_seconds_total', 'Reserved recovery audio', ['provider'])
COLLECTORS = (OUTCOME, SPEECH, LOSS, GPU, PAID, PAID_AUDIO)


def record(row):
    try:
        OUTCOME.labels(row['outcome'], row['class']).inc()
        if row.get('vad') in {'worker', 'strict'}:
            SPEECH.labels(row['vad'], row['class']).inc(row['speech_seconds'])
            LOSS.labels(row['vad'], row['class']).inc(row['speech_loss_seconds'])
        logger.info(
            'event=batch_shadow_outcome owner_hash=%s outcome=%s class=%s vad=%s speech_seconds=%.3f speech_loss_seconds=%.3f',
            row['owner_key'],
            row['outcome'],
            row['class'],
            row.get('vad', 'unknown'),
            row.get('speech_seconds', 0),
            row.get('speech_loss_seconds', 0),
        )
    except Exception:
        pass
