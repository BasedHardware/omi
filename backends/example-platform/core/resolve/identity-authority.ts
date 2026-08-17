import type { IdentityAuthorization, IdentityEndpoint, SourceIdentityRef } from "../schema";

export interface StandingPolicy {
  policy_ref: string;
  issuer_ref: string;
  producer_ref: string;
  contract_ref: string;
  namespace_instance_ref: string;
  identity_domain: string | null;
  scope_ref: string | null;
  authority_policy_version: string;
  lifecycle: "active" | "revoked";
}

export interface ImmutableOwnerConfirmation { confirmation_ref: string; owner_account_id: string; endpoints: readonly [IdentityEndpoint, IdentityEndpoint]; relation: "same" | "distinct"; }
export interface ImmutableProducerAssertion { assertion_ref: string; owner_account_id: string; endpoint: IdentityEndpoint; producer_ref: string; contract_ref: string; source_identity_ref: SourceIdentityRef; }
/** A replayable support record. It is deliberately about stored provenance, not a score. */
export interface ImmutableIdentitySupport {
  support_ref: string;
  owner_account_id: string;
  evidence_ref: string;
  claim_revision_id: string;
  /** Must be re-derived from the referenced evidence at a ledger boundary. */
  source_independence_key: string;
  /** Derived at extraction from the supplied context, never accepted from a model or caller. */
  support_origin?: "suggested" | "independent";
}
export interface IdentityAuthorityContext {
  owner_confirmations: readonly ImmutableOwnerConfirmation[];
  producer_assertions: readonly ImmutableProducerAssertion[];
  standing_policies: readonly StandingPolicy[];
  identity_support?: readonly ImmutableIdentitySupport[];
}

const endpointKey = (endpoint: IdentityEndpoint): string => endpoint.kind === "entity"
  ? `entity:${endpoint.entity_id}`
  : `source:${JSON.stringify([
    endpoint.source_identity_ref.namespace_instance_ref,
    endpoint.source_identity_ref.local_key,
    endpoint.source_identity_ref.producer.producer_ref,
    endpoint.source_identity_ref.producer.contract_ref,
    endpoint.source_identity_ref.asserted_identity.domain,
    endpoint.source_identity_ref.asserted_identity.scope_ref,
  ])}`;

export const endpointsMatch = (actual: readonly [IdentityEndpoint, IdentityEndpoint], expected: readonly [IdentityEndpoint, IdentityEndpoint]): boolean =>
  endpointKey(actual[0]) === endpointKey(expected[0]) && endpointKey(actual[1]) === endpointKey(expected[1]);

const scopeMatches = (policy: StandingPolicy, left: ImmutableProducerAssertion, right: ImmutableProducerAssertion, authorization: IdentityAuthorization): boolean => {
  const a = left.source_identity_ref;
  const b = right.source_identity_ref;
  return policy.lifecycle === "active" && policy.issuer_ref !== policy.producer_ref &&
    policy.producer_ref === left.producer_ref && policy.producer_ref === right.producer_ref &&
    policy.contract_ref === left.contract_ref && policy.contract_ref === right.contract_ref &&
    a.namespace_instance_ref === b.namespace_instance_ref && a.namespace_instance_ref === policy.namespace_instance_ref &&
    a.local_key === b.local_key && a.asserted_identity.domain === b.asserted_identity.domain &&
    a.asserted_identity.scope_ref === b.asserted_identity.scope_ref &&
    policy.identity_domain === a.asserted_identity.domain && policy.scope_ref === a.asserted_identity.scope_ref &&
    authorization.namespace_scope.namespace_instance_ref === policy.namespace_instance_ref &&
    authorization.namespace_scope.identity_domain === policy.identity_domain && authorization.namespace_scope.scope_ref === policy.scope_ref;
};

