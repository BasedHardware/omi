"""Facts → filters → one judgment → trace for What Matters Now."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field

import database.candidates as candidates_db
import database.task_recommendations as recommendation_db
import database.task_intelligence_control as task_control_db
import database.workstreams as workstreams_db
from models.action_item import EvidenceKind, EvidenceRef, EvidenceScope, TaskChangePayload, TaskStatus
from models.candidate import CandidateCreate, CandidateStatus, TaskCompleteCandidate
from models.goal import GoalStatus
from models.task_intelligence import TaskIntelligenceFeedbackAction, TaskIntelligenceFeedbackReason
from models.task_recommendation import (
    ContextMatchSignal,
    DecisionDebugProjection,
    DecisionRecord,
    DeterministicFacts,
    EvaluationRequest,
    FeedbackCreate,
    FeedbackRecord,
    FeedbackSubjectKind,
    InterventionCreate,
    InterventionRecord,
    NormalizedContextSnapshot,
    OpenLoopSnapshot,
    OpenLoopStatus,
    OutcomeCreate,
    OutcomeRecord,
    Recommendation,
    RecommendationSubjectKind,
    ShortlistEligibility,
    SnapshotReceipt,
    WhatMattersNowProjection,
)
from utils.metrics import TASK_INTELLIGENCE_ATTRIBUTION_TOTAL

MINIMUM_CAPTURE_CONFIDENCE = 0.8
MAX_SHORTLIST_SIZE = 20
MAX_RECOMMENDATIONS = 3
PROJECTION_TTL = timedelta(minutes=30)
MAX_LOCAL_SNAPSHOT_TTL = timedelta(hours=1)
DEFAULT_LATER_TTL = timedelta(days=1)
DISMISS_TTL = timedelta(days=30)
PROMPT_VERSION = 'what-matters-now.v1'
POLICY_VERSION = 'ranking.v1'
FACT_DEFINITION_VERSION = 'facts.v1'


class SnapshotValidationError(ValueError):
    pass


class JudgmentSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')

    subject_kind: RecommendationSubjectKind
    subject_id: str = Field(min_length=1, max_length=128)
    why_now: str = Field(min_length=1, max_length=1024)
    recommended_action: str = Field(min_length=1, max_length=128)
    alternative_action: Optional[str] = Field(default=None, max_length=128)


@dataclass(frozen=True)
class EvaluationSubject:
    kind: RecommendationSubjectKind
    subject_id: str
    feedback_subject_kind: FeedbackSubjectKind
    feedback_subject_id: str
    headline: str
    label: Optional[str]
    evidence_preview: str
    evidence_refs: tuple[EvidenceRef, ...]
    facts: DeterministicFacts
    eligibility: ShortlistEligibility
    material_token: str


class RecommendationJudgment(Protocol):
    model_version: str

    def judge(self, subjects: list[EvaluationSubject]) -> list[JudgmentSelection]: ...


def _stable_id(prefix: str, *parts: object) -> str:
    encoded = '\x1f'.join(str(part) for part in parts).encode('utf-8')
    return f'{prefix}_{hashlib.sha256(encoded).hexdigest()[:32]}'


def _recommendation_dedupe_key(subject: EvaluationSubject) -> str:
    # Suggested and What Matters Now are two presentation surfaces for the same
    # pending Candidate. Keep one bounded key so feedback on either surface
    # suppresses the equivalent intervention everywhere.
    if subject.kind == RecommendationSubjectKind.candidate:
        return _stable_id('candidate', subject.subject_id)
    return _stable_id('recommendation', subject.kind.value, subject.subject_id, subject.material_token)


def _as_aware(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _iso_token(value: Any) -> str:
    timestamp = _as_aware(value)
    return timestamp.isoformat() if timestamp is not None else str(value or '')


def _valid_evidence(raw: Any, *, device_id: Optional[str] = None) -> tuple[EvidenceRef, ...]:
    if not isinstance(raw, list):
        return ()
    records: list[EvidenceRef] = []
    for item in raw[:50]:
        try:
            evidence = EvidenceRef.model_validate(item)
        except (TypeError, ValueError):
            continue
        if evidence.scope == EvidenceScope.device_local and evidence.device_id != device_id:
            continue
        records.append(evidence)
    return tuple(records)


def _context_signals(
    kind: RecommendationSubjectKind,
    subject_id: str,
    snapshot: Optional[NormalizedContextSnapshot],
) -> list[ContextMatchSignal]:
    if snapshot is None:
        return []
    signals: set[ContextMatchSignal] = set()
    for match in snapshot.matches:
        if match.subject_kind == kind and match.subject_id == subject_id:
            signals.update(match.signals)
    return sorted(signals, key=lambda signal: signal.value)


def _days_to_due(due_at: Any, now: datetime) -> Optional[float]:
    due = _as_aware(due_at)
    if due is None:
        return None
    # Whole-day fact buckets avoid turning clock drift into material state churn.
    seconds = (due - now).total_seconds()
    return float(int(seconds // 86400) if seconds >= 0 else -int((-seconds) // 86400))


def _recent(updated_at: Any, now: datetime) -> bool:
    updated = _as_aware(updated_at)
    return updated is not None and now - updated <= timedelta(days=7)


def _eligibility(
    *,
    is_open: bool,
    unexpired: bool,
    facts: DeterministicFacts,
    recent_material_activity: bool,
) -> ShortlistEligibility:
    passes = (
        is_open
        and unexpired
        and facts.capture_confidence >= MINIMUM_CAPTURE_CONFIDENCE
        and facts.has_concrete_next_action
    )
    return ShortlistEligibility(
        open=is_open,
        unexpired=unexpired,
        passes_recommendation_gates=passes,
        recent_material_activity=recent_material_activity,
        inside_due_window=facts.days_to_due is not None and -1 <= facts.days_to_due <= 7,
    )


def _canonical_evidence_preview(facts: DeterministicFacts, evidence: tuple[EvidenceRef, ...]) -> str:
    if facts.days_to_due is not None:
        if facts.days_to_due < 0:
            return 'Due date has passed.'
        if facts.days_to_due <= 7:
            days = max(0, round(facts.days_to_due))
            return f'Due in {days} day' + ('' if days == 1 else 's') + '.'
    if facts.context_match_signals:
        return 'Relevant context is active: ' + ', '.join(signal.value for signal in facts.context_match_signals) + '.'
    if facts.someone_blocked:
        return 'Progress is waiting on input.'
    if evidence:
        return f'Linked to {len(evidence)} evidence source' + ('' if len(evidence) == 1 else 's') + '.'
    return 'Canonical state has a concrete next action.'


def _subject(
    *,
    kind: RecommendationSubjectKind,
    subject_id: str,
    feedback_subject_kind: Optional[FeedbackSubjectKind] = None,
    feedback_subject_id: Optional[str] = None,
    headline: str,
    label: Optional[str],
    evidence: tuple[EvidenceRef, ...],
    facts: DeterministicFacts,
    is_open: bool,
    unexpired: bool,
    recent_material_activity: bool,
    material_token: str,
) -> EvaluationSubject:
    eligibility = _eligibility(
        is_open=is_open,
        unexpired=unexpired,
        facts=facts,
        recent_material_activity=recent_material_activity,
    )
    resolved_feedback_kind = feedback_subject_kind or FeedbackSubjectKind(kind.value)
    return EvaluationSubject(
        kind=kind,
        subject_id=subject_id,
        feedback_subject_kind=resolved_feedback_kind,
        feedback_subject_id=feedback_subject_id or subject_id,
        headline=headline[:256] or 'Untitled work',
        label=label[:256] if label else None,
        evidence_preview=_canonical_evidence_preview(facts, evidence),
        evidence_refs=evidence,
        facts=facts,
        eligibility=eligibility,
        material_token=material_token,
    )


def _build_subjects(
    state: dict[str, list[dict[str, Any]]],
    *,
    context: Optional[NormalizedContextSnapshot],
    open_loop_snapshots: list[OpenLoopSnapshot],
    now: datetime,
) -> list[EvaluationSubject]:
    goals = {str(goal.get('goal_id') or goal.get('id')): goal for goal in state['goals']}
    focused_goal_ids = {
        goal_id
        for goal_id, goal in goals.items()
        if goal.get('status') == GoalStatus.focused.value and goal.get('is_active', True)
    }
    workstreams = {str(record.get('workstream_id') or record.get('id')): record for record in state['workstreams']}
    subjects: list[EvaluationSubject] = []

    for task in state['tasks']:
        subject_id = str(task.get('task_id') or task.get('id') or '')
        if not subject_id:
            continue
        kind = RecommendationSubjectKind.task
        goal_id = str(task.get('goal_id') or '')
        workstream_id = str(task.get('workstream_id') or '')
        workstream = workstreams.get(workstream_id)
        label = str((workstream or {}).get('title') or goals.get(goal_id, {}).get('title') or '') or None
        status = str(
            task.get('status') or (TaskStatus.completed.value if task.get('completed') else TaskStatus.active.value)
        )
        signals = _context_signals(kind, subject_id, context)
        facts = DeterministicFacts(
            days_to_due=_days_to_due(task.get('due_at'), now),
            someone_blocked=False,
            has_concrete_next_action=bool(str(task.get('description') or '').strip()),
            focused_goal_linked=goal_id in focused_goal_ids,
            context_match_signals=signals,
            capture_confidence=float(task.get('capture_confidence', 1.0)),
        )
        evidence = _valid_evidence(task.get('provenance'), device_id=context.device_id if context else None)
        subjects.append(
            _subject(
                kind=kind,
                subject_id=subject_id,
                headline=str(task.get('description') or ''),
                label=label,
                evidence=evidence,
                facts=facts,
                is_open=status == TaskStatus.active.value and not task.get('deleted', False),
                unexpired=True,
                recent_material_activity=_recent(task.get('updated_at') or task.get('created_at'), now),
                material_token=':'.join((status, _iso_token(task.get('updated_at')), _iso_token(task.get('due_at')))),
            )
        )

    for candidate in state['candidates']:
        subject_id = str(candidate.get('candidate_id') or candidate.get('id') or '')
        if not subject_id:
            continue
        kind = RecommendationSubjectKind.candidate
        raw_task_change = candidate.get('task_change')
        task_change: dict[str, Any] = raw_task_change if isinstance(raw_task_change, dict) else {}
        raw_proposal = candidate.get('workstream_proposal')
        proposal: dict[str, Any] = raw_proposal if isinstance(raw_proposal, dict) else {}
        headline = str(task_change.get('description') or proposal.get('title') or 'Review suggested work')
        goal_id = str(candidate.get('goal_id') or '')
        confidence = float(candidate.get('capture_confidence', 0))
        facts = DeterministicFacts(
            has_concrete_next_action=bool(headline.strip()),
            focused_goal_linked=goal_id in focused_goal_ids,
            context_match_signals=_context_signals(kind, subject_id, context),
            capture_confidence=confidence,
        )
        evidence = _valid_evidence(candidate.get('evidence_refs'), device_id=context.device_id if context else None)
        candidate_status = str(candidate.get('status') or CandidateStatus.pending.value)
        subjects.append(
            _subject(
                kind=kind,
                subject_id=subject_id,
                headline=headline,
                label=str(goals.get(goal_id, {}).get('title') or '') or None,
                evidence=evidence,
                facts=facts,
                is_open=candidate_status == CandidateStatus.pending.value,
                unexpired=True,
                recent_material_activity=_recent(candidate.get('created_at'), now),
                material_token=':'.join((candidate_status, _iso_token(candidate.get('created_at')))),
            )
        )

    for workstream_id, workstream in workstreams.items():
        if not workstream_id:
            continue
        kind = RecommendationSubjectKind.workstream
        goal_id = str(workstream.get('goal_id') or '')
        headline = str(workstream.get('title') or workstream.get('objective') or '')
        signals = _context_signals(kind, workstream_id, context)
        days_to_review = _days_to_due(workstream.get('next_review_at'), now)
        event_evidence: list[EvidenceRef] = []
        for event in state.get('workstream_events', []):
            if str(event.get('workstream_id') or '') != workstream_id:
                continue
            event_id = str(event.get('event_id') or event.get('id') or '')
            if event_id:
                event_evidence.append(
                    EvidenceRef(
                        kind=EvidenceKind.workstream_event,
                        id=event_id,
                        scope=EvidenceScope.canonical,
                    )
                )
            event_evidence.extend(_valid_evidence(event.get('evidence_refs')))
            if len(event_evidence) >= 50:
                break
        facts = DeterministicFacts(
            days_to_due=days_to_review,
            has_concrete_next_action=(days_to_review is not None and days_to_review <= 7) or bool(signals),
            focused_goal_linked=goal_id in focused_goal_ids,
            context_match_signals=signals,
            capture_confidence=1,
        )
        subjects.append(
            _subject(
                kind=kind,
                subject_id=workstream_id,
                headline=headline,
                label=str(goals.get(goal_id, {}).get('title') or '') or None,
                evidence=tuple(event_evidence[:50]),
                facts=facts,
                is_open=workstream.get('status') == 'open',
                unexpired=True,
                recent_material_activity=_recent(workstream.get('updated_at'), now),
                material_token=':'.join(
                    (
                        str(workstream.get('status')),
                        _iso_token(workstream.get('updated_at')),
                        _iso_token(workstream.get('next_review_at')),
                        ','.join(evidence.id for evidence in event_evidence[:50]),
                    )
                ),
            )
        )

    for artifact in state['artifacts']:
        subject_id = str(artifact.get('artifact_id') or artifact.get('id') or '')
        if not subject_id:
            continue
        kind = RecommendationSubjectKind.artifact
        workstream_id = str(artifact.get('workstream_id') or '')
        workstream = workstreams.get(workstream_id, {})
        goal_id = str(workstream.get('goal_id') or '')
        status = str(artifact.get('status') or '')
        facts = DeterministicFacts(
            has_concrete_next_action=status == 'awaiting_review',
            focused_goal_linked=goal_id in focused_goal_ids,
            context_match_signals=_context_signals(kind, subject_id, context),
            capture_confidence=1,
        )
        evidence = _valid_evidence(artifact.get('evidence_refs'), device_id=context.device_id if context else None)
        subjects.append(
            _subject(
                kind=kind,
                subject_id=subject_id,
                headline=f"Review {str(artifact.get('kind') or 'artifact').replace('_', ' ')}",
                label=str(workstream.get('title') or '') or None,
                evidence=evidence,
                facts=facts,
                is_open=status == 'awaiting_review',
                unexpired=True,
                recent_material_activity=_recent(artifact.get('created_at'), now),
                material_token=':'.join(
                    (status, str(artifact.get('version') or ''), str(artifact.get('content_hash') or ''))
                ),
            )
        )

    for snapshot in open_loop_snapshots:
        workstream = workstreams.get(snapshot.workstream_id, {})
        if not workstream or workstream.get('status') != 'open':
            continue
        goal_id = str(workstream.get('goal_id') or '')
        for loop in snapshot.open_loop_snapshot:
            kind = (
                RecommendationSubjectKind.decision
                if loop.kind.value == 'decision'
                else RecommendationSubjectKind.agent_open_loop
            )
            recommendation_subject_id = loop.subject_id if kind == RecommendationSubjectKind.decision else loop.loop_id
            signals = _context_signals(kind, recommendation_subject_id, context)
            user_actionable = loop.status in {OpenLoopStatus.open, OpenLoopStatus.blocked, OpenLoopStatus.awaiting_user}
            facts = DeterministicFacts(
                someone_blocked=loop.status in {OpenLoopStatus.blocked, OpenLoopStatus.awaiting_user},
                has_concrete_next_action=user_actionable and bool(loop.next_action_code),
                focused_goal_linked=goal_id in focused_goal_ids,
                context_match_signals=signals,
                capture_confidence=1,
            )
            evidence = (
                EvidenceRef(
                    kind=EvidenceKind.external,
                    id=loop.loop_id,
                    version=snapshot.context_packet_version,
                    scope=EvidenceScope.device_local,
                    device_id=snapshot.device_id,
                ),
            )
            feedback_kind = {
                'task': FeedbackSubjectKind.task,
                'artifact': FeedbackSubjectKind.artifact,
                'decision': FeedbackSubjectKind.decision,
                'approval': FeedbackSubjectKind.artifact,
                'external_wait': FeedbackSubjectKind.workstream,
            }[loop.kind.value]
            feedback_id = snapshot.workstream_id if feedback_kind == FeedbackSubjectKind.workstream else loop.subject_id
            subjects.append(
                _subject(
                    kind=kind,
                    subject_id=recommendation_subject_id,
                    feedback_subject_kind=feedback_kind,
                    feedback_subject_id=feedback_id,
                    headline=(
                        'Decision needed'
                        if kind == RecommendationSubjectKind.decision
                        else (
                            'Omi needs your input'
                            if loop.status == OpenLoopStatus.awaiting_user
                            else 'Continue agent work'
                        )
                    ),
                    label=str(workstream.get('title') or '') or None,
                    evidence=evidence,
                    facts=facts,
                    is_open=user_actionable,
                    unexpired=snapshot.expires_at > now,
                    recent_material_activity=_recent(loop.updated_at, now),
                    material_token=':'.join((loop.status.value, loop.next_action_code, loop.updated_at.isoformat())),
                )
            )

    # Canonical ID order is normalization for cache stability, not a relevance rank.
    subjects.sort(key=lambda subject: (subject.kind.value, subject.subject_id))
    return subjects


def filter_shortlist(subjects: list[EvaluationSubject], suppressed_dedupe_keys: set[str]) -> list[EvaluationSubject]:
    """Filter only. It must never calculate or sort by relevance."""

    shortlist: list[EvaluationSubject] = []
    for subject in subjects:
        dedupe_key = _recommendation_dedupe_key(subject)
        fact_window = (
            subject.eligibility.recent_material_activity
            or subject.eligibility.inside_due_window
            or bool(subject.facts.context_match_signals)
            or subject.facts.someone_blocked
        )
        if subject.eligibility.passes_recommendation_gates and fact_window and dedupe_key not in suppressed_dedupe_keys:
            shortlist.append(subject)
        if len(shortlist) == MAX_SHORTLIST_SIZE:
            break
    return shortlist


def _material_version(
    subjects: list[EvaluationSubject],
    *,
    suppressed_dedupe_keys: set[str],
    context: Optional[NormalizedContextSnapshot],
    open_loops: list[OpenLoopSnapshot],
    material_hint: Optional[str],
) -> str:
    payload = {
        'subjects': [
            {
                'kind': subject.kind.value,
                'id': subject.subject_id,
                'material': subject.material_token,
                'facts': subject.facts.model_dump(mode='json'),
                'eligibility': subject.eligibility.model_dump(mode='json'),
            }
            for subject in subjects
        ],
        'suppressed': sorted(suppressed_dedupe_keys),
        'context': (
            sorted(
                (
                    match.subject_kind.value,
                    match.subject_id,
                    tuple(sorted(signal.value for signal in match.signals)),
                )
                for match in context.matches
            )
            if context is not None
            else None
        ),
        'open_loops': sorted(
            (
                snapshot.workstream_id,
                snapshot.runtime_id,
                snapshot.context_packet_version,
                snapshot.checkpoint_ref or '',
                tuple(
                    sorted(
                        (
                            loop.loop_id,
                            loop.kind.value,
                            loop.subject_id,
                            loop.status.value,
                            loop.next_action_code,
                            loop.blocking_on_id or '',
                            loop.updated_at.isoformat(),
                        )
                        for loop in snapshot.open_loop_snapshot
                    )
                ),
            )
            for snapshot in open_loops
        ),
        'hint': material_hint,
        'policy': POLICY_VERSION,
    }
    return _stable_id('material', json.dumps(payload, sort_keys=True, separators=(',', ':')))


def evaluate(
    uid: str,
    request: EvaluationRequest,
    *,
    judgment: RecommendationJudgment,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
) -> WhatMattersNowProjection:
    evaluated_at = now or datetime.now(timezone.utc)
    device_scope = request.device_id or 'global'
    context = (
        recommendation_db.get_context_snapshot(
            uid, request.device_id, now=evaluated_at, firestore_client=firestore_client
        )
        if request.device_id is not None
        else None
    )
    open_loops = (
        recommendation_db.list_open_loop_snapshots(
            uid,
            device_id=request.device_id,
            now=evaluated_at,
            firestore_client=firestore_client,
        )
        if request.device_id is not None
        else []
    )
    state = recommendation_db.load_canonical_product_state(uid, firestore_client=firestore_client)
    subjects = _build_subjects(state, context=context, open_loop_snapshots=open_loops, now=evaluated_at)
    suppressed = recommendation_db.list_active_override_dedupe_keys(
        uid, now=evaluated_at, firestore_client=firestore_client
    )
    material_version = _material_version(
        subjects,
        suppressed_dedupe_keys=suppressed,
        context=context,
        open_loops=open_loops,
        material_hint=request.material_hint,
    )
    cached = recommendation_db.get_projection(
        uid,
        device_scope=device_scope,
        now=evaluated_at,
        include_expired=True,
        firestore_client=firestore_client,
    )
    if cached is not None and cached.material_version == material_version:
        if cached.expires_at > evaluated_at:
            return cached
        refreshed_expiry = evaluated_at + PROJECTION_TTL
        refreshed = cached.model_copy(
            update={
                'generated_at': evaluated_at,
                'expires_at': refreshed_expiry,
                'recommendations': [
                    item.model_copy(update={'expires_at': refreshed_expiry}) for item in cached.recommendations
                ],
            }
        )
        prior_decisions = recommendation_db.get_decisions(
            uid,
            cached.evaluation_id,
            device_scope=device_scope,
            firestore_client=firestore_client,
        )
        published = recommendation_db.save_projection(
            uid,
            device_scope=device_scope,
            projection=refreshed,
            decisions=[decision.model_copy(update={'expires_at': refreshed_expiry}) for decision in prior_decisions],
            firestore_client=firestore_client,
        )
        return published

    shortlist = filter_shortlist(subjects, suppressed)
    raw_selections = judgment.judge(shortlist)
    shortlist_by_key = {(subject.kind, subject.subject_id): subject for subject in shortlist}
    selected: list[tuple[EvaluationSubject, JudgmentSelection]] = []
    selected_keys: set[tuple[RecommendationSubjectKind, str]] = set()
    for selection in raw_selections:
        selection_key = (selection.subject_kind, selection.subject_id)
        subject = shortlist_by_key.get(selection_key)
        if subject is None or selection_key in selected_keys:
            continue
        selected.append((subject, selection))
        selected_keys.add(selection_key)
        if len(selected) == MAX_RECOMMENDATIONS:
            break

    expires_at = evaluated_at + PROJECTION_TTL
    evaluation_id = _stable_id('evaluation', uid, device_scope, material_version)
    output_version = _stable_id(
        'output', evaluation_id, *((subject.kind.value, subject.subject_id) for subject, _ in selected)
    )
    recommendations: list[Recommendation] = []
    for subject, selection in selected:
        dedupe_key = _recommendation_dedupe_key(subject)
        intervention_id = _stable_id('intervention', uid, output_version, dedupe_key)
        recommendations.append(
            Recommendation(
                intervention_id=intervention_id,
                output_version=output_version,
                subject_kind=subject.kind,
                subject_id=subject.subject_id,
                feedback_subject_kind=subject.feedback_subject_kind,
                feedback_subject_id=subject.feedback_subject_id,
                headline=subject.headline,
                why_now=selection.why_now,
                goal_or_workstream_label=subject.label,
                recommended_action=selection.recommended_action,
                alternative_action=selection.alternative_action,
                evidence_preview=subject.evidence_preview,
                evidence_refs=list(subject.evidence_refs),
                dedupe_key=dedupe_key,
                expires_at=expires_at,
            )
        )

    projection = WhatMattersNowProjection(
        evaluation_id=evaluation_id,
        output_version=output_version,
        material_version=material_version,
        generated_at=evaluated_at,
        expires_at=expires_at,
        recommendations=recommendations,
    )
    shortlist_ids = [_stable_id('subject', subject.kind.value, subject.subject_id) for subject in shortlist]
    traced_subjects = shortlist + [subject for subject in subjects if subject not in shortlist]
    decisions = [
        DecisionRecord(
            evaluation_id=evaluation_id,
            subject_kind=subject.kind,
            subject_id=subject.subject_id,
            shortlist_ids=shortlist_ids,
            facts_snapshot=subject.facts,
            eligibility=subject.eligibility,
            prompt_version=PROMPT_VERSION,
            policy_version=POLICY_VERSION,
            fact_definition_version=FACT_DEFINITION_VERSION,
            model_version=judgment.model_version,
            decision_summary=(
                'Selected by holistic judgment.'
                if (subject.kind, subject.subject_id) in selected_keys
                else (
                    'Not selected by holistic judgment.'
                    if subject in shortlist
                    else 'Removed by deterministic recommendation gates.'
                )
            ),
            reason_codes=[
                (
                    'selected'
                    if (subject.kind, subject.subject_id) in selected_keys
                    else 'not_selected' if subject in shortlist else 'ineligible'
                )
            ],
            evidence_refs=list(subject.evidence_refs),
            final_output_ref=output_version,
            evaluated_at=evaluated_at,
            expires_at=expires_at,
        )
        for subject in traced_subjects[:MAX_SHORTLIST_SIZE]
    ]
    published = recommendation_db.save_projection(
        uid,
        device_scope=device_scope,
        projection=projection,
        decisions=decisions,
        firestore_client=firestore_client,
    )
    if published != projection:
        return published
    for recommendation in recommendations:
        TASK_INTELLIGENCE_ATTRIBUTION_TOTAL.labels(
            event='intervention', subject_kind=recommendation.feedback_subject_kind.value, code='what_matters_now'
        ).inc()
    return projection


def get_debug_projection(
    uid: str,
    evaluation_id: str,
    *,
    device_id: Optional[str],
    now: Optional[datetime] = None,
    firestore_client: Any = None,
) -> Optional[DecisionDebugProjection]:
    checked_at = now or datetime.now(timezone.utc)
    projection = recommendation_db.get_evaluation_projection(
        uid,
        evaluation_id,
        device_scope=device_id or 'global',
        now=checked_at,
        firestore_client=firestore_client,
    )
    if projection is None:
        return None
    decisions = recommendation_db.get_decisions(
        uid, evaluation_id, device_scope=device_id or 'global', firestore_client=firestore_client
    )
    return DecisionDebugProjection(projection=projection, decisions=decisions)


def register_intervention(
    uid: str,
    request: InterventionCreate,
    *,
    idempotency_key: str,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
) -> InterventionRecord:
    created_at = now or datetime.now(timezone.utc)
    if request.expires_at <= created_at:
        raise SnapshotValidationError('intervention must expire in the future')
    record, newly_created = recommendation_db.create_intervention(
        uid,
        request,
        idempotency_key=idempotency_key,
        now=created_at,
        firestore_client=firestore_client,
    )
    if newly_created:
        TASK_INTELLIGENCE_ATTRIBUTION_TOTAL.labels(
            event='intervention', subject_kind=request.subject_kind.value, code=request.surface.value
        ).inc()
    return record


def record_feedback(
    uid: str,
    request: FeedbackCreate,
    *,
    idempotency_key: str,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
) -> FeedbackRecord:
    created_at = now or datetime.now(timezone.utc)
    override_expires_at: Optional[datetime] = None
    if request.action == TaskIntelligenceFeedbackAction.later:
        override_expires_at = request.later_until or created_at + DEFAULT_LATER_TTL
        if override_expires_at <= created_at:
            raise SnapshotValidationError('later_until must be in the future')
    elif request.action == TaskIntelligenceFeedbackAction.dismiss:
        override_expires_at = created_at + DISMISS_TTL
    record, newly_recorded = recommendation_db.create_feedback(
        uid,
        request,
        idempotency_key=idempotency_key,
        now=created_at,
        override_expires_at=override_expires_at,
        firestore_client=firestore_client,
    )
    if newly_recorded:
        TASK_INTELLIGENCE_ATTRIBUTION_TOTAL.labels(
            event='feedback', subject_kind=request.subject_kind.value, code=request.action.value
        ).inc()
    feedback_reason = request.reason
    if (
        feedback_reason is not None
        and feedback_reason
        in {
            TaskIntelligenceFeedbackReason.already_handled,
            TaskIntelligenceFeedbackReason.not_mine,
        }
        and request.subject_kind.value == 'candidate'
    ):
        candidate = candidates_db.get_candidate(uid, request.subject_id)
        if candidate is not None and candidate.status == CandidateStatus.pending:
            candidates_db.resolve_candidate_without_mutation(
                uid,
                request.subject_id,
                status=CandidateStatus.rejected,
                reason=feedback_reason.value,
                account_generation=candidate.account_generation,
            )
    elif request.reason == TaskIntelligenceFeedbackReason.already_handled and request.subject_kind.value == 'task':
        control = task_control_db.get_task_workflow_control(uid)
        proposal = CandidateCreate(
            root=TaskCompleteCandidate(
                task_id=request.subject_id,
                task_change=TaskChangePayload(status=TaskStatus.completed),
                capture_confidence=1,
                ownership_confidence=1,
                evidence_refs=[
                    EvidenceRef(
                        kind=EvidenceKind.external,
                        id=record.feedback_id,
                        scope=EvidenceScope.canonical,
                    )
                ],
                source_surface='feedback',
            )
        )
        completion_candidate = candidates_db.create_candidate(
            uid,
            proposal,
            idempotency_key=f'already-handled:{record.feedback_id}',
            account_generation=control.account_generation,
        )
        recommendation_db.link_feedback_completion_candidate(
            uid,
            record.feedback_id,
            completion_candidate.candidate_id,
            firestore_client=firestore_client,
        )
        record = record.model_copy(update={'proposed_completion_candidate_id': completion_candidate.candidate_id})
    return record


def record_outcome(
    uid: str,
    request: OutcomeCreate,
    *,
    idempotency_key: str,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
) -> OutcomeRecord:
    record, newly_recorded = recommendation_db.create_outcome(
        uid,
        request,
        idempotency_key=idempotency_key,
        now=now or datetime.now(timezone.utc),
        firestore_client=firestore_client,
    )
    if newly_recorded:
        TASK_INTELLIGENCE_ATTRIBUTION_TOTAL.labels(
            event='outcome', subject_kind=request.subject_kind.value, code=request.outcome_code.value
        ).inc()
    return record


def _validate_snapshot_window(generated_at: datetime, expires_at: datetime, now: datetime) -> None:
    if generated_at >= expires_at:
        raise SnapshotValidationError('snapshot generated_at must precede expires_at')
    if expires_at <= now:
        raise SnapshotValidationError('snapshot must expire in the future')
    if expires_at - generated_at > MAX_LOCAL_SNAPSHOT_TTL:
        raise SnapshotValidationError('snapshot TTL exceeds one hour')
    if generated_at > now + timedelta(minutes=5):
        raise SnapshotValidationError('snapshot generated_at is too far in the future')


def ingest_context_snapshot(
    uid: str,
    snapshot: NormalizedContextSnapshot,
    *,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
) -> SnapshotReceipt:
    checked_at = now or datetime.now(timezone.utc)
    _validate_snapshot_window(snapshot.generated_at, snapshot.expires_at, checked_at)
    return recommendation_db.replace_context_snapshot(uid, snapshot, firestore_client=firestore_client)


def ingest_open_loop_snapshot(
    uid: str,
    snapshot: OpenLoopSnapshot,
    *,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
) -> SnapshotReceipt:
    checked_at = now or datetime.now(timezone.utc)
    if snapshot.owner != uid:
        raise SnapshotValidationError('snapshot owner must match authenticated user')
    _validate_snapshot_window(snapshot.generated_at, snapshot.expires_at, checked_at)
    workstream = workstreams_db.get_workstream(uid, snapshot.workstream_id, firestore_client=firestore_client)
    workstream_status = getattr(getattr(workstream, 'status', None), 'value', getattr(workstream, 'status', None))
    if workstream is None or workstream_status != 'open':
        raise SnapshotValidationError('snapshot workstream must be canonical and owned by the authenticated user')
    return recommendation_db.replace_open_loop_snapshot(uid, snapshot, firestore_client=firestore_client)


__all__ = [
    'FACT_DEFINITION_VERSION',
    'POLICY_VERSION',
    'PROMPT_VERSION',
    'RecommendationJudgment',
    'SnapshotValidationError',
    'evaluate',
    'filter_shortlist',
    'get_debug_projection',
    'ingest_context_snapshot',
    'ingest_open_loop_snapshot',
    'record_feedback',
    'record_outcome',
    'register_intervention',
]
