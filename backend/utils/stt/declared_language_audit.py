"""How much declared-supported batch audio is really in a language Parakeet cannot transcribe (routing unchanged).

Serving batch intake trusts a named supported language (a conversation pin, or a single-language preference) and sends
the unit on without listening to it (``batch_language.resolve_language`` returns ``declared``). A pin is often the app
language, so some of that audio is Mandarin, Hindi or another language Parakeet renders as Latin phonetics. Nothing
measured how much.

This audit samples ``SAMPLE_PERCENT`` of those units by a stable hash of their audio. In the background it:

1. re-runs serving's privacy authorization and consent check for that unit, then a read-only funding check (no
   subscription provisioning, no held-audio or admission-decision telemetry). The serving guard is never touched, so a
   denial only skips the sample and never refuses or changes the upload. Owners without an Omi-funded allowance,
   including BYOK-only owners, are skipped (``not_funded``): the classifier is an Omi-paid vendor or GPU;
2. cuts the first 30 s, and skips it when it holds under ``MIN_SPEECH_SECONDS`` of voiced audio (leading silence);
3. classifies it with the self-hosted language gate when one is configured, otherwise with the existing Modulate
   language-ID endpoint (the vendor that already serves live STT) through ``batch_language.audit_detect``, which never
   touches the routing probe's circuit breaker, provider health or probe counters. Either classifier runs at most
   ``MAX_PROBES_PER_HOUR`` times per process;
4. counts ``omi_batch_pipeline_declared_language_audit_total{declared, heard, heard_class, confident, classifier}``.

It never changes a route, stores nothing, and records no user identifier or transcript. Shadow intake (its own guard
class) is not audited, and neither is a unit whose owner brought their own STT (BYOK or a custom provider): their
audio is never sent to an Omi-paid classifier for measurement. A unit admitted to a vendor STT route is skipped too
(``provider_routed``): it never reaches Parakeet, so it is not part of the leak.

``BATCH_DECLARED_LANGUAGE_AUDIT_ENABLED=false`` stops sampling.
"""

import contextvars
import hashlib
import io
import logging
import os
import threading
import time
import wave
from typing import Callable

import numpy as np
from prometheus_client import Counter

from config.live_stt_gpu_fleet import gpu_fleet_off
from config.prerecorded_language import language_class
from config.refactor_switches import default_on
from utils import funded_processing, stt_cap_dispatch
from utils.batch_pipeline.language_probe_authorization import ServingLanguageProbeGuard
from utils.executors import ExecutorSaturatedError, declared_language_audit_executor
from utils.stt import language_gate
from utils.stt.prerecorded_deadline import verification_deadline

logger = logging.getLogger(__name__)

SAMPLE_PERCENT = 2.0
CONFIDENT = 0.8  # top-1 probability for a verdict to count as confident
MIN_SPEECH_SECONDS = 3.0  # voiced audio needed in the 30 s probe; less is leading silence, not a language sample
_VOICED_RMS = 300  # int16 RMS of a voiced 20 ms frame
MAX_PROBES_PER_HOUR = 60  # classifications per process per hour (30 s each: vendor at most $0.005/h/process)

AUDIT = Counter(
    'omi_batch_pipeline_declared_language_audit_total',
    'Sampled declared-supported batch units classified by audio language ID (routing unchanged)',
    ['declared', 'heard', 'heard_class', 'confident', 'classifier'],
)
SKIPPED = Counter(
    'omi_batch_pipeline_declared_language_audit_skipped_total',
    'Declared-language audit samples dropped before classification',
    ['reason'],
)

_probe_lock = threading.Lock()
_probe_window = [0.0, 0]  # [hour start, probes in it]


def audit_enabled() -> bool:
    """Ship-on; only literal false stops sampling."""
    return default_on(
        'BATCH_DECLARED_LANGUAGE_AUDIT_ENABLED',
        os.getenv('BATCH_DECLARED_LANGUAGE_AUDIT_ENABLED', 'true').strip().lower() != 'false',
    )


_FINGERPRINT_BLOCKS = 16
_FINGERPRINT_BLOCK = 4096


def sampled(audio: bytes) -> bool:
    """A stable 2% decision from a bounded fingerprint (length plus 16 blocks spread across the whole unit).

    It runs inline on every declared unit, so it reads at most 64 KiB; spreading the blocks keeps equal-length units
    that open with the same silence from sharing a decision.
    """
    span = max(0, len(audio) - _FINGERPRINT_BLOCK)
    hasher = hashlib.blake2b(len(audio).to_bytes(8, 'big'), digest_size=8)
    for index in range(_FINGERPRINT_BLOCKS):
        start = span * index // (_FINGERPRINT_BLOCKS - 1)
        hasher.update(audio[start : start + _FINGERPRINT_BLOCK])
    digest = hasher.digest()
    return int.from_bytes(digest[:4], 'big') % 10000 < SAMPLE_PERCENT * 100


