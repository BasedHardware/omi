"""Conversation-wide speaker resolution: one diarization over the whole conversation.

Capture diarizes piecewise. Live labels restart on every reconnect or provider
failover, and sync labels restart on every uploaded VAD chunk (<=300s), so the
allocator in speaker_identity.py hands one person a new ``speaker_id`` per piece.
A 3.6h pendant dinner measured 1874 speaker_ids for about five voices.

This module re-diarizes the finished conversation from per-segment voice
embeddings, so ``speaker_id`` means one voice for the whole conversation. It is
pure: no network, storage, or Firestore. The caller supplies the segments, the
embeddings it could compute, the manual receipt keys, and enrolled voiceprints.

Operating points were measured on real pendant audio (far-field, noisy
restaurants) embedded with the production wespeaker-resnet34 model, clips cut
from the stored chunks exactly as speaker_resolution.py cuts them (transcription
of the clips confirmed the alignment). Owner purity was scored with the owner's
enrolled voiceprint: across AHC 0.65-0.75 and absorb 0.50-0.65, no confident
owner clip left the owner's voice and at most 5 of about 1000 confident
non-owner clips joined it; at 0.80 the owner absorbed 106. At 0.70/0.60 the
1874-id dinner resolved to six participants and a two-person call with desktop
mic/system ground truth to exactly two. The Parakeet server's per-chunk 0.55 cut
(tuned on VoxConverse broadcast audio) is not what fragments these transcripts;
chunk-local numbering is.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage

from utils.stt.speaker_identity import OMI_SPEAKER_ID_SENTINEL
from utils.stt.speaker_match import SPEAKER_MATCH_MIN_EVIDENCE_SECONDS, select_speaker_match

RESOLUTION_VERSION = 1

# Average-linkage cut on cosine distance between segment embeddings.
AHC_THRESHOLD = float(os.getenv('CONVERSATION_SPEAKER_AHC_THRESHOLD', '0.70'))
# Clusters with at least this much speech anchor the conversation's voices.
ANCHOR_SECONDS = float(os.getenv('CONVERSATION_SPEAKER_ANCHOR_SECONDS', '30'))
# Short-clip clusters whose centroid is this close to an anchor are fragments of
# that voice, not new people.
ABSORB_DISTANCE = float(os.getenv('CONVERSATION_SPEAKER_ABSORB_DISTANCE', '0.60'))
# A voice counts as a participant once it has spoken this long.
SIGNIFICANT_SECONDS = float(os.getenv('CONVERSATION_SPEAKER_SIGNIFICANT_SECONDS', '10'))
# Shorter segments are too noisy to embed; they inherit a voice instead.
MIN_EMBED_SECONDS = 1.0
# A voice's pooled centroid against an enrolled voiceprint. Pooling pulls the
# owner's voice far closer than one clip (0.24-0.33 on three measured
# conversations) while other voices stayed at or above 0.63, where the per-clip
# enrollment threshold (0.65) named a companion the owner and merged them.
VOICE_MATCH_THRESHOLD = float(os.getenv('CONVERSATION_SPEAKER_VOICE_MATCH_THRESHOLD', '0.50'))

OWNER_IDENTITY = 'user'


@dataclass(frozen=True)
class Identity:
    """Who a voice is: the owner, a person, or (``anonymous_key``) a voice a
    receipt marked as neither, which stays distinct from every other voice."""

    is_user: bool
    person_id: Optional[str]
    anonymous_key: Optional[int] = None

    @property
    def token(self) -> str:
        if self.is_user:
            return OWNER_IDENTITY
        if self.person_id:
            return f'person:{self.person_id}'
        return f'anonymous:{self.anonymous_key}'


@dataclass
class SpeakerResolution:
    speaker_ids: Dict[str, int]
    """segment id -> resolved speaker_id, for every segment the resolution covers."""
    significant_speaker_ids: List[int]
    voice_identities: Dict[int, Identity]
    """Identities decided from voiceprints (never covers manually labeled voices)."""
    embedded_segments: int
    input_speaker_ids: int
    coverage: float
    """Share of embeddable speech that voice evidence or a manual label placed."""
    stats: Dict[str, Any] = field(default_factory=dict)


def _seg(segment: Any, name: str, default: Any = None) -> Any:
    if isinstance(segment, Mapping):
        return segment.get(name, default)
    return getattr(segment, name, default)


def _duration(segment: Any) -> float:
    return max(0.0, float(_seg(segment, 'end', 0.0) or 0.0) - float(_seg(segment, 'start', 0.0) or 0.0))


def _unit_vector(vector: Any) -> Optional[np.ndarray]:
    array = np.asarray(vector, dtype=np.float64).reshape(-1)
    if array.size == 0 or not bool(np.all(np.isfinite(array))):
        return None
    norm = float(np.linalg.norm(array))
    return array / norm if norm > 0 else None


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(1.0 - np.dot(a, b))


class _Cluster:
    def __init__(self, members: List[int]):
        self.members = members  # indices into the unit list

    def extend(self, other: '_Cluster') -> None:
        self.members.extend(other.members)


def resolve_conversation_speakers(
    segments: Sequence[Any],
    embeddings: Mapping[str, Any],
    *,
    manual_speakers: Optional[Mapping[int, Identity]] = None,
    voiceprints: Optional[Mapping[str, Any]] = None,
) -> Optional[SpeakerResolution]:
    """Resolve one speaker_id per voice across the whole conversation.

    ``embeddings`` maps segment id -> voice embedding for the segments the caller
    could embed. ``manual_speakers`` is the receipt: speaker ids a person labeled.
    Those ids survive as the ids of their voices (the commit re-applies the
    receipt by id), segments sharing a labeled identity are one voice, and two
    different labeled identities are never merged. ``voiceprints`` maps
    ``'user'`` or a person id to an enrolled embedding.

    Returns None when no segment could be embedded: there is no voice evidence
    to resolve with, and the caller keeps capture's ids.
    """
    manual_speakers = dict(manual_speakers or {})
    eligible = [
        s
        for s in segments
        if _seg(s, 'id') and _seg(s, 'speaker_id') is not None and _seg(s, 'speaker_id') != OMI_SPEAKER_ID_SENTINEL
    ]
    if not eligible:
        return None

    vectors: Dict[str, np.ndarray] = {}
    for segment in eligible:
        raw = embeddings.get(_seg(segment, 'id'))
        if raw is None or _duration(segment) < MIN_EMBED_SECONDS:
            continue
        unit = _unit_vector(raw)
        if unit is not None:
            vectors[_seg(segment, 'id')] = unit
    if not vectors:
        return None

    # Units: a manually labeled identity is one unit (must-link); every other
    # embedded segment is its own unit.
    unit_keys: List[Tuple[str, str]] = []
    unit_segments: List[List[Any]] = []
    unit_identity: List[Optional[Identity]] = []
    index_by_key: Dict[Tuple[str, str], int] = {}

    def unit_for(key: Tuple[str, str], identity: Optional[Identity]) -> int:
        if key not in index_by_key:
            index_by_key[key] = len(unit_keys)
            unit_keys.append(key)
            unit_segments.append([])
            unit_identity.append(identity)
        return index_by_key[key]

    for segment in eligible:
        identity = manual_speakers.get(int(_seg(segment, 'speaker_id')))
        if identity is not None:
            unit_segments[unit_for(('manual', identity.token), identity)].append(segment)
        elif _seg(segment, 'id') in vectors:
            unit_segments[unit_for(('segment', _seg(segment, 'id')), None)].append(segment)

    unit_vectors: List[Optional[np.ndarray]] = []
    for members in unit_segments:
        embedded = [vectors[_seg(s, 'id')] for s in members if _seg(s, 'id') in vectors]
        unit_vectors.append(_unit_vector(np.mean(embedded, axis=0)) if embedded else None)

    embedded_units = [i for i, v in enumerate(unit_vectors) if v is not None]
    clusters: List[_Cluster] = []
    if len(embedded_units) == 1:
        clusters.append(_Cluster([embedded_units[0]]))
    elif embedded_units:
        tree = linkage(np.vstack([unit_vectors[i] for i in embedded_units]), method='average', metric='cosine')
        labels = fcluster(tree, t=AHC_THRESHOLD, criterion='distance')
        grouped: Dict[int, List[int]] = {}
        for unit, label in zip(embedded_units, labels):
            grouped.setdefault(int(label), []).append(unit)
        clusters.extend(_Cluster(members) for members in grouped.values())
    # A labeled identity with no embeddable audio is still its own voice.
    clusters.extend(_Cluster([i]) for i, v in enumerate(unit_vectors) if v is None)

    def identities_of(cluster: _Cluster) -> Set[str]:
        return {unit_identity[i].token for i in cluster.members if unit_identity[i] is not None}

    def talk(cluster: _Cluster) -> float:
        return sum(_duration(s) for i in cluster.members for s in unit_segments[i])

    def centroid(cluster: _Cluster) -> Optional[np.ndarray]:
        weighted = [
            unit_vectors[i] * max(talk(_Cluster([i])), 1e-3) for i in cluster.members if unit_vectors[i] is not None
        ]
        return _unit_vector(np.sum(weighted, axis=0)) if weighted else None

    # Cannot-link: split any cluster holding two labeled identities around them.
    split: List[_Cluster] = []
    for cluster in clusters:
        seeds = [i for i in cluster.members if unit_identity[i] is not None]
        if len(seeds) <= 1:
            split.append(cluster)
            continue
        parts = {seed: _Cluster([seed]) for seed in seeds}
        for i in cluster.members:
            if i in parts:
                continue
            vector = unit_vectors[i]
            anchored = [seed for seed in seeds if unit_vectors[seed] is not None]
            target = (
                min(anchored, key=lambda seed: _cosine(vector, unit_vectors[seed]))
                if vector is not None and anchored
                else seeds[0]
            )
            parts[target].members.append(i)
        split.extend(parts.values())
    clusters = split

    def compatible(a: _Cluster, b: _Cluster) -> bool:
        ids_a, ids_b = identities_of(a), identities_of(b)
        return not ids_a or not ids_b or ids_a == ids_b

    # Absorb short-clip fragments into the anchor voice they sit next to.
    anchors = [c for c in clusters if talk(c) >= ANCHOR_SECONDS and centroid(c) is not None]
    if anchors:
        anchor_centroids = {id(a): centroid(a) for a in anchors}
        for cluster in sorted([c for c in clusters if all(c is not a for a in anchors)], key=talk):
            vector = centroid(cluster)
            if vector is None:
                continue
            candidates = [a for a in anchors if compatible(a, cluster)]
            if not candidates:
                continue
            nearest = min(candidates, key=lambda a: _cosine(vector, anchor_centroids[id(a)]))
            if _cosine(vector, anchor_centroids[id(nearest)]) < ABSORB_DISTANCE:
                nearest.extend(cluster)
                cluster.members = []
        clusters = [c for c in clusters if c.members]

    # Identify voices against enrolled voiceprints, then merge voices that
    # resolve to the same identity: two clusters matching one voiceprint are one
    # person the clustering split.
    prints = {key: v for key, v in ((k, _unit_vector(p)) for k, p in (voiceprints or {}).items()) if v is not None}
    voice_identity: Dict[int, Identity] = {}
    for index, cluster in enumerate(clusters):
        if identities_of(cluster):
            continue
        evidence = sum(_duration(s) for i in cluster.members for s in unit_segments[i] if _seg(s, 'id') in vectors)
        vector = centroid(cluster)
        if vector is None or not prints or evidence < SPEAKER_MATCH_MIN_EVIDENCE_SECONDS:
            continue
        decision = select_speaker_match(
            {key: _cosine(vector, p) for key, p in prints.items()}, threshold=VOICE_MATCH_THRESHOLD
        )
        if decision.accepted:
            matched = decision.person_id
            voice_identity[index] = (
                Identity(is_user=True, person_id=None)
                if matched == OWNER_IDENTITY
                else Identity(is_user=False, person_id=matched)
            )

    def cluster_token(index: int) -> Optional[str]:
        manual = identities_of(clusters[index])
        if manual:
            return next(iter(manual))
        identity = voice_identity.get(index)
        return identity.token if identity else None

    merged: Dict[str, int] = {}
    keep: List[int] = []
    for index in range(len(clusters)):
        token = cluster_token(index)
        if token is None:
            keep.append(index)
        elif token in merged:
            clusters[merged[token]].extend(clusters[index])
        else:
            merged[token] = index
            keep.append(index)
    # A manual label outranks the voiceprint once both sit on one voice.
    final_identity = {
        pos: voice_identity[index]
        for pos, index in enumerate(keep)
        if index in voice_identity and not identities_of(clusters[index])
    }
    clusters = [clusters[index] for index in keep]

    # Assign every eligible segment to a cluster.
    cluster_of_segment: Dict[str, int] = {}
    for position, cluster in enumerate(clusters):
        for i in cluster.members:
            for segment in unit_segments[i]:
                cluster_of_segment[_seg(segment, 'id')] = position

    by_old_id: Dict[int, Dict[int, float]] = {}
    for segment in eligible:
        position = cluster_of_segment.get(_seg(segment, 'id'))
        if position is not None:
            votes = by_old_id.setdefault(int(_seg(segment, 'speaker_id')), {})
            votes[position] = votes.get(position, 0.0) + max(_duration(segment), 1e-3)
    placed = sorted(
        ((float(_seg(s, 'start', 0.0)) + float(_seg(s, 'end', 0.0))) / 2.0, cluster_of_segment[_seg(s, 'id')])
        for s in eligible
        if _seg(s, 'id') in cluster_of_segment
    )
    centers = np.array([center for center, _ in placed])
    for segment in eligible:
        segment_id = _seg(segment, 'id')
        if segment_id in cluster_of_segment:
            continue
        votes = by_old_id.get(int(_seg(segment, 'speaker_id')))
        if votes:
            # Capture's own label is the best evidence for a clip that was not embedded.
            cluster_of_segment[segment_id] = max(votes.items(), key=lambda item: (item[1], -item[0]))[0]
        elif placed and _duration(segment) < MIN_EMBED_SECONDS:
            # Too short to ever embed: the voice speaking around it.
            center = (float(_seg(segment, 'start', 0.0)) + float(_seg(segment, 'end', 0.0))) / 2.0
            cluster_of_segment[segment_id] = placed[int(np.argmin(np.abs(centers - center)))][1]
        # Otherwise it was embeddable but not embedded yet (budget, missing audio):
        # it keeps capture's id rather than borrowing a neighbour's voice.

    # Name each cluster. A labeled voice keeps its receipt key so the commit's
    # receipt re-application still lands on it; otherwise the voice keeps the
    # capture id carrying most of its speech, so re-resolution is stable.
    members_of: Dict[int, List[Any]] = {}
    for segment in eligible:
        position = cluster_of_segment.get(_seg(segment, 'id'))
        if position is not None:
            members_of.setdefault(position, []).append(segment)

    all_old_ids = {int(_seg(s, 'speaker_id')) for s in segments if _seg(s, 'speaker_id') is not None}
    reserved = set(all_old_ids) | set(manual_speakers) | {OMI_SPEAKER_ID_SENTINEL}
    next_fresh = max(reserved) + 1
    taken: Set[int] = set()
    manual_keys_by_token: Dict[str, List[int]] = {}
    for key, identity in manual_speakers.items():
        manual_keys_by_token.setdefault(identity.token, []).append(key)

    def first_start(position: int) -> float:
        return min(float(_seg(s, 'start', 0.0)) for s in members_of[position])

    new_id_of: Dict[int, int] = {}
    for position in sorted(members_of, key=first_start):
        speech_by_old: Dict[int, float] = {}
        for segment in members_of[position]:
            old = int(_seg(segment, 'speaker_id'))
            speech_by_old[old] = speech_by_old.get(old, 0.0) + _duration(segment)
        manual = identities_of(clusters[position])
        if manual:
            keys = [k for k in manual_keys_by_token.get(next(iter(manual)), []) if k in speech_by_old]
            candidates = sorted(keys, key=lambda k: (-speech_by_old[k], k))
        else:
            candidates = sorted(
                (k for k in speech_by_old if k not in manual_speakers), key=lambda k: (-speech_by_old[k], k)
            )
        chosen = next((k for k in candidates if k not in taken), None)
        if chosen is None:
            while next_fresh in reserved or next_fresh in taken:
                next_fresh += 1
            chosen = next_fresh
            next_fresh += 1
        taken.add(chosen)
        new_id_of[position] = chosen

    speaker_ids = {segment_id: new_id_of[position] for segment_id, position in cluster_of_segment.items()}
    significant = sorted(
        new_id_of[position]
        for position, members in members_of.items()
        if sum(_duration(s) for s in members) >= SIGNIFICANT_SECONDS
        or identities_of(clusters[position])
        or position in final_identity
    )
    return SpeakerResolution(
        speaker_ids=speaker_ids,
        significant_speaker_ids=significant,
        voice_identities={
            new_id_of[position]: identity for position, identity in final_identity.items() if position in new_id_of
        },
        embedded_segments=len(vectors),
        input_speaker_ids=len({int(_seg(s, 'speaker_id')) for s in eligible}),
        coverage=_coverage(eligible, vectors, manual_speakers),
        stats={'voices': len(members_of), 'eligible_segments': len(eligible)},
    )


def _coverage(eligible: Sequence[Any], vectors: Mapping[str, Any], manual_speakers: Mapping[int, Identity]) -> float:
    embeddable = [s for s in eligible if _duration(s) >= MIN_EMBED_SECONDS]
    total = sum(_duration(s) for s in embeddable)
    if total <= 0:
        return 1.0
    placed = sum(
        _duration(s) for s in embeddable if _seg(s, 'id') in vectors or int(_seg(s, 'speaker_id')) in manual_speakers
    )
    return placed / total


def significant_capture_speaker_ids(segments: Sequence[Any]) -> List[int]:
    """Participant ids when capture's own labels are trusted (one diarization scope)."""
    speech: Dict[int, float] = {}
    for segment in segments:
        speaker_id = _seg(segment, 'speaker_id')
        if speaker_id is None or speaker_id == OMI_SPEAKER_ID_SENTINEL:
            continue
        speech[int(speaker_id)] = speech.get(int(speaker_id), 0.0) + _duration(segment)
    return sorted(k for k, seconds in speech.items() if seconds >= SIGNIFICANT_SECONDS)
