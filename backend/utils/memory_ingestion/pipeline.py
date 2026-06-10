from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol

from pydantic import ValidationError

from utils.memory_ingestion.ids import StableIdFactory, stable_hash, stable_hmac
from utils.memory_ingestion.models import (
    ActorDescriptor,
    AuditTrace,
    CreateMemoryMutation,
    DerivedTriple,
    DroppedArtifactRecord,
    EntityOperation,
    EntityRef,
    EvidenceLinkMutation,
    EvidenceSpan,
    ExtractionMetadata,
    FrameObject,
    FrameResolution,
    InvalidateMemoryMutation,
    MemoryDecision,
    MemoryEventFrame,
    MemoryMutationPlan,
    MemoryPipelineInput,
    MemoryPipelineOutput,
    ModelManifest,
    Modality,
    MutationPrecondition,
    PipelineError,
    PipelineStats,
    RawContextEvent,
    RedactionRecord,
    RejectedItem,
    RelationshipOperation,
    ReviewItem,
    ReviewItemMutation,
    SensitivityClassification,
    SourceRef,
    StageTrace,
    TaskRouteMutation,
    TemporalScope,
    UserStateSnapshot,
    VectorDelete,
    VectorMutationPlan,
    VectorUpsert,
)
from utils.memory_ingestion.redaction import redact_payload, redact_text
from utils.memory_ingestion.stages.verify_output import verify_output


class ModelCallMode(str, Enum):
    live = "live"
    replay = "replay"
    stub = "stub"


class Clock(Protocol):
    def now(self) -> datetime:
        pass


class UtcClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class MemoryModelClient(Protocol):
    async def extract_frames(
        self,
        *,
        pipeline_input: MemoryPipelineInput,
        events: list[RawContextEvent],
        input_fingerprint: str,
        id_factory: StableIdFactory,
    ) -> list[MemoryEventFrame]:
        pass

    def manifest(self, pipeline_input: MemoryPipelineInput) -> ModelManifest:
        pass


class StubMemoryModelClient:
    async def extract_frames(
        self,
        *,
        pipeline_input: MemoryPipelineInput,
        events: list[RawContextEvent],
        input_fingerprint: str,
        id_factory: StableIdFactory,
    ) -> list[MemoryEventFrame]:
        frames: list[MemoryEventFrame] = []
        for event in events:
            frames.extend(_frames_from_structured_payload(event, pipeline_input.actor))
            frames.extend(_heuristic_frames_from_text(event, pipeline_input.actor))
        for frame in frames:
            frame.frame_id = _frame_id(frame, input_fingerprint, pipeline_input.config.ontology_version, id_factory)
        return frames

    def manifest(self, pipeline_input: MemoryPipelineInput) -> ModelManifest:
        return ModelManifest(
            extractor_model=pipeline_input.config.models.extractor_model,
            normalizer_model=pipeline_input.config.models.normalizer_model,
            entity_linker_model=pipeline_input.config.models.entity_linker_model,
            conflict_resolver_model=pipeline_input.config.models.conflict_resolver_model,
            provider_versions={"memory_ingestion": "stub.v1"},
            prompt_versions={"frame_extraction": "stub.v1"},
        )


