import { expect, test } from "bun:test";
import {
  ApplicationReadDenied,
  readAfterApplicationAuthorization,
  type ApplicationMemoryReadAuthorizationRequest,
} from "./authorization-boundary";
import { snapshot } from "./tree.fixture";
import { genericPolicyClassifier } from "./index";

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

test("application read requires scope and exact active persisted grant before store access", () => {
  let storeCalls = 0;
  const result = readAfterApplicationAuthorization(allowed(), (project) => {
    storeCalls++;
    expect(project(snapshot(), { account_timezone: "UTC" }).reader_projection_digest).not.toContain("owner");
    return "read-result";
  });
  expect(result).toBe("read-result");
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
      readAfterApplicationAuthorization(request, () => { storeCalls++; return "must-not-read"; });
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
  const projected = readAfterApplicationAuthorization(allowed(), (project) =>
    project(graph, { account_timezone: "UTC" }));
  expect(projected.owner_account_id).toBe("owner");
  expect(projected.reader_projection_digest).not.toBeNull();
  expect(projected.projection_authorization_digest).not.toBeNull();
  expect(projected.claims.every((claim) => claim.placement_status === "canonical" && claim.scope.locality === "durable")).toBe(true);
  expect(projected.claims.map((claim) => claim.claim_revision_id)).toEqual(["a"]);
  expect(projected.claims[0]!.policy_class).toEqual({ subject_class: "generic", sensitivity: "generic", capture_class: "generic" });

  const otherOwner = { ...graph, owner_account_id: "owner:b" };
  expect(() => readAfterApplicationAuthorization(allowed(), (project) =>
    project(otherOwner, { account_timezone: "UTC" }))).toThrow("projection_binding_mismatch");
  expect(() => readAfterApplicationAuthorization(allowed(), (project) =>
    project(graph, { account_timezone: "UTC", request_context: { reader_account_id: "owner", grant: { grant_id: "owner", policy_classes: [] } } } as never))).toThrow("projection_binding_mismatch");
});

test("owner status never substitutes for the application grant", () => {
  const request = allowed();
  let storeCalls = 0;
  expect(() => readAfterApplicationAuthorization({ ...request, persisted_grant: null }, () => { storeCalls++; })).toThrow(ApplicationReadDenied);
  expect(storeCalls).toBe(0);
});

test("authorization callback exposes only a closure capability, never a recoverable decision token", () => {
  readAfterApplicationAuthorization(allowed(), (capability) => {
    expect(typeof capability).toBe("function");
    expect(Reflect.ownKeys(Object(capability))).not.toContain("authorization_digest");
    return null;
  });
});

test("application projection refuses caller classifier overrides and keeps private policy out", () => {
  const malicious = { version: "attacker", classify: () => ({ subject_class: "generic", sensitivity: "generic", capture_class: "generic" }) };
  expect(() => readAfterApplicationAuthorization(allowed(), (project) =>
    project(snapshot(), { account_timezone: "UTC", classifier: malicious } as never))).toThrow("projection_binding_mismatch");
  const projected = readAfterApplicationAuthorization(allowed(), (project) => project(snapshot(), { account_timezone: "UTC" }));
  expect(projected.claims.map((claim) => claim.claim_revision_id)).toEqual(["a"]);
  expect(projected.classifier_version).toBe(genericPolicyClassifier.version);

  const unknown = snapshot();
  unknown.claims = unknown.claims.map((item) => item.revision_id === "a"
    ? { ...item, claim: { ...item.claim, policy_labels: ["unrecognized-policy-label"] } }
    : item);
  const unknownProjected = readAfterApplicationAuthorization(allowed(), (project) => project(unknown, { account_timezone: "UTC" }));
  expect(unknownProjected.claims).toEqual([]);
});

test("application projection rejects nested cross-owner claims and events before projection", () => {
  const claimMismatch = snapshot();
  claimMismatch.claims = claimMismatch.claims.map((item, index) => index === 0
    ? { ...item, claim: { ...item.claim, owner_account_id: "owner:b" } }
    : item);
  expect(() => readAfterApplicationAuthorization(allowed(), (project) =>
    project(claimMismatch, { account_timezone: "UTC" }))).toThrow("projection_binding_mismatch");

  const eventMismatch = snapshot();
  eventMismatch.events = eventMismatch.events!.map((item) => ({ ...item, event: { ...item.event, owner_account_id: "owner:b" } }));
  expect(() => readAfterApplicationAuthorization(allowed(), (project) =>
    project(eventMismatch, { account_timezone: "UTC" }))).toThrow("projection_binding_mismatch");
});
