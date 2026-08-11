// domain-pending(DIV-DOMTASK-001)
import { createHash } from "node:crypto";
import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import { parseTaskPageJson } from "@omi-core/ratified-contracts/projections/tasks";

import {
  createInMemoryLocalServiceStores,
  createLocalDevService,
  type LocalService,
  type LocalServiceStores,
} from "../app-facing";
import { createSqliteLocalServiceStores } from "../../../drivers/sqlite/service-stores";
import {
  actionItemsCompatCreateDigest,
  isActionItemsCompatInvocation,
} from "./action-items-compat";

const OWNER = "compatibility-owner";
const OTHER = "compatibility-other";
const PATH = "/v1/action-items";
const NOW = 1_786_406_400_123;
const PATCH_NOW = NOW + 60_000;
const RUN = "action-items-compat-run";
const BAD_REQUEST_WIRE = JSON.stringify({ error: "bad_request" });

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

const jsonResponseForTest = (value: unknown): Response => new Response(JSON.stringify(value), {
  status: 200,
  headers: { "content-type": "application/json" },
});

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
  baseRevision?: string,
): Promise<Response> => request(service, "/v1/tasks/ops", "POST", {
  write_id: "a".repeat(64),
  account_epoch: 7,
  domain: "tasks",
  op: {
    op: "patch",
    record_id: recordId,
    patch,
    ...(baseRevision === undefined ? {} : { base_revision: baseRevision }),
  },
});

type StoreComposition = "in-memory" | "sqlite";

const bootComposition = (
  composition: StoreComposition,
  options: {
    readonly owner?: string;
    readonly now?: () => number;
    readonly ids?: readonly string[];
  } = {},
): {
  readonly service: LocalService;
  readonly stores: LocalServiceStores;
  readonly close: () => void;
} => {
  const db = new Database(":memory:");
  const stores = composition === "sqlite"
    ? createSqliteLocalServiceStores(db)
    : createInMemoryLocalServiceStores();
  let nextId = 0;
  const service = createLocalDevService({
    db,
    ownerAccountId: options.owner ?? OWNER,
    memoryCount: 1,
    accountTimezone: "UTC",
    devSecretLabel: `action-items-compatibility-${composition}-proof`,
    stores,
    persistentQaStores: true,
    nowEpochMilliseconds: options.now ?? (() => NOW),
    actionItemId: () => options.ids?.[nextId++] ?? `compat-proof-${String(nextId).padStart(3, "0")}`,
  });
  return Object.freeze({ service, stores, close: () => db.close() });
};

const storeBytes = (stores: LocalServiceStores, owner = OWNER): string =>
  JSON.stringify(stores.tasks.listRecords(owner));

// Vendored equivalent of core/contracts/src/ids.ts `parseRecordId`: retain all
// three accepted branches so this proof exercises the real client boundary.
const vendoredCoreParseRecordId = (raw: string): string | null =>
  /^[a-z]{2,12}(?:-[a-z]{2,12}){2,4}$/.test(raw)
    || /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(raw)
    || /^[A-Za-z0-9_-]{4,128}$/.test(raw)
    ? raw
    : null;