class CoreMemoryPipeline:
    def __init__(
        self,
        *,
        model_client: MemoryModelClient | None = None,
        clock: Clock | None = None,
        private_fingerprint_key: str | None = None,
    ):
        self.model_client = model_client or StubMemoryModelClient()
        self.clock = clock or UtcClock()
        self.private_fingerprint_key = private_fingerprint_key

    async def run(self, pipeline_input: MemoryPipelineInput) -> MemoryPipelineOutput:
        stage_traces: list[StageTrace] = []
        errors: list[PipelineError] = []
        bootstrap_id_factory = StableIdFactory(pipeline_input.run_id)

        try:
            _validate_input(pipeline_input)
        except ValueError as exc:
            now = self.clock.now()
            errors.append(
                PipelineError(
                    error_id=bootstrap_id_factory.new_id("error", "validate", str(exc)),
                    stage_name="validate_redact_fingerprint",
                    severity="fatal",
                    code="invalid_input",
                    message=str(exc),
                )
            )
            return _failed_output(pipeline_input, errors, stage_traces, self.model_client.manifest(pipeline_input), now)

        redacted_input, redactions, dropped_artifacts = self._redact_input(pipeline_input, bootstrap_id_factory)
        input_fingerprint = _input_fingerprint(redacted_input)
        id_factory = StableIdFactory(input_fingerprint)
        private_fingerprint = None
        if redacted_input.config.output.include_private_input_fingerprint and self.private_fingerprint_key:
            private_fingerprint = f"pifp_{stable_hmac(self.private_fingerprint_key, input_fingerprint, length=40)}"

        redact_notes = ["hard-secret artifacts dropped before fingerprinting and extraction"]
        if dropped_artifacts:
            redact_notes.append(f"client_secret_scrub_miss: {len(dropped_artifacts)} artifact(s) dropped by backend")

        stage_traces.append(
            _stage_trace(
                "validate_redact_fingerprint",
                self.clock.now(),
                self.clock.now(),
                input_count=len(pipeline_input.raw_events),
                output_count=len(redactions) + len(dropped_artifacts),
                notes=redact_notes,
            )
        )

        redaction_frames, redaction_decisions, redaction_resolutions, redaction_rejections = [], [], [], []
        try:
            extracted_frames = await self.model_client.extract_frames(
                pipeline_input=redacted_input,
                events=redacted_input.raw_events,
                input_fingerprint=input_fingerprint,
                id_factory=id_factory,
            )
        except Exception as exc:
            errors.append(
                PipelineError(
                    error_id=id_factory.new_id("error", "extract_frames", str(exc)),
                    stage_name="extract_frames",
                    severity="error",
                    code="model_extraction_failed",
                    message=str(exc),
                )
            )
            extracted_frames = []

        frames = _dedupe_frames(redaction_frames + extracted_frames, id_factory)
        decisions, frame_resolutions = _decide_frames(
            frames,
            redaction_decisions,
            redaction_resolutions,
            redacted_input.user_state,
            redacted_input.config.routing,
            id_factory,
        )
        triples, relationship_ops = _compile_triples(
            frames,
            decisions,
            redacted_input.config.output.emit_diagnostic_triples_for_rejections,
            id_factory,
        )
        mutation_plan, vector_plan, review_items, rejected_items = _compile_mutations(
            frames,
            decisions,
            redaction_rejections,
            redacted_input,
            id_factory,
            self.clock.now(),
        )
        entity_ops = _compile_entity_ops(frames, id_factory)
        stage_traces.append(
            _stage_trace(
                "compile_output",
                self.clock.now(),
                self.clock.now(),
                input_count=len(frames),
                output_count=len(decisions),
            )
        )

        output = MemoryPipelineOutput(
            run_id=redacted_input.run_id,
            mode=redacted_input.mode,
            status="ok",
            input_fingerprint=input_fingerprint,
            private_input_fingerprint=private_fingerprint,
            pipeline_version=redacted_input.config.pipeline_version,
            ontology_version=redacted_input.config.ontology_version,
            config_version=redacted_input.config.config_version,
            model_manifest=self.model_client.manifest(redacted_input),
            event_frames=frames,
            frame_resolutions=frame_resolutions,
            derived_triples=triples,
            decisions=decisions,
            entity_ops=entity_ops,
            relationship_ops=relationship_ops,
            mutation_plan=mutation_plan,
            vector_plan=vector_plan,
            review_items=review_items,
            rejected_items=rejected_items,
            audit=AuditTrace(
                trace_id=id_factory.new_id("trace", redacted_input.run_id),
                run_id=redacted_input.run_id,
                stage_traces=stage_traces,
                redactions=redactions,
                dropped_artifacts=dropped_artifacts,
                prompt_call_refs=[],
                lint_results=[],
            ),
            stats=PipelineStats(
                raw_event_count=len(pipeline_input.raw_events),
                redaction_count=len(redactions),
                dropped_artifact_count=len(dropped_artifacts),
                event_frame_count=len(frames),
                decision_count=len(decisions),
                derived_triple_count=len(triples),
                create_count=len(mutation_plan.creates),
                review_count=len(review_items),
                rejected_count=len(rejected_items),
                vector_upsert_count=len(vector_plan.upserts),
                vector_delete_count=len(vector_plan.deletes),
            ),
            errors=errors,
        )
        lints = verify_output(output)
        output.audit.lint_results = lints
        if any(lint.severity == "error" for lint in lints):
            output.status = "partial"
            output.errors.extend(
                PipelineError(
                    error_id=id_factory.new_id("error", "verify_output", lint.code, lint.mutation_id, lint.frame_id),
                    stage_name="verify_output",
                    severity="error",
                    code=lint.code,
                    message=lint.message,
                    frame_id=lint.frame_id,
                )
                for lint in lints
                if lint.severity == "error"
            )
        if errors and output.status == "ok":
            output.status = "partial"
        return output

    def _redact_input(
        self,
        pipeline_input: MemoryPipelineInput,
        id_factory: StableIdFactory,
    ) -> tuple[MemoryPipelineInput, list[RedactionRecord], list[DroppedArtifactRecord]]:
        input_copy = copy.deepcopy(pipeline_input)
        redactions: list[RedactionRecord] = []
        dropped_artifacts: list[DroppedArtifactRecord] = []
        kept_events: list[RawContextEvent] = []
        for event in input_copy.raw_events:
            event_redactions: list[RedactionRecord] = []
            if event.text:
                event.text, text_redactions = redact_text(
                    event.text,
                    source_event_id=event.event_id,
                    id_factory=id_factory,
                    hmac_key=self.private_fingerprint_key,
                )
                event_redactions.extend(text_redactions)
            event.structured_payload, payload_redactions = redact_payload(
                event.structured_payload,
                source_event_id=event.event_id,
                id_factory=id_factory,
                hmac_key=self.private_fingerprint_key,
            )
            event_redactions.extend(payload_redactions)
            if event_redactions:
                redactions.extend(event_redactions)
                dropped_artifacts.append(
                    DroppedArtifactRecord(
                        dropped_id=id_factory.new_id("dropped", event.event_id, "secret"),
                        source_event_id=event.event_id,
                        reason="secret",
                        categories=sorted({redaction.category for redaction in event_redactions}),
                        source_type=input_copy.source.source_type,
                        source_id=input_copy.source.source_id,
                        app_id=event.source_ref.app_id,
                        timestamp=event.start_at or input_copy.source.captured_at,
                    )
                )
                continue
            kept_events.append(event)
        input_copy.raw_events = kept_events
        return input_copy, redactions, dropped_artifacts


