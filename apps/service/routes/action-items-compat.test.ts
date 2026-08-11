// domain-pending(DIV-DOMTASK-001)
import { createHash } from "node:crypto";
import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import { parseTaskPageJson } from "@omi-core/ratified-contracts/projections/tasks";

import {
  createInMemoryLocalServiceStores,
  createLocalDevService,
  type LocalService,
} from "../app-facing";
import { createSqliteLocalServiceStores } from "../../../drivers/sqlite/service-stores";

const OWNER = "compatibility-owner";
const OTHER = "compatibility-other";
const PATH = "/v1/action-items";
const NOW = 1_786_406_400_123;
const PATCH_NOW = NOW + 60_000;
const RUN = "action-items-compat-run";

const canonicalBag = (
  description: string,
  overrides: Readonly<Record<string, unknown>> = {},
): Readonly<Record<string, unknown>> => Object.freeze({
  description,
  completed: false,
  completedAt: null,
  dueAt: null,
  owner: "user",
  source: "manual",
  provenance: Object.freeze([]),
  sortOrder: 0,
  indentLevel: 0,
  createdAt: NOW,
  updatedAt: NOW,
  ...overrides,
});

const boot = (options: {
  readonly stores?: ReturnType<typeof createInMemoryLocalServiceStores>;
  readonly now?: () => number;
  readonly ids?: readonly string[];
  readonly db?: Database;
} = {}): LocalService => {
  let nextId = 0;
  return createLocalDevService({
    db: options.db ?? new Database(":memory:"),
    ownerAccountId: OWNER,
    memoryCount: 1,
    accountTimezone: "UTC",
    devSecretLabel: "action-items-compatibility-test",
    ...(options.stores === undefined ? {} : { stores: options.stores }),
    nowEpochMilliseconds: options.now ?? (() => NOW),
    actionItemId: () => options.ids?.[nextId++] ?? `compat-created-${String(nextId).padStart(3, "0")}`,
  });
};

const auth = (service: LocalService, extra: Record<string, string> = {}): Record<string, string> => ({
  authorization: `Bearer ${service.devToken}`,
  ...extra,
});

const request = (
  service: LocalService,
  path: string,
  method = "GET",
  body?: unknown,
  extraHeaders: Record<string, string> = {},
): Promise<Response> => Promise.resolve(service.app.request(path, {
  method,
  headers: auth(service, {
    ...(body === undefined ? {} : { "content-type": "application/json" }),
    ...extraHeaders,
  }),
  ...(body === undefined ? {} : { body: typeof body === "string" ? body : JSON.stringify(body) }),
}));

const json = async (response: Response): Promise<Record<string, unknown>> =>
  await response.json() as Record<string, unknown>;

const legacyDigest = (accountId: string, description: string): string =>
  createHash("sha256")
    .update(`${accountId.length}:${accountId}:${description.trim().toLowerCase()}`, "utf8")
    .digest("hex");

const evidenceCount = (service: LocalService): number =>
  service.evidence.snapshot(RUN).rows.find((row) =>
    row.shell === "macos" && row.domain === "tasks")!.http!.successful;

const evidenceHeaders = Object.freeze({ "x-omi-client-id": `${RUN}::macos` });

const cutOver = async (service: LocalService): Promise<void> => {
  const observe = async (body: Readonly<Record<string, unknown>>): Promise<void> => {
    const response = await request(service, "/v1/qa/control/observe", "POST", body);
    expect(response.status).toBe(200);
  };
  await observe({
    control_revision: 1,
    account_generation: "legacy",
    account_epoch: null,
    lifecycle_state: "active",
    deletion_epoch: null,
  });
  await observe({
    control_revision: 2,
    account_generation: "migrating",
    account_epoch: null,
    lifecycle_state: "active",
    deletion_epoch: null,
  });
  await observe({
    control_revision: 3,
    account_generation: "new",
    account_epoch: 7,
    lifecycle_state: "active",
    deletion_epoch: null,
  });
  const activated = await request(service, "/v1/qa/control/activate", "POST", {
    epoch: 7,
    at_control_revision: 3,
  });
  expect(activated.status).toBe(200);
};

const platformPatch = async (
  service: LocalService,
  recordId: string,
  patch: Readonly<Record<string, unknown>>,
): Promise<Response> => request(service, "/v1/tasks/ops", "POST", {
  write_id: "a".repeat(64),
  account_epoch: 7,
  domain: "tasks",
  op: { op: "patch", record_id: recordId, patch },
});