const expectVendoredRecordIdBoundary = (recordId: string): void => {
  expect(vendoredCoreParseRecordId(recordId)).toBe(recordId);
};

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

    for (const [description, id] of [
      ["second", "compat-exact-002"],
      ["third", "compat-exact-003"],
    ] as const) {
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
    expect(firstPageBody["action_items"]).toHaveLength(2);
    expect((firstPageBody["action_items"] as unknown[])[0]).toEqual(created);
    expect(((await request(service, `${PATH}?limit=2&offset=2`).then(json))["action_items"] as unknown[]))
      .toHaveLength(1);
    const defaults = await json(await request(service, PATH));
    expect(defaults["has_more"]).toBe(false);
    expect(defaults["action_items"]).toHaveLength(3);
    expect((await request(service, `${PATH}?limit=500`)).status).toBe(200);
    expect(((await request(service, `${PATH}?offset=2`).then(json))["action_items"] as unknown[]))
      .toHaveLength(1);

    const beforePatch = service.writePath.tasks.readRecord(OWNER, "compat-exact-001")!;
    const patchedResponse = await request(service, `${PATH}/compat-exact-001`, "PATCH", {
      description: "patched",
      completed: true,
      due_at: null,
      owner: "other",
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
      owner: "other",
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
    expect(first["id"]).toBe("compat-idempotent-001");
    expect(retry["id"]).toBe(first["id"]);
    expect(service.writePath.tasks.listRecords(OWNER)).toHaveLength(1);
    expect(clockCalls).toBe(1);

    const stored = service.writePath.tasks.readRecord(OWNER, String(first["id"]))!;
    const privateKeys = Object.keys(stored.content).filter((key) => key.includes("legacy"));
    expect(privateKeys).toHaveLength(1);
    expect(stored.content[privateKeys[0]!]).toBe(legacyDigest(OWNER, "  Mixed CASE task  "));
    for (const value of [first, retry]) {
      expect(JSON.stringify(value)).not.toContain(privateKeys[0]!);
      expect(JSON.stringify(value)).not.toContain(String(stored.content[privateKeys[0]!]));
    }

    expect((await request(service, `${PATH}/${String(first["id"])}`, "PATCH", {
      description: "a changed description",
      completed: true,
    })).status).toBe(200);
    expect(service.writePath.tasks.readRecord(OWNER, String(first["id"]))!.content[privateKeys[0]!])
      .toBe(legacyDigest(OWNER, "  Mixed CASE task  "));

    const afterCompletion = await json(await request(service, PATH, "POST", {
      description: "MIXED CASE TASK",
    }));
    expect(afterCompletion["id"]).toBe("compat-idempotent-002");
    expect(afterCompletion["id"]).not.toBe(first["id"]);
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

    const unpolluted: Record<string, unknown> = {};
    expect(unpolluted["polluted"]).toBeUndefined();
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
    ] as const) {
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

describe("legacy action-items single-process race and store-seam proofs", () => {
  for (const composition of ["in-memory", "sqlite"] as const) {
    test(`${composition}: concurrent open-create retries serialize to one row and one clock sample`, async () => {
      let clockCalls = 0;
      const booted = bootComposition(composition, {
        ids: ["compat-concurrent-proof"],
        now: () => {
          clockCalls += 1;
          return NOW;
        },
      });
      try {
        const descriptions = [
          "  Concurrent CAFÉ Task  ",
          "concurrent café task",
          " CONCURRENT CAFÉ TASK ",
          "\tConcurrent Café Task\n",
          "concurrent CAFÉ task",
          "  CONCURRENT café TASK",
        ];
        const responses = await Promise.all(descriptions.map((description) =>
          request(booted.service, PATH, "POST", { description })));
        expect(responses.every((response) => response.status === 200)).toBeTrue();
        const legacyWires = await Promise.all(responses.map((response) => response.text()));
        const legacyRows = legacyWires.map((wire) => JSON.parse(wire) as Record<string, unknown>);
        const returnedIds = legacyRows.map((row) => String(row["id"]));
        expect(new Set(returnedIds)).toEqual(new Set(["compat-concurrent-proof"]));
        for (const id of returnedIds) expectVendoredRecordIdBoundary(id);

        const records = booted.stores.tasks.listRecords(OWNER);
        expect(records).toHaveLength(1);
        expect(clockCalls).toBe(1);
        const privateKey = Object.keys(records[0]!.content).find((key) => key.startsWith("__omi."));
        expect(privateKey).toBeDefined();
        const privateDigest = String(records[0]!.content[privateKey!]);
        for (const wire of legacyWires) {
          expect(wire).not.toContain(privateKey!);
          expect(wire).not.toContain(privateDigest);
        }

        const tasksResponse = await request(booted.service, "/v1/tasks");
        expect(tasksResponse.status).toBe(200);
        const tasksWire = await tasksResponse.text();
        expect(parseTaskPageJson(tasksWire)?.items).toHaveLength(1);
        expect(tasksWire).not.toContain(privateKey!);
        expect(tasksWire).not.toContain(privateDigest);
      } finally {
        booted.close();
      }
    });

    test(`${composition}: missing PATCH and DELETE preserve byte-identical store contents`, async () => {
      const booted = bootComposition(composition);
      try {
        booted.stores.tasks.apply(OWNER, {
          op: "create",
          record_id: "compat-preflight-control",
          content: canonicalBag("must remain byte-identical"),
        });
        const before = storeBytes(booted.stores);
        const [patched, deleted] = await Promise.all([
          request(booted.service, `${PATH}/compat-missing-proof`, "PATCH", { description: "must not upsert" }),
          request(booted.service, `${PATH}/compat-missing-proof`, "DELETE"),
        ]);
        expect([patched.status, deleted.status]).toEqual([404, 404]);
        expect(storeBytes(booted.stores)).toBe(before);
      } finally {
        booted.close();
      }
    });

    test(`${composition}: an injected collision cannot overwrite a live row`, async () => {
      const booted = bootComposition(composition, {
        ids: ["compat-collision-live", "compat-collision-new"],
      });
      try {
        booted.stores.tasks.apply(OWNER, {
          op: "create",
          record_id: "compat-collision-live",
          content: canonicalBag("original live row"),
        });
        const original = JSON.stringify(booted.stores.tasks.readRecord(OWNER, "compat-collision-live"));
        const response = await request(booted.service, PATH, "POST", { description: "new row" });
        expect(response.status).toBe(200);
        const created = await json(response);
        expect(created["id"]).toBe("compat-collision-new");
        expectVendoredRecordIdBoundary(String(created["id"]));
        expect(JSON.stringify(booted.stores.tasks.readRecord(OWNER, "compat-collision-live"))).toBe(original);
        expect(booted.stores.tasks.listRecords(OWNER)).toHaveLength(2);
      } finally {
        booted.close();
      }
    });

    test(`${composition}: invalid injected ids fail without mutation`, async () => {
      for (const injectedId of ["bad id", "abc", "../escape"]) {
        const booted = bootComposition(composition, { ids: [injectedId] });
        try {
          expect(vendoredCoreParseRecordId(injectedId)).toBeNull();
          const before = storeBytes(booted.stores);
          const response = await request(booted.service, PATH, "POST", {
            description: `invalid id ${injectedId}`,
          });
          expect(response.status).toBe(500);
          expect(storeBytes(booted.stores)).toBe(before);
        } finally {
          booted.close();
        }
      }
    });

    test(`${composition}: delete and recreate preserve revision continuity against a stale platform patch`, async () => {
      const booted = bootComposition(composition);
      try {
        const recordId = "compat-revision-continuity";
        const created = booted.stores.tasks.apply(OWNER, {
          op: "create",
          record_id: recordId,
          content: canonicalBag("first incarnation"),
        });
        expect(created.applied).toBeTrue();
        if (!created.applied) throw new Error("initial create unexpectedly conflicted");
        const staleRevision = created.revision;
        if (staleRevision === null) throw new Error("create returned a null revision");

        expect(booted.stores.tasks.apply(OWNER, { op: "delete", record_id: recordId }).applied).toBeTrue();
        const recreated = booted.stores.tasks.apply(OWNER, {
          op: "create",
          record_id: recordId,
          content: canonicalBag("second incarnation"),
        });
        expect(recreated.applied).toBeTrue();
        if (!recreated.applied) throw new Error("recreate unexpectedly conflicted");
        expect(recreated.revision).not.toBe(staleRevision);

        await cutOver(booted.service);
        const beforeConflict = storeBytes(booted.stores);
        const stale = await platformPatch(
          booted.service,
          recordId,
          { description: "must conflict" },
          staleRevision,
        );
        expect(stale.status).toBe(409);
        expect(await stale.text()).toBe(JSON.stringify({ error: "conflict" }));
        expect(storeBytes(booted.stores)).toBe(beforeConflict);
      } finally {
        booted.close();
      }
    });

    test(`${composition}: malformed platform task bags remain non-mutating without choosing projection policy`, async () => {
      const booted = bootComposition(composition);
      try {
        const malformedId = "compat-malformed-platform-bag";
        await cutOver(booted.service);
        const platformCreated = await request(booted.service, "/v1/tasks/ops", "POST", {
          write_id: "e".repeat(64),
          account_epoch: 7,
          domain: "tasks",
          op: {
            op: "create",
            record_id: malformedId,
            content: { description: "only one field is known" },
          },
        });
        expect(platformCreated.status).toBe(200);
        const before = storeBytes(booted.stores);
        const response = await request(booted.service, PATH);
        const responseWire = await response.text();
        // COULD NOT DETERMINE from settled records whether this family should
        // fail, skip, or repair. This proof only forbids fabricating this row.
        expect(responseWire).not.toContain(malformedId);
        expect(storeBytes(booted.stores)).toBe(before);
      } finally {
        booted.close();
      }
    });
  }

  test("the historical digest frames a colon account and non-ASCII description exactly", () => {
    const owner = "team:user";
    const description = "  CAFÉ DéJÀ VU  ";
    const expectedPayload = "9:team:user:café déjà vu";
    const expectedDigest = "6ed7a2fb56db5e04805be8c7d9f4ededf798345baae4238916461683986e0c1d";
    expect(owner.length).toBe(9);
    expect(`${owner.length}:${owner}:${description.trim().toLowerCase()}`).toBe(expectedPayload);
    expect(actionItemsCompatCreateDigest(owner, description)).toBe(expectedDigest);
  });
});

describe("legacy action-items historical request validation", () => {
  for (const composition of ["in-memory", "sqlite"] as const) {
    test(`${composition}: POST distinguishes omitted source from every invalid explicit value`, async () => {
      const booted = bootComposition(composition, {
        ids: ["compat-source-default", "compat-source-custom"],
      });
      try {
        const defaulted = await request(booted.service, PATH, "POST", { description: "default source" });
        expect(defaulted.status).toBe(200);
        expect((await json(defaulted))["source"]).toBe("manual");

        const customSource = "historical:custom-source";
        const custom = await request(booted.service, PATH, "POST", {
          description: "custom source",
          source: customSource,
        });
        expect(custom.status).toBe(200);
        expect((await json(custom))["source"]).toBe(customSource);

        for (const source of [null, "", "x".repeat(65), 7, false, [], {}]) {
          const before = storeBytes(booted.stores);
          const response = await request(booted.service, PATH, "POST", {
            description: `rejected source ${typeof source}`,
            source,
          });
          expect(response.status).toBe(400);
          expect(await response.text()).toBe(BAD_REQUEST_WIRE);
          expect(storeBytes(booted.stores)).toBe(before);
        }
      } finally {
        booted.close();
      }
    });

    test(`${composition}: PATCH enforces historical owner and safe-integer sort order`, async () => {
      const booted = bootComposition(composition);
      try {
        const recordId = "compat-historical-patch";
        booted.stores.tasks.apply(OWNER, {
          op: "create",
          record_id: recordId,
          content: canonicalBag("historical validation"),
        });

        for (const owner of ["user", "other", "unknown"]) {
          const response = await request(booted.service, `${PATH}/${recordId}`, "PATCH", { owner });
          expect(response.status).toBe(200);
          expect((await json(response))["owner"]).toBe(owner);
        }
        for (const sortOrder of [-17, 0, 23]) {
          const response = await request(booted.service, `${PATH}/${recordId}`, "PATCH", {
            sort_order: sortOrder,
          });
          expect(response.status).toBe(200);
          expect((await json(response))["sort_order"]).toBe(sortOrder);
        }

        for (const owner of [null, "assistant", "USER", 7, false, [], {}]) {
          const before = storeBytes(booted.stores);
          const response = await request(booted.service, `${PATH}/${recordId}`, "PATCH", { owner });
          expect(response.status).toBe(400);
          expect(await response.text()).toBe(BAD_REQUEST_WIRE);
          expect(storeBytes(booted.stores)).toBe(before);
        }

        const invalidSortBodies: readonly unknown[] = [
          { sort_order: 1.5 },
          { sort_order: Number.MAX_SAFE_INTEGER + 1 },
          "{\"sort_order\":1e309}",
          { sort_order: null },
          { sort_order: "1" },
          { sort_order: true },
          { sort_order: {} },
        ];
        for (const body of invalidSortBodies) {
          const before = storeBytes(booted.stores);
          const response = await request(booted.service, `${PATH}/${recordId}`, "PATCH", body);
          expect(response.status).toBe(400);
          expect(await response.text()).toBe(BAD_REQUEST_WIRE);
          expect(storeBytes(booted.stores)).toBe(before);
        }
      } finally {
        booted.close();
      }
    });

    test(`${composition}: create and patch round-trip historical aware years 0001 through 9999`, async () => {
      const booted = bootComposition(composition, { ids: ["compat-early-year"] });
      try {
        const created = await request(booted.service, PATH, "POST", {
          description: "early datetime",
          due_at: "0001-01-02T03:04:05Z",
        });
        expect(created.status).toBe(200);
        expect((await json(created))["due_at"]).toBe("0001-01-02T03:04:05.000Z");
        expect(booted.stores.tasks.readRecord(OWNER, "compat-early-year")?.content["dueAt"])
          .toBe(Date.parse("0001-01-02T03:04:05.000Z"));

        const year99 = await request(booted.service, `${PATH}/compat-early-year`, "PATCH", {
          due_at: "0099-06-07T08:09:10Z",
        });
        expect(year99.status).toBe(200);
        expect((await json(year99))["due_at"]).toBe("0099-06-07T08:09:10.000Z");

        const year999 = await request(booted.service, `${PATH}/compat-early-year`, "PATCH", {
          due_at: "0999-12-31T23:59:59.999+01:30",
        });
        expect(year999.status).toBe(200);
        expect((await json(year999))["due_at"]).toBe("0999-12-31T22:29:59.999Z");
        expect(booted.stores.tasks.readRecord(OWNER, "compat-early-year")?.content["dueAt"])
          .toBe(Date.parse("0999-12-31T22:29:59.999Z"));

        const year9999 = await request(booted.service, `${PATH}/compat-early-year`, "PATCH", {
          due_at: "9999-12-31T23:59:59.999Z",
        });
        expect(year9999.status).toBe(200);
        expect((await json(year9999))["due_at"]).toBe("9999-12-31T23:59:59.999Z");

        for (const dueAt of [
          "0000-01-01T00:00:00Z",
          "10000-01-01T00:00:00Z",
          "0099-01-01T00:00:00",
          "0099-01-01T00:00:00.0000Z",
          "0999-02-29T00:00:00Z",
          "0099-01-01T00:00:00+24:00",
          "0099-01-01T00:00:00z",
          "0099-01-01T00:00:00+0000",
        ]) {
          const before = storeBytes(booted.stores);
          const response = await request(booted.service, `${PATH}/compat-early-year`, "PATCH", {
            due_at: dueAt,
          });
          expect(response.status).toBe(400);
          expect(await response.text()).toBe(BAD_REQUEST_WIRE);
          expect(storeBytes(booted.stores)).toBe(before);
        }
      } finally {
        booted.close();
      }
    });
  }
});

describe("legacy action-items exact producer-evidence classification", () => {
  test("the classifier accepts only the five released route shapes", () => {
    for (const [method, path] of [
      ["GET", PATH],
      ["GET", `${PATH}/ids`],
      ["POST", PATH],
      ["PATCH", `${PATH}/compat-safe-id`],
      ["DELETE", `${PATH}/%63ompat-safe-id`],
    ] as const) {
      expect(isActionItemsCompatInvocation(method, path)).toBeTrue();
    }

    for (const [method, path] of [
      ["GET", `${PATH}/`],
      ["PATCH", `${PATH}/`],
      ["PATCH", `${PATH}/compat-safe-id/nested`],
      ["DELETE", `${PATH}/..%2Fescape`],
      ["PATCH", `${PATH}/bad%20id`],
      ["DELETE", `${PATH}/%`],
      ["PATCH", `${PATH}/abc`],
      ["PATCH", `${PATH}/${"x".repeat(129)}`],
      ["PATCH", `${PATH}/search`],
      ["DELETE", `${PATH}/batch`],
      ["PATCH", `${PATH}/ids`],
      ["PUT", PATH],
      ["GET", `${PATH}/compat-safe-id`],
      ["POST", `${PATH}/compat-safe-id`],
    ] as const) {
      expect(isActionItemsCompatInvocation(method, path)).toBeFalse();
    }
  });

  test("later successful sibling routes cannot move the compatibility evidence counter", async () => {
    const service = boot();
    service.app.patch(`${PATH}/search/future`, () => jsonResponseForTest({ ok: true }));
    service.app.delete(`${PATH}/batch/future`, () => jsonResponseForTest({ ok: true }));
    service.app.patch(`${PATH}/`, () => jsonResponseForTest({ ok: true }));
    const headers = evidenceHeaders as Record<string, string>;

    expect((await request(service, `${PATH}/ids`, "GET", undefined, headers)).status).toBe(200);
    expect(evidenceCount(service)).toBe(1);
    for (const [method, path] of [
      ["PATCH", `${PATH}/search/future`],
      ["DELETE", `${PATH}/batch/future`],
      ["PATCH", `${PATH}/`],
    ] as const) {
      expect((await request(service, path, method, undefined, headers)).status).toBe(200);
      expect(evidenceCount(service)).toBe(1);
    }
  });
});
