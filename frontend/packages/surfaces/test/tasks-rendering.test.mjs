import assert from "node:assert/strict";
import test, { after } from "node:test";

import { EN_MESSAGES, t } from "@omi-core/i18n";
import {
  closeRenderHarness,
  loadProductionExport,
  renderComponent,
} from "./render-harness.mjs";

after(closeRenderHarness);

const translate = (key, vars) => t("en", key, vars);

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
