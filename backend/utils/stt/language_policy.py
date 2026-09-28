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
from database.live_language_profile import append_live_language_session
from langdetect import DetectorFactory, detect_langs
from utils.executors import db_executor, run_blocking, start_background_task, sync_executor
from utils.stt.live_metrics import LANGUAGE_CONSTRAINT, OUTPUT_LANGUAGE_SEGMENTS

logger = logging.getLogger(__name__)
MIN_LETTERS = 24
MIN_PROBABILITY = 0.95
MAX_PENDING_DETECTIONS = 32
MAX_DETECTION_CHARS = 512
LIVE_PROVIDERS = frozenset({'soniox', 'modulate', 'deepgram', 'parakeet'})
MIN_LEARNED_SESSIONS = 3
# Only near-identical spoken language pairs belong here. Codes are normalized
# to their base form before this intentionally small equivalence map is used.
LANGUAGE_EQUIVALENCE = {'ur': 'hi', 'hr': 'sr', 'bs': 'sr', 'id': 'ms'}
MAX_SONIOX_LANGUAGE_HINTS = 3


def canonical_language(language: str | None) -> str:
    code = normalized_stt_language(language)
    return LANGUAGE_EQUIVALENCE.get(code, code)


def learned_expected(primary: str, sessions: list[dict[str, int]]) -> tuple[str, ...]:
    if len(sessions) < MIN_LEARNED_SESSIONS:
        return ()
    counts = Counter[str]()
    session_presence = Counter[str]()
    for session in sessions:
        normalized = Counter[str]()
        for code, count in session.items():
            normalized[canonical_language(code)] += count
        counts.update(normalized)
        session_presence.update(normalized.keys())
    total = sum(counts.values())
    if not total:
        return ()
    primary = canonical_language(primary)
    declared = (primary,) if primary not in ('', 'en') and soniox_accepts_language_hint(primary) else ()
    candidates = sorted(
        (
            code
            for code, count in counts.items()
            if code != 'en'
            and count / total >= 0.2
            and session_presence[code] >= MIN_LEARNED_SESSIONS
            and soniox_accepts_language_hint(code)
            and code not in declared
        ),
        key=lambda code: (-counts[code], code),
    )
    expected = (*declared, *candidates)[:3]
    if counts['en'] / total >= 0.1 and soniox_accepts_language_hint('en'):
        expected = (*expected[:2], 'en') if len(expected) >= 3 else (*expected, 'en')
    return expected


@dataclass(frozen=True)
class LiveLanguageProfile:
    primary: str
    expected: tuple[str, ...]
    primary_group: str
    arm: str
    multi: bool
    in_scope: bool = True
    source: str = 'declared'

    @property
    def learning_enabled(self) -> bool:
        return self.in_scope and self.multi and os.getenv('STT_LEARNED_LANGUAGE_PROFILE', 'false').lower() == 'true'

    @classmethod
    def create(
        cls,
        language: str | None,
        *,
        multi: bool,
        uid: str | None,
        in_scope: bool = True,
        learned_sessions: list[dict[str, int]] | None = None,
    ) -> LiveLanguageProfile:
        primary = canonical_language(language)
        if not re.fullmatch(r'[a-z]{2,3}', primary):
            primary = ''
        expected = (primary, 'en') if multi and primary not in ('', 'en') else ((primary,) if primary else ())
        source = 'declared'
        if in_scope and multi and os.getenv('STT_LEARNED_LANGUAGE_PROFILE', 'false').lower() == 'true':
            learned = learned_expected(primary, learned_sessions or [])
            if learned:
                expected, source = learned, 'learned'
        group = 'non_en' if any(code != 'en' for code in expected) else ('en' if primary == 'en' else 'unknown')
        eligible = in_scope and multi and group == 'non_en'
        arm = 'hintable' if eligible and hintable_allocation(uid) else ('control' if eligible else 'na')
        return cls(primary, expected, group, arm, multi, in_scope, source)


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
    preferred_service: str | None = None,
) -> bool:
    """Read-only admission; the actual connect still owns its breaker probe."""
    return bool(
        profile
        and profile.in_scope
        and profile.arm == 'hintable'
        and (preferred_service or '').strip().lower() != 'parakeet'
        and 'soniox' in (model.strip() for model in models)
        and SONIOX_PROVIDER not in exclude
        and provider_is_enabled(SONIOX_PROVIDER, STTServingSurface.STREAMING)
        and os.getenv('SONIOX_API_KEY')
        and circuit_ready()
    )


