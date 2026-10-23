"""Self-hosted spoken-language gate (Parakeet `/v2/language`) for prerecorded routing.

Shadow: runs beside the vendor probe and records agreement; routing is unchanged.
Enforced (cohort under STT_PRERECORDED_LANGUAGE_GATE_PERCENT): replaces the vendor
probe. The gate never sees recognizer text. Any gate failure returns None and the
caller keeps the vendor path, so an unavailable gate can only cost money.
"""

from dataclasses import dataclass
import hashlib
import logging
import math
import os

import httpx
from prometheus_client import Counter

from config.prerecorded_language import language_class, language_gate_percent, self_lid_confidence_floor

logger = logging.getLogger(__name__)

GATE_TIMEOUT = httpx.Timeout(6, connect=2)
_BUCKETS = frozenset({'en', 'ja', 'zh', 'ko', 'vi', 'hi', 'ar', 'th'})

SELF_REQUESTS = Counter('omi_stt_language_gate_self_total', 'Self-hosted language gate calls', ['surface', 'outcome'])
SHADOW = Counter(
    'omi_stt_language_gate_shadow_total',
    'Self gate vs vendor probe on the same prerecorded audio (routing unchanged)',
    ['surface', 'self_route', 'vendor_route', 'self_bucket', 'vendor_bucket', 'vendor_conf', 'dur_bucket'],
)
ENFORCED = Counter(
    'omi_stt_language_gate_enforced_total',
    'Prerecorded routes decided by the self gate; vendor_fallback = gate unavailable, vendor probe used',
    ['surface', 'route', 'bucket'],
)


@dataclass(frozen=True)
class SelfVerdict:
    language: str
    language_probability: float
    p_supported: float
    audio_seconds: float

    @property
    def parakeet(self) -> bool:
        """Re-derived here, not trusted from the service's `route`: both sides must agree."""
        floor = self_lid_confidence_floor(self.audio_seconds)
        return floor is not None and self.p_supported >= floor and language_class(self.language) == 'supported'


def language_bucket(code: str | None) -> str:
    code = (code or '').split('-')[0].lower()
    if code in _BUCKETS:
        return code
    if code in {'', 'und', 'multi', 'unknown'}:
        return 'und'
    return 'other_p25' if language_class(code) == 'supported' else 'other'


def _duration_bucket(seconds: float | None) -> str:
    if not isinstance(seconds, (int, float)) or not math.isfinite(seconds):
        return 'unknown'
    if seconds < 3:
        return 'lt3'
    if seconds < 6:
        return '3to6'
    if seconds < 10:
        return '6to10'
    return 'ge10'


def _probability(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value) if 0 <= value <= 1 else None


def self_detect(probe: bytes, *, surface: str) -> SelfVerdict | None:
    """One bounded call; no retries. `probe` is a WAV of at most 30 s."""
    outcome = 'error'
    try:
        base = os.getenv('HOSTED_PARAKEET_API_URL', '').rstrip('/')
        if not base:
            outcome = 'no_url'
            return None
        with httpx.Client(timeout=GATE_TIMEOUT) as client:
            response = client.post(base + '/v2/language', files={'file': ('language.wav', probe, 'audio/wav')})
        if response.status_code != 200:
            outcome = 'unavailable' if response.status_code == 503 else f'http_{response.status_code // 100}xx'
            return None
        data = response.json()
        language = data.get('language') if isinstance(data, dict) else None
        p_supported = _probability(data.get('p_supported')) if isinstance(data, dict) else None
        top_p = _probability(data.get('language_probability')) if isinstance(data, dict) else None
        seconds = data.get('audio_seconds') if isinstance(data, dict) else None
        if (
            not isinstance(language, str)
            or not 2 <= len(language) <= 8
            or not language.isascii()
            or p_supported is None
            or top_p is None
            or isinstance(seconds, bool)
            or not isinstance(seconds, (int, float))
            or not math.isfinite(seconds)
            or seconds < 0
        ):
            outcome = 'invalid_response'
            return None
        outcome = 'accepted'
        return SelfVerdict(language.lower(), top_p, p_supported, float(seconds))
    except httpx.TimeoutException:
        outcome = 'timeout'
        return None
    except Exception:
        return None
    finally:
        try:
            SELF_REQUESTS.labels(surface, outcome).inc()
        except Exception:
            pass


def enforced_for(cohort_key: str | bytes | None, probe: bytes) -> bool:
    """Stable cohort: the caller's key (uid) when supplied, else the audio itself."""
    percent = language_gate_percent()
    if percent <= 0:
        return False
    if percent >= 100:
        return True
    key = cohort_key if cohort_key is not None else probe
    digest = hashlib.sha256(key.encode() if isinstance(key, str) else key).digest()
    return int.from_bytes(digest[:8], 'big') % 100 < percent


def record_shadow(surface: str, verdict: SelfVerdict | None, vendor) -> None:
    """`vendor` is the batch_language.LanguageDecision the route actually used."""
    try:
        vendor_route = (
            'unavailable'
            if vendor.evidence == 'unavailable'
            else 'parakeet' if vendor.parakeet_safe else 'multilingual'
        )
        self_route = 'unavailable' if verdict is None else 'parakeet' if verdict.parakeet else 'multilingual'
        vendor_bucket = language_bucket(vendor.language)
        vendor_conf = 'ge90' if vendor.confidence >= 0.9 else 'lt90'
        seconds = verdict.audio_seconds if verdict is not None else vendor.probe_seconds
        SHADOW.labels(
            surface,
            self_route,
            vendor_route,
            language_bucket(verdict.language) if verdict is not None else 'und',
            vendor_bucket,
            vendor_conf,
            _duration_bucket(seconds),
        ).inc()
        if verdict is not None and self_route == 'parakeet' and vendor_bucket not in {'en', 'other_p25', 'und'}:
            # The dangerous direction: bounded codes and scores only, for bucket review.
            logger.warning(
                'event=language_gate_shadow_disagreement surface=%s self_language=%s p_supported=%.4f '
                'vendor_language=%s vendor_confidence=%.3f audio_seconds=%.1f',
                surface,
                language_bucket(verdict.language),
                verdict.p_supported,
                vendor_bucket,
                vendor.confidence,
                verdict.audio_seconds,
            )
    except Exception:
        pass


def record_enforced(surface: str, verdict: SelfVerdict | None) -> None:
    try:
        if verdict is None:
            ENFORCED.labels(surface, 'vendor_fallback', 'und').inc()
        else:
            route = 'parakeet' if verdict.parakeet else 'multilingual'
            ENFORCED.labels(surface, route, language_bucket(verdict.language)).inc()
    except Exception:
        pass
