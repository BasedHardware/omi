"""Per-arm session outcomes for the Soniox idle-close treatment cohort.

The idle cohort (``config.soniox_idle``) assigns users by uid hash, so a
regression confined to the 5-25% treatment arm is diluted in fleet metrics.
Each listen session keeps one ledger, pinned to its intent-to-treat arm at
admission, and records it once at close with closed labels only:

- arm: ``control`` | ``treatment`` (``idle_settings_for(uid).arm``; every session,
  Soniox-served or not, so the comparison is intent-to-treat)
- plan: ``free`` | ``paid`` | ``unknown`` (pinned once by a background read at
  admission; ``unknown`` share is a ramp hold, not a bucket to compare)

Counters cover billed Soniox connected time, Soniox wire audio, decoded capture
audio (the speech denominator), sessions by transcript outcome, final delivered
words (sessions past the segment cap are counted apart and excluded from the
word comparison), first-output latency, unnamed speaker ordinals, speaker
scope rotations and live speaker-ID decisions (owner/person by outcome). Never uid, session or conversation labels. Recording never raises.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from prometheus_client import Counter, Histogram

from utils.observability.reasons import ListenSessionTranscriptOutcome, ReasonFamily, reason_label

logger = logging.getLogger(__name__)

ARMS = ('control', 'treatment')
PLANS = ('free', 'paid', 'unknown')
DECISION_TARGETS = ('owner', 'person')
DECISIONS = ('accepted', 'rejected', 'ambiguous', 'pending')
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
WORD_CAPTURE_SECONDS = Counter(
    'omi_soniox_idle_arm_word_capture_audio_seconds_total',
    'Capture seconds of sessions whose word count is complete (the words-per-second denominator)',
    ['arm', 'plan'],
)
WORD_OVERFLOW_SESSIONS = Counter(
    'omi_soniox_idle_arm_word_overflow_sessions_total',
    'Sessions past the tracked-segment cap; their words are excluded from the word comparison',
    ['arm', 'plan'],
)
SPEAKER_DECISIONS = Counter(
    'omi_soniox_idle_arm_live_speaker_decisions_total',
    'Live speaker-ID decisions by idle cohort arm, plan, target (owner/person) and decision',
    ['arm', 'plan', 'target', 'decision'],
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
            SESSIONS.labels(arm=_arm, plan=_plan, outcome='transcribed')
            SESSIONS.labels(arm=_arm, plan=_plan, outcome='no_transcript')
            SESSIONS.labels(arm=_arm, plan=_plan, outcome='too_short')
            SESSIONS.labels(arm=_arm, plan=_plan, outcome='unknown')
            for _target in DECISION_TARGETS:
                for _decision in DECISIONS:
                    SPEAKER_DECISIONS.labels(arm=_arm, plan=_plan, target=_target, decision=_decision)
            for _metric in (
                WORD_CAPTURE_SECONDS,
                WORD_OVERFLOW_SESSIONS,
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
        self.outcome = 'unknown'
        self.connected_seconds = 0.0
        self.wire_seconds = 0.0
        self.capture_seconds = 0.0
        self.first_output_seconds: Optional[float] = None
        self._words: dict[str, int] = {}
        self.words_truncated = False
        self._decisions: dict[tuple[str, str], int] = {}
        self.recorded = False

    def set_plan(self, subscription: Any) -> None:
        """Pin the plan once; later refreshes never reassign a session's plan."""
        if self.plan != 'unknown':
            return
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
                    self.words_truncated = True
                    continue
                self._words[segment_id] = len(str(segment.get('text') or '').split())
            for segment_id in removed:
                self._words.pop(segment_id, None)
        except Exception:
            pass

    def speaker_decision(self, target: str, decision: str) -> None:
        key = (
            target if target in DECISION_TARGETS else 'person',
            decision if decision in DECISIONS else 'rejected',
        )
        self._decisions[key] = self._decisions.get(key, 0) + 1

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
            SESSIONS.labels(
                outcome=reason_label(
                    ReasonFamily.LISTEN_SESSION_TRANSCRIPT, self.outcome, ListenSessionTranscriptOutcome
                ),
                **labels,
            ).inc()
            CONNECTED_SECONDS.labels(**labels).inc(self.connected_seconds)
            WIRE_AUDIO_SECONDS.labels(**labels).inc(self.wire_seconds)
            CAPTURE_AUDIO_SECONDS.labels(**labels).inc(self.capture_seconds)
            if self.words_truncated:
                WORD_OVERFLOW_SESSIONS.labels(**labels).inc()
            else:
                TRANSCRIPT_WORDS.labels(**labels).inc(self.words)
                WORD_CAPTURE_SECONDS.labels(**labels).inc(self.capture_seconds)
            for (target, decision), count in self._decisions.items():
                SPEAKER_DECISIONS.labels(target=target, decision=decision, **labels).inc(count)
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


def note_outcome(host: Any, outcome: str) -> None:
    ledger = host_ledger(host)
    if ledger is not None:
        ledger.outcome = outcome


def note_segments(host: Any, updated: list[dict[str, Any]], removed: list[str]) -> None:
    ledger = host_ledger(host)
    if ledger is not None:
        ledger.segments(updated, removed)


def note_speaker_decision(host: Any, target: str, decision: str) -> None:
    ledger = host_ledger(host)
    if ledger is not None:
        ledger.speaker_decision(target, decision)


async def pin_plan(host: Any, read_subscription: Callable[[str], Any]) -> None:
    """The only plan source: a background read at admission. A failed read leaves the plan
    ``unknown`` (a ramp hold), never a later snapshot. Never raises."""
    ledger = host_ledger(host)
    if ledger is None:
        return
    try:
        subscription = await host.persistence.call(read_subscription, host.request.uid)
        ledger.set_plan(subscription)
    except Exception as error:
        logger.warning('Soniox idle arm plan read failed type=%s', type(error).__name__)


def start_plan_pin(host: Any, read_subscription: Callable[[str], Any]) -> None:
    """Schedule ``pin_plan`` on the session's supervisor; a host without one keeps plan unknown."""
    if host_ledger(host) is None:
        return
    coro = pin_plan(host, read_subscription)
    try:
        host.spawn(coro, name='soniox_idle_arm_plan')
    except Exception:
        coro.close()


def record_session(host: Any, speakers: Optional[tuple[int, int]]) -> None:
    ledger = host_ledger(host)
    if ledger is not None:
        ledger.record(speakers)
