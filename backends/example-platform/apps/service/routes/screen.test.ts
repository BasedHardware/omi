// domain-pending(DIV-DOMAPPS-007)
// domain-pending(UNK-DOMAPPS-001)

import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import {
  createInMemoryLocalServiceStores,
  createLocalDevService,
  type LocalService,
} from "../app-facing";
import { createUnconfiguredScreenEmbeddingSource } from "../screen/embedding-source";
import { QA_FIXTURE_TIME_ANCHOR_UTC } from "../qa/seed";
import {
  SCREEN_DAYS_PATH,
  SCREEN_FRAMES_PATH,
  SCREEN_RETENTION_PATH,
  SCREEN_RETIRED_PATH,
  SCREEN_SEARCH_PATH,
  SCREEN_TIMELINE_PATH,
} from "./screen";

const ACCOUNT = "screen-route-account";
const NOW = QA_FIXTURE_TIME_ANCHOR_UTC;
const OLD = "2026-07-20T12:00:00.000Z";

const boot = (): LocalService => {
  const stores = createInMemoryLocalServiceStores();
  stores.settings.putIdentity(ACCOUNT, {
    displayName: "Screen fixture",
    email: "screen@example.invalid",
  });
  stores.accountLifecycle.setLifecycle(ACCOUNT, "active");
  return createLocalDevService({
    db: new Database(":memory:"),
    ownerAccountId: ACCOUNT,
    memoryCount: 0,
    accountTimezone: "UTC",
    devSecretLabel: "screen-route-proof",
    stores,
    listenDefaultUnmetered: true,
    screenEmbeddings: createUnconfiguredScreenEmbeddingSource(),
    screenRetentionIntervalMs: 0,
  });
};

const auth = (service: LocalService): Record<string, string> => ({
  authorization: `Bearer ${service.devToken}`,
  "content-type": "application/json",
});

const frame = (id: string, capturedAt: string, text: string) => Object.freeze({
  id,
  captured_at: capturedAt,
  app_bundle_id: "com.example.browser",
  app_name: "Browser",
  window_title: `${text} window`,
  device_name: "Fixture Mac",
  client_device_id: "device-1",
  frame_ref: Object.freeze({ kind: "opaque" as const, ref: `ref-${id}` }),
  dhash: `dhash-${id}`,
  ocr: Object.freeze({
    full_text: text,
    blocks: Object.freeze([
      Object.freeze({
        id: "0",
        text,
        x: 0.1,
        y: 0.2,
        w: 0.4,
        h: 0.1,
        confidence: 0.95,
      }),
    ]),
  }),
});

const ingest = (
  service: LocalService,
  frames: readonly ReturnType<typeof frame>[],
  session = "session-http",
) => service.app.request(SCREEN_FRAMES_PATH, {
  method: "POST",
  headers: auth(service),
  body: JSON.stringify({ capture_session_id: session, frames }),
});

