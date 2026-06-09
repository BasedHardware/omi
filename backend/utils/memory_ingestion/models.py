from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ConfidenceLabel = Literal["high", "medium", "low"]
UncertaintyReason = Literal[
    "low_quality_transcript",
    "overlapping_speech",
    "speaker_uncertain",
    "subject_ambiguous",
    "entity_ambiguous",
    "entity_link_uncertain",
    "temporal_scope_unclear",
    "weak_evidence",
    "inferred_not_stated",
    "conflicts_with_existing_memory",
    "conflicts_with_locked_memory",
    "conflicts_with_reviewed_memory",
    "duplicate_near_match",
    "source_truncated",
    "translation_loss",
    "sensitive_requires_review",
    "policy_boundary",
    "unsupported_by_existing_state",
]
DurabilityLabel = Literal["ephemeral", "short_term", "medium_term", "long_term"]
PipelineMode = Literal["production", "shadow", "offline", "backfill"]
MemoryStatus = Literal["active", "inactive", "rejected", "review", "archived"]


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelConfig(StrictBaseModel):
    extractor_model: str = "stub"
    normalizer_model: str | None = None
    entity_linker_model: str | None = None
    conflict_resolver_model: str | None = None
    temperature: float = 0.0
    max_output_tokens: int | None = None


class ThresholdConfig(StrictBaseModel):
    duplicate_text_similarity: float = 0.92
    low_quality_stt_confidence: float = 0.55


class PolicyConfig(StrictBaseModel):
    block_credentials: bool = True
    review_high_sensitivity: bool = True
    reject_ephemeral: bool = True


class RoutingConfig(StrictBaseModel):
    auto_create_high_confidence: bool = True
    auto_create_medium_confidence: bool = False
    review_low_confidence: bool = True
    review_sensitive: bool = True
    allow_supersession: bool = True
    allow_reviewed_supersession: bool = False
    allow_locked_supersession: bool = False
    route_tasks: bool = True


class OutputConfig(StrictBaseModel):
    include_private_input_fingerprint: bool = False
    vector_namespace: str = "ns2"
    emit_diagnostic_triples_for_rejections: bool = False


class MemoryPipelineConfig(StrictBaseModel):
    config_version: str = "memory_pipeline_config.v1"
    pipeline_version: str = "memory_pipeline.v1"
    ontology_version: str = "omi_memory_ontology.v0"
    models: ModelConfig = Field(default_factory=ModelConfig)
    thresholds: ThresholdConfig = Field(default_factory=ThresholdConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)


class SourceRef(StrictBaseModel):
    conversation_id: str | None = None
    transcript_segment_id: str | None = None
    memory_id: str | None = None
    integration_id: str | None = None
    app_id: str | None = None
    document_id: str | None = None
    external_id: str | None = None
    fixture_id: str | None = None


class SourceDescriptor(StrictBaseModel):
    source_type: Literal[
        "conversation",
        "transcript",
        "desktop_rewind",
        "manual_note",
        "integration",
        "import",
        "developer_api",
        "benchmark_fixture",
    ]
    source_id: str
    source_uri: str | None = None
    captured_at: datetime | None = None
    timezone: str | None = None
    language: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActorDescriptor(StrictBaseModel):
    user_id: str | None = None
    synthetic_user_id: str | None = None
    display_name: str | None = None
    known_aliases: list[str] = Field(default_factory=list)
    locale: str | None = None


class SpeakerRef(StrictBaseModel):
    speaker_id: str | None = None
    label: str | None = None
    is_actor_user: bool | None = None
    person_id: str | None = None
    confidence: float | None = None
    source: Literal["diarization", "user_labeled", "integration", "inferred", "unknown"] = "unknown"


class EventQuality(StrictBaseModel):
    stt_confidence: float | None = None
    diarization_confidence: float | None = None
    ocr_confidence: float | None = None
    extraction_source_confidence: float | None = None
    is_partial: bool = False
    quality_flags: list[
        Literal[
            "low_audio_quality",
            "overlapping_speech",
            "speaker_uncertain",
            "ocr_noisy",
            "truncated",
            "translated",
            "provider_duplicate",
            "out_of_order",
            "unknown",
        ]
    ] = Field(default_factory=list)


