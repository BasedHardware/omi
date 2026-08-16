import assert from "node:assert/strict";
import test, { after } from "node:test";

import { EN_MESSAGES, t } from "@omi-core/i18n";
import { coerceScreenRetentionDays } from "@omi-core/adapters-platform";
import {
  closeRenderHarness,
  loadProductionExport,
  renderComponent,
} from "./render-harness.mjs";

after(closeRenderHarness);

async function renderScreen(state, extra = {}) {
  const ScreenProduction = await loadProductionExport("ScreenProduction.tsx", "ScreenProduction");
  const fixtureScreenStore = await loadProductionExport("screen-fixtures.ts", "fixtureScreenStore");
  const store = extra.store ?? fixtureScreenStore(state);
  const rendered = await renderComponent(ScreenProduction, {
    store,
    fixture: state,
    locale: "en",
    ...extra.props,
  });
  return { rendered, store };
}

function textOf(rendered) {
  return rendered.container.textContent ?? "";
}

test("the four empty kinds render distinct copy and stay uncollapsed", async () => {
  const cases = [
    ["never-enabled", "screen.emptyNeverEnabledTitle", "screen.emptyNeverEnabledBody"],
    ["permission-denied", "screen.emptyPermissionDeniedTitle", "screen.emptyPermissionDeniedBody"],
    ["day-empty", "screen.emptyDayTitle", "screen.emptyDayBody"],
    ["search-miss", "screen.emptySearchTitle", "screen.emptySearchBody"],
  ];
  const titles = [];
  for (const [state, titleKey, bodyKey] of cases) {
    const { rendered } = await renderScreen(state);
    try {
      const region = rendered.container.querySelector(`[data-empty-kind="${state}"]`);
      assert.ok(region, `${state} has its own empty region`);
      assert.equal(rendered.container.querySelector("main")?.getAttribute("data-empty-kind"), state);
      assert.equal(region.querySelector("h2")?.textContent, EN_MESSAGES[titleKey]);
      assert.match(region.textContent ?? "", new RegExp(EN_MESSAGES[bodyKey].slice(0, 24)));
      titles.push(region.querySelector("h2")?.textContent);
      if (state === "permission-denied") {
        assert.ok([...rendered.container.querySelectorAll("button")].some((button) => button.textContent === EN_MESSAGES["screen.requestPermission"]));
        assert.equal(rendered.container.querySelector('[data-empty-kind="never-enabled"]'), null);
      }
      if (state === "never-enabled") {
        assert.equal(rendered.container.querySelector('[data-empty-kind="permission-denied"]'), null);
        assert.equal(rendered.container.querySelector('[data-permission-badge="denied"]'), null);
      }
      if (state === "search-miss") {
        assert.equal(rendered.container.querySelector('[data-empty-kind="day-empty"]'), null);
      }
    } finally {
      await rendered.cleanup();
    }
  }
  assert.equal(new Set(titles).size, 4, "the four empty kinds must not share a title");
  // red-proof: collapsing permission-denied into never-enabled, or search-miss
  // into day-empty, makes this uniqueness assertion fail at the rendered layer.
});

test("Rewind day picker does not claim an empty day while refresh is still loading", async () => {
  // red-proof: the day-span else used to render screen.emptyDayTitle whenever
  // oldest/newest timestamps were missing, including during initial-loading.
  // screenDaySpanKind returning null is not this proof — this query is.
  const { rendered } = await renderScreen("loading");
  try {
    const toggle = rendered.container.querySelector(".screen-day-toggle");
    assert.ok(toggle, "day picker toggle is on screen during loading");
    await rendered.act(async () => { toggle.click(); });
    const span = rendered.container.querySelector("[data-day-span='true']");
    assert.ok(span, "opening the picker still renders the span");
    assert.equal(
      span.textContent?.includes(EN_MESSAGES["screen.emptyDayTitle"]),
      false,
      "loading day span must not claim this day has no captures",
    );
    assert.equal(rendered.container.querySelector("[data-empty-kind='day-empty']"), null);
  } finally {
    await rendered.cleanup();
  }
});