def soniox_hints(language: str, profile: LiveLanguageProfile | None = None) -> list[str]:
    normalized = normalized_stt_language(language)
    if (
        profile
        and profile.in_scope
        and profile.multi
        and profile.primary_group == 'non_en'
        and os.getenv('STT_MULTI_LANGUAGE_HINTS', 'true').lower() == 'true'
    ):
        candidates = profile.expected
    else:
        candidates = (normalized,) if normalized and normalized != 'multi' else ()
        return [code for code in candidates if soniox_accepts_language_hint(code)]
    normalized_candidates = list(dict.fromkeys(canonical_language(code) for code in candidates))
    if not any(code in LANGUAGE_EQUIVALENCE.values() for code in normalized_candidates):
        return [code for code in normalized_candidates if soniox_accepts_language_hint(code)]

    # Keep each expected language beside its accepted variants; English stays
    # after the declared/learned non-English languages within the existing cap.
    ordered = []
    for code in normalized_candidates:
        if code == 'en':
            continue
        ordered.append(code)
        ordered.extend(alias for alias, canonical in LANGUAGE_EQUIVALENCE.items() if canonical == code)
    ordered.extend(code for code in normalized_candidates if code == 'en')
    hints = []
    for code in ordered:
        if code not in hints and soniox_accepts_language_hint(code):
            hints.append(code)
        if len(hints) >= MAX_SONIOX_LANGUAGE_HINTS:
            break
    return hints


def connection_constraint(provider: str, language: str, profile: LiveLanguageProfile) -> str:
    if provider == 'soniox':
        return 'hinted' if soniox_hints(language, profile) else 'auto'
    return 'forced' if language and language != 'multi' else 'auto'


def classify_output(
    text: str, profile: LiveLanguageProfile, provider_language: str | None = None
) -> tuple[str, str | None]:
    """Classify one finalized segment; caller runs uncertain detection off-loop."""
    if not profile.expected and not profile.learning_enabled:
        return 'undetermined', None
    language = canonical_language(provider_language)
    if not re.fullmatch(r'[a-z]{2,3}', language):
        language = ''
    if not language:
        text = text[:MAX_DETECTION_CHARS]
        if sum(letter.isalpha() for letter in text) < MIN_LETTERS:
            return 'undetermined', None
        try:
            DetectorFactory.seed = 0
            guesses = detect_langs(text)
        except Exception:
            return 'undetermined', None
        if not guesses or guesses[0].prob < MIN_PROBABILITY:
            return 'undetermined', None
        language = canonical_language(guesses[0].lang)
        if not re.fullmatch(r'[a-z]{2,3}', language):
            return 'undetermined', None
    return (
        'undetermined'
        if not profile.expected
        else 'in_profile' if language in {canonical_language(code) for code in profile.expected} else 'out_of_profile'
    ), language


