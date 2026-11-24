"""Closed, zero-initialized recurring voice measurements; no identifiers."""

from prometheus_client import Counter
from utils.observability.reasons import (
    ReasonFamily,
    RecurringProfileOutcome,
    RecurringMatchOutcome,
    IdentitySpeechOutcome,
    reason_label,
)

PROFILES = Counter('omi_recurring_voice_profiles_total', 'Recurring profile lifecycle', ['event'])
MATCHES = Counter('omi_recurring_voice_match_total', 'Recurring voice arbitration', ['outcome'])
SPEECH = Counter('omi_final_pass_identity_speech_seconds_total', 'Final pass word-time identity mix', ['identity'])


def profile_event(event):
    PROFILES.labels(event=reason_label(ReasonFamily.RECURRING_VOICE, event, RecurringProfileOutcome)).inc()


def match_outcome(outcome):
    MATCHES.labels(outcome=reason_label(ReasonFamily.RECURRING_VOICE, outcome, RecurringMatchOutcome)).inc()


def identity_speech(identity, seconds):
    SPEECH.labels(identity=reason_label(ReasonFamily.RECURRING_VOICE, identity, IdentitySpeechOutcome)).inc(
        max(0, seconds)
    )


for value in RecurringProfileOutcome:
    PROFILES.labels(event=reason_label(ReasonFamily.RECURRING_VOICE, value, RecurringProfileOutcome))
for value in RecurringMatchOutcome:
    MATCHES.labels(outcome=reason_label(ReasonFamily.RECURRING_VOICE, value, RecurringMatchOutcome))
for value in IdentitySpeechOutcome:
    SPEECH.labels(identity=reason_label(ReasonFamily.RECURRING_VOICE, value, IdentitySpeechOutcome))
