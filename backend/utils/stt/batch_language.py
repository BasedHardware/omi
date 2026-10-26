"""Independent, bounded audio LID before unknown-language Parakeet selection.

API contract: https://docs.modulate.ai/api-reference/language-detection/batch
No recognizer text participates in the decision. Errors/uncertainty stay multilingual.
"""

from dataclasses import dataclass, replace
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
from utils.stt.prerecorded_health import CREDIT_AUTH, PROVIDER_ERROR, note_provider_failure
from utils.stt.vendor_guard import (
    ENDPOINT_LID,
    breaker_allows,
    is_quota_error,
    record_breaker_other_failure,
    record_breaker_quota_error,
    record_breaker_success,
    record_vendor_burn,
)

MAX_PROBE_SECONDS = 30
MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024
MIN_CONFIDENCE = MIN_AUDIO_LID_CONFIDENCE
LID_URL = 'https://platform.modulate.ai/api/velma-2-language-detection-batch'


def _finite_number(value) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


DETECTIONS = Counter(
    'omi_batch_pipeline_language_detection_total', 'Independent audio LID routing', ['detected_language', 'decision']
)
PROBE_SECONDS = Counter(
    'omi_batch_pipeline_language_probe_audio_seconds_total', 'Bounded paid audio LID samples', ['outcome']
)
PROBE_OUTCOMES = Counter('omi_batch_pipeline_language_probe_total', 'One outcome per LID probe call', ['outcome'])


@dataclass(frozen=True)
class LanguageDecision:
    language: str
    confidence: float
    evidence: str
    probe_seconds: float | None = None

    @property
    def parakeet_safe(self):
        confidence = self.confidence
        if not _finite_number(confidence) or not 0 <= confidence <= 1:
            return False
        if self.evidence == 'self_lid':
            # confidence is P(supported) over the Parakeet-25 set, not a top-1 score.
            floor = self_lid_confidence_floor(self.probe_seconds)
            return floor is not None and language_class(self.language) == 'supported' and confidence >= floor
        minimum = audio_lid_confidence_floor(self.probe_seconds) if self.evidence == 'audio_lid' else MIN_CONFIDENCE
        return language_class(self.language) == 'supported' and confidence >= minimum


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


def _probe_failure_outcome(exc: BaseException) -> str:
    if is_quota_error(exc):
        return 'quota'
    if isinstance(exc, httpx.TimeoutException):
        return 'timeout'
    if isinstance(exc, httpx.TransportError):
        return 'transport'
    if isinstance(exc, httpx.HTTPStatusError):
        status = getattr(getattr(exc, 'response', None), 'status_code', 0) or 0
        return 'http_5xx' if 500 <= status <= 599 else 'http_4xx'
    return 'error'


def detect(audio: bytes, *, before_probe=None, **audio_options) -> LanguageDecision:
    """One cheap classification request; no client retries or content logging."""
    outcome, seconds, sent = 'error', 0.0, False
    decision = LanguageDecision('und', 0.0, 'unavailable')
    try:
        try:
            body, seconds = probe_wav(audio, **audio_options)
        except ValueError:
            outcome = 'unsupported_format'
            return decision
        key = os.getenv('MODULATE_API_KEY', '')
        if not key:
            outcome = 'no_key'
            return decision
        if before_probe is not None and not before_probe():
            outcome = 'skipped'
            return decision
        if not breaker_allows(ENDPOINT_LID):
            outcome = 'breaker_open'
            return decision
        with httpx.Client(timeout=httpx.Timeout(8, connect=2)) as client:
            sent = True
            response = client.post(
                LID_URL, headers={'X-API-Key': key}, files={'upload_file': ('language.wav', body, 'audio/wav')}
            )
        response.raise_for_status()
        record_breaker_success(ENDPOINT_LID)
        outcome = 'accepted'
        data = response.json()
        code = data.get('predicted_language_code')
        confidence = data.get('confidence')
        if (
            not isinstance(code, str)
            or len(code) != 2
            or not code.isascii()
            or not code.isalpha()
            or not _finite_number(confidence)
            or not 0 <= confidence <= 1
        ):
            outcome = 'invalid_response'
            note_provider_failure('modulate', PROVIDER_ERROR)
            return decision
        decision = LanguageDecision(code.lower(), float(confidence), 'audio_lid', seconds)
        return decision
    except Exception as e:
        outcome = _probe_failure_outcome(e)
        if outcome == 'quota':
            record_breaker_quota_error(ENDPOINT_LID)
        elif sent:
            record_breaker_other_failure(ENDPOINT_LID)
        # Observability only; the routing decision above is unchanged. A failed
        # probe is the degradation the sync empty-success guard needs to see.
        note_provider_failure('modulate', CREDIT_AUTH if outcome == 'quota' else PROVIDER_ERROR)
        return decision
    finally:
        try:
            PROBE_OUTCOMES.labels(outcome).inc()
        except Exception:
            pass
        if seconds and sent:
            try:
                PROBE_SECONDS.labels(outcome).inc(seconds)
            except Exception:
                pass
            record_vendor_burn(ENDPOINT_LID, 'ok' if outcome == 'accepted' else 'error', seconds)


def _self_gate(audio: bytes, surface: str, cohort_key, audio_options) -> tuple[bool, language_gate.SelfVerdict | None]:
    """(enforced, verdict), using the shared percentage cohort on every intake surface."""
    try:
        probe, probe_seconds = probe_wav(audio, **audio_options)
    except Exception:
        return False, None
    enforced = language_gate.enforced_for(cohort_key, probe)
    if not enforced and not language_gate_shadow_enabled():
        return False, None
    verdict = language_gate.self_detect(probe, surface=surface)
    if verdict is not None:
        reported_seconds = verdict.audio_seconds
        # The model service's duration must describe the bounded bytes sent by
        # this process. Use our decoded measurement for the short-clip floor.
        if not _finite_number(reported_seconds) or abs(reported_seconds - probe_seconds) > 0.1:
            verdict = None
        else:
            verdict = replace(verdict, audio_seconds=probe_seconds)
    return enforced, verdict


def _self_decision(verdict: language_gate.SelfVerdict) -> LanguageDecision:
    return LanguageDecision(verdict.language, verdict.p_supported, 'self_lid', verdict.audio_seconds)


def compare_shadow_pair(audio: bytes, *, before_call, surface='batch_shadow') -> bool:
    """Compare identical bounded audio without consulting enforcement or selecting a route.

    Each call needs a fresh privacy/funding check. A caller must already hold a
    durable, at-most-once fleet probe reservation. No recognizer is invoked.
    """
    if not language_gate_shadow_enabled():
        return False
    probe, seconds = probe_wav(audio)
    if not before_call():
        return False
    verdict = language_gate.self_detect(probe, surface=surface)
    if verdict is not None:
        if not _finite_number(verdict.audio_seconds) or abs(verdict.audio_seconds - seconds) > 0.1:
            verdict = None
        else:
            verdict = replace(verdict, audio_seconds=seconds)
    vendor = detect(probe, before_probe=before_call)
    language_gate.record_shadow(surface, verdict, vendor)
    return verdict is not None and vendor.evidence == 'audio_lid' and vendor.confidence >= 0.9


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