@dataclass
class LiveLanguageObservations:
    profile: LiveLanguageProfile
    providers: set[str] = field(default_factory=set)
    constraints: set[str] = field(default_factory=set)
    counts: Counter[str] = field(default_factory=Counter)
    out_codes: Counter[str] = field(default_factory=Counter)
    language_counts: Counter[str] = field(default_factory=Counter)
    pending: set[asyncio.Task[Any]] = field(default_factory=set)
    telemetry_failure_logged: bool = False
    learning_scheduled: bool = False

    def warn_once(self) -> None:
        if not self.telemetry_failure_logged:
            self.telemetry_failure_logged = True
            logger.warning('Live STT language telemetry failed')

    def connected(self, provider: str, language: str) -> None:
        constraint = connection_constraint(provider, language, self.profile)
        self.providers.add(provider)
        self.constraints.add(constraint)
        LANGUAGE_CONSTRAINT.labels(provider, constraint, self.profile.primary_group, self.profile.arm).inc()

    def _record(self, provider: str, result: tuple[str, str | None]) -> None:
        conformance, code = result
        code = canonical_language(code) if code else None
        self.counts[conformance] += 1
        if conformance == 'out_of_profile' and code:
            self.out_codes[code] += 1
        if code:
            self.language_counts[code] += 1
        OUTPUT_LANGUAGE_SEGMENTS.labels(
            provider, self.profile.primary_group, self.profile.arm, conformance, self.profile.source
        ).inc()

    def observe(self, segment: dict[str, Any], provider: str, spawn: Any) -> None:
        # Provider metadata is ephemeral; never persist it with transcript text.
        language = segment.pop('_provider_language', None)
        code = canonical_language(language if isinstance(language, str) else None)
        language = code if re.fullmatch(r'[a-z]{2,3}', code) else None
        text = str(segment.get('text') or '')[:MAX_DETECTION_CHARS]
        if (
            language
            or (not self.profile.expected and not self.profile.learning_enabled)
            or sum(c.isalpha() for c in text) < MIN_LETTERS
        ):
            self._record(provider, classify_output(text, self.profile, language))
            return
        if len(self.pending) >= MAX_PENDING_DETECTIONS:
            self._record(provider, ('undetermined', None))
            return

        async def detect() -> None:
            try:
                result = await run_blocking(sync_executor, classify_output, text, self.profile)
            except Exception:
                result = ('undetermined', None)
            self._record(provider, result)

        coroutine = detect()
        try:
            task = spawn(coroutine, name='stt_language_detect')
        except Exception:
            coroutine.close()
            raise
        self.pending.add(task)
        task.add_done_callback(self.pending.discard)

    async def summarize(self, uid: str | None = None) -> None:
        if self.pending:
            # Bounded so a backed-up executor cannot hold session close.
            await asyncio.wait(tuple(self.pending), timeout=2.0)
        logger.info(
            'live_stt_language_summary primary=%s expected=%s providers=%s constraint=%s arm=%s source=%s '
            'in_profile=%d out_of_profile=%d undetermined=%d top_out_code=%s',
            self.profile.primary or 'unknown',
            ','.join(self.profile.expected),
            ','.join(sorted(self.providers)),
            ','.join(sorted(self.constraints)),
            self.profile.arm,
            self.profile.source,
            self.counts['in_profile'],
            self.counts['out_of_profile'],
            self.counts['undetermined'],
            self.out_codes.most_common(1)[0][0] if self.out_codes else '',
        )
        if (
            uid
            and self.profile.in_scope
            and self.profile.multi
            and self.language_counts
            and not self.learning_scheduled
            and self.profile.learning_enabled
        ):
            self.learning_scheduled = True
            try:
                start_background_task(self._persist(uid, dict(self.language_counts)), name='stt_learned_language_write')
            except Exception:
                self.warn_once()

    async def _persist(self, uid: str, counts: dict[str, int]) -> None:
        try:
            await asyncio.wait_for(
                run_blocking(db_executor, append_live_language_session, uid, counts),
                timeout=3.0,
            )
        except Exception:
            self.warn_once()


def observe_live_segments(host: Any, segments: list[dict[str, Any]], provider: str) -> None:
    observations = getattr(host, 'language_observations', None)
    if getattr(host, 'use_custom_stt', False) or not isinstance(observations, LiveLanguageObservations):
        for segment in segments:
            segment.pop('_provider_language', None)
        return
    for segment in segments:
        try:
            observations.observe(segment, provider if provider in LIVE_PROVIDERS else 'other', host.spawn)
        except Exception:
            # Telemetry must never interrupt a provider callback or transcript delivery.
            segment.pop('_provider_language', None)
            observations.warn_once()


def record_live_connection(host: Any, provider: str) -> None:
    observations = getattr(host, 'language_observations', None)
    if isinstance(observations, LiveLanguageObservations):
        try:
            observations.connected(provider if provider in LIVE_PROVIDERS else 'other', host.stt_language)
        except Exception:
            observations.warn_once()
