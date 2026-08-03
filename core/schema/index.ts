import { Static, Type } from "@sinclair/typebox";
import { asJsonSchema2020 } from "./json";

const OpaqueId = () => Type.String({ minLength: 1 });

export const LocalityHintSchema = Type.Union([Type.Literal("durable"), Type.Literal("source_local")]);
export type LocalityHint = Static<typeof LocalityHintSchema>;

/** Open reference: a resolver/strategy may use any stable entity/topic/descriptor reference. */
export const ScopeSchema = Type.Object({
  locality: LocalityHintSchema,
  scope_ref: Type.Union([Type.String({ minLength: 1 }), Type.Null()]),
}, { additionalProperties: false });
export type Scope = Static<typeof ScopeSchema>;

export const L1EventSchema = Type.Object({
  event_id: OpaqueId(),
  event_revision_id: OpaqueId(),
  owner_account_id: OpaqueId(),
  capture_session_id: OpaqueId(),
  stream_id: OpaqueId(),
  event_kind: Type.String({ minLength: 1 }),
  payload_schema_ref: Type.String({ minLength: 1 }),
  schema_version: Type.String({ minLength: 1 }),
  payload: Type.Unknown(),
  event_time: Type.String({ minLength: 1 }),
  /** Null means the source recorded no ingest wall clock. Copying `event_time`
   * here is worse than null: it makes every lag/ordering analysis a measurement
   * of its own input. */
  ingest_time: Type.Union([Type.String({ minLength: 1 }), Type.Null()]),
  source_sequence: Type.Union([Type.Integer({ minimum: 0 }), Type.Null()]),
  evidence_addressable_refs: Type.Array(Type.String({ minLength: 1 })),
  source_trust: Type.String({ minLength: 1 }),
  policy_labels: Type.Array(Type.String()),
  canonical_redacted_hash: Type.String({ minLength: 1 }),
}, { additionalProperties: false });
export type L1Event = Static<typeof L1EventSchema>;

/**
 * A producer-scoped reference to a subject observed by a source.  This is a
 * coordinate in the capture, not a claim that two real-world people are the
 * same.  Rendered names deliberately live outside this value.
 */
export const SourceIdentityRefSchema = Type.Object({
  namespace_instance_ref: OpaqueId(),
  local_key: OpaqueId(),
  producer: Type.Object({ producer_ref: Type.Union([OpaqueId(), Type.Null()]), contract_ref: Type.Union([OpaqueId(), Type.Null()]) }, { additionalProperties: false }),
  asserted_identity: Type.Object({ domain: Type.Union([OpaqueId(), Type.Null()]), scope_ref: Type.Union([OpaqueId(), Type.Null()]) }, { additionalProperties: false }),
}, { additionalProperties: false });
export type SourceIdentityRef = Static<typeof SourceIdentityRefSchema>;

export const EvidenceSchema = Type.Object({
  evidence_id: OpaqueId(),
  event_revision_id: OpaqueId(),
  source_unit_ref: Type.Union([Type.String(), Type.Null()]),
  range: Type.Object({ start: Type.Integer({ minimum: 0 }), end: Type.Integer({ minimum: 0 }) }, { additionalProperties: false }),
  excerpt: Type.Union([Type.String(), Type.Null()]),
  /** Typed producer coordinate; never derive identity from `speaker_rendering`. */
  source_identity_ref: SourceIdentityRefSchema,
  speaker_rendering: Type.Union([Type.String(), Type.Null()]),
  source_local_mention_ref: Type.Union([Type.String(), Type.Null()]),
  state: Type.Union([Type.Literal("active"), Type.Literal("tombstoned"), Type.Literal("security_hidden")]),
  source_trust: Type.String({ minLength: 1 }),
  policy_labels: Type.Array(Type.String()),
  source_independence_key: Type.String({ minLength: 1 }),
}, { additionalProperties: false });
export type Evidence = Static<typeof EvidenceSchema>;

