import { expect, test } from "bun:test";
import {
  ApplicationReadDenied,
  readAfterApplicationAuthorization,
  type ApplicationMemoryReadAuthorizationRequest,
} from "./authorization-boundary";
import { snapshot } from "./tree.fixture";
import { genericPolicyClassifier } from "./index";
import { buildDeterministicAnchors } from "./tree";

const allowed = (): ApplicationMemoryReadAuthorizationRequest => ({
  owner_account_id: "owner",
  credential: {
    owner_account_id: "owner",
    credential_kind: "mcp_api_key",
    app_id: "app:a",
    key_id: "key:a",
    scopes: ["memories.read"],
    active: true,
  },
  persisted_grant: {
    owner_account_id: "owner",
    consumer: "mcp",
    app_id: "app:a",
    key_id: "key:a",
    enabled: true,
    default_read: true,
    scopes: ["memories.read"],
  },
});
const load = (graph = snapshot(), options: { account_timezone: string } = { account_timezone: "UTC" }) =>
  () => ({ snapshot: graph, options });

test("application read requires scope and exact active persisted grant before store access", () => {
  let storeCalls = 0;
  const result = readAfterApplicationAuthorization(allowed(), () => {
    storeCalls++;
    return { snapshot: snapshot(), options: { account_timezone: "UTC" } };
  });
  expect(result.reader_projection_digest).not.toContain("owner");
  expect(storeCalls).toBe(1);
});

test("application read denials all occur before the supplied store callback", () => {
  const base = allowed();
  const cases: readonly [string, ApplicationMemoryReadAuthorizationRequest, ApplicationReadDenied["reason"]][] = [
    ["oauth identity unresolved", { ...base, credential: { ...base.credential, credential_kind: "oauth" } }, "unsupported_credential_kind"],
    ["developer key grammar unsupported", { ...base, credential: { ...base.credential, credential_kind: "developer_api_key" } }, "unsupported_credential_kind"],
    ["scope absent independently of grant", { ...base, credential: { ...base.credential, scopes: [] } }, "missing_scope"],
    ["owner absent", { ...base, owner_account_id: "" }, "unresolvable_identity"],
    ["app absent", { ...base, credential: { ...base.credential, app_id: null } }, "unresolvable_identity"],
    ["key absent", { ...base, credential: { ...base.credential, key_id: null } }, "unresolvable_identity"],
    ["credential deleted", { ...base, credential: { ...base.credential, active: false } }, "inactive_credential"],
    ["grant absent independently of scope", { ...base, persisted_grant: null }, "missing_grant"],
    ["developer grant unsupported", { ...base, persisted_grant: { ...base.persisted_grant!, consumer: "developer_api" } }, "unsupported_credential_kind"],
    ["cross-owner credential", { ...base, credential: { ...base.credential, owner_account_id: "owner:b" } }, "grant_identity_mismatch"],
    ["cross-owner grant", { ...base, persisted_grant: { ...base.persisted_grant!, owner_account_id: "owner:b" } }, "grant_identity_mismatch"],
    ["wrong app", { ...base, persisted_grant: { ...base.persisted_grant!, app_id: "app:b" } }, "grant_identity_mismatch"],
    ["wrong key", { ...base, persisted_grant: { ...base.persisted_grant!, key_id: "key:b" } }, "grant_identity_mismatch"],
    ["grant disabled", { ...base, persisted_grant: { ...base.persisted_grant!, enabled: false } }, "inactive_grant"],
    ["default read disabled", { ...base, persisted_grant: { ...base.persisted_grant!, default_read: false } }, "inactive_grant"],
    ["grant lacks read scope", { ...base, persisted_grant: { ...base.persisted_grant!, scopes: [] } }, "grant_scope_mismatch"],
  ];
  for (const [label, request, reason] of cases) {
    let storeCalls = 0;
    try {
      readAfterApplicationAuthorization(request, () => { storeCalls++; return { snapshot: snapshot(), options: { account_timezone: "UTC" } }; });
      throw new Error(`expected denial: ${label}`);
    } catch (error) {
      expect(error).toBeInstanceOf(ApplicationReadDenied);
      expect((error as ApplicationReadDenied).reason).toBe(reason);
    }
    expect(storeCalls).toBe(0);
  }
});

test("application projection factory is branded, owner-bound, and canonical/default only", () => {
  const graph = snapshot();
  const projected = readAfterApplicationAuthorization(allowed(), load(graph));
  expect(projected.owner_account_id).toBe("owner");
  expect(projected.reader_projection_digest).not.toBeNull();
  expect(projected.projection_authorization_digest).not.toBeNull();
  expect(projected.claims.every((claim) => claim.placement_status === "canonical" && claim.scope.locality === "durable")).toBe(true);
  expect(projected.claims.map((claim) => claim.claim_revision_id)).toEqual(["a"]);
  expect(projected.claims[0]!.policy_class).toEqual({ subject_class: "generic", sensitivity: "generic", capture_class: "generic" });

  const otherOwner = { ...graph, owner_account_id: "owner:b" };
  expect(() => readAfterApplicationAuthorization(allowed(), load(otherOwner))).toThrow("projection_binding_mismatch");
  expect(() => readAfterApplicationAuthorization(allowed(), () => ({
    snapshot: graph,
    options: { account_timezone: "UTC", request_context: { reader_account_id: "owner", grant: { grant_id: "owner", policy_classes: [] } } },
  }) as never)).toThrow("projection_binding_mismatch");
});

