// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMCORE-007)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMAPPS-007)
// domain-pending(DIV-DOMX-001)
// domain-pending(DIV-DOMX-006)
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

test("authorization rejects every malformed runtime shape before store access", () => {
  const base = allowed();
  const withoutKey = (value: object, key: string): Record<string, unknown> =>
    Object.fromEntries(Object.entries(value).filter(([candidate]) => candidate !== key));
  const malformed: unknown[] = [
    ...["owner_account_id", "credential", "persisted_grant"].map((key) => withoutKey(base, key)),
    ...["owner_account_id", "credential_kind", "app_id", "key_id", "scopes", "active"]
      .map((key) => ({ ...base, credential: withoutKey(base.credential, key) })),
    ...["owner_account_id", "consumer", "app_id", "key_id", "enabled", "default_read", "scopes"]
      .map((key) => ({ ...base, persisted_grant: withoutKey(base.persisted_grant!, key) })),
    { ...base, extra: true },
    { ...base, credential: { ...base.credential, extra: true } },
    { ...base, credential: { ...base.credential, active: "false" } },
    { ...base, credential: { ...base.credential, scopes: "memories.read" } },
    { ...base, credential: { ...base.credential, scopes: ["memories.read", 7] } },
    { ...base, persisted_grant: { ...base.persisted_grant!, extra: true } },
    { ...base, persisted_grant: { ...base.persisted_grant!, enabled: 1 } },
    { ...base, persisted_grant: { ...base.persisted_grant!, default_read: "false" } },
    { ...base, persisted_grant: { ...base.persisted_grant!, scopes: "memories.read" } },
    { ...base, persisted_grant: { ...base.persisted_grant!, scopes: ["memories.read", false] } },
  ];
  for (const request of malformed) {
    let storeCalls = 0;
    expect(() => readAfterApplicationAuthorization(request as never, () => {
      storeCalls++;
      return { snapshot: snapshot(), options: { account_timezone: "UTC" } };
    })).toThrow();
    expect(storeCalls).toBe(0);
  }
});

