"""Build ranked conversation evidence and project labels through the manual receipt.

Only this producer decides which acoustic candidates may label a segment. Roster
names remain low-prior hypotheses, including when there is exactly one attendee.
"""

from collections import defaultdict
import heapq
import logging
from math import isfinite
from typing import Any, Mapping, Sequence

import numpy as np

from config.refactor_modes import shadow_or_serve
from database import speaker_evidence as storage
from models.speaker_evidence import (
    OWNER,
    ClusterSimilarity,
    EvidenceSegment,
    SpeakerCandidate,
    SpeakerEvidence,
    VoiceCluster,
)
from utils.manual_speaker_assignments import (
    apply_manual_assignments,
    manual_assignment_decision,
    manual_rejected_speakers,
)
from utils.speakers import policy
from utils.speakers.context import participant_hint, unique_roster
from utils.speakers.refinement import anchor_owner, merge_surplus, unit

# Explicit declaration of the shared parser's derived env contract, so registry
# tooling and operators can enumerate it without adding a second env reader.
_COHORT_ENV = dict(
    mode='SPEAKER_EVIDENCE_MODE',
    percent='SPEAKER_EVIDENCE_MODE_SERVE_PERCENT',
    digests='SPEAKER_EVIDENCE_MODE_SERVE_UID_SHA256S',
)
logger = logging.getLogger(__name__)
FLAG = _COHORT_ENV['mode']
assert _COHORT_ENV['percent'] == f'{FLAG}_SERVE_PERCENT'
assert _COHORT_ENV['digests'] == f'{FLAG}_SERVE_UID_SHA256S'
MAX_VOICE_CANDIDATES = 16
MAX_ROSTER_CANDIDATES = 32
MAX_SIMILARITIES = 256


