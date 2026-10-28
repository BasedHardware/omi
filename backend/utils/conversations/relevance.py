"""The one relevance decision every processed conversation passes through.

Callers say *why* they are processing (a ``ProcessingTrigger``); its row in
``processing_trigger.PROCESSING_MODES`` says whether relevance is assessed. Assessment
runs cheap deterministic rules first and asks the model only about the
ambiguous middle. Every outcome is a ``RelevanceDecision`` that is stored on
the conversation and counted, so a path that silently skips the gate shows up
as data instead of as junk in a user's list.

Discard is always recoverable (Show discarded, restore). A user's restore is
recorded as ``sync_relevance_user_kept`` and outranks every later assessment.

The ``CONVERSATION_RELEVANCE_JEV_PERCENT`` cohort asks the Jev decision model
(``relevance_jev.py``) before ``conv_discard`` for transcript-only conversations.
It discards above the default ``JEV_DISCARD_THRESHOLD`` (#14835),
unless the bounded cutoff or inclusive comparison is explicitly configured.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Callable, Iterable, Literal, Mapping, Optional, Sequence

from config.jev_decisions import JEV_MODEL, RelevanceArm
from utils.conversations.processing_trigger import PROCESSING_MODES, ProcessingTrigger, RelevancePolicy
from utils.conversations.relevance_rules import (
    RULES_VERSION,
    deterministic_relevance,
    deterministic_tiebreak,
    transcript_word_count,
)

from utils.observability.fallback import record_fallback
from utils.metrics import record_relevance_scorer_outcome
from utils.conversations.relevance_circuit import (
    observe_scorer_outcomes,
    get_relevance_circuit,
    report_scorer_outcome,
    scorer_error_outcome,
)

RELEVANCE_DECISION_FIELD = 'relevance_decision'


DecidedBy = Literal['policy', 'user', 'rule', 'model', 'jev', 'override', 'deterministic']

# Jev discards only when P(discard) = 1 - P(worth keeping) is above this by default.
# Re-measured 2026-10-05 on the owner's labels (EXP-004): tuned on 55 decided
# 2026-10 labels, then checked once on 77 held-out 2026-09-23 labels, where 0.80
# lost 3 of 20 kept conversations against 15-17 for the nano prompt, and kept
# 10 of 57 noise. Its ranking is good (AUC ~0.85) but calibration is not, so
# the cut is a measured cutoff, not a probability. Changing it needs a re-measure.
JEV_DISCARD_THRESHOLD = 0.80
JEV_DISCARD_THRESHOLD_ENV = 'CONVERSATION_RELEVANCE_JEV_DISCARD_THRESHOLD'
JEV_DISCARD_INCLUSIVE_ENV = 'CONVERSATION_RELEVANCE_JEV_DISCARD_INCLUSIVE'


def _jev_discard_policy() -> tuple[float, bool]:
    """Read the bounded Jev discard cutoff and comparator at decision time."""
    raw_threshold = os.getenv(JEV_DISCARD_THRESHOLD_ENV)
    try:
        threshold = float(raw_threshold) if raw_threshold is not None else JEV_DISCARD_THRESHOLD
    except (TypeError, ValueError):
        threshold = JEV_DISCARD_THRESHOLD
    if not math.isfinite(threshold) or not 0.5 <= threshold <= 0.95:
        threshold = JEV_DISCARD_THRESHOLD

    raw_inclusive = os.getenv(JEV_DISCARD_INCLUSIVE_ENV, '').strip().lower()
    inclusive = raw_inclusive in {'1', 'true', 'yes', 'on'}
    return threshold, inclusive


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
    arm: Optional[RelevanceArm] = None
    # Snapshot the effective cutoff when Jev decides so later serialization
    # cannot report a different policy if the process environment changes.
    jev_threshold: Optional[float] = None
    jev_comparison: Optional[Literal['>', '>=']] = None

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
        if self.arm is not None:
            record['arm'] = self.arm
        if self.jev_p_discard is not None:
            record['jev'] = {
                'p_discard': round(self.jev_p_discard, 4),
                'threshold': self.jev_threshold if self.jev_threshold is not None else JEV_DISCARD_THRESHOLD,
                'comparison': self.jev_comparison if self.jev_comparison is not None else '>',
                'model': JEV_MODEL,
            }
        return record


@dataclass(frozen=True)
class DecisionArm:
    """Provider-neutral arm: probe without IO, then decide or decline (None)."""

    name: str
    available: Callable[[], bool]
    decide: Callable[[], Optional[RelevanceDecision]]
    paid: bool = True


def _decision_chain(arms: Sequence[DecisionArm]) -> RelevanceDecision:
    available = [candidate for candidate in arms if candidate.available()]
    terminal = available[-1]
    assert not terminal.paid, 'Relevance chain must end in a total deterministic arm'
    primary = next((candidate for candidate in available if candidate.paid), None)
    circuit = get_relevance_circuit(primary.name) if primary is not None else None
    ticket = circuit.acquire() if circuit is not None else None

    def circuit_decision() -> RelevanceDecision:
        assert primary is not None
        record_fallback(
            component='conversation_relevance',
            from_mode=primary.name,
            to_mode=terminal.name,
            reason='circuit_open',
            outcome='degraded',
        )
        decision = terminal.decide()
        assert decision is not None
        return replace(decision, reason='circuit_open') if decision.decided_by == 'deterministic' else decision

    if circuit is not None and ticket is None:
        return circuit_decision()
    for index, candidate in enumerate(available):
        outcome = 'unavailable'

        def observe(value: str) -> None:
            nonlocal outcome
            outcome = value

        with observe_scorer_outcomes(observe):
            decision = candidate.decide()
        if candidate.paid:
            # JEV's adapter records its exact client outcome; nano has no such
            # observer, so record its callback/exception result here.
            if candidate.name != 'jev':
                record_relevance_scorer_outcome('success' if decision is not None else outcome, arm=candidate.name)
            if candidate is primary:
                assert circuit is not None and ticket is not None
                opened = circuit.record(ticket, success=decision is not None)
                if decision is None and opened:
                    record_fallback(
                        component='conversation_relevance',
                        from_mode=candidate.name,
                        to_mode=terminal.name,
                        reason=outcome,
                        outcome='degraded',
                    )
                    decision = terminal.decide()
                    assert decision is not None
                    return replace(
                        decision, reason='circuit_open' if decision.decided_by == 'deterministic' else decision.reason
                    )
        if decision is not None:
            return decision
        if index + 1 < len(available):
            record_fallback(
                component='conversation_relevance',
                from_mode=candidate.name,
                to_mode=available[index + 1].name,
                reason=outcome,
                outcome='degraded',
            )
    raise AssertionError('Relevance chain must end in a total deterministic arm')


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
    arm: RelevanceArm = 'nano',
    record_arm: bool = False,
) -> RelevanceDecision:
    """Decide keep/discard. Thunks run only when their tier is reached.

    Withheld models keep the ambiguous middle without attempting any paid arm.
    Attempted paid arms run in order: Jev (when supplied),
    legacy nano, deterministic tie-break. A None answer, error callback or
    model exception advances the chain. The final arm uses only lexicon evidence,
    never duration or raw length to discard. Photos and trusted wake words
    keep when no model can assess their content. Calendar protection applies
    to every discard. A capture below the short-clip floor is not sent to Jev
    (its keep would stand the clip up with full notes); the quiet-minimum path
    upstream normally intercepts such clips first, so a calendar rescue here
    only ever keeps a short in-meeting fragment instead of discarding it.
    """

    # Speech the floor can measure: an empty transcript is not a short clip but a
    # capture scrap, whose calendar retention (SCA-381 evidence) stands unchanged.
    # Lazy: notes_short_clip pulls the notes/recovery stack, which this leaf module must not import eagerly.
    from utils.llm.notes_short_clip import below_short_clip_floor

    floor_words = sum(transcript_word_count(text) for text in texts)
    short_clip = (
        floor_words > 0
        and not has_photos
        and not trusted_wake_word
        and below_short_clip_floor(words=floor_words, speech_seconds=speech_seconds)
    )

    def keep(decided_by: DecidedBy, reason: str) -> RelevanceDecision:
        return RelevanceDecision('keep', decided_by, reason, trigger)

    def discard_unless_calendar(
        decided_by: DecidedBy,
        reason: str,
        jev_p_discard: Optional[float] = None,
        jev_threshold: Optional[float] = None,
        jev_comparison: Optional[Literal['>', '>=']] = None,
    ) -> RelevanceDecision:
        if calendar_retains():
            return RelevanceDecision(
                'keep',
                'override',
                'calendar_overlap',
                trigger,
                jev_p_discard=jev_p_discard,
                jev_threshold=jev_threshold,
                jev_comparison=jev_comparison,
            )
        return RelevanceDecision(
            'discard',
            decided_by,
            reason,
            trigger,
            jev_p_discard=jev_p_discard,
            jev_threshold=jev_threshold,
            jev_comparison=jev_comparison,
        )

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

    jev_failed = False

    def jev_decision() -> Optional[RelevanceDecision]:
        nonlocal jev_failed
        assert jev_discard_probability is not None
        try:
            p_discard = jev_discard_probability()
        except Exception as error:
            report_scorer_outcome(scorer_error_outcome(error))
            p_discard = None
        if p_discard is None:
            jev_failed = True
            return None
        threshold, inclusive = _jev_discard_policy()
        comparison: Literal['>', '>='] = '>=' if inclusive else '>'
        should_discard = p_discard >= threshold if inclusive else p_discard > threshold
        if should_discard:
            return discard_unless_calendar('jev', 'jev_discard', p_discard, threshold, comparison)
        return RelevanceDecision(
            'keep',
            'jev',
            'jev_keep',
            trigger,
            jev_p_discard=p_discard,
            jev_threshold=threshold,
            jev_comparison=comparison,
        )

    def nano_decision() -> Optional[RelevanceDecision]:
        failed = False

        def on_error(_error: Exception) -> None:
            nonlocal failed
            failed = True
            report_scorer_outcome(scorer_error_outcome(_error))

        assert model_discards is not None
        adjacent = neighbor()
        try:
            discards = model_discards(on_error, adjacent)
        except Exception as error:
            on_error(error)
            return None
        if failed:
            return None
        nano_reason = 'neighbor_fragment' if discards and adjacent else 'model_discard' if discards else 'model_keep'
        reason = 'jev_fallback_model' if jev_failed else nano_reason
        decision = discard_unless_calendar('model', reason) if discards else keep('model', reason)
        if discards and adjacent and decision.discard:
            decision = replace(decision, neighbor_id=adjacent.conversation_id)
        return decision

    def deterministic_decision() -> RelevanceDecision:
        reason = 'jev_fallback_deterministic' if jev_failed else 'model_fallback_deterministic'
        # These inputs skipped the rule tier because transcript evidence cannot
        # judge them. Do not reintroduce transcript-only discards on failure.
        verdict = 'keep' if has_photos or trusted_wake_word else deterministic_tiebreak(texts)
        return (
            discard_unless_calendar('deterministic', reason) if verdict == 'discard' else keep('deterministic', reason)
        )

    arms: list[DecisionArm] = []
    if jev_discard_probability is not None:
        # A sub-floor capture never reaches Jev: its keep would stand the clip up
        # as a standalone conversation. Unavailable (not a declined answer) so the
        # scorer circuit does not read the floor as a Jev failure.
        arms.append(DecisionArm('jev', lambda: jev_discard_probability is not None and not short_clip, jev_decision))
    arms.extend(
        (
            DecisionArm('model', lambda: model_discards is not None, nano_decision),
            DecisionArm('deterministic', lambda: True, deterministic_decision, paid=False),
        )
    )
    return replace(_decision_chain(arms), arm=arm if record_arm or arm != 'nano' else None)


def final_relevance(decision: Optional[RelevanceDecision], *, discarded: bool) -> Optional[RelevanceDecision]:
    """The decision to store: the structuring model's empty title is its own discard."""
    if decision is not None and discarded and not decision.discard:
        return replace(decision, verdict='discard', decided_by='model', reason='empty_title', jev_p_discard=None)
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


def content_minimum(uid: str, conversation: Any, *, user_kept: bool = False) -> Any:
    """V2 pre-model content policy; owners wire this before paid relevance/notes.

    Lazy import keeps the existing deterministic relevance authority import-light.
    The optional minimum is a compute decision, never a duration discard verdict.
    """
    from utils.conversations.relevance_media import minimum_for_processing

    return minimum_for_processing(uid, conversation, user_kept=user_kept)
