import { sha256CanonicalRedacted } from "../ledger";
import { projectTreeInputSnapshot, type GraphSnapshot, type PolicyClass, type TreeInputOptions, type TreeInputSnapshot } from "./index";

// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
const authorizationBrand: unique symbol = Symbol("application-read-authorization");
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
const projectedInputBrand: unique symbol = Symbol("application-grant-projected-tree-input");
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
export interface ApplicationReadAuthorization {
  readonly owner_account_id: string;
  // domain-pending(DIV-DOMAPPS-001)
  readonly app_id: string;
  // domain-pending(DIV-DOMAPPS-006)
  readonly key_id: string;
  /** Opaque non-owner principal; it grants no authority by itself. */
  readonly principal_digest: string;
  readonly projection_policy_classes: readonly Readonly<PolicyClass>[];
  readonly authorization_digest: string;
  readonly [authorizationBrand]: true;
}

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
export interface ApplicationGrantProjectedTreeInputSnapshot extends TreeInputSnapshot {
  readonly reader_projection_digest: string;
  readonly projection_authorization_digest: string;
  readonly [projectedInputBrand]: true;
}

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
const deepFreeze = <Value>(value: Value): Value => {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    for (const nested of Object.values(value)) deepFreeze(nested);
    Object.freeze(value);
  }
  return value;
};

/**
 * Pure application authorization gate. Scope and persisted grant are checked
 * independently, and every denial is resolved before the store callback can run.
 * The returned branded decision binds the exact non-owner application grant.
 */
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
export const readAfterApplicationAuthorization = <Result>(
  request: ApplicationMemoryReadAuthorizationRequest,
  readStore: (authorization: ApplicationReadAuthorization) => Result,
): Result => {
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
    [authorizationBrand]: true,
  });
  return readStore(authorization);
};

/**
 * The only positive application projection factory. It selects canonical,
 * durable/default inputs and never routes through retrieve/Grant's owner shortcut.
 */
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
export const projectApplicationDefaultReadTreeInput = (
  snapshot: GraphSnapshot,
  options: Omit<TreeInputOptions, "request_context">,
  authorization: ApplicationReadAuthorization,
): ApplicationGrantProjectedTreeInputSnapshot => {
  if (authorization[authorizationBrand] !== true
    || snapshot.owner_account_id !== authorization.owner_account_id
    || "request_context" in options) deny("projection_binding_mismatch");
  // domain-pending(DIV-DOMCORE-008)
  const canonicalDefaultSnapshot: GraphSnapshot = {
    ...snapshot,
    claims: snapshot.claims.filter((item) => item.placement_status === "canonical"
      && item.claim.lifecycle === "canonical"
      && item.claim.scope.locality === "durable"),
  };
  const input = projectTreeInputSnapshot(canonicalDefaultSnapshot, options);
  // domain-pending(DIV-DOMCORE-008)
  const claims = input.claims.filter((claim) => claim.policy_class.subject_class === APPLICATION_DEFAULT_SYNTHESIZED_POLICY.subject_class
    && claim.policy_class.sensitivity === APPLICATION_DEFAULT_SYNTHESIZED_POLICY.sensitivity
    && claim.policy_class.capture_class === APPLICATION_DEFAULT_SYNTHESIZED_POLICY.capture_class);
  const visibleClaimIds = new Set(claims.map((claim) => claim.claim_revision_id));
  const visibleEvidenceIds = new Set(claims.flatMap((claim) => claim.evidence_refs));
  const projected = {
    ...input,
    graph_generation: sha256CanonicalRedacted({
      graph_generation: input.graph_generation,
      projection_authorization_digest: authorization.authorization_digest,
      live_claim_revision_ids: [...visibleClaimIds].sort(),
      evidence_ids: [...visibleEvidenceIds].sort(),
    }),
    reader_projection_digest: authorization.principal_digest,
    projection_authorization_digest: authorization.authorization_digest,
    claims,
    evidence_index: input.evidence_index.filter((span) => visibleEvidenceIds.has(span.evidence_id)),
    policy_classes: Object.fromEntries(claims.map((claim) => [claim.claim_revision_id, { ...claim.policy_class }])),
    diagnostics: input.diagnostics.filter((diagnostic) => "claim_revision_id" in diagnostic
      ? visibleClaimIds.has(diagnostic.claim_revision_id)
      : diagnostic.claim_revision_ids.some((revision) => visibleClaimIds.has(revision))),
  };
  const detached = structuredClone(projected) as ApplicationGrantProjectedTreeInputSnapshot;
  Object.defineProperty(detached, projectedInputBrand, { value: true, enumerable: false, configurable: false, writable: false });
  return deepFreeze(detached);
};

// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
export const isApplicationGrantProjectedTreeInput = (
  input: TreeInputSnapshot,
): input is ApplicationGrantProjectedTreeInputSnapshot =>
  (input as Partial<ApplicationGrantProjectedTreeInputSnapshot>)[projectedInputBrand] === true
  && typeof input.projection_authorization_digest === "string"
  && input.projection_authorization_digest.length > 0
  && typeof input.reader_projection_digest === "string"
  && input.reader_projection_digest.length > 0;
