import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { EN_MESSAGES } from "@omi-core/i18n";
import {
  combineHomeRefreshStatuses,
  homeSurfacePresentation,
} from "../src/production/home-presentation.ts";
import { refreshPhaseNoticeKey } from "../src/production/lifecycle-presentation.ts";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

const refresh = (phase, hasSavedData) => ({ phase, hasSavedData });

function present(phase, hasSavedData, rowCount) {
  const status = refresh(phase, hasSavedData);
  return homeSurfacePresentation(status, rowCount, refreshPhaseNoticeKey(phase));
}

test("home search reads loaded projections without claiming backend completeness", async () => {
  const source = await read("src/production/HomeProduction.tsx");
  assert.match(source, /type SearchProjection<T>/);
  assert.match(source, /list\(\): Promise<T\[\]>/);
  assert.match(source, /status\(\): StoreStatus/);
  assert.match(source, /subscribe\(listener: \(\) => void\)/);
  assert.match(source, /Promise\.allSettled/);
  assert.match(source, /memorySource\.list\(\)/);
  assert.match(source, /conversationSource\.list\(\)/);
  assert.doesNotMatch(source, /taskSource|Task\b/);
  assert.doesNotMatch(source, /\brefresh\(|\bfetch\(|\bsearch\(|complete:\s*true|\bbackend\b/i);
  // red-proof: adding refresh/search/fetch or a completeness assertion makes
  // Home cease to be a filter over the already-loaded projections.
});

test("home search is a merged chronological spine, clearable, and keyboard focusable", async () => {
  const source = await read("src/production/HomeProduction.tsx");
  const styles = await read("src/production/home.css");
  assert.match(source, /autoFocus/);
  assert.match(source, /event\.metaKey \|\| event\.ctrlKey/);
  assert.match(source, /event\.key\.toLocaleLowerCase\(\) !== "k"/);
  assert.match(source, /searchRef\.current\?\.focus\(\)/);
  assert.match(source, /common\.clearSearch/);
  assert.match(source, /common\.noResults/);
  assert.match(source, /home-result-spine/);
  assert.match(source, /kind: "memory"/);
  assert.match(source, /kind: "conversation"/);
  assert.doesNotMatch(source, /kind: "task"/);
  assert.match(source, /sort\(\(left, right\) => right\.timestamp - left\.timestamp\)/);
  assert.match(source, /home-kind-filter/);
  assert.match(source, /\["all", "conversation", "memory"\]/);
  assert.match(source, /aria-disabled="true" disabled>\{t\(locale, "nav\.rewind"\)\}/);
  assert.match(source, /home\.loadedCount/);
  assert.match(source, /home\.matchCount/);
  assert.match(styles, /grid-template-rows:\s*auto 12px minmax\(0,1fr\)/);
  assert.match(styles, /height:\s*64px/);
  assert.doesNotMatch(styles, /@media\s*\(/);
  assert.doesNotMatch(styles, /#(?:[0-9a-f]{3,8})\b/i);
  // red-proof: removing the controlled clear path, Cmd-K focus, or a result
  // spine/filter fails this interaction-and-hierarchy guard.
});

test("home does not fabricate ask, chat, send, or mutation affordances", async () => {
  const source = await read("src/production/HomeProduction.tsx");
  assert.doesNotMatch(source, /store\.create|store\.patch|store\.delete|\b(?:ask|chat|send)\b/i);
  assert.match(source, /href=\{conversationHref\(row\.value\.id\)\}/);
  assert.doesNotMatch(source, /href=\{.*memory|href=\{.*task/i);
  // red-proof: adding an Ask button or clickable memory/task destination would
  // claim behavior the current loaded projections do not provide.
});

test("home renders each of the five refresh states distinguishably", async () => {
  const source = await read("src/production/HomeProduction.tsx");

  const phases = [
    "initial-loading",
    "refreshing",
    "ready",
    "saved-but-refresh-failed",
    "unavailable",
  ];
  const seen = new Map();
  for (const phase of phases) {
    const hasSavedData = phase === "saved-but-refresh-failed" || phase === "refreshing";
    const rowCount = phase === "saved-but-refresh-failed" ? 2 : phase === "unavailable" || phase === "initial-loading" ? 0 : phase === "ready" ? 0 : 1;
    const view = present(phase, hasSavedData, rowCount);
    const fingerprint = `${view.phase}|${view.noticeKey}|rows:${view.showsSavedRows}|fail:${view.showsFailureIndication}`;
    assert.equal(view.phase, phase);
    assert.ok(!seen.has(fingerprint), `phase ${phase} collides with ${seen.get(fingerprint)}`);
    seen.set(fingerprint, phase);
  }
  assert.equal(seen.size, 5);

  // saved-but-refresh-failed must keep saved rows and the failure indication together.
  const savedFailed = present("saved-but-refresh-failed", true, 3);
  assert.equal(savedFailed.noticeKey, "lifecycle.savedFailed");
  assert.equal(savedFailed.showsSavedRows, true);
  assert.equal(savedFailed.showsFailureIndication, true);
  assert.equal(EN_MESSAGES["lifecycle.savedFailed"], "Showing saved data. Couldn't refresh.");

  // Catalog keys already exist — inventing a new string fails i18n parity and this check.
  // Keys live in lifecycle-presentation.ts (shared).
  const lifecyclePresentation = await read("src/production/lifecycle-presentation.ts");
  for (const key of ["lifecycle.loading", "lifecycle.refreshing", "lifecycle.savedFailed", "lifecycle.unavailable"]) {
    assert.equal(typeof EN_MESSAGES[key], "string");
    assert.ok(EN_MESSAGES[key].length > 0);
    assert.match(lifecyclePresentation, new RegExp(`"${key}"`));
  }
  assert.equal(refreshPhaseNoticeKey("ready"), null);

  // STATIC TRIPWIRE — HomeProduction must consume homeSurfacePresentation for notice
  // text, notice visibility, and row visibility. No jsdom here; same discipline as
  // integration/cross-side/tasks-rendering-parity.test.mjs: pin the shipped wiring
  // against the production file's own source text so an unmirrored edit fails loudly.
  // Labelled a tripwire on purpose (AGENTS.md): reading source is not behavioural
  // coverage; the behavioural half is homeSurfacePresentation above.
  const mustContain = [
    "homeSurfacePresentation(refresh, results.length, refreshPhaseNoticeKey(refresh.phase))",
    "{presentation.noticeKey && <div className={`status-notice ${presentation.phase}`} role=\"status\">{t(locale, presentation.noticeKey)}</div>}",
    "{presentation.showsSavedRows ? (",
    "data-surface-state={presentation.phase}",
  ];
  const missing = mustContain.filter((fragment) => !source.includes(fragment));
  assert.deepEqual(
    missing,
    [],
    `HomeProduction.tsx no longer wires homeSurfacePresentation: ${JSON.stringify(missing)}`,
  );
  assert.doesNotMatch(source, /homePhaseLabel/);
  assert.doesNotMatch(source, /loadFailed|setLoadFailed|home-load-error|lifecycle\.error/);
  // A phase special-case in the JSX would let notice/rows diverge from the helper.
  assert.doesNotMatch(source, /saved-but-refresh-failed/);
  // red-proof: (1) suppress the failure notice in HomeProduction for
  // saved-but-refresh-failed — the mustContain notice line fails.
  // (2) map saved-but-refresh-failed to the ready notice in
  // lifecycle-presentation.ts — savedFailed.noticeKey === "lifecycle.savedFailed" fails.
});

test("home combines two source phases with a conservative worst-of reading", () => {
  assert.deepEqual(
    combineHomeRefreshStatuses(refresh("ready", true), refresh("unavailable", false)),
    refresh("saved-but-refresh-failed", true),
  );
  assert.deepEqual(
    combineHomeRefreshStatuses(refresh("unavailable", false), refresh("unavailable", false)),
    refresh("unavailable", false),
  );
  assert.deepEqual(
    combineHomeRefreshStatuses(refresh("ready", true), refresh("saved-but-refresh-failed", true)),
    refresh("saved-but-refresh-failed", true),
  );
  assert.deepEqual(
    combineHomeRefreshStatuses(refresh("ready", true), refresh("initial-loading", false)),
    refresh("initial-loading", true),
  );
  assert.deepEqual(
    combineHomeRefreshStatuses(refresh("ready", true), refresh("refreshing", true)),
    refresh("refreshing", true),
  );
  assert.deepEqual(
    combineHomeRefreshStatuses(refresh("ready", true), refresh("ready", false)),
    refresh("ready", true),
  );
  // red-proof: returning ready whenever either side is ready would tell the user
  // Home is fine while the other projection is unavailable or stale-failed.
});
