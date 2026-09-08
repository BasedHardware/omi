from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar, Literal
from enum import Enum

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
    auto_create_medium_confidence: bool = True  # relaxed from False post-hallucination-campaign
    review_uncertain: bool = True
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


class SourceStrength(str, Enum):
    """Signal quality tier for extraction behavior modulation."""

    HIGH = "high"  # chat_exchange, conversation — clean, intentional
    MEDIUM = "medium"  # voice_transcript, manual_note — some noise
    LOW = "low"  # transcript, desktop_rewind, ocr_screenshot_text, ambient_voice
    UNKNOWN = "unknown"  # benchmark_fixture


class SourceTypeConfig(StrictBaseModel):
    """Extensible per-source-type configuration for extraction behavior.

    To add a new source type:
      1. Add the literal to SourceDescriptor.source_type
      2. Add an entry here (or accept UNKNOWN defaults)
      3. Zero other code changes needed — prompt receives guidance string automatically.
    """

    strength: SourceStrength = SourceStrength.UNKNOWN
    label: str  # human-readable name for the prompt
    confidence_cap: float = 1.0
    requires_corroboration: bool = False
    default_empty_on_noise: bool = False
    guidance_notes: str = ""

    REGISTRY: ClassVar[dict[str, "SourceTypeConfig"]] = {}