test("ready Rewind day picker may claim an empty day once refresh has finished", async () => {
  const ScreenProduction = await loadProductionExport("ScreenProduction.tsx", "ScreenProduction");
  const fixtureScreenStore = await loadProductionExport("screen-fixtures.ts", "fixtureScreenStore");
  const base = fixtureScreenStore("loading");
  const readyEmptySpan = {
    ...base,
    status() {
      return { refresh: { phase: "ready", hasSavedData: false }, queue: { phase: "idle", pendingCount: 0 } };
    },
  };
  const rendered = await renderComponent(ScreenProduction, {
    store: readyEmptySpan,
    fixture: "ready-empty-span",
    locale: "en",
  });
  try {
    const toggle = rendered.container.querySelector(".screen-day-toggle");
    assert.ok(toggle, "day picker toggle is on screen when ready with no timestamps");
    await rendered.act(async () => { toggle.click(); });
    const span = rendered.container.querySelector("[data-day-span='true']");
    assert.ok(span);
    assert.equal(
      span.textContent?.includes(EN_MESSAGES["screen.emptyDayTitle"]),
      true,
      "a finished ready snapshot with no timestamps may claim this day has no captures",
    );
  } finally {
    await rendered.cleanup();
  }
});

test("ready Rewind renders app badge, window title, timestamp, extracted text, and playback counter", async () => {
  const { rendered } = await renderScreen("ready");
  try {
    const text = textOf(rendered);
    assert.match(text, /Safari/);
    assert.match(text, /Harborline Cafe/);
    assert.ok(rendered.container.querySelector("[data-app-badge='true']"));
    assert.ok(rendered.container.querySelector("[data-window-title='true']"));
    assert.ok(rendered.container.querySelector("[data-timestamp-pill='true']"));
    assert.match(text, /Extracted Text/);
    assert.equal(
      rendered.container.querySelector("[data-frame-counter='true']")?.textContent,
      t("en", "screen.frameCounter", { current: 1, total: 2 }),
    );
    assert.equal(rendered.container.querySelector("main")?.getAttribute("data-capture-tone"), "green");
    assert.ok(rendered.container.querySelector("img.screen-frame-image"));
    assert.equal(rendered.container.querySelector("main")?.getAttribute("data-route"), "screen");
    assert.equal(rendered.container.querySelector("main")?.getAttribute("data-frame-image"), "ready");
  } finally {
    await rendered.cleanup();
  }
});

test("search debounce waits 300ms then groups Harborline hits with snippet marks", async () => {
  const { rendered, store } = await renderScreen("ready");
  try {
    await rendered.act(async () => {
      store.setSearchQuery("Harborline");
    });
    assert.equal(rendered.container.querySelector(".screen-result-hit"), null, "hits wait for debounce");
    await rendered.act(async () => { store.runDebounce(); });
    const hit = rendered.container.querySelector(".screen-result-hit");
    assert.ok(hit, "debounced search renders a hit");
    assert.ok(hit.querySelector("mark"), "matched OCR terms are marked in the snippet");
    assert.match(hit.textContent ?? "", /Harborline/);
    const highlight = rendered.container.querySelector(".screen-highlight");
    assert.ok(highlight, "matched OCR blocks highlight on the frame");
    assert.equal(highlight.style.left, "8%");
    assert.equal(highlight.style.top, "12%");
    assert.equal(highlight.style.width, "40%");
    assert.equal(highlight.style.height, "8%");
  } finally {
    await rendered.cleanup();
  }
});