/** A source-local mention is durable even when entity resolution abstains. */
export const MentionSchema = Type.Object({
  mention_id: OpaqueId(),
  owner_account_id: OpaqueId(),
  claim_revision_id: OpaqueId(),
  span: Type.Object({ start: Type.Integer({ minimum: 0 }), end: Type.Integer({ minimum: 0 }) }, { additionalProperties: false }),
  evidence_id: OpaqueId(),
  source_identity_ref: Type.Union([SourceIdentityRefSchema, Type.Null()]),
  speaker_rendering: Type.Union([Type.String({ minLength: 1 }), Type.Null()]),
  slot_id: OpaqueId(),
  surface: Type.String({ minLength: 1 }),
  antecedent_handle: Type.Union([Type.String({ minLength: 1 }), Type.Null()]),
  resolution: Type.Union([Type.Literal("resolved"), Type.Literal("unresolved")]),
  entity_id: Type.Union([Type.String({ minLength: 1 }), Type.Null()]),
}, { additionalProperties: false });
export type Mention = Static<typeof MentionSchema>;

/**
 * A model may propose an anaphora edge, but it becomes usable only as this
 * persisted, unit-bounded record.  It is operational support for a previously
 * authorized binding, never identity authority in its own right.
 */
export const CoreferenceSupportSchema = Type.Object({
  coreference_support_id: OpaqueId(),
  owner_account_id: OpaqueId(),
  discourse_unit_ref: OpaqueId(),
  antecedent_mention_id: OpaqueId(),
  anaphor_mention_id: OpaqueId(),
  evidence_refs: Type.Array(OpaqueId(), { minItems: 1 }),
  lineage_refs: Type.Array(OpaqueId(), { minItems: 1 }),
  lifecycle: Type.Union([Type.Literal("active"), Type.Literal("reversed")]),
}, { additionalProperties: false });
export type CoreferenceSupport = Static<typeof CoreferenceSupportSchema>;

export const ArgumentSchema = Type.Object({
  slot_id: Type.String({ minLength: 1 }),
  role: Type.String({ minLength: 1 }),
  /** Extraction keeps the observed rendering separate from the identity coordinate. */
  surface: Type.Optional(Type.String({ minLength: 1 })),
  span: Type.Optional(Type.Object({ start: Type.Integer({ minimum: 0 }), end: Type.Integer({ minimum: 0 }) }, { additionalProperties: false })),
  value: Type.Union([
    Type.Object({ kind: Type.Literal("entity_ref"), ref: Type.String({ minLength: 1 }) }, { additionalProperties: false }),
    /** A durable source coordinate, not a durable entity binding. */
    Type.Object({ kind: Type.Literal("source_local_ref"), ref: Type.String({ minLength: 1 }) }, { additionalProperties: false }),
    Type.Object({ kind: Type.Literal("literal"), value: Type.Unknown() }, { additionalProperties: false }),
  ]),
}, { additionalProperties: false });
export type ClaimArgument = Static<typeof ArgumentSchema>;

/** A slot names one role occurrence; two arguments may not share that name. */
export const hasDistinctArgumentSlotIds = (arguments_: readonly ClaimArgument[]): boolean => {
  const slotIds = new Set<string>();
  for (const argument of arguments_) {
    if (slotIds.has(argument.slot_id)) return false;
    slotIds.add(argument.slot_id);
  }
  return true;
};

/**
 * Claims carry this JSON Schema extension so the shared strict validator can
 * enforce uniqueness by a property rather than by whole argument object.
 * JSON Schema's standard `uniqueItems` compares complete objects and cannot
 * express this invariant for an unbounded arguments array.
 */
const DistinctSlotArgumentsSchema = Type.Array(ArgumentSchema, {
  uniqueItemProperties: ["slot_id"],
});

/**
 * Temporal typing is open at the imprecise bucket boundary: buckets describe
 * physical/coarse time supplied by a strategy, never a content taxonomy.
 */
export const TypedTemporalExprSchema = Type.Union([
  Type.Object({ kind: Type.Literal("relative"), anchor: Type.Union([Type.Literal("query"), Type.Literal("capture")]), unit: Type.Union([Type.Literal("day"), Type.Literal("week"), Type.Literal("month"), Type.Literal("quarter"), Type.Literal("year")]), offset: Type.Integer() }, { additionalProperties: false }),
  Type.Object({ kind: Type.Literal("absolute"), granularity: Type.Union([Type.Literal("day"), Type.Literal("week"), Type.Literal("month"), Type.Literal("quarter"), Type.Literal("year"), Type.Literal("instant")]), value: Type.String({ minLength: 1 }) }, { additionalProperties: false }),
  Type.Object({ kind: Type.Literal("imprecise"), bucket: Type.String({ minLength: 1 }), precision: Type.String({ minLength: 1 }) }, { additionalProperties: false }),
]);
export type TypedTemporalExpr = Static<typeof TypedTemporalExprSchema>;