# Build registry after class definition
def _build_source_type_registry() -> dict[str, SourceTypeConfig]:
    return {
        "chat_exchange": SourceTypeConfig(
            strength=SourceStrength.HIGH,
            label="CHAT EXCHANGE",
            confidence_cap=1.0,
            requires_corroboration=False,
            default_empty_on_noise=False,
            guidance_notes=(
                "Highest-confidence source. If the primary user explicitly states "
                "a fact about themselves, extract it. Do NOT suppress clear claims. "
                "Assistant-authored turns are contextual evidence only: extract them "
                "with subject_attribution=assistant_suggested when they name a "
                "specific, personalized, grounded user task/tool/setting (for example "
                "a USCIS form or MacBook resolution recommendation). Do NOT extract "
                "generic assistant praise, 'back to work' nudges, app-switch reminders "
                "(Telegram/Discord/X), broad Omi encouragement, or name-only mentions. "
                "Chat messages often contain MULTIPLE facts — extract each one. "
                "Informal language, profanity, non-English, and casual chitchat "
                "wrapping do NOT invalidate a clear factual signal."
            ),
        ),
        "conversation": SourceTypeConfig(
            strength=SourceStrength.HIGH,
            label="CONVERSATION",
            confidence_cap=1.0,
            requires_corroboration=False,
            default_empty_on_noise=False,
            guidance_notes="High-confidence multi-party conversation. Standard extraction rules apply.",
        ),
        "voice_transcript": SourceTypeConfig(
            strength=SourceStrength.MEDIUM,  # v6: raised from LOW — voice has real signal for bio facts
            label="VOICE TRANSCRIPT",
            confidence_cap=0.9,  # v6: raised from 0.85 — high-value bio facts deserve confidence
            requires_corroboration=False,  # v6: was True — single-mention bio facts were being suppressed
            default_empty_on_noise=True,
            guidance_notes=(
                "Voice transcript: EXTRACTION-ENCOURAGING for biographical facts. "
                "is_currently_true is the PRIMARY predicate for this source — expect to use it "
                "for ~30% of extractions. Extract ALL clear first-person biographical statements: "
                "origin/nationality, residence/location, visa/immigration status, religion, "
                "family relationships (parents, siblings, spouse, children), health diagnoses "
                "(self or family), work arrangements (WFH, role), education status, travel history, "
                "language fluency, and any other durable state {user_name} states about themselves. "
                "Each distinct biographical fact gets its OWN frame — do not consolidate different "
                "facts together. A single session can produce 3-6+ is_currently_true frames normally. "
                "Require ≥1 clear first-person statement per fact (not ≥2). "
                "Filler words (um, like, yeah, so) do NOT invalidate a fact — extract when "
                "the substantive content is clear despite surrounding disfluency. "
                "Only output [] when input is predominantly filler with ZERO factual statements "
                "about {user_name}. Biographical facts are ALWAYS worth extracting if stated."
            ),
        ),
        "manual_note": SourceTypeConfig(
            strength=SourceStrength.MEDIUM,
            label="MANUAL NOTE",
            confidence_cap=0.85,
            requires_corroboration=False,
            default_empty_on_noise=False,
            guidance_notes=(
                "User-typed note: intentional but may be terse or informal. "
                "Extract specific facts; skip vague journaling."
            ),
        ),
        "transcript": SourceTypeConfig(
            strength=SourceStrength.LOW,
            label="VOICE TRANSCRIPT (ambient)",
            confidence_cap=0.7,
            requires_corroboration=True,
            default_empty_on_noise=True,
            guidance_notes=(
                "Ambient voice transcript: often noisy with filler/disfluencies. "
                "EXTRA CONSERVATIVE. Require ≥2 independent utterances supporting "
                "the same fact. If >60% filler → output [] immediately."
            ),
        ),
        "desktop_rewind": SourceTypeConfig(
            strength=SourceStrength.LOW,
            label="SCREENSHOT / DESKTOP REWIND",
            confidence_cap=0.6,
            requires_corroboration=False,
            default_empty_on_noise=True,
            guidance_notes=(
                "Screen capture / OCR: fragmented, may contain UI chrome. "
                "SKEPTICAL. Only extract coherent factual statements about "
                "{user_name}. Never extract UI elements or transient state."
            ),
        ),
        "ocr_screenshot_text": SourceTypeConfig(
            strength=SourceStrength.LOW,
            label="SCREENSHOT OCR",
            confidence_cap=0.8,  # v5: raised from 0.6 — must detect credentials
            requires_corroboration=False,
            default_empty_on_noise=True,
            guidance_notes=(
                "Screenshot OCR: may contain UI fragments, but ALSO may contain "
                "credentials, PII, or sensitive information. "
                "PRIORITY RULE: If you see ANY of these patterns → EXTRACT immediately, "
                "do NOT return []: "
                "password/Passwd/PWD fields, keychain dialogs, login/sign-in pages, "
                "email addresses (even garbled like user@gm8il.com), API keys, "
                "security tokens, credential managers (1Password, keychain), "
                "SSH hosts/usernames (Termius), encryption passwords, "
                "masked characters (•••, ****), 'confidential', 'sensitive data', "
                "Chrome 'wants to use your password' dialogs. "
                "Use predicate 'credential_detected' for passwords/auth material, "
                "'sensitive_info_visible' for emails/personal identifiers. "
                "The garbled text quality does NOT matter — if a security pattern is "
                "present, extract it. Prefer false positives over missing credentials. "
                "If [SECURITY_OCR_ALERT] marker is present in input → you MUST extract."
            ),
        ),
        "ambient_voice": SourceTypeConfig(
            strength=SourceStrength.LOW,
            label="AMBIENT VOICE RECORDING",
            confidence_cap=0.65,
            requires_corroboration=True,
            default_empty_on_noise=True,
            guidance_notes="Always-on ambient recording. High noise floor. Very conservative.",
        ),
        "integration": SourceTypeConfig(
            strength=SourceStrength.MEDIUM,
            label="INTEGRATION FEED",
            confidence_cap=0.8,
            requires_corroboration=False,
            default_empty_on_noise=False,
            guidance_notes="Third-party integration data. Structure varies by provider.",
        ),
        "import": SourceTypeConfig(
            strength=SourceStrength.MEDIUM,
            label="IMPORTED DATA",
            confidence_cap=0.75,
            requires_corroboration=False,
            default_empty_on_noise=False,
            guidance_notes="Bulk-imported data. May have varying quality.",
        ),
        "developer_api": SourceTypeConfig(
            strength=SourceStrength.HIGH,
            label="DEVELOPER API",
            confidence_cap=1.0,
            requires_corroboration=False,
            default_empty_on_noise=False,
            guidance_notes="Developer-submitted via API. Trust caller's intent.",
        ),
        "benchmark_fixture": SourceTypeConfig(
            strength=SourceStrength.UNKNOWN,
            label="BENCHMARK FIXTURE",
            confidence_cap=1.0,
            requires_corroboration=False,
            default_empty_on_noise=False,
            guidance_notes=(
                "Test fixture. Apply standard extraction rules. "
                "Real source_type preserved in metadata for evaluation."
            ),
        ),
    }


SourceTypeConfig.REGISTRY = _build_source_type_registry()


class SourceDescriptor(StrictBaseModel):
    source_type: Literal[
        # --- Existing ---
        "conversation",
        "transcript",
        "desktop_rewind",
        "manual_note",
        "integration",
        "import",
        "developer_api",
        "benchmark_fixture",
        # --- NEW: granular source types ---
        "chat_exchange",  # HIGH: intentional user statements in chat UI
        "voice_transcript",  # MEDIUM: push-to-talk / recorded voice
        "ocr_screenshot_text",  # LOW: screen capture OCR output
        "ambient_voice",  # LOW: always-on ambient recording
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
    ] = Field(
        default_factory=list[
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
        ]
    )


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
    ] = Field(
        default_factory=list[
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
        ]
    )
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


