"""Finalize adapter: record evidence once, compare in shadow, project in cohort."""

from utils.observability.reasons import ReasonFamily, reason_label, RefactorShadowOutcome
from contextvars import ContextVar
from dataclasses import dataclass, field
import logging
from typing import Any

from prometheus_client import Counter

from config.refactor_modes import serving_for, shadow_or_serve, shadow_sampled
from database import speaker_evidence as storage
from utils.speakers.evidence import FLAG, build_evidence, cluster_key, project_labels, roster_candidates
from utils.observability.fallback import record_fallback
from utils.conversations.audio_placement import text_window_refusal
from utils.speakers.context import unique_roster
from utils.speakers.refinement import pcm_energy

logger = logging.getLogger(__name__)
TOTAL = Counter('omi_speaker_evidence_total', 'Speaker evidence production outcomes', ['status', 'outcome'])
AGREEMENT = Counter('omi_speaker_evidence_shadow_agreement_total', 'Label projection comparison', ['outcome'])
OWNER_SHARE = Counter('omi_speaker_evidence_confident_owner_total', 'Conversations with a confident owner', ['present'])
ANCHORS = Counter('omi_speaker_evidence_owner_anchor_total', 'Owner anchor method', ['anchor'])
COUNT_HINTS = Counter('omi_speaker_evidence_count_hint_total', 'Participant count refinement', ['outcome'])
SHADOW_SAMPLE_PERCENT = 5.0


@dataclass
class EvidencePass:
    resolution: Any = None
    reason: str = 'disabled'
    abstentions: set[str] = field(default_factory=set)
    energies: dict[str, float] = field(default_factory=dict)
    channel_ids: list[str] = field(default_factory=list)


_current: ContextVar[EvidencePass | None] = ContextVar('speaker_evidence_pass', default=None)


def begin(conversation=None):
    # Desktop mic labels are channel attribution before acoustic resolution.
    # Never reinterpret an automatic voice or manual label as channel evidence.
    channels = (
        [
            s.id
            for s in conversation.transcript_segments
            if s.is_user and not s.person_id and not s.speaker_match_source and not s.speaker_label_source
        ]
        if conversation is not None and str(getattr(conversation, 'source', '')).split('.')[-1] == 'desktop'
        else []
    )
    return _current.set(EvidencePass(channel_ids=channels))


def capture_energy(segment_id, pcm):
    current = _current.get()
    if current is not None and shadow_or_serve(FLAG) and len(current.energies) < 1500:
        current.energies[segment_id] = pcm_energy(pcm)


def energy_metadata():
    current = _current.get()
    return {k: v for k, v in current.energies.items() if -100 <= v <= 0} if current else {}


def restore_energy(values):
    current = _current.get()
    if current is not None and shadow_or_serve(FLAG) and isinstance(values, dict):
        current.energies.update(
            {k: v for k, v in list(values.items())[:1500] if isinstance(v, (int, float)) and -100 <= v <= 0}
        )


def reason(value: str) -> None:
    current = _current.get()
    if current is not None:
        if current.reason != value and current.reason not in ('disabled', 'resolved', 'partial'):
            current.abstentions.add(current.reason)
        current.reason = value


def capture_resolution(resolution: Any) -> None:
    current = _current.get()
    if current is not None:
        current.resolution = resolution


def window_abstentions(placements, abstained):
    current = _current.get()
    if current is not None:
        current.abstentions.update(p.reason for sid, p in placements.items() if sid in abstained)


def _roster(uid: str, conversation: Any) -> list[dict]:
    candidates = roster_candidates(
        getattr(conversation, 'calendar_meeting_context', None)
        or (getattr(conversation, 'external_data', None) or {}).get('calendar_meeting_context')
    )
    try:
        from utils.episodes.boundaries import boundary_roster

        times = {name: getattr(conversation, name, None) for name in ('started_at', 'finished_at', 'last_speech_at')}
        candidates.extend(
            {'name': person.name, 'email': person.email}
            for person in boundary_roster(uid, conversation.id, conversation=times)
        )
    except Exception as error:
        logger.warning(
            'event=refactor_shadow lane=L2 check=boundary_roster outcome=error exception_type=%s', type(error).__name__
        )
        AGREEMENT.labels(outcome='error').inc()
        record_fallback(
            component='other',
            from_mode='boundary_roster',
            to_mode='calendar_roster',
            reason='dependency_unavailable',
            outcome='degraded',
            log=logger,
        )
    return unique_roster(candidates)


