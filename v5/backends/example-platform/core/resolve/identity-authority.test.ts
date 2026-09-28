import { expect, test } from "bun:test";
import { buildEntityResolutionRequest, planEntityResolution } from "./entities";
import { authorizeIdentity } from "./identity-authority";
import { identityThreatFixtures, source } from "../../harness/identity-fixtures";
import type { IdentityAuthorization, IdentityEndpoint, SourceIdentityRef } from "../schema";
import { ingestConversation, localHandleForSourceIdentity } from "../extract/ingest";

const endpoint = (identity: SourceIdentityRef): IdentityEndpoint => ({ kind: "source_identity", source_identity_ref: identity });
const entityEndpoint = (entity_id: string): IdentityEndpoint => ({ kind: "entity", entity_id });
const ownerAuthorization = (identity: SourceIdentityRef, entity_id: string, relation: "same" | "distinct" = "same", frontier = 7): IdentityAuthorization => ({
  authorization_id: `authorization:${identity.namespace_instance_ref}:${identity.local_key}:${entity_id}:${relation}`,
  owner_account_id: "owner", endpoints: [endpoint(identity), entityEndpoint(entity_id)], relation,
  support: { kind: "owner_confirmation", confirmation_ref: `confirmation:${identity.namespace_instance_ref}:${identity.local_key}:${entity_id}:${relation}` },
  standing_policy_ref: null, namespace_scope: { namespace_instance_ref: identity.namespace_instance_ref, identity_domain: identity.asserted_identity.domain, scope_ref: identity.asserted_identity.scope_ref }, authority_policy_version: "identity-policy:v1", evaluated_frontier: frontier,
  actor_provenance: { actor_ref: "owner", producer_ref: null }, lifecycle: "active", superseded_by: null,
});
const ownerContext = (authorization: IdentityAuthorization) => ({ owner_confirmations: [{ confirmation_ref: (authorization.support as { confirmation_ref: string }).confirmation_ref, owner_account_id: "owner", endpoints: authorization.endpoints, relation: authorization.relation }], producer_assertions: [], standing_policies: [] });

test("I2/I3 adversarial precondition: a model-selected candidate is not authority", () => {
  const table = {
    owner_account_id: "owner",
    entities: [{ entity_id: "entity:david", owner_account_id: "owner", entity_revision_id: "entity:david:r1", handle: "david", labels: ["David"] }],
    constraints: [],
  };
  const request = buildEntityResolutionRequest("owner", { handle: "local:m", mention_ref: "m", antecedent_handle: null, uncertainty: [] }, ["evidence:1"], ["entity:david"]);
  expect(planEntityResolution(table, request, { decision: "same", entity_id: "entity:david" })).toMatchObject({ outcome: "abstain" });
});

test("I2 rejects label/candidate/free-text support, producer collisions and self-granted standing", () => {
  const [a, b] = identityThreatFixtures.colliding_person_id_different_producers;
  const authorization = ownerAuthorization(a, "entity:david");
  const expected = { owner_account_id: "owner", endpoints: [endpoint(a), entityEndpoint("entity:david")] as const, relation: "same" as const, evaluated_frontier: 7 };
  expect(authorizeIdentity({ ...authorization, support: { kind: "label_equality", text: "David" } } as unknown as IdentityAuthorization, expected, ownerContext(authorization))).toMatchObject({ authorized: false });
  expect(authorizeIdentity({ ...authorization, support: { kind: "candidate_membership", candidate_id: "entity:david" } } as unknown as IdentityAuthorization, expected, ownerContext(authorization))).toMatchObject({ authorized: false });
  expect(authorizeIdentity({ ...authorization, support: { kind: "evidence_text", text: "David is David" } } as unknown as IdentityAuthorization, expected, ownerContext(authorization))).toMatchObject({ authorized: false });
  const producerAuthorization: IdentityAuthorization = { ...authorization, support: { kind: "producer_identity_key_equality", left_assertion_ref: "assertion:a", right_assertion_ref: "assertion:b" }, standing_policy_ref: "policy:a", actor_provenance: { actor_ref: "producer:a", producer_ref: "producer:a" } };
  const producerContext = {
    owner_confirmations: [],
    producer_assertions: [
      { assertion_ref: "assertion:a", owner_account_id: "owner", endpoint: endpoint(a), producer_ref: "producer:a", contract_ref: "contract:v1", source_identity_ref: a },
      { assertion_ref: "assertion:b", owner_account_id: "owner", endpoint: endpoint(b), producer_ref: "producer:b", contract_ref: "contract:v1", source_identity_ref: b },
    ],
    standing_policies: [{ policy_ref: "policy:a", issuer_ref: "producer:a", producer_ref: "producer:a", contract_ref: "contract:v1", namespace_instance_ref: a.namespace_instance_ref, identity_domain: a.asserted_identity.domain, scope_ref: a.asserted_identity.scope_ref, authority_policy_version: "identity-policy:v1", lifecycle: "active" as const }],
  };
  expect(authorizeIdentity(producerAuthorization, expected, producerContext)).toMatchObject({ authorized: false });
  expect(authorizeIdentity(authorization, { ...expected, endpoints: [endpoint(a), entityEndpoint("entity:other")] }, ownerContext(authorization))).toMatchObject({ authorized: false });
  expect(authorizeIdentity(authorization, { ...expected, relation: "distinct" }, ownerContext(authorization))).toMatchObject({ authorized: false });
});

