import { expect, test } from "bun:test";
import {
  bindFirebaseIdentity,
  parseBindingManifest,
  type BindingManifest,
} from "./bind-firebase-identity";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
} from "../drivers/postgres/connection";
const manifest: BindingManifest = {
  projectId: "test-project",
  uid: "firebase-user",
  accountId: "opaque-account",
  principalId: "opaque-principal",
  applicationId: "omi-app",
  credentialId: "credential-1",
  controlRevision: 7,
  controlHash: "a".repeat(64),
  credentialHash: "b".repeat(64),
  grantHash: "c".repeat(64),
  expiresAt: 1500,
  reasonRef: "ticket-123",
};
function harness() {
  let root: Record<string, unknown> | undefined;
  let binding: Record<string, unknown> | undefined;
  let mode = "";
  const events: string[] = [],
    names: string[] = [];
  const pool: PostgresTransactionPool = {
    async withTransaction(options, callback) {
      expect(options).toMatchObject({
        isolationLevel: "serializable",
        accessMode: "read write",
      });
      const before = [root, binding];
      const connection: CheckedOutPostgresConnection = {
        connectionIdentity: {},
        async query(statement) {
          names.push(statement.name);
          const rows = statement.name.endsWith(".authority")
            ? mode === "deny"
              ? []
              : [{ control_revision: 7 }]
            : statement.name.endsWith(".existing_identity")
            ? root
              ? [root]
              : []
            : statement.name.endsWith(".existing_credential")
            ? binding
              ? [binding]
              : []
            : [];
          return rows as never;
        },
        async execute(statement) {
          names.push(statement.name);
          if (statement.name.endsWith(".insert_identity"))
            root = {
              account_id: manifest.accountId,
              principal_id: manifest.principalId,
              source_control_revision: 7,
            };
          else {
            if (mode === "fail") throw Error("private provider error");
            binding = {
              principal_id: manifest.principalId,
              credential_id: manifest.credentialId,
            };
          }
          return { rowCount: 1 };
        },
      };
      try {
        return await callback(connection);
      } catch (error) {
        [root, binding] = before;
        throw error;
      }
    },
  };
  const options = {
    manifest,
    token: "private-test-token",
    pool,
    now: () => 1000,
    verifier: {
      async resolve() {
        return {
          firebase_project_id: manifest.projectId,
          firebase_uid: manifest.uid,
          authentication_strength: "firebase-id-token" as const,
          expires_at_epoch_seconds: 2000,
        };
      },
    },
    async audit(event: string) {
      events.push(event);
    },
  };
  return {
    options,
    events,
    names,
    state: () => ({ root, binding }),
    setMode(value: string) {
      mode = value;
      if (value === "conflict") root = { account_id: "another-account" };
    },
  };
}
test("binding creates two immutable mappings once and exact replay is unchanged", async () => {
  const h = harness();
  expect(await bindFirebaseIdentity(h.options)).toBe("bound");
  expect(await bindFirebaseIdentity(h.options)).toBe("unchanged");
  expect(h.names.filter((name) => name.includes(".insert_"))).toHaveLength(2);
  expect(h.events).toEqual(["intent", "bound", "intent", "unchanged"]);
});
test("absent authority or conflicting tenant binding cannot insert", async () => {
  for (const mode of ["deny", "conflict"]) {
    const h = harness();
    h.setMode(mode);
    await expect(bindFirebaseIdentity(h.options)).rejects.toThrow(
      "binding_unavailable_or_conflicting"
    );
    expect(h.names.some((name) => name.includes(".insert_"))).toBe(false);
    expect(h.events).toEqual(["intent", "failed"]);
  }
});
test("second insert failure rolls back the first and closes provider errors", async () => {
  const h = harness();
  h.setMode("fail");
  await expect(bindFirebaseIdentity(h.options)).rejects.toThrow(
    "binding_unavailable_or_conflicting"
  );
  expect(h.state()).toEqual({ root: undefined, binding: undefined });
});
test("identity failure, expired scope and unavailable audit prevent mutation", async () => {
  const h = harness();
  await expect(
    bindFirebaseIdentity({
      ...h.options,
      verifier: {
        async resolve() {
          return null;
        },
      },
    })
  ).rejects.toThrow("binding_identity_rejected");
  await expect(
    bindFirebaseIdentity({
      ...h.options,
      audit: async () => {
        throw Error("receipt unavailable");
      },
    })
  ).rejects.toThrow();
  expect(() =>
    parseBindingManifest({ ...manifest, expiresAt: 1000 }, 1000)
  ).toThrow();
  expect(() =>
    parseBindingManifest({ ...manifest, expiresAt: 2000 }, 1000)
  ).toThrow();
  expect(h.names).toHaveLength(0);
});

test("a different verified Firebase UID cannot retarget the operator manifest", async () => {
  const h = harness();
  const verified = await h.options.verifier.resolve();
  await expect(
    bindFirebaseIdentity({
      ...h.options,
      verifier: {
        async resolve() {
          return { ...verified, firebase_uid: "other-user" };
        },
      },
    })
  ).rejects.toThrow("binding_identity_rejected");
  expect(h.names).toHaveLength(0);
});

test("audit failure after commit is marked for reconciliation without pretending rollback", async () => {
  const h = harness();
  const events: string[] = [];
  await expect(
    bindFirebaseIdentity({
      ...h.options,
      async audit(event) {
        events.push(event);
        if (event === "bound") throw Error("receipt write failed");
      },
    })
  ).rejects.toThrow("binding_unavailable_or_conflicting");
  expect(events).toEqual(["intent", "bound", "reconcile_required"]);
  expect(h.state().binding).toBeDefined();
});