class RawContextEvent(StrictBaseModel):
    event_id: str
    event_type: Literal[
        "transcript_segment",
        "conversation_summary",
        "conversation_metadata",
        "screen_ocr",
        "app_event",
        "manual_text",
        "calendar_event",
        "email_snippet",
        "document_snippet",
        "chat_message",
        "task_event",
        "other",
    ]
    text: str | None = None
    structured_payload: dict[str, Any] = Field(default_factory=dict)
    start_at: datetime | None = None
    end_at: datetime | None = None
    order: int | None = None
    speaker: SpeakerRef | None = None
    source_ref: SourceRef
    quality: EventQuality = Field(default_factory=EventQuality)
    visibility: Literal["private", "shared", "public", "unknown"] = "unknown"


class EntityRef(StrictBaseModel):
    entity_id: str | None = None
    entity_type: Literal[
        "user",
        "person",
        "organization",
        "project",
        "product",
        "place",
        "event",
        "task",
        "concept",
        "unknown",
    ]
    canonical_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    confidence: ConfidenceLabel | None = None


class EntitySnapshot(StrictBaseModel):
    entity: EntityRef
    external_refs: list[SourceRef] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    merged_entity_ids: list[str] = Field(default_factory=list)


class RelationshipSnapshot(StrictBaseModel):
    relationship_id: str | None = None
    subject: EntityRef
    predicate: str
    object: EntityRef
    confidence: ConfidenceLabel | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)


class SpeakerProfileSnapshot(StrictBaseModel):
    speaker_id: str
    person: EntityRef | None = None
    label: str | None = None
    confidence: ConfidenceLabel | None = None


class ExistingMemorySnapshot(StrictBaseModel):
    memory_id: str
    text: str
    normalized_text: str | None = None
    kind: str | None = None
    status: MemoryStatus = "active"
    locked: bool = False
    reviewed: bool = False
    rejected: bool = False
    origin: Literal["manual", "auto", "import", "developer_api", "unknown"] = "unknown"
    created_at: datetime | None = None
    updated_at: datetime | None = None
    invalid_at: datetime | None = None
    subject: EntityRef | None = None
    entities: list[EntityRef] = Field(default_factory=list)
    event_frame_ids: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    confidence: ConfidenceLabel | None = None
    uncertainty_reasons: list[UncertaintyReason] = Field(default_factory=list)
    supersedes: list[str] = Field(default_factory=list)
    superseded_by: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class UserStateSnapshot(StrictBaseModel):
    snapshot_id: str
    snapshot_at: datetime
    active_memories: list[ExistingMemorySnapshot] = Field(default_factory=list)
    inactive_memories: list[ExistingMemorySnapshot] = Field(default_factory=list)
    rejected_memories: list[ExistingMemorySnapshot] = Field(default_factory=list)
    reviewed_memories: list[ExistingMemorySnapshot] = Field(default_factory=list)
    entities: list[EntitySnapshot] = Field(default_factory=list)
    relationships: list[RelationshipSnapshot] = Field(default_factory=list)
    speaker_profiles: list[SpeakerProfileSnapshot] = Field(default_factory=list)
    user_profile: dict[str, Any] = Field(default_factory=dict)


class MemoryPipelineInput(StrictBaseModel):
    schema_version: Literal["memory_pipeline_input.v1"] = "memory_pipeline_input.v1"
    run_id: str
    mode: PipelineMode
    source: SourceDescriptor
    actor: ActorDescriptor | None = None
    user_state: UserStateSnapshot
    raw_events: list[RawContextEvent]
    config: MemoryPipelineConfig = Field(default_factory=MemoryPipelineConfig)


class TemporalScope(StrictBaseModel):
    kind: Literal["unknown", "instant", "range", "recurring", "habitual", "open_ended", "historical"] = "unknown"
    valid_at: datetime | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    recurrence: str | None = None
    text: str | None = None


class Modality(StrictBaseModel):
    kind: Literal["asserted", "desired", "planned", "considered", "hypothetical", "negated", "past", "uncertain"] = (
        "asserted"
    )
    text: str | None = None


