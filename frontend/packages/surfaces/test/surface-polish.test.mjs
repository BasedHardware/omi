import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test, { after } from "node:test";

import { EN_MESSAGES, t } from "@omi-core/i18n";
import {
  closeRenderHarness,
  loadProductionExport,
  renderComponent,
} from "./render-harness.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

after(closeRenderHarness);

test("shared CSS ranks primary, secondary, and tertiary controls instead of one pill", async () => {
  const styles = await read("src/production/styles.css");
  assert.match(styles, /\.control-primary \{[^}]*background: var\(--accent\)/);
  assert.match(styles, /\.control-primary \{[^}]*color: var\(--content-inverse\)/);
  assert.match(styles, /\.control-tertiary \{[^}]*background: transparent/);
  assert.match(styles, /\.control-segment-group \{/);
  assert.match(styles, /\.control-segment-group button\[aria-pressed="true"\]/);
  assert.doesNotMatch(
    styles,
    /html\[data-platform="desktop"\]\[data-color-mode="dark"\] button,/,
    "dark mode must not flatten every button onto the elevated fill",
  );
  // red-proof: deleting .control-primary or restoring the dark-mode `button`
  // catch-all makes Play and Start capture look like a rate toggle again.
});

test("page titles, row titles, and metadata use distinct type tokens", async () => {
  const styles = await read("src/production/styles.css");
  assert.match(styles, /\.production-page-heading h1 \{[^}]*font-size: var\(--type-title-size\)/);
  assert.match(styles, /\.production-page-heading h1 \{[^}]*font-weight: var\(--type-title-weight\)/);
  assert.match(styles, /\.memory-meta \{[^}]*font-size: var\(--type-meta-size\)/);
  assert.match(styles, /\.production-empty-state h2 \{[^}]*font-size: var\(--type-heading-size\)/);
  assert.doesNotMatch(
    styles,
    /html\[data-platform="desktop"\] \.production-header h1[^}]*font-size:\s*24px/,
    "desktop titles must not hand-tune a size that collapses the token scale",
  );
  assert.doesNotMatch(
    styles,
    /html\[data-platform="desktop"\] \.memory-meta \{[^}]*font-size:\s*9px/,
    "metadata must stay on the meta token, not a 9px one-off",
  );
  // red-proof: restoring the 24px/9px desktop overrides makes title and meta
  // the same visual weight as body copy.
});

test("Listen Start capture is primary and transcript announcements are tertiary", async () => {
  const ListenProduction = await loadProductionExport("ListenProduction.tsx", "ListenProduction");
  const fixtureListenStore = await loadProductionExport("listen-fixtures.ts", "fixtureListenStore");
  const rendered = await renderComponent(ListenProduction, {
    store: fixtureListenStore("ready"),
    source: { kind: "fixture", fixture: "ready" },
    locale: "en",
  });
  try {
    const start = [...rendered.container.querySelectorAll("button")]
      .find((button) => button.textContent?.trim() === EN_MESSAGES["listen.start"]);
    const announcements = rendered.container.querySelector(".listen-announcement-control");
    assert.ok(start, "Start capture is on screen");
    assert.ok(announcements, "transcript announcement control is on screen");
    assert.equal(start.className.includes("control-primary"), true);
    assert.equal(start.className.includes("control-tertiary"), false);
    assert.equal(announcements.className.includes("control-tertiary"), true);
    assert.equal(announcements.className.includes("control-primary"), false);
    assert.notEqual(start.className, announcements.className);
  } finally {
    await rendered.cleanup();
  }
  // red-proof: putting both buttons on listen-primary-control without rank
  // classes makes this inequality fail at the rendered layer.
});

