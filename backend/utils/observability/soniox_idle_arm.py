"""Per-arm session outcomes for the Soniox idle-close treatment cohort.

The idle cohort (``config.soniox_idle``) assigns users by uid hash, so a
regression confined to the 5-25% treatment arm is diluted in fleet metrics.
Each listen session keeps one ledger, pinned to its intent-to-treat arm at
admission, and records it once at close with closed labels only:

- arm: ``control`` | ``treatment`` (``idle_settings_for(uid).arm``; every session,
  Soniox-served or not, so the comparison is intent-to-treat)
- plan: ``free`` | ``paid`` | ``unknown`` (set from the session's credit refresh)

Counters cover billed Soniox connected time, Soniox wire audio, decoded capture
audio (the speech denominator), sessions by transcript outcome, final delivered
words, first-output latency, unnamed speaker ordinals and speaker scope
rotations. Never uid, session or conversation labels. Recording never raises.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)

ARMS = ('control', 'treatment')
PLANS = ('free', 'paid', 'unknown')
OUTCOMES = ('transcribed', 'no_transcript', 'too_short', 'none')
# Segment ids tracked for the final word count; a longer session keeps counting
# words already tracked and stops adding new ids (under-count, both arms alike).
MAX_TRACKED_SEGMENTS = 20000

SESSIONS = Counter(
    'omi_soniox_idle_arm_sessions_total',
    'Listen sessions by Soniox idle cohort arm, plan and transcript outcome',
    ['arm', 'plan', 'outcome'],
)
CONNECTED_SECONDS = Counter(
    'omi_soniox_idle_arm_connected_seconds_total',
    'Billed Soniox websocket seconds by idle cohort arm and plan, recorded at session close',
    ['arm', 'plan'],
)
WIRE_AUDIO_SECONDS = Counter(
    'omi_soniox_idle_arm_wire_audio_seconds_total',
    'Soniox wire PCM seconds (including replay) by idle cohort arm and plan, recorded at session close',
    ['arm', 'plan'],
)
CAPTURE_AUDIO_SECONDS = Counter(
    'omi_soniox_idle_arm_capture_audio_seconds_total',
    'Decoded listen capture seconds by idle cohort arm and plan, recorded at session close',
    ['arm', 'plan'],
)
TRANSCRIPT_WORDS = Counter(
    'omi_soniox_idle_arm_transcript_words_total',
    'Final words delivered to the client by idle cohort arm and plan (last text per segment, removals excluded)',
    ['arm', 'plan'],
)
FIRST_OUTPUT_SECONDS = Histogram(
    'omi_soniox_idle_arm_first_output_seconds',
    'First decoded audio to first delivered transcript by idle cohort arm and plan',
    ['arm', 'plan'],
    buckets=(0.5, 1, 2, 5, 10, 15, 20, 30, 45, 60),
)
SPEAKER_ORDINALS = Histogram(
    'omi_soniox_idle_arm_speaker_ordinals_per_session',
    'Distinct visible unnamed speaker ordinals per session by idle cohort arm and plan',
    ['arm', 'plan'],
    buckets=(0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 13, 16, 24, 32),
)
SPEAKER_SCOPE_ROTATIONS = Counter(
    'omi_soniox_idle_arm_speaker_scope_rotations_total',
    'Speaker scope/epoch rotations summed per session by idle cohort arm and plan',
    ['arm', 'plan'],
)

try:
    for _arm in ARMS:
        for _plan in PLANS:
            for _outcome in OUTCOMES:
                SESSIONS.labels(arm=_arm, plan=_plan, outcome=_outcome)
            for _metric in (
                CONNECTED_SECONDS,
                WIRE_AUDIO_SECONDS,
                CAPTURE_AUDIO_SECONDS,
                TRANSCRIPT_WORDS,
                FIRST_OUTPUT_SECONDS,
                SPEAKER_ORDINALS,
                SPEAKER_SCOPE_ROTATIONS,
            ):
                _metric.labels(arm=_arm, plan=_plan)
except Exception:
    pass  # Missing zero children are a telemetry HOLD, never a startup failure.


def resolve_arm(uid: Optional[str]) -> str:
    try:
        from config.soniox_idle import idle_settings_for

        arm = idle_settings_for(uid).arm
        return arm if arm in ARMS else 'control'
    except Exception:
        return 'control'


class IdleArmLedger:
    """One listen session's per-arm totals. Event-loop confined; every method swallows errors."""

    def __init__(self, uid: Optional[str]):
        self.arm = resolve_arm(uid)
        self.plan = 'unknown'
        self.outcome = 'none'
        self.connected_seconds = 0.0
        self.wire_seconds = 0.0
        self.capture_seconds = 0.0
        self.first_output_seconds: Optional[float] = None
        self._words: dict[str, int] = {}
        self.recorded = False

    def set_plan(self, subscription: Any) -> None:
        try:
            if subscription is None:
                self.plan = 'free'
                return
            from models.users import PlanType

            self.plan = 'free' if getattr(subscription, 'plan', None) == PlanType.basic else 'paid'
        except Exception:
            pass

    def add_connected(self, seconds: float) -> None:
        if seconds > 0:
            self.connected_seconds += seconds

    def add_wire(self, seconds: float) -> None:
        if seconds > 0:
            self.wire_seconds += seconds

    def add_capture(self, seconds: float) -> None:
        if seconds > 0:
            self.capture_seconds += seconds

    def first_output(self, seconds: float) -> None:
        if self.first_output_seconds is None and seconds >= 0:
            self.first_output_seconds = seconds

    def segments(self, updated: list[dict[str, Any]], removed: list[str]) -> None:
        try:
            for segment in updated:
                segment_id = segment.get('id')
                if not segment_id:
                    continue
                if segment_id not in self._words and len(self._words) >= MAX_TRACKED_SEGMENTS:
                    continue
                self._words[segment_id] = len(str(segment.get('text') or '').split())
            for segment_id in removed:
                self._words.pop(segment_id, None)
        except Exception:
            pass

    @property
    def words(self) -> int:
        return sum(self._words.values())

    def record(self, speakers: Optional[tuple[int, int]]) -> None:
        """Record the session once; ``speakers`` is (unnamed ordinals, scope rotations) or None."""
        if self.recorded:
            return
        self.recorded = True
        try:
            labels = {'arm': self.arm, 'plan': self.plan if self.plan in PLANS else 'unknown'}
            outcome = self.outcome if self.outcome in OUTCOMES else 'none'
            SESSIONS.labels(outcome=outcome, **labels).inc()
            CONNECTED_SECONDS.labels(**labels).inc(self.connected_seconds)
            WIRE_AUDIO_SECONDS.labels(**labels).inc(self.wire_seconds)
            CAPTURE_AUDIO_SECONDS.labels(**labels).inc(self.capture_seconds)
            TRANSCRIPT_WORDS.labels(**labels).inc(self.words)
            if self.first_output_seconds is not None:
                FIRST_OUTPUT_SECONDS.labels(**labels).observe(self.first_output_seconds)
            if speakers is not None:
                ordinals, rotations = speakers
                SPEAKER_ORDINALS.labels(**labels).observe(ordinals)
                if rotations:
                    SPEAKER_SCOPE_ROTATIONS.labels(**labels).inc(rotations)
        except Exception as error:
            logger.warning('Soniox idle arm metric failed type=%s', type(error).__name__)
        finally:
            self._words.clear()


def session_ledger(telemetry: Any) -> Optional[IdleArmLedger]:
    try:
        ledger = getattr(telemetry, 'idle_arm', None)
        return ledger if isinstance(ledger, IdleArmLedger) else None
    except Exception:
        return None


def host_ledger(host: Any) -> Optional[IdleArmLedger]:
    return session_ledger(getattr(host, 'demand_telemetry', None))


def note_plan(host: Any, subscription: Any) -> None:
    ledger = host_ledger(host)
    if ledger is not None:
        ledger.set_plan(subscription)


def note_outcome(host: Any, outcome: str) -> None:
    ledger = host_ledger(host)
    if ledger is not None:
        ledger.outcome = outcome


def note_segments(host: Any, updated: list[dict[str, Any]], removed: list[str]) -> None:
    ledger = host_ledger(host)
    if ledger is not None:
        ledger.segments(updated, removed)


def record_session(host: Any, speakers: Optional[tuple[int, int]]) -> None:
    ledger = host_ledger(host)
    if ledger is not None:
        ledger.record(speakers)
