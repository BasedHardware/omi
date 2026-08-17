// domain-pending(DIV-DOMAPPS-007)
// domain-pending(UNK-DOMAPPS-001)

import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Database } from "bun:sqlite";
import { expect, test } from "bun:test";

import { createSqliteLocalServiceStores } from "./index";

const ACCOUNT = "sqlite-screen-account";
const NOW = "2026-08-07T12:00:00.000Z";
const OLD = "2026-07-20T12:00:00.000Z";

const frame = (id: string, capturedAt: string, text: string) => Object.freeze({
  id,
  captured_at: capturedAt,
  app_bundle_id: "com.example.browser",
  app_name: "Browser",
  window_title: `${text} window`,
  device_name: "Fixture Mac",
  client_device_id: "device-1",
  frame_ref: Object.freeze({ kind: "chunk" as const, path: `chunks/${id}.hevc`, offset: 40 }),
  dhash: `dhash-${id}`,
  ocr: Object.freeze({
    full_text: text,
    blocks: Object.freeze([
      Object.freeze({
        id: "0",
        text,
        x: 0.1,
        y: 0.1,
        w: 0.5,
        h: 0.12,
        confidence: 0.92,
      }),
    ]),
  }),
});

test("SQLite FTS ranks, snippets, and names matched block ids", () => {
  const db = new Database(":memory:");
  const stores = createSqliteLocalServiceStores(db);
  stores.screen.ingest({
    accountId: ACCOUNT,
    captureSessionId: "session-fts",
    frames: [
      frame("rare", NOW, "Harborline Cafe once"),
      frame("common", NOW, "Harborline Harborline Cafe reservation"),
      frame("miss", NOW, "Cedar Loop packing"),
    ],
  });
  const page = stores.screen.searchText(ACCOUNT, "Harborline");
  expect(page.hits.map((hit) => hit.frame_id)).toEqual(["common", "rare"]);
  expect(page.hits[0]?.snippet.toLowerCase()).toContain("harborline");
  expect(page.hits[0]?.snippet).toContain("<<");
  expect(page.hits[0]?.matched_block_ids).toEqual(["0"]);
  expect(page.hits[0]!.rank).toBeGreaterThan(page.hits[1]!.rank);
  db.close();
});

test("SQLite retention sweep retires frame_refs and survives reopen", () => {
  const directory = mkdtempSync(join(tmpdir(), "omi-screen-store-"));
  const path = join(directory, "service.sqlite");
  try {
    const firstDb = new Database(path, { create: true });
    const first = createSqliteLocalServiceStores(firstDb);
    first.screen.ingest({
      accountId: ACCOUNT,
      captureSessionId: "session-ret",
      frames: [frame("old", OLD, "old Harborline"), frame("new", NOW, "new Harborline")],
    });
    first.screen.writeRetention(ACCOUNT, 3, NOW);
    expect(first.screen.listRetiredFrameRefs(ACCOUNT).map((row) => row.frame_id)).toEqual(["old"]);
    expect(first.screen.daySpan(ACCOUNT, "UTC").frame_count).toBe(1);
    firstDb.close();

    const secondDb = new Database(path);
    const second = createSqliteLocalServiceStores(secondDb);
    expect(second.screen.searchText(ACCOUNT, "Harborline").hits.map((hit) => hit.frame_id))
      .toEqual(["new"]);
    expect(second.screen.listRetiredFrameRefs(ACCOUNT)[0]?.frame_ref).toEqual({
      kind: "chunk",
      path: "chunks/old.hevc",
      offset: 40,
    });
    expect(second.screen.readRetention(ACCOUNT).days).toBe(3);
    second.screen.writeRetention(ACCOUNT, "nope", NOW);
    expect(second.screen.readRetention(ACCOUNT).days).toBe(0);
    expect(second.screen.daySpan(ACCOUNT, "UTC").frame_count).toBe(1);
    secondDb.close();
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("SQLite FTS virtual table is created on the service-store migration path", () => {
  const db = new Database(":memory:");
  createSqliteLocalServiceStores(db);
  const row = db.query(`
    SELECT name FROM sqlite_master
    WHERE type = 'table' AND name = 'service_screen_ocr_fts'
  `).get() as { readonly name: string } | null;
  expect(row?.name).toBe("service_screen_ocr_fts");
  db.close();
});
