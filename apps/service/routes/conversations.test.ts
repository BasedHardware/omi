// domain-pending(DIV-DOMCORE-013)
// domain-pending(UNK-DOMCORE-002)
import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import {
  createInMemoryLocalServiceStores,
  createLocalService,
} from "../app-facing";
import type { ConversationRecord } from "../stores/conversations-store";

const OWNER = "acct-conversations-route";
const CREATED = "2026-08-03T12:00:00.000Z";
const MUTATED = "2026-08-07T12:00:00.000Z";

const row = (
  id: string,
  overrides: Partial<ConversationRecord> = {},
): ConversationRecord => ({
  id,
  structured: { title: `Title ${id}`, overview: `Overview ${id}` },
  created_at: CREATED,
  updated_at: CREATED,
  started_at: CREATED,
  finished_at: MUTATED,
  source: "omi",
  status: "completed",
  discarded: false,
  starred: false,
  visibility: "private",
  is_locked: false,
  folder_id: null,
  ...overrides,
});

const boot = () => {
  const db = new Database(":memory:");
  const stores = createInMemoryLocalServiceStores();
  stores.conversations.upsert(OWNER, row("conversation-a"));
  stores.conversations.upsert(OWNER, row("conversation-b"));
  const service = createLocalService({
    db,
    ownerAccountId: OWNER,
    memoryCount: 1,
    accountTimezone: "UTC",
    devSecretLabel: "conversation-route-test",
    stores,
  });
  const request = (path: string, init: RequestInit = {}) => service.app.request(path, {
    ...init,
    headers: {
      authorization: `Bearer ${service.devToken}`,
      ...(init.headers ?? {}),
    },
  });
  return { db, stores, service, request };
};

const body = async (response: Response): Promise<unknown> => response.json();

describe("GET /v1/conversations", () => {
  test("is registered in the default real composition with the prototype seed", async () => {
    const db = new Database(":memory:");
    const service = createLocalService({
      db,
      ownerAccountId: OWNER,
      memoryCount: 1,
      accountTimezone: "UTC",
      devSecretLabel: "conversation-default-composition-test",
    });
    try {
      const response = await service.app.request("/v1/conversations", {
        headers: { authorization: `Bearer ${service.devToken}` },
      });
      expect(response.status).toBe(200);
      expect(await body(response)).toEqual([{
        id: "quiet-chat-qa",
        structured: {
          title: "QA bridge check",
          overview: "A deterministic conversation for shell acceptance.",
        },
        created_at: CREATED,
        updated_at: MUTATED,
        started_at: "2026-08-07T11:50:00.000Z",
        finished_at: MUTATED,
        source: "omi",
        status: "completed",
        discarded: false,
        starred: false,
        visibility: "private",
        is_locked: false,
        folder_id: "work-folder-qa",
      }]);
    } finally {
      db.close();
    }
  });

  test("serves the decided record shape with prototype limit/offset parsing", async () => {
    const { db, request } = boot();
    try {
      const page = await request("/v1/conversations?limit=1junk&offset=1");
      expect(page.status).toBe(200);
      expect(await body(page)).toEqual([row("conversation-b")]);

      const fallback = await request("/v1/conversations?limit=-1&offset=invalid");
      expect(fallback.status).toBe(200);
      expect(await body(fallback)).toEqual([row("conversation-a"), row("conversation-b")]);
    } finally {
      db.close();
    }
  });

  test("requires the same bearer authorization as the prototype", async () => {
    const { db, service } = boot();
    try {
      const response = await service.app.request("/v1/conversations");
      expect(response.status).toBe(401);
      expect(await body(response)).toEqual({ error: "unauthorized" });
    } finally {
      db.close();
    }
  });
});