describe("legacy action-items compatibility red-to-green proofs", () => {
  test("the real app factory serves all five adapter invocations", async () => {
    const service = boot({ ids: ["compat-created-red-green"] });
    service.writePath.tasks.apply(OWNER, {
      op: "create",
      record_id: "compat-existing-red-green",
      content: canonicalBag("existing"),
    });

    const statuses = [];
    statuses.push((await request(service, `${PATH}/ids`)).status);
    statuses.push((await request(service, `${PATH}?limit=50&offset=0`)).status);
    statuses.push((await request(service, PATH, "POST", { description: "created" })).status);
    statuses.push((await request(
      service,
      `${PATH}/compat-existing-red-green`,
      "PATCH",
      { description: "patched" },
    )).status);
    statuses.push((await request(service, `${PATH}/compat-existing-red-green`, "DELETE")).status);

    expect(statuses).toEqual([200, 200, 200, 200, 204]);
  });

  test("successful producer evidence moves only after an actual legacy Tasks response", async () => {
    const service = boot();
    expect(evidenceCount(service)).toBe(0);
    expect((await request(service, `${PATH}/ids`, "GET", undefined, evidenceHeaders)).status).toBe(200);
    expect(evidenceCount(service)).toBe(1);
  });

  test("a compatibility-created row is accepted by the vendored /v1/tasks parser", async () => {
    const service = boot({ ids: ["compat-cross-read"] });
    expect((await request(service, PATH, "POST", {
      description: "Created through compatibility",
      due_at: "2026-08-11T00:00:00.000Z",
      source: "assistant",
    })).status).toBe(200);

    const response = await request(service, "/v1/tasks");
    expect(response.status).toBe(200);
    const page = parseTaskPageJson(await response.text());
    expect(page).not.toBeNull();
    expect(page!.items).toHaveLength(1);
    expect(page!.items[0]).toMatchObject({
      description: "Created through compatibility",
      completed: false,
      completedAt: null,
      dueAt: Date.parse("2026-08-11T00:00:00.000Z"),
      owner: "user",
      source: "assistant",
      provenance: [],
      sortOrder: 0,
      indentLevel: 0,
      createdAt: NOW,
      updatedAt: NOW,
    });
    expect(Object.keys(page!.items[0]!)).toHaveLength(13);
  });
});

