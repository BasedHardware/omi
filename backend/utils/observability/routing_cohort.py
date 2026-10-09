"""Bounded intent-to-treat telemetry for managed live-STT sockets.

Companion series preserve existing metric schemas. No UID, endpoint, target or
session identifier is retained. Context follows child tasks; adapters and
attempts also pin the object so later callbacks cannot borrow another socket.
"""

from contextvars import ContextVar
import math

from prometheus_client import Counter

COHORT_OUTCOMES = Counter(
    'omi_stt_routing_cohort_outcomes_total',
    'Managed router cohort terminal attempts and completed-session outcomes',
    ['routing_arm', 'signal', 'outcome'],
)
COHORT_PAID_AUDIO = Counter(
    'omi_stt_routing_cohort_paid_audio_seconds_total',
    'Paid adapter accepted PCM seconds including replay, emitted at session end; not vendor billing',
    ['routing_arm', 'provider'],
)
_SIGNALS = {
    'terminal': ('success', 'failure', 'cancelled'),
    'transcript': ('transcribed', 'no_transcript', 'too_short'),
    'fallback_exhausted': ('yes', 'no'),
    'terminal_after_text': ('yes', 'no'),
}
_PAID = ('soniox', 'modulate', 'deepgram')
for _arm in ('off', 'shadow', 'on'):
    for _signal, _outcomes in _SIGNALS.items():
        for _outcome in _outcomes:
            COHORT_OUTCOMES.labels(routing_arm=_arm, signal=_signal, outcome=_outcome)
    for _provider in _PAID:
        COHORT_PAID_AUDIO.labels(routing_arm=_arm, provider=_provider)


class RoutingCohort:
    def __init__(self, arm: str):
        if arm not in {'off', 'shadow', 'on'}:
            raise ValueError('invalid routing cohort')
        self.arm = arm
        self.exhausted = False
        self._finished = False
        self._paid = {provider: 0.0 for provider in _PAID}

    def terminal(self, outcome: str) -> None:
        if outcome in _SIGNALS['terminal']:
            try:
                COHORT_OUTCOMES.labels(routing_arm=self.arm, signal='terminal', outcome=outcome).inc()
            except Exception:
                pass  # Companion telemetry must never interrupt serving.

    def paid_audio(self, provider: str, seconds: float) -> None:
        if not self._finished and provider in _PAID and math.isfinite(seconds) and seconds > 0:
            self._paid[provider] += seconds

    def finish(self, transcript: str, *, terminal_after_text: bool) -> None:
        if self._finished or transcript not in _SIGNALS['transcript']:
            return
        self._finished = True
        for signal, outcome in (
            ('transcript', transcript),
            ('fallback_exhausted', 'yes' if self.exhausted else 'no'),
            ('terminal_after_text', 'yes' if terminal_after_text else 'no'),
        ):
            try:
                COHORT_OUTCOMES.labels(routing_arm=self.arm, signal=signal, outcome=outcome).inc()
            except Exception:
                pass
        for provider, seconds in self._paid.items():
            try:
                COHORT_PAID_AUDIO.labels(routing_arm=self.arm, provider=provider).inc(seconds)
            except Exception:
                pass


current_routing_cohort: ContextVar[RoutingCohort | None] = ContextVar('live_stt_routing_cohort', default=None)
