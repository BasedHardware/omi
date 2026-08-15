// domain-pending(DIV-DOMCORE-013)
// domain-pending(UNK-DOMCORE-002)
import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import { parseConversationPageJson } from "@omi-core/ratified-contracts/projections/conversations";
import { parseFolderPageJson } from "@omi-core/ratified-contracts/projections/folders";

import {
  createLocalDevService,
} from "../app-facing";
import type { ConversationRecord } from "../stores/conversations-store";

const DEV_KEY_MATERIAL_LABEL = "omi-conversations-folders-conformance";
const OWNER_ACCOUNT_ID = "local-dev-user";
const CREATED = "2026-08-03T12:00:00.000Z";
const MUTATED = "2026-08-07T12:00:00.000Z";

const boot = () => {
  const db = new Database(":memory:");
  const service = createLocalDevService({
    db,
    ownerAccountId: OWNER_ACCOUNT_ID,
    memoryCount: 1,
    accountTimezone: "UTC",
    devSecretLabel: DEV_KEY_MATERIAL_LABEL,
  });
  const request = (path: string) => service.app.request(path, {
    headers: { authorization: `Bearer ${service.devToken}` },
  });
  return { db, service, request };
};

const flatten = (record: ConversationRecord) => Object.freeze({
  id: record.id,
  title: record.structured.title,
  overview: record.structured.overview,
  status: record.status,
  folderId: record.folder_id,
  starred: record.starred,
  visibility: record.visibility,
  discarded: record.discarded,
  isLocked: record.is_locked,
  source: record.source,
});

describe("ratified conversations and folders page wire conformance", () => {
  test("GET /v1/conversations envelope bytes pass parseConversationPageJson", async () => {
    const { db, request } = boot();
    try {
      const response = await request("/v1/conversations?limit=25");
      expect(response.status).toBe(200);
      expect(response.headers.get("content-type")).toBe("application/json");
      const raw = await response.text();
      const page = parseConversationPageJson(raw);
      expect(page).not.toBeNull();
      expect(page?.completeness.version).toBe("conversations-completeness-v1");
      expect(page?.completeness.status).toBe("complete");
      expect(page?.window.status).toBe("complete");
      expect(page?.items.some((item) => item.id === "quiet-chat-qa")).toBe(true);
    } finally {
      db.close();
    }
  });

  test("GET /v1/folders envelope bytes pass parseFolderPageJson", async () => {
    const { db, request } = boot();
    try {
      const response = await request("/v1/folders?limit=25");
      expect(response.status).toBe(200);
      expect(response.headers.get("content-type")).toBe("application/json");
      const raw = await response.text();
      const page = parseFolderPageJson(raw);
      expect(page).not.toBeNull();
      expect(page?.completeness.version).toBe("folders-completeness-v1");
      expect(page?.completeness.status).toBe("complete");
      expect(page?.window.status).toBe("complete");
      expect(page?.items.some((item) => item.id === "work-folder-qa")).toBe(true);
    } finally {
      db.close();
    }
  });
});

describe("platform vs legacy conversations read against the same origin", () => {
  test("envelope items match the offset-array records, including interrupted", async () => {
    const { db, service, request } = boot();
    try {
      expect(service.writePath.conversations.upsert(OWNER_ACCOUNT_ID, {
        id: "interrupted-chat-qa",
        structured: { title: "Interrupted", overview: "Stays visible" },
        created_at: CREATED,
        updated_at: MUTATED,
        started_at: "2026-08-07T11:50:00.000Z",
        finished_at: MUTATED,
        source: "omi",
        status: "interrupted",
        discarded: false,
        starred: false,
        visibility: "private",
        is_locked: false,
        folder_id: null,
      }).stored).toBe(true);

      const legacyResponse = await request("/v1/conversations?limit=500&offset=0");
      expect(legacyResponse.status).toBe(200);
      const legacy = await legacyResponse.json() as ConversationRecord[];
      expect(Array.isArray(legacy)).toBe(true);

      const platformResponse = await request("/v1/conversations?limit=100");
      expect(platformResponse.status).toBe(200);
      const page = parseConversationPageJson(await platformResponse.text());
      expect(page).not.toBeNull();
      if (page === null) throw new Error("platform page failed to parse");

      const legacyView = legacy.map(flatten).sort((a, b) => a.id.localeCompare(b.id));
      const platformView = page.items.map((item) => Object.freeze({
        id: item.id,
        title: item.title,
        overview: item.overview,
        status: item.status,
        folderId: item.folderId,
        starred: item.starred,
        visibility: item.visibility,
        discarded: item.discarded,
        isLocked: item.isLocked,
        source: item.source,
      })).sort((a, b) => a.id.localeCompare(b.id));

      expect(platformView).toEqual(legacyView);
      expect(legacyView.some((row) => row.id === "interrupted-chat-qa" && row.status === "interrupted"))
        .toBe(true);
      expect(legacyView.some((row) => row.id === "quiet-chat-qa")).toBe(true);
    } finally {
      db.close();
    }
  });
});
