import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import {
  createInMemoryLocalServiceStores,
  createLocalDevService,
} from "../app-facing";

const ACCOUNT_ID = "account-lifecycle-auth-fixture";

type LifecycleState = "active" | "deletion_pending" | "deleted";

const boot = (state: LifecycleState) => {
  const base = createInMemoryLocalServiceStores();
  base.settings.putIdentity(ACCOUNT_ID, {
    displayName: "Lifecycle fixture",
    email: "lifecycle@example.invalid",
  });
  base.accountLifecycle.setLifecycle(ACCOUNT_ID, state);
  const service = createLocalDevService({
    db: new Database(":memory:"),
    ownerAccountId: ACCOUNT_ID,
    memoryCount: 1,
    accountTimezone: "UTC",
    devSecretLabel: `account-lifecycle-${state}`,
    stores: base,
  });
  return { service, stores: base, authorization: `Bearer ${service.devToken}` };
};

const appFacingRequests = (authorization: string): ReadonlyArray<{
  readonly name: string;
  readonly path: string;
  readonly init?: RequestInit;
}> => {
  const auth = { authorization };
  const jsonAuth = { ...auth, "content-type": "application/json" };
  return [
    { name: "memories", path: "/v1/memories", init: { headers: auth } },
    { name: "memories alias", path: "/v1/memories/recall", init: { headers: auth } },
    { name: "conversations list", path: "/v1/conversations", init: { headers: auth } },
    {
      name: "conversation patch",
      path: "/v1/conversations/missing/title?title=updated",
      init: { method: "PATCH", headers: auth },
    },
    {
      name: "conversation delete",
      path: "/v1/conversations/missing?cascade=false",
      init: { method: "DELETE", headers: auth },
    },
    { name: "folders list", path: "/v1/folders", init: { headers: auth } },
    {
      name: "folder create",
      path: "/v1/folders",
      init: { method: "POST", headers: jsonAuth, body: JSON.stringify({ name: "Folder" }) },
    },
    {
      name: "folder patch",
      path: "/v1/folders/missing",
      init: { method: "PATCH", headers: jsonAuth, body: "{}" },
    },
    {
      name: "folder delete",
      path: "/v1/folders/missing",
      init: { method: "DELETE", headers: auth },
    },
    { name: "tasks read", path: "/v1/tasks", init: { headers: auth } },
    {
      name: "tasks write",
      path: "/v1/tasks/ops",
      init: {
        method: "POST",
        headers: jsonAuth,
        body: JSON.stringify({
          write_id: "a".repeat(64),
          account_epoch: 1,
          domain: "tasks",
          op: { op: "create", record_id: "lifecycle-task", content: {} },
        }),
      },
    },
    { name: "settings", path: "/v1/settings", init: { headers: auth } },
    { name: "QA reset", path: "/v1/qa/reset", init: { method: "POST", headers: auth } },
    {
      name: "QA control reset",
      path: "/v1/qa/control/reset",
      init: { method: "POST", headers: jsonAuth, body: "{}" },
    },
    {
      name: "QA control observe",
      path: "/v1/qa/control/observe",
      init: { method: "POST", headers: jsonAuth, body: "{}" },
    },
    {
      name: "QA control activate",
      path: "/v1/qa/control/activate",
      init: { method: "POST", headers: jsonAuth, body: "{}" },
    },
    {
      name: "QA control deactivate",
      path: "/v1/qa/control/deactivate",
      init: { method: "POST", headers: jsonAuth, body: "{}" },
    },
    { name: "QA control tasks", path: "/v1/qa/control/tasks", init: { headers: auth } },
    {
      name: "current session",
      path: "/v1/session/current",
      init: { method: "DELETE", headers: auth },
    },
  ];
};

describe("account lifecycle is part of authentication", () => {
  test("local QA composition explicitly seeds only its configured owner and reseeds it", () => {
    const seeded = boot("active");
    expect(seeded.stores.accountLifecycle.readLifecycle(ACCOUNT_ID)).toBe("active");
    seeded.stores.accountLifecycle.setLifecycle("unrelated-account", "deleted");

    seeded.service.reseed();
    expect(seeded.stores.accountLifecycle.readLifecycle(ACCOUNT_ID)).toBe("active");
    expect(seeded.stores.accountLifecycle.readLifecycle("unrelated-account")).toBeNull();
  });

  for (const state of ["deletion_pending", "deleted"] as const) {
    test(`a valid token for an account that is ${state} gets 401 on every authenticated route`, async () => {
      const { service, authorization } = boot(state);
      const observed: Array<{ readonly name: string; readonly status: number }> = [];
      for (const request of appFacingRequests(authorization)) {
        const response = await service.app.request(request.path, request.init);
        observed.push({ name: request.name, status: response.status });
      }

      expect(observed).toEqual(observed.map(({ name }) => ({ name, status: 401 })));
    });
  }

  test("missing lifecycle state is byte-indistinguishable from deleted and reaches no route", async () => {
    const missing = boot("active");
    missing.stores.accountLifecycle.reset();
    const deleted = boot("deleted");

    const observe = async (candidate: ReturnType<typeof boot>) => {
      const responses: Array<{
        readonly name: string;
        readonly status: number;
        readonly body: string;
      }> = [];
      for (const request of appFacingRequests(candidate.authorization)) {
        const response = await candidate.service.app.request(request.path, request.init);
        responses.push({
          name: request.name,
          status: response.status,
          body: await response.text(),
        });
      }
      return responses;
    };

    const missingResponses = await observe(missing);
    const deletedResponses = await observe(deleted);
    expect(missingResponses).toEqual(deletedResponses);
    expect(missingResponses.every((response) => response.status === 401)).toBe(true);
    expect(JSON.stringify(missingResponses)).not.toContain(ACCOUNT_ID);
    expect(JSON.stringify(missingResponses)).not.toContain("lifecycle");
    expect(missing.stores.folders.listFolders(ACCOUNT_ID)).toEqual([]);
    expect(missing.stores.tasks.listRecords(ACCOUNT_ID)).toEqual([]);
  });
});
