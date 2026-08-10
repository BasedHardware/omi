import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import { createInMemoryLocalServiceStores, createLocalService } from "../app-facing";
import type { ConversationRecord } from "../stores/conversations-store";
import type { FolderRecord } from "../stores/folders-store";

const OWNER = "acct-folders-route";
const CREATED = "2026-08-03T12:00:00.000Z";
const MUTATED = "2026-08-07T12:00:00.000Z";

const folder = (id: string, overrides: Partial<FolderRecord> = {}): FolderRecord => ({
  id,
  name: id,
  description: null,
  color: "#6B7280",
  icon: "folder",
  created_at: CREATED,
  updated_at: MUTATED,
  order: 0,
  is_default: false,
  is_system: false,
  ...overrides,
});

const conversation = (folderId: string): ConversationRecord => ({
  id: "conversation-folder-route",
  structured: { title: "Folder route", overview: "Conversation reassignment proof." },
  created_at: CREATED,
  updated_at: MUTATED,
  started_at: CREATED,
  finished_at: MUTATED,
  source: "omi",
  status: "completed",
  discarded: false,
  starred: false,
  visibility: "private",
  is_locked: false,
  folder_id: folderId,
});

const boot = (injected = false) => {
  const db = new Database(":memory:");
  const stores = injected ? createInMemoryLocalServiceStores() : undefined;
  const service = createLocalService({
    db,
    ownerAccountId: OWNER,
    memoryCount: 1,
    accountTimezone: "UTC",
    devSecretLabel: "folder-route-test",
    ...(stores === undefined ? {} : { stores }),
  });
  const request = (path: string, init: RequestInit = {}) => service.app.request(path, {
    ...init,
    headers: {
      authorization: `Bearer ${service.devToken}`,
      ...(init.headers ?? {}),
    },
  });
  return { db, request, service, stores: service.writePath };
};

const body = async (response: Response): Promise<unknown> => response.json();
const json = (value: unknown): RequestInit => ({
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(value),
});

describe("GET /v1/folders", () => {
  test("returns the prototype's unpaginated bare seed array", async () => {
    const { db, request } = boot();
    try {
      const response = await request("/v1/folders?limit=1&offset=1");
      expect(response.status).toBe(200);
      expect(await body(response)).toEqual([
        folder("default-folder-qa", { name: "Other", is_default: true, is_system: true }),
        folder("work-folder-qa", {
          name: "Work",
          description: "QA work items",
          color: "#007AFF",
          icon: "briefcase",
          order: 1,
        }),
      ]);
    } finally {
      db.close();
    }
  });

  test("requires bearer authorization", async () => {
    const { db, service } = boot();
    try {
      const response = await service.app.request("/v1/folders");
      expect(response.status).toBe(401);
      expect(await body(response)).toEqual({ error: "unauthorized" });
    } finally {
      db.close();
    }
  });
});

describe("POST /v1/folders", () => {
  test("pins validation, null-body failure, defaults, id-only response, and order", async () => {
    const { db, request } = boot();
    try {
      const invalidJson = await request("/v1/folders", { method: "POST", body: "{" });
      expect(invalidJson.status).toBe(400);
      expect(await body(invalidJson)).toEqual({ error: "invalid_json" });

      const nullBody = await request("/v1/folders", json(null));
      expect(nullBody.status).toBe(500);
      expect(await body(nullBody)).toEqual({ error: "qa_server_error" });

      for (const value of [{}, { name: 7 }, { name: "   " }]) {
        const response = await request("/v1/folders", json(value));
        expect(response.status).toBe(400);
        expect(await body(response)).toEqual({ error: "name_required" });
      }

      const created = await request("/v1/folders", json({
        name: "  Preserved  ",
        description: 7,
        color: null,
        icon: false,
      }));
      expect(created.status).toBe(201);
      expect(await body(created)).toEqual({ id: "qa-folder-created-001" });

      const second = await request("/v1/folders", json({ name: "Second" }));
      expect(second.status).toBe(201);
      expect(await body(second)).toEqual({ id: "qa-folder-created-002" });

      const listed = await request("/v1/folders");
      expect(await body(listed)).toContainEqual(folder("qa-folder-created-001", {
        name: "  Preserved  ",
        created_at: MUTATED,
        order: 2,
      }));
      expect(await body(await request("/v1/folders"))).toContainEqual(
        folder("qa-folder-created-002", { name: "Second", created_at: MUTATED, order: 3 }),
      );
    } finally {
      db.close();
    }
  });
});

