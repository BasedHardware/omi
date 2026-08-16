import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test, { after } from "node:test";

import { EN_MESSAGES } from "@omi-core/i18n";
import {
  closeRenderHarness,
  loadProductionExport,
  renderComponent,
} from "./render-harness.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

after(closeRenderHarness);

function human(serverId, text) {
  return {
    role: "user",
    text,
    delivery: { kind: "canonical", serverId, clientMessageId: serverId, generationOutcome: null },
    attachments: [],
  };
}

function reply(serverId, text, events = []) {
  return {
    role: "assistant",
    text,
    delivery: { kind: "canonical", serverId, clientMessageId: null, generationOutcome: "completed" },
    attachments: [],
    ...(events.length === 0 ? {} : { agentRun: { state: "complete", events } }),
  };
}

const capabilityEvent = (adapter, tier) => ({
  sequence: 1,
  kind: "capability_receipt",
  safeSummary: "capability",
  details: { adapter, tier, deterministic: false },
});

function threadStore({ messages, hasOlder = false, olderCursor = null }) {
  return {
    status: () => ({
      refresh: { phase: "ready", hasSavedData: messages.length > 0 },
      queue: { phase: "idle", pendingCount: 0 },
    }),
    subscribe() { return () => {}; },
    async refresh() {},
    async history() { return { messages, hasOlder, olderCursor }; },
    async loadOlder() { return { messages: [], hasOlder: false, olderCursor: null }; },
    async send() {},
    capabilities() {
      return {
        maxAttachmentsPerMessage: 4,
        maxAttachmentBytes: 10_000,
        allowedAttachmentMimeTypes: ["application/pdf"],
      };
    },
    stagingAvailable() { return true; },
    async stageAttachment() { return null; },
    async scanAttachment() { return "clean"; },
    async deadLetters() { return []; },
    async discardDeadLetter() {},
    async cancel() {},
    async resolveApproval() {},
  };
}

test("every turn in the thread carries its own speaker, including the first", async () => {
  // NOT a red-proof — this passed before the fix too, and that is the finding.
  // Nothing suppresses the first turn's speaker: `.chat-role` is unconditional,
  // so a bare first message is a clipped one, not an unlabelled one. The list is
  // the scroll container and it opens at the bottom, so the frozen history row
  // above it sat over a turn cut through its meta line. This guards the half of
  // the report that turned out to be sound, so a later "collapse repeated
  // speakers" idea cannot make the screenshot's reading come true.
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const rendered = await renderComponent(ChatProduction, {
    store: threadStore({
      messages: [human("m1", "yo what's up"), reply("m2", "Not much."), human("m3", "what's up")],
    }),
  });
  try {
    const roles = [...rendered.container.querySelectorAll(".chat-message .chat-role")]
      .map((node) => node.textContent);
    assert.deepEqual(roles, [
      EN_MESSAGES["chat.roleUser"],
      EN_MESSAGES["chat.roleAssistant"],
      EN_MESSAGES["chat.roleUser"],
    ]);
  } finally {
    await rendered.cleanup();
  }
});

test("the top-of-history row scrolls with the transcript instead of pinning above it", async () => {
  // red-proof: `.chat-history-controls` used to be a sibling of the message
  // list. On desktop the list is the scroll container, so the row stayed frozen
  // at the top of the panel while the thread scrolled under it — a centred
  // "beginning of the conversation" announcement parked over a thread that was
  // scrolled past its beginning, clipping the first visible turn's speaker.
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const rendered = await renderComponent(ChatProduction, {
    store: threadStore({ messages: [human("m1", "yo what's up")], hasOlder: true, olderCursor: "c1" }),
  });
  try {
    const list = rendered.container.querySelector(".chat-message-list");
    const controls = rendered.container.querySelector(".chat-history-controls");
    assert.ok(list, "the thread renders its scrolling message list");
    assert.ok(controls, "an older page is reachable from the top of the thread");
    assert.ok(
      list.contains(controls),
      "the top-of-history row must live inside the element that scrolls",
    );
    // The half that JSDOM cannot show: which element actually scrolls. Without
    // this the containment assertion above could be satisfied while the CSS
    // moved the scroller somewhere else and re-froze the row.
    const css = await read("src/production/chat.css");
    assert.match(
      css,
      /main\[data-route="chat"\] \.chat-message-list \{[^}]*overflow-y: auto/,
      "the message list is still the scroll container this row must live inside",
    );
  } finally {
    await rendered.cleanup();
  }
});

test("a thread at its beginning states it inline, not as a centred announcement", async () => {
  // Swift renders nothing at the top of a fully-loaded transcript
  // (ChatMessagesView.loadMoreButton returns an empty view when there is no
  // earlier action). Matching that: no standing sentence above the first turn.
  // red-proof: restoring the `chat-history-start` paragraph re-adds the banner.
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const rendered = await renderComponent(ChatProduction, {
    store: threadStore({ messages: [human("m1", "yo what's up")] }),
  });
  try {
    // Boolean-shaped on purpose: `assert.equal(node, null)` makes a failure
    // inspect a whole JSDOM element, which stalls the runner instead of failing.
    assert.equal(
      rendered.container.querySelector(".chat-history-start") === null,
      true,
      "no standing beginning-of-conversation sentence above the first turn",
    );
    assert.equal(
      rendered.container.textContent.includes(EN_MESSAGES["chat.historyStart"]),
      false,
      "a loaded-to-the-start thread says nothing where the older-page control would be",
    );
    assert.ok(
      rendered.container.querySelector(".chat-message"),
      "the thread itself is unaffected",
    );
  } finally {
    await rendered.cleanup();
  }
});

