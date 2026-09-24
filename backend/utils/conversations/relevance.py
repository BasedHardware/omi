"""The one relevance decision every processed conversation passes through.

Callers say *why* they are processing (a ``ProcessingTrigger``); its row in
``processing_trigger.PROCESSING_MODES`` says whether relevance is assessed. Assessment
runs cheap deterministic rules first and asks the model only about the
ambiguous middle. Every outcome is a ``RelevanceDecision`` that is stored on
the conversation and counted, so a path that silently skips the gate shows up
as data instead of as junk in a user's list.

Discard is always recoverable (Show discarded, restore). A user's restore is
recorded as ``sync_relevance_user_kept`` and outranks every later assessment.

With ``CONVERSATION_RELEVANCE_JEV_ENABLED`` the model tier asks the Jev decision
model (``relevance_jev.py``) instead of ``conv_discard`` for transcript-only
conversations, and discards only above ``JEV_DISCARD_THRESHOLD`` (#14835).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Iterable, Literal, Mapping, Optional, Sequence

from config.jev_decisions import JEV_MODEL
from utils.conversations.processing_trigger import PROCESSING_MODES, ProcessingTrigger, RelevancePolicy
from utils.conversations.relevance_rules import RULES_VERSION, deterministic_relevance

RELEVANCE_DECISION_FIELD = 'relevance_decision'


DecidedBy = Literal['policy', 'user', 'rule', 'model', 'jev', 'override']

# Jev discards only when P(discard) = 1 - P(worth keeping) is above this. On the
# owner's labels (2026-09-23) 0.95 lost none of 20 conversations he kept; on the
# agent-labelled set the zero-loss point was 0.93, and calibration is poor, so
# the margin is deliberately above it. Lowering it needs a re-measured set.
JEV_DISCARD_THRESHOLD = 0.95


@dataclass(frozen=True)
class Neighbor:
    """A kept conversation within the boundary gap of the one being judged."""

    conversation_id: str
    gap_seconds: float
    position: Literal['before', 'after']  # where the neighbor sits relative to this one


@dataclass(frozen=True)
class RelevanceDecision:
    verdict: Literal['keep', 'discard']
    decided_by: DecidedBy
    reason: str
    trigger: ProcessingTrigger
    # Set when a discarded fragment belongs to an adjacent kept conversation.
    neighbor_id: Optional[str] = None
    # Jev's P(discard) when the Jev tier ran, including a calendar override of its discard.
    jev_p_discard: Optional[float] = None

    @property
    def discard(self) -> bool:
        return self.verdict == 'discard'

    def as_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            'verdict': self.verdict,
            'decided_by': self.decided_by,
            'reason': self.reason,
            'trigger': self.trigger.value,
            'rules_version': RULES_VERSION,
        }
        if self.neighbor_id:
            record['neighbor_id'] = self.neighbor_id
        if self.jev_p_discard is not None:
            record['jev'] = {
                'p_discard': round(self.jev_p_discard, 4),
                'threshold': JEV_DISCARD_THRESHOLD,
                'model': JEV_MODEL,
            }
        return record


def find_neighbor(
    rows: Iterable[Mapping[str, Any]],
    *,
    conversation_id: Optional[str],
    started_at: Optional[datetime],
    finished_at: Optional[datetime],
    gap_seconds: float,
) -> Optional[Neighbor]:
    """The nearest visible completed conversation whose span is within ``gap_seconds``.

    Pure: callers fetch candidate rows. Same boundary gap that splits
    conversations, so a neighbor is exactly a conversation this one would have
    joined had capture not split it.
    """
    if started_at is None or finished_at is None:
        return None
    best: Optional[Neighbor] = None
    for row in rows:
        other_id = row.get('id')
        other_start, other_end = row.get('started_at'), row.get('finished_at')
        if not other_id or other_id == conversation_id or row.get('discarded') or row.get('deleted'):
            continue
        if not isinstance(other_start, datetime) or not isinstance(other_end, datetime):
            continue
        if other_end <= started_at:
            gap, position = (started_at - other_end).total_seconds(), 'before'
        elif other_start >= finished_at:
            gap, position = (other_start - finished_at).total_seconds(), 'after'
        else:
            gap, position = 0.0, 'before'  # overlapping capture of the same moment
        if gap < gap_seconds and (best is None or gap < best.gap_seconds):
            best = Neighbor(str(other_id), gap, position)
    return best


def decide_relevance(
    *,
    trigger: ProcessingTrigger,
    texts: Sequence[str],
    speech_seconds: Optional[float],
    has_photos: bool,
    user_kept: bool,
    exempt: bool,
    trusted_wake_word: bool,
    model_discards: Optional[Callable[[Callable[[Exception], None], Optional[Neighbor]], bool]],
    calendar_retains: Callable[[], bool],
    neighbor: Callable[[], Optional[Neighbor]] = lambda: None,
    jev_discard_probability: Optional[Callable[[], Optional[float]]] = None,
) -> RelevanceDecision:
    """Decide keep/discard. Thunks run only when their tier is reached.

    ``model_discards`` receives an error callback; the model tier fails open to
    keep, and the callback lets the decision record say so. ``None`` means the
    plan withholds the model (free-tier desktop): the rules still run, and what
    they cannot settle is kept. ``neighbor`` is looked up only for the model
    tier: a short fragment is judged as a possible continuation of the adjacent
    conversation, and a discard links to it instead of standing alone.
    ``calendar_retains`` is consulted only for a discard verdict: a scrap
    recorded inside a booked meeting is evidence, never noise (SCA-381).

    ``jev_discard_probability`` replaces ``model_discards`` for the model tier
    when the caller supplies it (flag on and the conversation is transcript
    only). It returns P(discard), or ``None`` when Jev gave no answer, which
    keeps. It inherits the model tier's plan gate: with ``model_discards=None``
    neither runs.
    """

    def keep(decided_by: DecidedBy, reason: str) -> RelevanceDecision:
        return RelevanceDecision('keep', decided_by, reason, trigger)

    def discard_unless_calendar(
        decided_by: DecidedBy, reason: str, jev_p_discard: Optional[float] = None
    ) -> RelevanceDecision:
        if calendar_retains():
            return RelevanceDecision('keep', 'override', 'calendar_overlap', trigger, jev_p_discard=jev_p_discard)
        return RelevanceDecision('discard', decided_by, reason, trigger, jev_p_discard=jev_p_discard)

    if PROCESSING_MODES[trigger].relevance is RelevancePolicy.KEEP:
        return keep('policy', trigger.value)
    if exempt:
        return keep('policy', 'exempt')
    if user_kept:
        return keep('user', 'restored')

    # Photos carry content the transcript rules cannot see, and a trusted wake
    # word is judged by the model's wake-word rules (an invocation the
    # assistant already handled may be discarded); both skip the rules.
    if not has_photos and not trusted_wake_word:
        verdict, rule = deterministic_relevance(texts, speech_seconds)
        if verdict == 'keep':
            return keep('rule', rule)
        if verdict == 'discard':
            return discard_unless_calendar('rule', rule)

    if model_discards is None:
        return keep('policy', 'model_withheld')

    if jev_discard_probability is not None:
        p_discard = jev_discard_probability()
        if p_discard is None:
            return keep('jev', 'jev_error')
        if p_discard > JEV_DISCARD_THRESHOLD:
            return discard_unless_calendar('jev', 'jev_discard', p_discard)
        return RelevanceDecision('keep', 'jev', 'jev_keep', trigger, jev_p_discard=p_discard)

    model_failed = False

    def on_model_error(_error: Exception) -> None:
        nonlocal model_failed
        model_failed = True

    adjacent = neighbor()
    discards = model_discards(on_model_error, adjacent)
    if model_failed:
        return keep('model', 'model_error')
    if discards:
        decision = discard_unless_calendar('model', 'neighbor_fragment' if adjacent else 'model_discard')
        if adjacent and decision.discard:
            return RelevanceDecision('discard', 'model', 'neighbor_fragment', trigger, adjacent.conversation_id)
        return decision
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