def _validate_input(pipeline_input: MemoryPipelineInput) -> None:
    event_ids = [event.event_id for event in pipeline_input.raw_events]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("raw_events must have unique event_id values")
    if pipeline_input.mode == "production":
        return
    if not pipeline_input.raw_events:
        raise ValueError("raw_events must not be empty")


def _input_fingerprint(pipeline_input: MemoryPipelineInput) -> str:
    payload = pipeline_input.model_dump(mode="json", exclude={"run_id", "mode"})
    return f"ifp_{stable_hash(payload, length=40)}"


def _failed_output(
    pipeline_input: MemoryPipelineInput,
    errors: list[PipelineError],
    stage_traces: list[StageTrace],
    manifest: ModelManifest,
    now: datetime,
) -> MemoryPipelineOutput:
    id_factory = StableIdFactory(pipeline_input.run_id)
    empty_mutation_plan = MemoryMutationPlan(plan_id=id_factory.new_id("plan", "failed"))
    return MemoryPipelineOutput(
        run_id=pipeline_input.run_id,
        mode=pipeline_input.mode,
        status="failed",
        input_fingerprint="ifp_failed",
        pipeline_version=pipeline_input.config.pipeline_version,
        ontology_version=pipeline_input.config.ontology_version,
        config_version=pipeline_input.config.config_version,
        model_manifest=manifest,
        event_frames=[],
        frame_resolutions=[],
        derived_triples=[],
        decisions=[],
        entity_ops=[],
        relationship_ops=[],
        mutation_plan=empty_mutation_plan,
        vector_plan=VectorMutationPlan(),
        review_items=[],
        rejected_items=[],
        audit=AuditTrace(
            trace_id=id_factory.new_id("trace", pipeline_input.run_id, now.isoformat()),
            run_id=pipeline_input.run_id,
            stage_traces=stage_traces,
            redactions=[],
            dropped_artifacts=[],
            prompt_call_refs=[],
            lint_results=[],
        ),
        stats=PipelineStats(raw_event_count=len(pipeline_input.raw_events)),
        errors=errors,
    )


def _stage_trace(
    stage_name: str,
    started_at: datetime,
    finished_at: datetime,
    *,
    status: str = "ok",
    input_count: int | None = None,
    output_count: int | None = None,
    notes: list[str] | None = None,
) -> StageTrace:
    return StageTrace(
        stage_name=stage_name,
        status=status,  # type: ignore[arg-type]
        started_at=started_at,
        finished_at=finished_at,
        input_count=input_count,
        output_count=output_count,
        notes=notes or [],
    )


def _frames_from_structured_payload(event: RawContextEvent, actor: ActorDescriptor | None) -> list[MemoryEventFrame]:
    raw_frames = event.structured_payload.get("memory_frames") or event.structured_payload.get("candidate_frames") or []
    frames: list[MemoryEventFrame] = []
    if not isinstance(raw_frames, list):
        return frames
    for index, raw_frame in enumerate(raw_frames):
        if not isinstance(raw_frame, dict):
            continue
        frame_payload = dict(raw_frame)
        frame_payload.setdefault("subject", _actor_subject(actor).model_dump())
        frame_payload.setdefault("temporal", TemporalScope().model_dump())
        frame_payload.setdefault("modality", Modality().model_dump())
        frame_payload.setdefault("sensitivity", SensitivityClassification().model_dump())
        frame_payload.setdefault("evidence", [_evidence_for_event(event, index).model_dump()])
        frame_payload.setdefault("source_event_ids", [event.event_id])
        frame_payload.setdefault("extraction", ExtractionMetadata(source_block_id=event.event_id).model_dump())
        try:
            frames.append(MemoryEventFrame.model_validate(frame_payload))
        except ValidationError:
            continue
    return frames


