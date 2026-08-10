import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test, { after } from "node:test";

import { EN_MESSAGES } from "@omi-core/i18n";
import {
  combineHomeRefreshStatuses,
  homeSurfacePresentation,
} from "../src/production/home-presentation.ts";
import { refreshPhaseNoticeKey } from "../src/production/lifecycle-presentation.ts";
import {
  closeRenderHarness,
  loadProductionExport,
  renderComponent,
} from "./render-harness.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

const refresh = (phase, hasSavedData) => ({ phase, hasSavedData });

after(closeRenderHarness);

function projection(initialPhase = "initial-loading", initialRows = []) {
  let rows = initialRows;
  let status = refresh(initialPhase, initialRows.length > 0);
  const listeners = new Set();
  return {
    source: {
      list: async () => rows,
      status: () => ({ refresh: status, pendingWrites: 0, deadLetters: [] }),
      subscribe(listener) {
        listeners.add(listener);
        return () => listeners.delete(listener);
      },
    },
    ready(value = []) {
      rows = value;
      status = refresh("ready", value.length > 0);
      for (const listener of listeners) listener();
    },
  };
}

function present(phase, hasSavedData, rowCount, filtering = false) {
  const status = refresh(phase, hasSavedData);
  return homeSurfacePresentation(status, rowCount, refreshPhaseNoticeKey(phase), filtering);
}

