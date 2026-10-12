"""Generation-bounded clear-rejection history protects ordinary FIFO work."""

from __future__ import annotations

from math import isfinite
from typing import Any, Mapping, Optional

from utils.manual_speaker_assignments import manual_rejected_speakers
from utils.observability.speaker_embedding_budget import REJECTOR_TAIL_DENIALS
from utils.stt import speaker_match as policy
from utils.stt.speaker_match import SpeakerMatchDecision
from utils.transcribe_decisions import USER_SELF_PERSON_ID


def clear_reject(decision: Optional[SpeakerMatchDecision], distances: Mapping[str, float]) -> bool:
    # Below-threshold margin abstentions are ambiguous even though the legacy
    # decision counter calls them rejected. Protect the entire owner near band.
    return bool(
        decision is not None
        and decision.best_id is not None
        and not decision.accepted
        and not decision.owner_contended
        and distances
        and all(isfinite(distance) and distance >= policy.SPEAKER_MATCH_THRESHOLD for distance in distances.values())
        and distances.get(USER_SELF_PERSON_ID, float('inf')) >= policy.OWNER_NEAR_MISS_THRESHOLD
    )


class RejectorHistory:
    def __init__(self, matcher: Any) -> None:
        self.matcher = matcher
        # Admission bounds both inventories to 128 voices. Saturate at three;
        # -1 permanently protects any other completed result in this generation.
        self.comparisons: dict[int, int] = {}
        self.manual: set[int] = set()

    def proven(self, voice: int) -> bool:
        return (
            self.comparisons.get(voice, 0) >= 3
            and voice not in self.manual
            and self.matcher._mapping_origin.get(voice) != 'manual'
            and clear_reject(self.matcher._voice_decisions.get(voice), self.matcher._voice_distances.get(voice, {}))
        )

    def comparison(self, voice: int, decision: Optional[SpeakerMatchDecision], evidence_seconds: float) -> None:
        clear = evidence_seconds >= policy.SPEAKER_MATCH_MIN_EVIDENCE_SECONDS and clear_reject(
            decision, self.matcher._voice_distances.get(voice, {})
        )
        previous = self.comparisons.get(voice, 0)
        self.comparisons[voice] = min(3, previous + 1) if clear and previous >= 0 else -1

    def recovery_denial(self, voice: int) -> Optional[str]:
        """Classify extra-query eligibility without changing scheduling proof."""
        if self.proven(voice):
            return 'proven_rejector'
        decision = self.matcher._voice_decisions.get(voice)
        if voice not in self.comparisons and decision is None:
            return None
        if decision is not None and policy.owner_near_miss(decision):
            return None
        return (
            'clearly_far'
            if clear_reject(decision, self.matcher._voice_distances.get(voice, {}))
            else 'completed_not_near_owner'
        )

    def observe_manual(self, receipt: Mapping[str, Any]) -> None:
        # Reuse the final authority snapshot; no new reads or publication policy.
        rejected = manual_rejected_speakers(receipt)
        self.manual.update(
            voice
            for voice in self.matcher._embedding_attempts
            if voice in rejected or self.matcher._manual_voice_decision(receipt, voice) is not None
        )

    def deny_tail(self, voice: int, tokens: float) -> bool:
        if tokens <= 2 and self.proven(voice):
            REJECTOR_TAIL_DENIALS.labels(reason='reserved_tail').inc()
            self.matcher._record_exit('rejector_tail_reserved', voice)
            return True
        return False

    def clear(self) -> None:
        self.comparisons.clear()
        self.manual.clear()
