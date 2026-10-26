"""Source-cluster evidence is the authority for owner-attributed memory writes."""

from dataclasses import dataclass
from typing import Any, Literal, Optional, Sequence

OwnerTrust = Literal["unique_owner", "no_owner", "multi_owner", "no_speaker_ids"]
ClusterKey = tuple[Optional[str], Any]
OWNER_MATCH_SOURCES = frozenset(('conversation_voice', 'speaker_evidence_v2'))


def speaker_cluster_key(segment: Any) -> Optional[ClusterKey]:
    """Return the scope-qualified cluster identity, or None when it is not evidence.

    Numeric ``speaker_id`` values are conversation-local and can repeat across
    ``speaker_id_scope`` values after a merge. A TranscriptSegment that only
    materialized ``speaker_id`` from the SPEAKER_00 default is not a cluster.
    """
    if getattr(segment, "_speaker_id_synthesized", False):
        return None
    speaker_id = getattr(segment, "speaker_id", None)
    if speaker_id is None:
        return None
    return (getattr(segment, "speaker_id_scope", None), speaker_id)


def count_speaker_ids(segments: Any) -> tuple[int, int]:
    """Return distinct cluster counts and clusters flagged as the account owner."""
    distinct: set[ClusterKey] = set()
    owner: set[ClusterKey] = set()
    for segment in segments:
        key = speaker_cluster_key(segment)
        if key is None:
            continue
        distinct.add(key)
        if getattr(segment, "is_user", False):
            owner.add(key)
    return len(distinct), len(owner)


@dataclass(frozen=True)
class OwnerAttributionEvidence:
    distinct_speaker_ids: int
    owner_speaker_ids: int
    owner_cluster_id: Optional[ClusterKey]
    trust: OwnerTrust

    @classmethod
    def from_segments(cls, segments: Sequence[Any]) -> "OwnerAttributionEvidence":
        distinct, owners = count_speaker_ids(segments)
        trust: OwnerTrust = (
            "no_speaker_ids"
            if distinct == 0
            else "no_owner" if owners == 0 else "multi_owner" if owners > 1 else "unique_owner"
        )
        cluster: Optional[ClusterKey] = None
        if trust == "unique_owner":
            for segment in segments:
                if not getattr(segment, "is_user", False):
                    continue
                key = speaker_cluster_key(segment)
                if key is not None:
                    cluster = key
                    break
        return cls(distinct, owners, cluster, trust)


def may_attribute_to_owner(evidence: OwnerAttributionEvidence, *, segment: Any = None) -> bool:
    """Admit a user fact, or bind a quote only to the uniquely identified owner cluster.

    Legacy transcripts without cluster evidence fail closed. Segment labels alone
    cannot override the conversation's evidence, including for quote promotion.
    """
    return evidence.trust == "unique_owner" and (
        segment is None or speaker_cluster_key(segment) == evidence.owner_cluster_id
    )


def confident_owner_segments(segments: Sequence[Any]) -> list[Any]:
    """Memory input requires a positive identity decision, never a legacy boolean.

    Keep the full transcript for notes/playback. Only this derived input is
    narrowed. Ambiguous multi-owner clusters and a carried ``is_user`` without
    a current user decision do not authorize memory formation. An explicit
    manual label is a positive owner decision too.
    """
    # TranscriptSegment supplies status='user' for a legacy is_user payload.
    # That compatibility default is not an identity decision. Require the
    # producer's positive-match provenance (or the explicit manual authority).
    trusted = [
        segment
        for segment in segments
        if getattr(segment, 'is_user', False)
        and not getattr(segment, 'person_id', None)
        and (
            getattr(segment, 'speaker_label_source', None) == 'manual'
            or (
                getattr(segment, 'speaker_identity_status', None) == 'user'
                and getattr(segment, 'speaker_match_source', None) in OWNER_MATCH_SOURCES
                and getattr(segment, 'speaker_label_source', None) != 'carried'
            )
        )
    ]
    # An unproven legacy boolean on another voice must not veto a real manual
    # confirmation. Ambiguity is measured across trusted owner decisions only.
    evidence = OwnerAttributionEvidence.from_segments(trusted)
    return [segment for segment in trusted if may_attribute_to_owner(evidence, segment=segment)]
