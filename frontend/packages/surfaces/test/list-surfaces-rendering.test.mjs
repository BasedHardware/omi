import assert from "node:assert/strict";
import test, { after } from "node:test";

import { EN_MESSAGES, t } from "@omi-core/i18n";
import {
  closeRenderHarness,
  loadProductionExport,
  renderComponent,
} from "./render-harness.mjs";

after(closeRenderHarness);

async function setInputValue(rendered, input, value) {
  const setter = Object.getOwnPropertyDescriptor(rendered.window.HTMLInputElement.prototype, "value")?.set;
  assert.ok(setter, "jsdom input value setter is available");
  await rendered.act(async () => {
    setter.call(input, value);
    input.dispatchEvent(new rendered.window.Event("input", { bubbles: true }));
    await Promise.resolve();
  });
}

function assertTrueEmpty(rendered, title, body) {
  const empty = rendered.container.querySelector('[data-empty-kind="empty-projection"]');
  assert.ok(empty, "ready zero-row fixture renders true-empty");
  assert.ok(empty.textContent?.includes(title), `true-empty includes title: ${title}`);
  assert.ok(empty.textContent?.includes(body), `true-empty includes body: ${body}`);
  assert.equal(empty.textContent?.includes(EN_MESSAGES["common.noResults"]), false);
}

test("MemoriesProduction renders loading, true-empty, and filter-miss as distinct DOM states", async () => {
  const MemoriesProduction = await loadProductionExport("MemoriesProduction.tsx", "MemoriesProduction");
  const fixtureStore = await loadProductionExport("memory-fixtures.ts", "fixtureStore");

  const loading = await renderComponent(MemoriesProduction, { store: fixtureStore("loading"), fixture: "loading" });
  try {
    assert.equal(loading.container.querySelector("[data-empty-kind]"), null);
  } finally {
    await loading.cleanup();
  }

  const empty = await renderComponent(MemoriesProduction, { store: fixtureStore("empty"), fixture: "empty" });
  try {
    assertTrueEmpty(empty, EN_MESSAGES["memories.emptyTitle"], EN_MESSAGES["memories.emptyBody"]);
  } finally {
    await empty.cleanup();
  }

  const filtered = await renderComponent(MemoriesProduction, { store: fixtureStore("normal"), fixture: "normal" });
  try {
    const search = filtered.container.querySelector('input[type="search"]');
    assert.ok(search);
    await setInputValue(filtered, search, "no saved memory matches this query");
    const miss = filtered.container.querySelector('[data-empty-kind="filtered-out"]');
    assert.ok(miss);
    assert.equal(miss.textContent?.trim(), EN_MESSAGES["common.noResults"]);
    assert.equal(filtered.container.querySelector('[data-empty-kind="empty-projection"]'), null);
  } finally {
    await filtered.cleanup();
  }
});