def maybe_audit(
    declared: str,
    audio: bytes,
    *,
    cut: Callable[[bytes], tuple[bytes, float]],
    guard,
    vendor: Callable[[bytes], object],
) -> None:
    """Queue one sampled audit of a declared-supported serving unit. Never raises, never blocks.

    ``cut`` is ``batch_language.probe_wav`` and ``vendor`` its ``audit_detect`` (passed in: that module imports this
    one). Inline work is the bounded sampling fingerprint and the submission; the cut and everything after run on the
    audit pool.
    ``guard`` is serving intake's ``ServingLanguageProbeGuard``; any other caller (shadow intake) is not audited.
    """
    try:
        if not audio or not audit_enabled() or not sampled(audio):
            return
        if not isinstance(guard, ServingLanguageProbeGuard):
            return
        if guard.custom_stt:
            SKIPPED.labels('custom_stt').inc()
            return
        if guard.provider_routed:
            SKIPPED.labels('provider_routed').inc()  # a vendor transcribes it; no Parakeet leak to measure
            return
        access = (guard.store, guard.item, guard.authorize)
        context = contextvars.copy_context()
        # A fire-and-forget probe must not inherit the caller's request deadline.
        context.run(verification_deadline.set, None)
        try:
            declared_language_audit_executor.submit(context.run, _classify, declared, audio, cut, access, vendor)
        except ExecutorSaturatedError:
            SKIPPED.labels('busy').inc()
        except Exception as error:
            SKIPPED.labels('submit').inc()
            logger.warning('event=declared_language_audit outcome=submit_failed error=%s', type(error).__name__)
    except Exception as error:
        SKIPPED.labels('error').inc()
        logger.warning('event=declared_language_audit outcome=error error=%s', type(error).__name__)


def voiced_seconds(probe: bytes) -> float:
    """Seconds of 20 ms frames above a voicing RMS in a 16-bit PCM WAV probe, at the probe's own rate."""
    with wave.open(io.BytesIO(probe), 'rb') as reader:
        if reader.getsampwidth() != 2:
            return 0.0
        rate, channels = reader.getframerate(), reader.getnchannels()
        pcm = np.frombuffer(reader.readframes(reader.getnframes()), dtype='<i2').astype(np.float64)
    if channels > 1:
        pcm = pcm[: len(pcm) // channels * channels].reshape(-1, channels).mean(axis=1)
    size = max(1, rate // 50)  # 20 ms
    frames = len(pcm) // size
    if frames == 0:
        return 0.0
    rms = np.sqrt((pcm[: frames * size].reshape(frames, size) ** 2).mean(axis=1))
    return float((rms >= _VOICED_RMS).sum()) * 0.02


def _self_gate_configured() -> bool:
    return bool(os.getenv('HOSTED_LID_API_URL', '').strip()) or (
        not gpu_fleet_off() and bool(os.getenv('HOSTED_PARAKEET_API_URL', '').strip())
    )


def _probe_allowed() -> bool:
    with _probe_lock:
        now = time.monotonic()
        if now - _probe_window[0] >= 3600:
            _probe_window[0], _probe_window[1] = now, 0
        if _probe_window[1] >= MAX_PROBES_PER_HOUR:
            return False
        _probe_window[1] += 1
        return True


def _authorization(access) -> str | None:
    """None when the sample may be classified, else the skip reason. Never records admission telemetry."""
    store, item, authorize = access
    try:
        authorize(store, item, snapshots=None)  # serving's privacy authorization; raises when blocked
        if not funded_processing.consent_allows(item.owner_id):
            return 'not_authorized'
    except Exception:
        return 'not_authorized'
    try:
        # ready_usage_only: no subscription provisioning. sync_admission would also record held audio and a decision.
        if not stt_cap_dispatch.funded_allowance(item.owner_id, lane='batch', ready_usage_only=True).managed:
            return 'not_funded'
    except Exception:
        return 'not_funded'
    return None


def _classify(declared: str, audio: bytes, cut, access, vendor) -> None:
    try:
        try:
            probe, seconds = cut(audio)  # only the first 30 s is kept, never the whole unit
        except Exception:
            SKIPPED.labels('decode').inc()
            return
        # Local checks first: a silent probe needs no authorization reads.
        if voiced_seconds(probe) < MIN_SPEECH_SECONDS:
            SKIPPED.labels('no_speech').inc()
            return
        skip = _authorization(access)
        if skip is not None:
            SKIPPED.labels(skip).inc()
            return
        if not _probe_allowed():
            SKIPPED.labels('probe_cap').inc()
            return
        bucket = language_gate.language_bucket(declared)
        if _self_gate_configured():
            verdict = language_gate.self_detect(probe, surface='batch_audit')
            if verdict is None:
                SKIPPED.labels('self_unavailable').inc()
                return
            if abs(verdict.audio_seconds - seconds) > 0.1:
                SKIPPED.labels('duration_mismatch').inc()  # the reply must describe the bytes we sent
                return
            heard, probability, classifier = verdict.language, verdict.language_probability, 'self'
        else:
            decision = vendor(probe)
            if getattr(decision, 'evidence', None) != 'audio_lid':
                SKIPPED.labels('vendor_unavailable').inc()
                return
            heard, probability, classifier = decision.language, decision.confidence, 'vendor'
        AUDIT.labels(
            bucket,
            language_gate.language_bucket(heard),
            language_class(heard),
            'true' if probability >= CONFIDENT else 'false',
            classifier,
        ).inc()
    except Exception as error:
        SKIPPED.labels('error').inc()
        logger.warning('event=declared_language_audit outcome=classify_failed error=%s', type(error).__name__)
