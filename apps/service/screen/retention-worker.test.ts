// domain-pending(DIV-DOMAPPS-007)
// domain-pending(UNK-DOMAPPS-001)

import { describe, expect, test } from "bun:test";

import { createInMemoryScreenStore } from "../stores/screen-store";
import {
  SCREEN_RETENTION_INTERVAL_MS,
  createScreenRetentionWorker,
} from "./retention-worker";
import { createUnconfiguredScreenEmbeddingSource } from "./embedding-source";

const ACCOUNT = "worker-account";
const NOW = "2026-08-07T12:00:00.000Z";
const OLD = "2026-07-20T12:00:00.000Z";

const frame = (id: string, capturedAt: string) => Object.freeze({
  id,
  captured_at: capturedAt,
  app_bundle_id: "com.example.browser",
  app_name: "Browser",
  window_title: "window",
  device_name: "Fixture Mac",
  client_device_id: "device-1",
  frame_ref: Object.freeze({ kind: "opaque" as const, ref: id }),
  dhash: `dhash-${id}`,
  ocr: Object.freeze({
    full_text: "Harborline",
    blocks: Object.freeze([
      Object.freeze({
        id: "0",
        text: "Harborline",
        x: 0.1,
        y: 0.1,
        w: 0.4,
        h: 0.1,
        confidence: 0.9,
      }),
    ]),
  }),
});

test("worker sweeps at construction and on each scheduled tick", () => {
  const store = createInMemoryScreenStore();
  store.ingest({
    accountId: ACCOUNT,
    captureSessionId: "session",
    frames: [frame("old", OLD), frame("new", NOW)],
  });
  store.writeRetention(ACCOUNT, 3, "2026-07-21T12:00:00.000Z");
  expect(store.daySpan(ACCOUNT, "UTC").frame_count).toBe(2);

  const ticks: Array<() => void> = [];
  const worker = createScreenRetentionWorker({
    store,
    now: () => NOW,
    intervalMs: 1_000,
    schedule: (tick) => {
      ticks.push(tick);
      return {};
    },
    clear: () => {},
  });
  expect(store.listRetiredFrameRefs(ACCOUNT).map((row) => row.frame_id)).toEqual(["old"]);
  store.ingest({
    accountId: ACCOUNT,
    captureSessionId: "session",
    frames: [frame("older", "2026-06-01T12:00:00.000Z")],
  });
  expect(ticks).toHaveLength(1);
  ticks[0]?.();
  expect(store.listRetiredFrameRefs(ACCOUNT).map((row) => row.frame_id).sort())
    .toEqual(["old", "older"]);
  worker.stop();
});

test("parity interval is six hours and zero disables the timer", () => {
  expect(SCREEN_RETENTION_INTERVAL_MS).toBe(6 * 60 * 60 * 1000);
  const store = createInMemoryScreenStore();
  let scheduled = 0;
  createScreenRetentionWorker({
    store,
    now: () => NOW,
    intervalMs: 0,
    schedule: () => {
      scheduled += 1;
      return {};
    },
  });
  expect(scheduled).toBe(0);
});

test("unconfigured embedding source returns not_configured", async () => {
  const source = createUnconfiguredScreenEmbeddingSource();
  expect(await source.search({ accountId: ACCOUNT, query: "Harborline", limit: 10 }))
    .toEqual({ status: "not_configured" });
});
