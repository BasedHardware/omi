// domain-pending(DIV-DOMAPPS-007)
// domain-pending(UNK-DOMAPPS-001)

import { describe, expect, test } from "bun:test";

import {
  SCREEN_DEFAULT_RETENTION_DAYS,
  SCREEN_UNLIMITED_RETENTION_DAYS,
  createInMemoryScreenStore,
  parseScreenRetentionDays,
} from "./screen-store";

const ACCOUNT = "screen-store-account";
const OTHER = "other-screen-account";
const NOW = "2026-08-07T12:00:00.000Z";
const OLD = "2026-07-20T12:00:00.000Z";
const SESSION = "session-one";

const frame = (id: string, capturedAt: string, text: string, extras: {
  readonly blockText?: string;
  readonly appName?: string;
} = {}) => Object.freeze({
  id,
  captured_at: capturedAt,
  app_bundle_id: "com.example.browser",
  app_name: extras.appName ?? "Browser",
  window_title: `${text} window`,
  device_name: "Fixture Mac",
  client_device_id: "device-1",
  frame_ref: Object.freeze({ kind: "chunk" as const, path: `chunks/${id}.hevc`, offset: 0 }),
  dhash: `dhash-${id}`,
  ocr: Object.freeze({
    full_text: text,
    blocks: Object.freeze([
      Object.freeze({
        id: "0",
        text: extras.blockText ?? text,
        x: 0.1,
        y: 0.1,
        w: 0.5,
        h: 0.1,
        confidence: 0.9,
      }),
    ]),
  }),
});

describe("parseScreenRetentionDays", () => {
  test("allowed windows pass through; invalid fails safe to unlimited", () => {
    // red-proof: coerce negative to 7 (a deleting default) and the fail-safe assertion breaks
    expect(parseScreenRetentionDays(3)).toBe(3);
    expect(parseScreenRetentionDays(7)).toBe(7);
    expect(parseScreenRetentionDays(14)).toBe(14);
    expect(parseScreenRetentionDays(30)).toBe(30);
    expect(parseScreenRetentionDays(0)).toBe(SCREEN_UNLIMITED_RETENTION_DAYS);
    expect(parseScreenRetentionDays(-1)).toBe(SCREEN_UNLIMITED_RETENTION_DAYS);
    expect(parseScreenRetentionDays("nope")).toBe(SCREEN_UNLIMITED_RETENTION_DAYS);
    expect(parseScreenRetentionDays(undefined)).toBe(SCREEN_UNLIMITED_RETENTION_DAYS);
    expect(parseScreenRetentionDays(1.5)).toBe(SCREEN_UNLIMITED_RETENTION_DAYS);
  });
});

describe("in-memory screen store", () => {
  test("ingest is owner-scoped, idempotent, and conflicts on mutated ids", () => {
    const store = createInMemoryScreenStore();
    const first = store.ingest({
      accountId: ACCOUNT,
      captureSessionId: SESSION,
      frames: [frame("f1", NOW, "Harborline Cafe table")],
    });
    expect(first.accepted).toBe(1);
    expect(first.duplicate).toBe(0);
    const replay = store.ingest({
      accountId: ACCOUNT,
      captureSessionId: SESSION,
      frames: [frame("f1", NOW, "Harborline Cafe table")],
    });
    expect(replay.accepted).toBe(0);
    expect(replay.duplicate).toBe(1);
    expect(() => store.ingest({
      accountId: ACCOUNT,
      captureSessionId: SESSION,
      frames: [frame("f1", NOW, "different text")],
    })).toThrow("screen frame id conflict");
    store.ingest({
      accountId: OTHER,
      captureSessionId: SESSION,
      frames: [frame("f1", NOW, "other owner")],
    });
    expect(store.daySpan(ACCOUNT, "UTC").frame_count).toBe(1);
    expect(store.daySpan(OTHER, "UTC").frame_count).toBe(1);
  });

  test("timeline is ordered by captured_at and grouped on the account timezone day", () => {
    const store = createInMemoryScreenStore();
    store.ingest({
      accountId: ACCOUNT,
      captureSessionId: SESSION,
      frames: [
        frame("late", "2026-08-07T19:00:00.000Z", "later"),
        frame("early", "2026-08-07T11:00:00.000Z", "earlier"),
        frame("next-day", "2026-08-08T01:00:00.000Z", "tomorrow utc"),
      ],
    });
    const utc = store.listTimeline(ACCOUNT, "2026-08-07", "UTC");
    expect(utc.frames.map((row) => row.id)).toEqual(["early", "late"]);
    expect(utc.frames[0]?.app_name).toBe("Browser");
    const la = store.listTimeline(ACCOUNT, "2026-08-07", "America/Los_Angeles");
    expect(la.frames.map((row) => row.id)).toEqual(["early", "late", "next-day"]);
  });

  test("search ranks, snippets, and names matched block ids", () => {
    const store = createInMemoryScreenStore();
    store.ingest({
      accountId: ACCOUNT,
      captureSessionId: SESSION,
      frames: [
        frame("hit", NOW, "Harborline Cafe reservation", { blockText: "Harborline Cafe" }),
        frame("miss", NOW, "unrelated packing list"),
        frame("other", NOW, "Harborline twice Harborline Cafe"),
      ],
    });
    const page = store.searchText(ACCOUNT, "Harborline");
    expect(page.hits.map((hit) => hit.frame_id)).toEqual(["other", "hit"]);
    expect(page.hits[0]?.snippet).toContain("<<Harborline>>");
    expect(page.hits[0]?.matched_block_ids).toEqual(["0"]);
    expect(store.searchText(OTHER, "Harborline").hits).toEqual([]);
  });

  test("retention default is 7, 0 is unlimited, and invalid write never deletes", () => {
    const store = createInMemoryScreenStore();
    store.ingest({
      accountId: ACCOUNT,
      captureSessionId: SESSION,
      frames: [frame("old", OLD, "old Harborline"), frame("new", NOW, "new Harborline")],
    });
    expect(store.readRetention(ACCOUNT).days).toBe(SCREEN_DEFAULT_RETENTION_DAYS);
    store.writeRetention(ACCOUNT, -4, NOW);
    expect(store.readRetention(ACCOUNT).days).toBe(SCREEN_UNLIMITED_RETENTION_DAYS);
    expect(store.daySpan(ACCOUNT, "UTC").frame_count).toBe(2);
    store.writeRetention(ACCOUNT, 3, NOW);
    expect(store.listRetiredFrameRefs(ACCOUNT).map((row) => row.frame_id)).toEqual(["old"]);
    expect(store.listRetiredFrameRefs(ACCOUNT)[0]?.frame_ref).toEqual({
      kind: "chunk",
      path: "chunks/old.hevc",
      offset: 0,
    });
    expect(store.daySpan(ACCOUNT, "UTC")).toEqual({
      days: ["2026-08-07"],
      oldest_captured_at: NOW,
      newest_captured_at: NOW,
      frame_count: 1,
    });
    expect(store.searchText(ACCOUNT, "Harborline").hits.map((hit) => hit.frame_id)).toEqual(["new"]);
  });

  test("pixels on ingest are refused", () => {
    const store = createInMemoryScreenStore();
    expect(() => store.ingest({
      accountId: ACCOUNT,
      captureSessionId: SESSION,
      frames: [{ ...frame("px", NOW, "text"), pixels: "AAAA" } as never],
    })).toThrow("screen pixels must not cross the wire");
  });
});