def finish(token, uid: str, conversation: Any, receipt: Any) -> None:
    current = _current.get()
    _current.reset(token)
    if current is None or not shadow_or_serve(FLAG):
        return
    try:
        evidence = build_evidence(
            conversation.transcript_segments,
            current.resolution,
            receipt=receipt,
            roster=_roster(uid, conversation),
            channel_ids=current.channel_ids,
            energies=current.energies,
            near_field_allowed=str(getattr(conversation, 'source', '')).split('.')[-1] in ('omi', 'phone'),
            abstentions=sorted(
                current.abstentions
                | (set() if current.reason == 'resolved' else {current.reason})
                | ({'manual_receipt_unavailable'} if receipt is None else set())
            ),
        )
        labels = project_labels(evidence, receipt or {})
        previous_count = len(
            {
                cluster_key(s, current.resolution, set(current.channel_ids))
                for s in conversation.transcript_segments
                if s.id and s.speaker_id != 99
            }
        )
        count_changed = previous_count > len(evidence.clusters)
        logger.info(
            'event=refactor_shadow lane=L2 check=participant_count outcome=%s', 'disagree' if count_changed else 'agree'
        )
        agrees = all(
            labels.get(s.id) == (s.is_user, s.person_id) for s in conversation.transcript_segments if s.id in labels
        )
        outcome = 'agree' if agrees else 'disagree'
        sampled = shadow_sampled(FLAG, uid, SHADOW_SAMPLE_PERCENT)
        if sampled:
            storage.store_evidence(
                uid, conversation.id, evidence, expected_updated_at=getattr(conversation, 'updated_at', None)
            )
        TOTAL.labels(status=evidence.status, outcome='stored' if sampled else 'observed').inc()
        ANCHORS.labels(anchor=evidence.owner_anchor).inc()
        COUNT_HINTS.labels(
            outcome=(
                'unresolved'
                if 'participant_count_unresolved' in evidence.abstentions
                else 'reduced' if count_changed else 'present' if evidence.participant_count_hint else 'absent'
            )
        ).inc()
        OWNER_SHARE.labels(
            present=str(
                any(
                    c.person_id == 'owner' and c.band == 'confident' and (c.label_eligible or c.source == 'manual')
                    for v in evidence.clusters
                    for c in v.candidates
                )
            ).lower()
        ).inc()
        AGREEMENT.labels(outcome=reason_label(ReasonFamily.PARITY, outcome, RefactorShadowOutcome)).inc()
        logger.info('event=refactor_shadow lane=L2 check=project_labels outcome=%s', outcome)
        if serving_for(FLAG, uid) and receipt is not None:
            by_segment = {sid: cluster for cluster in evidence.clusters for sid in cluster.segment_ids}
            for segment in conversation.transcript_segments:
                if text_window_refusal(segment.start, segment.end) is not None:
                    continue
                if segment.id in labels:
                    segment.is_user, segment.person_id = labels[segment.id]
                    segment.speaker_identity_status = (
                        'user'
                        if segment.is_user
                        else (
                            'not_user'
                            if segment.person_id
                            else (
                                getattr(segment, 'speaker_identity_status', 'unknown')
                                if getattr(segment, 'speaker_identity_status', 'unknown') in ('ambiguous', 'no_match')
                                else 'unknown'
                            )
                        )
                    )
                cluster = by_segment.get(segment.id)
                if (
                    cluster is not None
                    and current.resolution
                    and segment.id in current.resolution.speaker_ids
                    and cluster.speaker_id is not None
                    and cluster.speaker_id != segment.speaker_id
                ):
                    segment.assign_resolved_speaker(cluster.speaker_id, f'conversation:{conversation.id}')
            if (
                current.resolution
                and current.resolution.coverage >= 0.9
                and getattr(conversation, 'speaker_resolution', None)
            ):
                conversation.speaker_resolution.participant_speaker_ids = sorted(
                    {
                        c.speaker_id
                        for c in evidence.clusters
                        if c.speech_seconds >= 10
                        and c.speaker_id is not None
                        and any(sid in current.resolution.speaker_ids for sid in c.segment_ids)
                    }
                )
    except Exception as error:
        TOTAL.labels(status='unavailable', outcome='error').inc()
        AGREEMENT.labels(outcome='error').inc()
        logger.warning(
            'event=refactor_shadow lane=L2 check=project_labels outcome=error exception_type=%s', type(error).__name__
        )
        record_fallback(
            component='other',
            from_mode='speaker_evidence',
            to_mode='capture_speaker_ids',
            reason='other',
            outcome='degraded',
            log=logger,
        )
