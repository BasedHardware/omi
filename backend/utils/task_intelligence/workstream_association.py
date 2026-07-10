"""Canonical-memory evidence association into durable workflow workstreams."""

import hashlib
import json
import logging
from collections.abc import Callable, Iterable
from typing import Any, Optional, Protocol, cast

import database.recurrence_inbox as recurrence_inbox_db
import database.workstreams as workstreams_db
from database.vector_db import (
    delete_workstream_association_vector,
    query_workstream_association_candidates,
)
from models.action_item import TaskCreatePayload
from models.candidate import CandidateCreate, WorkstreamCreateCandidate, WorkstreamProposal
from models.memory_recurrence import CanonicalRecurrenceSignal
from models.task_intelligence import TaskWorkflowMode
from models.workstream import (
    Workstream,
    WorkstreamEventCreate,
    WorkstreamEventKind,
    WorkstreamSensitivity,
    WorkstreamStatus,
)
from models.workstream_association import (
    AssociationAdjudicationInput,
    AssociationCandidateView,
    AssociationEvidence,
    AssociationJudgment,
    AssociationOutcome,
    AssociationOutcomeKind,
    AssociationReason,
    RecurrenceConsumptionOutcome,
    RecurrenceInboxReceipt,
    RecurrenceOutcomeKind,
)
from utils.llm.gateway_client import invoke_chat_structured_gateway
from utils.memory.memory_system import MemorySystem, resolve_memory_system
from utils.metrics import TASK_WORKSTREAM_ASSOCIATION_TOTAL
from utils.observability.fallback import record_fallback
from utils.task_intelligence import candidate_service
from utils.task_intelligence.workstream_index import rebuild_workstream_association_index

ASSOCIATION_POLICY_VERSION = 'association.v1'
ASSOCIATION_INDEX_VERSION = 'workstream-association-v1'
ASSOCIATION_TOP_K = 5
RECURRENCE_POLICY_VERSION = 'recurrence.v1'
RECURRENCE_MIN_OCCURRENCES = 2
RECURRENCE_MIN_DISTINCT_DAYS = 2
RECURRENCE_MIN_CONFIDENCE = 0.7

AssociationTelemetry = Callable[[AssociationOutcomeKind], None]
logger = logging.getLogger(__name__)


class AssociationAdjudicator(Protocol):
    def __call__(self, request: AssociationAdjudicationInput) -> AssociationJudgment: ...


ASSOCIATION_PROMPT_V1 = """You associate one minimized canonical-memory evidence summary with an existing workstream.

Workstreams cluster by intent and outcome, not entity overlap. Select a workstream
only when the evidence advances, changes, blocks, unblocks, or stales that exact
objective. A person or company name alone is never enough. If the evidence belongs
but is immaterial, return that workstream with material=false and reason=immaterial.
If no candidate clearly matches, return no workstream and reason=no_match or ambiguous.
For a material match, event_summary is required: express only the new state change in
500 characters or fewer. It must be a fresh minimized abstraction, never a copy of
the evidence summary. For every non-material result, omit event_summary.

Input JSON:
{payload}
"""


def _default_adjudicator(request: AssociationAdjudicationInput) -> AssociationJudgment:
    prompt = ASSOCIATION_PROMPT_V1.format(payload=request.model_dump_json())
    result = invoke_chat_structured_gateway(
        prompt,
        AssociationJudgment,
        feature='workstream_association',
    )
    if result is None:
        return AssociationJudgment(material=False, reason=AssociationReason.model_unavailable)
    return AssociationJudgment.model_validate(result)


def _association_idempotency_key(evidence: AssociationEvidence, workstream_id: str) -> str:
    refs = [
        {
            'kind': ref.kind.value,
            'id': ref.id,
            'version': ref.version,
            'scope': ref.scope.value,
            'device_id': ref.device_id,
        }
        for ref in evidence.evidence_refs
    ]
    conversation_refs = [ref for ref in refs if ref['kind'] == 'conversation']
    if conversation_refs:
        refs = conversation_refs
    payload = json.dumps(
        {'policy': ASSOCIATION_POLICY_VERSION, 'workstream_id': workstream_id, 'refs': refs},
        sort_keys=True,
        separators=(',', ':'),
    )
    return f'association_{hashlib.sha256(payload.encode("utf-8")).hexdigest()[:40]}'