test("keyboard arrows step frames and groups; Escape unwinds search", async () => {
  const { rendered, store } = await renderScreen("ready");
  try {
    assert.equal(store.frameCursor(), 0);
    await rendered.act(async () => {
      rendered.window.dispatchEvent(new rendered.window.KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    });
    assert.equal(store.frameCursor(), 1);
    assert.equal(
      rendered.container.querySelector("[data-frame-counter='true']")?.textContent,
      t("en", "screen.frameCounter", { current: 2, total: 2 }),
    );
    await rendered.act(async () => {
      store.setSearchQuery("Harborline");
      store.runDebounce();
    });
    await rendered.act(async () => {
      rendered.window.dispatchEvent(new rendered.window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    assert.equal(store.searchQuery(), "");
  } finally {
    await rendered.cleanup();
  }
});

test("day jumps skip empty days by walking the real capture span", async () => {
  const { rendered, store } = await renderScreen("ready");
  try {
    assert.equal(store.selectedDay(), "2026-08-07");
    await rendered.act(async () => { await store.jumpDay("older"); });
    assert.equal(store.selectedDay(), "2026-08-04");
    await rendered.act(async () => { await store.jumpDay("newer"); });
    assert.equal(store.selectedDay(), "2026-08-07");
    await rendered.act(async () => { await store.jumpDay("oldest"); });
    assert.equal(store.selectedDay(), "2026-08-04");
    const { rendered: emptyDay, store: emptyStore } = await renderScreen("day-empty");
    try {
      assert.equal(emptyStore.selectedDay(), "2026-08-06");
      await emptyDay.act(async () => { await emptyStore.jumpDay("older"); });
      assert.equal(emptyStore.selectedDay(), "2026-08-04");
      assert.notEqual(emptyStore.selectedDay(), "2026-08-06");
    } finally {
      await emptyDay.cleanup();
    }
  } finally {
    await rendered.cleanup();
  }
});

test("playback counter advances on a tick and an engine error is never permission-denied", async () => {
  const { rendered, store } = await renderScreen("ready");
  try {
    await rendered.act(async () => { store.play(); });
    assert.equal(store.playing(), true);
    await rendered.act(async () => { store.runPlaybackTick(); });
    assert.equal(store.frameCursor(), 1);
    assert.match(rendered.container.querySelector("[data-frame-counter='true']")?.textContent ?? "", /2\/2/);
  } finally {
    await rendered.cleanup();
  }
  const { rendered: recovered } = await renderScreen("recovered");
  try {
    assert.equal(recovered.container.querySelector("main")?.getAttribute("data-permission"), "granted");
    assert.equal(recovered.container.querySelector("main")?.getAttribute("data-engine-state"), "error");
    assert.equal(recovered.container.querySelector("[data-empty-kind='permission-denied']"), null);
    assert.ok([...recovered.container.querySelectorAll("button")].some((button) => button.textContent === EN_MESSAGES["screen.rebuildIndex"]));
    assert.ok(recovered.container.querySelector("[data-engine-error='true']"));
  } finally {
    await recovered.cleanup();
  }
});

test("bridge-absent degrades capture and frame images without hiding history", async () => {
  const { rendered } = await renderScreen("bridge-absent");
  try {
    const text = textOf(rendered);
    assert.match(text, /Safari|Harborline|Notes|Cedar/);
    assert.match(text, /Capture controls are not available here/);
    assert.match(text, /On-device frame images are not available in this host/);
    assert.doesNotMatch(text, /Frame image is not available here/);
    assert.equal(rendered.container.querySelector(".screen-capture-toggle"), null, "no working capture control is drawn");
    assert.ok(rendered.container.querySelector(".production-disabled-control"));
    assert.equal(rendered.container.querySelector("img.screen-frame-image"), null);
    assert.ok(rendered.container.querySelector(".screen-frame-host-unavailable"));
    assert.equal(rendered.container.querySelector(".screen-frame-unavailable"), null);
    assert.equal(rendered.container.querySelector("main")?.getAttribute("data-frame-image"), "unavailable");
    assert.equal(rendered.container.querySelector("main")?.getAttribute("data-bridge"), "absent");
  } finally {
    await rendered.cleanup();
  }
});

test("RED-PROOF missing frame bytes render .screen-frame-unavailable, not an image", async () => {
  // red-proof: restore the ready fixture's image here, or collapse this
  // branch into the bridge-absent copy. The control token reads this
  // paragraph, not the HTTP fetch.
  const { rendered: missing } = await renderScreen("frame-bytes-missing");
  try {
    const text = textOf(missing);
    assert.equal(missing.container.querySelector("img.screen-frame-image"), null);
    assert.ok(missing.container.querySelector(".screen-frame-unavailable"));
    assert.equal(missing.container.querySelector(".screen-frame-host-unavailable"), null);
    assert.match(text, /Frame image is not available here/);
    assert.doesNotMatch(text, /On-device frame images are not available in this host/);
    assert.equal(missing.container.querySelector("main")?.getAttribute("data-frame-image"), "unavailable");
    assert.equal(missing.container.querySelector("main")?.getAttribute("data-bridge"), "present");
  } finally {
    await missing.cleanup();
  }

  const { rendered: restored } = await renderScreen("ready");
  try {
    const img = restored.container.querySelector("img.screen-frame-image");
    assert.ok(img, "ready Rewind draws the frame image the user sees");
    assert.match(img.getAttribute("src") ?? "", /^data:image\/png;base64,/);
    assert.equal(restored.container.querySelector(".screen-frame-unavailable"), null);
    assert.equal(restored.container.querySelector("main")?.getAttribute("data-frame-image"), "ready");
  } finally {
    await restored.cleanup();
  }
});

test("openFrame citation entry selects the exact frame", async () => {
  const { rendered, store } = await renderScreen("ready");
  try {
    let opened = false;
    await rendered.act(async () => {
      opened = await store.openFrame("demo-screen-cedar-packing");
    });
    assert.equal(opened, true);
    assert.equal(store.selectedFrame()?.id, "demo-screen-cedar-packing");
    assert.match(rendered.container.querySelector("[data-window-title='true']")?.textContent ?? "", /Cedar Loop packing/);
  } finally {
    await rendered.cleanup();
  }
});

test("retention fail-safe renders unlimited, never a deleting window, and bytes-unknown stays honest", async () => {
  const SettingsProduction = await loadProductionExport("SettingsProduction.tsx", "SettingsProduction");
  const fixtureSettingsStore = await loadProductionExport("settings-fixtures.ts", "fixtureSettingsStore");
  const fixtureScreenStore = await loadProductionExport("screen-fixtures.ts", "fixtureScreenStore");
  const unlimited = await renderComponent(SettingsProduction, {
    store: fixtureSettingsStore("signed-in"),
    screenStore: fixtureScreenStore("retention-unlimited"),
    locale: "en",
  });
  try {
    assert.equal(unlimited.container.querySelector("[data-retention-days]")?.getAttribute("data-retention-days"), "0");
    assert.match(unlimited.container.querySelector("[data-settings-screen='true']")?.textContent ?? "", /Unlimited/);
    assert.doesNotMatch(unlimited.container.querySelector("[data-settings-screen='true']")?.textContent ?? "", /delete|\b0 days\b/i);
  } finally {
    await unlimited.cleanup();
  }
  const unknown = await renderComponent(SettingsProduction, {
    store: fixtureSettingsStore("signed-in"),
    screenStore: fixtureScreenStore("bytes-unknown"),
    locale: "en",
  });
  try {
    const summary = unknown.container.querySelector("[data-storage-summary='true']")?.textContent ?? "";
    assert.match(summary, /couldn't read|storage size couldn't be read/);
    assert.doesNotMatch(summary, /0 GB/);
    assert.equal(unknown.container.querySelector("[data-bytes-known]")?.getAttribute("data-bytes-known"), "false");
  } finally {
    await unknown.cleanup();
  }
  assert.equal(coerceScreenRetentionDays(-1), 0);
  assert.equal(coerceScreenRetentionDays(Number.NaN), 0);
  assert.equal(coerceScreenRetentionDays(7), 7);
});

test("Rewind citation href helper pins the frame query without inventing a citation source", async () => {
  const href = await loadProductionExport("ProductionChrome.tsx", "productionRewindFrameHref");
  const rendered = await renderComponent(() => null, {});
  try {
    assert.match(href("demo-screen-harborline-reservation"), /route=rewind/);
    assert.match(href("demo-screen-harborline-reservation"), /frame=demo-screen-harborline-reservation/);
  } finally {
    await rendered.cleanup();
  }
});

test("excluded pause names that this app is not being captured", async () => {
  const ScreenProduction = await loadProductionExport("ScreenProduction.tsx", "ScreenProduction");
  const fixtureScreenStore = await loadProductionExport("screen-fixtures.ts", "fixtureScreenStore");
  const base = fixtureScreenStore("ready");
  const store = {
    ...base,
    captureStatus: () => ({
      ...base.captureStatus(),
      state: "paused",
      reason: "excluded",
    }),
    engineState: () => "paused",
  };
  const rendered = await renderComponent(ScreenProduction, { store, locale: "en" });
  try {
    const badge = rendered.container.querySelector(".screen-capture-badge.is-paused");
    assert.ok(badge, "paused capture is visible on Rewind");
    assert.equal(badge.getAttribute("data-capture-reason"), "excluded");
    assert.equal(badge.textContent, EN_MESSAGES["screen.capturePausedExcluded"]);
    assert.notEqual(badge.textContent, EN_MESSAGES["screen.capturePaused"]);
  } finally {
    await rendered.cleanup();
  }
  // red-proof: a generic "Capture paused" badge while Rewind is frontmost
  // looks like recording is working.
});
