import { describe, expect, test } from "bun:test";

import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import {
  MCP_LIVE_KEY_SCOPE,
  defineMcpCredentialAdapter,
  type McpGrantRecord,
  type McpKeyRecord,
} from "../stores/mcp-credential-adapter";

const digest = (character: string): string => character.repeat(64);
const issuer = createAuthorizedLedgerWriteContextIssuer();
const context = () => issuer.issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "user:one",
  account_id: "account:alice", application_id: "app:mcp", credential_id: "credential:one",
  credential_generation: 1, capability: "memories.read", grant_id: "grant:one",
  grant_version: 1, account_epoch: 7, destination_activation_revision: 17,
  lifecycle_state: "active",
  deletion_epoch: null,
  authentication_strength: "user-presence",
  issued_at_epoch_seconds: 100, expires_at_epoch_seconds: 200,
  authorization_state_digest: digest("a"),
}, 150);

describe("MCP credential adapter", () => {
  test("maps live list/create/revoke/grant/wipe without exposing a new token scheme", async () => {
    const keys = new Map<string, McpKeyRecord>();
    const grants = new Map<string, McpGrantRecord>();
    const adapter = defineMcpCredentialAdapter({
      load: async (keyId) => keys.get(keyId) ?? null,
      list: async (owner) => [...keys.values()].filter((record) => record.owner_account_id === owner),
      save: async (record) => { keys.set(record.key_id, record); },
      saveGrant: async (grant) => { grants.set(grant.grant_id, grant); },
      loadGrant: async (grantId) => grants.get(grantId) ?? null,
    }, () => ({ prefix: "omk_live", secret_hash: digest("a") }));

    const created = await adapter.create(context(), "laptop", "2026-08-14T00:00:00Z");
    expect(created.kind).toBe("ok");
    if (created.kind !== "ok") return;
    expect(created.record.scopes).toEqual([MCP_LIVE_KEY_SCOPE]);
    expect(created.record.key_prefix).toBe("omk_live");
    expect(created.record.secret_hash).toBe(digest("a"));

    const listed = await adapter.list(context());
    expect(listed.kind).toBe("listed");
    if (listed.kind !== "listed") return;
    expect(JSON.stringify(listed)).not.toContain(digest("a"));
    expect(listed.records[0]?.scopes).toEqual([MCP_LIVE_KEY_SCOPE]);

    await expect(adapter.revoke(context(), created.record.key_id)).resolves.toEqual({ kind: "revoked" });
    const granted = await adapter.create(context(), "second", "2026-08-14T00:01:00Z");
    if (granted.kind !== "ok") return;
    const grant = await adapter.grant(context(), granted.record.key_id);
    expect(grant.kind).toBe("granted");
    if (grant.kind !== "granted") return;
    await expect(adapter.revokeGrant(context(), grant.grant.grant_id)).resolves.toEqual({ kind: "revoked" });
    await expect(adapter.wipeForAccountDeletion(context()))
      .resolves.toMatchObject({ kind: "wiped" });
  });
});