def _heuristic_frames_from_text(event: RawContextEvent, actor: ActorDescriptor | None) -> list[MemoryEventFrame]:
    if not event.text:
        return []
    text = " ".join(event.text.split())
    patterns = [
        (r"\bremember that (?:i|the user) (?:like|likes|love|loves) (?P<object>[^.?!]+)", "preference", "likes"),
        (r"\b(?:i|the user) (?:like|likes|love|loves) (?P<object>[^.?!]+)", "preference", "likes"),
        (r"\b(?:i|the user) (?:prefer|prefers) (?P<object>[^.?!]+)", "preference", "prefers"),
        (r"\b(?:i|the user) (?:work|works) on (?P<object>[^.?!]+)", "project_fact", "works_on"),
        (r"\b(?:i|the user) (?:use|uses) (?P<object>[^.?!]+)", "project_fact", "uses"),
        (r"\b(?:i|the user) (?:need|needs) to (?P<object>[^.?!]+)", "task_candidate", "needs"),
    ]
    frames: list[MemoryEventFrame] = []
    for index, (pattern, frame_type, predicate) in enumerate(patterns):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        object_value = match.group("object").strip()
        if not object_value:
            continue
        confidence = "medium" if event.speaker and event.speaker.is_actor_user is not True else "high"
        uncertainty_reasons = [] if confidence == "high" else ["speaker_uncertain"]
        frames.append(
            MemoryEventFrame(
                frame_type=frame_type,  # type: ignore[arg-type]
                subject=_actor_subject(actor),
                predicate=predicate,
                object=FrameObject(object_type="literal", value=object_value, confidence=confidence),
                canonical_text=_canonical_text(predicate, object_value),
                original_text=text,
                durability="short_term" if frame_type == "task_candidate" else "medium_term",
                evidence=[_evidence_for_event(event, index, quote=match.group(0))],
                source_event_ids=[event.event_id],
                confidence=confidence,  # type: ignore[arg-type]
                uncertainty_reasons=uncertainty_reasons,  # type: ignore[arg-type]
                extraction=ExtractionMetadata(source_block_id=event.event_id, notes=["heuristic_stub"]),
                scope="conversation" if event.source_ref.conversation_id else "unknown",
                scope_ref=event.source_ref if event.source_ref.conversation_id else None,
            )
        )
        break
    return frames


def _actor_subject(actor: ActorDescriptor | None) -> EntityRef:
    name = "actor_user"
    entity_id = None
    if actor:
        entity_id = actor.user_id or actor.synthetic_user_id
        name = actor.display_name or name
    return EntityRef(entity_id=entity_id, entity_type="user", canonical_name=name, confidence="high")


def _canonical_text(predicate: str, object_value: str) -> str:
    if predicate == "likes":
        return f"User likes {object_value}."
    if predicate == "prefers":
        return f"User prefers {object_value}."
    if predicate == "works_on":
        return f"User works on {object_value}."
    if predicate == "uses":
        return f"User uses {object_value}."
    return f"User needs to {object_value}."


def _evidence_for_event(event: RawContextEvent, index: int, quote: str | None = None) -> EvidenceSpan:
    evidence_id = (
        f"evidence_{stable_hash(event.event_id, index, quote or event.text or event.structured_payload, length=20)}"
    )
    return EvidenceSpan(
        evidence_id=evidence_id,
        source_event_id=event.event_id,
        source_ref=event.source_ref,
        quote=quote,
        start_at=event.start_at,
        end_at=event.end_at,
        speaker=event.speaker,
    )


def _frame_id(
    frame: MemoryEventFrame,
    input_fingerprint: str,
    ontology_version: str,
    id_factory: StableIdFactory,
) -> str:
    source_evidence_ids = [evidence.evidence_id for evidence in frame.evidence]
    return id_factory.new_id(
        "frame",
        input_fingerprint,
        frame.canonical_text.casefold(),
        source_evidence_ids,
        ontology_version,
    )


def _positive_secret_signals(
    redactions: list[RedactionRecord],
    pipeline_input: MemoryPipelineInput,
    id_factory: StableIdFactory,
) -> tuple[list[MemoryEventFrame], list[MemoryDecision], list[FrameResolution], list[RejectedItem]]:
    frames: list[MemoryEventFrame] = []
    decisions: list[MemoryDecision] = []
    resolutions: list[FrameResolution] = []
    rejections: list[RejectedItem] = []
    events_by_id = {event.event_id: event for event in pipeline_input.raw_events}
    for redaction in redactions:
        event = events_by_id[redaction.source_event_id]
        evidence = _evidence_for_event(event, 0, quote=redaction.placeholder)
        frame = MemoryEventFrame(
            frame_id=id_factory.new_id("frame", "redaction", redaction.redaction_id),
            frame_type="sensitive_candidate",
            subject=_actor_subject(pipeline_input.actor),
            predicate="contains_secret",
            object=FrameObject(object_type="literal", value=redaction.placeholder, confidence="high"),
            canonical_text=f"Blocked {redaction.category} detected in source event.",
            temporal=TemporalScope(kind="instant", valid_at=event.start_at),
            modality=Modality(kind="asserted"),
            durability="ephemeral",
            sensitivity=SensitivityClassification(
                level="blocked",
                categories=[redaction.category if redaction.category in ("api_key", "password") else "credential"],
                auto_store_allowed=False,
                review_required=False,
            ),
            scope="conversation" if event.source_ref.conversation_id else "unknown",
            scope_ref=event.source_ref if event.source_ref.conversation_id else None,
            importance="critical",
            evidence=[evidence],
            source_event_ids=[event.event_id],
            confidence="high",
            extraction=ExtractionMetadata(extractor="deterministic_redaction", source_block_id=event.event_id),
        )
        decision = MemoryDecision(
            decision_id=id_factory.new_id("decision", frame.frame_id, "reject_secret"),
            frame_id=frame.frame_id or "",
            action="reject_secret",
            rationale="Credential or secret material is blocked by deterministic redaction policy.",
            confidence="high",
        )
        frames.append(frame)
        decisions.append(decision)
        resolutions.append(
            FrameResolution(
                frame_id=frame.frame_id or "",
                status="decisioned",
                decision_id=decision.decision_id,
                rationale="blocked secret was deterministically decisioned",
            )
        )
        rejections.append(
            RejectedItem(
                rejected_id=id_factory.new_id("rejected", decision.decision_id),
                frame_id=frame.frame_id or "",
                decision_id=decision.decision_id,
                reason="secret_or_credential",
                rationale=decision.rationale,
            )
        )
    return frames, decisions, resolutions, rejections


