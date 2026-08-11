import assert from "node:assert/strict";
import test, { after } from "node:test";

import {
  closeRenderHarness,
  loadProductionExport,
  renderComponent,
} from "./render-harness.mjs";

after(closeRenderHarness);

async function settle(rendered) {
  await rendered.act(async () => {
    for (let index = 0; index < 8; index += 1) await Promise.resolve();
  });
}

test("polish fixture resolver exactly covers the immutable domain lifecycle map", async () => {
  const polishEvidenceStates = await loadProductionExport("polish-evidence-fixtures.ts", "polishEvidenceStates");
  const states = polishEvidenceStates();
  const resolvePolishFixture = await loadProductionExport("polish-evidence-fixtures.ts", "resolvePolishFixture");
  assert.deepEqual(states, {
    memories: ["loading", "empty", "ready", "error", "offline", "busy"],
    tasks: ["loading", "empty", "ready", "error", "offline", "busy", "complete"],
    conversations: ["loading", "empty", "ready", "error", "offline", "busy"],
    folders: ["loading", "empty", "ready", "error", "offline"],
    chat: ["loading", "empty", "ready", "error", "offline", "busy", "complete", "cancelled"],
    listen: ["loading", "empty", "ready", "error", "offline", "busy", "complete"],
    settings: ["loading", "empty", "ready", "error", "offline"],
  });
  assert.deepEqual(resolvePolishFixture("memories-platform", "offline"), {
    domain: "memories", state: "offline", fixture: "degraded",
  });
  assert.deepEqual(resolvePolishFixture("tasks", "complete"), {
    domain: "tasks", state: "complete", fixture: "complete",
  });
  assert.deepEqual(resolvePolishFixture("listen", "busy"), {
    domain: "listen", state: "busy", fixture: "busy",
  });
  assert.equal(resolvePolishFixture("folders", "cancelled"), null);
  assert.equal(resolvePolishFixture("unknown", "ready"), null);
});

test("folder polish fixtures expose truthful source and distinct lifecycle phases", async () => {
  const FoldersProduction = await loadProductionExport("FoldersProduction.tsx", "FoldersProduction");
  const fixtureFolderStore = await loadProductionExport("conversation-fixtures.ts", "fixtureFolderStore");
  for (const [state, phase] of [["loading", "initial-loading"], ["error", "unavailable"], ["offline", "saved-but-refresh-failed"], ["ready", "ready"]]) {
    const label = `polish:${state}`;
    const rendered = await renderComponent(FoldersProduction, {
      store: fixtureFolderStore(state),
      source: { kind: "fixture", fixture: label },
      fixture: label,
    });
    try {
      await settle(rendered);
      const main = rendered.container.querySelector('main[data-route="folders"]');
      assert.equal(main?.dataset.qaFixture, label);
      assert.equal(main?.querySelector(".data-source-badge")?.dataset.sourceKind, "fixture");
      assert.equal(main?.querySelector(".production-lifecycle-region")?.dataset.phase, phase);
    } finally {
      await rendered.cleanup();
    }
  }
});

test("Listen polish fixtures distinguish empty, ready, busy, offline, and completed transcript states", async () => {
  const ListenProduction = await loadProductionExport("ListenProduction.tsx", "ListenProduction");
  const fixtureListenStore = await loadProductionExport("listen-fixtures.ts", "fixtureListenStore");
  const expectations = {
    empty: ["idle", "0"],
    ready: ["idle", "1"],
    busy: ["capturing", "2"],
    offline: ["offline-buffering", "2"],
    complete: ["stopped-at-ceiling", "2"],
  };
  for (const [state, [capture, count]] of Object.entries(expectations)) {
    const label = `polish:${state}`;
    const rendered = await renderComponent(ListenProduction, {
      store: fixtureListenStore(state),
      source: { kind: "fixture", fixture: label },
      fixture: label,
    });
    try {
      await settle(rendered);
      const main = rendered.container.querySelector('main[data-route="listen"]');
      assert.equal(main?.dataset.qaFixture, label);
      assert.equal(main?.dataset.captureKind, capture);
      assert.equal(main?.dataset.consumerSemantic, `listen:capture:${capture}:segments:${count}`);
      assert.equal(main?.querySelector(".data-source-badge")?.dataset.sourceKind, "fixture");
    } finally {
      await rendered.cleanup();
    }
  }
});

test("task complete and Chat ready/complete fixtures are visually distinct facts", async () => {
  const fixtureTaskStore = await loadProductionExport("task-fixtures.ts", "fixtureStore");
  const completedTasks = await fixtureTaskStore("complete").list();
  assert.ok(completedTasks.length > 0);
  assert.ok(completedTasks.every((task) => task.completed && task.completedAt !== null));

  const fixtureChatStore = await loadProductionExport("chat-fixtures.ts", "fixtureChatStore");
  const ready = await fixtureChatStore("ready").history();
  const complete = await fixtureChatStore("normal").history();
  assert.equal(ready.messages.some((message) => message.agentRun?.state === "complete"), false);
  assert.equal(complete.messages.some((message) => message.agentRun?.state === "complete"), true);
});
