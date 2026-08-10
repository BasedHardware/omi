import assert from "node:assert/strict";
import test, { after } from "node:test";

import { EN_MESSAGES } from "@omi-core/i18n";
import {
  closeRenderHarness,
  loadProductionExport,
  renderComponent,
} from "./render-harness.mjs";

after(closeRenderHarness);

function status() {
  return {
    refresh: { phase: "ready", hasSavedData: true },
    queue: { phase: "idle", pendingCount: 0 },
  };
}

function row(id, sender, text, outcome = sender === "ai" ? "completed" : null) {
  return {
    id,
    text,
    sender,
    type: "text",
    createdAt: sender === "human" ? 1 : 2,
    updatedAt: sender === "human" ? 1 : 2,
    chatSessionId: null,
    appId: null,
    journalRevision: 1,
    payloadHash: "sha256:rendered",
    messageSource: "desktop_chat",
    rating: null,
    reported: false,
    generationOutcome: outcome,
    revision: `revision-${id}`,
    attachments: [],
  };
}

class RenderedDomainChat {
  listeners = new Set();
  rows = [];
  active = [];
  sent = [];
  cancelled = [];
  deliveries = [];
  dead = [];
  discarded = [];

  status() { return status(); }
  subscribe(listener) { this.listeners.add(listener); return () => this.listeners.delete(listener); }
  async refresh() {}
  historyPage() { return { hasOlder: false, olderCursor: null }; }
  async loadOlder() { return []; }
  async list() { return this.rows; }
  pendingMessageIds() { return []; }
  activeGenerations() { return this.active; }
  async generationDeliveries() { return this.deliveries; }
  async deadLetters() { return this.dead; }
  async discardDeadLetter(opId) {
    this.discarded.push(opId);
    this.dead = this.dead.filter((letter) => letter.opId !== opId);
    this.notify();
  }
  capabilities() {
    return {
      maxAttachmentsPerMessage: 2,
      maxAttachmentBytes: 10_000,
      allowedAttachmentMimeTypes: ["application/pdf"],
    };
  }
  async send(text, attachmentIds) {
    this.sent.push({ text, attachmentIds: [...attachmentIds] });
    const admitted = row("domain-authored-human", "human", text);
    admitted.revision = null;
    this.rows = [admitted];
    this.active = [{
      generationId: "generation-live",
      clientMessageId: "domain-authored-human",
      text: "First",
      lastEventId: "event-delta-1",
      observationState: "streaming",
      failure: null,
    }];
    this.notify();
  }
  async cancelGeneration(generationId) { this.cancelled.push(generationId); }
  pushDelta() {
    this.active = [{ ...this.active[0], text: "First second" }];
    this.notify();
  }
  terminal() {
    this.rows = [
      this.rows[0],
      row("canonical-assistant", "ai", "First second complete"),
    ];
    this.active = [];
    this.notify();
  }
  notify() { for (const listener of this.listeners) listener(); }
}

async function setTextarea(rendered, textarea, value) {
  const setter = Object.getOwnPropertyDescriptor(
    rendered.window.HTMLTextAreaElement.prototype,
    "value",
  )?.set;
  assert.ok(setter, "jsdom textarea value setter is available");
  await rendered.act(async () => {
    setter.call(textarea, value);
    textarea.dispatchEvent(new rendered.window.Event("input", { bubbles: true }));
    await Promise.resolve();
  });
}

async function click(rendered, element) {
  await rendered.act(async () => {
    element.dispatchEvent(new rendered.window.MouseEvent("click", { bubbles: true }));
    for (let index = 0; index < 8; index += 1) await Promise.resolve();
  });
}