def get_evidence(uid: str, conversation_id: str) -> SpeakerEvidence | None:
    if not shadow_or_serve(FLAG):
        return None
    try:
        return storage.get_evidence(uid, conversation_id)
    except Exception as error:
        # Corrupt evidence cannot prevent notes using the transcript. Storage's
        # strict read boundary still records malformed payload diagnostics.
        from utils.observability.fallback import record_fallback

        logger.warning('event=speaker_evidence_read outcome=error exception_type=%s', type(error).__name__)
        record_fallback(
            component='other',
            from_mode='speaker_evidence',
            to_mode='existing_labels',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        return None


def _get(value: Any, key: str, default: Any = None) -> Any:
    return value.get(key, default) if isinstance(value, Mapping) else getattr(value, key, default)


def _person(person_id: str) -> str:
    return OWNER if person_id == 'user' else person_id


def roster_candidates(context: Any) -> list[dict]:
    """Only explicit attendee names; never infer an identity from a meeting title."""
    attendees = _get(context, 'participants', []) or _get(context, 'attendees', []) or []
    return [
        {
            'name': _get(p, 'name') or _get(p, 'display_name'),
            'email': _get(p, 'email'),
            'person_id': _get(p, 'person_id'),
        }
        for p in attendees
    ]


def _receipt_scope(segment: Any, scope: str | None) -> str | None:
    """A retained provider scope keeps carried receipts valid after resolution."""
    provider = _get(segment, 'provider_speaker') or {}
    original = _get(provider, 'scope')
    if (
        (scope or '').startswith(('conversation:', 'legacy-conversation:'))
        and isinstance(original, str)
        and original
        and str(_get(provider, 'id', -1)).isdigit()
    ):
        return original
    return scope


def _manual_decision(current: Mapping, origin: Mapping, receipt: Mapping, rejected: dict) -> dict | None:
    # Current and preserved provider scopes are both proven keys for this stable
    # segment ID. Generation ordering still comes from the shared receipt policy.
    decisions = [
        decision
        for row in (current, origin)
        if (decision := manual_assignment_decision(row, receipt, rejected)) is not None
    ]
    return max(decisions, key=lambda d: d.get('generation', 0), default=None)


def cluster_key(segment: Any, resolution: Any, channel_ids: set[str]) -> tuple:
    """The producer and count observer share the same voice/channel partition."""
    sid = _get(segment, 'id')
    resolved = resolution.speaker_ids.get(sid) if resolution else None
    key = (
        ('resolved', resolved)
        if resolved is not None
        else (_get(segment, 'speaker_id_scope'), _get(segment, 'speaker_id'))
    )
    return (*key, sid in channel_ids)


def build_evidence(
    segments: Sequence[Any],
    resolution: Any = None,
    *,
    receipt: Mapping | None = None,
    roster: Sequence[Mapping] = (),
    abstentions: Sequence[str] = (),
    channel_ids: Sequence[str] = (),
    energies: Mapping[str, float] | None = None,
    near_field_allowed: bool = False,
) -> SpeakerEvidence:
    receipt = receipt or {}
    roster = unique_roster(roster)
    hint = participant_hint(roster, segments)
    channel_set = set(channel_ids)
    groups: dict[tuple, list] = defaultdict(list)
    refs = []
    for segment in segments:
        sid = _get(segment, 'id')
        speaker = _get(segment, 'speaker_id')
        if not sid or speaker == 99:
            continue
        scope = _get(segment, 'speaker_id_scope')
        key = cluster_key(segment, resolution, channel_set)
        groups[key].append(segment)
        refs.append(EvidenceSegment(id=sid, speaker_id=speaker, speaker_id_scope=_receipt_scope(segment, scope)))
    references = {ref.id: ref.model_dump() for ref in refs}
    rejected = manual_rejected_speakers(receipt)
    clusters, centroids = [], {}
    reasons = set(abstentions)
    for key, members in groups.items():
        voice = key[1] if key[0] == 'resolved' else None
        speaker_id = voice if voice is not None else _get(members[0], 'speaker_id')
        scopes = {_get(s, 'speaker_id_scope') for s in members}
        scope = next(iter(scopes)) if len(scopes) == 1 else None
        distances = resolution.voice_distances.get(voice, {}) if resolution else {}
        identity = resolution.voice_identities.get(voice) if resolution else None
        accepted = OWNER if identity and identity.is_user else identity.person_id if identity else None
        candidates = []
        # Owner is always present, even without an enrolled print or usable audio.
        ranked = sorted(((pid, d) for pid, d in distances.items() if isfinite(d)), key=lambda x: x[1])
        # Finalize historically rejected enrolled people in the 0.50-0.65 gap
        # after live accepted them. Reuse live's point and runner-up margin.
        if ranked and not accepted:
            pid, distance = ranked[0]
            runner = ranked[1][1] if len(ranked) > 1 else float('inf')
            if pid != 'user' and policy.ENROLLED_PERSON.accepts(distance) and runner - distance >= policy.MATCH_MARGIN:
                accepted = pid
        ranked = ranked[:MAX_VOICE_CANDIDATES]
        if not any(pid == 'user' for pid, _ in ranked):
            ranked.append(('user', distances.get('user', float('inf'))))
        for pid, distance in ranked:
            value = policy.probability(distance)
            candidates.append(
                SpeakerCandidate(
                    person_id=_person(pid),
                    probability=value,
                    band=policy.band(value),
                    source='voice',
                    label_eligible=_person(pid) == accepted,
                )
            )
        for index, person in enumerate(roster[:MAX_ROSTER_CANDIDATES]):
            name = person.get('name')
            if name:
                candidates.append(
                    SpeakerCandidate(
                        person_id=person.get('person_id') or f'roster:{index}',
                        name=name,
                        probability=policy.ROSTER_PRIOR,
                        band='unknown',
                        source='roster',
                    )
                )
        # Excerpt manual labels appear as evidence but never label their whole cluster.
        for segment in members:
            metadata = {
                'id': _get(segment, 'id'),
                'speaker_id': speaker_id,
                'speaker_id_scope': scope,
            }
            decision = _manual_decision(metadata, references[metadata['id']], receipt, rejected)
            if decision and (decision.get('is_user') or decision.get('person_id')):
                pid = OWNER if decision.get('is_user') else decision['person_id']
                if not any(c.source == 'manual' and c.person_id == pid for c in candidates):
                    candidates.append(SpeakerCandidate(person_id=pid, probability=1, band='confident', source='manual'))
        candidates.sort(key=lambda c: (-c.probability, c.source, c.person_id))
        cluster = VoiceCluster(
            id=f'v{len(clusters)}',
            segment_ids=[_get(s, 'id') for s in members],
            speaker_id=speaker_id,
            speaker_id_scope=scope,
            speech_seconds=sum(max(0, _get(s, 'end', 0) - _get(s, 'start', 0)) for s in members),
            candidates=candidates,
        )
        clusters.append(cluster)
        centroid = resolution.voice_centroids.get(voice) if resolution else None
        if centroid is not None:
            normalized = unit(centroid)
            if normalized is not None:
                centroids[cluster.id] = normalized
        if voice is None:
            reasons.add(
                'no_compatible_centroid'
                if any((_get(s, 'speaker_id_scope') or '').startswith('final:batch:') for s in members)
                else 'no_voice_evidence'
            )
        elif not accepted and not any(c.source == 'manual' for c in candidates):
            reasons.add(resolution.voice_identity_statuses.get(voice, 'insufficient_evidence'))
    clusters, centroids, count_abstained = merge_surplus(clusters, centroids, hint, channel_ids=channel_ids)
    if count_abstained:
        reasons.add('participant_count_unresolved')
    owner_anchor = anchor_owner(
        clusters,
        channel_ids=channel_ids,
        energies=energies,
        near_field_allowed=near_field_allowed and bool(resolution) and resolution.coverage >= 0.9,
    )
    if owner_anchor == 'none':
        reasons.add('owner_unanchored')
    similarities = []
    for i, a in enumerate(clusters):
        for b in clusters[i + 1 :]:
            a_vector, b_vector = centroids.get(a.id), centroids.get(b.id)
            if a_vector is not None and b_vector is not None and a_vector.shape == b_vector.shape:
                similarity = float(np.dot(a_vector, b_vector))
                if isfinite(similarity) and similarity >= policy.SIMILARITY_FLOOR:
                    pair = (max(-1.0, min(1.0, similarity)), a.id, b.id)
                    if len(similarities) < MAX_SIMILARITIES:
                        heapq.heappush(similarities, pair)
                    elif pair > similarities[0]:
                        heapq.heapreplace(similarities, pair)
    similarities = [ClusterSimilarity(a=a, b=b, similarity=value) for value, a, b in sorted(similarities, reverse=True)]
    status = 'resolved' if resolution and resolution.coverage >= 0.9 else 'partial' if resolution else 'unavailable'
    if owner_anchor == 'channel' and status == 'unavailable':
        status = 'partial'
    return SpeakerEvidence(
        status=status,
        policy_version=policy.POLICY_VERSION,
        participant_count_hint=hint,
        owner_anchor=owner_anchor,
        clusters=clusters,
        segments=refs,
        similarities=similarities[:MAX_SIMILARITIES],
        abstentions=sorted(reasons),
    )


def project_labels(evidence: SpeakerEvidence, receipt: Mapping) -> dict[str, tuple[bool, str | None]]:
    """Joint acoustic decisions, then the same generation/scoping rules as storage."""
    metadata = {s.id: s.model_dump() for s in evidence.segments}
    rejected = manual_rejected_speakers(receipt)
    projected = {}
    for cluster in evidence.clusters:
        accepted = next(
            (c for c in cluster.candidates if c.label_eligible and c.source in ('voice', 'channel', 'near_field')), None
        )
        for sid in cluster.segment_ids:
            current = {'id': sid, 'speaker_id': cluster.speaker_id, 'speaker_id_scope': cluster.speaker_id_scope}
            decision = _manual_decision(current, metadata.get(sid, current), receipt, rejected)
            # Abstention is no new decision: preserve existing labels and status.
            if accepted is None and decision is None:
                continue
            automatic = {
                **current,
                'is_user': bool(accepted and accepted.person_id == OWNER),
                'person_id': accepted.person_id if accepted and accepted.person_id != OWNER else None,
            }
            overlay = {'segments': {sid: decision}} if decision is not None else {}
            labeled = apply_manual_assignments([automatic], overlay)[0]
            projected[sid] = (bool(labeled.get('is_user')), labeled.get('person_id'))
    return projected
