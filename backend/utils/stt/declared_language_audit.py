"""How much declared-supported batch audio is really in a language Parakeet cannot transcribe (routing unchanged).

Batch intake trusts a named supported language (a conversation pin, or a single-language preference) and sends the
unit to Parakeet without listening to it (``batch_language.resolve_language`` returns ``declared``). A pin is often the
app language, so some of that audio is Mandarin, Hindi or another language Parakeet renders as Latin phonetics. Nothing
measured how much.

This audit samples ``SAMPLE_PERCENT`` of those units by a stable hash of their audio and asks the self-hosted language
gate (Parakeet's own ``/v2/language``, the same GPU service that transcribes the unit) about the first 30 s. It records
``omi_batch_pipeline_declared_language_audit_total{declared, heard, heard_class, confident}`` and never changes a
route. It runs on a small background pool off the intake path; a full pool skips the sample.

The audio goes only to our own Parakeet service, which receives the same unit for ASR moments later; no vendor is
called, nothing is stored, and no user identifier or transcript is recorded.

``BATCH_DECLARED_LANGUAGE_AUDIT_ENABLED=false`` stops sampling.
"""

import hashlib
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from prometheus_client import Counter

from config.prerecorded_language import language_class
from config.refactor_switches import default_on
from utils.stt import language_gate

logger = logging.getLogger(__name__)

SAMPLE_PERCENT = 2.0
MAX_PENDING = 4  # probes (at most 30 s of audio each) waiting for the gate at once
CONFIDENT = 0.8  # top-1 probability for heard=<language> to count as confident

AUDIT = Counter(
    'omi_batch_pipeline_declared_language_audit_total',
    'Sampled declared-supported batch units classified by the self-hosted language gate (routing unchanged)',
    ['declared', 'heard', 'heard_class', 'confident'],
)
SKIPPED = Counter(
    'omi_batch_pipeline_declared_language_audit_skipped_total',
    'Declared-language audit samples dropped before classification',
    ['reason'],
)

_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='declared-language-audit')
_PENDING = threading.BoundedSemaphore(MAX_PENDING)


def audit_enabled() -> bool:
    """Ship-on; only literal false stops sampling."""
    return default_on(
        'BATCH_DECLARED_LANGUAGE_AUDIT_ENABLED',
        os.getenv('BATCH_DECLARED_LANGUAGE_AUDIT_ENABLED', 'true').strip().lower() != 'false',
    )


def sampled(audio: bytes) -> bool:
    digest = hashlib.sha256(audio[:65536]).digest()
    return int.from_bytes(digest[:4], 'big') % 10000 < SAMPLE_PERCENT * 100


def maybe_audit(declared: str, audio: bytes, *, cut: Callable[[bytes], tuple[bytes, float]]) -> None:
    """Queue one sampled audit of a declared-supported unit. Never raises, never blocks.

    ``cut`` is ``batch_language.probe_wav`` (passed in: that module imports this one)."""
    try:
        if not audio or not audit_enabled() or not sampled(audio):
            return
        if not _PENDING.acquire(blocking=False):
            SKIPPED.labels('busy').inc()
            return
        try:
            probe, _seconds = cut(audio)  # only the first 30 s is kept, never the whole unit
            _POOL.submit(_classify, declared, probe)
        except Exception:
            _PENDING.release()
            SKIPPED.labels('decode_or_submit').inc()
    except Exception:
        pass


def _classify(declared: str, probe: bytes) -> None:
    try:
        verdict = language_gate.self_detect(probe, surface='batch_audit')
        if verdict is None:
            AUDIT.labels(language_gate.language_bucket(declared), 'unavailable', 'unavailable', 'false').inc()
            return
        AUDIT.labels(
            language_gate.language_bucket(declared),
            language_gate.language_bucket(verdict.language),
            language_class(verdict.language),
            'true' if verdict.language_probability >= CONFIDENT else 'false',
        ).inc()
    except Exception:
        SKIPPED.labels('error').inc()
    finally:
        _PENDING.release()
