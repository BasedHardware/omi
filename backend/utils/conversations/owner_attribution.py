"""Source-cluster evidence is the authority for owner-attributed memory writes."""

from dataclasses import dataclass
from typing import Any, Literal, Optional, Sequence

OwnerTrust = Literal["unique_owner", "no_owner", "multi_owner", "no_speaker_ids"]


def count_speaker_ids(segments: Any) -> tuple[int, int]:
    """Return distinct cluster counts and clusters flagged as the account owner."""
    distinct: set[Any] = set()
    owner: set[Any] = set()
    for segment in segments:
        speaker_id = getattr(segment, "speaker_id", None)
        if speaker_id is None:
            continue
        distinct.add(speaker_id)
        if getattr(segment, "is_user", False):
            owner.add(speaker_id)
    return len(distinct), len(owner)


@dataclass(frozen=True)
class OwnerAttributionEvidence:
    distinct_speaker_ids: int
    owner_speaker_ids: int
    owner_cluster_id: Optional[int]
    trust: OwnerTrust

    @classmethod
    def from_segments(cls, segments: Sequence[Any]) -> "OwnerAttributionEvidence":
        distinct, owners = count_speaker_ids(segments)
        trust: OwnerTrust = (
            "no_speaker_ids"
            if distinct == 0
            else "no_owner" if owners == 0 else "multi_owner" if owners > 1 else "unique_owner"
        )
        cluster = (
            next(
                (
                    segment.speaker_id
                    for segment in segments
                    if getattr(segment, "is_user", False) and getattr(segment, "speaker_id", None) is not None
                ),
                None,
            )
            if trust == "unique_owner"
            else None
        )
        return cls(distinct, owners, cluster, trust)


def may_attribute_to_owner(evidence: OwnerAttributionEvidence, *, segment: Any = None) -> bool:
    """Admit a user fact, or bind a quote only to the uniquely identified owner cluster.

    Legacy transcripts without cluster evidence fail closed. Segment labels alone
    cannot override the conversation's evidence, including for quote promotion.
    """
    return evidence.trust == "unique_owner" and (
        segment is None or getattr(segment, "speaker_id", None) == evidence.owner_cluster_id
    )