test("owner status never substitutes for the application grant", () => {
  const request = allowed();
  let storeCalls = 0;
  expect(() => readAfterApplicationAuthorization({ ...request, persisted_grant: null }, () => {
    storeCalls++;
    return { snapshot: snapshot(), options: { account_timezone: "UTC" } };
  })).toThrow(ApplicationReadDenied);
  expect(storeCalls).toBe(0);
});

test("authorization invokes a zero-authority loader and returns its internally projected snapshot", () => {
  let receivedArguments = -1;
  const projected = readAfterApplicationAuthorization(allowed(), function (...args: unknown[]) {
    receivedArguments = args.length;
    return { snapshot: snapshot(), options: { account_timezone: "UTC" } };
  } as never);
  expect(receivedArguments).toBe(0);
  expect(projected.claims.map((claim) => claim.claim_revision_id)).toEqual(["a"]);
});

test("projection rejects inherited owners and accessors without invoking getters", () => {
  const inherited = snapshot();
  const originalClaim = inherited.claims[0]!.claim;
  const inheritedClaim = Object.create({ owner_account_id: "owner:b" });
  for (const [key, value] of Object.entries(originalClaim)) if (key !== "owner_account_id") inheritedClaim[key] = value;
  inherited.claims = [{ ...inherited.claims[0]!, claim: inheritedClaim }, ...inherited.claims.slice(1)];
  expect(() => readAfterApplicationAuthorization(allowed(), load(inherited))).toThrow();

  let getterCalls = 0;
  const withGetter = snapshot();
  Object.defineProperty(withGetter.claims[0]!.claim, "owner_account_id", { enumerable: true, get: () => { getterCalls++; return "owner"; } });
  expect(() => readAfterApplicationAuthorization(allowed(), load(withGetter))).toThrow();
  expect(getterCalls).toBe(0);
});

test("projection rejects proxies and non-JSON nested values", () => {
  const proxied = snapshot();
  proxied.claims = [new Proxy(proxied.claims[0]!, {}), ...proxied.claims.slice(1)];
  expect(() => readAfterApplicationAuthorization(allowed(), load(proxied))).toThrow();
  const dated = snapshot();
  dated.events![0]!.event.payload = { when: new Date("2026-01-01T00:00:00Z") };
  expect(() => readAfterApplicationAuthorization(allowed(), load(dated))).toThrow();
});

test("application projection refuses caller classifier overrides and keeps private policy out", () => {
  const malicious = { version: "attacker", classify: () => ({ subject_class: "generic", sensitivity: "generic", capture_class: "generic" }) };
  expect(() => readAfterApplicationAuthorization(allowed(), () => ({
    snapshot: snapshot(), options: { account_timezone: "UTC", classifier: malicious },
  }) as never)).toThrow();
  const projected = readAfterApplicationAuthorization(allowed(), load());
  expect(projected.claims.map((claim) => claim.claim_revision_id)).toEqual(["a"]);
  expect(projected.classifier_version).toBe(genericPolicyClassifier.version);

  const unknown = snapshot();
  unknown.claims = unknown.claims.map((item) => item.revision_id === "a"
    ? { ...item, claim: { ...item.claim, policy_labels: ["unrecognized-policy-label"] } }
    : item);
  const unknownProjected = readAfterApplicationAuthorization(allowed(), load(unknown));
  expect(unknownProjected.claims).toEqual([]);
});

test("application projection rejects nested cross-owner claims and events before projection", () => {
  const claimMismatch = snapshot();
  claimMismatch.claims = claimMismatch.claims.map((item, index) => index === 0
    ? { ...item, claim: { ...item.claim, owner_account_id: "owner:b" } }
    : item);
  expect(() => readAfterApplicationAuthorization(allowed(), load(claimMismatch))).toThrow("projection_binding_mismatch");

  const eventMismatch = snapshot();
  eventMismatch.events = eventMismatch.events!.map((item) => ({ ...item, event: { ...item.event, owner_account_id: "owner:b" } }));
  expect(() => readAfterApplicationAuthorization(allowed(), load(eventMismatch))).toThrow("projection_binding_mismatch");
});

