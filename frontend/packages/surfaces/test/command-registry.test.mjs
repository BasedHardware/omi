import assert from "node:assert/strict";
import test, { after } from "node:test";
import { createElement, useState } from "react";

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
    const actionButton = rendered.window.document.createElement("button");
    const actionLink = rendered.window.document.createElement("a");
    actionLink.href = "#task-action";
    rendered.container.append(actionButton, actionLink);
    const actionIcon = rendered.window.document.createElementNS("http://www.w3.org/2000/svg", "svg");
    actionLink.append(actionIcon);
    for (const [control, eventTarget] of [[actionButton, actionButton], [actionLink, actionIcon]]) {
      control.focus();
      const arrowFromControl = new rendered.window.KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true });
      eventTarget.dispatchEvent(arrowFromControl);
      assert.equal(
        dispatch(arrowFromControl, registry, { ...taskContext, handlers: { "navigate-task": () => calls.push("arrow") } }),
        false,
        "task arrows do not steal focus from buttons or links",
      );
      assert.equal(rendered.window.document.activeElement, control);
    }
    const dualPlatformModifier = new rendered.window.KeyboardEvent("keydown", { key: "k", metaKey: true, ctrlKey: true, bubbles: true });
    assert.equal(dispatch(dualPlatformModifier, registry, context), false, "Meta+Control together is not a platform chord");

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

    const textarea = rendered.window.document.createElement("textarea");
    rendered.container.append(textarea);
    const composingSend = new rendered.window.KeyboardEvent("keydown", { key: "Enter", isComposing: true, bubbles: true });
    textarea.dispatchEvent(composingSend);
    assert.equal(dispatch(composingSend, registry, chatContext), false, "IME composition Enter does not submit Chat");
    const composingSave = new rendered.window.KeyboardEvent("keydown", { key: "Enter", ctrlKey: true, isComposing: true, bubbles: true });
    textarea.dispatchEvent(composingSave);
    assert.equal(dispatch(composingSave, registry, {
      activeRoute: "memories",
      navigate: () => undefined,
      handlers: { "save-memory": () => calls.push("save") },
    }), false, "IME composition Enter does not save a memory");
    const legacyComposing = new rendered.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true });
    Object.defineProperty(legacyComposing, "keyCode", { configurable: true, value: 229 });
    textarea.dispatchEvent(legacyComposing);
    assert.equal(dispatch(legacyComposing, registry, chatContext), false, "legacy IME keyCode does not submit Chat");

    const repeatedSend = new rendered.window.KeyboardEvent("keydown", { key: "Enter", repeat: true, bubbles: true });
    textarea.dispatchEvent(repeatedSend);
    assert.equal(dispatch(repeatedSend, registry, chatContext), false, "held Enter does not repeatedly submit Chat");
    const repeatedCreate = new rendered.window.KeyboardEvent("keydown", { key: "n", ctrlKey: true, repeat: true, bubbles: true });
    assert.equal(dispatch(repeatedCreate, registry, taskContext), false, "held create chord does not create tasks repeatedly");
    const repeatedDelete = new rendered.window.KeyboardEvent("keydown", { key: "d", ctrlKey: true, repeat: true, bubbles: true });
    assert.equal(dispatch(repeatedDelete, registry, { ...taskContext, enabled: { "delete-task": true } }), false, "held delete chord does not delete tasks repeatedly");
    const repeatedPalette = new rendered.window.KeyboardEvent("keydown", { key: "p", ctrlKey: true, shiftKey: true, repeat: true, bubbles: true });
    assert.equal(dispatch(repeatedPalette, registry, { ...context, handlers: { "open-command-palette": () => calls.push("palette") } }), false, "held palette chord does not reopen repeatedly");
    const repeatedArrow = new rendered.window.KeyboardEvent("keydown", { key: "ArrowDown", repeat: true, bubbles: true });
    assert.equal(dispatch(repeatedArrow, registry, { ...taskContext, handlers: { "navigate-task": () => calls.push("arrow") } }), true, "task arrows explicitly allow keyboard repeat");
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
  const Fixture = () => createElement("main", { className: "production-shell", "data-production-shell": "true" },
    createElement(ProductionChrome, { locale: "en", active: "home", placement: "top" }),
    createElement("section", { className: "fixture-page" }, createElement("button", { type: "button" }, "Page action")),
    createElement(ProductionChrome, { locale: "en", active: "home", placement: "bottom" }),
  );
  const rendered = await renderComponent(Fixture, {});
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
    const primaryNav = rendered.container.querySelector(`nav[aria-label="${EN_MESSAGES["nav.primary"]}"]`);
    assert.equal(primaryNav?.getAttribute("aria-hidden"), "true", "modal help hides the background landmark");
    assert.equal(primaryNav?.inert, true, "modal help makes the background inert");
    assert.ok(dialog.textContent?.includes(EN_MESSAGES["chat.title"]));
    const dialogButtons = Array.from(dialog.querySelectorAll("button:not([disabled])"));
    const firstDialogButton = dialogButtons[0];
    const lastDialogButton = dialogButtons.at(-1);
    assert.ok(firstDialogButton && lastDialogButton);
    lastDialogButton.focus();
    await rendered.act(async () => {
      lastDialogButton.dispatchEvent(new rendered.window.KeyboardEvent("keydown", { key: "Tab", bubbles: true }));
    });
    assert.equal(rendered.window.document.activeElement, firstDialogButton, "forward Tab wraps within command help");
    firstDialogButton.focus();
    await rendered.act(async () => {
      firstDialogButton.dispatchEvent(new rendered.window.KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true }));
    });
    assert.equal(rendered.window.document.activeElement, lastDialogButton, "reverse Tab wraps within command help");
    const input = rendered.window.document.createElement("input");
    rendered.container.append(input);
    input.dispatchEvent(new rendered.window.KeyboardEvent("keydown", { key: "p", ctrlKey: true, shiftKey: true, bubbles: true }));
    assert.ok(rendered.container.querySelector('[role="dialog"]'), "palette chord is ignored while typing");
    await rendered.act(async () => {
      rendered.window.dispatchEvent(new rendered.window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    assert.equal(rendered.window.document.activeElement, trigger, "closing help restores trigger focus");
    const restoredPrimaryNav = rendered.container.querySelector(`nav[aria-label="${EN_MESSAGES["nav.primary"]}"]`);
    assert.equal(restoredPrimaryNav?.getAttribute("aria-hidden"), null, "closing help restores the background landmark");
    assert.equal(restoredPrimaryNav?.inert, false, "closing help restores background interaction");

    const mobileLabels = rendered.container.querySelector(".nav-mobile")?.textContent ?? "";
    for (const label of ["Home", "Conversations", "Tasks"]) assert.match(mobileLabels, new RegExp(label));
  } finally {
    await rendered.cleanup();
  }
});

