import assert from "node:assert/strict";
import test, { after } from "node:test";

import { EN_MESSAGES } from "@omi-core/i18n";
import {
  closeRenderHarness,
  loadProductionExport,
  renderComponent,
} from "./render-harness.mjs";

after(closeRenderHarness);

async function renderMemories(state = "normal", prepare) {
  const MemoriesProduction = await loadProductionExport("MemoriesProduction.tsx", "MemoriesProduction");
  const fixtureStore = await loadProductionExport("memory-fixtures.ts", "fixtureStore");
  const store = fixtureStore(state);
  if (prepare) await prepare(store);
  return renderComponent(MemoriesProduction, { store, fixture: state });
}

function setTextareaValue(rendered, textarea, value) {
  const setter = Object.getOwnPropertyDescriptor(rendered.window.HTMLTextAreaElement.prototype, "value")?.set;
  assert.ok(setter, "jsdom textarea value setter is available");
  setter.call(textarea, value);
  textarea.dispatchEvent(new rendered.window.Event("input", { bubbles: true }));
}

test("memory cards render provenance as metadata and classify only the body as long", async () => {
  const rendered = await renderMemories("normal", async (store) => {
    const [first] = await store.list();
    await store.patch(first.id, { content: `provenance-key: ${"a".repeat(235)}` });
  });
  try {
    const card = rendered.container.querySelector(".memory-card");
    assert.ok(card);
    assert.equal(card.getAttribute("data-long"), null, "a 235-character body is not long even when its prefix makes the stored value exceed 240");
    assert.equal(card.querySelector(".memory-provenance")?.textContent, "provenance-key:");
    assert.equal(card.querySelector(".memory-content")?.textContent, "a".repeat(235));
  } finally {
    await rendered.cleanup();
  }
});

test("memory create and edit affordances execute keyboard-safe form behavior", async () => {
  const rendered = await renderMemories();
  try {
    const create = rendered.container.querySelector("button.memory-create-trigger");
    assert.ok(create);
    assert.equal(create.getAttribute("aria-expanded"), "false");
    await rendered.act(async () => { create.click(); });
    assert.equal(create.getAttribute("aria-expanded"), "true");
    const form = rendered.container.querySelector("form.memory-create");
    const createDraft = form?.querySelector(`textarea[aria-label="${EN_MESSAGES["memories.create"]}"]`);
    assert.ok(form && createDraft);
    assert.equal(rendered.window.document.activeElement, createDraft);
    await rendered.act(async () => {
      setTextareaValue(rendered, createDraft, "Created through the rendered form");
    });
    await rendered.act(async () => {
      form.dispatchEvent(new rendered.window.Event("submit", { bubbles: true, cancelable: true }));
      await Promise.resolve();
    });
    assert.ok(rendered.container.textContent?.includes("Created through the rendered form"));
    assert.equal(rendered.container.querySelector("form.memory-create"), null);

    const edit = rendered.container.querySelector(`button[aria-label="${EN_MESSAGES["memories.edit"]}"]`);
    assert.ok(edit);
    await rendered.act(async () => { edit.click(); });
    const editor = rendered.container.querySelector(`textarea[aria-label="${EN_MESSAGES["memories.edit"]}"]`);
    assert.ok(editor);
    assert.equal(rendered.window.document.activeElement, editor);
    await rendered.act(async () => {
      editor.dispatchEvent(new rendered.window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    assert.equal(rendered.container.querySelector(`textarea[aria-label="${EN_MESSAGES["memories.edit"]}"]`), null);
  } finally {
    await rendered.cleanup();
  }
});

test("shared chrome mirrors the shipped destination hierarchy without fake content", async () => {
  const ProductionChrome = await loadProductionExport("ProductionChrome.tsx", "ProductionChrome");
  const rendered = await renderComponent(ProductionChrome, { locale: "en", active: "memories" });
  try {
    for (const icon of rendered.container.querySelectorAll("svg.nav-icon")) {
      assert.equal(icon.getAttribute("aria-hidden"), "true");
      assert.equal(icon.getAttribute("focusable"), "false");
    }
    const links = [...rendered.container.querySelectorAll("a")];
    assert.ok(links.every((link) => link.getAttribute("aria-disabled") === null), "navigation destinations are enabled links");
    const home = links.find((link) => link.textContent?.includes(EN_MESSAGES["nav.home"]));
    assert.ok(home?.getAttribute("href")?.includes("route=home"));
    const activeLinks = links.filter((link) => link.getAttribute("aria-current") === "page");
    assert.ok(activeLinks.length > 0);
    assert.ok(activeLinks.every((link) => /Library|Conversations/.test(link.textContent ?? "")));
    for (const shipped of [EN_MESSAGES["nav.apps"], EN_MESSAGES["nav.rewind"]]) {
      assert.equal(links.some((link) => link.textContent?.includes(shipped)), true);
    }
    const microphone = rendered.container.querySelector(`a.nav-icon-control[title="${EN_MESSAGES["nav.microphone"]}"]`);
    assert.ok(microphone?.getAttribute("href")?.includes("route=listen"));
    const screen = rendered.container.querySelector(`button.nav-icon-control[title="${EN_MESSAGES["nav.screenCapture"]}"]`);
    assert.equal(screen?.getAttribute("aria-disabled"), "true", "screen capture remains visibly parked");
  } finally {
    await rendered.cleanup();
  }
});
