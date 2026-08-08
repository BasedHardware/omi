import { sha256CanonicalRedacted } from "../ledger";
import { genericPolicyClassifier, projectTreeInputSnapshot, type GraphSnapshot, type PolicyClass, type TreeInputSnapshot } from "./index";
import { sha256CanonicalContent } from "./content-digest";
import { deepFreezePlainJson, normalizePlainJson } from "./plain-json";

const projectedInputs = new WeakSet<object>();
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMAPPS-001)
export const APPLICATION_DEFAULT_SYNTHESIZED_POLICY: Readonly<PolicyClass> = Object.freeze({
  subject_class: "generic",
  sensitivity: "generic",
  capture_class: "generic",
});

// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
export interface ResolvedApplicationCredential {
  owner_account_id: string | null;
  // domain-pending(DIV-DOMAPPS-006)
  credential_kind: "mcp_api_key" | "oauth" | "developer_api_key";
  // domain-pending(DIV-DOMAPPS-001)
  app_id: string | null;
  // domain-pending(DIV-DOMAPPS-006)
  key_id: string | null;
  scopes: readonly string[];
  /** `false` means the credential lookup found no currently usable key. */
  active: boolean;
}

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
export interface PersistedApplicationMemoryGrant {
  owner_account_id: string;
  // domain-pending(DIV-DOMAPPS-006)
  consumer: "mcp" | "developer_api";
  // domain-pending(DIV-DOMAPPS-001)
  app_id: string;
  // domain-pending(DIV-DOMAPPS-006)
  key_id: string;
  enabled: boolean;
  default_read: boolean;
  scopes: readonly string[];
}

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
export interface ApplicationMemoryReadAuthorizationRequest {
  owner_account_id: string;
  credential: ResolvedApplicationCredential;
  persisted_grant: PersistedApplicationMemoryGrant | null;
}

// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
interface ApplicationReadAuthorization {
  readonly owner_account_id: string;
  // domain-pending(DIV-DOMAPPS-001)
  readonly app_id: string;
  // domain-pending(DIV-DOMAPPS-006)
  readonly key_id: string;
  /** Opaque non-owner principal; it grants no authority by itself. */
  readonly principal_digest: string;
  readonly projection_policy_classes: readonly Readonly<PolicyClass>[];
  readonly authorization_digest: string;
}

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
export interface ApplicationGrantProjectedTreeInputSnapshot extends TreeInputSnapshot {
  readonly reader_projection_digest: string;
  readonly projection_authorization_digest: string;
}

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMAPPS-001)
export interface ApplicationProjectionLoad {
  readonly snapshot: GraphSnapshot;
  readonly options: { readonly account_timezone: string };
}

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMAPPS-001)
export type ApplicationProjectionLoader = () => ApplicationProjectionLoad;

// domain-pending(DIV-DOMAPPS-001)
export type ApplicationReadDenial =
  | "unsupported_credential_kind"
  | "missing_scope"
  | "unresolvable_identity"
  | "inactive_credential"
  | "missing_grant"
  | "grant_identity_mismatch"
  | "inactive_grant"
  | "grant_scope_mismatch"
  | "projection_binding_mismatch";

// domain-pending(DIV-DOMAPPS-001)
export class ApplicationReadDenied extends Error {
  constructor(readonly reason: ApplicationReadDenial) {
    super(`application read denied: ${reason}`);
    this.name = "ApplicationReadDenied";
  }
}

