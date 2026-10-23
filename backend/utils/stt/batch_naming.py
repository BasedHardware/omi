"""Pure, already-loaded enrollment snapshots for CPU batch projection.

No profile acquisition, owner audio repair, cloud clients or text naming.
A caller must scope a snapshot from authorized data already in memory.
"""

from dataclasses import dataclass, field
from math import isfinite
from typing import Callable, Mapping

from models.diarization import OMI_EMBEDDING_SPACE
from utils.conversations.final_pass_assignment import name_centroids
from utils.stt.conversation_speakers import unit_voice_vector
from utils.stt.voiceprints import usable_person_voiceprint

from utils.stt.voice_centroids import (
    EMBEDDING_MODEL,
    EMBEDDING_REVISION,
    COMMUNITY_MODEL_REVISION as DIARIZER_REVISION,
)


def snapshot_voiceprints(owner_profile, people, *, named_allowed):
    """Apply the same stored-vector/version filters as sync, without any reads."""
    prints = {}
    owner_profile = owner_profile or {}
    owner = unit_voice_vector(owner_profile.get('speaker_embedding'))
    if owner is not None:
        prints['user'] = owner
    if named_allowed is not True:
        return prints
    for person in people or ():
        if person.get('is_dismissed') or person.get('is_deleted') or person.get('revoked_at'):
            continue
        vector = unit_voice_vector(usable_person_voiceprint(person))
        if (
            vector is not None
            and person.get('id')
            and person['id'] != 'user'
            and (owner is None or owner.shape == vector.shape)
        ):
            prints[person['id']] = vector
    return prints


@dataclass(frozen=True)
class NamingSnapshot:
    owner_id: str
    privacy_generation: int
    owner_profile: Mapping = field(default_factory=dict)
    people: tuple = ()
    named_allowed: bool = False
    embedding_space: str = OMI_EMBEDDING_SPACE
    # Trusted canonical receipt, never supplied by GPU output/request metadata.
    manual_receipt: Mapping = field(default_factory=dict)
    # Optional already-read people snapshot fence; caller owns its authority.
    validate: Callable | None = None


def compatible_centroids(diarization):
    provenance = diarization.get('provenance') or {}
    if (
        diarization.get('embedding_space') != OMI_EMBEDDING_SPACE
        or provenance.get('embedding_model') != EMBEDDING_MODEL
        or provenance.get('embedding_revision') != EMBEDDING_REVISION
        or provenance.get('model_revision') != DIARIZER_REVISION
    ):
        return False
    return True


def naming_decisions(diarization, snapshot, *, owner_id, privacy_generation):
    if (
        not isinstance(snapshot, NamingSnapshot)
        or snapshot.owner_id != owner_id
        or snapshot.privacy_generation != privacy_generation
    ):
        return {}
    if snapshot.embedding_space != OMI_EMBEDDING_SPACE or not compatible_centroids(diarization):
        return {}
    from utils.manual_speaker_assignments import manual_owner_reserved

    prints = snapshot_voiceprints(
        snapshot.owner_profile, snapshot.people, named_allowed=snapshot.named_allowed and snapshot.validate is not None
    )
    centroids = {}
    for voice, entry in (diarization.get('centroids') or {}).items():
        seconds = entry.get('evidence_seconds')
        if type(seconds) not in (int, float) or not isfinite(seconds):
            continue
        if unit_voice_vector(entry.get('embedding')) is not None:
            centroids[voice] = entry
    decisions = name_centroids(centroids, prints, owner_reserved=manual_owner_reserved(snapshot.manual_receipt))
    # Distinct diarized voices cannot publish the same person twice. Retain
    # every candidate in ambiguity comparison, then deduplicate accepted people.
    accepted = {}
    from dataclasses import replace

    for voice, decision in sorted(decisions.items(), key=lambda pair: pair[1].best_distance):
        if decision.person_id and decision.person_id in accepted:
            decisions[voice] = replace(decision, person_id=None)
        elif decision.person_id:
            accepted[decision.person_id] = voice
    return decisions