export const ResolvedTimeIntervalSchema = Type.Union([
  Type.Object({ kind: Type.Literal("calendar_interval"), start: Type.String({ minLength: 1 }), end: Type.String({ minLength: 1 }), timezone: Type.String({ minLength: 1 }), granularity: Type.Union([Type.Literal("day"), Type.Literal("week"), Type.Literal("month"), Type.Literal("quarter"), Type.Literal("year")]) }, { additionalProperties: false }),
  Type.Object({ kind: Type.Literal("instant"), start: Type.String({ minLength: 1 }), end: Type.String({ minLength: 1 }), timezone: Type.String({ minLength: 1 }), granularity: Type.Literal("instant") }, { additionalProperties: false }),
  Type.Object({ kind: Type.Literal("imprecise"), bucket: Type.String({ minLength: 1 }), precision: Type.String({ minLength: 1 }), timezone: Type.String({ minLength: 1 }) }, { additionalProperties: false }),
]);
export type ResolvedTimeInterval = Static<typeof ResolvedTimeIntervalSchema>;

/** Resolver inputs are recorded with its output so restart never reinterprets time. */
export const PersistedValidTimeSchema = Type.Object({
  typed_expression: TypedTemporalExprSchema,
  resolved_interval: ResolvedTimeIntervalSchema,
  derivation: Type.Object({ resolver_version: Type.String({ minLength: 1 }), timezone: Type.String({ minLength: 1 }) }, { additionalProperties: false }),
}, { additionalProperties: false });
export type PersistedValidTime = Static<typeof PersistedValidTimeSchema>;

const TemporalScopeSchema = (requireValidTime: boolean) => Type.Object({
  observed_at: Type.String({ minLength: 1 }),
  precision: Type.String({ minLength: 1 }),
  ...(requireValidTime ? { valid_time: PersistedValidTimeSchema } : { valid_time: Type.Optional(PersistedValidTimeSchema) }),
}, { additionalProperties: false });

const ClaimFields = {
  claim_lineage_id: OpaqueId(),
  claim_revision_id: OpaqueId(),
  owner_account_id: OpaqueId(),
  /** The vocabulary handle; `predicate` remains the immutable observed spelling. */
  predicate_id: Type.Optional(OpaqueId()),
  predicate: Type.String({ minLength: 1 }),
  /** Historical identity is immutable; resolution is always bound to its frontier. */
  proposition_key_raw: Type.Optional(Type.String({ minLength: 1 })),
  proposition_key_resolved: Type.Optional(Type.String({ minLength: 1 })),
  predicate_alias_frontier: Type.Optional(Type.String({ minLength: 1 })),
  arguments: DistinctSlotArgumentsSchema,
  /** Negation is claim semantics; losing it makes contradiction detection unsound. */
  polarity: Type.Optional(Type.Union([Type.Literal("positive"), Type.Literal("negative")])),
  /** The extraction-selected role, never a rendering comparison, may inherit speaker attestation. */
  observed_speaker_slot_id: Type.Optional(Type.Union([Type.String({ minLength: 1 }), Type.Null()])),
  temporal_scope: TemporalScopeSchema(false),
  evidence_refs: Type.Array(Type.String({ minLength: 1 })),
  policy_labels: Type.Array(Type.String()),
  source_language: Type.String({ minLength: 1 }),
  scope: ScopeSchema,
};

export const ProvisionalClaimSchema = Type.Object({
  ...ClaimFields,
  lifecycle: Type.Literal("provisional"),
  ambiguity_markers: Type.Array(Type.String()),
  context_packet: Type.Union([
    Type.Object({ version: Type.String({ minLength: 1 }), referent_refs: Type.Array(Type.String()), topic_refs: Type.Array(Type.String()) }, { additionalProperties: false }),
    Type.Null(),
  ]),
}, { additionalProperties: false });
export type ProvisionalClaim = Static<typeof ProvisionalClaimSchema>;

