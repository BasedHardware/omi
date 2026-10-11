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
import heapq
import math
import time
from dataclasses import dataclass, field
from typing import Callable, Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

import config.speaker_match_scores as match_scores

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage

from utils.stt.speaker_identity import OMI_SPEAKER_ID_SENTINEL
from utils.stt.speaker_match import (
    SPEAKER_MATCH_MARGIN as SPEAKER_MATCH_MARGIN,
    SPEAKER_MATCH_MIN_EVIDENCE_SECONDS,
    arbitrate_owner_matches,
    select_speaker_match,
)

RESOLUTION_VERSION = 2

AHC_THRESHOLD = float(os.getenv('CONVERSATION_SPEAKER_AHC_THRESHOLD', '0.70'))
ANCHOR_SECONDS = float(os.getenv('CONVERSATION_SPEAKER_ANCHOR_SECONDS', '30'))
ABSORB_DISTANCE = float(os.getenv('CONVERSATION_SPEAKER_ABSORB_DISTANCE', '0.60'))
# A voice counts as a participant once it has spoken this long.
SIGNIFICANT_SECONDS = float(os.getenv('CONVERSATION_SPEAKER_SIGNIFICANT_SECONDS', '10'))
# Shorter segments are too noisy to embed; they inherit a voice instead.
MIN_EMBED_SECONDS = 1.0
# A voice's pooled centroid against an enrolled voiceprint.
VOICE_MATCH_THRESHOLD = float(os.getenv('CONVERSATION_SPEAKER_VOICE_MATCH_THRESHOLD', '0.50'))

OWNER_IDENTITY = 'user'


@dataclass(frozen=True)
class Identity:
    """Who a voice is: owner, person, or (anonymous_key) an unlabeled distinct voice."""

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
    contradicted_segment_ids: Set[str] = field(default_factory=set)
    match_scores: List[dict] = field(default_factory=list)
    voice_identity_statuses: Dict[int, str] = field(default_factory=dict)
    """Evidence states for automatic voices only; manual receipts remain authoritative."""
    owner_voiceprint_available: bool = False
    """Whether this pass's validated roster included the owner for identity comparison."""


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


# Cached historical matching uses the exact normalization and distance policy.
unit_voice_vector = _unit_vector
voice_cosine_distance = _cosine


class _Cluster:
    def __init__(self, members: List[int]):
        self.members = members  # indices into the unit list

    def extend(self, other: '_Cluster') -> None:
        self.members.extend(other.members)


def _constrained_clusters(
    indices: List[int],
    vectors: Mapping[int, np.ndarray],
    compatible: Callable[[_Cluster, _Cluster], bool],
    threshold: Callable[[_Cluster, _Cluster], float],
    deadline: float,
) -> List[_Cluster]:
    """Average linkage with transitive constraints; capped by the caller before entry.

    Lance-Williams updates keep pair work quadratic. Forbidden pairs never enter
    the heap; a new cluster is compatible only if every original constraint holds.
    """
    active = {i: _Cluster([i]) for i in indices}
    sizes = {i: 1 for i in indices}
    distances = {}
    heap = []
    for offset, a in enumerate(indices):
        if time.monotonic() >= deadline:
            raise TimeoutError('grouping budget')
        for b in indices[offset + 1 :]:
            distance = _cosine(vectors[a], vectors[b])
            distances[a, b] = distance
            if compatible(active[a], active[b]) and distance <= threshold(active[a], active[b]):
                heapq.heappush(heap, (distance, a, b))
    fresh = max(indices, default=-1) + 1
    while heap:
        if time.monotonic() >= deadline:
            raise TimeoutError('grouping budget')
        distance, a, b = heapq.heappop(heap)
        if a not in active or b not in active:
            continue
        merged = _Cluster(active[a].members + active[b].members)
        for c in list(active):
            if c in (a, b):
                continue
            ac = distances[tuple(sorted((a, c)))]
            bc = distances[tuple(sorted((b, c)))]
            updated = (sizes[a] * ac + sizes[b] * bc) / (sizes[a] + sizes[b])
            distances[c, fresh] = updated
            if compatible(active[c], merged) and updated <= threshold(active[c], merged):
                heapq.heappush(heap, (updated, c, fresh))
        active[fresh] = merged
        sizes[fresh] = sizes[a] + sizes[b]
        del active[a], active[b]
        fresh += 1
    return list(active.values())