test("home search reads loaded projections without claiming backend completeness", async () => {
  // RETAINED-SOURCE-ASSERTION: forbidden backend-search calls and projection-only reads are port-boundary facts.
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

test("home search source stays a memory-and-conversation chronological projection", async () => {
  // RETAINED-SOURCE-ASSERTION: the allowed result union and sort implementation are structural projection constraints.
  const source = await read("src/production/HomeProduction.tsx");
  const styles = await read("src/production/home.css");
  assert.match(source, /kind: "memory"/);
  assert.match(source, /kind: "conversation"/);
  assert.doesNotMatch(source, /kind: "task"/);
  assert.match(source, /sort\(\(left, right\) => right\.timestamp - left\.timestamp\)/);
  assert.match(source, /\["all", "conversation", "memory"\]/);
  assert.match(styles, /grid-template-rows:\s*auto 12px minmax\(0,1fr\)/);
  assert.match(styles, /height:\s*64px/);
  assert.doesNotMatch(styles, /@media\s*\(/);
  assert.doesNotMatch(styles, /#(?:[0-9a-f]{3,8})\b/i);
  // STRUCTURAL PROJECTION/CSS ASSERTION: the allowed union, descending sort,
  // host-selected grid, and token use are implementation-boundary facts. The
  // search, clear, focus, filter, and row hierarchy execute below.
});

test("home does not fabricate ask, chat, send, or mutation affordances", async () => {
  // RETAINED-SOURCE-ASSERTION: capability absence is an API and dependency boundary, not one fixture's rendered state.
  const source = await read("src/production/HomeProduction.tsx");
  assert.doesNotMatch(source, /store\.create|store\.patch|store\.delete|\b(?:ask|chat|send)\b/i);
  assert.match(source, /href=\{conversationHref\(row\.value\.id\)\}/);
  assert.doesNotMatch(source, /href=\{.*memory|href=\{.*task/i);
  // red-proof: adding an Ask button or clickable memory/task destination would
  // claim behavior the current loaded projections do not provide.
});

test("home empty kinds distinguish true-empty from filter-miss", () => {
  assert.equal(present("ready", false, 0, false).emptyKind, "empty-projection");
  assert.equal(present("ready", true, 0, true).emptyKind, "filtered-out");
  assert.equal(present("ready", true, 2, true).emptyKind, null);
  assert.equal(present("ready", true, 2, false).emptyKind, null);
  assert.equal(EN_MESSAGES["home.startTyping"], "Start typing to search what's saved");
  assert.equal(EN_MESSAGES["common.noResults"], "No results");
  // red-proof: returning one shared emptyKind for both filtering=true and
  // filtering=false when rowCount is 0 collapses the two claims.
});

test("HomeProduction with zero rows makes no empty claim while loading, then renders true-empty once ready", async () => {
  const memories = projection();
  const conversations = projection();
  const HomeProduction = await loadProductionExport("HomeProduction.tsx", "HomeProduction");
  const rendered = await renderComponent(HomeProduction, {
    sources: { memories: memories.source, conversations: conversations.source },
  });

  try {
    assert.equal(
      rendered.container.querySelector("[data-empty-kind]") === null,
      true,
      "initial-loading must not render an empty-state claim",
    );
    await rendered.act(async () => {
      memories.ready();
      conversations.ready();
      await Promise.resolve();
    });
    const empty = rendered.container.querySelector('[data-empty-kind="empty-projection"]');
    assert.ok(empty, "ready with zero rows must render the true-empty state");
    assert.equal(empty.textContent?.trim(), EN_MESSAGES["home.startTyping"]);
    assert.equal(rendered.container.querySelector('[data-empty-kind="filtered-out"]'), null);
  } finally {
    await rendered.cleanup();
  }

  // red-proof: current trunk at 8e2e1c52b2 returned emptyKind=null correctly,
  // but HomeProduction's unconditional final else still rendered empty-projection;
  // the initial-loading assertion failed against that real shipped behavior.
});

test("HomeProduction renders a merged searchable spine with clear, filter, and keyboard focus behavior", async () => {
  const HomeProduction = await loadProductionExport("HomeProduction.tsx", "HomeProduction");
  const fixtureMemoryStore = await loadProductionExport("memory-fixtures.ts", "fixtureStore");
  const fixtureConversationStore = await loadProductionExport("conversation-fixtures.ts", "fixtureConversationStore");
  const rendered = await renderComponent(HomeProduction, {
    sources: {
      memories: fixtureMemoryStore("normal"),
      conversations: fixtureConversationStore("normal"),
    },
  });

  try {
    const input = rendered.container.querySelector('input[type="search"]');
    assert.ok(input);
    assert.equal(rendered.window.document.activeElement, input, "search is focused on entry");
    const rows = [...rendered.container.querySelectorAll(".home-result-row")];
    assert.ok(rows.some((row) => row.matches("article")), "merged spine contains memories");
    assert.ok(rows.some((row) => row.matches("a")), "merged spine contains conversations");
    assert.equal(rows[0].textContent?.includes("Keep the morning review short"), true, "rows render newest-first");

    input.blur();
    await rendered.act(async () => {
      rendered.window.dispatchEvent(new rendered.window.KeyboardEvent("keydown", { key: "k", metaKey: true, bubbles: true }));
    });
    assert.equal(rendered.window.document.activeElement, input, "Command-K focuses search");

    const setter = Object.getOwnPropertyDescriptor(rendered.window.HTMLInputElement.prototype, "value")?.set;
    assert.ok(setter);
    await rendered.act(async () => {
      setter.call(input, "no saved row has this phrase");
      input.dispatchEvent(new rendered.window.Event("input", { bubbles: true }));
    });
    assert.ok(rendered.container.querySelector('[data-empty-kind="filtered-out"]'));
    const clear = rendered.container.querySelector(`button[aria-label="${EN_MESSAGES["common.clearSearch"]}"]`);
    assert.ok(clear);
    await rendered.act(async () => { clear.click(); });
    assert.equal(input.value, "");
    assert.equal(rendered.window.document.activeElement, input);

    const memoryFilter = [...rendered.container.querySelectorAll(".home-kind-filter button")]
      .find((button) => button.textContent?.trim() === EN_MESSAGES["nav.memories"]);
    assert.ok(memoryFilter);
    await rendered.act(async () => { memoryFilter.click(); });
    assert.ok(rendered.container.querySelectorAll(".home-result-row").length > 0);
    assert.equal(rendered.container.querySelector("a.home-result-row"), null, "memory filter excludes conversation rows");
    const rewind = [...rendered.container.querySelectorAll(".home-kind-filter button")]
      .find((button) => button.textContent?.trim() === EN_MESSAGES["nav.rewind"]);
    assert.ok(rewind?.disabled, "unsupported Rewind is visibly disabled");
  } finally {
    await rendered.cleanup();
  }
});

test("home renders each of the five refresh states distinguishably", async () => {
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
  for (const key of ["lifecycle.loading", "lifecycle.refreshing", "lifecycle.savedFailed", "lifecycle.unavailable"]) {
    assert.equal(typeof EN_MESSAGES[key], "string");
    assert.ok(EN_MESSAGES[key].length > 0);
  }
  assert.equal(refreshPhaseNoticeKey("ready"), null);

  const HomeProduction = await loadProductionExport("HomeProduction.tsx", "HomeProduction");
  const fixtureMemoryStore = await loadProductionExport("memory-fixtures.ts", "fixtureStore");
  const [savedMemory] = await fixtureMemoryStore("normal").list();
  const renderCases = [
    { phase: "initial-loading", rows: [], notice: EN_MESSAGES["lifecycle.loading"], emptyKind: null },
    { phase: "refreshing", rows: [savedMemory], notice: EN_MESSAGES["lifecycle.refreshing"], emptyKind: null },
    { phase: "ready", rows: [], notice: null, emptyKind: "empty-projection" },
    { phase: "saved-but-refresh-failed", rows: [savedMemory], notice: EN_MESSAGES["lifecycle.savedFailed"], emptyKind: null },
    { phase: "unavailable", rows: [], notice: EN_MESSAGES["lifecycle.unavailable"], emptyKind: null },
  ];
  for (const renderCase of renderCases) {
    const memories = projection(renderCase.phase, renderCase.rows);
    const conversations = projection(renderCase.phase);
    const rendered = await renderComponent(HomeProduction, {
      sources: { memories: memories.source, conversations: conversations.source },
    });
    try {
      const main = rendered.container.querySelector("main[data-route=home]");
      assert.equal(main?.getAttribute("data-surface-state"), renderCase.phase);
      const notice = rendered.container.querySelector(".status-notice");
      assert.equal(notice?.textContent ?? null, renderCase.notice, `${renderCase.phase} renders its truthful notice`);
      assert.equal(
        rendered.container.querySelector("[data-empty-kind]")?.getAttribute("data-empty-kind") ?? null,
        renderCase.emptyKind,
        `${renderCase.phase} renders only its truthful empty claim`,
      );
      assert.equal(
        rendered.container.querySelectorAll(".home-result-row").length,
        renderCase.rows.length,
        `${renderCase.phase} preserves the expected saved rows`,
      );
    } finally {
      await rendered.cleanup();
    }
  }
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

test("home makes no empty-state claim before it is ready to make one", () => {
  // The review of aac098b87a..8b20f36e53 caught this: listEmptyKind gates on
  // phase === "ready" precisely so a refresh notice is never paired with a
  // lying empty region, but homeSurfacePresentation received status.phase and
  // never consulted it. Home therefore announced "nothing is saved" — or worse,
  // "your filter excluded everything" — while it was still loading.
  for (const phase of ["initial-loading", "refreshing", "unavailable", "saved-but-refresh-failed"]) {
    assert.equal(
      present(phase, false, 0).emptyKind,
      null,
      `${phase} with zero rows must not claim an empty kind`,
    );
    assert.equal(
      present(phase, false, 0, true).emptyKind,
      null,
      `${phase} with zero rows and an active filter must not claim a filter miss`,
    );
  }

  // Ready is the only phase entitled to an opinion, and it keeps both of them.
  assert.equal(present("ready", true, 0).emptyKind, "empty-projection");
  assert.equal(present("ready", true, 0, true).emptyKind, "filtered-out");
  assert.equal(present("ready", true, 3).emptyKind, null);
});
