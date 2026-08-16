import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test, { after } from "node:test";
import { fileURLToPath } from "node:url";

import { PlatformTasksStore } from "@omi-core/domain";
import { EN_MESSAGES, t } from "@omi-core/i18n";
import {
  closeRenderHarness,
  loadProductionExport,
  renderComponent,
} from "./render-harness.mjs";

after(closeRenderHarness);

const translate = (key, vars) => t("en", key, vars);

function setTextareaValue(rendered, textarea, value) {
  const setter = Object.getOwnPropertyDescriptor(rendered.window.HTMLTextAreaElement.prototype, "value")?.set;
  assert.ok(setter, "jsdom textarea value setter is available");
  setter.call(textarea, value);
  textarea.dispatchEvent(new rendered.window.Event("input", { bubbles: true }));
}

test("TasksProduction renders shared chrome, translated affordances, and accessible task flows", async () => {
  const TasksProduction = await loadProductionExport("TasksProduction.tsx", "TasksProduction");
  const fixtureStore = await loadProductionExport("task-fixtures.ts", "fixtureStore");
  const baseStore = fixtureStore("normal");
  const patches = [];
  const deletes = [];
  const store = {
    ...baseStore,
    async patch(id, patch) {
      patches.push({ id, patch });
      await baseStore.patch(id, patch);
    },
    async delete(id) {
      deletes.push(id);
      await baseStore.delete(id);
    },
  };
  let readyCount = 0;
  const rendered = await renderComponent(TasksProduction, {
    store,
    fixture: "normal",
    translate,
    now: Date.UTC(2026, 7, 7, 12, 0, 0),
    onReady: () => { readyCount += 1; },
  });

  try {
    const shell = rendered.container.querySelector("main.tasks-production-shell[data-route=tasks]");
    assert.ok(shell);
    assert.equal(readyCount, 1, "the rendered boot calls onReady exactly once");
    assert.equal(rendered.container.querySelectorAll("nav.production-nav").length, 2, "top and bottom shared chrome render");

    const shortcuts = rendered.container.querySelector(".tasks-shortcuts");
    assert.ok(shortcuts);
    for (const key of ["tasks.shortcutNew", "tasks.shortcutDelete", "tasks.shortcutIndent", "tasks.shortcutOutdent"]) {
      assert.ok(shortcuts.textContent?.includes(EN_MESSAGES[key]), `${key} renders translated copy`);
    }
    const fab = rendered.container.querySelector("button.tasks-mobile-fab");
    assert.ok(fab);
    assert.equal(fab.getAttribute("aria-expanded"), "false");

    const cards = [...rendered.container.querySelectorAll("article.task-card")];
    assert.ok(cards.length >= 2);
    assert.equal(cards[0].tabIndex, 0);
    assert.match(cards[0].getAttribute("data-indent-level") ?? "", /^[0-3]$/);
    const counts = [...rendered.container.querySelectorAll(".tasks-group-count")].map((node) => Number(node.textContent));
    assert.equal(counts.reduce((sum, count) => sum + count, 0), cards.length, "rendered group counts sum to rendered rows");
    assert.ok(rendered.container.querySelector(".tasks-group-overdue")?.textContent?.includes(EN_MESSAGES["tasks.overdue"]));
    assert.ok(rendered.container.querySelector(".tasks-group-noDeadline")?.textContent?.includes(EN_MESSAGES["tasks.noDeadline"]));
    assert.equal(rendered.container.querySelectorAll(".tasks-group-empty").length, 0, "empty urgency groups do not add visual noise");
    assert.ok(rendered.container.textContent?.includes(EN_MESSAGES["tasks.dueDateHint"]), "date intent is explicit");

    await rendered.act(async () => {
      rendered.window.dispatchEvent(new rendered.window.KeyboardEvent("keydown", { key: "]", metaKey: true, bubbles: true }));
    });
    assert.equal(patches.length, 0, "indent shortcut does nothing before a task is selected");

    await rendered.act(async () => { cards[0].focus(); });
    assert.equal(cards[0].classList.contains("is-selected"), true);
    await rendered.act(async () => {
      cards[0].dispatchEvent(new rendered.window.KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    });
    assert.equal(rendered.window.document.activeElement, cards[1], "ArrowDown moves focus to the next rendered task");

    const selectedId = cards[1].getAttribute("data-task-id");
    await rendered.act(async () => {
      rendered.window.dispatchEvent(new rendered.window.KeyboardEvent("keydown", { key: "]", metaKey: true, bubbles: true }));
      await Promise.resolve();
    });
    assert.equal(patches.at(-1)?.id, selectedId, "indent shortcut mutates only the selected task");
    assert.equal(patches.at(-1)?.patch.indentLevel, 1, "Command-] indents by one level");

    await rendered.act(async () => {
      rendered.window.dispatchEvent(new rendered.window.KeyboardEvent("keydown", { key: "]", ctrlKey: true, bubbles: true }));
      await Promise.resolve();
    });
    assert.equal(patches.at(-1)?.patch.indentLevel, 2, "Control-] indents by one level");

    await rendered.act(async () => {
      rendered.window.dispatchEvent(new rendered.window.KeyboardEvent("keydown", { key: "[", ctrlKey: true, bubbles: true }));
      await Promise.resolve();
    });
    assert.equal(patches.at(-1)?.patch.indentLevel, 1, "Control-[ outdents by one level");

    await rendered.act(async () => {
      rendered.window.dispatchEvent(new rendered.window.KeyboardEvent("keydown", { key: "[", metaKey: true, bubbles: true }));
      await Promise.resolve();
    });
    assert.equal(patches.at(-1)?.patch.indentLevel, 0, "Command-[ outdents by one level");
    const lowerClampPatchCount = patches.length;
    await rendered.act(async () => {
      rendered.window.dispatchEvent(new rendered.window.KeyboardEvent("keydown", { key: "[", metaKey: true, bubbles: true }));
      await Promise.resolve();
    });
    assert.equal(patches.length, lowerClampPatchCount, "outdent clamps at level zero without a redundant patch");

    for (const expectedLevel of [1, 2, 3]) {
      await rendered.act(async () => {
        rendered.window.dispatchEvent(new rendered.window.KeyboardEvent("keydown", { key: "]", ctrlKey: true, bubbles: true }));
        await Promise.resolve();
      });
      assert.equal(patches.at(-1)?.patch.indentLevel, expectedLevel, `Control-] reaches level ${expectedLevel}`);
    }
    const upperClampPatchCount = patches.length;
    await rendered.act(async () => {
      rendered.window.dispatchEvent(new rendered.window.KeyboardEvent("keydown", { key: "]", ctrlKey: true, bubbles: true }));
      await Promise.resolve();
    });
    assert.equal(patches.length, upperClampPatchCount, "indent clamps at level three without a redundant patch");

    const add = rendered.container.querySelector("button.tasks-add-trigger");
    assert.ok(add);
    for (const modifier of [{ ctrlKey: true, name: "Control" }, { metaKey: true, name: "Command" }]) {
      await rendered.act(async () => {
        rendered.window.dispatchEvent(new rendered.window.KeyboardEvent("keydown", {
          key: "n",
          bubbles: true,
          [modifier.ctrlKey ? "ctrlKey" : "metaKey"]: true,
        }));
        await new Promise((resolve) => rendered.window.requestAnimationFrame(resolve));
      });
      assert.equal(add.getAttribute("aria-expanded"), "true", `${modifier.name}-N opens task creation`);
      assert.equal(
        rendered.window.document.activeElement,
        rendered.container.querySelector(`textarea[aria-label="${EN_MESSAGES["tasks.newTask"]}"]`),
        `${modifier.name}-N focuses the task draft`,
      );
      await rendered.act(async () => { add.click(); });
      assert.equal(add.getAttribute("aria-expanded"), "false");
    }

    const search = rendered.container.querySelector('input[type="search"]');
    assert.ok(search);
    search.focus();
    for (const modifier of [{ metaKey: true }, { ctrlKey: true }]) {
      await rendered.act(async () => {
        search.dispatchEvent(new rendered.window.KeyboardEvent("keydown", { key: "n", bubbles: true, ...modifier }));
      });
      assert.equal(add.getAttribute("aria-expanded"), "false", "Command/Control-N is ignored inside inputs");
    }

    await rendered.act(async () => {
      add.click();
      await new Promise((resolve) => rendered.window.requestAnimationFrame(resolve));
    });
    assert.equal(add.getAttribute("aria-expanded"), "true");
    const draft = rendered.container.querySelector(`textarea[aria-label="${EN_MESSAGES["tasks.newTask"]}"]`);
    assert.equal(rendered.window.document.activeElement, draft, "opening create moves focus to the draft");

    const edit = cards[0].querySelector(`button[aria-label="${EN_MESSAGES["common.edit"]}"]`);
    assert.ok(edit);
    await rendered.act(async () => { edit.click(); });
    assert.match(cards[0].querySelector('input[type="date"]')?.value ?? "", /^\d{4}-\d{2}-\d{2}$/);

    const previousConfirm = Object.getOwnPropertyDescriptor(globalThis, "confirm");
    Object.defineProperty(globalThis, "confirm", { configurable: true, value: () => true });
    try {
      cards[1].focus();
      await rendered.act(async () => {
        rendered.window.dispatchEvent(new rendered.window.KeyboardEvent("keydown", { key: "d", metaKey: true, bubbles: true }));
        await Promise.resolve();
      });
      assert.equal(deletes.at(-1), selectedId, "delete shortcut mutates only the selected task");
    } finally {
      if (previousConfirm) Object.defineProperty(globalThis, "confirm", previousConfirm);
      else Reflect.deleteProperty(globalThis, "confirm");
    }
    // red-proof: removing Control modifiers, the `[` branch, either clamp, or
    // the global Meta/Control-N branch fails the rendered shortcut assertions.
  } finally {
    await rendered.cleanup();
  }
});

test("Tasks empty state starts a focused first task", async () => {
  const TasksProduction = await loadProductionExport("TasksProduction.tsx", "TasksProduction");
  const fixtureStore = await loadProductionExport("task-fixtures.ts", "fixtureStore");
  const rendered = await renderComponent(TasksProduction, {
    store: fixtureStore("empty"),
    fixture: "empty",
    translate,
    now: Date.UTC(2026, 7, 7, 12, 0, 0),
  });
  try {
    const empty = rendered.container.querySelector('[data-empty-kind="empty-projection"] .production-empty-state');
    assert.ok(empty?.textContent?.includes(EN_MESSAGES["tasks.emptyTitle"]));
    const action = empty.querySelector("button");
    assert.equal(action?.textContent, EN_MESSAGES["tasks.newTask"]);
    await rendered.act(async () => {
      action.click();
      await new Promise((resolve) => rendered.window.requestAnimationFrame(resolve));
    });
    const draft = rendered.container.querySelector(`textarea[aria-label="${EN_MESSAGES["tasks.newTask"]}"]`);
    assert.equal(rendered.window.document.activeElement, draft);
    assert.equal(rendered.container.querySelector(".tasks-create")?.classList.contains("is-open"), true);
  } finally {
    await rendered.cleanup();
  }
});

test("Tasks create, edit, and complete each render on the card", async () => {
  // red-proof: if add() never reloads, or TaskCard ignores the patched
  // description/completed flags, this fails at the card the user sees.
  const TasksProduction = await loadProductionExport("TasksProduction.tsx", "TasksProduction");
  const fixtureStore = await loadProductionExport("task-fixtures.ts", "fixtureStore");
  const store = fixtureStore("empty");
  const rendered = await renderComponent(TasksProduction, {
    store,
    fixture: "empty",
    translate,
    now: Date.UTC(2026, 7, 7, 12, 0, 0),
  });
  try {
    const start = rendered.container.querySelector('[data-empty-kind="empty-projection"] button');
    assert.ok(start);
    await rendered.act(async () => {
      start.click();
      await new Promise((resolve) => rendered.window.requestAnimationFrame(resolve));
    });
    const draft = rendered.container.querySelector(`textarea[aria-label="${EN_MESSAGES["tasks.newTask"]}"]`);
    assert.ok(draft);
    await rendered.act(async () => {
      draft.focus();
      setTextareaValue(rendered, draft, "round-trip created task");
    });
    const add = [...rendered.container.querySelectorAll("button")].find((button) => button.textContent === EN_MESSAGES["tasks.add"]);
    assert.ok(add);
    assert.equal(add.disabled, false, "create enables once the draft has text");
    await rendered.act(async () => {
      add.click();
      for (let index = 0; index < 8; index += 1) await Promise.resolve();
    });
    let card = rendered.container.querySelector("article.task-card");
    assert.ok(card, "created task must render as a card");
    assert.match(card.querySelector(".task-description")?.textContent ?? "", /round-trip created task/);

    const edit = card.querySelector(`button[aria-label="${EN_MESSAGES["common.edit"]}"]`);
    assert.ok(edit);
    await rendered.act(async () => { edit.click(); });
    const editor = card.querySelector("textarea.task-editor");
    assert.ok(editor);
    await rendered.act(async () => {
      editor.focus();
      setTextareaValue(rendered, editor, "round-trip edited task");
    });
    const save = [...card.querySelectorAll("button")].find((button) => button.textContent === EN_MESSAGES["common.save"]);
    assert.ok(save);
    await rendered.act(async () => {
      save.click();
      for (let index = 0; index < 8; index += 1) await Promise.resolve();
    });
    card = rendered.container.querySelector("article.task-card");
    assert.match(card?.querySelector(".task-description")?.textContent ?? "", /round-trip edited task/);

    const check = card.querySelector("button.task-check");
    assert.ok(check);
    await rendered.act(async () => {
      check.click();
      for (let index = 0; index < 8; index += 1) await Promise.resolve();
    });
    card = rendered.container.querySelector("article.task-card");
    assert.equal(card?.classList.contains("is-completed"), true, "completed task must render as completed");
    assert.equal(card?.querySelector("button.task-check")?.getAttribute("aria-pressed"), "true");
  } finally {
    await rendered.cleanup();
  }
});

test("Tasks treats an earlier due time today as overdue", async () => {
  const TasksProduction = await loadProductionExport("TasksProduction.tsx", "TasksProduction");
  const fixtureStore = await loadProductionExport("task-fixtures.ts", "fixtureStore");
  const now = Date.UTC(2026, 7, 7, 12, 0, 0);
  const store = fixtureStore("normal", now);
  const rows = await store.list();
  const task = rows.find((row) => row.dueAt !== null && row.dueAt > now);
  assert.ok(task, "fixture exposes a future task that can cross the same-day boundary");
  await store.patch(task.id, { dueAt: now - 60 * 60 * 1000 });

  const rendered = await renderComponent(TasksProduction, {
    store,
    fixture: "normal",
    translate,
    now,
  });
  try {
    const overdue = rendered.container.querySelector(".tasks-group-overdue");
    const today = rendered.container.querySelector(".tasks-group-today");
    assert.ok(overdue?.textContent?.includes(task.description));
    assert.equal(today?.textContent?.includes(task.description) ?? false, false);
  } finally {
    await rendered.cleanup();
  }
});

test("Tasks arrow navigation preserves focus on nested controls and shell links", async () => {
  const TasksProduction = await loadProductionExport("TasksProduction.tsx", "TasksProduction");
  const fixtureStore = await loadProductionExport("task-fixtures.ts", "fixtureStore");

  const assertArrowDoesNotLeave = async (rendered, control, eventTarget = control, key) => {
    await rendered.act(async () => { control.focus(); });
    const before = rendered.window.document.activeElement;
    assert.equal(before, control);
    const event = new rendered.window.KeyboardEvent("keydown", { key, bubbles: true, cancelable: true });
    event.preventDefault();
    eventTarget.dispatchEvent(event);
    await Promise.resolve();
    assert.equal(rendered.window.document.activeElement, control, `${key} does not steal focus from an interactive control`);
  };

  const renderFixture = async (fixture) => renderComponent(TasksProduction, {
    store: fixtureStore(fixture),
    fixture,
    translate,
    now: Date.UTC(2026, 7, 7, 12, 0, 0),
  });

  const normal = await renderFixture("normal");
  try {
    const firstCard = normal.container.querySelector("article.task-card");
    assert.ok(firstCard);
    const nestedControls = [
      firstCard.querySelector(".task-check"),
      firstCard.querySelector(`button[aria-label="${EN_MESSAGES["common.edit"]}"]`),
      firstCard.querySelector(`button[aria-label="${EN_MESSAGES["common.delete"]}"]`),
      normal.container.querySelector("button.tasks-add-trigger"),
      normal.container.querySelector(".production-nav-bottom a"),
    ];
    for (const control of nestedControls) {
      assert.ok(control, "fixture exposes the expected action control");
      const target = control.matches("a") ? control.querySelector("svg") : control;
      assert.ok(target, "interactive control has an event target");
      for (const key of ["ArrowUp", "ArrowDown"]) await assertArrowDoesNotLeave(normal, control, target, key);
    }
  } finally {
    await normal.cleanup();
  }

  const long = await renderFixture("long");
  try {
    const showMore = long.container.querySelector("button[aria-expanded]");
    assert.ok(showMore, "long fixture exposes a show-more action");
    for (const key of ["ArrowUp", "ArrowDown"]) await assertArrowDoesNotLeave(long, showMore, showMore, key);
  } finally {
    await long.cleanup();
  }

  const retry = await renderFixture("saved-failed");
  try {
    const retryButton = retry.container.querySelector(`button[aria-label="${EN_MESSAGES["common.retry"]}"]`);
    assert.ok(retryButton, "saved-failed fixture exposes a retry action");
    for (const key of ["ArrowUp", "ArrowDown"]) await assertArrowDoesNotLeave(retry, retryButton, retryButton, key);
  } finally {
    await retry.cleanup();
  }
});

function taskRouteStub(name) {
  return {
    async list() { return []; },
    status() { return { refresh: { phase: "ready", hasSavedData: false }, queue: { phase: "idle", pendingCount: 0 } }; },
    subscribe() { return () => {}; },
    async refresh() {},
    async deadLetters() { return []; },
    async discardDeadLetter() {},
    async create() {},
    async patch() {},
    async delete() {},
    label: name,
  };
}

test("openTaskRouteSource opens the platform store", async () => {
  const openTaskRouteSource = await loadProductionExport("task-sources.ts", "openTaskRouteSource");
  const calls = { platformTasks: 0 };
  const { tasksGeneration } = await openTaskRouteSource({
    selection: { memories: "platform", conversations: "platform", folders: "platform", tasks: "platform" },
    async openPlatformTasks() { calls.platformTasks += 1; return taskRouteStub("platform-tasks"); },
  });
  assert.equal(tasksGeneration, "platform");
  assert.deepEqual(calls, { platformTasks: 1 });
  // red-proof: routing Tasks through a retired openTasks() port would keep
  // the last surface on a wire nothing serves.
});

test("a refused task write keeps the list and does not claim the view failed to load", async () => {
  const TasksProduction = await loadProductionExport("TasksProduction.tsx", "TasksProduction");
  const fixtureStore = await loadProductionExport("task-fixtures.ts", "fixtureStore");
  const baseStore = fixtureStore("normal");
  const store = {
    ...baseStore,
    async patch() {
      throw new Error("platform task write refused: opaque read handle has no write id");
    },
  };
  const rendered = await renderComponent(TasksProduction, {
    store,
    fixture: "normal",
    translate,
    now: Date.UTC(2026, 7, 7, 12, 0, 0),
  });
  try {
    const cardsBefore = rendered.container.querySelectorAll("article.task-card").length;
    assert.ok(cardsBefore > 0);
    const check = rendered.container.querySelector("button.task-check");
    assert.ok(check);
    await rendered.act(async () => { check.click(); });
    assert.equal(rendered.container.querySelectorAll("article.task-card").length, cardsBefore);
    const banner = rendered.container.querySelector(".production-operation-error");
    assert.equal(banner?.textContent, EN_MESSAGES["dead.body"]);
    assert.notEqual(banner?.textContent, EN_MESSAGES["lifecycle.error"]);
  } finally {
    await rendered.cleanup();
  }
});

test("checking a seeded task marks it complete and keeps it complete after refresh", async () => {
  // Rendered-layer proof through PlatformTasksStore, not a fixture that
  // always succeeds on patch. red-proof: drop the listed-handle branch in
  // assertWritableId. Click then paints dead.body / lifecycle.error and the
  // card stays open. APPLIED AND OBSERVED RED.
  const TasksProduction = await loadProductionExport("TasksProduction.tsx", "TasksProduction");
  const seededDescription = "Pack rain shells for the Cedar Loop hike";
  const env = new ManualEnv();
  const { http, store } = await openSeededPlatformStore(env, seededDescription);
  const rendered = await renderComponent(TasksProduction, {
    store,
    translate,
    now: Date.UTC(2026, 7, 7, 12, 0, 0),
    calendarDay: (timestamp) => new Date(timestamp).toISOString().slice(0, 10),
    formatDate: (timestamp) => new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeZone: "UTC" }).format(new Date(timestamp)),
  });
  try {
    const card = [...rendered.container.querySelectorAll("article.task-card")]
      .find((node) => node.textContent?.includes(seededDescription));
    assert.ok(card, "seeded task renders");
    assert.equal(card.classList.contains("is-completed"), false);
    const check = card.querySelector("button.task-check");
    assert.ok(check);
    await rendered.act(async () => { check.click(); });
    await rendered.act(async () => { await env.advance(10); });
    const completed = [...rendered.container.querySelectorAll("article.task-card")]
      .find((node) => node.textContent?.includes(seededDescription));
    assert.ok(completed);
    assert.equal(completed.classList.contains("is-completed"), true);
    assert.equal(completed.querySelector("button.task-check")?.getAttribute("aria-pressed"), "true");
    const posted = http.calls.find((call) => call.method === "POST");
    assert.equal(posted?.path, "/v1/tasks/ops");
    assert.match(String(posted?.body?.op?.record_id ?? ""), /^task1_[a-f0-9]{64}$/);
    await rendered.act(async () => { await store.refresh(); });
    const afterRefresh = [...rendered.container.querySelectorAll("article.task-card")]
      .find((node) => node.textContent?.includes(seededDescription));
    assert.ok(afterRefresh);
    assert.equal(afterRefresh.classList.contains("is-completed"), true);
    assert.equal(rendered.container.querySelector(".production-operation-error"), null);
    assert.equal(rendered.container.textContent?.includes(EN_MESSAGES["lifecycle.error"]), false);
  } finally {
    await rendered.cleanup();
  }
});