test("Rewind Play is a primary action and playback rates are a segmented toggle", async () => {
  const ScreenProduction = await loadProductionExport("ScreenProduction.tsx", "ScreenProduction");
  const fixtureScreenStore = await loadProductionExport("screen-fixtures.ts", "fixtureScreenStore");
  const rendered = await renderComponent(ScreenProduction, {
    store: fixtureScreenStore("ready"),
    locale: "en",
  });
  try {
    const play = [...rendered.container.querySelectorAll("button")]
      .find((button) => button.textContent?.trim() === EN_MESSAGES["screen.play"]);
    const rates = rendered.container.querySelectorAll(".control-segment-group button");
    const frame = rendered.container.querySelector("img.screen-frame-image");
    const stage = rendered.container.querySelector(".screen-frame-stage");
    assert.ok(play, "Play is on screen");
    assert.equal(play.className.includes("control-primary"), true);
    assert.equal(play.closest(".control-segment-group"), null, "Play is not a rate pill");
    assert.equal(rates.length, 5);
    for (const rate of rates) {
      assert.equal(rate.className.includes("control-primary"), false);
      assert.match(rate.textContent ?? "", /×$/);
    }
    assert.ok(frame, "the current frame image stays on screen");
    assert.equal(frame.closest(".screen-frame-stage"), stage);
    assert.equal(frame.getAttribute("width"), "1280");
    assert.equal(frame.getAttribute("height"), "800");
  } finally {
    await rendered.cleanup();
  }
  // red-proof: rendering Play inside the rate group, giving 4× control-primary,
  // or dropping the frame <img> fails the assertions the user can see.
});

test("Rewind frame stage is a filled bounded island, not a collapsed or empty box", async () => {
  const css = await read("src/production/screen.css");
  assert.match(css, /\.screen-frame-stage \{[^}]*min-height: calc\(var\(--row-min-height\) \* 3\)/);
  assert.match(css, /\.screen-frame-stage \{[^}]*max-height: calc\(var\(--row-min-height\) \* 5\)/);
  assert.match(css, /\.screen-frame-stage \{[^}]*background: var\(--surface-elevated\)/);
  assert.doesNotMatch(css, /\.screen-frame-stage \{[^}]*min-height:\s*0/);
  assert.doesNotMatch(css, /\.screen-frame-stage \{[^}]*background:\s*transparent/);
  assert.match(css, /\.screen-frame-image \{[^}]*max-width:\s*100%/);
  assert.match(css, /\.screen-frame-image \{[^}]*object-fit:\s*contain/);
  assert.match(
    css,
    /\.screen-frame-unavailable,\s*\n\.screen-frame-host-unavailable,\s*\n\.screen-frame-loading \{[^}]*margin: 0/,
  );
  const source = await read("src/production/ScreenProduction.tsx");
  assert.match(source, /className="screen-frame-host-unavailable"/);
  assert.match(source, /className="screen-frame-unavailable"/);
  assert.match(source, /screen\.frameImageHostUnavailable/);
  assert.match(source, /screen\.frameImageUnavailable/);
  assert.doesNotMatch(
    source,
    /image\.kind === "unavailable" \|\| !bridgeAvailable/,
    "host-absent and missing-bytes stay distinct branches",
  );
  // red-proof: min-height 0 plus width 100% collapsed the Harborline frame in
  // shell captures; this CSS ratchet fails before that layout can land again.
  // Merging host-absent into .screen-frame-unavailable would make the
  // control-acceptance screen token unreadable as a distinct miss.
});

test("desktop catch-alls cannot restyle segmented toggles as raised pills", async () => {
  const styles = await read("src/production/styles.css");
  assert.match(styles, /html\[data-platform="desktop"\] \.control-segment-group button/);
  assert.match(
    styles,
    /html\[data-platform="desktop"\]\[data-color-mode="dark"\] button:not\(\.control-primary\):not\(\.control-danger\):not\(\.control-tertiary\):not\(\.control-segment\)/,
  );
  // red-proof: `html[data-platform=desktop] button { background: glass }` is
  // more specific than `.control-segment-group button` and turns 0.5×–8× back
  // into five identical pills unless the desktop override exists.
});