def _dedupe_frames(frames: list[MemoryEventFrame], id_factory: StableIdFactory) -> list[MemoryEventFrame]:
    seen: dict[tuple[str, str, str], str] = {}
    result: list[MemoryEventFrame] = []
    for frame in frames:
        if frame.frame_id is None:
            frame.frame_id = id_factory.new_id("frame", frame.canonical_text, frame.source_event_ids)
        key = (
            frame.subject.entity_type,
            (frame.subject.canonical_name or frame.subject.entity_id or "").casefold(),
            _normalized_text(frame.canonical_text),
        )
        if key in seen:
            frame.duplicate_of_frame_id = seen[key]
        else:
            seen[key] = frame.frame_id
        result.append(frame)
    return result


def _decide_frames(
    frames: list[MemoryEventFrame],
    existing_decisions: list[MemoryDecision],
    existing_resolutions: list[FrameResolution],
    user_state: UserStateSnapshot,
    routing,
    id_factory: StableIdFactory,
) -> tuple[list[MemoryDecision], list[FrameResolution]]:
    decisions_by_frame = {decision.frame_id: decision for decision in existing_decisions}
    resolutions_by_frame = {resolution.frame_id: resolution for resolution in existing_resolutions}
    decisions = list(existing_decisions)
    resolutions = list(existing_resolutions)
    active = user_state.active_memories + [
        memory for memory in user_state.reviewed_memories if memory.status == "active"
    ]
    rejected = user_state.rejected_memories
    for frame in frames:
        frame_id = frame.frame_id or ""
        if frame_id in decisions_by_frame or frame_id in resolutions_by_frame:
            continue
        if frame.duplicate_of_frame_id:
            resolutions.append(
                FrameResolution(
                    frame_id=frame_id,
                    status="merged",
                    merged_into_frame_id=frame.duplicate_of_frame_id,
                    rationale="same-run duplicate frame",
                )
            )
            continue
        decision = _decision_for_frame(frame, active, rejected, routing, id_factory)
        decisions.append(decision)
        resolutions.append(
            FrameResolution(
                frame_id=frame_id,
                status="decisioned",
                decision_id=decision.decision_id,
                rationale=decision.rationale,
            )
        )
    return decisions, resolutions


