import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test, { after } from "node:test";

import { EN_MESSAGES } from "@omi-core/i18n";
import { createElement, useState } from "react";
import {
  closeRenderHarness,
  loadProductionExport,
  renderComponent,
} from "./render-harness.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

after(closeRenderHarness);

test("shared lifecycle primitive gives every phase one truthful semantic region", async () => {
  const ProductionLifecycleRegion = await loadProductionExport("ProductionPrimitives.tsx", "ProductionLifecycleRegion");
  const cases = [
    ["initial-loading", false, true],
    ["refreshing", true, true],
    ["ready", true, false],
    ["saved-but-refresh-failed", true, false],
    ["unavailable", false, false],
  ];
  for (const [phase, hasSavedData, busy] of cases) {
    const rendered = await renderComponent(ProductionLifecycleRegion, {
      phase,
      hasSavedData,
      locale: "en",
      queue: { phase: "retrying", pendingCount: 2 },
      deadLetterCount: 1,
      lastSuccessAgeMs: 65_000,
      nextAction: "Retry refresh",
      operationError: phase === "unavailable" ? "Refresh failed" : null,
      retry: { onRetry() {} },
    });
    try {
      const region = rendered.container.querySelector(".production-lifecycle-region");
      assert.ok(region);
      assert.equal(region.getAttribute("data-phase"), phase);
      assert.equal(region.getAttribute("aria-busy"), busy ? "true" : null);
      assert.equal(region.getAttribute("aria-label"), EN_MESSAGES["lifecycle.region"]);
      assert.ok(region.querySelector('[role="status"]'), `${phase} has a status boundary`);
      assert.equal(region.querySelectorAll('[role="status"]').length, 1, "one atomic status boundary prevents lifecycle spam");
      assert.ok(region.querySelector(".lifecycle-next-action"));
      assert.ok(region.querySelector(".lifecycle-dead-letters"));
      assert.ok(region.querySelector(".lifecycle-retry"));
      if (phase === "unavailable") assert.ok(region.querySelector('[role="alert"]'));
      else assert.equal(region.querySelector('[role="alert"]'), null);
    } finally {
      await rendered.cleanup();
    }
  }
});

test("data-source badge exposes the exact visible provenance at every source kind", async () => {
  const ProductionDataSourceBadge = await loadProductionExport("ProductionPrimitives.tsx", "ProductionDataSourceBadge");
  for (const source of [{ kind: "fixture", fixture: "normal" }, { kind: "live", origin: "bridge" }]) {
    const rendered = await renderComponent(ProductionDataSourceBadge, { source, locale: "en" });
    try {
      const badge = rendered.container.querySelector(".data-source-badge");
      assert.ok(badge);
      assert.equal(badge.getAttribute("data-source-kind"), source.kind);
      assert.equal(badge.getAttribute("aria-label"), badge.textContent?.trim());
      assert.notEqual(badge.textContent?.trim(), "");
    } finally {
      await rendered.cleanup();
    }
  }

  const live = await renderComponent(ProductionDataSourceBadge, {
    source: { kind: "live", origin: "bridge" },
    locale: "en",
  });
  try {
    const badge = live.container.querySelector(".data-source-badge");
    assert.equal(badge?.textContent, "Your account data");
    assert.equal(badge?.getAttribute("aria-label"), "Your account data");
    assert.equal(badge?.getAttribute("data-source-origin"), "bridge");
    assert.doesNotMatch(badge?.textContent ?? "", /backend|bridge/i);
  } finally {
    await live.cleanup();
  }
});

test("operation errors announce once and unchanged store rerenders are quiet", async () => {
  const ProductionOperationError = await loadProductionExport("ProductionPrimitives.tsx", "ProductionOperationError");
  let setError;
  let bump;
  function Wrapper() {
    const [error, update] = useState("Needs action");
    const [, updateTick] = useState(0);
    setError = update;
    bump = () => updateTick((value) => value + 1);
    return createElement(ProductionOperationError, { error });
  }
  const rendered = await renderComponent(Wrapper, {});
  try {
    assert.ok(rendered.container.querySelector('[role="alert"]'));
    await rendered.act(async () => { bump(); });
    assert.equal(rendered.container.querySelector('[role="alert"]'), null, "same text must not re-alert");
    await rendered.act(async () => { setError("A different action is required"); });
    assert.ok(rendered.container.querySelector('[role="alert"]'));
  } finally {
    await rendered.cleanup();
  }
});