test("ConversationsProduction renders loading, true-empty, filter-miss, and detail-miss distinctly", async () => {
  const ConversationsProduction = await loadProductionExport("ConversationsProduction.tsx", "ConversationsProduction");
  const fixtureConversationStore = await loadProductionExport("conversation-fixtures.ts", "fixtureConversationStore");
  const fixtureFolderStore = await loadProductionExport("conversation-fixtures.ts", "fixtureFolderStore");

  const props = (state, extra = {}) => ({
    store: fixtureConversationStore(state),
    foldersStore: fixtureFolderStore(),
    fixture: state,
    ...extra,
  });
  const loading = await renderComponent(ConversationsProduction, props("loading"));
  try {
    assert.equal(loading.container.querySelector("[data-empty-kind]"), null);
  } finally {
    await loading.cleanup();
  }

  const empty = await renderComponent(ConversationsProduction, props("empty"));
  try {
    assertTrueEmpty(empty, EN_MESSAGES["conversations.emptyTitle"], EN_MESSAGES["conversations.emptyBody"]);
  } finally {
    await empty.cleanup();
  }

  const filtered = await renderComponent(ConversationsProduction, props("normal"));
  try {
    const search = filtered.container.querySelector('input[type="search"]');
    assert.ok(search);
    await setInputValue(filtered, search, "no saved conversation matches this query");
    const miss = filtered.container.querySelector('[data-empty-kind="filtered-out"]');
    assert.ok(miss);
    assert.equal(miss.textContent?.trim(), EN_MESSAGES["common.noResults"]);
  } finally {
    await filtered.cleanup();
  }

  const detailMiss = await renderComponent(ConversationsProduction, props("empty", { detailId: "missing-conversation" }));
  try {
    const miss = detailMiss.container.querySelector('[data-empty-kind="detail-not-found"]');
    assert.ok(miss);
    assert.ok(miss.textContent?.includes(EN_MESSAGES["conversations.detailNotFound"]));
    assert.ok(miss.textContent?.includes(EN_MESSAGES["conversations.detailNotFoundBody"]));
    assert.ok(miss.querySelector("a.conversation-back"), "missing detail offers a real path back to the list");
  } finally {
    await detailMiss.cleanup();
  }

  const loadingDetail = await renderComponent(ConversationsProduction, props("loading", { detailId: "calm-conversation-one" }));
  try {
    // red-proof: ConversationsProduction treated `detailId && !selected` as
    // not-found without consulting phase, so a still-loading detail URL claimed
    // the conversation was removed. conversationDetailKind returning "loading"
    // is not this proof — this query is.
    assert.equal(
      loadingDetail.container.querySelector('[data-empty-kind="detail-not-found"]') == null,
      true,
      "loading detail must not claim the conversation was removed",
    );
    assert.equal(
      loadingDetail.container.textContent?.includes(EN_MESSAGES["conversations.detailNotFound"]),
      false,
    );
    assert.equal(
      loadingDetail.container.textContent?.includes(EN_MESSAGES["conversations.detailNotFoundBody"]),
      false,
    );
    const loadingRegion = loadingDetail.container.querySelector(".production-empty-state");
    assert.equal(loadingRegion != null, true, "unresolved detail during initial-loading is a composed loading state");
    assert.equal(loadingRegion?.querySelector("h2")?.textContent, EN_MESSAGES["common.loading"]);
  } finally {
    await loadingDetail.cleanup();
  }

  const hydratedBase = fixtureConversationStore("normal");
  const hydratedLoading = {
    ...hydratedBase,
    status() {
      return { refresh: { phase: "initial-loading", hasSavedData: true }, queue: { phase: "idle", pendingCount: 0 } };
    },
  };
  const hydratedDetail = await renderComponent(ConversationsProduction, {
    store: hydratedLoading,
    foldersStore: fixtureFolderStore(),
    fixture: "loading-with-rows",
    detailId: "calm-conversation-one",
  });
  try {
    // red-proof: a found row during initial-loading used to be possible only
    // because the JSX asked `selected` first; once that check moved behind a
    // phase-first helper, a hydrated detail would vanish behind common.loading.
    // conversationDetailKind returning "detail" is not this proof — this query is.
    assert.equal(
      hydratedDetail.container.querySelector("[data-conversation-detail='calm-conversation-one']") != null,
      true,
      "a saved conversation stays on screen during initial-loading",
    );
    assert.ok(hydratedDetail.container.textContent?.includes("Morning review"));
    assert.equal(
      hydratedDetail.container.querySelector('[data-empty-kind="detail-not-found"]'),
      null,
    );
    assert.equal(
      hydratedDetail.container.textContent?.includes(EN_MESSAGES["conversations.detailNotFound"]),
      false,
    );
  } finally {
    await hydratedDetail.cleanup();
  }
});