test("visible owner-bearing lineage requires an own tenant identity", () => {
  const claimWithoutOwner = snapshot();
  delete (claimWithoutOwner.claims[0]!.claim as { owner_account_id?: string }).owner_account_id;
  expect(() => readAfterApplicationAuthorization(allowed(), load(claimWithoutOwner))).toThrow("projection_binding_mismatch");

  const eventWithoutOwner = snapshot();
  delete (eventWithoutOwner.events![0]!.event as { owner_account_id?: string }).owner_account_id;
  expect(() => readAfterApplicationAuthorization(allowed(), load(eventWithoutOwner))).toThrow("projection_binding_mismatch");

  const entityWithoutOwner = snapshot();
  delete (entityWithoutOwner.entities[0]!.entity as { owner_account_id?: string }).owner_account_id;
  expect(() => readAfterApplicationAuthorization(allowed(), load(entityWithoutOwner))).toThrow("projection_binding_mismatch");
});

test("hidden private missing evidence is noninterfering while hidden cross-owner data still rejects", () => {
  const hiddenMalformed = snapshot();
  hiddenMalformed.claims = hiddenMalformed.claims.map((item) => item.revision_id === "private"
    ? { ...item, claim: { ...item.claim, evidence_refs: ["missing-private"] } }
    : item);
  const projected = readAfterApplicationAuthorization(allowed(), load(hiddenMalformed));
  expect(projected.claims.map((claim: { claim_revision_id: string }) => claim.claim_revision_id)).toEqual(["a"]);

  const hiddenCrossOwner = snapshot();
  hiddenCrossOwner.claims = hiddenCrossOwner.claims.map((item) => item.revision_id === "private"
    ? { ...item, claim: { ...item.claim, owner_account_id: "owner:b" } }
    : item);
  expect(() => readAfterApplicationAuthorization(allowed(), load(hiddenCrossOwner))).toThrow();
});

test("visible generic event-chain faults fail closed", () => {
  const missingEvent = snapshot();
  missingEvent.evidence = missingEvent.evidence!.map((item) => ({
    ...item, evidence: { ...item.evidence, event_revision_id: "missing-event" },
  }));
  expect(() => readAfterApplicationAuthorization(allowed(), load(missingEvent))).toThrow("projection_binding_mismatch");
});

test("hidden identity constraints cannot rename or coalesce visible application topology", () => {
  const withoutConstraint = snapshot();
  const hiddenEvent = {
    revision_id: "event:private",
    event: {
      ...withoutConstraint.events![0]!.event,
      event_id: "event:private",
      event_revision_id: "event:private",
      evidence_addressable_refs: ["e:private"],
      policy_labels: ["sensitivity:private"],
    },
  };
  const hiddenEvidence = {
    revision_id: "e:private",
    evidence: {
      ...withoutConstraint.evidence![0]!.evidence,
      evidence_id: "e:private",
      event_revision_id: "event:private",
      policy_labels: ["sensitivity:private"],
    },
  };
  withoutConstraint.events = [...withoutConstraint.events!, hiddenEvent];
  withoutConstraint.evidence = [...withoutConstraint.evidence!, hiddenEvidence];
  withoutConstraint.claims = withoutConstraint.claims.map((item) => item.revision_id === "private"
    ? { ...item, claim: { ...item.claim, evidence_refs: ["e:private"] } }
    : item);
  withoutConstraint.entities = [...withoutConstraint.entities, {
    revision_id: "entity:hidden",
    entity: { ...withoutConstraint.entities[0]!.entity, entity_id: "entity:hidden", entity_revision_id: "entity:hidden", handle: "hidden" },
  }];
  const withConstraint = structuredClone(withoutConstraint);
  const endpoints = [{ kind: "entity" as const, entity_id: "entity" }, { kind: "entity" as const, entity_id: "entity:hidden" }] as const;
  withConstraint.identity_constraints = [{
    revision_id: "constraint:hidden",
    constraint: {
      constraint_id: "constraint:hidden",
      owner_account_id: "owner",
      endpoints,
      left_handle: "entity",
      right_handle: "hidden",
      relation: "same",
      evidence_refs: ["e:private"],
      identity_authorization: {
        authorization_id: "authorization:hidden",
        owner_account_id: "owner",
        endpoints,
        relation: "same",
        support: { kind: "owner_confirmation", confirmation_ref: "confirmation:hidden" },
        standing_policy_ref: null,
        namespace_scope: { namespace_instance_ref: null, identity_domain: null, scope_ref: null },
        authority_policy_version: "identity-policy:v1",
        evaluated_frontier: 1,
        actor_provenance: { actor_ref: "owner", producer_ref: null },
        lifecycle: "active",
        superseded_by: null,
      },
      effective_at: 1,
      reversed_at: null,
    },
  }];

  const baseline = readAfterApplicationAuthorization(allowed(), load(withoutConstraint));
  const constrained = readAfterApplicationAuthorization(allowed(), load(withConstraint));
  expect(constrained.identity_constraints).toEqual([]);
  expect(constrained.projected_content_digest).toBe(baseline.projected_content_digest);
  expect(constrained.graph_generation).toBe(baseline.graph_generation);
  expect(buildDeterministicAnchors(constrained)).toEqual(buildDeterministicAnchors(baseline));
});
