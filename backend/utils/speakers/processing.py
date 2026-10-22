"""Finalize adapter: record evidence once, compare in shadow, project in cohort."""

from contextvars import ContextVar
from dataclasses import dataclass, field
import logging
from typing import Any

from prometheus_client import Counter

from config.refactor_modes import serving_for, shadow_or_serve
from database import speaker_evidence as storage
from utils.speakers.evidence import FLAG, build_evidence, project_labels, roster_candidates
from utils.observability.fallback import record_fallback
from utils.conversations.audio_placement import text_window_refusal

logger = logging.getLogger(__name__)
TOTAL = Counter('omi_speaker_evidence_total', 'Speaker evidence production outcomes', ['status', 'outcome'])
AGREEMENT = Counter('omi_speaker_evidence_shadow_agreement_total', 'Label projection comparison', ['outcome'])
OWNER_SHARE = Counter('omi_speaker_evidence_confident_owner_total', 'Conversations with a confident owner', ['present'])


@dataclass
class EvidencePass:
    resolution: Any = None
    reason: str = 'disabled'
    abstentions: set[str] = field(default_factory=set)


_current: ContextVar[EvidencePass | None] = ContextVar('speaker_evidence_pass', default=None)


def begin():
    return _current.set(EvidencePass())


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

        candidates.extend({'name': person.name} for person in boundary_roster(uid, conversation.id))
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
    unique = {str(person.get('name')): person for person in candidates if person.get('name')}
    return list(unique.values())


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
            abstentions=sorted(
                current.abstentions
                | (set() if current.reason == 'resolved' else {current.reason})
                | ({'manual_receipt_unavailable'} if receipt is None else set())
            ),
        )
        labels = project_labels(evidence, receipt or {})
        agrees = all(
            labels.get(s.id) == (s.is_user, s.person_id) for s in conversation.transcript_segments if s.id in labels
        )
        outcome = 'agree' if agrees else 'disagree'
        storage.store_evidence(
            uid, conversation.id, evidence, expected_updated_at=getattr(conversation, 'updated_at', None)
        )
        TOTAL.labels(status=evidence.status, outcome='stored').inc()
        OWNER_SHARE.labels(
            present=str(
                any(
                    c.person_id == 'owner' and c.band == 'confident' and (c.label_eligible or c.source == 'manual')
                    for v in evidence.clusters
                    for c in v.candidates
                )
            ).lower()
        ).inc()
        AGREEMENT.labels(outcome=outcome).inc()
        logger.info('event=refactor_shadow lane=L2 check=project_labels outcome=%s', outcome)
        if serving_for(FLAG, uid) and receipt is not None:
            for segment in conversation.transcript_segments:
                if segment.id in labels and text_window_refusal(segment.start, segment.end) is None:
                    segment.is_user, segment.person_id = labels[segment.id]
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