test("rendered live Chat streams changing assistant text and converges without duplicate bubbles", async () => {
  // red-proof: omit activeGenerations() from projectedHistory. The rendered
  // `.is-streaming` assertion fails even though the domain observer has text.
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const createProductionChatStore = await loadProductionExport(
    "ProductionChatStore.ts",
    "createProductionChatStore",
  );
  const domain = new RenderedDomainChat();
  const store = createProductionChatStore(domain);
  const rendered = await renderComponent(ChatProduction, { store });
  try {
    const textarea = rendered.container.querySelector("textarea.chat-draft");
    const send = rendered.container.querySelector("button.chat-send");
    assert.ok(textarea);
    assert.ok(send);
    await setTextarea(rendered, textarea, "Question from the rendered composer");
    await click(rendered, send);

    let bubbles = [...rendered.container.querySelectorAll(".chat-message")];
    assert.equal(bubbles.length, 2, "canonical human plus one streaming assistant");
    assert.equal(bubbles[0].dataset.delivery, "canonical", "admission is canonical even with null revision");
    assert.ok(bubbles[0].textContent.includes("Question from the rendered composer"));
    assert.ok(bubbles[1].textContent.includes("First"));
    assert.equal(bubbles[1].dataset.delivery, "streaming");

    await rendered.act(async () => { domain.pushDelta(); await Promise.resolve(); });
    const streaming = rendered.container.querySelector(".chat-message.is-streaming");
    assert.ok(streaming?.textContent.includes("First second"), "second delta changes visible text before terminal");
    const stop = streaming.querySelector("button");
    assert.ok(stop);
    assert.equal(stop.disabled, false, "cancel remains interactive during streaming");
    await click(rendered, stop);
    assert.deepEqual(domain.cancelled, ["generation-live"]);

    await rendered.act(async () => { domain.terminal(); await Promise.resolve(); });
    bubbles = [...rendered.container.querySelectorAll(".chat-message")];
    assert.equal(bubbles.length, 2, "terminal replaces the projection without a duplicate assistant");
    assert.equal(bubbles.filter((bubble) => bubble.textContent.includes("First second complete")).length, 1);
    assert.equal(rendered.container.querySelector(".chat-message.is-streaming"), null);
  } finally {
    await rendered.cleanup();
  }
});

test("staged safe metadata renders generically while only ordered opaque ids reach send", async () => {
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const createProductionChatStore = await loadProductionExport(
    "ProductionChatStore.ts",
    "createProductionChatStore",
  );
  const domain = new RenderedDomainChat();
  const descriptors = [
    {
      id: "opaque-stage-one",
      mimeType: "application/pdf",
      sizeBytes: 100,
      expiresAt: "2026-08-11T12:00:00.000Z",
      state: "staged",
    },
    {
      id: "opaque-stage-two",
      mimeType: "application/pdf",
      sizeBytes: 200,
      expiresAt: "2026-08-11T12:00:00.000Z",
      state: "staged",
    },
  ];
  let nextDescriptor = 0;
  const staging = {
    isAvailable: () => true,
    async pickAndStage() { return descriptors[nextDescriptor++]; },
  };
  const store = createProductionChatStore(domain, staging);
  const rendered = await renderComponent(ChatProduction, { store });
  try {
    const attach = rendered.container.querySelector("button.chat-attach");
    assert.ok(attach);
    await click(rendered, attach);
    await click(rendered, attach);
    assert.deepEqual(
      [...rendered.container.querySelectorAll(".chat-attachments li span")].map((item) => item.textContent),
      ["Staged application/pdf, 100 bytes", "Staged application/pdf, 200 bytes"],
      "staging cannot claim a durable server name that P7 did not return",
    );

    const textarea = rendered.container.querySelector("textarea.chat-draft");
    const send = rendered.container.querySelector("button.chat-send");
    await setTextarea(rendered, textarea, "Send staged files");
    await click(rendered, send);
    assert.deepEqual(domain.sent, [{
      text: "Send staged files",
      attachmentIds: ["opaque-stage-one", "opaque-stage-two"],
    }]);
    const serialized = JSON.stringify(domain.sent);
    assert.doesNotMatch(serialized, /application\/pdf|sizeBytes|expiresAt/);
  } finally {
    await rendered.cleanup();
  }
});