describe("legacy action-items exact wire and store semantics", () => {
  test("create, ids, pagination, patch and delete have the exact compatible shapes", async () => {
    let clockCalls = 0;
    const service = boot({
      ids: ["compat-exact-001", "compat-exact-002", "compat-exact-003"],
      now: () => {
        clockCalls += 1;
        return clockCalls === 1 ? NOW : PATCH_NOW;
      },
    });
    const createdResponse = await request(service, PATH, "POST", {
      description: "  SHIP It  ",
      due_at: "2026-08-11T03:04:05.678+02:30",
      source: "assistant",
    });
    expect(createdResponse.status).toBe(200);
    const created = await json(createdResponse);
    expect(created).toEqual({
      id: "compat-exact-001",
      description: "  SHIP It  ",
      completed: false,
      completed_at: null,
      due_at: "2026-08-11T00:34:05.678Z",
      owner: "user",
      source: "assistant",
      provenance: [],
      sort_order: 0,
      indent_level: 0,
      created_at: new Date(NOW).toISOString(),
      updated_at: new Date(NOW).toISOString(),
    });
    expect(clockCalls).toBe(1);

    for (const [description, id] of [["second", "compat-exact-002"], ["third", "compat-exact-003"]]) {
      expect((await request(service, PATH, "POST", { description })).status).toBe(200);
      expect(service.writePath.tasks.readRecord(OWNER, id)).not.toBeNull();
    }
    const ids = await request(service, `${PATH}/ids`);
    expect(ids.status).toBe(200);
    expect(await json(ids)).toEqual({
      ids: ["compat-exact-001", "compat-exact-002", "compat-exact-003"],
    });

    const firstPage = await request(service, `${PATH}?limit=2&offset=0`);
    expect(firstPage.status).toBe(200);
    const firstPageBody = await json(firstPage);
    expect(firstPageBody).toMatchObject({ has_more: true });
    expect(firstPageBody.action_items).toHaveLength(2);
    expect((firstPageBody.action_items as unknown[])[0]).toEqual(created);
    expect(((await request(service, `${PATH}?limit=2&offset=2`).then(json)).action_items as unknown[]))
      .toHaveLength(1);
    const defaults = await json(await request(service, PATH));
    expect(defaults.has_more).toBe(false);
    expect(defaults.action_items).toHaveLength(3);
    expect((await request(service, `${PATH}?limit=500`)).status).toBe(200);
    expect(((await request(service, `${PATH}?offset=2`).then(json)).action_items as unknown[]))
      .toHaveLength(1);

    const beforePatch = service.writePath.tasks.readRecord(OWNER, "compat-exact-001")!;
    const patchedResponse = await request(service, `${PATH}/compat-exact-001`, "PATCH", {
      description: "patched",
      completed: true,
      due_at: null,
      owner: "assistant",
      sort_order: 4,
      indent_level: 2,
    });
    expect(patchedResponse.status).toBe(200);
    const patched = await json(patchedResponse);
    expect(patched).toEqual({
      ...created,
      description: "patched",
      completed: true,
      completed_at: new Date(PATCH_NOW).toISOString(),
      due_at: null,
      owner: "assistant",
      sort_order: 4,
      indent_level: 2,
      updated_at: new Date(PATCH_NOW).toISOString(),
    });
    expect(clockCalls).toBe(4);
    const afterPatch = service.writePath.tasks.readRecord(OWNER, "compat-exact-001")!;
    expect(afterPatch.revision).not.toBe(beforePatch.revision);
    expect(afterPatch.content).toMatchObject({
      description: "patched",
      completed: true,
      completedAt: PATCH_NOW,
      dueAt: null,
      updatedAt: PATCH_NOW,
    });

    const reopenedResponse = await request(service, `${PATH}/compat-exact-001`, "PATCH", {
      completed: false,
    });
    expect(reopenedResponse.status).toBe(200);
    expect(await json(reopenedResponse)).toEqual({
      ...patched,
      completed: false,
      completed_at: null,
    });
    expect(clockCalls).toBe(5);
    const afterReopen = service.writePath.tasks.readRecord(OWNER, "compat-exact-001")!;
    expect(afterReopen.revision).not.toBe(afterPatch.revision);

    const deleted = await request(service, `${PATH}/compat-exact-001`, "DELETE");
    expect(deleted.status).toBe(204);
    expect(await deleted.text()).toBe("");
    expect(service.writePath.tasks.readRecord(OWNER, "compat-exact-001")).toBeNull();
    expect(await json(await request(service, `${PATH}/ids`))).toEqual({
      ids: ["compat-exact-002", "compat-exact-003"],
    });
    const recreated = service.writePath.tasks.apply(OWNER, {
      op: "create",
      record_id: "compat-exact-001",
      content: canonicalBag("recreated"),
    });
    expect(recreated.applied).toBeTrue();
    if (!recreated.applied) throw new Error("recreate unexpectedly conflicted");
    expect(recreated.revision).not.toBe(beforePatch.revision);
    expect(recreated.revision).not.toBe(afterPatch.revision);
    expect(recreated.revision).not.toBe(afterReopen.revision);
  });

  test("open retries reuse the historical digest, while completion permits a fresh id", async () => {
    let clockCalls = 0;
    const service = boot({
      ids: ["compat-idempotent-001", "compat-idempotent-002"],
      now: () => NOW + clockCalls++ * 1_000,
    });
    const first = await json(await request(service, PATH, "POST", {
      description: "  Mixed CASE task  ",
    }));
    const retry = await json(await request(service, PATH, "POST", {
      description: "mixed case task",
    }));
    expect(first.id).toBe("compat-idempotent-001");
    expect(retry.id).toBe(first.id);
    expect(service.writePath.tasks.listRecords(OWNER)).toHaveLength(1);
    expect(clockCalls).toBe(1);

    const stored = service.writePath.tasks.readRecord(OWNER, String(first.id))!;
    const privateKeys = Object.keys(stored.content).filter((key) => key.includes("legacy"));
    expect(privateKeys).toHaveLength(1);
    expect(stored.content[privateKeys[0]!]).toBe(legacyDigest(OWNER, "  Mixed CASE task  "));
    for (const value of [first, retry]) {
      expect(JSON.stringify(value)).not.toContain(privateKeys[0]!);
      expect(JSON.stringify(value)).not.toContain(String(stored.content[privateKeys[0]!]));
    }

    expect((await request(service, `${PATH}/${first.id}`, "PATCH", {
      description: "a changed description",
      completed: true,
    })).status).toBe(200);
    expect(service.writePath.tasks.readRecord(OWNER, String(first.id))!.content[privateKeys[0]!])
      .toBe(legacyDigest(OWNER, "  Mixed CASE task  "));

    const afterCompletion = await json(await request(service, PATH, "POST", {
      description: "MIXED CASE TASK",
    }));
    expect(afterCompletion.id).toBe("compat-idempotent-002");
    expect(afterCompletion.id).not.toBe(first.id);
    expect(service.writePath.tasks.listRecords(OWNER)).toHaveLength(2);
  });

  test("platform ops and the legacy route converge on the same internal record", async () => {
    const service = boot({ ids: ["compat-shared-authority"] });
    const created = await request(service, PATH, "POST", { description: "legacy value" });
    expect(created.status).toBe(200);
    await cutOver(service);
    const patched = await platformPatch(service, "compat-shared-authority", {
      description: "platform value",
      dueAt: Date.parse("2026-09-01T12:00:00.000Z"),
      updatedAt: PATCH_NOW,
    });
    expect(patched.status).toBe(200);
    const listed = await json(await request(service, `${PATH}?limit=50&offset=0`));
    expect(listed).toMatchObject({
      has_more: false,
      action_items: [{
        id: "compat-shared-authority",
        description: "platform value",
        due_at: "2026-09-01T12:00:00.000Z",
        updated_at: new Date(PATCH_NOW).toISOString(),
      }],
    });
  });
});