test("Tasks new-task control is primary and the more menu is not", async () => {
  const TasksProduction = await loadProductionExport("TasksProduction.tsx", "TasksProduction");
  const fixtureStore = await loadProductionExport("task-fixtures.ts", "fixtureStore");
  const rendered = await renderComponent(TasksProduction, {
    store: fixtureStore("normal"),
    fixture: "normal",
    translate: (key, vars) => t("en", key, vars),
    now: Date.UTC(2026, 7, 7, 12, 0, 0),
  });
  try {
    const add = rendered.container.querySelector(".tasks-add-trigger");
    const more = rendered.container.querySelector(".tasks-settings-trigger");
    assert.ok(add, "new-task control is on screen");
    assert.ok(more, "more menu is on screen");
    assert.equal(add.className.includes("control-primary"), true);
    assert.equal(add.className.includes("control-tertiary"), false);
    assert.equal(more.className.includes("control-primary"), false);
    assert.equal(more.className.includes("control-tertiary"), true);
  } finally {
    await rendered.cleanup();
  }
  // red-proof: leaving + and … on the same unranked class makes this fail.
});

test("Chat true-empty and loading states render through the composed empty primitive", async () => {
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const fixtureChatStore = await loadProductionExport("chat-fixtures.ts", "fixtureChatStore");
  const empty = await renderComponent(ChatProduction, { store: fixtureChatStore("empty"), fixture: "empty" });
  try {
    const region = empty.container.querySelector(".chat-empty-state .production-empty-state");
    assert.ok(region);
    assert.equal(region.querySelector("h2")?.textContent, EN_MESSAGES["chat.emptyTitle"]);
    assert.ok(region.textContent?.includes(EN_MESSAGES["chat.emptyBody"]));
    assert.ok(region.querySelector(".production-empty-state-icon"));
  } finally {
    await empty.cleanup();
  }

  const loading = await renderComponent(ChatProduction, { store: fixtureChatStore("loading"), fixture: "loading" });
  try {
    const region = loading.container.querySelector(".chat-empty-state .production-empty-state");
    assert.ok(region);
    assert.equal(region.querySelector("h2")?.textContent, EN_MESSAGES["common.loading"]);
    assert.equal(loading.container.querySelector("[data-empty-kind]"), null, "loading must not claim an empty kind");
  } finally {
    await loading.cleanup();
  }
  // red-proof: reverting Chat empty/loading to a bare <p class="chat-empty-state">
  // drops the heading/icon and fails these queries.
});

function chatBodyStore({ phase, messages }) {
  return {
    status: () => ({
      refresh: { phase, hasSavedData: messages.length > 0 },
      queue: { phase: "idle", pendingCount: 0 },
    }),
    subscribe() { return () => {}; },
    async refresh() {},
    async history() {
      return { messages, hasOlder: false, olderCursor: null };
    },
    async loadOlder() { return { messages: [], hasOlder: false, olderCursor: null }; },
    async send() {},
    capabilities() {
      return {
        maxAttachmentsPerMessage: 2,
        maxAttachmentBytes: 10_000,
        allowedAttachmentMimeTypes: ["application/pdf"],
      };
    },
    stagingAvailable() { return false; },
    async stageAttachment() { return null; },
    async scanAttachment() { return "clean"; },
    async deadLetters() { return []; },
    async discardDeadLetter() {},
    async cancel() {},
    async resolveApproval() {},
  };
}

const savedUserMessage = {
  role: "user",
  text: "What did we decide about the handoff?",
  delivery: {
    kind: "canonical",
    serverId: "saved-chat-human",
    clientMessageId: "saved-chat-human",
    generationOutcome: null,
  },
  attachments: [],
};

test("Chat keeps saved messages on screen while refresh is still initial-loading", async () => {
  // red-proof: ChatProduction's first branch used to be `phase === "initial-loading"`
  // with no messageCount check, so a hydrated projection disappeared behind
  // common.loading. The helper returning "thread" is not this proof — this
  // query is.
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const rendered = await renderComponent(ChatProduction, {
    store: chatBodyStore({ phase: "initial-loading", messages: [savedUserMessage] }),
  });
  try {
    assert.ok(
      rendered.container.querySelector(".chat-message"),
      "saved messages stay in the thread during initial-loading",
    );
    assert.equal(
      rendered.container.querySelector(".chat-empty-state"),
      null,
      "loading empty must not replace a thread that already has rows",
    );
    assert.equal(rendered.container.querySelector("[data-empty-kind]"), null);
    assert.ok(rendered.container.textContent.includes("What did we decide about the handoff?"));
  } finally {
    await rendered.cleanup();
  }
});