def _decision_for_frame(
    frame: MemoryEventFrame,
    active_memories,
    rejected_memories,
    routing,
    id_factory: StableIdFactory,
) -> MemoryDecision:
    frame_id = frame.frame_id or ""
    matching_active = None
    if frame.frame_type == "sensitive_candidate" or frame.sensitivity.level == "blocked":
        action = "reject_secret"
        rationale = "Credential or secret material is blocked."
    elif frame.frame_type == "task_candidate":
        action = "route_to_task" if routing.route_tasks else "reject_low_value"
        rationale = "Task-like frame belongs to action-item routing, not memory storage."
    elif frame.frame_type == "non_memory":
        action = "reject_noop"
        rationale = "Frame is explicitly not memory-worthy."
    elif frame.durability == "ephemeral":
        action = "reject_ephemeral"
        rationale = "Ephemeral frame should not become durable memory."
    else:
        matching_rejected = _find_matching_memory(frame, rejected_memories)
        matching_active = _find_matching_memory(frame, active_memories)
        conflicting_active = _find_conflicting_memory(frame, active_memories)
        if matching_rejected:
            action = "reject_matches_rejected"
            rationale = "Frame matches a previously rejected memory."
        elif (matching_active and matching_active.locked) or (conflicting_active and conflicting_active.locked):
            action = "route_to_review"
            rationale = "Frame conflicts or overlaps with a locked memory."
            matching_active = matching_active or conflicting_active
        elif (matching_active and matching_active.reviewed) or (conflicting_active and conflicting_active.reviewed):
            action = "route_to_review"
            rationale = "Reviewed memory is protected from automatic rewrite."
            matching_active = matching_active or conflicting_active
        elif conflicting_active and routing.allow_supersession:
            action = "supersede_memory"
            rationale = "Frame changes an active semantic claim; supersession preserves memory history."
            matching_active = conflicting_active
        elif matching_active:
            action = "attach_evidence"
            rationale = "Frame matches an active memory; attach evidence instead of recreating."
        elif frame.sensitivity.review_required or frame.sensitivity.level == "high":
            action = "route_to_review" if routing.review_sensitive else "reject_policy"
            rationale = "Sensitive memory requires review."
        elif frame.confidence == "high" and routing.auto_create_high_confidence:
            action = "create_memory"
            rationale = "High-confidence ordinary frame is eligible for active memory creation."
        elif _is_unknown_speaker_only_ordinary_frame(frame):
            action = "create_memory"
            rationale = "Ordinary first-person memory has only generic speaker-label uncertainty."
        elif frame.confidence == "medium" and routing.auto_create_medium_confidence:
            action = "create_memory"
            rationale = "Medium-confidence frame is eligible by routing config."
        elif frame.confidence == "low" and routing.review_low_confidence:
            action = "route_to_review"
            rationale = "Low-confidence frame requires review."
        else:
            action = "route_to_review"
            rationale = "Frame is not eligible for automatic memory creation."
    target = matching_active or _find_matching_memory(frame, active_memories)
    preconditions = []
    target_ids = []
    if target:
        target_ids = [target.memory_id]
        preconditions.append(
            MutationPrecondition(
                target_type="memory",
                target_id=target.memory_id,
                expected_updated_at=target.updated_at,
                expected_invalid_at=target.invalid_at,
                expected_status=target.status,
                expected_locked=target.locked,
            )
        )
    final_memory_text = (
        frame.canonical_text if action in ("create_memory", "update_memory", "supersede_memory") else None
    )
    if action == "route_to_review":
        final_memory_text = frame.canonical_text
    return MemoryDecision(
        decision_id=id_factory.new_id("decision", frame_id, action, target_ids),
        frame_id=frame_id,
        action=action,  # type: ignore[arg-type]
        target_memory_ids=target_ids,
        final_memory_text=final_memory_text,
        rationale=rationale,
        confidence=frame.confidence,
        uncertainty_reasons=frame.uncertainty_reasons,
        preconditions=preconditions,
    )


def _is_unknown_speaker_only_ordinary_frame(frame: MemoryEventFrame) -> bool:
    return (
        frame.confidence == "medium"
        and frame.sensitivity.level == "none"
        and frame.sensitivity.review_required is False
        and set(frame.uncertainty_reasons) == {"speaker_uncertain"}
    )


def _find_matching_memory(frame: MemoryEventFrame, memories):
    frame_text = _normalized_text(frame.canonical_text)
    for memory in memories:
        memory_text = _normalized_text(memory.normalized_text or memory.text)
        if frame_text == memory_text:
            return memory
    return None


def _find_conflicting_memory(frame: MemoryEventFrame, memories):
    if not (
        frame.predicate.startswith("no_longer_")
        or frame.modality.kind in ("negated", "past")
        or frame.polarity == "negative"
    ):
        return None
    frame_kind = _memory_kind(frame.frame_type)
    for memory in memories:
        if memory.kind and memory.kind != frame_kind:
            continue
        if frame.subject and memory.subject:
            frame_subject = frame.subject.entity_id or frame.subject.canonical_name
            memory_subject = memory.subject.entity_id or memory.subject.canonical_name
            if frame_subject and memory_subject and frame_subject != memory_subject:
                continue
        return memory
    return None


def _normalized_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _compile_triples(
    frames: list[MemoryEventFrame],
    decisions: list[MemoryDecision],
    include_diagnostic_rejections: bool,
    id_factory: StableIdFactory,
) -> tuple[list[DerivedTriple], list[RelationshipOperation]]:
    decision_by_frame = {decision.frame_id: decision for decision in decisions}
    triples: list[DerivedTriple] = []
    relationships: list[RelationshipOperation] = []
    for frame in frames:
        frame_id = frame.frame_id or ""
        decision = decision_by_frame.get(frame_id)
        if not decision:
            continue
        if decision.action.startswith("reject_") and not include_diagnostic_rejections:
            continue
        if decision.action == "route_to_task" or frame.frame_type in (
            "task_candidate",
            "non_memory",
            "sensitive_candidate",
        ):
            continue
        objects: list[tuple[str, FrameObject]] = []
        if frame.object:
            objects.append((frame.predicate, frame.object))
        for role, argument in frame.arguments.items():
            objects.append((f"{frame.predicate}_{role}", argument))
        for predicate, object_value in objects:
            triple = DerivedTriple(
                triple_id=id_factory.new_id(
                    "triple",
                    frame_id,
                    frame.subject.model_dump(mode="json"),
                    predicate,
                    object_value.model_dump(mode="json"),
                    frame.temporal.model_dump(mode="json"),
                ),
                source_frame_id=frame_id,
                subject=frame.subject,
                predicate=predicate,
                object=object_value,
                valid_at=frame.temporal.valid_at or frame.temporal.valid_from,
                valid_until=frame.temporal.valid_until,
                confidence=frame.confidence,
                uncertainty_reasons=frame.uncertainty_reasons,
                evidence=frame.evidence,
            )
            triples.append(triple)
            if frame.frame_type == "relationship":
                relationships.append(
                    RelationshipOperation(
                        op_id=id_factory.new_id("relationship_op", triple.triple_id),
                        action="create_relationship",
                        subject=frame.subject,
                        predicate=predicate,
                        object=object_value,
                        source_frame_id=frame_id,
                        evidence=frame.evidence,
                        confidence=frame.confidence,
                    )
                )
    return triples, relationships


