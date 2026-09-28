// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMX-006)
import { createHash } from "node:crypto";
import { describe, expect, test } from "bun:test";

import { createQaDevAuthRegistry, type QaPrincipal } from "./dev-auth";

const PRINCIPAL: QaPrincipal = Object.freeze({
  owner_account_id: "owner-qa-1",
  app_id: "app-qa-1",
  key_id: "key-qa-1",
  scopes: Object.freeze(["memories.read"]),
});

const TOKEN = "qa_dev_token_roundtrip_001";

describe("createQaDevAuthRegistry", () => {
  test("round-trip: registered token authenticates to the exact expected credential tuple", () => {
    const registry = createQaDevAuthRegistry();
    registry.register(PRINCIPAL, TOKEN);
    const credential = registry.authenticate(`Bearer ${TOKEN}`);
    expect(credential).not.toBeNull();
    expect(credential).toEqual({
      kind: "mcp_api_key",
      scopes: ["memories.read"],
      rateLimitKey: {
        prefix: "mcp",
        uid: "owner-qa-1",
        app_id: "app-qa-1",
        key_id: "key-qa-1",
      },
      authentication: {
        // A real SHA-256 over the principal tuple, not the tuple in clear text.
        // Asserted as a literal so a regression to a readable identity string
        // fails here rather than silently shipping identifiers into logs.
        digest: createHash("sha256")
          .update(JSON.stringify([
            "qa-dev-auth-principal-v1",
            "owner-qa-1",
            "app-qa-1",
            "key-qa-1",
          ]))
          .digest("hex"),
      },
    });
    expect(credential!.authentication).not.toEqual(expect.objectContaining({ token: TOKEN }));
    expect(JSON.stringify(credential)).not.toContain(TOKEN);
  });

  test("unknown token, missing header, malformed scheme, and revoked credential all return null and are mutually indistinguishable", () => {
    const registry = createQaDevAuthRegistry();
    registry.register(PRINCIPAL, TOKEN);

    const missing = registry.authenticate(undefined);
    const malformed = registry.authenticate("Token qa_not_bearer");
    const unknown = registry.authenticate("Bearer qa_unknown_token_zzz");
    registry.revokeCredential(PRINCIPAL);
    const revoked = registry.authenticate(`Bearer ${TOKEN}`);

    expect(missing).toBeNull();
    expect(malformed).toBeNull();
    expect(unknown).toBeNull();
    expect(revoked).toBeNull();
    // Same null sentinel — callers cannot branch on failure kind.
    expect(missing).toBe(unknown);
    expect(unknown).toBe(revoked);
    expect(revoked).toBe(malformed);
  });

  test("Bearer header grammar rejects double space, wrong case, leading space, and a second token", () => {
    const registry = createQaDevAuthRegistry();
    registry.register(PRINCIPAL, TOKEN);
    expect(registry.authenticate(`Bearer  ${TOKEN}`)).toBeNull();
    expect(registry.authenticate(`bearer ${TOKEN}`)).toBeNull();
    expect(registry.authenticate(` Bearer ${TOKEN}`)).toBeNull();
    expect(registry.authenticate(`Bearer ${TOKEN} extra`)).toBeNull();
  });

  test("revokeCredential clears active, revokeGrant clears the grant, and restore returns both", () => {
    const registry = createQaDevAuthRegistry();
    registry.register(PRINCIPAL, TOKEN);

    expect(registry.resolveCredential(PRINCIPAL).active).toBe(true);
    expect(registry.resolveGrant(PRINCIPAL)).toEqual({
      owner_account_id: "owner-qa-1",
      consumer: "mcp",
      app_id: "app-qa-1",
      key_id: "key-qa-1",
      enabled: true,
      default_read: true,
      scopes: ["memories.read"],
    });

    registry.revokeCredential(PRINCIPAL);
    expect(registry.resolveCredential(PRINCIPAL).active).toBe(false);
    expect(registry.authenticate(`Bearer ${TOKEN}`)).toBeNull();

    registry.revokeGrant(PRINCIPAL);
    expect(registry.resolveGrant(PRINCIPAL)).toBeNull();

    registry.restore(PRINCIPAL);
    expect(registry.resolveCredential(PRINCIPAL).active).toBe(true);
    expect(registry.resolveGrant(PRINCIPAL)).not.toBeNull();
    expect(registry.authenticate(`Bearer ${TOKEN}`)).not.toBeNull();
  });

  test("mutating a returned credential or grant does not change the next resolve", () => {
    // red-proof: return the internal object directly
    const registry = createQaDevAuthRegistry();
    registry.register(PRINCIPAL, TOKEN);

    const credential = registry.resolveCredential(PRINCIPAL);
    credential.active = false;
    credential.owner_account_id = "mutated-owner";
    credential.app_id = "mutated-app";
    expect(registry.resolveCredential(PRINCIPAL)).toEqual({
      owner_account_id: "owner-qa-1",
      credential_kind: "mcp_api_key",
      app_id: "app-qa-1",
      key_id: "key-qa-1",
      scopes: ["memories.read"],
      active: true,
    });

    const grant = registry.resolveGrant(PRINCIPAL);
    expect(grant).not.toBeNull();
    grant!.enabled = false;
    grant!.default_read = false;
    grant!.owner_account_id = "mutated-owner";
    grant!.app_id = "mutated-app";
    expect(registry.resolveGrant(PRINCIPAL)).toEqual({
      owner_account_id: "owner-qa-1",
      consumer: "mcp",
      app_id: "app-qa-1",
      key_id: "key-qa-1",
      enabled: true,
      default_read: true,
      scopes: ["memories.read"],
    });
  });

  test("authorizationChecks increments once per resolveGrant call", () => {
    const registry = createQaDevAuthRegistry();
    registry.register(PRINCIPAL, TOKEN);
    expect(registry.authorizationChecks()).toBe(0);
    registry.resolveGrant(PRINCIPAL);
    expect(registry.authorizationChecks()).toBe(1);
    registry.resolveCredential(PRINCIPAL);
    expect(registry.authorizationChecks()).toBe(1);
    registry.revokeGrant(PRINCIPAL);
    expect(registry.resolveGrant(PRINCIPAL)).toBeNull();
    expect(registry.authorizationChecks()).toBe(2);
    registry.restore(PRINCIPAL);
    registry.resolveGrant(PRINCIPAL);
    expect(registry.authorizationChecks()).toBe(3);
  });

  test("scopes arrays returned from resolve and authenticate are frozen copies", () => {
    const registry = createQaDevAuthRegistry();
    registry.register(PRINCIPAL, TOKEN);
    const credential = registry.authenticate(`Bearer ${TOKEN}`);
    expect(Object.isFrozen(credential!.scopes)).toBe(true);
    expect(Object.isFrozen(registry.resolveCredential(PRINCIPAL).scopes)).toBe(true);
    expect(Object.isFrozen(registry.resolveGrant(PRINCIPAL)!.scopes)).toBe(true);
  });
});