class CandidateEntityMention(StrictBaseModel):
    surface: str
    type_hint: str | None = None
    normalized_entity_id: str | None = None
    confidence: ConfidenceLabel = "medium"


class CandidateEvidenceSpan(StrictBaseModel):
    source_event_id: str
    source_ref: SourceRef
    quote: str | None = None
    speaker: SpeakerRef | None = None
    char_start: int | None = None
    char_end: int | None = None
    source_unit_id: str | None = None
    start_sec: float | None = None
    end_sec: float | None = None
    ocr_block_id: str | None = None
    bbox: list[float | int] | None = None
    ocr_confidence: float | None = None


WorkingMemorySourceType = Literal[
    "voice_transcript",
    "chat_exchange",
    "screenshot_ocr",
    "assistant_session",
    "integration_event",
    "text",
    "conversation",
    "transcript",
    "desktop_rewind",
    "ocr_screenshot_text",
    "ambient_voice",
    "manual_note",
    "developer_api",
    "benchmark_fixture",
]
WorkingMemorySourceSignal = Literal[
    "direct_user",
    "assistant_observed",
    "ocr_observed",
    "app_event",
    "transcript",
    "integration_event",
    "manual_text",
]
WorkingMemorySubjectScope = Literal[
    "primary_user",
    "identified_person",
    "unidentified_non_primary_speaker",
    "workspace",
    "project",
    "artifact",
    "unknown",
]
WorkingMemorySubjectEvidenceType = Literal[
    "direct_user_statement",
    "assistant_observed",
    "ocr_observed",
    "source_local_speaker",
    "inferred_from_context",
    "unknown",
]
WorkingMemoryActorRole = Literal["user", "assistant", "other", "system", "unknown"]
WorkingMemoryRouteHint = Literal["available_now", "pending_l2", "context_only", "review_likely", "reject_likely"]
WorkingMemoryAllowedUse = Literal["read_with_status", "review_only", "context_only", "hidden_until_l2"]
WorkingMemoryKindHint = Literal[
    "identity",
    "preference",
    "project_context",
    "task",
    "plan",
    "relationship_context",
    "tool_use",
    "ui_workspace",
    "context_only",
]


class WorkingMemoryArtifactRef(StrictBaseModel):
    kind: Literal["time_span", "char_span", "screen_region", "event", "document", "unknown"] = "unknown"
    value: dict[str, Any] = Field(default_factory=dict)


class WorkingMemoryEvidence(StrictBaseModel):
    """Source-backed evidence object for realtime L1 working memory.

    This is source evidence, not generated memory text. Speaker labels are
    source/session-local; L2 owns any stable identity resolution.
    """

    evidence_id: str
    source_id: str
    source_unit_id: str | None = None
    artifact_ref: WorkingMemoryArtifactRef = Field(default_factory=WorkingMemoryArtifactRef)
    quote: str
    source_type: WorkingMemorySourceType
    source_signal: WorkingMemorySourceSignal
    source_speaker_label: str | None = None
    speaker_scope: Literal["session-local", "source-local", "not_applicable"] = "not_applicable"
    extractor_id: str = "l1_realtime_v1"
    extractor_version: str | None = None
    capture_confidence: ConfidenceLabel = "medium"
    independence_group: str | None = None
    redaction_status: Literal["active", "tombstoned", "security_hidden"] = "active"