def _compile_mutations(
    frames: list[MemoryEventFrame],
    decisions: list[MemoryDecision],
    existing_rejections: list[RejectedItem],
    pipeline_input: MemoryPipelineInput,
    id_factory: StableIdFactory,
    now: datetime,
) -> tuple[MemoryMutationPlan, VectorMutationPlan, list[ReviewItem], list[RejectedItem]]:
    frame_by_id = {frame.frame_id: frame for frame in frames}
    plan = MemoryMutationPlan(plan_id=id_factory.new_id("plan", pipeline_input.run_id))
    vector_plan = VectorMutationPlan()
    review_items: list[ReviewItem] = []
    rejected_items: list[RejectedItem] = list(existing_rejections)
    for decision in decisions:
        frame = frame_by_id.get(decision.frame_id)
        if not frame:
            continue
        source_refs = _source_refs_for_frame(frame)
        if decision.action == "create_memory":
            memory_id = id_factory.new_id("memory", decision.decision_id, frame.canonical_text)
            mutation = CreateMemoryMutation(
                mutation_id=id_factory.new_id("mutation", decision.decision_id, "create", memory_id),
                decision_id=decision.decision_id,
                frame_id=decision.frame_id,
                memory_id=memory_id,
                text=decision.final_memory_text or frame.canonical_text,
                kind=_memory_kind(frame.frame_type),
                subject=frame.subject,
                entities=_entities_for_frame(frame),
                status="active",
                confidence=decision.confidence,
                uncertainty_reasons=decision.uncertainty_reasons,
                source_refs=source_refs,
                evidence=frame.evidence,
                event_frame_ids=[decision.frame_id],
                ontology_version=pipeline_input.config.ontology_version,
                created_at=now,
            )
            plan.creates.append(mutation)
            vector_plan.upserts.append(
                VectorUpsert(
                    vector_id=memory_id,
                    namespace=pipeline_input.config.output.vector_namespace,
                    source_type="memory",
                    source_id=memory_id,
                    text=mutation.text,
                    metadata={
                        "run_id": pipeline_input.run_id,
                        "decision_id": decision.decision_id,
                        "frame_id": decision.frame_id,
                        "kind": mutation.kind,
                    },
                )
            )
        elif decision.action == "supersede_memory" and decision.target_memory_ids:
            old_memory_id = decision.target_memory_ids[0]
            new_memory_id = id_factory.new_id("memory", decision.decision_id, frame.canonical_text)
            plan.creates.append(
                CreateMemoryMutation(
                    mutation_id=id_factory.new_id("mutation", decision.decision_id, "create", new_memory_id),
                    decision_id=decision.decision_id,
                    frame_id=decision.frame_id,
                    memory_id=new_memory_id,
                    text=decision.final_memory_text or frame.canonical_text,
                    kind=_memory_kind(frame.frame_type),
                    subject=frame.subject,
                    entities=_entities_for_frame(frame),
                    status="active",
                    confidence=decision.confidence,
                    uncertainty_reasons=decision.uncertainty_reasons,
                    source_refs=source_refs,
                    evidence=frame.evidence,
                    event_frame_ids=[decision.frame_id],
                    ontology_version=pipeline_input.config.ontology_version,
                    created_at=now,
                )
            )
            plan.invalidations.append(
                InvalidateMemoryMutation(
                    mutation_id=id_factory.new_id("mutation", decision.decision_id, "invalidate", old_memory_id),
                    decision_id=decision.decision_id,
                    frame_id=decision.frame_id,
                    memory_id=old_memory_id,
                    reason="superseded",
                    superseded_by_memory_id=new_memory_id,
                    invalid_at=now,
                    preconditions=decision.preconditions,
                )
            )
            vector_plan.upserts.append(
                VectorUpsert(
                    vector_id=new_memory_id,
                    namespace=pipeline_input.config.output.vector_namespace,
                    source_type="memory",
                    source_id=new_memory_id,
                    text=decision.final_memory_text or frame.canonical_text,
                    metadata={
                        "run_id": pipeline_input.run_id,
                        "decision_id": decision.decision_id,
                        "frame_id": decision.frame_id,
                        "kind": _memory_kind(frame.frame_type),
                    },
                )
            )
            vector_plan.deletes.append(
                VectorDelete(
                    vector_id=old_memory_id,
                    namespace=pipeline_input.config.output.vector_namespace,
                    source_type="memory",
                    source_id=old_memory_id,
                    reason="superseded",
                )
            )
        elif decision.action == "attach_evidence" and decision.target_memory_ids:
            target_id = decision.target_memory_ids[0]
            plan.evidence_links.append(
                EvidenceLinkMutation(
                    mutation_id=id_factory.new_id("mutation", decision.decision_id, "evidence", target_id),
                    decision_id=decision.decision_id,
                    frame_id=decision.frame_id,
                    memory_id=target_id,
                    evidence=frame.evidence,
                    source_refs=source_refs,
                    preconditions=decision.preconditions,
                )
            )
        elif decision.action == "route_to_review":
            reason = _review_reason(frame, decision)
            review_id = id_factory.new_id("review", decision.decision_id)
            review_items.append(
                ReviewItem(
                    review_id=review_id,
                    frame_id=decision.frame_id,
                    decision_id=decision.decision_id,
                    proposed_memory_text=decision.final_memory_text,
                    reason=reason,
                    uncertainty_reasons=decision.uncertainty_reasons,
                    evidence=frame.evidence,
                )
            )
            plan.review_upserts.append(
                ReviewItemMutation(
                    mutation_id=id_factory.new_id("mutation", decision.decision_id, "review", review_id),
                    decision_id=decision.decision_id,
                    frame_id=decision.frame_id,
                    review_id=review_id,
                )
            )
        elif decision.action == "route_to_task":
            plan.task_routes.append(
                TaskRouteMutation(
                    mutation_id=id_factory.new_id("mutation", decision.decision_id, "task"),
                    decision_id=decision.decision_id,
                    frame_id=decision.frame_id,
                    task_text=frame.canonical_text,
                    source_refs=source_refs,
                )
            )
        elif decision.action.startswith("reject_"):
            if any(item.decision_id == decision.decision_id for item in rejected_items):
                continue
            rejected_items.append(
                RejectedItem(
                    rejected_id=id_factory.new_id("rejected", decision.decision_id),
                    frame_id=decision.frame_id,
                    decision_id=decision.decision_id,
                    reason=_rejected_reason(decision.action),
                    rationale=decision.rationale,
                )
            )
    return plan, vector_plan, review_items, rejected_items