// domain-pending(DIV-DOMCORE-001)
const REQUIRED_MEMORY_READ_SCOPE = "memories.read";
const deny = (reason: ApplicationReadDenial): never => { throw new ApplicationReadDenied(reason); };
const isResolved = (value: string | null): value is string => typeof value === "string" && value.length > 0;
const normalizedStrings = (values: readonly string[]): readonly string[] => [...new Set(values)].sort();
const genericPolicyLabels = new Set(["subject:generic", "sensitivity:generic", "capture:generic"]);
const hasOnlyGenericPolicyLabels = (labels: readonly string[]): boolean => labels.every((label) => genericPolicyLabels.has(label));
const rejectNestedOwnerMismatch = (snapshot: GraphSnapshot, ownerAccountId: string): void => {
  const visited = new WeakSet<object>();
  const inspect = (value: unknown): void => {
    if (value === null || typeof value !== "object" || visited.has(value)) return;
    visited.add(value);
    if (Object.prototype.hasOwnProperty.call(value, "owner_account_id")
      && (value as { owner_account_id?: unknown }).owner_account_id !== ownerAccountId) deny("projection_binding_mismatch");
    for (const nested of Object.values(value)) inspect(nested);
  };
  inspect(snapshot);
};

const sameEvidenceSpan = (
  left: TreeInputSnapshot["evidence_index"][number],
  right: TreeInputSnapshot["evidence_index"][number],
): boolean => sha256CanonicalContent(left) === sha256CanonicalContent(right);

const validateVisibleEvidenceClosure = (input: TreeInputSnapshot): void => {
  const evidenceById = new Map<string, TreeInputSnapshot["evidence_index"][number]>();
  for (const evidence of input.evidence_index) {
    if (!evidence.evidence_id || evidenceById.has(evidence.evidence_id)) deny("projection_binding_mismatch");
    evidenceById.set(evidence.evidence_id, evidence);
  }
  for (const claim of input.claims) {
    const refs = [...claim.evidence_refs].sort();
    const spanIds = claim.evidence_spans.map((span) => span.evidence_id).sort();
    if (refs.length === 0 || refs.length !== new Set(refs).size || refs.length !== spanIds.length
      || refs.some((ref, index) => ref !== spanIds[index])) deny("projection_binding_mismatch");
    for (const span of claim.evidence_spans) {
      const indexed = evidenceById.get(span.evidence_id);
      if (!indexed || !sameEvidenceSpan(span, indexed)) deny("projection_binding_mismatch");
    }
  }
};

const hasExactOwnOwner = (value: object, ownerAccountId: string): boolean =>
  Object.prototype.hasOwnProperty.call(value, "owner_account_id")
  && (value as { owner_account_id?: unknown }).owner_account_id === ownerAccountId;

const validateVisibleTenantLineage = (
  snapshot: GraphSnapshot,
  claims: TreeInputSnapshot["claims"],
  evidenceIndex: TreeInputSnapshot["evidence_index"],
  ownerAccountId: string,
): void => {
  for (const claim of claims) {
    const rawClaims = snapshot.claims.filter((item) => item.revision_id === claim.claim_revision_id);
    if (rawClaims.length !== 1 || !hasExactOwnOwner(rawClaims[0]!.claim, ownerAccountId)) deny("projection_binding_mismatch");
    for (const argument of claim.arguments) if (argument.value.kind === "entity_ref") {
      const entities = snapshot.entities.filter((item) => item.entity.entity_id === argument.value.ref);
      if (entities.length !== 1 || !hasExactOwnOwner(entities[0]!.entity, ownerAccountId)) deny("projection_binding_mismatch");
    }
  }
  for (const evidence of evidenceIndex) {
    const events = (snapshot.events ?? []).filter((item) => item.revision_id === evidence.event_revision_id
      || item.event.event_revision_id === evidence.event_revision_id);
    if (events.length !== 1 || !hasExactOwnOwner(events[0]!.event, ownerAccountId)) deny("projection_binding_mismatch");
  }
};