describe("screen routes", () => {
  test("unauthenticated requests are 401 on every screen path", async () => {
    const service = boot();
    for (const [path, method] of [
      [SCREEN_FRAMES_PATH, "POST"],
      [SCREEN_TIMELINE_PATH, "GET"],
      [SCREEN_DAYS_PATH, "GET"],
      [SCREEN_SEARCH_PATH, "GET"],
      [SCREEN_RETENTION_PATH, "GET"],
      [SCREEN_RETENTION_PATH, "PUT"],
      [SCREEN_RETIRED_PATH, "GET"],
    ] as const) {
      const response = await service.app.request(path, { method });
      expect(response.status).toBe(401);
      expect(await response.json()).toEqual({ error: "unauthorized" });
    }
  });

  test("HTTP proof: ingest → timeline → search snippet/blocks → retention sweep → day-span", async () => {
    const service = boot();
    const headers = auth(service);

    const ingested = await ingest(service, [
      frame("recent-harborline", NOW, "Harborline Cafe reservation"),
      frame("old-harborline", OLD, "Harborline Cafe last month"),
    ]);
    expect(ingested.status).toBe(201);
    expect(await ingested.json()).toEqual({
      capture_session_id: "session-http",
      accepted: 2,
      duplicate: 0,
      frames: [
        { id: "recent-harborline", inserted: true },
        { id: "old-harborline", inserted: true },
      ],
    });

    const timeline = await service.app.request(
      `${SCREEN_TIMELINE_PATH}?day=2026-08-07`,
      { headers },
    );
    expect(timeline.status).toBe(200);
    expect(await timeline.json()).toEqual({
      day: "2026-08-07",
      frames: [
        {
          id: "recent-harborline",
          capture_session_id: "session-http",
          captured_at: NOW,
          app_bundle_id: "com.example.browser",
          app_name: "Browser",
          window_title: "Harborline Cafe reservation window",
          device_name: "Fixture Mac",
          client_device_id: "device-1",
          frame_ref: { kind: "opaque", ref: "ref-recent-harborline" },
          dhash: "dhash-recent-harborline",
        },
      ],
    });

    const search = await service.app.request(
      `${SCREEN_SEARCH_PATH}?q=Harborline`,
      { headers },
    );
    expect(search.status).toBe(200);
    const searchBody = await search.json() as {
      readonly query: string;
      readonly hits: readonly {
        readonly frame_id: string;
        readonly snippet: string;
        readonly matched_block_ids: readonly string[];
      }[];
      readonly semantic: { readonly status: string };
    };
    expect(searchBody.query).toBe("Harborline");
    expect(searchBody.semantic).toEqual({ status: "not_configured" });
    expect(searchBody.hits.map((hit) => hit.frame_id).sort()).toEqual([
      "old-harborline",
      "recent-harborline",
    ]);
    const recentHit = searchBody.hits.find((hit) => hit.frame_id === "recent-harborline");
    expect(recentHit?.snippet).toContain("<<Harborline>>");
    expect(recentHit?.matched_block_ids).toEqual(["0"]);

    const retention = await service.app.request(SCREEN_RETENTION_PATH, {
      method: "PUT",
      headers,
      body: JSON.stringify({ days: 3 }),
    });
    expect(retention.status).toBe(200);
    expect(await retention.json()).toEqual({ days: 3 });

    const retired = await service.app.request(SCREEN_RETIRED_PATH, { headers });
    expect(retired.status).toBe(200);
    expect(await retired.json()).toEqual({
      retired: [
        {
          frame_id: "old-harborline",
          frame_ref: { kind: "opaque", ref: "ref-old-harborline" },
          retired_at: NOW,
        },
      ],
    });

    const days = await service.app.request(SCREEN_DAYS_PATH, { headers });
    expect(days.status).toBe(200);
    expect(await days.json()).toEqual({
      days: ["2026-08-07"],
      oldest_captured_at: NOW,
      newest_captured_at: NOW,
      frame_count: 1,
    });

    const oldDay = await service.app.request(
      `${SCREEN_TIMELINE_PATH}?day=2026-07-20`,
      { headers },
    );
    expect(await oldDay.json()).toEqual({ day: "2026-07-20", frames: [] });
  });

  test("invalid retention PUT fails safe to unlimited and does not delete", async () => {
    const service = boot();
    await ingest(service, [frame("keep-me", OLD, "old text")]);
    const written = await service.app.request(SCREEN_RETENTION_PATH, {
      method: "PUT",
      headers: auth(service),
      body: JSON.stringify({ days: -1 }),
    });
    expect(written.status).toBe(200);
    expect(await written.json()).toEqual({ days: 0 });
    const days = await service.app.request(SCREEN_DAYS_PATH, { headers: auth(service) });
    expect(await days.json()).toMatchObject({ frame_count: 1 });
    const read = await service.app.request(SCREEN_RETENTION_PATH, { headers: auth(service) });
    expect(await read.json()).toEqual({ days: 0 });
  });

  test("ingest validation refuses pixels and colliding ids", async () => {
    const service = boot();
    const pixels = await service.app.request(SCREEN_FRAMES_PATH, {
      method: "POST",
      headers: auth(service),
      body: JSON.stringify({
        capture_session_id: "session-http",
        frames: [{ ...frame("px", NOW, "text"), pixels: "AAAA" }],
      }),
    });
    expect(pixels.status).toBe(400);
    expect(await pixels.json()).toEqual({ error: "pixels_forbidden" });

    await ingest(service, [frame("dup", NOW, "original")]);
    const conflict = await ingest(service, [frame("dup", NOW, "changed")]);
    expect(conflict.status).toBe(409);
    expect(await conflict.json()).toEqual({ error: "conflict" });
  });

  test("default retention read is 7 before any write", async () => {
    const service = boot();
    const read = await service.app.request(SCREEN_RETENTION_PATH, { headers: auth(service) });
    expect(read.status).toBe(200);
    expect(await read.json()).toEqual({ days: 7 });
  });
});
