"""The one relevance decision every processed conversation passes through.

Callers say *why* they are processing (a ``ProcessingTrigger``); the policy
table below says whether that trigger assesses relevance at all. Assessment
runs cheap deterministic rules first and asks the model only about the
ambiguous middle. Every outcome is a ``RelevanceDecision`` that is stored on
the conversation and counted, so a path that silently skips the gate shows up
as data instead of as junk in a user's list.

Discard is always recoverable (Show discarded, restore). A user's restore is
recorded as ``sync_relevance_user_kept`` and outranks every later assessment.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, Literal, Mapping, Optional, Sequence

from utils.conversations.relevance_rules import RULES_VERSION, deterministic_relevance

RELEVANCE_DECISION_FIELD = 'relevance_decision'


class ProcessingTrigger(str, Enum):
    """Why a conversation is being processed."""

    CAPTURE_END = 'capture_end'  # listen finalization, developer/import create
    CLIENT_FINALIZE = 'client_finalize'  # a client ends the conversation
    SYNC_UPDATE = 'sync_update'  # offline sync created or appended to it
    FIRST_OPEN = 'first_open'  # deferred enrichment when the user opens it
    USER_REPROCESS = 'user_reprocess'  # the user asked to reprocess it
    MERGE = 'merge'  # the user merged conversations into it


class RelevancePolicy(str, Enum):
    ASSESS = 'assess'
    KEEP = 'keep'


# Every trigger must appear here; tests enforce exhaustiveness. KEEP is only
# for triggers that are themselves a user action on this conversation.
RELEVANCE_POLICY: Mapping[ProcessingTrigger, RelevancePolicy] = MappingProxyType(
    {
        ProcessingTrigger.CAPTURE_END: RelevancePolicy.ASSESS,
        # Ending a capture is not a judgment about its content; a discard here
        # stays one tap from restore.
        ProcessingTrigger.CLIENT_FINALIZE: RelevancePolicy.ASSESS,
        # Reassessed over the whole merged transcript on every append, so a
        # fragment that later gains real speech is promoted automatically.
        ProcessingTrigger.SYNC_UPDATE: RelevancePolicy.ASSESS,
        ProcessingTrigger.FIRST_OPEN: RelevancePolicy.KEEP,
        ProcessingTrigger.USER_REPROCESS: RelevancePolicy.KEEP,
        ProcessingTrigger.MERGE: RelevancePolicy.KEEP,
    }
)

DecidedBy = Literal['policy', 'user', 'rule', 'model', 'override']


@dataclass(frozen=True)
class RelevanceDecision:
    verdict: Literal['keep', 'discard']
    decided_by: DecidedBy
    reason: str
    trigger: ProcessingTrigger

    @property
    def discard(self) -> bool:
        return self.verdict == 'discard'

    def as_record(self) -> dict[str, Any]:
        return {
            'verdict': self.verdict,
            'decided_by': self.decided_by,
            'reason': self.reason,
            'trigger': self.trigger.value,
            'rules_version': RULES_VERSION,
        }


def decide_relevance(
    *,
    trigger: ProcessingTrigger,
    texts: Sequence[str],
    speech_seconds: Optional[float],
    has_photos: bool,
    user_kept: bool,
    exempt: bool,
    trusted_wake_word: bool,
    model_discards: Callable[[Callable[[Exception], None]], bool],
    calendar_retains: Callable[[], bool],
) -> RelevanceDecision:
    """Decide keep/discard. Thunks run only when their tier is reached.

    ``model_discards`` receives an error callback; the model tier fails open to
    keep, and the callback lets the decision record say so.
    ``calendar_retains`` is consulted only for a discard verdict: a scrap
    recorded inside a booked meeting is evidence, never noise (SCA-381).
    """

    def keep(decided_by: DecidedBy, reason: str) -> RelevanceDecision:
        return RelevanceDecision('keep', decided_by, reason, trigger)

    def discard_unless_calendar(decided_by: DecidedBy, reason: str) -> RelevanceDecision:
        if calendar_retains():
            return keep('override', 'calendar_overlap')
        return RelevanceDecision('discard', decided_by, reason, trigger)

    if RELEVANCE_POLICY[trigger] is RelevancePolicy.KEEP:
        return keep('policy', trigger.value)
    if exempt:
        return keep('policy', 'exempt')
    if user_kept:
        return keep('user', 'restored')

    # Photos carry content the transcript rules cannot see; the model reads both.
    if not has_photos:
        verdict, rule = deterministic_relevance(texts, speech_seconds)
        if verdict == 'keep':
            return keep('rule', rule)
        # A trusted wake word is a deliberate request; only the model, with its
        # wake-word rules, may discard one.
        if verdict == 'discard' and not trusted_wake_word:
            return discard_unless_calendar('rule', rule)

    model_failed = False

    def on_model_error(_error: Exception) -> None:
        nonlocal model_failed
        model_failed = True

    discards = model_discards(on_model_error)
    if model_failed:
        return keep('model', 'model_error')
    if discards:
        return discard_unless_calendar('model', 'model_discard')
    return keep('model', 'model_keep')


def final_relevance(decision: Optional[RelevanceDecision], *, discarded: bool) -> Optional[RelevanceDecision]:
    """The decision to store: the structuring model's empty title is its own discard."""
    if decision is not None and discarded and not decision.discard:
        return RelevanceDecision('discard', 'model', 'empty_title', decision.trigger)
    return decision


def sync_intake_decision(rule: str) -> dict[str, Any]:
    """Record for a fragment the sync intake transaction discards by rule.

    Intake applies only the deterministic tier; everything else is assessed
    when the sync pipeline processes the conversation (``SYNC_UPDATE``).
    """
    return {
        'verdict': 'discard',
        'decided_by': 'rule',
        'reason': rule,
        'trigger': 'sync_intake',
        'rules_version': RULES_VERSION,
    }