/**
 * Pure application authorization gate. Scope and persisted grant are checked
 * independently, and every denial is resolved before the zero-authority store
 * loader can run. Projection remains internal to this boundary.
 */
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
export const readAfterApplicationAuthorization = (
  request: ApplicationMemoryReadAuthorizationRequest,
  loadStore: ApplicationProjectionLoader,
): ApplicationGrantProjectedTreeInputSnapshot => {
  request = normalizePlainJson(request);
  const credential = request.credential;
  if (credential.credential_kind !== "mcp_api_key") deny("unsupported_credential_kind");
  if (!credential.scopes.includes(REQUIRED_MEMORY_READ_SCOPE)) deny("missing_scope");
  if (!isResolved(request.owner_account_id) || !isResolved(credential.owner_account_id) || !isResolved(credential.app_id) || !isResolved(credential.key_id)) deny("unresolvable_identity");
  if (!credential.active) deny("inactive_credential");

  const grant = request.persisted_grant;
  if (grant === null) deny("missing_grant");
  if (grant.consumer !== "mcp") deny("unsupported_credential_kind");
  if (grant.owner_account_id !== request.owner_account_id
    || credential.owner_account_id !== request.owner_account_id
    || grant.owner_account_id !== credential.owner_account_id
    || grant.app_id !== credential.app_id
    || grant.key_id !== credential.key_id) deny("grant_identity_mismatch");
  if (!grant.enabled || !grant.default_read) deny("inactive_grant");
  if (!grant.scopes.includes(REQUIRED_MEMORY_READ_SCOPE)) deny("grant_scope_mismatch");

  // domain-pending(DIV-DOMAPPS-001)
  // domain-pending(DIV-DOMAPPS-006)
  const principalDigest = sha256CanonicalRedacted({
    kind: "application-key-principal",
    owner_account_id: request.owner_account_id,
    app_id: credential.app_id,
    key_id: credential.key_id,
  });
  // domain-pending(DIV-DOMAPPS-001)
  // domain-pending(DIV-DOMAPPS-006)
  const authorizationDigest = sha256CanonicalRedacted({
    owner_account_id: request.owner_account_id,
    app_id: credential.app_id,
    key_id: credential.key_id,
    credential_scopes: normalizedStrings(credential.scopes),
    credential_kind: credential.credential_kind,
    grant_consumer: grant.consumer,
    grant_enabled: grant.enabled,
    grant_default_read: grant.default_read,
    grant_scopes: normalizedStrings(grant.scopes),
    principal_digest: principalDigest,
    projection_policy_classes: [APPLICATION_DEFAULT_SYNTHESIZED_POLICY],
    projection: { default_synthesized: true, archive_read: false, raw_read: false },
  });
  const authorization: ApplicationReadAuthorization = Object.freeze({
    owner_account_id: String(request.owner_account_id),
    app_id: String(credential.app_id),
    key_id: String(credential.key_id),
    principal_digest: principalDigest,
    projection_policy_classes: Object.freeze([APPLICATION_DEFAULT_SYNTHESIZED_POLICY]),
    authorization_digest: authorizationDigest,
  });
  const loaded = normalizePlainJson(loadStore());
  return projectApplicationDefaultReadTreeInput(loaded.snapshot, loaded.options, authorization);
};

