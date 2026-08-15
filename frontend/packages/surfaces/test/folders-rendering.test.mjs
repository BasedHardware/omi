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
    assert.equal(badge, null, "live folders do not stamp a provenance pill");
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

test("Folders links preserve shell context while clearing obsolete detail and fixture state", async () => {
  const foldersConversationHref = await loadProductionExport("FoldersProduction.tsx", "foldersConversationHref");
  const context = "?theme=dark&locale=ar&platform=mobile&conversation=old&qa=folders&state=empty&folder=old";
  assert.equal(
    foldersConversationHref(context, "work-folder-one"),
    "?theme=dark&locale=ar&platform=mobile&route=conversations&folder=work-folder-one",
  );
  assert.equal(
    foldersConversationHref(context),
    "?theme=dark&locale=ar&platform=mobile&route=conversations",
  );
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
    assert.equal(
      main?.querySelector(".status-notice")?.textContent,
      EN_MESSAGES["lifecycle.savedFailed"],
    );
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

function folderStub(name) {
  return {
    async list() { return []; },
    status() { return { refresh: { phase: "ready", hasSavedData: false }, queue: { phase: "idle", pendingCount: 0 } }; },
    subscribe() { return () => {}; },
    async refresh() {},
    label: name,
  };
}

test("openFolderRouteSource on a platform selection never opens the legacy store", async () => {
  const openFolderRouteSource = await loadProductionExport("folder-sources.ts", "openFolderRouteSource");
  const calls = { folders: 0, platformFolders: 0 };
  const { foldersGeneration } = await openFolderRouteSource({
    selection: { memories: "platform", conversations: "platform", folders: "platform", tasks: "legacy" },
    async openFolders() { calls.folders += 1; return folderStub("legacy-folders"); },
    async openPlatformFolders() { calls.platformFolders += 1; return folderStub("platform-folders"); },
  });
  assert.equal(foldersGeneration, "platform");
  assert.deepEqual(calls, { folders: 0, platformFolders: 1 });
  // red-proof: routing Folders through openFolders() under a platform selection
  // hits the unpaginated legacy array this service dual-serves.
});

test("openFolderRouteSource on a legacy selection stays on the legacy store", async () => {
  const openFolderRouteSource = await loadProductionExport("folder-sources.ts", "openFolderRouteSource");
  const calls = { folders: 0, platformFolders: 0 };
  const { foldersGeneration } = await openFolderRouteSource({
    selection: { memories: "legacy", conversations: "legacy", folders: "legacy", tasks: "legacy" },
    async openFolders() { calls.folders += 1; return folderStub("legacy-folders"); },
    async openPlatformFolders() { calls.platformFolders += 1; return folderStub("platform-folders"); },
  });
  assert.equal(foldersGeneration, "legacy");
  assert.deepEqual(calls, { folders: 1, platformFolders: 0 });
});