class SensitivityClassification(StrictBaseModel):
    level: Literal["none", "low", "medium", "high", "blocked"] = "none"
    categories: list[
        Literal[
            "credential",
            "api_key",
            "password",
            "financial_account",
            "government_id",
            "health",
            "mental_health",
            "biometric",
            "precise_location",
            "third_party_private_fact",
            "work_confidential",
            "minor",
            "ordinary_personal_fact",
            "ordinary_work_fact",
            "none",
        ]
    ] = Field(default_factory=lambda: ["none"])
    auto_store_allowed: bool = True
    review_required: bool = False


class FrameObject(StrictBaseModel):
    object_type: Literal["entity", "literal", "date", "time_range", "quantity", "structured", "unknown"]
    value: str | int | float | bool | dict[str, Any] | None = None
    entity: EntityRef | None = None
    unit: str | None = None
    confidence: ConfidenceLabel | None = None


class EvidenceSpan(StrictBaseModel):
    evidence_id: str
    source_event_id: str
    source_ref: SourceRef
    quote: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    speaker: SpeakerRef | None = None


class ExtractionMetadata(StrictBaseModel):
    extractor: str = "stub"
    model: str | None = None
    prompt_version: str | None = None
    source_block_id: str | None = None
    notes: list[str] = Field(default_factory=list)


class MemoryEventFrame(StrictBaseModel):
    frame_id: str | None = None
    frame_type: Literal[
        "personal_fact",
        "preference",
        "relationship",
        "goal",
        "routine",
        "constraint",
        "decision",
        "project_fact",
        "skill",
        "interest",
        "life_event",
        "task_candidate",
        "sensitive_candidate",
        "non_memory",
    ]
    subject: EntityRef
    predicate: str
    object: FrameObject | None = None
    arguments: dict[str, FrameObject] = Field(default_factory=dict)
    canonical_text: str
    original_text: str | None = None
    temporal: TemporalScope = Field(default_factory=TemporalScope)
    modality: Modality = Field(default_factory=Modality)
    polarity: Literal["positive", "negative", "neutral"] = "neutral"
    durability: DurabilityLabel = "medium_term"
    sensitivity: SensitivityClassification = Field(default_factory=SensitivityClassification)
    scope: Literal["global", "project", "person", "conversation", "episode", "unknown"] = "unknown"
    scope_ref: EntityRef | SourceRef | None = None
    importance: Literal["critical", "high", "medium", "low"] = "medium"
    evidence: list[EvidenceSpan]
    source_event_ids: list[str]
    confidence: ConfidenceLabel
    uncertainty_reasons: list[UncertaintyReason] = Field(default_factory=list)
    extraction: ExtractionMetadata = Field(default_factory=ExtractionMetadata)
    normalized_from_frame_ids: list[str] = Field(default_factory=list)
    duplicate_of_frame_id: str | None = None


class DerivedTriple(StrictBaseModel):
    triple_id: str
    source_frame_id: str
    subject: EntityRef
    predicate: str
    object: FrameObject
    valid_at: datetime | None = None
    valid_until: datetime | None = None
    asserted_at: datetime | None = None
    confidence: ConfidenceLabel
    uncertainty_reasons: list[UncertaintyReason] = Field(default_factory=list)
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class MutationPrecondition(StrictBaseModel):
    target_type: Literal["memory", "entity", "relationship"]
    target_id: str
    expected_updated_at: datetime | None = None
    expected_invalid_at: datetime | None = None
    expected_status: str | None = None
    expected_locked: bool | None = None


class MemoryDecision(StrictBaseModel):
    decision_id: str
    frame_id: str
    action: Literal[
        "create_memory",
        "update_memory",
        "supersede_memory",
        "merge_duplicate",
        "attach_evidence",
        "route_to_review",
        "route_to_task",
        "reject_noop",
        "reject_low_value",
        "reject_ephemeral",
        "reject_duplicate",
        "reject_matches_rejected",
        "reject_secret",
        "reject_policy",
        "reject_unsupported_inference",
    ]
    target_memory_ids: list[str] = Field(default_factory=list)
    target_entity_ids: list[str] = Field(default_factory=list)
    final_memory_text: str | None = None
    rationale: str
    confidence: ConfidenceLabel
    uncertainty_reasons: list[UncertaintyReason] = Field(default_factory=list)
    preconditions: list[MutationPrecondition] = Field(default_factory=list)


class FrameResolution(StrictBaseModel):
    frame_id: str
    status: Literal["decisioned", "merged", "dropped"]
    decision_id: str | None = None
    merged_into_frame_id: str | None = None
    rationale: str