def associate_canonical_evidence(
    uid: str,
    evidence: AssociationEvidence,
    *,
    account_generation: Optional[int] = None,
    firestore_client: Any = None,
    retrieve_ids: Callable[..., list[str]] = query_workstream_association_candidates,
    hydrate: Callable[..., Optional[Workstream]] = workstreams_db.get_workstream,
    purge_stale: Callable[[str, str], bool] = delete_workstream_association_vector,
    adjudicate: AssociationAdjudicator = _default_adjudicator,
    append_event: Callable[..., Any] = workstreams_db.append_workstream_event,
    telemetry: Optional[AssociationTelemetry] = None,
) -> AssociationOutcome:
    """Retrieve, hydrate, adjudicate, and append one minimized material event."""

    def finish(outcome: AssociationOutcome) -> AssociationOutcome:
        reason = outcome.judgment_reason.value if outcome.judgment_reason else 'none'
        TASK_WORKSTREAM_ASSOCIATION_TOTAL.labels(outcome=outcome.outcome.value, reason=reason).inc()
        logger.info(
            'workstream_association outcome=%s reason=%s retrieved_ids=%s hydrated_ids=%s workstream_id=%s',
            outcome.outcome.value,
            reason,
            outcome.retrieved_candidate_ids,
            outcome.hydrated_candidate_ids,
            outcome.workstream_id or 'none',
        )
        if telemetry is not None:
            telemetry(outcome.outcome)
        return outcome

    if resolve_memory_system(uid, db_client=firestore_client) != MemorySystem.CANONICAL:
        return finish(AssociationOutcome(outcome=AssociationOutcomeKind.not_canonical_cohort))
    control = workstreams_db.get_task_workflow_control(uid, firestore_client=firestore_client)
    if control.workflow_mode == TaskWorkflowMode.off:
        return finish(AssociationOutcome(outcome=AssociationOutcomeKind.workflow_disabled))

    retrieved_ids = list(dict.fromkeys(retrieve_ids(uid, evidence.summary, limit=ASSOCIATION_TOP_K)))
    candidates: list[Workstream] = []
    for workstream_id in retrieved_ids:
        workstream = hydrate(uid, workstream_id, firestore_client=firestore_client)
        if workstream is None or workstream.status != WorkstreamStatus.open:
            purge_stale(uid, workstream_id)
            continue
        candidates.append(workstream)
        if len(candidates) == ASSOCIATION_TOP_K:
            break
    hydrated_ids = [item.workstream_id for item in candidates]
    if not candidates:
        return finish(
            AssociationOutcome(
                outcome=AssociationOutcomeKind.no_candidates,
                retrieved_candidate_ids=retrieved_ids,
            )
        )

    request = AssociationAdjudicationInput(
        evidence_summary=evidence.summary,
        candidates=[
            AssociationCandidateView(
                workstream_id=item.workstream_id,
                objective=item.objective,
                current_state_summary=item.current_state_summary,
            )
            for item in candidates
        ],
    )
    judgment = adjudicate(request)
    if judgment.workstream_id not in set(hydrated_ids):
        return finish(
            AssociationOutcome(
                outcome=AssociationOutcomeKind.no_match,
                retrieved_candidate_ids=retrieved_ids,
                hydrated_candidate_ids=hydrated_ids,
                judgment_reason=judgment.reason,
            )
        )
    if not judgment.material:
        return finish(
            AssociationOutcome(
                outcome=AssociationOutcomeKind.immaterial,
                retrieved_candidate_ids=retrieved_ids,
                hydrated_candidate_ids=hydrated_ids,
                workstream_id=judgment.workstream_id,
                judgment_reason=judgment.reason,
            )
        )

    normalized_evidence = ' '.join(evidence.summary.casefold().split())
    normalized_event = ' '.join(cast(str, judgment.event_summary).casefold().split())
    if normalized_event in normalized_evidence or normalized_evidence in normalized_event:
        return finish(
            AssociationOutcome(
                outcome=AssociationOutcomeKind.minimization_rejected,
                retrieved_candidate_ids=retrieved_ids,
                hydrated_candidate_ids=hydrated_ids,
                workstream_id=judgment.workstream_id,
                judgment_reason=judgment.reason,
            )
        )
    if control.workflow_mode == TaskWorkflowMode.shadow:
        return finish(
            AssociationOutcome(
                outcome=AssociationOutcomeKind.would_append,
                retrieved_candidate_ids=retrieved_ids,
                hydrated_candidate_ids=hydrated_ids,
                workstream_id=judgment.workstream_id,
                judgment_reason=judgment.reason,
            )
        )

    event = append_event(
        uid,
        cast(str, judgment.workstream_id),
        WorkstreamEventCreate(
            kind=WorkstreamEventKind.system,
            summary=cast(str, judgment.event_summary),
            evidence_refs=evidence.evidence_refs,
            sensitivity=WorkstreamSensitivity.normal,
        ),
        idempotency_key=_association_idempotency_key(evidence, cast(str, judgment.workstream_id)),
        account_generation=control.account_generation if account_generation is None else account_generation,
        firestore_client=firestore_client,
        required_status=WorkstreamStatus.open,
    )
    return finish(
        AssociationOutcome(
            outcome=AssociationOutcomeKind.appended,
            retrieved_candidate_ids=retrieved_ids,
            hydrated_candidate_ids=hydrated_ids,
            workstream_id=judgment.workstream_id,
            event_id=event.event_id,
            judgment_reason=judgment.reason,
        )
    )