def resolve_conversation_speakers(
    segments: Sequence[Any],
    embeddings: Mapping[str, Any],
    *,
    manual_speakers: Optional[Mapping[int, Identity]] = None,
    voiceprints: Optional[Mapping[str, Any]] = None,
    abstained_segment_ids: Optional[Set[str]] = None,
    embedding_seconds: Optional[Mapping[str, float]] = None,
    grouping: str = 'incumbent',
    provider_keys: Optional[Mapping[str, Tuple[str, int]]] = None,
    cross_scope_threshold: float = 0.60,
    grouping_deadline: float = float('inf'),
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
    if grouping not in ('incumbent', 'provider_strict', 'provider_cannot_link', 'owner_link'):
        raise ValueError('unknown grouping')
    if grouping != 'incumbent':
        if len(segments) > 256 or not provider_keys:
            raise ValueError('grouping input limit or missing provenance')
        if not 0 < cross_scope_threshold <= AHC_THRESHOLD:
            raise ValueError('invalid cross-scope threshold')
    manual_speakers = dict(manual_speakers or {})
    all_eligible = [
        s
        for s in segments
        if _seg(s, 'id')
        and isinstance(sid := _seg(s, 'speaker_id'), (int, str))
        and str(sid).isdigit()
        and int(sid) != OMI_SPEAKER_ID_SENTINEL
    ]
    abstained = abstained_segment_ids or set()
    eligible = [s for s in all_eligible if _seg(s, 'id') not in abstained]
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
    unit_segments: List[List[Any]] = []
    unit_identity: Dict[int, Identity] = {}
    index_by_key: Dict[Tuple[str, str], int] = {}

    def unit_for(key: Tuple[str, str], identity: Optional[Identity]) -> int:
        if key not in index_by_key:
            index_by_key[key] = len(unit_segments)
            unit_segments.append([])
            if identity is not None:
                unit_identity[index_by_key[key]] = identity
        return index_by_key[key]

    for segment in eligible:
        identity = manual_speakers.get(int(_seg(segment, 'speaker_id')))
        if identity is not None:
            unit_segments[unit_for(('manual', identity.token), identity)].append(segment)
        elif _seg(segment, 'id') in vectors:
            if grouping != 'incumbent' and _seg(segment, 'id') not in (provider_keys or {}):
                raise ValueError('missing provider provenance')
            if grouping in ('provider_strict', 'owner_link'):
                key = ('provider', repr((provider_keys or {})[_seg(segment, 'id')]))
            else:
                key = ('segment', _seg(segment, 'id'))
            unit_segments[unit_for(key, None)].append(segment)

    unit_vector: Dict[int, np.ndarray] = {}
    for index, members in enumerate(unit_segments):
        embedded = [vectors[_seg(s, 'id')] for s in members if _seg(s, 'id') in vectors]
        pooled = _unit_vector(np.mean(embedded, axis=0)) if embedded else None
        if pooled is not None:
            unit_vector[index] = pooled

    def identities_of(cluster: _Cluster) -> Set[str]:
        return {unit_identity[i].token for i in cluster.members if i in unit_identity}

    def compatible(a: _Cluster, b: _Cluster) -> bool:
        ids_a, ids_b = identities_of(a), identities_of(b)
        if ids_a and ids_b and ids_a != ids_b:
            return False
        if grouping == 'incumbent' or (ids_a and ids_a == ids_b):
            return True  # Explicit manual must-link outranks the provider prior.
        scopes = {}
        for i in a.members + b.members:
            for segment in unit_segments[i]:
                key = (provider_keys or {}).get(_seg(segment, 'id'))
                if key is None:
                    continue  # Manual units without capture evidence remain authoritative.
                scope, speaker = key
                if scope in scopes and scopes[scope] != speaker:
                    return False
                scopes[scope] = speaker
        return True

    def merge_threshold(a: _Cluster, b: _Cluster) -> float:
        scopes = {
            (provider_keys or {}).get(_seg(s, 'id'), ('', -1))[0]
            for i in a.members + b.members
            for s in unit_segments[i]
        }
        return cross_scope_threshold if grouping == 'provider_cannot_link' and len(scopes) > 1 else AHC_THRESHOLD

    embedded_units = sorted(unit_vector)
    clusters: List[_Cluster] = []
    if grouping != 'incumbent':
        clusters = _constrained_clusters(
            embedded_units,
            unit_vector,
            compatible,
            merge_threshold,
            grouping_deadline,
        )
    elif len(embedded_units) == 1:
        clusters.append(_Cluster([embedded_units[0]]))
    elif embedded_units:
        tree = linkage(np.vstack([unit_vector[i] for i in embedded_units]), method='average', metric='cosine')
        labels = fcluster(tree, t=AHC_THRESHOLD, criterion='distance')
        grouped: Dict[int, List[int]] = {}
        for unit, label in zip(embedded_units, labels):
            grouped.setdefault(int(label), []).append(unit)
        clusters.extend(_Cluster(members) for members in grouped.values())
    # A labeled identity with no embeddable audio is still its own voice.
    clusters.extend(_Cluster([i]) for i in range(len(unit_segments)) if i not in unit_vector)

    def talk(cluster: _Cluster) -> float:
        return sum(_duration(s) for i in cluster.members for s in unit_segments[i])

    def centroid(cluster: _Cluster) -> Optional[np.ndarray]:
        weighted = [unit_vector[i] * max(talk(_Cluster([i])), 1e-3) for i in cluster.members if i in unit_vector]
        return _unit_vector(np.sum(weighted, axis=0)) if weighted else None

    # Cannot-link: split any cluster holding two labeled identities around them.
    split: List[_Cluster] = []
    for cluster in clusters:
        seeds = [i for i in cluster.members if i in unit_identity]
        if len(seeds) <= 1:
            split.append(cluster)
            continue
        parts = {seed: _Cluster([seed]) for seed in seeds}
        for i in cluster.members:
            if i in parts:
                continue
            target = seeds[0]
            anchored = [seed for seed in seeds if seed in unit_vector]
            if i in unit_vector and anchored:
                member_vector = unit_vector[i]
                target = min((_cosine(member_vector, unit_vector[seed]), seed) for seed in anchored)[1]
            parts[target].members.append(i)
        split.extend(parts.values())
    clusters = split

    # Absorb short-clip fragments into the anchor voice they sit next to.
    anchor_centroids: Dict[int, np.ndarray] = {}
    anchors: List[_Cluster] = []
    for cluster in clusters:
        anchor_vector = centroid(cluster) if talk(cluster) >= ANCHOR_SECONDS else None
        if anchor_vector is not None:
            anchors.append(cluster)
            anchor_centroids[id(cluster)] = anchor_vector
    if anchors:
        for cluster in sorted([c for c in clusters if id(c) not in anchor_centroids], key=talk):
            fragment = centroid(cluster)
            if fragment is None:
                continue
            candidates = [a for a in anchors if compatible(a, cluster)]
            if not candidates:
                continue
            distance, position = min((_cosine(fragment, anchor_centroids[id(a)]), k) for k, a in enumerate(candidates))
            nearest = candidates[position]
            limit = (
                ABSORB_DISTANCE if grouping == 'incumbent' else min(ABSORB_DISTANCE, merge_threshold(nearest, cluster))
            )
            if distance < limit:
                nearest.extend(cluster)
                cluster.members = []
        clusters = [c for c in clusters if c.members]

    # Identify voices jointly before any identity-based merging. Sharing the
    # owner voiceprint is not evidence that two acoustically distinct voices are
    # one person, especially when it is the only enrolled print.
    prints = {key: v for key, v in ((k, _unit_vector(p)) for k, p in (voiceprints or {}).items()) if v is not None}
    if grouping == 'owner_link':
        owner_clusters = []
        for cluster in clusters:
            if time.monotonic() >= grouping_deadline:
                raise TimeoutError('grouping budget')
            evidence_ids = [
                _seg(s, 'id') for i in cluster.members for s in unit_segments[i] if _seg(s, 'id') in vectors
            ]
            evidence = (
                sum((embedding_seconds or {}).get(sid, 0.0) for sid in evidence_ids)
                if embedding_seconds is not None
                else sum(_duration(s) for i in cluster.members for s in unit_segments[i] if _seg(s, 'id') in vectors)
            )
            vector = centroid(cluster)
            if identities_of(cluster) or evidence < SPEAKER_MATCH_MIN_EVIDENCE_SECONDS or vector is None:
                continue
            decision = select_speaker_match(
                {key: _cosine(vector, p) for key, p in prints.items()}, threshold=VOICE_MATCH_THRESHOLD
            )
            if decision.person_id == OWNER_IDENTITY:
                target = next((c for c in owner_clusters if compatible(c, cluster)), None)
                if target is not None:
                    target.extend(cluster)
                    cluster.members = []
                else:
                    owner_clusters.append(cluster)
        clusters = [c for c in clusters if c.members]
    voice_identity: Dict[int, Identity] = {}
    distances = {}
    decisions = {}
    score_seconds: Dict[int, Optional[float]] = {}
    for index, cluster in enumerate(clusters):
        evidence_ids = [_seg(s, 'id') for i in cluster.members for s in unit_segments[i] if _seg(s, 'id') in vectors]
        try:
            if embedding_seconds is not None and all(sid in embedding_seconds for sid in evidence_ids):
                seconds = [float(embedding_seconds[sid]) for sid in evidence_ids]
                if any(not np.isfinite(value) or value < 0 for value in seconds):
                    raise ValueError('Invalid embedded audio duration')
                score_seconds[index] = sum(seconds)
            else:
                score_seconds[index] = None
        except Exception:
            score_seconds[index] = None
            match_scores.record_failure(None, reason='malformed_doc')
        if identities_of(cluster):
            continue
        evidence = (
            (score_seconds[index] or 0.0)
            if embedding_seconds is not None
            else sum(_duration(s) for i in cluster.members for s in unit_segments[i] if _seg(s, 'id') in vectors)
        )
        vector = centroid(cluster)
        if vector is None or not prints or evidence < SPEAKER_MATCH_MIN_EVIDENCE_SECONDS:
            continue
        distances[index] = {key: _cosine(vector, p) for key, p in prints.items()}
        decisions[index] = select_speaker_match(distances[index], threshold=VOICE_MATCH_THRESHOLD)
    decisions = arbitrate_owner_matches(
        distances,
        decisions,
        owner_reserved=any(OWNER_IDENTITY in identities_of(cluster) for cluster in clusters),
    )
    for index, decision in decisions.items():
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
    score_members = {index: [index] for index in range(len(clusters))}
    for index in range(len(clusters)):
        token = cluster_token(index)
        if token is None:
            keep.append(index)
        elif token in merged and compatible(clusters[merged[token]], clusters[index]):
            clusters[merged[token]].extend(clusters[index])
            score_members[merged[token]].extend(score_members[index])
        else:
            merged[token] = index
            keep.append(index)
    # A manual label outranks the voiceprint once both sit on one voice.
    final_identity = {
        pos: voice_identity[index]
        for pos, index in enumerate(keep)
        if index in voice_identity and not identities_of(clusters[index])
    }
    final_status = {
        pos: ('unknown' if index not in decisions else 'ambiguous' if decisions[index].owner_contended else 'no_match')
        for pos, index in enumerate(keep)
        if not identities_of(clusters[index]) and index not in voice_identity
    }
    clusters = [clusters[index] for index in keep]

    # Assign every eligible segment to a cluster.
    cluster_of_segment: Dict[str, int] = {}
    for position, cluster in enumerate(clusters):
        for i in cluster.members:
            for segment in unit_segments[i]:
                cluster_of_segment[_seg(segment, 'id')] = position

    by_old_id: Dict[Tuple[str, int], Dict[int, float]] = {}
    contradicted = set()

    def capture_key(segment):
        if grouping != 'incumbent':
            return (provider_keys or {}).get(_seg(segment, 'id'), ('missing:' + _seg(segment, 'id'), -1))
        return (_seg(segment, 'speaker_id_scope') or '', int(_seg(segment, 'speaker_id')))

    for segment in eligible:
        position = cluster_of_segment.get(_seg(segment, 'id'))
        if position is not None:
            votes = by_old_id.setdefault(capture_key(segment), {})
            votes[position] = votes.get(position, 0.0) + max(_duration(segment), 1e-3)
    for segment in eligible:
        segment_id = _seg(segment, 'id')
        if segment_id in cluster_of_segment:
            continue
        votes = by_old_id.get(capture_key(segment))
        if votes:
            if len(votes) == 1:
                cluster_of_segment[segment_id] = next(iter(votes))
            else:
                # Acoustic contradiction within this provider voice: no majority
                # can establish which person uttered an unembedded short reply.
                contradicted.add(segment_id)
        elif _duration(segment) < MIN_EMBED_SECONDS and not _seg(segment, 'is_user', False):
            # A distinct provider voice has no compatible acoustic vote. Temporal
            # proximity cannot promote it to its neighbour's owner/person identity.
            # Missing votes do not contradict an independently accepted owner.
            contradicted.add(segment_id)
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

    all_old_ids = {
        int(sid) for s in segments if isinstance(sid := _seg(s, 'speaker_id'), (int, str)) and str(sid).isdigit()
    }
    reserved = set(all_old_ids) | set(manual_speakers) | {OMI_SPEAKER_ID_SENTINEL}
    next_fresh = max(reserved) + 1
    taken: Set[int] = {
        int(_seg(s, 'speaker_id'))
        for s in all_eligible
        if _seg(s, 'id') in abstained and int(_seg(s, 'speaker_id')) not in manual_speakers
    }
    manual_keys_by_token: Dict[str, List[int]] = {}
    for key, identity in manual_speakers.items():
        manual_keys_by_token.setdefault(identity.token, []).append(key)

    def first_start(position: int) -> float:
        return min(float(_seg(s, 'start', 0.0) or 0.0) for s in members_of[position])

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
    score_rows = []
    try:
        if match_scores.enabled():
            for position, root in enumerate(keep):
                parts = [i for i in score_members[root] if i in decisions]
                if position not in new_id_of or not parts:
                    continue
                combined_distances = {
                    pid: min(distances[i][pid] for i in parts if pid in distances[i])
                    for pid in {pid for i in parts for pid in distances[i]}
                }
                representative = root if root in decisions else parts[0]
                known_seconds = [seconds for i in score_members[root] if (seconds := score_seconds[i]) is not None]
                combined_seconds = sum(known_seconds) if len(known_seconds) == len(score_members[root]) else None
                row = match_scores.summarize(
                    new_id_of[position],
                    combined_distances,
                    decisions[representative],
                    combined_seconds,
                    'resolution',
                    threshold=VOICE_MATCH_THRESHOLD,
                    margin_threshold=SPEAKER_MATCH_MARGIN,
                )
                row['merged_cluster_count'] = len(score_members[root])
                row['scored_cluster_count'] = len(parts)
                row['distance_aggregation'] = 'min_constituent_v1'
                row['margin_aggregation'] = 'representative_v1'
                score_rows.append(row)
            score_rows = match_scores.merge(None, score_rows)
    except Exception:
        match_scores.record_failure(None)
    return SpeakerResolution(
        owner_voiceprint_available=OWNER_IDENTITY in prints,
        contradicted_segment_ids=contradicted,
        speaker_ids=speaker_ids,
        significant_speaker_ids=significant,
        voice_identities={
            new_id_of[position]: identity for position, identity in final_identity.items() if position in new_id_of
        },
        voice_identity_statuses={
            new_id_of[position]: status for position, status in final_status.items() if position in new_id_of
        },
        match_scores=score_rows,
        embedded_segments=len(vectors),
        input_speaker_ids=len({int(_seg(s, 'speaker_id')) for s in all_eligible}),
        coverage=_coverage(all_eligible, vectors, manual_speakers, abstained),
        stats={
            'voices': len(members_of),
            'eligible_segments': len(eligible),
            'owner_contended': sum(decision.owner_contended for decision in decisions.values()),
        },
    )


def _coverage(
    eligible: Sequence[Any],
    vectors: Mapping[str, Any],
    manual_speakers: Mapping[int, Identity],
    abstained: Set[str],
) -> float:
    # Finite speech duration still counts when its text window cannot be placed,
    # including negative-start windows. Only nonfinite durations are unusable.
    embeddable = [
        (s, duration) for s in eligible if math.isfinite(duration := _duration(s)) and duration >= MIN_EMBED_SECONDS
    ]
    total = sum(duration for _, duration in embeddable)
    if total <= 0:
        return 1.0
    placed = sum(
        duration
        for s, duration in embeddable
        if _seg(s, 'id') not in abstained
        and (_seg(s, 'id') in vectors or int(_seg(s, 'speaker_id')) in manual_speakers)
    )
    return placed / total


def significant_capture_speaker_ids(segments: Sequence[Any]) -> List[int]:
    """Participant ids when capture's own labels are trusted (one diarization scope)."""
    speech: Dict[int, float] = {}
    for segment in segments:
        sid = _seg(segment, 'speaker_id')
        if not (isinstance(sid, (int, str)) and str(sid).isdigit() and int(sid) != OMI_SPEAKER_ID_SENTINEL):
            continue
        speech[int(sid)] = speech.get(int(sid), 0.0) + _duration(segment)
    return sorted(k for k, seconds in speech.items() if seconds >= SIGNIFICANT_SECONDS)
