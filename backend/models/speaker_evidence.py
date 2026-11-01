"""Contract for per-conversation speaker evidence (refactor lane L2; consumers L3, L4, L5).

The speaker identity service is the only producer. Segment labels (``is_user``,
``person_id``) are a projection of this record plus the manual receipt, computed in
one place. Consumers read candidates and bands; they never re-threshold scores.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Band = Literal['confident', 'likely', 'unknown']
CandidateSource = Literal['voice', 'manual', 'roster', 'introduction', 'channel', 'near_field']
EvidenceStatus = Literal['resolved', 'partial', 'unavailable']

OWNER = 'owner'


class SpeakerCandidate(BaseModel):
    """A person this voice may be. ``person_id`` is ``owner`` for the account holder."""

    person_id: str
    name: Optional[str] = None
    probability: float = Field(ge=0.0, le=1.0)  # calibrated by the one policy module
    band: Band
    source: CandidateSource
    label_eligible: bool = False  # joint policy decision; probability alone never authorizes a label
    # Manual evidence can bind an excerpt rather than the whole voice. None on
    # older evidence means unknown scope, never permission to expand it.
    segment_ids: Optional[List[str]] = None


class VoiceCluster(BaseModel):
    """One voice across every scope (live, sync, batch, final pass) of the conversation."""

    id: str  # stable within the conversation: 'v0', 'v1', ...
    segment_ids: List[str]
    speech_seconds: float = 0.0
    speaker_id: Optional[int] = None
    speaker_id_scope: Optional[str] = None
    candidates: List[SpeakerCandidate] = []  # ranked, most probable first

    @property
    def best(self) -> Optional[SpeakerCandidate]:
        return self.candidates[0] if self.candidates else None


class ClusterSimilarity(BaseModel):
    a: str
    b: str
    similarity: float = Field(ge=-1.0, le=1.0)


class EvidenceSegment(BaseModel):
    """Receipt keys only; no transcript or audio is duplicated into evidence."""

    id: str
    speaker_id: Optional[int] = None
    speaker_id_scope: Optional[str] = None


class SpeakerEvidence(BaseModel):
    version: Literal[1] = 1
    status: EvidenceStatus
    policy_version: str
    participant_count_hint: Optional[int] = Field(default=None, ge=1, le=256)
    owner_anchor: Optional[Literal['voiceprint', 'near_field', 'channel', 'none']] = None
    clusters: List[VoiceCluster] = []
    similarities: List[ClusterSimilarity] = []  # only pairs worth showing (above a policy floor)
    segments: List[EvidenceSegment] = []
    abstentions: List[str] = []  # truthful reasons, e.g. 'batch_boundary', 'unaligned_audio'
