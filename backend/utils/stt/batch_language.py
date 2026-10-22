"""Independent, bounded audio LID before unknown-language Parakeet selection.

API contract: https://docs.modulate.ai/api-reference/language-detection/batch
No recognizer text participates in the decision. Errors/uncertainty stay multilingual.
"""

from dataclasses import dataclass
from io import BytesIO
import math
import os
import wave

import httpx
from prometheus_client import Counter

from config.prerecorded_language import (
    MIN_AUDIO_LID_CONFIDENCE,
    audio_lid_confidence_floor,
    language_class,
    language_gate_shadow_enabled,
    language_guard_enabled,
    self_lid_confidence_floor,
)
from config.stt_provider_policy import MODULATE_SUPPORTED_LANGUAGES, normalized_stt_language
from utils.stt import language_gate

MAX_PROBE_SECONDS = 30
MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024
MIN_CONFIDENCE = MIN_AUDIO_LID_CONFIDENCE
LID_URL = 'https://platform.modulate.ai/api/velma-2-language-detection-batch'
DETECTIONS = Counter(
    'omi_batch_pipeline_language_detection_total', 'Independent audio LID routing', ['detected_language', 'decision']
)
PROBE_SECONDS = Counter(
    'omi_batch_pipeline_language_probe_audio_seconds_total', 'Bounded paid audio LID samples', ['outcome']
)


@dataclass(frozen=True)
class LanguageDecision:
    language: str
    confidence: float
    evidence: str
    probe_seconds: float | None = None

    @property
    def parakeet_safe(self):
        if self.evidence == 'self_lid':
            # confidence is P(supported) over the Parakeet-25 set, not a top-1 score.
            floor = self_lid_confidence_floor(self.probe_seconds)
            return floor is not None and language_class(self.language) == 'supported' and floor <= self.confidence <= 1
        minimum = audio_lid_confidence_floor(self.probe_seconds) if self.evidence == 'audio_lid' else MIN_CONFIDENCE
        return language_class(self.language) == 'supported' and minimum <= self.confidence <= 1


def probe_wav(audio: bytes, *, sample_rate=16000, channels=1, encoding=None) -> tuple[bytes, float]:
    """At most 30 seconds leave this process, even for multi-hour recordings."""
    if encoding:
        if encoding not in {'linear16', 'pcm16', 'pcm_s16le'}:
            raise ValueError('unsupported probe encoding')
        if not 8000 <= sample_rate <= 48000 or channels not in (1, 2):
            raise ValueError('invalid probe format')
        frames = audio[: MAX_PROBE_SECONDS * sample_rate * channels * 2]
        rate, width, channel_count = sample_rate, 2, channels
    else:
        with wave.open(BytesIO(audio), 'rb') as source:
            rate, width, channel_count = source.getframerate(), source.getsampwidth(), source.getnchannels()
            if not 8000 <= rate <= 48000 or width != 2 or channel_count not in (1, 2):
                raise ValueError('invalid probe format')
            frames = source.readframes(MAX_PROBE_SECONDS * rate)
    if rate <= 0 or width != 2 or channel_count not in (1, 2) or not frames:
        raise ValueError('invalid probe audio')
    duration = len(frames) / (rate * width * channel_count)
    output = BytesIO()
    with wave.open(output, 'wb') as target:
        target.setparams((channel_count, width, rate, 0, 'NONE', 'not compressed'))
        target.writeframes(frames)
    return output.getvalue(), duration