/**
 * The only positive application projection factory. It selects canonical,
 * durable/default inputs and never routes through retrieve/Grant's owner shortcut.
 */
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
const projectApplicationDefaultReadTreeInput = (
  snapshot: GraphSnapshot,
  options: { account_timezone: string },
  authorization: ApplicationReadAuthorization,
): ApplicationGrantProjectedTreeInputSnapshot => {
  if (snapshot.owner_account_id !== authorization.owner_account_id
    || typeof options.account_timezone !== "string"
    || options.account_timezone.length === 0
    || Object.keys(options).some((key) => key !== "account_timezone")) deny("projection_binding_mismatch");
  rejectNestedOwnerMismatch(snapshot, authorization.owner_account_id);
  // domain-pending(DIV-DOMCORE-008)
  const canonicalDefaultSnapshot: GraphSnapshot = {
    ...snapshot,
    // Identity closure can rename visible entity arguments before projection.
    // Omit it until complete visible-only support can be proven.
    identity_constraints: [],
    claims: snapshot.claims.filter((item) => item.placement_status === "canonical"
      && item.claim.lifecycle === "canonical"
      && item.claim.scope.locality === "durable"),
  };
  const input = projectTreeInputSnapshot(canonicalDefaultSnapshot, { account_timezone: options.account_timezone, classifier: genericPolicyClassifier });
  const evidenceById = new Map(input.evidence_index.map((span) => [span.evidence_id, span]));
  // domain-pending(DIV-DOMCORE-008)
  const claims = input.claims.filter((claim) => claim.policy_class.subject_class === APPLICATION_DEFAULT_SYNTHESIZED_POLICY.subject_class
    && claim.policy_class.sensitivity === APPLICATION_DEFAULT_SYNTHESIZED_POLICY.sensitivity
    && claim.policy_class.capture_class === APPLICATION_DEFAULT_SYNTHESIZED_POLICY.capture_class
    && hasOnlyGenericPolicyLabels(claim.policy_labels)
    && claim.evidence_refs.every((evidenceId) => {
      const evidence = evidenceById.get(evidenceId);
      // Preserve a policy-eligible claim with a missing span so the visible
      // closure validator can deny it instead of silently hiding corruption.
      return evidence === undefined || hasOnlyGenericPolicyLabels(evidence.policy_labels);
    }));
  const visibleClaimIds = new Set(claims.map((claim) => claim.claim_revision_id));
  const visibleEvidenceIds = new Set(claims.flatMap((claim) => claim.evidence_refs));
  const evidence_index = input.evidence_index.filter((span) => visibleEvidenceIds.has(span.evidence_id));
  // Identity constraints can rename/coalesce visible topology. Until complete
  // visible support can be proven, the application projection omits them.
  // domain-pending(DIV-DOMCORE-008)
  const identity_constraints: TreeInputSnapshot["identity_constraints"] = [];
  const policy_classes = Object.fromEntries(claims.map((claim) => [claim.claim_revision_id, { ...claim.policy_class }]));
  const diagnostics = input.diagnostics.filter((diagnostic) => "claim_revision_id" in diagnostic
    ? visibleClaimIds.has(diagnostic.claim_revision_id)
    : diagnostic.claim_revision_ids.some((revision) => visibleClaimIds.has(revision)));
  validateVisibleTenantLineage(canonicalDefaultSnapshot, claims, evidence_index, authorization.owner_account_id);
  validateVisibleEvidenceClosure({ ...input, claims, identity_constraints, evidence_index, policy_classes, diagnostics });
  const projected_content_digest = sha256CanonicalContent({
    owner_account_id: input.owner_account_id,
    claims,
    identity_constraints,
    evidence_index,
    policy_classes,
    diagnostics,
  });
  const projected = {
    ...input,
    graph_generation: sha256CanonicalRedacted({
      projection_version: "application-default-generic-v1",
      projection_authorization_digest: authorization.authorization_digest,
      projected_content_digest,
      account_timezone: input.account_timezone,
      classifier_version: input.classifier_version,
      liveness_hook_version: input.liveness_hook_version,
      live_claim_revision_ids: [...visibleClaimIds].sort(),
      evidence_ids: [...visibleEvidenceIds].sort(),
    }),
    reader_projection_digest: authorization.principal_digest,
    projection_authorization_digest: authorization.authorization_digest,
    projected_content_digest,
    claims,
    identity_constraints,
    evidence_index,
    policy_classes,
    diagnostics,
  };
  const detached = normalizePlainJson(projected) as ApplicationGrantProjectedTreeInputSnapshot;
  projectedInputs.add(detached);
  return deepFreezePlainJson(detached);
};

// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
export const isApplicationGrantProjectedTreeInput = (
  input: TreeInputSnapshot,
): input is ApplicationGrantProjectedTreeInputSnapshot =>
  projectedInputs.has(input)
  && typeof input.projection_authorization_digest === "string"
  && input.projection_authorization_digest.length > 0
  && typeof input.reader_projection_digest === "string"
  && input.reader_projection_digest.length > 0;