test("Chat refreshing with zero messages is loading, not beginning-of-conversation", async () => {
  // red-proof: the final else used to render the thread (and chat.historyStart)
  // for every phase that was not initial-loading/unavailable/ready-empty.
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const rendered = await renderComponent(ChatProduction, {
    store: chatBodyStore({ phase: "refreshing", messages: [] }),
  });
  try {
    const region = rendered.container.querySelector(".chat-empty-state .production-empty-state");
    assert.ok(region, "zero-row refreshing is a composed loading state");
    assert.equal(region.querySelector("h2")?.textContent, EN_MESSAGES["common.loading"]);
    assert.equal(rendered.container.querySelector("[data-empty-kind]"), null);
    assert.equal(rendered.container.querySelector(".chat-history-start"), null);
    assert.equal(rendered.container.textContent.includes(EN_MESSAGES["chat.historyStart"]), false);
    assert.equal(rendered.container.textContent.includes(EN_MESSAGES["chat.emptyTitle"]), false);
  } finally {
    await rendered.cleanup();
  }
});

test("Chat desktop empty/loading slot fills so the composer stays the last row", async () => {
  const css = await read("src/production/chat.css");
  assert.match(
    css,
    /html\[data-platform="desktop"\] main\[data-route="chat"\] \.chat-empty-state \{[^}]*flex: 1 1 auto/,
  );
  assert.match(
    css,
    /html\[data-platform="desktop"\] main\[data-route="chat"\] \.chat-empty-state \{[^}]*min-height: 0/,
  );
  assert.match(
    css,
    /\.chat-message-text \{[^}]*max-width: var\(--measure-body\)/,
  );
  assert.match(
    css,
    /\.chat-agent-capability,\s*\n\.chat-agent-state \{[^}]*text-overflow: ellipsis/,
  );
  assert.doesNotMatch(
    css,
    /\.chat-agent-capability,\s*\n\.chat-agent-state \{[^}]*padding: 2px /,
  );
  // red-proof: without flex on .chat-empty-state the composer sits under the
  // empty copy instead of at the panel bottom; restoring padding: 2px puts a
  // hardcoded size back on the capability chip.
});

test("Listen waiting for speech uses the composed empty primitive without changing the words", async () => {
  const ListenProduction = await loadProductionExport("ListenProduction.tsx", "ListenProduction");
  const fixtureListenStore = await loadProductionExport("listen-fixtures.ts", "fixtureListenStore");
  const rendered = await renderComponent(ListenProduction, {
    store: fixtureListenStore("empty"),
    source: { kind: "fixture", fixture: "empty" },
    locale: "en",
  });
  try {
    const start = [...rendered.container.querySelectorAll("button")]
      .find((button) => button.textContent?.trim() === EN_MESSAGES["listen.start"]);
    assert.ok(start);
    await rendered.act(async () => { start.click(); });
    const waiting = rendered.container.querySelector(".listen-transcript-waiting .production-empty-state");
    assert.ok(waiting, "capturing with no segments is a composed waiting state");
    assert.equal(waiting.querySelector("h2")?.textContent, EN_MESSAGES["listen.transcriptWaiting"]);
  } finally {
    await rendered.cleanup();
  }
});

test("Listen and Tasks desktop shells no longer paint a second window card over the glass panel", async () => {
  const listen = await read("src/production/listen.css");
  const tasks = await read("src/production/tasks.css");
  assert.doesNotMatch(
    listen,
    /html\[data-platform="desktop"\] \.listen-production-shell \{[^}]*border:\s*1px solid var\(--border\)/,
  );
  assert.doesNotMatch(
    listen,
    /html\[data-platform="desktop"\] \.listen-production-shell \{[^}]*background:\s*var\(--surface-raised\)/,
  );
  assert.doesNotMatch(
    tasks,
    /html\[data-platform="desktop"\] \.tasks-production-shell \{[^}]*border:\s*1px solid var\(--border\)/,
  );
  // red-proof: restoring the per-surface desktop window chrome puts a white
  // card on the glass host and this assertion fails.
});