class WorkingMemoryCandidate(StrictBaseModel):
    """V15 L1 working-memory candidate.

    L1 candidates are broad, natural-language, and immediately retrievable with
    status attached. They are not durable memories: L2 owns stable IDs, durable
    active/reject decisions, dedup, supersession, and temporal validity.
    """

    schema_version: Literal["working_memory_candidate.v1"] = "working_memory_candidate.v1"
    candidate_id: str
    user_id: str
    session_id: str
    source_id: str
    source_type: WorkingMemorySourceType
    created_at: datetime | None = None
    observed_at_range: dict[str, datetime | None] | None = None
    candidate_text: str
    subject_scope: WorkingMemorySubjectScope
    subject_entity_id: str | None = None
    subject_evidence_type: WorkingMemorySubjectEvidenceType
    actor_role: WorkingMemoryActorRole
    speaker_identity_claim: str | None = None
    evidence: list[WorkingMemoryEvidence]
    source_refs: list[str] = Field(default_factory=list)
    evidence_quotes: list[str] = Field(default_factory=list)
    evidence_spans: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])
    capture_confidence: ConfidenceLabel = "medium"
    candidate_kind_hint: WorkingMemoryKindHint
    risk_flags: list[str] = Field(default_factory=list)
    route_hint: WorkingMemoryRouteHint = "pending_l2"
    allowed_use: WorkingMemoryAllowedUse = "read_with_status"
    extractor_id: str = "l1_realtime_v1"
    extractor_version: str | None = None

    @model_validator(mode="after")
    def validate_working_memory_contract(self) -> "WorkingMemoryCandidate":
        if not self.evidence:
            raise ValueError("working memory candidates require evidence before metric-eligible use")
        candidate_text_normalized = " ".join(self.candidate_text.lower().split())
        for item in self.evidence:
            quote_normalized = " ".join(item.quote.lower().split())
            if quote_normalized == candidate_text_normalized:
                raise ValueError("evidence quote must be a source quote, not generated candidate text")
        if self.allowed_use == "read_with_status" and self.route_hint == "reject_likely":
            raise ValueError("reject-likely candidates cannot be read as working memory")
        return self


class LiberalMemoryCandidate(StrictBaseModel):
    """High-recall L1 memory candidate.

    Liberal candidates are intentionally natural-language and source-grounded.
    They are not final memories: they do not need canonical entity IDs, a fixed
    predicate, or an active/review/reject decision. L2 owns those decisions.
    """

    schema_version: Literal["liberal_memory_candidate.v1"] = "liberal_memory_candidate.v1"
    candidate_id: str
    candidate_text: str
    source_type: str
    source_example_id: str | None = None
    source_unit_ids: list[str] = Field(default_factory=list)
    source_artifact_ids: list[str] = Field(default_factory=list)
    source_chunk_ids: list[str] = Field(default_factory=list)
    evidence_spans: list[CandidateEvidenceSpan] = Field(default_factory=list)
    raw_quotes: list[str] = Field(default_factory=list)
    speaker_or_actor_attribution: str | None = None
    attribution_confidence: ConfidenceLabel = "medium"
    candidate_kind_hint: str | None = None
    predicate_hint: str | None = None
    subject_mention: str | None = None
    entity_mentions: list[CandidateEntityMention] = Field(default_factory=list)
    time_qualifiers: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    confidence: ConfidenceLabel = "medium"
    extractor_id: str = "liberal_l1_v1"
    prompt_version: str | None = None
    extraction_notes: list[str] = Field(default_factory=list)


class CandidateClaim(StrictBaseModel):
    candidate_id: str
    source_type: str
    source_id: str
    route_id: str | None = None
    speaker_or_actor_attribution: str | None = None
    raw_claim: str
    predicate_hint: str | None = None
    subject_mention: str | None = None
    object_mentions: list[str] = Field(default_factory=list)
    qualifier_mentions: list[str] = Field(default_factory=list)
    entity_mentions: list[CandidateEntityMention] = Field(default_factory=list)
    evidence_spans: list[CandidateEvidenceSpan] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    confidence: ConfidenceLabel = "medium"
    extraction_notes: list[str] = Field(default_factory=list)


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
        "task",
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
    category: Literal[
        "api_key",
        "password",
        "private_key",
        "token",
        "cookie",
        "database_url",
        "one_time_code",
        "unknown_secret",
    ]
    placeholder: str
    char_start: int | None = None
    char_end: int | None = None
    payload_path: str | None = None
    value_hash: str | None = None


class DroppedArtifactRecord(StrictBaseModel):
    dropped_id: str
    source_event_id: str
    reason: Literal["secret"]
    categories: list[
        Literal[
            "api_key",
            "password",
            "private_key",
            "token",
            "cookie",
            "database_url",
            "one_time_code",
            "unknown_secret",
        ]
    ]
    artifact_dropped: bool = True
    source_type: str | None = None
    source_id: str | None = None
    app_id: str | None = None
    timestamp: datetime | None = None


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
    dropped_artifacts: list[DroppedArtifactRecord] = Field(default_factory=list)
    prompt_call_refs: list[PromptCallRef]
    lint_results: list[LintResult]


class PipelineStats(StrictBaseModel):
    raw_event_count: int = 0
    redaction_count: int = 0
    dropped_artifact_count: int = 0
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
    schema_version: Literal["memory_pipeline_output"] = "memory_pipeline_output"
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
    candidates: list[CandidateClaim] = Field(default_factory=list)
    liberal_candidates: list[LiberalMemoryCandidate] = Field(default_factory=list)
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