test("provenance stays a chip and keeps naming the tier it actually had", async () => {
  // red-proof: dropping the capability chip, or letting the local test gateway
  // read as an external model, is the failure this guards. Quieter is allowed;
  // overstating is not.
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const rendered = await renderComponent(ChatProduction, {
    store: threadStore({
      messages: [
        human("m1", "yo what's up"),
        reply("m2", "Hello.", [capabilityEvent("omi.local-test-gateway.v1", "unknown")]),
      ],
    }),
  });
  try {
    const summary = rendered.container.querySelector(".chat-agent-run summary");
    assert.ok(summary, "provenance is still reachable under the answer");
    const capability = summary.querySelector(".chat-agent-capability");
    assert.equal(capability.textContent, EN_MESSAGES["chat.agentLocalTestGateway"]);
    assert.notEqual(capability.textContent, EN_MESSAGES["chat.agentProvider"]);
  } finally {
    await rendered.cleanup();
  }
});

test("the agent-run disclosure is inline weight, not a bordered full-width panel", async () => {
  // red-proof: restoring `border: 1px solid var(--border)` plus the raised fill
  // on `.chat-agent-run` puts a boxed panel under every answer again.
  const css = await read("src/production/chat.css");
  const block = /\.chat-agent-run \{([^}]*)\}/.exec(css);
  assert.ok(block, "the disclosure still has its own rule");
  assert.doesNotMatch(block[1], /border:\s*1px solid var\(--border\)/);
  assert.doesNotMatch(block[1], /background:\s*var\(--surface-raised\)/);
  assert.match(css, /\.chat-agent-run summary \{[^}]*min-height: var\(--min-tap-target\)/);
});

test("the attachment cap is composer help, not a standing line above the input", async () => {
  // red-proof: rendering `chat.attachmentLimit` unconditionally puts
  // "Up to 4 attachments per message." back over the textarea on every visit.
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const rendered = await renderComponent(ChatProduction, {
    store: threadStore({ messages: [human("m1", "yo what's up")] }),
  });
  try {
    assert.equal(
      rendered.container.textContent.includes(
        EN_MESSAGES["chat.attachmentLimit"].replace("{count}", "4"),
      ),
      false,
      "an idle composer with no attachments states no cap",
    );
    const attach = rendered.container.querySelector(".chat-attach");
    assert.ok(attach, "attaching is still offered");
    assert.equal(
      attach.getAttribute("title"),
      EN_MESSAGES["chat.attachmentLimit"].replace("{count}", "4"),
      "the cap survives on the control it constrains",
    );
  } finally {
    await rendered.cleanup();
  }
});

test("a cap that blocks attaching is still said out loud", async () => {
  // red-proof: moving every hint into the tooltip would silence the states
  // that explain a disabled control. Only the idle cap is demoted.
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const base = threadStore({ messages: [human("m1", "yo what's up")] });
  const rendered = await renderComponent(ChatProduction, {
    store: { ...base, stagingAvailable: () => false },
  });
  try {
    const hint = rendered.container.querySelector(".chat-attachment-hint");
    assert.ok(hint, "an unavailable attachment path keeps its visible reason");
    assert.equal(hint.textContent, EN_MESSAGES["chat.attachmentUnavailable"]);
  } finally {
    await rendered.cleanup();
  }
});

test("the composer is attach, then input, then send — Swift's order", async () => {
  // Swift decides this one: ChatInputView's HStack is `paperclip Button` then
  // the input, and the upstream tip still reads that way. What made the leading
  // slot look wrong here was weight, not position — a word-width labelled
  // button where Swift draws a 32pt glyph.
  // red-proof: reordering to `chat-draft, chat-attach, chat-send` invents a
  // third answer that neither Swift nor this repo's mobile template agrees with.
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const rendered = await renderComponent(ChatProduction, {
    store: threadStore({ messages: [human("m1", "yo what's up")] }),
  });
  try {
    const row = rendered.container.querySelector(".chat-composer-row");
    const order = [...row.children].map((node) => node.className.split(" ")[0]);
    assert.deepEqual(order, ["chat-attach", "chat-draft", "chat-send"]);
    // Mobile lays the same three out in two columns plus a full-width Send row,
    // so its template has to follow the DOM order too: a template that sizes
    // column one for the wrong child shrink-wraps the textarea.
    const css = await read("src/production/chat.css");
    assert.match(
      css,
      /html\[data-platform="mobile"\] \.chat-composer-row \{[^}]*grid-template-columns: auto minmax\(0, 1fr\)/,
    );
  } finally {
    await rendered.cleanup();
  }
});

test("attach is a named glyph, not a word, and never a nameless one", async () => {
  // The whole point of moving to Swift's weight is that the control stops
  // spending a word of the composer on itself. That is only safe while the
  // accessible name survives the visible text going away.
  // red-proof: rendering `{t(locale, "chat.attach")}` as the button's child puts
  // the word back; dropping `aria-label` leaves a button a screen reader can
  // only call "button" — and `check-accessibility-names` fails the build on it.
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const rendered = await renderComponent(ChatProduction, {
    store: threadStore({ messages: [human("m1", "yo what's up")] }),
  });
  try {
    const attach = rendered.container.querySelector(".chat-attach");
    assert.ok(attach, "attaching is still offered");
    assert.equal(attach.textContent.trim(), "", "no visible word in the leading slot");
    assert.equal(attach.getAttribute("aria-label"), EN_MESSAGES["chat.attach"]);
    const icon = attach.querySelector("svg.production-icon");
    assert.ok(icon, "the glyph comes from the audited icon vocabulary");
    assert.equal(icon.getAttribute("aria-hidden"), "true", "the glyph is not a second name");
  } finally {
    await rendered.cleanup();
  }
});
