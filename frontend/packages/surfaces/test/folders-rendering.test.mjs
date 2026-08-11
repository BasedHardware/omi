import assert from "node:assert/strict";
import test, { after } from "node:test";

import { EN_MESSAGES } from "@omi-core/i18n";
import {
  closeRenderHarness,
  loadProductionExport,
  renderComponent,
} from "./render-harness.mjs";

after(closeRenderHarness);

async function settle(rendered) {
  await rendered.act(async () => {
    for (let index = 0; index < 6; index += 1) await Promise.resolve();
  });
}

test("Folders exposes source, lifecycle, result semantics, and system-folder filtering", async () => {
  const FoldersProduction = await loadProductionExport("FoldersProduction.tsx", "FoldersProduction");
  const fixtureFolderStore = await loadProductionExport("conversation-fixtures.ts", "fixtureFolderStore");
  const rendered = await renderComponent(FoldersProduction, { store: fixtureFolderStore() });
  try {
    await settle(rendered);
    const main = rendered.container.querySelector('main[data-route="folders"]');
    assert.ok(main);
    const badge = main.querySelector(".data-source-badge");
    assert.equal(badge?.dataset.sourceKind, "live");
    assert.equal(badge?.getAttribute("aria-label"), badge?.textContent);
    const lifecycle = main.querySelector(".production-lifecycle-region");
    assert.equal(lifecycle?.getAttribute("aria-label"), EN_MESSAGES["lifecycle.region"]);
    assert.equal(lifecycle?.getAttribute("data-phase"), "ready");
    const list = main.querySelector(".folders-list");
    assert.equal(list?.getAttribute("aria-label"), EN_MESSAGES["nav.folders"]);
    assert.ok(list?.textContent?.includes("Work"));
    assert.equal(list?.textContent?.includes("Other"), false, "system folder is not presented as a user folder");
    assert.equal(list?.getAttribute("aria-live"), null, "list changes use the shared announcement instead");
    assert.equal(main.querySelectorAll('[data-live-region="true"]').length, 1);
    const row = list?.querySelector("a.folder-row");
    assert.equal(row?.getAttribute("href"), "?route=conversations&folder=work-folder-one");
    assert.ok(row?.textContent?.includes(EN_MESSAGES["folders.open"]));
    assert.ok(main.querySelector(".production-notice"), "the read-only journey is explicit rather than inert");
  } finally {
    await rendered.cleanup();
  }
});
test("Folders keeps saved rows visible when a later list read fails", async () => {
  const FoldersProduction = await loadProductionExport("FoldersProduction.tsx", "FoldersProduction");
  const fixtureFolderStore = await loadProductionExport("conversation-fixtures.ts", "fixtureFolderStore");
  const seed = fixtureFolderStore();
  const rows = await seed.list();
  let listCalls = 0;
  const store = {
    status: () => ({ refresh: { phase: "ready", hasSavedData: true }, queue: { phase: "idle", pendingCount: 0 } }),
    subscribe: () => () => {},
    async refresh() {},
    async list() {
      listCalls += 1;
      if (listCalls > 1) throw new Error("saved projection read failed");
      return rows;
    },
  };
  const rendered = await renderComponent(FoldersProduction, { store });
  try {
    await settle(rendered);
    const main = rendered.container.querySelector('main[data-route="folders"]');
    assert.equal(main?.querySelector(".production-lifecycle-region")?.getAttribute("data-phase"), "saved-but-refresh-failed");
    assert.ok(main?.querySelector(".folders-list")?.textContent?.includes("Work"));
    assert.ok(main?.querySelector(".lifecycle-retry"), "saved failure leaves an actionable retry");
    assert.equal(main?.querySelector('[data-empty-kind]'), null, "saved rows are not replaced by an empty claim");
  } finally {
    await rendered.cleanup();
  }
});

test("Folders empty state leads to the complete conversation list", async () => {
  const FoldersProduction = await loadProductionExport("FoldersProduction.tsx", "FoldersProduction");
  const store = {
    status: () => ({ refresh: { phase: "ready", hasSavedData: false }, queue: { phase: "idle", pendingCount: 0 } }),
    subscribe: () => () => {},
    async refresh() {},
    async list() { return []; },
  };
  const rendered = await renderComponent(FoldersProduction, { store });
  try {
    await settle(rendered);
    const empty = rendered.container.querySelector(".production-empty-state");
    assert.ok(empty?.textContent?.includes(EN_MESSAGES["folders.emptyTitle"]));
    assert.equal(empty?.querySelector("a")?.getAttribute("href"), "?route=conversations");
  } finally {
    await rendered.cleanup();
  }
});