test("modal command help isolates page controls and restores shell state on close paths", async () => {
  const ProductionChrome = await loadProductionExport("ProductionChrome.tsx", "ProductionChrome");
  const dispatch = await loadProductionExport("command-registry.ts", "dispatchProductionCommand");
  const createRegistry = await loadProductionExport("command-registry.ts", "createProductionCommandRegistry");
  let pageClicks = 0;
  let inputEvents = 0;
  let unmountTop = () => undefined;
  const Fixture = () => {
    const [showTop, setShowTop] = useState(true);
    unmountTop = () => setShowTop(false);
    return createElement("main", { className: "production-shell", "data-production-shell": "true" },
      showTop ? createElement(ProductionChrome, { locale: "en", active: "home", placement: "top" }) : null,
      createElement("section", { className: "fixture-page" },
        createElement("button", { type: "button", onClick: () => { pageClicks += 1; } }, "Page action"),
        createElement("input", { onInput: () => { inputEvents += 1; } }),
      ),
      createElement(ProductionChrome, { locale: "en", active: "home", placement: "bottom" }),
    );
  };
  const rendered = await renderComponent(Fixture, {});
  try {
    const shell = rendered.container.querySelector("[data-production-shell='true']");
    const page = shell?.querySelector(".fixture-page");
    const pageButton = page?.querySelector("button");
    const pageInput = page?.querySelector("input");
    const bottomNav = shell?.querySelector(".production-nav-bottom");
    const bottomLink = bottomNav?.querySelector("a");
    assert.ok(shell && page && pageButton && pageInput && bottomNav && bottomLink);
    const priorPageAria = "false";
    const priorPageInert = true;
    page.setAttribute("aria-hidden", priorPageAria);
    page.inert = priorPageInert;
    bottomNav.setAttribute("aria-hidden", "false");
    bottomNav.inert = true;
    bottomLink.addEventListener("click", () => { pageClicks += 1; });

    const trigger = rendered.container.querySelector("button.command-discovery-trigger");
    assert.ok(trigger);
    await rendered.act(async () => { trigger.click(); });
    const dialog = rendered.container.querySelector('[role="dialog"]');
    const topNav = rendered.container.querySelector(`nav[aria-label="${EN_MESSAGES["nav.primary"]}"]`);
    const backdrop = rendered.container.querySelector(".command-palette-backdrop");
    assert.ok(dialog && topNav && backdrop);
    assert.equal(page.getAttribute("aria-hidden"), "true");
    assert.equal(page.inert, true);
    assert.equal(bottomNav.getAttribute("aria-hidden"), "true");
    assert.equal(bottomNav.inert, true);
    assert.equal(topNav.getAttribute("aria-hidden"), "true");
    pageButton.click();
    pageInput.dispatchEvent(new rendered.window.Event("input", { bubbles: true, cancelable: true }));
    bottomLink.click();
    assert.equal(pageClicks, 0, "inert page and bottom navigation reject programmatic pointer activation");
    assert.equal(inputEvents, 0, "inert page rejects programmatic input events");
    pageInput.focus();
    assert.equal(rendered.window.document.activeElement, dialog, "focus cannot escape the modal shell");
    const blockedCommand = new rendered.window.KeyboardEvent("keydown", { key: "n", ctrlKey: true, bubbles: true });
    assert.equal(dispatch(blockedCommand, createRegistry(), {
      activeRoute: "tasks",
      navigate: () => undefined,
      handlers: { "new-task": () => { pageClicks += 1; } },
      paletteOpen: true,
    }), false, "background command dispatch is disabled while modal help is open");

    await rendered.act(async () => {
      rendered.window.dispatchEvent(new rendered.window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    assert.equal(page.getAttribute("aria-hidden"), priorPageAria);
    assert.equal(page.inert, priorPageInert);
    assert.equal(bottomNav.getAttribute("aria-hidden"), "false");
    assert.equal(bottomNav.inert, true);

    await rendered.act(async () => { trigger.click(); });
    const reopenedBackdrop = rendered.container.querySelector(".command-palette-backdrop");
    assert.ok(reopenedBackdrop);
    await rendered.act(async () => {
      reopenedBackdrop.dispatchEvent(new rendered.window.MouseEvent("mousedown", { bubbles: true }));
    });
    assert.equal(page.getAttribute("aria-hidden"), priorPageAria, "backdrop close restores page semantics");
    assert.equal(page.inert, priorPageInert, "backdrop close restores page inert state");

    await rendered.act(async () => { trigger.click(); });
    assert.ok(rendered.container.querySelector(".command-palette-backdrop"));
    await rendered.act(async () => { unmountTop(); });
    assert.equal(page.getAttribute("aria-hidden"), priorPageAria, "unmount restores page semantics");
    assert.equal(page.inert, priorPageInert, "unmount restores page inert state");
    assert.equal(bottomNav.getAttribute("aria-hidden"), "false", "unmount restores bottom nav semantics");
    assert.equal(bottomNav.inert, true, "unmount restores bottom nav inert state");
  } finally {
    await rendered.cleanup();
  }
});