def _recurrence_idempotency_key(signal: CanonicalRecurrenceSignal) -> str:
    payload = f'{RECURRENCE_POLICY_VERSION}:{signal.stable_loop_key}'
    return f'recurrence_{hashlib.sha256(payload.encode("utf-8")).hexdigest()[:40]}'


def consume_recurrence_signal(
    uid: str,
    signal: CanonicalRecurrenceSignal,
    *,
    firestore_client: Any = None,
    create_candidate: Callable[..., Any] = candidate_service.create_candidate,
) -> RecurrenceConsumptionOutcome:
    if resolve_memory_system(uid, db_client=firestore_client) != MemorySystem.CANONICAL:
        return RecurrenceConsumptionOutcome(
            outcome=RecurrenceOutcomeKind.not_canonical_cohort,
            signal_id=signal.signal_id,
        )
    control = workstreams_db.get_task_workflow_control(uid, firestore_client=firestore_client)
    if control.workflow_mode == TaskWorkflowMode.off:
        return RecurrenceConsumptionOutcome(
            outcome=RecurrenceOutcomeKind.workflow_disabled,
            signal_id=signal.signal_id,
        )
    if (
        not signal.unresolved
        or signal.occurrence_count < RECURRENCE_MIN_OCCURRENCES
        or signal.distinct_day_count < RECURRENCE_MIN_DISTINCT_DAYS
        or signal.confidence < RECURRENCE_MIN_CONFIDENCE
    ):
        return RecurrenceConsumptionOutcome(
            outcome=RecurrenceOutcomeKind.below_threshold,
            signal_id=signal.signal_id,
        )

    idempotency_key = _recurrence_idempotency_key(signal)
    if control.workflow_mode == TaskWorkflowMode.shadow:
        return RecurrenceConsumptionOutcome(
            outcome=RecurrenceOutcomeKind.would_create,
            signal_id=signal.signal_id,
            idempotency_key=idempotency_key,
        )

    proposal = CandidateCreate(
        root=WorkstreamCreateCandidate(
            capture_confidence=signal.confidence,
            ownership_confidence=0.5,
            evidence_refs=signal.evidence_refs,
            source_surface='canonical_memory_recurrence',
            workstream_proposal=WorkstreamProposal(
                title=signal.title,
                objective=signal.objective,
                anchor_task=TaskCreatePayload(description=signal.anchor_task_description),
            ),
        )
    )
    candidate = create_candidate(
        uid,
        proposal,
        idempotency_key=idempotency_key,
        account_generation=control.account_generation,
    )
    return RecurrenceConsumptionOutcome(
        outcome=RecurrenceOutcomeKind.candidate_created,
        signal_id=signal.signal_id,
        candidate_id=candidate.candidate_id,
        idempotency_key=idempotency_key,
    )