class CreateMemoryMutation(StrictBaseModel):
    mutation_id: str
    decision_id: str
    frame_id: str
    memory_id: str
    text: str
    kind: str
    subject: EntityRef
    entities: list[EntityRef]
    status: Literal["active", "review"]
    confidence: ConfidenceLabel
    uncertainty_reasons: list[UncertaintyReason]
    source_refs: list[SourceRef]
    evidence: list[EvidenceSpan]
    event_frame_ids: list[str]
    ontology_version: str
    created_at: datetime | None = None


class UpdateMemoryMutation(StrictBaseModel):
    mutation_id: str
    decision_id: str
    frame_id: str
    memory_id: str
    new_text: str | None = None
    add_entities: list[EntityRef] = Field(default_factory=list)
    add_source_refs: list[SourceRef] = Field(default_factory=list)
    add_evidence: list[EvidenceSpan] = Field(default_factory=list)
    add_event_frame_ids: list[str] = Field(default_factory=list)
    confidence: ConfidenceLabel
    uncertainty_reasons: list[UncertaintyReason]
    preconditions: list[MutationPrecondition]


class InvalidateMemoryMutation(StrictBaseModel):
    mutation_id: str
    decision_id: str
    frame_id: str
    memory_id: str
    reason: Literal["superseded", "contradicted", "merged", "user_rejected", "stale"]
    superseded_by_memory_id: str | None = None
    invalid_at: datetime | None = None
    preconditions: list[MutationPrecondition]


class EvidenceLinkMutation(StrictBaseModel):
    mutation_id: str
    decision_id: str
    frame_id: str
    memory_id: str
    evidence: list[EvidenceSpan]
    source_refs: list[SourceRef]
    preconditions: list[MutationPrecondition]


class ReviewItemMutation(StrictBaseModel):
    mutation_id: str
    decision_id: str
    frame_id: str
    review_id: str


class TaskRouteMutation(StrictBaseModel):
    mutation_id: str
    decision_id: str
    frame_id: str
    task_text: str
    source_refs: list[SourceRef]


class MemoryMutationPlan(StrictBaseModel):
    plan_id: str
    creates: list[CreateMemoryMutation] = Field(default_factory=list)
    updates: list[UpdateMemoryMutation] = Field(default_factory=list)
    invalidations: list[InvalidateMemoryMutation] = Field(default_factory=list)
    evidence_links: list[EvidenceLinkMutation] = Field(default_factory=list)
    review_upserts: list[ReviewItemMutation] = Field(default_factory=list)
    task_routes: list[TaskRouteMutation] = Field(default_factory=list)


class VectorUpsert(StrictBaseModel):
    vector_id: str
    namespace: str
    source_type: Literal["memory", "conversation", "entity", "relationship"]
    source_id: str
    text: str
    metadata: dict[str, Any]


class VectorDelete(StrictBaseModel):
    vector_id: str | None = None
    namespace: str
    source_type: Literal["memory", "conversation", "entity", "relationship"]
    source_id: str
    reason: Literal["superseded", "updated", "invalidated", "rejected", "deleted"]


class VectorMutationPlan(StrictBaseModel):
    upserts: list[VectorUpsert] = Field(default_factory=list)
    deletes: list[VectorDelete] = Field(default_factory=list)


class EntityOperation(StrictBaseModel):
    op_id: str
    action: Literal["create_entity", "update_entity", "merge_entities", "no_op"]
    entity: EntityRef
    target_entity_ids: list[str] = Field(default_factory=list)
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    confidence: ConfidenceLabel
    uncertainty_reasons: list[UncertaintyReason] = Field(default_factory=list)


class RelationshipOperation(StrictBaseModel):
    op_id: str
    action: Literal["create_relationship", "update_relationship", "invalidate_relationship", "no_op"]
    subject: EntityRef
    predicate: str
    object: FrameObject
    source_frame_id: str
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    confidence: ConfidenceLabel


class ReviewItem(StrictBaseModel):
    review_id: str
    frame_id: str
    decision_id: str
    proposed_memory_text: str | None
    reason: Literal[
        "low_confidence",
        "subject_ambiguous",
        "speaker_uncertain",
        "sensitive_requires_review",
        "conflicts_with_locked_memory",
        "conflicts_with_reviewed_memory",
        "entity_ambiguous",
        "high_impact_update",
        "other",
    ]
    uncertainty_reasons: list[UncertaintyReason]
    evidence: list[EvidenceSpan]


