import assert from "node:assert/strict";
import test from "node:test";

import {
  adjacentCaptureDay,
  followNewestCaptureDay,
  groupScreenSearchHits,
  highlightRectsFor,
  SCREEN_APP_BUCKET_COUNT,
  SCREEN_APP_HUE_CEILING,
  screenActivityBlocks,
  screenAdjacentAppIndex,
  screenAppColor,
  screenAppColorForBucket,
  screenAppColorHash,
  screenDaySpanKind,
  screenEmptyKind,
  screenPausedMessageKey,
  screenTrackTickFormat,
  screenTrackTickStepMs,
  screenTrackTicks,
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

test("day-picker span does not claim an empty day before refresh is ready", () => {
  assert.equal(
    screenDaySpanKind({
      phase: "initial-loading",
      oldestCapturedAt: null,
      newestCapturedAt: null,
    }),
    null,
  );
  assert.equal(
    screenDaySpanKind({
      phase: "refreshing",
      oldestCapturedAt: null,
      newestCapturedAt: null,
    }),
    null,
  );
  assert.equal(
    screenDaySpanKind({
      phase: "ready",
      oldestCapturedAt: null,
      newestCapturedAt: null,
    }),
    "day-empty",
  );
  assert.equal(
    screenDaySpanKind({
      phase: "initial-loading",
      oldestCapturedAt: "2026-08-04T11:58:00.000Z",
      newestCapturedAt: "2026-08-07T11:50:00.000Z",
    }),
    "range",
  );
  // red-proof: fall through to screen.emptyDayTitle whenever timestamps are
  // missing, including while the day list is still loading.
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

test("no app colour this palette can emit is off-brand, over the whole domain", () => {
  // The brand rule is checked over every bucket rather than over a sample of
  // app names, because the output domain is small enough that the complete
  // argument costs the same as the statistical one. INV-UI-1 forbids the
  // blue-through-magenta family; `SCREEN_APP_HUE_CEILING` is the wall, and the
  // topmost band stops two degrees inside it.
  let brightest = 0;
  for (let bucket = 0; bucket < SCREEN_APP_BUCKET_COUNT; bucket += 1) {
    const swatch = screenAppColorForBucket(bucket);
    assert.ok(
      swatch.hue >= 2 && swatch.hue < SCREEN_APP_HUE_CEILING,
      `bucket ${bucket} emitted hue ${swatch.hue}`,
    );
    // The muddy stretches the bands skip: yellow-olive, and the dirty
    // teal-cyan seam. A continuous sweep is a gradient, not a palette.
    assert.ok(
      !(swatch.hue > 36 && swatch.hue < 90) && !(swatch.hue > 170 && swatch.hue < 188),
      `bucket ${bucket} landed in a skipped stretch at hue ${swatch.hue}`,
    );
    assert.equal(swatch.saturation, 0.92);
    assert.match(swatch.css, /^rgb\(\d+, \d+, \d+\)$/);
    brightest = Math.max(brightest, swatch.brightness);
  }
  assert.equal(brightest, 1);
});

test("an app keeps its colour across launches, casing, and stray whitespace", () => {
  // Stability is the whole point: a day of capture reads as a shape only if
  // the blue stretch is the same app tomorrow. A per-process string hash draws
  // blue this morning and orange after a relaunch.
  assert.equal(screenAppColor("Safari").css, screenAppColor("Safari").css);
  assert.equal(screenAppColor("Google Chrome").css, screenAppColor(" google chrome ").css);
  assert.notEqual(screenAppColor("Safari").css, screenAppColor("Notes").css);
  // Pinned to this source, not to a runtime seed: FNV-1a over "safari".
  assert.equal(screenAppColorHash("safari"), 0xac2c745cee0d4e51n);
});

test("activity blocks tile a day and the last one is given its sampling interval", () => {
  const frames = [
    { captured_at: "2026-08-07T11:30:00.000Z", app_name: "Safari", app_bundle_id: "com.apple.Safari" },
    { captured_at: "2026-08-07T11:40:00.000Z", app_name: "Safari", app_bundle_id: "com.apple.Safari" },
    { captured_at: "2026-08-07T11:50:00.000Z", app_name: "Notes", app_bundle_id: "com.apple.Notes" },
  ];
  const blocks = screenActivityBlocks(frames);
  assert.equal(blocks.length, 2);
  assert.equal(blocks[0].app, "Safari");
  assert.equal(blocks[0].endedAt, Date.parse("2026-08-07T11:50:00.000Z"), "a run ends where the next app starts");
  assert.equal(blocks[1].endedAt, Date.parse("2026-08-07T12:00:00.000Z"), "the final frame stands for a span, not an instant");
  assert.equal(screenActivityBlocks([]).length, 0);
});

test("ticks land on wall-clock boundaries and thin out as the span grows", () => {
  const start = Date.parse("2026-08-07T11:07:00.000Z");
  const ticks = screenTrackTicks(start, start + 3_600_000);
  assert.ok(ticks.length > 0 && ticks.length <= 13);
  for (const tick of ticks) assert.equal(tick % screenTrackTickStepMs(3_600_000), 0);
  assert.equal(screenTrackTickStepMs(3_600_000), 300_000);
  assert.equal(screenTrackTickStepMs(24 * 3_600_000), 7_200_000);
  assert.deepEqual(screenTrackTickFormat(7_200_000), { hour: "numeric" });
  assert.deepEqual(screenTrackTickFormat(300_000), { hour: "numeric", minute: "2-digit" });
});

test("previous app skips the run you are in, and stops rather than wrapping", () => {
  const frames = ["A", "A", "B", "C", "C"].map((app, index) => ({
    captured_at: new Date(Date.UTC(2026, 7, 7, 11, index)).toISOString(),
    app_name: app,
    app_bundle_id: `com.example.${app}`,
  }));
  assert.equal(screenAdjacentAppIndex(frames, 4, "previous"), 2, "from mid-C, back to the start of B");
  assert.equal(screenAdjacentAppIndex(frames, 2, "previous"), 0, "from B, back to the start of A");
  assert.equal(screenAdjacentAppIndex(frames, 1, "previous"), null, "the first run has nothing before it");
  assert.equal(screenAdjacentAppIndex(frames, 0, "next"), 2);
  assert.equal(screenAdjacentAppIndex(frames, 3, "next"), null);
  assert.equal(screenAdjacentAppIndex([], 0, "next"), null);
});