test("authorization rejects non-index scope properties before store access", () => {
  const request = allowed();
  const scopes = [...request.credential.scopes];
  Object.defineProperty(scopes, "4294967295", { value: "smuggled.scope", enumerable: true });
  let storeCalls = 0;
  expect(() => readAfterApplicationAuthorization({ ...request, credential: { ...request.credential, scopes } }, () => {
    storeCalls++;
    return { snapshot: snapshot(), options: { account_timezone: "UTC" } };
  })).toThrow("plain JSON rejects array properties");
  expect(storeCalls).toBe(0);
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
  expect(() => readAfterApplicationAuthorization(allowed(), () => ({
    snapshot: graph, options: { account_timezone: "UTC" }, extra: "not-authority",
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

test("later private evidence revisions cannot suppress a visible generic predecessor", () => {
  const absent = snapshot();
  absent.evidence = absent.evidence!.map((item) => ({ ...item, commit_sequence: 1 }));
  const hidden = structuredClone(absent);
  hidden.evidence = [...hidden.evidence!, {
    revision_id: "e:private-head",
    commit_sequence: 2,
    evidence: {
      ...hidden.evidence![0]!.evidence,
      excerpt: "hidden replacement",
      policy_labels: ["sensitivity:private"],
    },
  }];
  const absentProjection = readAfterApplicationAuthorization(allowed(), load(absent));
  const hiddenProjection = readAfterApplicationAuthorization(allowed(), load(hidden));
  expect(JSON.stringify(hiddenProjection)).toBe(JSON.stringify(absentProjection));
  expect(hiddenProjection.projected_content_digest).toBe(absentProjection.projected_content_digest);
  expect(hiddenProjection.graph_generation).toBe(absentProjection.graph_generation);
});

test("malformed or foreign visible evidence heads fail closed", () => {
  const tied = snapshot();
  tied.evidence = [
    { ...tied.evidence![0]!, revision_id: "e:r1", commit_sequence: 2 },
    { ...tied.evidence![0]!, revision_id: "e:r2", commit_sequence: 2 },
  ];
  expect(() => readAfterApplicationAuthorization(allowed(), load(tied))).toThrow("projection_binding_mismatch");

  const foreign = snapshot();
  foreign.events = [...foreign.events!, {
    revision_id: "event:foreign",
    event: { ...foreign.events![0]!.event, event_id: "event:foreign", event_revision_id: "event:foreign", owner_account_id: "owner:b" },
  }];
  foreign.evidence = [
    { ...foreign.evidence![0]!, revision_id: "e:r1", commit_sequence: 1 },
    { ...foreign.evidence![0]!, revision_id: "e:r2", commit_sequence: 2,
      evidence: { ...foreign.evidence![0]!.evidence, event_revision_id: "event:foreign" } },
  ];
  expect(() => readAfterApplicationAuthorization(allowed(), load(foreign))).toThrow("projection_binding_mismatch");
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

test("hidden private-only duplicate entity topology is byte-noninterfering", () => {
  const absent = snapshot();
  const hidden = snapshot();
  hidden.entities = [...hidden.entities, {
    revision_id: "entity:hidden",
    entity: { ...hidden.entities[0]!.entity, entity_id: "entity:hidden", entity_revision_id: "entity:hidden" },
  }];
  hidden.claims = hidden.claims.map((item) => item.revision_id === "private"
    ? { ...item, claim: { ...item.claim, arguments: item.claim.arguments.map((argument) => ({
      ...argument, value: argument.value.kind === "entity_ref" ? { ...argument.value, ref: "entity:hidden" } : argument.value,
    })) } }
    : item);

  const absentProjection = readAfterApplicationAuthorization(allowed(), load(absent));
  const hiddenProjection = readAfterApplicationAuthorization(allowed(), load(hidden));
  expect(JSON.stringify(hiddenProjection)).toBe(JSON.stringify(absentProjection));
  expect(buildDeterministicAnchors(hiddenProjection)).toEqual(buildDeterministicAnchors(absentProjection));
});

test("hidden private lineage heads cannot suppress a visible generic predecessor", () => {
  const hidden = snapshot();
  hidden.claims = hidden.claims.map((item) => item.revision_id === "a"
    ? { ...item, commit_sequence: 1 }
    : {
      ...item,
      commit_sequence: 2,
      claim: {
        ...item.claim,
        claim_lineage_id: "lineage:a",
        supersedes_revision_ids: ["a"],
      },
    });
  const absent = { ...hidden, claims: hidden.claims.filter((item) => item.revision_id !== "private"),
    adjacency: hidden.adjacency.filter((edge) => edge.claim_revision_id !== "private") };
  const hiddenProjection = readAfterApplicationAuthorization(allowed(), load(hidden));
  const absentProjection = readAfterApplicationAuthorization(allowed(), load(absent));
  expect(hiddenProjection.claims.map((claim) => claim.claim_revision_id)).toEqual(["a"]);
  expect(JSON.stringify(hiddenProjection)).toBe(JSON.stringify(absentProjection));
});

test("malformed or foreign records retained by the visible closure fail closed", () => {
  const duplicateHandle = snapshot();
  duplicateHandle.entities = [...duplicateHandle.entities, {
    revision_id: "entity:second",
    entity: { ...duplicateHandle.entities[0]!.entity, entity_id: "entity:second", entity_revision_id: "entity:second" },
  }];
  duplicateHandle.claims = duplicateHandle.claims.map((item) => item.revision_id === "a"
    ? { ...item, claim: { ...item.claim, arguments: [...item.claim.arguments, {
      slot_id: "object", role: "object", value: { kind: "entity_ref" as const, ref: "entity:second" },
    }] } }
    : item);
  expect(() => readAfterApplicationAuthorization(allowed(), load(duplicateHandle))).toThrow();

  const predicateWithoutOwner = snapshot();
  predicateWithoutOwner.claims = predicateWithoutOwner.claims.map((item) => item.revision_id === "a"
    ? { ...item, claim: { ...item.claim, predicate_id: "predicate:a" } }
    : item);
  predicateWithoutOwner.predicates = [{
    revision_id: "predicate:a",
    predicate: {
      predicate_id: "predicate:a", owner_account_id: "owner", predicate_revision_id: "predicate:a",
      identity_name: "met", display_name: "met", lifecycle: "canonical", slot_ids: ["subject"],
    },
  }];
  delete (predicateWithoutOwner.predicates[0]!.predicate as { owner_account_id?: string }).owner_account_id;
  expect(() => readAfterApplicationAuthorization(allowed(), load(predicateWithoutOwner))).toThrow("projection_binding_mismatch");

  const foreignPredicate = snapshot();
  foreignPredicate.claims = foreignPredicate.claims.map((item) => item.revision_id === "a"
    ? { ...item, claim: { ...item.claim, predicate_id: "predicate:a" } }
    : item);
  foreignPredicate.predicates = [{
    revision_id: "predicate:a",
    predicate: {
      predicate_id: "predicate:a", owner_account_id: "owner:b", predicate_revision_id: "predicate:a",
      identity_name: "met", display_name: "met", lifecycle: "canonical", slot_ids: ["subject"],
    },
  }];
  expect(() => readAfterApplicationAuthorization(allowed(), load(foreignPredicate))).toThrow("projection_binding_mismatch");
});