test("I2 owner confirmation and registered producer key equality are the only automatic controls", () => {
  const identity = source("namespace:registered", "42", "producer:directory");
  const owner = ownerAuthorization(identity, "entity:david");
  const expected = { owner_account_id: "owner", endpoints: [endpoint(identity), entityEndpoint("entity:david")] as const, relation: "same" as const, evaluated_frontier: 7 };
  expect(authorizeIdentity(owner, expected, ownerContext(owner))).toMatchObject({ authorized: true, reason: "owner_confirmation" });
  const a = source("namespace:registered", "42", "producer:directory");
  const b = source("namespace:registered", "42", "producer:directory");
  const producer: IdentityAuthorization = { ...owner, endpoints: [endpoint(a), endpoint(b)], support: { kind: "producer_identity_key_equality", left_assertion_ref: "assertion:1", right_assertion_ref: "assertion:2" }, standing_policy_ref: "policy:directory", actor_provenance: { actor_ref: "registry", producer_ref: "producer:directory" } };
  expect(authorizeIdentity(producer, { owner_account_id: "owner", endpoints: [endpoint(a), endpoint(b)], relation: "same", evaluated_frontier: 7 }, {
    owner_confirmations: [], producer_assertions: [
      { assertion_ref: "assertion:1", owner_account_id: "owner", endpoint: endpoint(a), producer_ref: "producer:directory", contract_ref: "contract:v1", source_identity_ref: a },
      { assertion_ref: "assertion:2", owner_account_id: "owner", endpoint: endpoint(b), producer_ref: "producer:directory", contract_ref: "contract:v1", source_identity_ref: b },
    ], standing_policies: [{ policy_ref: "policy:directory", issuer_ref: "registry", producer_ref: "producer:directory", contract_ref: "contract:v1", namespace_instance_ref: "namespace:registered", identity_domain: "real-world-subject", scope_ref: "owner:fixture", authority_policy_version: "identity-policy:v1", lifecycle: "active" }],
  })).toMatchObject({ authorized: true, reason: "registered_producer_identity_key_equality" });
});

test("E1 rejects a consolidation adjudication with an empty support set", () => {
  const endpoints = [entityEndpoint("A"), entityEndpoint("B")] as const;
  const authorization = {
    authorization_id: "authorization:empty-support", owner_account_id: "owner", endpoints, relation: "same" as const,
    support: { kind: "consolidation_adjudication" as const, support_refs: [], proposal_lineage_ref: "proposal:empty" },
    standing_policy_ref: null, namespace_scope: { namespace_instance_ref: null, identity_domain: null, scope_ref: null }, authority_policy_version: "identity-policy:v1", evaluated_frontier: 7,
    actor_provenance: { actor_ref: "dream", producer_ref: null }, lifecycle: "active" as const, superseded_by: null,
  };
  expect(authorizeIdentity(authorization, { owner_account_id: "owner", endpoints, relation: "same", evaluated_frontier: 7 }, { owner_confirmations: [], producer_assertions: [], standing_policies: [], identity_support: [] }))
    .toMatchObject({ authorized: false, reason: "empty_identity_support_set" });
});

test("E1 rejects consolidation support that has only one provenance root", () => {
  const endpoints = [entityEndpoint("A"), entityEndpoint("B")] as const;
  const authorization = {
    authorization_id: "authorization:shared-root", owner_account_id: "owner", endpoints, relation: "same" as const,
    support: { kind: "consolidation_adjudication" as const, support_refs: ["support:one", "support:two"], proposal_lineage_ref: "proposal:shared-root" },
    standing_policy_ref: null, namespace_scope: { namespace_instance_ref: null, identity_domain: null, scope_ref: null }, authority_policy_version: "identity-policy:v1", evaluated_frontier: 7,
    actor_provenance: { actor_ref: "dream", producer_ref: null }, lifecycle: "active" as const, superseded_by: null,
  };
  const support = (support_ref: string) => ({ support_ref, owner_account_id: "owner", evidence_ref: `evidence:${support_ref}`, claim_revision_id: `claim:${support_ref}`, source_independence_key: "capture:one", support_origin: "independent" as const });
  expect(authorizeIdentity(authorization, { owner_account_id: "owner", endpoints, relation: "same", evaluated_frontier: 7 }, { owner_confirmations: [], producer_assertions: [], standing_policies: [], identity_support: [support("support:one"), support("support:two")] }))
    .toEqual({ authorized: false, reason: "non_independent_support_set" });
});

test("E4 source identity equality includes producer, contract, domain, and scope", () => {
  const asserted = source("namespace:shared", "42", "producer:a");
  const other = { ...asserted, producer: { producer_ref: "producer:b", contract_ref: "contract:other" }, asserted_identity: { domain: "other-domain", scope_ref: "other-scope" } };
  const authorization = ownerAuthorization(asserted, "entity:person");
  expect(authorizeIdentity(authorization, { owner_account_id: "owner", endpoints: [endpoint(other), entityEndpoint("entity:person")], relation: "same", evaluated_frontier: 7 }, ownerContext(authorization))).toMatchObject({ authorized: false });
});