class RejectedItem(StrictBaseModel):
    rejected_id: str
    frame_id: str
    decision_id: str
    reason: Literal[
        "not_memory_worthy",
        "ephemeral",
        "duplicate",
        "matches_rejected_memory",
        "secret_or_credential",
        "policy_blocked",
        "unsupported_inference",
        "low_quality_source",
        "task_not_memory",
        "other",
    ]
    rationale: str


class RedactionRecord(StrictBaseModel):
    redaction_id: str
    source_event_id: str
    category: Literal["api_key", "password", "private_key", "token", "cookie", "database_url", "unknown_secret"]
    placeholder: str
    char_start: int | None = None
    char_end: int | None = None
    payload_path: str | None = None
    value_hash: str | None = None


class StageTrace(StrictBaseModel):
    stage_name: str
    status: Literal["ok", "partial", "failed"]
    started_at: datetime
    finished_at: datetime
    input_count: int | None = None
    output_count: int | None = None
    notes: list[str] = Field(default_factory=list)


class PromptCallRef(StrictBaseModel):
    call_id: str
    stage_name: str
    model: str
    prompt_version: str | None = None
    input_fingerprint: str | None = None
    output_fingerprint: str | None = None


class LintResult(StrictBaseModel):
    lint_id: str
    severity: Literal["warning", "error"]
    code: str
    message: str
    frame_id: str | None = None
    decision_id: str | None = None
    mutation_id: str | None = None


class AuditTrace(StrictBaseModel):
    trace_id: str
    run_id: str
    stage_traces: list[StageTrace]
    redactions: list[RedactionRecord]
    prompt_call_refs: list[PromptCallRef]
    lint_results: list[LintResult]


class PipelineStats(StrictBaseModel):
    raw_event_count: int = 0
    redaction_count: int = 0
    event_frame_count: int = 0
    decision_count: int = 0
    derived_triple_count: int = 0
    create_count: int = 0
    review_count: int = 0
    rejected_count: int = 0
    vector_upsert_count: int = 0
    vector_delete_count: int = 0


class PipelineError(StrictBaseModel):
    error_id: str
    stage_name: str
    severity: Literal["warning", "error", "fatal"]
    code: str
    message: str
    frame_id: str | None = None
    source_event_id: str | None = None


class ModelManifest(StrictBaseModel):
    extractor_model: str
    normalizer_model: str | None = None
    entity_linker_model: str | None = None
    conflict_resolver_model: str | None = None
    embedding_model: str | None = None
    provider_versions: dict[str, str] = Field(default_factory=dict)
    prompt_versions: dict[str, str] = Field(default_factory=dict)


class MemoryPipelineOutput(StrictBaseModel):
    schema_version: Literal["memory_pipeline_output.v1"] = "memory_pipeline_output.v1"
    run_id: str
    mode: PipelineMode
    status: Literal["ok", "partial", "failed"]
    input_fingerprint: str
    private_input_fingerprint: str | None = None
    pipeline_version: str
    ontology_version: str
    config_version: str
    model_manifest: ModelManifest
    event_frames: list[MemoryEventFrame]
    frame_resolutions: list[FrameResolution]
    derived_triples: list[DerivedTriple]
    decisions: list[MemoryDecision]
    entity_ops: list[EntityOperation]
    relationship_ops: list[RelationshipOperation]
    mutation_plan: MemoryMutationPlan
    vector_plan: VectorMutationPlan
    review_items: list[ReviewItem]
    rejected_items: list[RejectedItem]
    audit: AuditTrace
    stats: PipelineStats
    errors: list[PipelineError] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_benchmark_label_leakage(self):
        dumped = self.model_dump(mode="json")
        if "labels" in dumped:
            raise ValueError("core pipeline output must not contain benchmark labels")
        return self


class AppliedMemoryPipelineOutput(StrictBaseModel):
    run_id: str
    status: Literal["ok", "partial", "failed"]
    applied_mutation_ids: list[str] = Field(default_factory=list)
    skipped_mutation_ids: list[str] = Field(default_factory=list)
    errors: list[PipelineError] = Field(default_factory=list)