test("absent staging host renders unavailable and cannot mint a placeholder attachment", async () => {
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const createProductionChatStore = await loadProductionExport(
    "ProductionChatStore.ts",
    "createProductionChatStore",
  );
  const domain = new RenderedDomainChat();
  const rendered = await renderComponent(ChatProduction, {
    store: createProductionChatStore(domain),
  });
  try {
    const attach = rendered.container.querySelector("button.chat-attach");
    assert.ok(attach);
    assert.equal(attach.disabled, true);
    assert.ok(rendered.container.textContent.includes(EN_MESSAGES["chat.attachmentUnavailable"]));
    assert.equal(rendered.container.querySelector(".chat-attachments"), null);
  } finally {
    await rendered.cleanup();
  }
});

test("observer and provider failures render as non-streaming assistant failures", async () => {
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const createProductionChatStore = await loadProductionExport(
    "ProductionChatStore.ts",
    "createProductionChatStore",
  );
  const domain = new RenderedDomainChat();
  domain.rows = [row("failed-human", "human", "Question")];
  domain.active = [{
    generationId: "observer-failed",
    clientMessageId: "failed-human",
    text: "Partial answer",
    lastEventId: "event-1",
    observationState: "failed",
    failure: "bridge disconnected",
  }];
  const rendered = await renderComponent(ChatProduction, {
    store: createProductionChatStore(domain),
  });
  try {
    let failed = rendered.container.querySelector(".chat-message.is-failed");
    assert.ok(failed, "observer failure is visible as failed");
    assert.equal(failed.dataset.delivery, "failed");
    assert.equal(failed.getAttribute("aria-busy"), null, "observer failure is not still streaming");
    assert.ok(failed.textContent.includes("Partial answer"));

    await rendered.act(async () => {
      domain.active = [];
      domain.deliveries = [{
        generationId: "provider-failed",
        clientMessageId: "failed-human",
        terminal: { kind: "failed", error: { code: "provider_down", retryable: true } },
      }];
      domain.notify();
      await Promise.resolve();
    });
    failed = rendered.container.querySelector(".chat-message.is-failed");
    assert.ok(failed, "provider terminal failure is visible after active observation is removed");
    assert.equal(failed.getAttribute("aria-busy"), null);
    assert.equal(rendered.container.querySelector(".chat-message.is-streaming"), null);
  } finally {
    await rendered.cleanup();
  }
});

test("retained dead send shows exact authored text and ordered ids with discard only", async () => {
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const createProductionChatStore = await loadProductionExport(
    "ProductionChatStore.ts",
    "createProductionChatStore",
  );
  const domain = new RenderedDomainChat();
  domain.rows = [row("canonical-existing", "human", "Already admitted")];
  domain.dead = [{
    opId: "dead-send-1",
    recordId: "dead-human",
    domain: "chat",
    summary: "Send chat",
    payload: JSON.stringify({
      op: "create",
      text: "Exact authored text",
      attachmentIds: ["opaque-one", "opaque-two"],
    }),
    failure: { kind: "permanent", reason: "forbidden", detail: "fixed" },
    deadAt: 1,
  }];
  const rendered = await renderComponent(ChatProduction, {
    store: createProductionChatStore(domain),
  });
  try {
    const panel = rendered.container.querySelector(".chat-dead-letters");
    assert.ok(panel);
    assert.ok(panel.textContent.includes("Exact authored text"));
    assert.deepEqual(
      [...panel.querySelectorAll(".chat-dead-attachment-ids code")].map((item) => item.textContent),
      ["opaque-one", "opaque-two"],
    );
    assert.equal([...panel.querySelectorAll("button")].some((button) => /retry/i.test(button.textContent)), false);
    const discard = panel.querySelector("button");
    assert.ok(discard);
    await click(rendered, discard);
    assert.deepEqual(domain.discarded, ["dead-send-1"]);
    assert.equal(rendered.container.querySelector(".chat-dead-letters"), null);
  } finally {
    await rendered.cleanup();
  }
});