/** The only I2 automatic authority set. This function is pure and fail-closed. */
export const authorizeIdentity = (authorization: IdentityAuthorization | null | undefined, expected: { owner_account_id: string; endpoints: readonly [IdentityEndpoint, IdentityEndpoint]; relation: "same" | "distinct"; evaluated_frontier: number }, context: IdentityAuthorityContext): { authorized: boolean; reason: string } => {
  if (!authorization) return { authorized: false, reason: "missing_authorization" };
  if (authorization.lifecycle !== "active" || authorization.superseded_by !== null) return { authorized: false, reason: "inactive_authorization" };
  if (authorization.owner_account_id !== expected.owner_account_id || authorization.relation !== expected.relation || authorization.evaluated_frontier !== expected.evaluated_frontier || !endpointsMatch(authorization.endpoints, expected.endpoints)) return { authorized: false, reason: "authorization_replay_or_endpoint_mismatch" };
  if (authorization.support.kind === "owner_confirmation") {
    const confirmation = context.owner_confirmations.find((item) => item.confirmation_ref === authorization.support.confirmation_ref);
    return confirmation && confirmation.owner_account_id === expected.owner_account_id && confirmation.relation === expected.relation && endpointsMatch(confirmation.endpoints, expected.endpoints)
      ? { authorized: true, reason: "owner_confirmation" }
      : { authorized: false, reason: "missing_immutable_owner_confirmation" };
  }
  if (authorization.support.kind === "consolidation_adjudication") {
    // One source root cannot corroborate a merge.  This is deliberately a
    // cardinality check in addition to distinctness below: a singleton is
    // trivially distinct but not independent support.
    if (authorization.support.support_refs.length < 2) return { authorized: false, reason: authorization.support.support_refs.length === 0 ? "empty_identity_support_set" : "non_independent_support_set" };
    const supports = authorization.support.support_refs.map((ref) => context.identity_support?.find((item) => item.support_ref === ref));
    if (supports.some((item) => !item)) return { authorized: false, reason: "missing_identity_support" };
    const verified = supports as ImmutableIdentitySupport[];
    if (verified.some((item) => item.owner_account_id !== expected.owner_account_id)) return { authorized: false, reason: "foreign_identity_support" };
    // Compatibility fields remain forbidden at the ledger boundary.  The
    // durable derived origin is the only admissible cascade-control field.
    if (verified.some((item) => (item as { provenance_bearing?: boolean; entity_link_support?: "independent" | "suggested" }).provenance_bearing === false || (item as { entity_link_support?: "independent" | "suggested" }).entity_link_support === "suggested")) return { authorized: false, reason: "non_independent_or_unprovenanced_support" };
    // Fail CLOSED on an absent origin.  Defaulting a missing origin to
    // "independent" would let any record whose provenance was never derived
    // count as corroboration -- inverting D50(b), whose whole purpose is that
    // downstream reuse must not corroborate the error that produced it.
    // Unrecorded provenance is not evidence of independent provenance.
    if (verified.some((item) => item.support_origin !== "independent")) return { authorized: false, reason: "non_independent_or_unprovenanced_support" };
    // Independent means distinct persisted source roots, not merely distinct model outputs.
    if (new Set(verified.map((item) => item.source_independence_key)).size !== verified.length) return { authorized: false, reason: "non_independent_support_set" };
    return { authorized: true, reason: "consolidation_adjudication" };
  }
  const left = context.producer_assertions.find((item) => item.assertion_ref === authorization.support.left_assertion_ref);
  const right = context.producer_assertions.find((item) => item.assertion_ref === authorization.support.right_assertion_ref);
  const policy = authorization.standing_policy_ref ? context.standing_policies.find((item) => item.policy_ref === authorization.standing_policy_ref) : undefined;
  return left && right && policy && left.owner_account_id === expected.owner_account_id && right.owner_account_id === expected.owner_account_id &&
    authorization.authority_policy_version === policy.authority_policy_version && endpointsMatch([left.endpoint, right.endpoint], expected.endpoints) && scopeMatches(policy, left, right, authorization)
    ? { authorized: true, reason: "registered_producer_identity_key_equality" }
    : { authorized: false, reason: "invalid_producer_authority" };
};
