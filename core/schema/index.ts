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
  ingest_time: Type.String({ minLength: 1 }),
  source_sequence: Type.Union([Type.Integer({ minimum: 0 }), Type.Null()]),
  evidence_addressable_refs: Type.Array(Type.String({ minLength: 1 })),
  source_trust: Type.String({ minLength: 1 }),
  policy_labels: Type.Array(Type.String()),
  canonical_redacted_hash: Type.String({ minLength: 1 }),
}, { additionalProperties: false });
export type L1Event = Static<typeof L1EventSchema>;

export const EvidenceSchema = Type.Object({
  evidence_id: OpaqueId(),
  event_revision_id: OpaqueId(),
  source_unit_ref: Type.Union([Type.String(), Type.Null()]),
  range: Type.Object({ start: Type.Integer({ minimum: 0 }), end: Type.Integer({ minimum: 0 }) }, { additionalProperties: false }),
  excerpt: Type.Union([Type.String(), Type.Null()]),
  source_local_speaker_ref: Type.Union([Type.String(), Type.Null()]),
  source_local_mention_ref: Type.Union([Type.String(), Type.Null()]),
  state: Type.Union([Type.Literal("active"), Type.Literal("tombstoned"), Type.Literal("security_hidden")]),
  source_trust: Type.String({ minLength: 1 }),
  policy_labels: Type.Array(Type.String()),
  source_independence_key: Type.String({ minLength: 1 }),
}, { additionalProperties: false });
export type Evidence = Static<typeof EvidenceSchema>;

export const ArgumentSchema = Type.Object({
  slot_id: Type.String({ minLength: 1 }),
  role: Type.String({ minLength: 1 }),
  value: Type.Union([
    Type.Object({ kind: Type.Literal("entity_ref"), ref: Type.String({ minLength: 1 }) }, { additionalProperties: false }),
    Type.Object({ kind: Type.Literal("literal"), value: Type.Unknown() }, { additionalProperties: false }),
  ]),
}, { additionalProperties: false });
export type ClaimArgument = Static<typeof ArgumentSchema>;

const ClaimFields = {
  claim_lineage_id: OpaqueId(),
  claim_revision_id: OpaqueId(),
  owner_account_id: OpaqueId(),
  predicate: Type.String({ minLength: 1 }),
  arguments: Type.Array(ArgumentSchema),
  temporal_scope: Type.Object({ observed_at: Type.String({ minLength: 1 }), precision: Type.String({ minLength: 1 }) }, { additionalProperties: false }),
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

export const IdentityConstraintSchema = Type.Object({
  constraint_id: OpaqueId(),
  owner_account_id: OpaqueId(),
  left_handle: Type.String({ minLength: 1 }),
  right_handle: Type.String({ minLength: 1 }),
  relation: Type.Union([Type.Literal("same"), Type.Literal("distinct")]),
  evidence_refs: Type.Array(Type.String({ minLength: 1 })),
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
  entity: asJsonSchema2020(EntitySchema), identity_constraint: asJsonSchema2020(IdentityConstraintSchema),
};
