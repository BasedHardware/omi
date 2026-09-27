"""Session-scoped live STT language prior and bounded output observations."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Collection

from config.stt_provider_policy import (
    SONIOX_PROVIDER,
    STTServingSurface,
    normalized_stt_language,
    provider_is_enabled,
    soniox_accepts_language_hint,
)
from langdetect import DetectorFactory, detect_langs
from utils.stt.live_metrics import LANGUAGE_CONSTRAINT, OUTPUT_LANGUAGE_SEGMENTS

logger = logging.getLogger(__name__)
DetectorFactory.seed = 0
MIN_LETTERS = 24
MIN_PROBABILITY = 0.95
MAX_PENDING_DETECTIONS = 32
LIVE_PROVIDERS = frozenset({'soniox', 'modulate', 'deepgram', 'parakeet'})


@dataclass(frozen=True)
class LiveLanguageProfile:
    primary: str
    expected: tuple[str, ...]
    primary_group: str
    arm: str
    multi: bool

    @classmethod
    def create(cls, language: str | None, *, multi: bool, uid: str | None) -> LiveLanguageProfile:
        primary = normalized_stt_language(language)
        if not re.fullmatch(r'[a-z]{2,3}', primary):
            primary = ''
        expected = (primary, 'en') if multi and primary not in ('', 'en') else ((primary,) if primary else ())
        group = 'unknown' if not primary else ('en' if primary == 'en' else 'non_en')
        eligible = multi and group == 'non_en'
        arm = 'hintable' if eligible and hintable_allocation(uid) else ('control' if eligible else 'na')
        return cls(primary, expected, group, arm, multi)


def hintable_allocation(uid: str | None) -> bool:
    if not uid:
        return False
    try:
        percent = min(100.0, max(0.0, float(os.getenv('STT_NON_EN_MULTI_PREFER_HINTABLE_PERCENT', '0'))))
    except ValueError:
        percent = 0.0
    bucket = int.from_bytes(hashlib.sha256(('stt-hintable:' + uid).encode()).digest()[:8], 'big')
    return bucket / 2**64 * 100 < percent


def prefer_hintable_soniox(
    profile: LiveLanguageProfile | None,
    models: Collection[str],
    exclude: Collection[str],
    circuit_ready: Callable[[], bool],
) -> bool:
    """Read-only admission; the actual connect still owns its breaker probe."""
    return bool(
        profile
        and profile.arm == 'hintable'
        and 'soniox' in (model.strip() for model in models)
        and SONIOX_PROVIDER not in exclude
        and provider_is_enabled(SONIOX_PROVIDER, STTServingSurface.STREAMING)
        and os.getenv('SONIOX_API_KEY')
        and circuit_ready()
    )


def soniox_hints(language: str, profile: LiveLanguageProfile | None = None) -> list[str]:
    normalized = normalized_stt_language(language)
    candidates = (
        profile.expected
        if profile
        and profile.multi
        and profile.primary_group == 'non_en'
        and os.getenv('STT_MULTI_LANGUAGE_HINTS', 'true').lower() == 'true'
        else (normalized,) if normalized and normalized != 'multi' else ()
    )
    return [code for code in candidates if soniox_accepts_language_hint(code)]


def connection_constraint(provider: str, language: str, profile: LiveLanguageProfile) -> str:
    if provider == 'soniox':
        return 'hinted' if soniox_hints(language, profile) else 'auto'
    return 'forced' if language and language != 'multi' else 'auto'


def classify_output(
    text: str, profile: LiveLanguageProfile, provider_language: str | None = None
) -> tuple[str, str | None]:
    """Classify one finalized segment; caller runs uncertain detection off-loop."""
    if not profile.expected:
        return 'undetermined', None
    language = normalized_stt_language(provider_language)
    if not re.fullmatch(r'[a-z]{2,3}', language):
        language = ''
    if not language:
        if sum(letter.isalpha() for letter in text) < MIN_LETTERS:
            return 'undetermined', None
        try:
            guesses = detect_langs(text)
        except Exception:
            return 'undetermined', None
        if not guesses or guesses[0].prob < MIN_PROBABILITY:
            return 'undetermined', None
        language = normalized_stt_language(guesses[0].lang)
        if not re.fullmatch(r'[a-z]{2,3}', language):
            return 'undetermined', None
    return ('in_profile' if language in profile.expected else 'out_of_profile'), language


@dataclass
class LiveLanguageObservations:
    profile: LiveLanguageProfile
    providers: set[str] = field(default_factory=set)
    constraints: set[str] = field(default_factory=set)
    counts: Counter[str] = field(default_factory=Counter)
    out_codes: Counter[str] = field(default_factory=Counter)
    pending: set[asyncio.Task[Any]] = field(default_factory=set)

    def connected(self, provider: str, language: str) -> None:
        constraint = connection_constraint(provider, language, self.profile)
        self.providers.add(provider)
        self.constraints.add(constraint)
        LANGUAGE_CONSTRAINT.labels(provider, constraint, self.profile.primary_group, self.profile.arm).inc()

    def _record(self, provider: str, result: tuple[str, str | None]) -> None:
        conformance, code = result
        self.counts[conformance] += 1
        if conformance == 'out_of_profile' and code:
            self.out_codes[code] += 1
        OUTPUT_LANGUAGE_SEGMENTS.labels(provider, self.profile.primary_group, self.profile.arm, conformance).inc()

    def observe(self, segment: dict[str, Any], provider: str, spawn: Any) -> None:
        # Provider metadata is ephemeral; never persist it with transcript text.
        language = segment.pop('_provider_language', None)
        code = normalized_stt_language(language if isinstance(language, str) else None)
        language = code if re.fullmatch(r'[a-z]{2,3}', code) else None
        text = str(segment.get('text') or '')
        if language or not self.profile.expected or sum(c.isalpha() for c in text) < MIN_LETTERS:
            self._record(provider, classify_output(text, self.profile, language))
            return
        if len(self.pending) >= MAX_PENDING_DETECTIONS:
            self._record(provider, ('undetermined', None))
            return

        async def detect() -> None:
            self._record(provider, await asyncio.to_thread(classify_output, text, self.profile))

        task = spawn(detect(), name='stt_language_detect')
        self.pending.add(task)
        task.add_done_callback(self.pending.discard)

    async def summarize(self) -> None:
        if self.pending:
            await asyncio.gather(*tuple(self.pending), return_exceptions=True)
        logger.info(
            'live_stt_language_summary primary=%s expected=%s providers=%s constraint=%s arm=%s '
            'in_profile=%d out_of_profile=%d undetermined=%d top_out_code=%s',
            self.profile.primary or 'unknown',
            ','.join(self.profile.expected),
            ','.join(sorted(self.providers)),
            ','.join(sorted(self.constraints)),
            self.profile.arm,
            self.counts['in_profile'],
            self.counts['out_of_profile'],
            self.counts['undetermined'],
            self.out_codes.most_common(1)[0][0] if self.out_codes else '',
        )


def observe_live_segments(host: Any, segments: list[dict[str, Any]], provider: str) -> None:
    if getattr(host, 'use_custom_stt', False):
        return
    observations = getattr(host, 'language_observations', None)
    if isinstance(observations, LiveLanguageObservations):
        for segment in segments:
            observations.observe(segment, provider if provider in LIVE_PROVIDERS else 'other', host.spawn)


def record_live_connection(host: Any, provider: str) -> None:
    observations = getattr(host, 'language_observations', None)
    if isinstance(observations, LiveLanguageObservations):
        observations.connected(provider if provider in LIVE_PROVIDERS else 'other', host.stt_language)
