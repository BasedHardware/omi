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
  "x-omi-client-id": "test-client",
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
});