describe("legacy action-items hardening and account scoping", () => {
  test("authentication and lifecycle refusals cannot mutate", async () => {
    const service = boot();
    for (const init of [
      {},
      { headers: { authorization: "Bearer invalid" } },
      { headers: { authorization: service.devToken } },
    ]) {
      const response = await service.app.request(PATH, {
        method: "POST",
        ...init,
        body: JSON.stringify({ description: "must not exist" }),
      });
      expect(response.status).toBe(401);
    }
    expect(service.writePath.tasks.listRecords(OWNER)).toEqual([]);

    const stores = createInMemoryLocalServiceStores();
    stores.accountLifecycle.setLifecycle(OWNER, "deletion_pending");
    const revoked = boot({ stores });
    expect((await request(revoked, PATH, "POST", { description: "revoked" })).status).toBe(401);
    expect(stores.tasks.listRecords(OWNER)).toEqual([]);
  });

  test("malformed bodies, queries, account smuggling, unsafe ids and prototype keys never mutate", async () => {
    const service = boot({ ids: ["compat-hardening-seed"] });
    expect((await request(service, PATH, "POST", { description: "seed" })).status).toBe(200);
    const before = service.writePath.tasks.readRecord(OWNER, "compat-hardening-seed")!;

    const badPosts: readonly [string, unknown, Record<string, string>?][] = [
      [PATH, "{"],
      [PATH, null],
      [PATH, []],
      [PATH, {}],
      [PATH, { description: "" }],
      [PATH, { description: "x", due_at: "2026-02-30T00:00:00.000Z" }],
      [PATH, { description: "x", account_id: OTHER }],
      [`${PATH}?account_id=${OTHER}`, { description: "x" }],
      [PATH, `{"description":"x","__proto__":{"polluted":true}}`],
      [PATH, { description: "x", constructor: { prototype: { polluted: true } } }],
      [PATH, { description: "x" }, { "x-account-id": OTHER }],
      [PATH, { description: "x" }, { "content-type": "text/plain" }],
    ];
    for (const [path, body, headers] of badPosts) {
      const response = await request(service, path, "POST", body, headers);
      expect({ path, status: response.status }).toEqual({ path, status: 400 });
    }

    for (const path of [
      `${PATH}?limit=0`,
      `${PATH}?limit=501`,
      `${PATH}?offset=-1`,
      `${PATH}?limit=1&limit=2`,
      `${PATH}?offset=0&offset=1`,
      `${PATH}?accountId=${OTHER}`,
    ]) {
      expect((await request(service, path)).status).toBe(400);
    }
    for (const path of [
      `${PATH}/..%2Fescape`,
      `${PATH}/%00unsafe`,
      `${PATH}/${"x".repeat(129)}`,
    ]) {
      expect((await request(service, path, "PATCH", { description: "mutated" })).status).toBe(400);
      expect((await request(service, path, "DELETE")).status).toBe(400);
    }
    expect((await request(service, `${PATH}/compat-hardening-seed`, "DELETE", {})).status).toBe(400);

    expect(({} as Record<string, unknown>).polluted).toBeUndefined();
    expect(Object.getPrototypeOf(service.writePath.tasks.readRecord(OWNER, "compat-hardening-seed")!.content))
      .toBe(Object.prototype);
    expect(service.writePath.tasks.readRecord(OWNER, "compat-hardening-seed")).toEqual(before);
    expect(service.writePath.tasks.listRecords(OTHER)).toEqual([]);
  });

  test("missing ids are 404 and unsupported methods and frozen sibling paths keep the app not-found shape", async () => {
    const service = boot();
    expect((await request(service, `${PATH}/safe-missing-id`, "PATCH", { description: "x" })).status)
      .toBe(404);
    expect((await request(service, `${PATH}/safe-missing-id`, "DELETE")).status).toBe(404);

    for (const [path, method] of [
      [PATH, "PUT"],
      [`${PATH}/ids`, "POST"],
      [`${PATH}/safe-missing-id`, "GET"],
      [`${PATH}/search`, "POST"],
      [`${PATH}/batch`, "PATCH"],
      [`${PATH}/`, "GET"],
    ]) {
      const response = await request(service, path, method);
      expect(response.status).toBe(404);
      expect(await response.text()).toBe(JSON.stringify({ error: "not_found" }));
    }
    expect(service.writePath.tasks.listRecords(OWNER)).toEqual([]);
  });

  test("producer evidence counts every emitted success and no refusal or not-found intent", async () => {
    const service = boot({ ids: ["compat-evidence-id"] });
    const headers = evidenceHeaders as Record<string, string>;
    expect((await request(service, `${PATH}/ids`, "GET", undefined, headers)).status).toBe(200);
    expect((await request(service, `${PATH}?limit=50&offset=0`, "GET", undefined, headers)).status).toBe(200);
    expect((await request(service, PATH, "POST", { description: "evidence" }, headers)).status).toBe(200);
    expect((await request(service, `${PATH}/compat-evidence-id`, "PATCH", { completed: true }, headers)).status)
      .toBe(200);
    expect((await request(service, `${PATH}/compat-evidence-id`, "DELETE", undefined, headers)).status).toBe(204);
    expect(evidenceCount(service)).toBe(5);

    expect((await request(service, PATH, "POST", {}, headers)).status).toBe(400);
    expect((await request(service, `${PATH}/compat-evidence-id`, "DELETE", undefined, headers)).status).toBe(404);
    expect((await request(service, `${PATH}/search`, "POST", undefined, headers)).status).toBe(404);
    expect(evidenceCount(service)).toBe(5);
  });
});