test("live announcements debounce and deduplicate count/state changes", async () => {
  const ProductionLiveAnnouncement = await loadProductionExport("ProductionPrimitives.tsx", "ProductionLiveAnnouncement");
  const pending = [];
  const scheduler = {
    setTimeout(callback, delayMs) {
      const handle = { callback, delayMs, cancelled: false };
      pending.push(handle);
      return handle;
    },
    clearTimeout(handle) { handle.cancelled = true; },
  };
  const flush = async () => {
    const due = pending.splice(0);
    await rendered.act(async () => {
      for (const handle of due) if (!handle.cancelled) handle.callback();
    });
  };
  let setMessage;
  function Wrapper() {
    const [message, update] = useState("2 results");
    setMessage = update;
    return createElement(ProductionLiveAnnouncement, { message, delayMs: 10, scheduler });
  }
  const rendered = await renderComponent(Wrapper, {});
  try {
    const live = rendered.container.querySelector('[data-live-region="true"]');
    assert.ok(live);
    assert.equal(live.textContent, "", "announcement waits for debounce");
    assert.deepEqual(pending.map(({ delayMs }) => delayMs), [10]);
    await flush();
    assert.equal(live.textContent, "2 results");
    await rendered.act(async () => { setMessage("2 results"); });
    assert.equal(pending.length, 0, "unchanged text does not schedule a timer");
    assert.equal(live.textContent, "2 results", "unchanged text is not re-enqueued");
    await rendered.act(async () => { setMessage("3 results"); });
    await flush();
    assert.equal(live.textContent, "3 results");
  } finally {
    await rendered.cleanup();
  }
});

test("disabled control primitive always supplies a name, explanation, and explicit focus policy", async () => {
  const ProductionDisabledControl = await loadProductionExport("ProductionPrimitives.tsx", "ProductionDisabledControl");
  const rendered = await renderComponent(() => createElement("div", null,
    createElement(ProductionDisabledControl, { label: "Attach audio", explanation: "Audio capture is unavailable" }),
    createElement(ProductionDisabledControl, { focusable: true, label: "Share audio", explanation: "Audio sharing is unavailable" }),
    createElement(ProductionDisabledControl, { as: "span", focusable: true, label: "Screen capture", explanation: "Screen capture permission is required" }),
  ), {});
  try {
    const button = rendered.container.querySelector("button");
    assert.ok(button?.disabled);
    assert.equal(button?.getAttribute("aria-label"), "Attach audio");
    assert.ok(button?.getAttribute("aria-describedby"));
    assert.equal(button?.getAttribute("tabindex"), null, "native disabled controls intentionally leave the tab order");
    const explainedNative = [...rendered.container.querySelectorAll('[role="button"]')]
      .find((control) => control.getAttribute("aria-label") === "Share audio");
    assert.equal(explainedNative?.getAttribute("tabindex"), "0", "focusable policy exposes an explanation target");
    const custom = rendered.container.querySelector('[role="button"]');
    assert.ok(custom);
    assert.equal(custom?.getAttribute("aria-disabled"), "true");
    assert.equal(custom?.getAttribute("tabindex"), "0");
    assert.ok(custom?.getAttribute("aria-describedby"));
    assert.ok([...rendered.container.querySelectorAll(".visually-hidden")].some((node) => node.textContent?.includes("permission")));
  } finally {
    await rendered.cleanup();
  }
});

