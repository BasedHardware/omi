import { describe, expect, test } from "bun:test";

import { inspectApplicationAccountControl } from
  "../../apps/service/control/application-control-source";
import {
  LOAD_APPLICATION_ACCOUNT_CONTROL,
  createPostgresApplicationAccountControlSource,
} from "./application-account-control-source";

const row = (overrides: Record<string, unknown> = {}) => ({
  account_id: "account:alice",
  control_revision: "17",
  account_generation: "new",
  account_epoch: "12",
  lifecycle_state: "active",
  deletion_epoch: null,
  activated_epoch: "12",
  activation_control_revision: "17",
  conflict_reason: null,
  conflict_at_revision: null,
  ...overrides,
});

describe("PostgreSQL application account-control source", () => {
  test("loads one exact coherent projection through the fixed query", async () => {
    const statements: unknown[] = [];
    const source = createPostgresApplicationAccountControlSource({
      async query(statement) { statements.push(statement); return [row()]; },
    });
    await expect(inspectApplicationAccountControl(source, "account:alice")).resolves.toEqual({
      admitted: true,
      account_epoch: 12,
      control_revision: 17,
      destination_activation_revision: 17,
    });
    expect(statements).toEqual([{
      name: "application_control.load_current",
      text: LOAD_APPLICATION_ACCOUNT_CONTROL,
      values: ["account:alice"],
    }]);
  });

  test("absence, source failure, malformed rows, and owner substitution fail closed", async () => {
    for (const result of [
      [],
      [row({ account_id: "account:bob" })],
      [row({ control_revision: "017" })],
      [row({ conflict_reason: "provider raw text", conflict_at_revision: "17" })],
      [row(), row()],
      new Proxy([row()], {}),
    ]) {
      const source = createPostgresApplicationAccountControlSource({ query: async () => result });
      const inspected = await inspectApplicationAccountControl(source, "account:alice");
      expect(inspected.admitted).toBe(false);
    }
    const unavailable = createPostgresApplicationAccountControlSource({
      query: async () => { throw new Error("database secret"); },
    });
    await expect(unavailable.load("account:alice")).resolves.toEqual({ status: "unavailable" });
    await expect(unavailable.load("bad account\nraw")).resolves.toEqual({ status: "unavailable" });
  });

  test("valid closed conflict and lifecycle states remain structurally representable", async () => {
    const conflicted = createPostgresApplicationAccountControlSource({
      query: async () => [row({
        conflict_reason: "conflicting_observation",
        conflict_at_revision: "17",
      })],
    });
    await expect(inspectApplicationAccountControl(conflicted, "account:alice"))
      .resolves.toEqual({ admitted: false, reason: "control_state_conflicting" });

    const deleted = createPostgresApplicationAccountControlSource({
      query: async () => [row({
        lifecycle_state: "deleted", deletion_epoch: "12",
      })],
    });
    await expect(inspectApplicationAccountControl(deleted, "account:alice"))
      .resolves.toEqual({ admitted: false, reason: "account_lifecycle_not_active" });
  });

  test("construction snapshots the only callable and rejects hostile ports", async () => {
    const port = { query: async () => [row()] };
    const source = createPostgresApplicationAccountControlSource(port);
    port.query = async () => { throw new Error("mutated"); };
    await expect(source.load("account:alice")).resolves.toMatchObject({ status: "current" });
    expect(() => createPostgresApplicationAccountControlSource(new Proxy(port, {})))
      .toThrow("invalid PostgreSQL account control query port");
  });
});