def persist_recurrence_signals_for_maintenance(
    uid: str,
    signals: Iterable[CanonicalRecurrenceSignal],
    *,
    firestore_client: Any = None,
    enqueue: Callable[..., RecurrenceInboxReceipt] = recurrence_inbox_db.enqueue_recurrence_signal,
) -> int:
    """Durably hand off a consolidation batch before its memory watermark advances."""
    control = workstreams_db.get_task_workflow_control(uid, firestore_client=firestore_client)
    signal_list = list(signals)
    if control.workflow_mode == TaskWorkflowMode.shadow:
        return sum(
            consume_recurrence_signal(uid, signal, firestore_client=firestore_client).outcome
            == RecurrenceOutcomeKind.would_create
            for signal in signal_list
        )
    if control.workflow_mode == TaskWorkflowMode.off:
        return 0

    persisted = 0
    for signal in signal_list:
        try:
            enqueue(
                uid,
                signal,
                account_generation=control.account_generation,
                firestore_client=firestore_client,
            )
            persisted += 1
        except Exception:
            record_fallback(
                component='other',
                from_mode='recurrence_signal',
                to_mode='recurrence_inbox_retry',
                reason='enqueue_failed',
                outcome='degraded',
            )
            raise
    return persisted


def drain_recurrence_inbox_for_maintenance(
    uid: str,
    signals: Iterable[CanonicalRecurrenceSignal] = (),
    *,
    firestore_client: Any = None,
    list_pending: Callable[..., list[RecurrenceInboxReceipt]] = recurrence_inbox_db.list_pending_recurrence_receipts,
    complete: Callable[..., None] = recurrence_inbox_db.complete_recurrence_receipt,
    retry: Callable[..., None] = recurrence_inbox_db.retry_recurrence_receipt,
) -> int:
    control = workstreams_db.get_task_workflow_control(uid, firestore_client=firestore_client)
    if control.workflow_mode in {TaskWorkflowMode.off, TaskWorkflowMode.shadow}:
        return 0

    created = 0
    receipts = list_pending(
        uid,
        account_generation=control.account_generation,
        firestore_client=firestore_client,
    )
    for receipt in receipts:
        try:
            result = consume_recurrence_signal(uid, receipt.signal, firestore_client=firestore_client)
            complete(
                uid,
                receipt.receipt_id,
                outcome=result.outcome,
                firestore_client=firestore_client,
            )
            created += int(result.outcome == RecurrenceOutcomeKind.candidate_created)
        except Exception as exc:
            retry(
                uid,
                receipt.receipt_id,
                error_code=type(exc).__name__,
                firestore_client=firestore_client,
            )
            record_fallback(
                component='other',
                from_mode='recurrence_inbox',
                to_mode='recurrence_inbox_retry',
                reason='other',
                outcome='degraded',
            )
    return created


def consume_recurrence_signals_for_maintenance(
    uid: str,
    signals: Iterable[CanonicalRecurrenceSignal],
    *,
    firestore_client: Any = None,
    enqueue: Callable[..., RecurrenceInboxReceipt] = recurrence_inbox_db.enqueue_recurrence_signal,
    list_pending: Callable[..., list[RecurrenceInboxReceipt]] = recurrence_inbox_db.list_pending_recurrence_receipts,
    complete: Callable[..., None] = recurrence_inbox_db.complete_recurrence_receipt,
    retry: Callable[..., None] = recurrence_inbox_db.retry_recurrence_receipt,
) -> int:
    evaluated_or_persisted = persist_recurrence_signals_for_maintenance(
        uid,
        signals,
        firestore_client=firestore_client,
        enqueue=enqueue,
    )
    control = workstreams_db.get_task_workflow_control(uid, firestore_client=firestore_client)
    if control.workflow_mode == TaskWorkflowMode.shadow:
        return evaluated_or_persisted
    return drain_recurrence_inbox_for_maintenance(
        uid,
        firestore_client=firestore_client,
        list_pending=list_pending,
        complete=complete,
        retry=retry,
    )


__all__ = [
    'ASSOCIATION_INDEX_VERSION',
    'ASSOCIATION_POLICY_VERSION',
    'ASSOCIATION_PROMPT_V1',
    'associate_canonical_evidence',
    'consume_recurrence_signal',
    'consume_recurrence_signals_for_maintenance',
    'drain_recurrence_inbox_for_maintenance',
    'persist_recurrence_signals_for_maintenance',
    'rebuild_workstream_association_index',
]