def _source_refs_for_frame(frame: MemoryEventFrame) -> list[SourceRef]:
    refs = []
    for evidence in frame.evidence:
        if evidence.source_ref not in refs:
            refs.append(evidence.source_ref)
    return refs


def _entities_for_frame(frame: MemoryEventFrame) -> list[EntityRef]:
    entities = [frame.subject]
    if frame.object and frame.object.entity:
        entities.append(frame.object.entity)
    for argument in frame.arguments.values():
        if argument.entity:
            entities.append(argument.entity)
    return entities


def _memory_kind(frame_type: str) -> str:
    if frame_type in {
        "preference",
        "personal_fact",
        "project_fact",
        "relationship",
        "goal",
        "routine",
        "constraint",
        "skill",
        "interest",
        "decision",
    }:
        return frame_type
    return "other"


def _review_reason(frame: MemoryEventFrame, decision: MemoryDecision) -> str:
    if "speaker_uncertain" in decision.uncertainty_reasons:
        return "speaker_uncertain"
    if "subject_ambiguous" in decision.uncertainty_reasons:
        return "subject_ambiguous"
    if "conflicts_with_locked_memory" in decision.uncertainty_reasons or "locked" in decision.rationale:
        return "conflicts_with_locked_memory"
    if "conflicts_with_reviewed_memory" in decision.uncertainty_reasons or "Reviewed" in decision.rationale:
        return "conflicts_with_reviewed_memory"
    if frame.sensitivity.review_required:
        return "sensitive_requires_review"
    if decision.confidence == "low":
        return "low_confidence"
    return "other"


def _rejected_reason(action: str) -> str:
    return {
        "reject_secret": "secret_or_credential",
        "reject_ephemeral": "ephemeral",
        "reject_duplicate": "duplicate",
        "reject_matches_rejected": "matches_rejected_memory",
        "reject_policy": "policy_blocked",
        "reject_unsupported_inference": "unsupported_inference",
        "reject_low_value": "not_memory_worthy",
    }.get(action, "other")


def _compile_entity_ops(frames: list[MemoryEventFrame], id_factory: StableIdFactory) -> list[EntityOperation]:
    ops: list[EntityOperation] = []
    seen: set[str] = set()
    for frame in frames:
        for entity in _entities_for_frame(frame):
            key = entity.entity_id or f"{entity.entity_type}:{entity.canonical_name}"
            if not key or key in seen or entity.entity_type == "user":
                continue
            seen.add(key)
            ops.append(
                EntityOperation(
                    op_id=id_factory.new_id("entity_op", key),
                    action="no_op" if entity.entity_id else "create_entity",
                    entity=entity,
                    evidence=frame.evidence,
                    confidence=entity.confidence or frame.confidence,
                    uncertainty_reasons=frame.uncertainty_reasons,
                )
            )
    return ops