function corpusPage(wireCase) {
  const rows = JSON.parse(readFileSync(resolve(
    dirname(fileURLToPath(import.meta.url)),
    "../../../contracts/ratified/fixtures/tasks-read-conformance.json",
  ), "utf8"));
  const row = rows.find((entry) => entry.wireCase === wireCase);
  assert.ok(row, `corpus row ${wireCase} is missing`);
  return structuredClone(row.page);
}

function okPage(page) {
  return { status: 200, json: page, text: JSON.stringify(page) };
}

async function openSeededPlatformStore(env, description) {
  const open = corpusPage("window:complete_terminal");
  open.accountEpoch = 7;
  open.items[0] = {
    ...open.items[0],
    description,
    completed: false,
    completedAt: null,
  };
  const after = structuredClone(open);
  after.items[0] = {
    ...after.items[0],
    completed: true,
    completedAt: Date.UTC(2026, 7, 7, 12, 0, 0),
    revision: "b".repeat(64),
  };
  const revision = "c".repeat(64);
  const http = new ScriptedHttp([
    okPage(open),
    {
      status: 200,
      json: { applied: { record_id: "demo-task-cedar-shells", revision }, idempotent: false },
      text: JSON.stringify({ applied: { record_id: "demo-task-cedar-shells", revision }, idempotent: false }),
    },
    okPage(after),
  ]);
  const store = await PlatformTasksStore.open(new MemoryStore().openBridge("u1"), env, http);
  return { http, store };
}