test("shared primitives expose the complete pointer, touch, keyboard, selection, disabled, and busy state matrix", async () => {
  const ProductionFilterChips = await loadProductionExport("ProductionPrimitives.tsx", "ProductionFilterChips");
  const ProductionLifecycleRegion = await loadProductionExport("ProductionPrimitives.tsx", "ProductionLifecycleRegion");
  const styles = await read("src/production/styles.css");
  const changes = [];
  const rendered = await renderComponent(() => createElement("div", { className: "production-shell" },
    createElement(ProductionFilterChips, {
      label: "Memory filters",
      value: "all",
      options: [
        { value: "all", label: "All" },
        { value: "locked", label: "Locked", disabled: true },
      ],
      onValueChange(value) { changes.push(value); },
    }),
    createElement(ProductionLifecycleRegion, {
      phase: "refreshing",
      hasSavedData: true,
      locale: "en",
    }),
  ), {});
  try {
    const [selected, disabled] = rendered.container.querySelectorAll(".production-filter-chips button");
    assert.equal(selected?.getAttribute("aria-pressed"), "true", "selection is not hover-dependent");
    assert.equal(disabled?.disabled, true, "disabled state is native and blocks activation");
    disabled?.click();
    assert.deepEqual(changes, [], "disabled control cannot invoke its action");
    assert.equal(rendered.container.querySelector(".production-lifecycle-region")?.getAttribute("aria-busy"), "true");

    const stateContract = [
      ["pointer hover", /button:hover:not\(:disabled\)/],
      ["touch or pointer pressed", /button:active:not\(:disabled\)/],
      ["keyboard focus", /\.production-shell[\s\S]*:focus-visible[\s\S]*outline:/],
      ["selected", /\[aria-pressed="true"\], \[aria-selected="true"\], \.is-selected/],
      ["disabled", /button:disabled, \[aria-disabled="true"\]/],
      ["busy", /\[aria-busy="true"\] \{ cursor: progress;/],
    ];
    for (const [state, selector] of stateContract) assert.match(styles, selector, `${state} has a shared treatment`);
    assert.match(styles, /button:active:not\(:disabled\)[^\{]*\{[^}]*transform:/, "pressed feedback exists independently of hover");
    assert.match(styles, /\[aria-pressed="true"\][^\{]*\{[^}]*border-color:/, "selected feedback exists independently of hover");
  } finally {
    await rendered.cleanup();
  }
});

test("production dates keep a localized date primary and exact time in secondary detail", async () => {
  const conversations = await read("src/production/ConversationsProduction.tsx");
  const memories = await read("src/production/MemoriesProduction.tsx");
  const tasks = await read("src/production/TasksProduction.tsx");
  assert.match(conversations, /dateStyle: "medium", timeStyle: "short"/, "conversation detail exposes localized date and exact time");
  assert.match(conversations, /dateStyle: "medium"/, "conversation groups remain plain-language dates");
  assert.match(conversations, /timeStyle: "short"/, "row time stays secondary rather than competing with the day label");
  assert.match(memories, /formatDate\(memory\.updatedAt, locale\)/, "memory metadata uses the shared localized medium date");
  assert.match(tasks, /dateStyle: "medium"/, "task due dates use localized medium date granularity");
});

test("shared primitive/static CSS contract covers provenance, focus, motion, transparency, and non-live lists", async () => {
  const primitives = await read("src/production/ProductionPrimitives.tsx");
  const styles = await read("src/production/styles.css");
  assert.match(primitives, /data-source-kind=\{source\.kind\}/);
  assert.match(primitives, /aria-label=\{detail\}/);
  assert.match(primitives, /aria-busy=\{loading \? "true" : undefined\}/);
  assert.match(primitives, /data-live-region="true"/);
  assert.match(primitives, /aria-describedby/);
  assert.match(styles, /:where\(input, textarea, select, button, a/);
  assert.match(styles, /\.production-shell input:focus-visible[\s\S]*outline:[^;]+!important/);
  assert.match(styles, /prefers-reduced-motion/);
  assert.match(styles, /prefers-reduced-transparency/);
  assert.match(styles, /data-source-badge/);
  assert.doesNotMatch(styles, /\.data-source-badge\s*\{[^}]*display:\s*none/i);
  assert.match(styles, /\.production-page-heading h1 \{[^}]*max-width: var\(--measure-title\)/);
  assert.match(styles, /\.production-page-description \{[^}]*max-width: var\(--measure-body\)/);
  assert.match(styles, /\.memory-meta \{[^}]*font-family: var\(--type-meta-family\)/);
  assert.doesNotMatch(styles, /\.eyebrow, \.memory-meta, \.qa-label[^}]*text-transform: uppercase/);
  assert.match(styles, /\.dead-letter-payload \{[^}]*font-family: var\(--type-code-family\)/);
});

test("desktop route polish preserves semantic themes and 44-point interaction targets", async () => {
  const files = ["styles.css", "home.css", "tasks.css", "conversations.css", "memories-platform.css"];
  const sources = await Promise.all(files.map((file) => read(`src/production/${file}`)));
  const routes = sources.slice(1).join("\n");
  const all = sources.join("\n");
  assert.match(sources[0], /--glass-surface-soft:/);
  assert.match(sources[0], /--accent-soft:/);
  assert.doesNotMatch(
    routes,
    /(?:button|input|select|textarea|task-check|trigger|control)[^{]*\{[^}]*min-height:\s*(?:2\d|3\d|4[0-3])px/i,
    "route controls keep the shared 44-point target even when their glyph is visually compact",
  );
  assert.doesNotMatch(routes, /background:\s*rgba\(255,\s*255,\s*255/i, "route surfaces use semantic theme roles");
  assert.match(all, /prefers-reduced-motion/);
  assert.match(all, /prefers-reduced-transparency/);
});

test("shared visual gallery renders one coherent semantic component vocabulary", async () => {
  const ProductionPageHeader = await loadProductionExport("ProductionPrimitives.tsx", "ProductionPageHeader");
  const ProductionSection = await loadProductionExport("ProductionPrimitives.tsx", "ProductionSection");
  const ProductionNotice = await loadProductionExport("ProductionPrimitives.tsx", "ProductionNotice");
  const ProductionEmptyState = await loadProductionExport("ProductionPrimitives.tsx", "ProductionEmptyState");
  const ProductionIconButton = await loadProductionExport("ProductionPrimitives.tsx", "ProductionIconButton");
  function Gallery() {
    return createElement("main", { className: "production-component-gallery" },
      createElement(ProductionPageHeader, {
        eyebrow: "Component gallery",
        title: "Memories",
        description: "A single hierarchy shared by every production route.",
        actions: createElement(ProductionIconButton, { icon: "plus", label: "Add memory", tone: "primary" }),
      }),
      createElement(ProductionSection, {
        title: "Saved memories",
        description: "3 items",
        actions: createElement(ProductionIconButton, { icon: "refresh", label: "Refresh" }),
        children: createElement("div", null,
          createElement(ProductionNotice, { tone: "success", title: "Up to date", detail: "Last checked just now" }),
          createElement(ProductionNotice, { tone: "warning", title: "Working offline", detail: "Changes will sync later" }),
        ),
      }),
      createElement(ProductionEmptyState, {
        icon: "inbox",
        title: "Nothing here yet",
        detail: "Create the first item when you are ready.",
        action: createElement("button", { type: "button" }, "Create item"),
      }),
    );
  }
  const rendered = await renderComponent(Gallery, {});
  try {
    assert.equal(rendered.container.querySelectorAll("h1").length, 1);
    assert.equal(rendered.container.querySelectorAll(".production-section").length, 1);
    assert.equal(rendered.container.querySelectorAll(".production-notice").length, 2);
    assert.equal(rendered.container.querySelectorAll(".production-icon").length, 5);
    for (const button of rendered.container.querySelectorAll(".production-icon-button")) {
      assert.ok(button.getAttribute("aria-label"));
      assert.equal(button.getAttribute("aria-label"), button.getAttribute("title"));
    }
  } finally {
    await rendered.cleanup();
  }
});

test("production icon vocabulary is explicit and chrome/search do not draw one-off glyphs", async () => {
  const icons = await read("src/production/ProductionIcon.tsx");
  const chrome = await read("src/production/ProductionChrome.tsx");
  const primitives = await read("src/production/ProductionPrimitives.tsx");
  const styles = await read("src/production/styles.css");
  assert.match(icons, /Readonly<Record<ProductionIconName, LucideIcon>>/);
  assert.match(chrome, /<ProductionIcon className="nav-icon"/);
  assert.doesNotMatch(chrome, /<svg|<path|<circle|<rect/);
  assert.match(primitives, /<ProductionIcon name="search"/);
  assert.doesNotMatch(styles, /\.production-search-icon::after/);
  for (const file of ["HomeProduction.tsx", "MemoriesProduction.tsx", "TasksProduction.tsx", "ConversationsProduction.tsx"]) {
    const source = await read(`src/production/${file}`);
    assert.doesNotMatch(source, /[★☆☀◐○‹]|•••|>\+<|>×</u, `${file} uses the shared icon vocabulary`);
  }
  for (const file of ["home.css", "tasks.css", "conversations.css", "styles.css"]) {
    const source = await read(`src/production/${file}`);
    assert.doesNotMatch(source, /[★☆☀◐○‹]|Open Runde/u, `${file} uses semantic typography and icons`);
  }
});

test("named control collections expose groups and ready errors never advertise an unbound retry", async () => {
  const primitives = await read("src/production/ProductionPrimitives.tsx");
  const routes = await Promise.all([
    "ChatProduction.tsx",
    "MemoriesProduction.tsx",
    "MemoriesPlatformProduction.tsx",
    "TasksProduction.tsx",
    "ConversationsProduction.tsx",
    "SettingsProduction.tsx",
  ].map((file) => read(`src/production/${file}`)));
  assert.match(primitives, /production-filter-chips[^>]+role="group"/);
  for (const source of routes) {
    assert.doesNotMatch(source, /nextAction=\{[^\n]*\|\| operationError/);
  }
  for (const [file, className] of [
    ["HomeProduction.tsx", "home-kind-filter"],
    ["ListenProduction.tsx", "listen-controls"],
    ["ProductionChrome.tsx", "nav-utilities"],
    ["TasksProduction.tsx", "task-actions"],
    ["MemoriesProduction.tsx", "memory-actions"],
    ["ConversationsProduction.tsx", "conversation-row-actions"],
  ]) {
    const source = await read(`src/production/${file}`);
    assert.match(source, new RegExp(`className="${className}" role="group"`));
  }
});

test("every titled production route uses the shared page-header hierarchy", async () => {
  for (const file of [
    "ChatProduction.tsx",
    "MemoriesProduction.tsx",
    "MemoriesPlatformProduction.tsx",
    "TasksProduction.tsx",
    "ConversationsProduction.tsx",
    "FoldersProduction.tsx",
    "ListenProduction.tsx",
    "SettingsProduction.tsx",
  ]) {
    const source = await read(`src/production/${file}`);
    assert.match(source, /<ProductionPageHeader/, `${file} adopts the shared header`);
    assert.doesNotMatch(source, /<header className="(?:production-header|tasks-header|settings-header)/, `${file} has no parallel header implementation`);
  }
});
