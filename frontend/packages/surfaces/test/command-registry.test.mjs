import assert from "node:assert/strict";
import test, { after } from "node:test";

import { EN_MESSAGES } from "@omi-core/i18n";
import {
  closeRenderHarness,
  loadProductionExport,
  renderComponent,
} from "./render-harness.mjs";

after(closeRenderHarness);

test("registry dispatches platform chords and preserves text-entry conflicts", async () => {
  const createRegistry = await loadProductionExport("command-registry.ts", "createProductionCommandRegistry");
  const dispatch = await loadProductionExport("command-registry.ts", "dispatchProductionCommand");
  const rendered = await renderComponent(() => null, {});
  try {
    const registry = createRegistry();
    const calls = [];
    const context = {
      activeRoute: "home",
      navigate: () => undefined,
      handlers: { "focus-home-search": () => calls.push("search") },
    };
    const input = rendered.window.document.createElement("input");
    rendered.container.append(input);
    const inField = new rendered.window.KeyboardEvent("keydown", { key: "k", metaKey: true, bubbles: true });
    input.dispatchEvent(inField);
    assert.equal(dispatch(inField, registry, context), true, "Command-K remains available in search text entry");
    assert.deepEqual(calls, ["search"]);

    const taskContext = {
      activeRoute: "tasks",
      navigate: () => undefined,
      handlers: { "new-task": () => calls.push("new") },
    };
    const textTask = new rendered.window.KeyboardEvent("keydown", { key: "n", ctrlKey: true, bubbles: true });
    input.dispatchEvent(textTask);
    assert.equal(dispatch(textTask, registry, taskContext), false, "task mutation chords do not steal text input");
    const outside = new rendered.window.KeyboardEvent("keydown", { key: "n", ctrlKey: true, bubbles: true });
    assert.equal(dispatch(outside, registry, taskContext), true);
    assert.deepEqual(calls, ["search", "new"]);

    const modifiedArrow = new rendered.window.KeyboardEvent("keydown", { key: "ArrowDown", shiftKey: true, bubbles: true });
    assert.equal(dispatch(modifiedArrow, registry, { ...taskContext, handlers: { "navigate-task": () => calls.push("arrow") } }), false, "modified arrows do not navigate tasks");

    const chatContext = {
      activeRoute: "chat",
      navigate: () => undefined,
      handlers: { "send-chat": () => calls.push("send") },
      enabled: { "send-chat": true },
    };
    const newline = new rendered.window.KeyboardEvent("keydown", { key: "Enter", shiftKey: true, bubbles: true });
    input.dispatchEvent(newline);
    assert.equal(dispatch(newline, registry, chatContext), false, "Shift-Enter remains a newline");
    const modifiedSend = new rendered.window.KeyboardEvent("keydown", { key: "Enter", ctrlKey: true, bubbles: true });
    input.dispatchEvent(modifiedSend);
    assert.equal(dispatch(modifiedSend, registry, chatContext), false, "extra modifiers do not submit Chat");
  } finally {
    await rendered.cleanup();
  }
});

test("disabled commands do not consume events and route commands cover every live route", async () => {
  const createRegistry = await loadProductionExport("command-registry.ts", "createProductionCommandRegistry");
  const dispatch = await loadProductionExport("command-registry.ts", "dispatchProductionCommand");
  const rendered = await renderComponent(() => null, {});
  try {
    const registry = createRegistry();
    const calls = [];
    const context = {
      activeRoute: "tasks",
      navigate: (route) => calls.push(route),
      handlers: { "delete-task": () => calls.push("deleted") },
      enabled: { "delete-task": false },
    };
    const disabled = new rendered.window.KeyboardEvent("keydown", { key: "d", metaKey: true, bubbles: true });
    assert.equal(dispatch(disabled, registry, context), false);
    assert.deepEqual(calls, []);

    for (const [id, route] of [
      ["navigate-home", "home"], ["navigate-memories", "memories"], ["navigate-conversations", "conversations"],
      ["navigate-folders", "folders"], ["navigate-tasks", "tasks"], ["navigate-chat", "chat"],
      ["navigate-settings", "settings"], ["navigate-listen", "listen"],
    ]) {
      const command = registry.find((candidate) => candidate.id === id);
      assert.ok(command, `${id} is registered`);
      command.invoke(context);
      assert.equal(calls.at(-1), route);
    }
  } finally {
    await rendered.cleanup();
  }
});

test("registry IDs stay unique and every integrated handler has one definition", async () => {
  const createRegistry = await loadProductionExport("command-registry.ts", "createProductionCommandRegistry");
  const registry = createRegistry();
  const ids = registry.map((command) => command.id);
  assert.equal(new Set(ids).size, ids.length, "command IDs are stable and unique");
  for (const id of [
    "focus-home-search", "new-task", "navigate-task", "delete-task", "indent-task", "outdent-task",
    "save-memory", "cancel-memory", "send-chat",
  ]) assert.ok(ids.includes(id), `${id} handler cannot drift outside the registry`);
});

test("command help exposes accurate landmarks, labels, chords, and focus restoration", async () => {
  const ProductionChrome = await loadProductionExport("ProductionChrome.tsx", "ProductionChrome");
  const rendered = await renderComponent(ProductionChrome, { locale: "en", active: "home", placement: "top" });
  try {
    const primary = rendered.container.querySelector(`nav[aria-label="${EN_MESSAGES["nav.primary"]}"]`);
    assert.ok(primary);
    const trigger = rendered.container.querySelector("button.command-discovery-trigger");
    assert.ok(trigger);
    assert.match(trigger.textContent ?? "", /Keyboard shortcuts/);
    await rendered.act(async () => {
      rendered.window.dispatchEvent(new rendered.window.KeyboardEvent("keydown", { key: "p", metaKey: true, shiftKey: true, bubbles: true }));
    });
    const dialog = rendered.container.querySelector('[role="dialog"]');
    assert.ok(dialog);
    assert.equal(rendered.window.document.activeElement, dialog, "opening help moves focus into the discovery surface");
    assert.ok(dialog.textContent?.includes(EN_MESSAGES["chat.title"]));
    const input = rendered.window.document.createElement("input");
    rendered.container.append(input);
    input.dispatchEvent(new rendered.window.KeyboardEvent("keydown", { key: "p", ctrlKey: true, shiftKey: true, bubbles: true }));
    assert.ok(rendered.container.querySelector('[role="dialog"]'), "palette chord is ignored while typing");
    await rendered.act(async () => {
      rendered.window.dispatchEvent(new rendered.window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    assert.equal(rendered.window.document.activeElement, trigger, "closing help restores trigger focus");

    const mobileLabels = rendered.container.querySelector(".nav-mobile")?.textContent ?? "";
    for (const label of ["Home", "Conversations", "Tasks"]) assert.match(mobileLabels, new RegExp(label));
  } finally {
    await rendered.cleanup();
  }
});