describe("PATCH /v1/folders/:id", () => {
  test("pins lookup order, JSON errors, null failure, five-key merge, and ignored keys", async () => {
    const { db, request } = boot();
    try {
      const missing = await request("/v1/folders/missing", { method: "PATCH", body: "{" });
      expect(missing.status).toBe(404);
      expect(await body(missing)).toEqual({ error: "not_found" });

      const invalidJson = await request("/v1/folders/work-folder-qa", {
        method: "PATCH",
        body: "{",
      });
      expect(invalidJson.status).toBe(400);
      expect(await body(invalidJson)).toEqual({ error: "invalid_json" });

      const nullBody = await request("/v1/folders/work-folder-qa", {
        ...json(null),
        method: "PATCH",
      });
      expect(nullBody.status).toBe(500);
      expect(await body(nullBody)).toEqual({ error: "qa_server_error" });

      const patched = await request("/v1/folders/work-folder-qa", {
        ...json({
          name: null,
          description: { nested: true },
          color: false,
          icon: ["array"],
          order: "last",
          is_system: true,
          updated_at: "hostile",
          extra: "ignored",
        }),
        method: "PATCH",
      });
      expect(patched.status).toBe(200);
      expect(await body(patched)).toEqual(folder("work-folder-qa", {
        name: null,
        description: { nested: true },
        color: false,
        icon: ["array"],
        order: "last",
      }));

      const empty = await request("/v1/folders/work-folder-qa", { ...json({}), method: "PATCH" });
      expect(empty.status).toBe(200);
      expect(await body(empty)).toEqual(await body(await request("/v1/folders")).then(
        (rows) => (rows as FolderRecord[]).find((row) => row.id === "work-folder-qa"),
      ));
    } finally {
      db.close();
    }
  });
});

describe("DELETE /v1/folders/:id", () => {
  test("pins system, self, empty, unknown, and explicit-target outcomes", async () => {
    const { db, request } = boot();
    try {
      const cases = [
        ["/v1/folders/missing", 404, "not_found"],
        ["/v1/folders/default-folder-qa?move_to_folder_id=default-folder-qa", 400, "system_folder"],
        ["/v1/folders/work-folder-qa?move_to_folder_id=work-folder-qa", 400, "self_move"],
        ["/v1/folders/work-folder-qa?move_to_folder_id=", 404, "target_not_found"],
        ["/v1/folders/work-folder-qa?move_to_folder_id=missing", 404, "target_not_found"],
      ] as const;
      for (const [path, status, error] of cases) {
        const response = await request(path, { method: "DELETE" });
        expect(response.status, path).toBe(status);
        expect(await body(response), path).toEqual({ error });
      }

      const removed = await request(
        "/v1/folders/work-folder-qa?move_to_folder_id=default-folder-qa",
        { method: "DELETE" },
      );
      expect(removed.status).toBe(204);
      expect(await removed.text()).toBe("");
      const conversations = await body(await request("/v1/conversations")) as ConversationRecord[];
      expect(conversations[0]?.folder_id).toBe("default-folder-qa");
    } finally {
      db.close();
    }
  });

  test("falls back to default, but preserves the prototype's dangling reference without one", async () => {
    const withDefault = boot(true);
    try {
      withDefault.stores.folders.upsert(OWNER, folder("default", { is_default: true }));
      withDefault.stores.folders.upsert(OWNER, folder("source", { order: 1 }));
      withDefault.stores.conversations.upsert(OWNER, conversation("source"));
      expect((await withDefault.request("/v1/folders/source", { method: "DELETE" })).status)
        .toBe(204);
      expect(withDefault.stores.conversations.readRecord(OWNER, "conversation-folder-route")?.folder_id)
        .toBe("default");
    } finally {
      withDefault.db.close();
    }

    const withoutDefault = boot(true);
    try {
      withoutDefault.stores.folders.upsert(OWNER, folder("source"));
      withoutDefault.stores.conversations.upsert(OWNER, conversation("source"));
      expect((await withoutDefault.request("/v1/folders/source", { method: "DELETE" })).status)
        .toBe(204);
      expect(withoutDefault.stores.folders.hasFolder(OWNER, "source")).toBe(false);
      expect(withoutDefault.stores.conversations.readRecord(
        OWNER,
        "conversation-folder-route",
      )?.folder_id).toBe("source");
    } finally {
      withoutDefault.db.close();
    }
  });

  test("decodes one id segment and rejects nested paths", async () => {
    const { db, request, stores } = boot(true);
    try {
      stores.folders.upsert(OWNER, folder("space folder"));
      expect((await request("/v1/folders/space%20folder", { method: "DELETE" })).status)
        .toBe(204);
      expect((await request("/v1/folders/a/b", { method: "DELETE" })).status).toBe(404);
    } finally {
      db.close();
    }
  });
});