test("TasksProduction renders loading, true-empty, and filter-miss as distinct DOM states", async () => {
  const TasksProduction = await loadProductionExport("TasksProduction.tsx", "TasksProduction");
  const fixtureStore = await loadProductionExport("task-fixtures.ts", "fixtureStore");
  const taskProps = (state) => ({
    store: fixtureStore(state),
    fixture: state,
    translate: (key, vars) => t("en", key, vars),
    now: Date.UTC(2026, 7, 7, 12, 0, 0),
  });

  const loading = await renderComponent(TasksProduction, taskProps("loading"));
  try {
    assert.equal(loading.container.querySelector("[data-empty-kind]"), null);
  } finally {
    await loading.cleanup();
  }

  const empty = await renderComponent(TasksProduction, taskProps("empty"));
  try {
    assertTrueEmpty(empty, EN_MESSAGES["tasks.emptyTitle"], EN_MESSAGES["tasks.emptyBody"]);
  } finally {
    await empty.cleanup();
  }

  const filtered = await renderComponent(TasksProduction, taskProps("normal"));
  try {
    const search = filtered.container.querySelector('input[type="search"]');
    assert.ok(search);
    await setInputValue(filtered, search, "no saved task matches this query");
    const miss = filtered.container.querySelector('[data-empty-kind="filtered-out"]');
    assert.ok(miss);
    assert.equal(miss.textContent?.trim(), EN_MESSAGES["common.noResults"]);
  } finally {
    await filtered.cleanup();
  }

  const base = fixtureStore("normal");
  const hydratedLoading = {
    ...base,
    status() {
      return { refresh: { phase: "initial-loading", hasSavedData: true }, queue: { phase: "idle", pendingCount: 0 } };
    },
  };
  const hidden = await renderComponent(TasksProduction, {
    store: hydratedLoading,
    fixture: "loading-with-rows",
    translate: (key, vars) => t("en", key, vars),
    now: Date.UTC(2026, 7, 7, 12, 0, 0),
  });
  try {
    // red-proof: TasksProduction's first branch used to be `phase === "initial-loading"`
    // with no rowCount check, so a hydrated projection disappeared behind
    // common.loading. tasksBodyKind returning "rows" is not this proof — this
    // query is.
    assert.equal(
      hidden.container.querySelector("article.task-card") != null,
      true,
      "saved tasks stay on screen during initial-loading",
    );
    assert.equal(
      hidden.container.querySelector(".tasks-empty-state .production-empty-state h2") == null,
      true,
    );
    assert.equal(hidden.container.querySelector("[data-empty-kind]") == null, true);
    assert.ok(hidden.container.textContent?.includes("Follow up on the overdue review note"));
  } finally {
    await hidden.cleanup();
  }

  const emptyBase = fixtureStore("empty");
  const refreshingEmpty = {
    ...emptyBase,
    status() {
      return { refresh: { phase: "refreshing", hasSavedData: false }, queue: { phase: "idle", pendingCount: 0 } };
    },
  };
  const refreshing = await renderComponent(TasksProduction, {
    store: refreshingEmpty,
    fixture: "refreshing-empty",
    translate: (key, vars) => t("en", key, vars),
    now: Date.UTC(2026, 7, 7, 12, 0, 0),
  });
  try {
    // red-proof: zero-row refreshing used to fall through the final else into
    // an empty groups region. That is not empty-projection copy, but it is
    // also not a finished snapshot — Chat's historyStart bug in another
    // costume. The JSX must read tasksBodyKind === "loading".
    const region = refreshing.container.querySelector(".tasks-empty-state .production-empty-state");
    assert.ok(region, "zero-row refreshing is a composed loading state");
    assert.equal(region.querySelector("h2")?.textContent, EN_MESSAGES["common.loading"]);
    assert.equal(refreshing.container.querySelector("[data-empty-kind]"), null);
    assert.equal(refreshing.container.textContent?.includes(EN_MESSAGES["tasks.emptyTitle"]), false);
  } finally {
    await refreshing.cleanup();
  }
});

test("ChatProduction true-empty renders both title and body without filter-miss copy", async () => {
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const fixtureChatStore = await loadProductionExport("chat-fixtures.ts", "fixtureChatStore");
  const rendered = await renderComponent(ChatProduction, { store: fixtureChatStore("empty"), fixture: "empty" });
  try {
    const empty = rendered.container.querySelector(".chat-empty-state");
    assert.ok(empty);
    assert.ok(empty.textContent?.includes(EN_MESSAGES["chat.emptyTitle"]));
    assert.ok(empty.textContent?.includes(EN_MESSAGES["chat.emptyBody"]));
    assert.equal(empty.textContent?.includes(EN_MESSAGES["common.noResults"]), false);
  } finally {
    await rendered.cleanup();
  }
});

test("ChatProduction renders a retained cancellation as deliberately stopped", async () => {
  // red-proof: collapse cancelled into ordinary canonical delivery in
  // ChatProduction.deliveryLabel. The rendered label assertion fails while
  // the retained partial remains, catching the user-visible ambiguity.
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const fixtureChatStore = await loadProductionExport("chat-fixtures.ts", "fixtureChatStore");
  const rendered = await renderComponent(ChatProduction, {
    store: fixtureChatStore("cancelled"),
    fixture: "cancelled",
  });
  try {
    const cancelled = rendered.container.querySelector(".chat-message.is-cancelled");
    assert.ok(cancelled, "retained partial is still a rendered message");
    assert.ok(cancelled.textContent?.includes("Checking the saved review notes"));
    assert.ok(cancelled.textContent?.includes(EN_MESSAGES["chat.stopped"]));
  } finally {
    await rendered.cleanup();
  }
});