describe("legacy action-items composition parity", () => {
  test("in-memory and SQLite compositions agree and QA reset clears their one Tasks authority", async () => {
    const inMemory = boot({ ids: ["compat-parity-id"] });
    const sqliteDb = new Database(":memory:");
    const sqlite = createLocalDevService({
      db: sqliteDb,
      ownerAccountId: OWNER,
      memoryCount: 1,
      accountTimezone: "UTC",
      devSecretLabel: "action-items-compatibility-test",
      stores: createSqliteLocalServiceStores(sqliteDb),
      nowEpochMilliseconds: () => NOW,
      actionItemId: () => "compat-parity-id",
    });

    const steps: readonly [string, string, unknown?][] = [
      [PATH, "POST", { description: "parity", due_at: "2026-08-12T10:00:00.000Z" }],
      [`${PATH}/ids`, "GET"],
      [`${PATH}?limit=1&offset=0`, "GET"],
      [`${PATH}/compat-parity-id`, "PATCH", { completed: true }],
      [`${PATH}/compat-parity-id`, "DELETE"],
    ];
    for (const [path, method, body] of steps) {
      const [memoryResponse, sqliteResponse] = await Promise.all([
        request(inMemory, path, method, body),
        request(sqlite, path, method, body),
      ]);
      expect(sqliteResponse.status).toBe(memoryResponse.status);
      expect(await sqliteResponse.text()).toBe(await memoryResponse.text());
    }

    expect((await request(inMemory, PATH, "POST", { description: "after delete" })).status).toBe(200);
    expect((await request(sqlite, PATH, "POST", { description: "after delete" })).status).toBe(200);
    for (const service of [inMemory, sqlite]) {
      expect(service.writePath.tasks.listRecords(OWNER)).toHaveLength(1);
      expect((await request(service, "/v1/qa/reset", "POST")).status).toBe(200);
      expect(service.writePath.tasks.listRecords(OWNER)).toEqual([]);
      expect(await json(await request(service, `${PATH}/ids`))).toEqual({ ids: [] });
    }
    sqliteDb.close();
  });
});