class ScriptedHttp {
  constructor(queue) {
    this.queue = queue;
    this.calls = [];
  }
  async request(method, path, body) {
    this.calls.push(body === undefined ? { method, path } : { method, path, body });
    const next = this.queue.shift();
    if (!next) throw new Error("unscripted request");
    return next;
  }
}

class MemoryStore {
  constructor() {
    this.logs = new Map();
    this.kvs = new Map();
    this.generations = new Map();
  }
  openBridge(uid) {
    const generation = (this.generations.get(uid) ?? 0) + 1;
    this.generations.set(uid, generation);
    const ns = (name) => `${uid}::${name}`;
    return {
      uid,
      generation,
      openLog: async (name) => {
        const key = ns(name);
        if (!this.logs.has(key)) this.logs.set(key, { lsn: 0, entries: [] });
        const log = this.logs.get(key);
        return {
          append: async (payload) => {
            log.lsn += 1;
            log.entries.push({ lsn: log.lsn, payload });
            return log.lsn;
          },
          scan: async (after) => log.entries.filter((entry) => entry.lsn > after),
          truncate: async (upTo) => {
            log.entries = log.entries.filter((entry) => entry.lsn > upTo);
          },
        };
      },
      openKv: async (name) => {
        const key = ns(name);
        if (!this.kvs.has(key)) this.kvs.set(key, new Map());
        const kv = this.kvs.get(key);
        return {
          get: async (k) => kv.get(k) ?? null,
          set: async (k, v) => void kv.set(k, v),
          delete: async (k) => void kv.delete(k),
        };
      },
      destroyAll: async () => {
        for (const key of [...this.logs.keys()]) if (key.startsWith(`${uid}::`)) this.logs.delete(key);
        for (const key of [...this.kvs.keys()]) if (key.startsWith(`${uid}::`)) this.kvs.delete(key);
      },
    };
  }
}

class ManualEnv {
  constructor() {
    this.t = 1_000_000;
    this.seed = 42;
    this.timers = [];
    this.fallbackSink = { records: [], record(event) { this.records.push(event); } };
  }
  now() { return this.t; }
  random() {
    this.seed ^= this.seed << 13;
    this.seed ^= this.seed >>> 17;
    this.seed ^= this.seed << 5;
    return (this.seed >>> 0) / 0xffffffff;
  }
  delay(ms, fn) {
    const timer = { at: this.t + ms, fn, cancelled: false };
    this.timers.push(timer);
    return () => { timer.cancelled = true; };
  }
  async advance(ms) {
    const target = this.t + ms;
    for (;;) {
      const due = this.timers.filter((timer) => !timer.cancelled && timer.at <= target).sort((a, b) => a.at - b.at)[0];
      if (!due) break;
      this.t = due.at;
      this.timers = this.timers.filter((timer) => timer !== due);
      due.fn();
      for (let i = 0; i < 50; i++) await Promise.resolve();
    }
    this.t = target;
    for (let i = 0; i < 50; i++) await Promise.resolve();
  }
}
