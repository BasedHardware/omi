import assert from "node:assert/strict";
import test from "node:test";

import {
  adjacentCaptureDay,
  followNewestCaptureDay,
  groupScreenSearchHits,
  highlightRectsFor,
  screenEmptyKind,
  screenPausedMessageKey,
  snippetParts,
  storageSummaryLabel,
} from "../src/production/screen-presentation.ts";

test("empty kinds stay distinct for never-enabled, permission-denied, day-empty, and search-miss", () => {
  const base = {
    phase: "ready",
    permission: "granted",
    captureEverEnabled: true,
    historyFrameCount: 3,
    dayFrameCount: 2,
    searchQuery: "",
    searchHitCount: 0,
  };
  assert.equal(screenEmptyKind({ ...base, permission: "denied", captureEverEnabled: false, historyFrameCount: 0, dayFrameCount: 0 }), "permission-denied");
  assert.equal(screenEmptyKind({ ...base, captureEverEnabled: false, historyFrameCount: 0, dayFrameCount: 0 }), "never-enabled");
  assert.equal(screenEmptyKind({ ...base, dayFrameCount: 0 }), "day-empty");
  assert.equal(screenEmptyKind({ ...base, searchQuery: "Harborline", searchHitCount: 0 }), "search-miss");
  assert.equal(screenEmptyKind({ ...base, phase: "initial-loading", dayFrameCount: 0 }), null);
  // red-proof: treating permission-denied as never-enabled, or a search miss as
  // a day with no captures, collapses two of these four assertions.
});

test("search hits group by app/window inside a 30s window", () => {
  const hit = (id, at, app, windowTitle) => ({
    frame_id: id,
    captured_at: at,
    app_bundle_id: app,
    app_name: app,
    window_title: windowTitle,
    snippet: "<<Harborline>>",
    matched_block_ids: ["0"],
    rank: 1,
  });
  const groups = groupScreenSearchHits([
    hit("a", "2026-08-07T11:30:00.000Z", "com.apple.Safari", "Cafe"),
    hit("b", "2026-08-07T11:30:20.000Z", "com.apple.Safari", "Cafe"),
    hit("c", "2026-08-07T11:31:00.000Z", "com.apple.Safari", "Cafe"),
    hit("d", "2026-08-07T11:30:10.000Z", "com.apple.Notes", "Packing"),
  ]);
  assert.equal(groups.length, 3);
  assert.equal(groups[0]?.hits.length, 2);
  assert.equal(groups[1]?.appBundleId, "com.apple.Notes");
  assert.equal(groups[2]?.hits[0]?.frame_id, "c");
});

test("highlight geometry is taken from matched OCR blocks, not guessed", () => {
  const rects = highlightRectsFor(
    [{ id: "0", text: "Harborline Cafe", x: 0.08, y: 0.12, w: 0.4, h: 0.08, confidence: 0.98 }],
    ["0"],
  );
  assert.deepEqual(rects, [{ id: "0", x: 0.08, y: 0.12, w: 0.4, h: 0.08 }]);
  assert.deepEqual(highlightRectsFor([{ id: "0", text: "x", x: 0.1, y: 0.1, w: 0.1, h: 0.1, confidence: 1 }], ["9"]), []);
  assert.deepEqual(snippetParts("<<Harborline>> Cafe"), [
    { text: "Harborline", matched: true },
    { text: " Cafe", matched: false },
  ]);
});

test("day jumps skip dates that hold no captures", () => {
  const days = ["2026-08-04", "2026-08-07"];
  assert.equal(adjacentCaptureDay(days, "2026-08-07", "older"), "2026-08-04");
  assert.equal(adjacentCaptureDay(days, "2026-08-06", "older"), "2026-08-04");
  assert.equal(adjacentCaptureDay(days, "2026-08-04", "newer"), "2026-08-07");
  assert.equal(adjacentCaptureDay(days, "2026-08-07", "oldest"), "2026-08-04");
  assert.equal(adjacentCaptureDay(days, "2026-08-07", "newer"), null);
});

test("storage card never invents a zero size when bytes were not readable", () => {
  assert.deepEqual(storageSummaryLabel({ frames: 3, bytesOnDisk: null }), { frames: 3, size: null });
  assert.deepEqual(storageSummaryLabel({ frames: 3, bytesOnDisk: 2_400_000_000 }), { frames: 3, size: "2.4 GB" });
});

test("live capture follows the newest day only when that is already the selected day", () => {
  assert.equal(
    followNewestCaptureDay({
      previousDays: ["2026-08-04", "2026-08-07"],
      selectedDay: "2026-08-07",
      nextDays: ["2026-08-04", "2026-08-07", "2026-08-16"],
    }),
    "2026-08-16",
  );
  assert.equal(
    followNewestCaptureDay({
      previousDays: ["2026-08-04", "2026-08-07"],
      selectedDay: "2026-08-04",
      nextDays: ["2026-08-04", "2026-08-07", "2026-08-16"],
    }),
    "2026-08-04",
  );
  assert.equal(
    followNewestCaptureDay({ previousDays: [], selectedDay: null, nextDays: ["2026-08-07"] }),
    "2026-08-07",
  );
  // red-proof: always jumping to newest steals a user who was reading an older day.
});

test("paused capture copy names excluded and idle instead of a generic pause", () => {
  assert.equal(screenPausedMessageKey("excluded"), "screen.capturePausedExcluded");
  assert.equal(screenPausedMessageKey("idle"), "screen.capturePausedIdle");
  assert.equal(screenPausedMessageKey("lock"), "screen.capturePaused");
  assert.equal(screenPausedMessageKey(null), "screen.capturePaused");
});