export const CanonicalClaimSchema = Type.Object({
  ...ClaimFields,
  // A canonical claim is durable truth: it must retain the exact typed expression,
  // resolved interval, resolver version, and timezone used at commit time.
  temporal_scope: TemporalScopeSchema(true),
  lifecycle: Type.Literal("canonical"),
  canonical_claim_id: OpaqueId(),
  source_provisional_revision_ids: Type.Array(Type.String({ minLength: 1 })),
  /** Explicit revision-to-revision lineage edge; it is independent of commit ordering. */
  supersedes_revision_ids: Type.Optional(Type.Array(Type.String({ minLength: 1 }))),
}, { additionalProperties: false });
export type CanonicalClaim = Static<typeof CanonicalClaimSchema>;

export const EntitySchema = Type.Object({
  entity_id: OpaqueId(),
  owner_account_id: OpaqueId(),
  entity_revision_id: OpaqueId(),
  handle: Type.String({ minLength: 1 }),
  labels: Type.Array(Type.String()),
}, { additionalProperties: false });
export type Entity = Static<typeof EntitySchema>;

/** Predicates are vocabulary objects. `predicate_id`, not display text, is claim identity. */
export const PredicateSchema = Type.Object({
  predicate_id: OpaqueId(),
  owner_account_id: OpaqueId(),
  predicate_revision_id: OpaqueId(),
  /** Identity is the normalized relation name plus this object's slot set, never its rendering. */
  identity_name: Type.String({ minLength: 1 }),
  display_name: Type.String({ minLength: 1 }),
  lifecycle: Type.Union([Type.Literal("provisional"), Type.Literal("canonical")]),
  slot_ids: Type.Array(OpaqueId()),
}, { additionalProperties: false });
export type Predicate = Static<typeof PredicateSchema>;

/** Append-only vocabulary assertions; they do not assert real-world identity. */
export const PredicateAssertionSchema = Type.Object({
  assertion_id: OpaqueId(),
  owner_account_id: OpaqueId(),
  predicate_id: OpaqueId(),
  relation: Type.Union([Type.Literal("alias_of"), Type.Literal("split_from")]),
  target_predicate_id: OpaqueId(),
  /** Slot alignment travels with vocabulary alignment so the resulting predicate remains traversable. */
  slot_aliases: Type.Array(Type.Object({ from_slot_id: OpaqueId(), to_slot_id: OpaqueId() }, { additionalProperties: false })),
  alias_frontier: OpaqueId(),
  /** A collision proposal is inert until a budgeted consolidation derivation admits it. */
  admission: Type.Union([Type.Literal("proposal"), Type.Literal("accepted")]),
  lifecycle: Type.Union([Type.Literal("active"), Type.Literal("superseded")]),
  supersedes_assertion_id: Type.Union([OpaqueId(), Type.Null()]),
}, { additionalProperties: false });
export type PredicateAssertion = Static<typeof PredicateAssertionSchema>;

export const IdentityEndpointSchema = Type.Union([
  Type.Object({ kind: Type.Literal("source_identity"), source_identity_ref: SourceIdentityRefSchema }, { additionalProperties: false }),
  Type.Object({ kind: Type.Literal("entity"), entity_id: OpaqueId() }, { additionalProperties: false }),
]);
export type IdentityEndpoint = Static<typeof IdentityEndpointSchema>;