def detect(audio: bytes, *, before_probe=None, **audio_options) -> LanguageDecision:
    """One cheap classification request; no client retries or content logging."""
    outcome, seconds, sent = 'error', 0.0, False
    decision = LanguageDecision('und', 0.0, 'unavailable')
    try:
        body, seconds = probe_wav(audio, **audio_options)
        key = os.getenv('MODULATE_API_KEY', '')
        if not key or before_probe is not None and not before_probe():
            return decision
        with httpx.Client(timeout=httpx.Timeout(8, connect=2)) as client:
            sent = True
            response = client.post(
                LID_URL, headers={'X-API-Key': key}, files={'upload_file': ('language.wav', body, 'audio/wav')}
            )
        response.raise_for_status()
        outcome = 'accepted'
        data = response.json()
        code = data.get('predicted_language_code')
        confidence = data.get('confidence')
        if (
            not isinstance(code, str)
            or len(code) != 2
            or not code.isascii()
            or not code.isalpha()
            or isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            return decision
        decision = LanguageDecision(code.lower(), float(confidence), 'audio_lid', seconds)
        return decision
    except Exception:
        return decision
    finally:
        if seconds and sent:
            try:
                PROBE_SECONDS.labels(outcome).inc(seconds)
            except Exception:
                pass


def _self_gate(audio: bytes, surface: str, cohort_key, audio_options) -> tuple[bool, language_gate.SelfVerdict | None]:
    """(enforced, verdict). Batch intake is shadow-only until its GPU worker accepts self_lid evidence."""
    try:
        probe, _ = probe_wav(audio, **audio_options)
    except Exception:
        return False, None
    enforced = surface != 'batch' and language_gate.enforced_for(cohort_key, probe)
    if not enforced and not language_gate_shadow_enabled():
        return False, None
    return enforced, language_gate.self_detect(probe, surface=surface)


def _self_decision(verdict: language_gate.SelfVerdict) -> LanguageDecision:
    return LanguageDecision(verdict.language, verdict.p_supported, 'self_lid', verdict.audio_seconds)


def resolve_language(
    language, audio: bytes, *, before_probe=None, surface='prerecorded', cohort_key=None, **audio_options
) -> LanguageDecision:
    code = normalized_stt_language(language.strip() if isinstance(language, str) else None)
    if not language_guard_enabled() or language_class(language) != 'unknown':
        return LanguageDecision(code, 1.0, 'declared')
    enforced, verdict = _self_gate(audio, surface, cohort_key, audio_options)
    if enforced:
        language_gate.record_enforced(surface, verdict)
    if enforced and verdict is not None:
        decision = _self_decision(verdict)
    else:
        # Gate unavailable in an enforced cohort falls back to today's vendor path.
        decision = detect(audio, before_probe=before_probe, **audio_options)
        if not enforced:
            language_gate.record_shadow(surface, verdict, decision)
    bounded = decision.language if decision.language in MODULATE_SUPPORTED_LANGUAGES else 'other'
    if decision.language == 'und':
        bounded = 'und'
    try:
        DETECTIONS.labels(bounded, 'parakeet' if decision.parakeet_safe else 'multilingual').inc()
        if not decision.parakeet_safe:
            from utils.observability.fallback import record_fallback

            record_fallback(
                component='stt_selection', from_mode='parakeet', to_mode='modulate', reason='other', outcome='degraded'
            )
    except Exception:
        pass
    return decision


def select_decision(language, decision, selector):
    resolved = decision.language if decision.parakeet_safe else language
    selected = selector(resolved)
    from utils.batch_pipeline.language_metrics import record_route

    record_route('prerecorded', decision.language, 'parakeet' if selected[0] == 'parakeet' else 'multilingual')
    return selected


def resolve_file(language, path, *, selector, before_probe=None, cohort_key=None):
    """Return the final provider before a sync segment's dispatch/accounting."""
    if not language_guard_enabled() or language_class(language) != 'unknown':
        return selector(language)
    try:
        with wave.open(str(path), 'rb') as source:
            body, _ = probe_wav_from_reader(source)
        decision = resolve_language(language, body, before_probe=before_probe, cohort_key=cohort_key)
    except Exception:
        decision = LanguageDecision('und', 0.0, 'unavailable')
    return select_decision(language, decision, selector)


def probe_wav_from_reader(source):
    output = BytesIO()
    with wave.open(output, 'wb') as target:
        target.setparams(source.getparams())
        target.writeframes(source.readframes(MAX_PROBE_SECONDS * source.getframerate()))
    return output.getvalue(), 0


def resolve_url(language, url, *, selector):
    if not language_guard_enabled() or language_class(language) != 'unknown':
        return selector(language)
    try:
        chunks, size = [], 0
        with httpx.Client(timeout=httpx.Timeout(10, connect=2)) as client:
            with client.stream('GET', url) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes(chunk_size=65536):
                    remaining = MAX_DOWNLOAD_BYTES - size
                    chunks.append(chunk[:remaining])
                    size += min(len(chunk), remaining)
                    if size >= MAX_DOWNLOAD_BYTES:
                        break
        decision = resolve_language(language, b''.join(chunks))
    except Exception:
        decision = LanguageDecision('und', 0.0, 'unavailable')
    return select_decision(language, decision, selector)
