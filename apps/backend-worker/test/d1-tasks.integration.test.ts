import { createExecutionContext } from "cloudflare:test";
import { env } from "cloudflare:workers";
import { parseTaskPageJson } from "@omi-core/ratified-contracts/projections/tasks";
import { beforeEach, describe, expect, test } from "vitest";

import handler from "../src/index";

const taskSchema =
  "CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, account_id TEXT NOT NULL, description TEXT NOT NULL, completed INTEGER NOT NULL, completed_at INTEGER, due_at INTEGER, owner TEXT, source TEXT NOT NULL, provenance TEXT NOT NULL, sort_order REAL NOT NULL, indent_level INTEGER NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, revision TEXT)";

const seedTask = {
  id: "task:test-one",
  accountId: "test-account",
  description: "Ship the D1 tasks slice",
  completed: 0,
  completedAt: null,
  dueAt: null,
  owner: null,
  source: "assistant",
  provenance: JSON.stringify(["assistant: planner"]),
  sortOrder: 1,
  indentLevel: 0,
  createdAt: 1785900000,
  updatedAt: 1785900100,
  revision: null,
};

const authenticatedHeaders = {
  authorization: "Bearer test-token",
  "x-omi-client-id": "test-account",
};

beforeEach(async () => {
  await env.DB.exec(taskSchema);
  await env.DB.prepare("DELETE FROM tasks").run();
  await env.DB.prepare(
    "INSERT OR REPLACE INTO tasks (id, account_id, description, completed, completed_at, due_at, owner, source, provenance, sort_order, indent_level, created_at, updated_at, revision) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
  )
    .bind(
      seedTask.id,
      seedTask.accountId,
      seedTask.description,
      seedTask.completed,
      seedTask.completedAt,
      seedTask.dueAt,
      seedTask.owner,
      seedTask.source,
      seedTask.provenance,
      seedTask.sortOrder,
      seedTask.indentLevel,
      seedTask.createdAt,
      seedTask.updatedAt,
      seedTask.revision
    )
    .run();
});