describe("conversation mutation conformance to qa-api-server/server.mjs:552-645", () => {
  test("pins every documented validation code plus unknown/nested path 404s", async () => {
    const { db, request } = boot();
    try {
      const cases: readonly {
        path: string;
        init: RequestInit;
        status: number;
        error: string;
      }[] = [
        {
          path: "/v1/conversations/conversation-a/title",
          init: { method: "PATCH" },
          status: 400,
          error: "title_required",
        },
        {
          path: "/v1/conversations/conversation-a/starred?starred=yes",
          init: { method: "PATCH" },
          status: 400,
          error: "starred_required",
        },
        {
          path: "/v1/conversations/conversation-a/visibility?value=friends",
          init: { method: "PATCH" },
          status: 400,
          error: "invalid_visibility",
        },
        {
          path: "/v1/conversations/conversation-a/folder",
          init: { method: "PATCH", body: "{" },
          status: 400,
          error: "invalid_json",
        },
        {
          path: "/v1/conversations/conversation-a/folder",
          init: { method: "PATCH", body: "{}" },
          status: 400,
          error: "folder_id_required",
        },
        {
          path: "/v1/conversations/conversation-a/folder",
          init: { method: "PATCH", body: JSON.stringify({ folder_id: 7 }) },
          status: 400,
          error: "folder_id_invalid",
        },
        {
          path: "/v1/conversations/conversation-a/folder",
          init: { method: "PATCH", body: JSON.stringify({ folder_id: "missing" }) },
          status: 404,
          error: "folder_not_found",
        },
        {
          path: "/v1/conversations/conversation-a/unknown",
          init: { method: "PATCH" },
          status: 404,
          error: "not_found",
        },
        {
          path: "/v1/conversations/conversation-a/title/nested",
          init: { method: "PATCH" },
          status: 404,
          error: "not_found",
        },
      ];

      for (const expected of cases) {
        const response = await request(expected.path, expected.init);
        expect(response.status, expected.path).toBe(expected.status);
        expect(await body(response), expected.path).toEqual({ error: expected.error });
      }
    } finally {
      db.close();
    }
  });

  test("preserves the prototype's null-body qa_server_error wart", async () => {
    const { db, request } = boot();
    try {
      const response = await request("/v1/conversations/conversation-a/folder", {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: "null",
      });
      expect(response.status).toBe(500);
      expect(await body(response)).toEqual({ error: "qa_server_error" });
    } finally {
      db.close();
    }
  });

  test("mutates named fields, bumps updated_at and state revision, and returns the row", async () => {
    const { db, stores, request } = boot();
    try {
      const title = await request("/v1/conversations/conversation-a/title?title=", {
        method: "PATCH",
      });
      expect(title.status).toBe(200);
      expect(await body(title)).toMatchObject({
        id: "conversation-a",
        structured: { title: "", overview: "Overview conversation-a" },
        updated_at: MUTATED,
      });

      const starred = await request(
        "/v1/conversations/conversation-a/starred?starred=true",
        { method: "PATCH" },
      );
      expect(starred.status).toBe(200);
      expect(await body(starred)).toMatchObject({ starred: true, updated_at: MUTATED });

      const visibility = await request(
        "/v1/conversations/conversation-a/visibility?value=shared",
        { method: "PATCH" },
      );
      expect(visibility.status).toBe(200);
      expect(await body(visibility)).toMatchObject({ visibility: "shared", updated_at: MUTATED });

      const folder = await request("/v1/conversations/conversation-a/folder", {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ folder_id: "work-folder-qa" }),
      });
      expect(folder.status).toBe(200);
      expect(await body(folder)).toMatchObject({
        folder_id: "work-folder-qa",
        updated_at: MUTATED,
      });
      expect(stores.conversations.readStateRevision(OWNER)).toBe(4);
    } finally {
      db.close();
    }
  });

  test("a missing folder returns 404 and a route read proves the row is unchanged", async () => {
    const { db, stores, request } = boot();
    try {
      const beforeResponse = await request("/v1/conversations");
      const before = (await body(beforeResponse) as ConversationRecord[])
        .find((record) => record.id === "conversation-a");

      const mutation = await request("/v1/conversations/conversation-a/folder", {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ folder_id: "does-not-exist" }),
      });
      expect(mutation.status).toBe(404);
      expect(await body(mutation)).toEqual({ error: "folder_not_found" });

      const afterResponse = await request("/v1/conversations");
      const after = (await body(afterResponse) as ConversationRecord[])
        .find((record) => record.id === "conversation-a");
      expect(after).toEqual(before);
      expect(stores.conversations.readStateRevision(OWNER)).toBe(0);
    } finally {
      db.close();
    }
  });

  test("delete requires cascade=false before it parses or removes the id", async () => {
    const { db, stores, request } = boot();
    try {
      const absent = await request("/v1/conversations/conversation-a", { method: "DELETE" });
      expect(absent.status).toBe(400);
      expect(await body(absent)).toEqual({ error: "cascade_required" });
      expect(stores.conversations.readRecord(OWNER, "conversation-a")).not.toBeNull();

      const wrong = await request(
        "/v1/conversations/conversation-a?cascade=true",
        { method: "DELETE" },
      );
      expect(wrong.status).toBe(400);
      expect(await body(wrong)).toEqual({ error: "cascade_required" });

      const removed = await request(
        "/v1/conversations/conversation-a?cascade=false",
        { method: "DELETE" },
      );
      expect(removed.status).toBe(204);
      expect(await removed.text()).toBe("");
      expect(stores.conversations.readRecord(OWNER, "conversation-a")).toBeNull();
      expect(stores.conversations.readStateRevision(OWNER)).toBe(1);
    } finally {
      db.close();
    }
  });
});