/** Immutable, structurally-verifiable authority — excerpts and candidates cannot inhabit this union. */
export const IdentityAuthorizationSchema = Type.Object({
  authorization_id: OpaqueId(),
  owner_account_id: OpaqueId(),
  endpoints: Type.Tuple([IdentityEndpointSchema, IdentityEndpointSchema]),
  relation: Type.Union([Type.Literal("same"), Type.Literal("distinct")]),
  support: Type.Union([
    Type.Object({ kind: Type.Literal("owner_confirmation"), confirmation_ref: OpaqueId() }, { additionalProperties: false }),
    Type.Object({ kind: Type.Literal("producer_identity_key_equality"), left_assertion_ref: OpaqueId(), right_assertion_ref: OpaqueId() }, { additionalProperties: false }),
    /** Model output is deliberately absent: authority verifies independent immutable support roots. */
    Type.Object({ kind: Type.Literal("consolidation_adjudication"), support_refs: Type.Array(OpaqueId(), { minItems: 1 }), proposal_lineage_ref: OpaqueId() }, { additionalProperties: false }),
  ]),
  standing_policy_ref: Type.Union([OpaqueId(), Type.Null()]),
  namespace_scope: Type.Object({ namespace_instance_ref: Type.Union([OpaqueId(), Type.Null()]), identity_domain: Type.Union([OpaqueId(), Type.Null()]), scope_ref: Type.Union([OpaqueId(), Type.Null()]) }, { additionalProperties: false }),
  authority_policy_version: OpaqueId(),
  evaluated_frontier: Type.Integer({ minimum: 0 }),
  actor_provenance: Type.Object({ actor_ref: OpaqueId(), producer_ref: Type.Union([OpaqueId(), Type.Null()]) }, { additionalProperties: false }),
  lifecycle: Type.Union([Type.Literal("active"), Type.Literal("superseded"), Type.Literal("revoked")]),
  superseded_by: Type.Union([OpaqueId(), Type.Null()]),
}, { additionalProperties: false });
export type IdentityAuthorization = Static<typeof IdentityAuthorizationSchema>;

export const IdentityConstraintSchema = Type.Object({
  constraint_id: OpaqueId(),
  owner_account_id: OpaqueId(),
  /** Typed referent/entity endpoints are the only active identity keys. */
  endpoints: Type.Optional(Type.Tuple([IdentityEndpointSchema, IdentityEndpointSchema])),
  /**
   * Legacy immutable rendering fields.  They are retained for audit/migration
   * only and must never take part in active relation closure.
   */
  left_handle: Type.String({ minLength: 1 }),
  right_handle: Type.String({ minLength: 1 }),
  relation: Type.Union([Type.Literal("same"), Type.Literal("distinct")]),
  /** Legacy field retained for old immutable rows; it is never authorization. */
  evidence_refs: Type.Optional(Type.Array(Type.String({ minLength: 1 }))),
  identity_authorization: Type.Optional(IdentityAuthorizationSchema),
  effective_at: Type.Integer({ minimum: 0 }),
  reversed_at: Type.Union([Type.Integer({ minimum: 0 }), Type.Null()]),
}, { additionalProperties: false });
export type IdentityConstraint = Static<typeof IdentityConstraintSchema>;

export type ClaimLifecycle = "provisional" | "canonical" | "deferred" | "rejected";
const transitions: Record<ClaimLifecycle, readonly ClaimLifecycle[]> = {
  provisional: ["canonical", "deferred", "rejected"],
  deferred: ["canonical", "rejected"],
  canonical: [],
  rejected: [],
};

export const isValidLifecycleTransition = (from: ClaimLifecycle, to: ClaimLifecycle): boolean => transitions[from].includes(to);
export const transitionClaimLifecycle = (from: ClaimLifecycle, to: ClaimLifecycle): { from: ClaimLifecycle; to: ClaimLifecycle } | { error: string } =>
  isValidLifecycleTransition(from, to) ? { from, to } : { error: `invalid lifecycle transition: ${from} -> ${to}` };

/** JSON Schema 2020-12 documents exported for non-TypeScript consumers. */
export const EnvelopeJsonSchemas2020 = {
  l1_event: asJsonSchema2020(L1EventSchema), evidence: asJsonSchema2020(EvidenceSchema),
  provisional_claim: asJsonSchema2020(ProvisionalClaimSchema), canonical_claim: asJsonSchema2020(CanonicalClaimSchema),
  entity: asJsonSchema2020(EntitySchema), predicate: asJsonSchema2020(PredicateSchema), predicate_assertion: asJsonSchema2020(PredicateAssertionSchema), identity_constraint: asJsonSchema2020(IdentityConstraintSchema), identity_authorization: asJsonSchema2020(IdentityAuthorizationSchema), source_identity_ref: asJsonSchema2020(SourceIdentityRefSchema), mention: asJsonSchema2020(MentionSchema), coreference_support: asJsonSchema2020(CoreferenceSupportSchema),
};