describe("D1-authoritative tasks read", () => {
  test("reads only the authenticated account's seeded task through the worker route", async () => {
    await env.DB.prepare(
      "INSERT INTO tasks (id, account_id, description, completed, completed_at, due_at, owner, source, provenance, sort_order, indent_level, created_at, updated_at, revision) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
      .bind(
        "task:foreign",
        "other-account",
        "Foreign task must not cross the account boundary",
        0,
        null,
        null,
        null,
        "assistant",
        JSON.stringify(["assistant: planner"]),
        2,
        0,
        1785900000,
        1785900100,
        null
      )
      .run();

    const response = await handler.fetch(
      new Request("https://worker.test/v1/tasks?limit=10", {
        headers: authenticatedHeaders,
      }),
      {
        ...env,
        API_TOKEN: "test-token",
        AI: { run: async () => ({ response: "" }) },
      } as never,
      createExecutionContext()
    );

    expect(response.status).toBe(200);
    const text = await response.text();
    const page = parseTaskPageJson(text);
    expect(page).not.toBeNull();
    if (page === null) throw new Error("page was not parseable");
    expect(page.items).toHaveLength(1);
    expect(page.items[0]).toMatchObject({
      id: "task:test-one",
      description: "Ship the D1 tasks slice",
      completed: false,
      completedAt: null,
      dueAt: null,
      owner: null,
      source: "assistant",
      provenance: ["assistant: planner"],
      sortOrder: 1,
      indentLevel: 0,
      createdAt: 1785900000,
      updatedAt: 1785900100,
      revision: null,
    });
    expect(page.window).toEqual({
      status: "complete",
      complete: true,
      hasMore: false,
      nextCursor: null,
    });
    expect(page.completeness.status).toBe("complete");
    expect(page.absence).toBeNull();
  });

  test("unknown and foreign cursors are invalid instead of skipping later ids", async () => {
    await env.DB.prepare(
      "INSERT INTO tasks (id, account_id, description, completed, completed_at, due_at, owner, source, provenance, sort_order, indent_level, created_at, updated_at, revision) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
      .bind(
        "task:test-two",
        seedTask.accountId,
        "Second D1 task",
        0,
        null,
        null,
        null,
        "assistant",
        JSON.stringify(["assistant: planner"]),
        2,
        0,
        1785900200,
        1785900200,
        null
      )
      .run();
    await env.DB.prepare(
      "INSERT INTO tasks (id, account_id, description, completed, completed_at, due_at, owner, source, provenance, sort_order, indent_level, created_at, updated_at, revision) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
      .bind(
        "task:aaa-foreign",
        "other-account",
        "Foreign cursor must not page this account",
        0,
        null,
        null,
        null,
        "assistant",
        JSON.stringify(["assistant: planner"]),
        0,
        0,
        1785900000,
        1785900000,
        null
      )
      .run();

    const workerEnv = {
      ...env,
      API_TOKEN: "test-token",
      AI: { run: async () => ({ response: "" }) },
    } as never;
    const fetchTasks = (path: string) =>
      handler.fetch(
        new Request(`https://worker.test${path}`, {
          headers: authenticatedHeaders,
        }),
        workerEnv,
        createExecutionContext()
      );

    const first = await fetchTasks("/v1/tasks?limit=1");
    expect(first.status).toBe(200);
    const firstPage = parseTaskPageJson(await first.text());
    expect(firstPage).not.toBeNull();
    if (firstPage === null) throw new Error("first page was not parseable");
    expect(firstPage.items.map((item) => item.id)).toEqual(["task:test-one"]);
    expect(firstPage.window).toEqual({
      status: "more",
      complete: false,
      hasMore: true,
      nextCursor: "task:test-one",
    });

    const second = await fetchTasks(
      `/v1/tasks?limit=1&cursor=${encodeURIComponent("task:test-one")}`
    );
    expect(second.status).toBe(200);
    const secondPage = parseTaskPageJson(await second.text());
    expect(secondPage).not.toBeNull();
    if (secondPage === null) throw new Error("second page was not parseable");
    expect(secondPage.items.map((item) => item.id)).toEqual(["task:test-two"]);
    expect(secondPage.window).toEqual({
      status: "complete",
      complete: true,
      hasMore: false,
      nextCursor: null,
    });

    const afterLast = await fetchTasks(
      `/v1/tasks?limit=1&cursor=${encodeURIComponent("task:test-two")}`
    );
    expect(afterLast.status).toBe(200);
    const afterLastPage = parseTaskPageJson(await afterLast.text());
    expect(afterLastPage).not.toBeNull();
    if (afterLastPage === null)
      throw new Error("last-item page was not parseable");
    expect(afterLastPage.items).toEqual([]);
    expect(afterLastPage.window).toEqual({
      status: "complete",
      complete: true,
      hasMore: false,
      nextCursor: null,
    });
    expect(afterLastPage.absence).toEqual({ kind: "query_gap" });

    const unknown = await fetchTasks("/v1/tasks?cursor=task:missing");
    const foreign = await fetchTasks(
      `/v1/tasks?cursor=${encodeURIComponent("task:aaa-foreign")}`
    );
    const oversized = await fetchTasks(`/v1/tasks?cursor=${"x".repeat(1025)}`);
    expect(unknown.status).toBe(400);
    expect(foreign.status).toBe(400);
    expect(oversized.status).toBe(400);
    expect((await unknown.json()) as unknown).toEqual({
      error: { code: "bad_request", retryable: false, action: "edit_request" },
    });
    expect((await foreign.json()) as unknown).toEqual({
      error: { code: "bad_request", retryable: false, action: "edit_request" },
    });
    expect((await oversized.json()) as unknown).toEqual({
      error: { code: "bad_request", retryable: false, action: "edit_request" },
    });
  });

  test("omitted limit pages 25 tasks like production DEFAULT_PAGE_LIMIT", async () => {
    await env.DB.prepare("DELETE FROM tasks").run();
    const insert = env.DB.prepare(
      "INSERT INTO tasks (id, account_id, description, completed, completed_at, due_at, owner, source, provenance, sort_order, indent_level, created_at, updated_at, revision) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    );
    for (let index = 0; index < 26; index++) {
      const id = `task:${String(index).padStart(2, "0")}`;
      await insert
        .bind(
          id,
          seedTask.accountId,
          `Task ${index}`,
          0,
          null,
          null,
          null,
          "assistant",
          JSON.stringify(["assistant: planner"]),
          index,
          0,
          1785900000 + index,
          1785900000 + index,
          null
        )
        .run();
    }

    const response = await handler.fetch(
      new Request("https://worker.test/v1/tasks", {
        headers: authenticatedHeaders,
      }),
      {
        ...env,
        API_TOKEN: "test-token",
        AI: { run: async () => ({ response: "" }) },
      } as never,
      createExecutionContext()
    );

    expect(response.status).toBe(200);
    const page = parseTaskPageJson(await response.text());
    expect(page).not.toBeNull();
    if (page === null) throw new Error("page was not parseable");
    expect(page.items.map((item) => item.id)).toEqual(
      Array.from(
        { length: 25 },
        (_, index) => `task:${String(index).padStart(2, "0")}`
      )
    );
    expect(page.window).toEqual({
      status: "more",
      complete: false,
      hasMore: true,
      nextCursor: "task:24",
    });
  });
});
