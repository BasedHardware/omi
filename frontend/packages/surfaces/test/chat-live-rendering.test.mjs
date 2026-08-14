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
  approvals = [];
  deliveries = [];
  timelines = [];
  dead = [];
  discarded = [];
  caps = {
    maxAttachmentsPerMessage: 2,
    maxAttachmentBytes: 10_000,
    allowedAttachmentMimeTypes: ["application/pdf"],
  };
  sendFailure = null;
  sendGate = null;
  window = { hasOlder: false, olderCursor: null };
  olderRows = [];
  olderGate = null;
  admittedAttachments = [];

  status() { return status(); }
  subscribe(listener) { this.listeners.add(listener); return () => this.listeners.delete(listener); }
  async refresh() {}
  historyPage() { return this.window; }
  async loadOlder() {
    if (this.olderGate) await this.olderGate;
    this.window = { hasOlder: false, olderCursor: null };
    return this.olderRows;
  }
  async list() { return this.rows; }
  pendingMessageIds() { return []; }
  activeGenerations() { return this.active; }
  async generationDeliveries() { return this.deliveries; }
  agentRunTimelines() { return this.timelines; }
  async deadLetters() { return this.dead; }
  async discardDeadLetter(opId) {
    this.discarded.push(opId);
    this.dead = this.dead.filter((letter) => letter.opId !== opId);
    this.notify();
  }
  capabilities() {
    return this.caps;
  }
  async send(text, attachmentIds) {
    this.sent.push({ text, attachmentIds: [...attachmentIds] });
    if (this.sendGate) await this.sendGate;
    if (this.sendFailure) throw this.sendFailure;
    const admitted = row("domain-authored-human", "human", text);
    admitted.revision = null;
    admitted.attachments = this.admittedAttachments;
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
  async resolveApproval(resolution) { this.approvals.push(resolution); this.notify(); }
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

class JournalFirstRaceChatStore {
  listeners = new Set();
  messages = [];
  sent = [];
  currentStatus = status();
  holdNextHistory = false;
  releaseOlderHistory = null;
  rejectOlderHistory = null;

  status() { return this.currentStatus; }
  subscribe(listener) { this.listeners.add(listener); return () => this.listeners.delete(listener); }
  async refresh() {}
  async history() {
    const page = {
      messages: [...this.messages],
      hasOlder: false,
      olderCursor: null,
    };
    if (!this.holdNextHistory) return page;
    this.holdNextHistory = false;
    return new Promise((resolve, reject) => {
      this.releaseOlderHistory = () => resolve(page);
      this.rejectOlderHistory = () => reject(new Error("stale pre-admission history failed"));
    });
  }
  async loadOlder() { return { messages: [], hasOlder: false, olderCursor: null }; }
  async send(input) {
    this.sent.push(input);
    // The real outbox resolves at durable journal time. Canonical admission is
    // a later transport callback, so the component's direct post-send history
    // read can legitimately capture the pre-admission projection.
    this.messages = [
      {
        role: "user",
        text: input.text,
        delivery: { kind: "echo", clientMessageId: "journal-race-human" },
        attachments: [],
      },
      {
        role: "assistant",
        text: "Stale streaming answer",
        delivery: { kind: "streaming", generationId: "journal-race-generation" },
        attachments: [],
      },
    ];
    this.holdNextHistory = true;
  }
  capabilities() {
    return {
      maxAttachmentsPerMessage: 2,
      maxAttachmentBytes: 10_000,
      allowedAttachmentMimeTypes: ["application/pdf"],
    };
  }
  stagingAvailable() { return false; }
  async stageAttachment() { return null; }
  async scanAttachment() { return "clean"; }
  async deadLetters() { return []; }
  async discardDeadLetter() {}
  async cancel() {}
  async resolveApproval() {}
  admitCanonical(text) {
    this.messages = [
      {
        role: "user",
        text,
        delivery: {
          kind: "canonical",
          serverId: "canonical-race-human",
          clientMessageId: "canonical-race-human",
          generationOutcome: null,
        },
        attachments: [],
      },
      {
        role: "assistant",
        text: "Canonical terminal answer",
        delivery: {
          kind: "canonical",
          serverId: "canonical-race-assistant",
          clientMessageId: null,
          generationOutcome: "completed",
        },
        attachments: [],
      },
    ];
    for (const listener of this.listeners) listener();
  }
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

test("Chat preserves the reader's live-edge choice and older-history anchor", async () => {
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const createProductionChatStore = await loadProductionExport(
    "ProductionChatStore.ts",
    "createProductionChatStore",
  );
  const domain = new RenderedDomainChat();
  domain.rows = [
    row("current-human", "human", "Current question"),
    row("current-answer", "ai", "Current answer"),
  ];
  domain.window = { hasOlder: true, olderCursor: "older-cursor" };
  domain.olderRows = [row("older-human", "human", "Earlier question")];
  let releaseOlder;
  domain.olderGate = new Promise((resolve) => { releaseOlder = resolve; });
  const rendered = await renderComponent(ChatProduction, {
    store: createProductionChatStore(domain),
  });
  try {
    await rendered.act(async () => {
      for (let index = 0; index < 6; index += 1) await Promise.resolve();
    });
    const list = rendered.container.querySelector(".chat-message-list");
    assert.ok(list);
    Object.defineProperties(list, {
      clientHeight: { configurable: true, value: 300 },
      scrollHeight: { configurable: true, value: 1_000, writable: true },
      scrollTop: { configurable: true, value: 180, writable: true },
    });
    await rendered.act(async () => {
      list.dispatchEvent(new rendered.window.Event("scroll", { bubbles: true }));
    });
    assert.ok(rendered.container.querySelector(".chat-jump-latest"), "leaving the edge reveals Latest");

    const loadOlder = rendered.container.querySelector(".chat-history-controls button");
    assert.ok(loadOlder);
    await rendered.act(async () => {
      loadOlder.dispatchEvent(new rendered.window.MouseEvent("click", { bubbles: true }));
      await Promise.resolve();
    });
    list.scrollHeight = 1_300;
    await rendered.act(async () => {
      releaseOlder();
      for (let index = 0; index < 8; index += 1) await Promise.resolve();
    });
    assert.equal(list.scrollTop, 480, "prepending 300px keeps the same visible history anchored");

    list.scrollHeight = 1_500;
    await rendered.act(async () => {
      domain.rows = [...domain.rows, row("new-answer", "ai", "A newer answer")];
      domain.notify();
      for (let index = 0; index < 8; index += 1) await Promise.resolve();
    });
    assert.equal(list.scrollTop, 480, "new output never yanks a reader who moved upward");
    const latest = rendered.container.querySelector(".chat-jump-latest");
    assert.ok(latest);
    await click(rendered, latest);
    assert.equal(list.scrollTop, 1_500, "Latest explicitly resumes the live edge");
    assert.equal(rendered.container.querySelector(".chat-jump-latest"), null);

    await rendered.act(async () => {
      list.dispatchEvent(new rendered.window.WheelEvent("wheel", { bubbles: true, deltaY: -1 }));
    });
    assert.ok(rendered.container.querySelector(".chat-jump-latest"), "upward wheel intent releases follow");
    await click(rendered, rendered.container.querySelector(".chat-jump-latest"));

    await rendered.act(async () => {
      list.dispatchEvent(new rendered.window.KeyboardEvent("keydown", { bubbles: true, key: "PageUp" }));
    });
    assert.ok(rendered.container.querySelector(".chat-jump-latest"), "keyboard history navigation releases follow");
    await click(rendered, rendered.container.querySelector(".chat-jump-latest"));

    const touchStart = new rendered.window.Event("touchstart", { bubbles: true });
    const touchMove = new rendered.window.Event("touchmove", { bubbles: true });
    Object.defineProperty(touchStart, "touches", { value: [{ clientY: 100 }] });
    Object.defineProperty(touchMove, "touches", { value: [{ clientY: 140 }] });
    await rendered.act(async () => {
      list.dispatchEvent(touchStart);
      list.dispatchEvent(touchMove);
    });
    assert.ok(rendered.container.querySelector(".chat-jump-latest"), "touch history navigation releases follow");
  } finally {
    await rendered.cleanup();
  }
});

test("mobile Chat keeps Latest above the sticky composer", async () => {
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const createProductionChatStore = await loadProductionExport(
    "ProductionChatStore.ts",
    "createProductionChatStore",
  );
  const domain = new RenderedDomainChat();
  domain.rows = [row("human", "human", "Question"), row("answer", "ai", "Answer")];
  const rendered = await renderComponent(ChatProduction, { store: createProductionChatStore(domain) });
  try {
    rendered.window.document.documentElement.dataset.platform = "mobile";
    const composer = rendered.container.querySelector(".chat-composer");
    const list = rendered.container.querySelector(".chat-message-list");
    assert.ok(composer);
    assert.ok(list);
    Object.defineProperty(composer, "getBoundingClientRect", {
      configurable: true,
      value: () => ({ height: 176, width: 320, top: 400, right: 320, bottom: 576, left: 0, x: 0, y: 400, toJSON() {} }),
    });
    await rendered.act(async () => {
      rendered.window.dispatchEvent(new rendered.window.Event("resize"));
      list.dispatchEvent(new rendered.window.WheelEvent("wheel", { bubbles: true, deltaY: -1 }));
    });
    const latest = rendered.container.querySelector(".chat-jump-latest");
    assert.ok(latest);
    assert.equal(latest.style.getPropertyValue("--chat-mobile-composer-height"), "176px");
    assert.equal(latest.textContent, EN_MESSAGES["chat.latest"]);
  } finally {
    await rendered.cleanup();
  }
});

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
    // red-proof: hard-code the rendered admission count to zero; the post-send
    // assertion fails while dispatch and generation still appear healthy.
    const productionRoot = rendered.container.querySelector("main[data-route='chat']");
    assert.equal(productionRoot?.dataset.consumerChatAdmissionCount, "0");
    const textarea = rendered.container.querySelector("textarea.chat-draft");
    const send = rendered.container.querySelector("button.chat-send");
    assert.ok(textarea);
    assert.ok(send);
    await setTextarea(rendered, textarea, "Question from the rendered composer");
    await click(rendered, send);

    let bubbles = [...rendered.container.querySelectorAll(".chat-message")];
    assert.equal(bubbles.length, 2, "canonical human plus one streaming assistant");
    assert.equal(bubbles[0].dataset.delivery, "canonical", "admission is canonical even with null revision");
    assert.equal(
      productionRoot.dataset.consumerChatAdmissionCount,
      "1",
      "rendered evidence advances only after canonical user admission",
    );
    assert.match(productionRoot.dataset.consumerSemantic, /:admitted:1:/);
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

test("RED-PROOF older async history cannot overwrite a newer canonical admission", async () => {
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const store = new JournalFirstRaceChatStore();
  const rendered = await renderComponent(ChatProduction, { store });
  try {
    const productionRoot = rendered.container.querySelector("main[data-route='chat']");
    const textarea = rendered.container.querySelector("textarea.chat-draft");
    const send = rendered.container.querySelector("button.chat-send");
    assert.ok(productionRoot);
    assert.ok(textarea);
    assert.ok(send);

    await setTextarea(rendered, textarea, "Journal-first race question");
    await click(rendered, send);
    assert.equal(store.sent.length, 1);
    assert.equal(typeof store.releaseOlderHistory, "function", "post-send history is held with the pre-admission snapshot");

    await rendered.act(async () => {
      store.admitCanonical("Journal-first race question");
      for (let index = 0; index < 8; index += 1) await Promise.resolve();
    });
    assert.equal(productionRoot.dataset.consumerChatAdmissionCount, "1");
    assert.equal(rendered.container.querySelectorAll(".chat-message").length, 2);
    assert.ok(rendered.container.textContent.includes("Canonical terminal answer"));
    assert.equal(rendered.container.querySelector(".chat-message.is-streaming"), null);

    await rendered.act(async () => {
      store.releaseOlderHistory();
      for (let index = 0; index < 8; index += 1) await Promise.resolve();
    });
    assert.equal(
      productionRoot.dataset.consumerChatAdmissionCount,
      "1",
      "a pre-admission response resolving last cannot roll rendered canonical admission backward",
    );
    assert.ok(rendered.container.textContent.includes("Journal-first race question"));
    assert.ok(
      rendered.container.textContent.includes("Canonical terminal answer"),
      "the older streaming projection cannot replace the canonical terminal assistant",
    );
    assert.equal(rendered.container.textContent.includes("Stale streaming answer"), false);
    assert.equal(rendered.container.querySelector(".chat-message.is-streaming"), null);
  } finally {
    await rendered.cleanup();
  }
});

test("stale post-send history rejection cannot surface an error after canonical admission", async () => {
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const store = new JournalFirstRaceChatStore();
  const rendered = await renderComponent(ChatProduction, { store });
  try {
    const productionRoot = rendered.container.querySelector("main[data-route='chat']");
    const textarea = rendered.container.querySelector("textarea.chat-draft");
    const send = rendered.container.querySelector("button.chat-send");
    assert.ok(productionRoot);
    assert.ok(textarea);
    assert.ok(send);

    await setTextarea(rendered, textarea, "Stale rejection race question");
    await click(rendered, send);
    assert.equal(typeof store.rejectOlderHistory, "function");

    await rendered.act(async () => {
      store.admitCanonical("Stale rejection race question");
      for (let index = 0; index < 8; index += 1) await Promise.resolve();
    });
    await rendered.act(async () => {
      store.currentStatus = {
        refresh: { phase: "unavailable", hasSavedData: true },
        queue: { phase: "idle", pendingCount: 0 },
      };
      store.rejectOlderHistory();
      for (let index = 0; index < 8; index += 1) await Promise.resolve();
    });
    assert.equal(productionRoot.dataset.consumerChatAdmissionCount, "1");
    assert.ok(rendered.container.textContent.includes("Canonical terminal answer"));
    assert.equal(rendered.container.querySelector("[role='alert']"), null);
    assert.equal(productionRoot.dataset.surfaceState, "ready");
    assert.equal(rendered.container.querySelector(".status-notice"), null);
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
  domain.admittedAttachments = [{
    id: "canonical-one",
    displayName: "normalized-report.pdf",
    mediaType: "application/pdf",
    sizeBytes: 100,
    contentReference: "opaque-content-one",
  }];
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
      [...rendered.container.querySelectorAll(".chat-attachments li .chat-attachment-meta")].map((item) => item.textContent),
      ["Attached application/pdf, 100 bytes", "Attached application/pdf, 200 bytes"],
      "staging cannot claim a durable server name that P7 did not return",
    );
    assert.deepEqual(
      [...rendered.container.querySelectorAll("[data-attachment-scan]")].map((item) => item.getAttribute("data-attachment-scan")),
      ["clean", "clean"],
    );
    assert.ok(
      [...rendered.container.querySelectorAll(".chat-attachment-scanner")].every(
        (item) => item.textContent === EN_MESSAGES["chat.attachmentScanner"],
      ),
    );
    assert.equal(EN_MESSAGES["chat.attachmentScanner"], "dev-noop-scanner");

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
    assert.equal(rendered.container.querySelector(".chat-attachments"), null);
    assert.ok(
      rendered.container.querySelector(".chat-message-attachments")?.textContent.includes(
        "normalized-report.pdf",
      ),
      "canonical admission metadata replaces the provisional staged description",
    );
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
    const describedBy = attach.getAttribute("aria-describedby");
    assert.ok(describedBy, "disabled Attach names the element carrying its reason");
    assert.equal(
      rendered.container.querySelector(`#${describedBy}`)?.textContent,
      EN_MESSAGES["chat.attachmentUnavailable"],
    );
    assert.equal(rendered.container.querySelector(".chat-attachments"), null);
  } finally {
    await rendered.cleanup();
  }
});

test("send failure preserves draft and staged descriptors and double submit is fenced", async () => {
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const createProductionChatStore = await loadProductionExport(
    "ProductionChatStore.ts",
    "createProductionChatStore",
  );
  const domain = new RenderedDomainChat();
  domain.sendFailure = new Error("enqueue failed");
  const announcementCallbacks = [];
  const announcementScheduler = {
    setTimeout(callback) { announcementCallbacks.push(callback); return callback; },
    clearTimeout() {},
  };
  const staging = {
    isAvailable: () => true,
    async pickAndStage() {
      return {
        id: "opaque-preserved",
        mimeType: "application/pdf",
        sizeBytes: 100,
        expiresAt: "2026-08-11T12:00:00.000Z",
        state: "staged",
      };
    },
  };
  const rendered = await renderComponent(ChatProduction, {
    store: createProductionChatStore(domain, staging),
    announcementScheduler,
  });
  try {
    await click(rendered, rendered.container.querySelector("button.chat-attach"));
    const textarea = rendered.container.querySelector("textarea.chat-draft");
    await setTextarea(rendered, textarea, "Keep this authored draft");
    await click(rendered, rendered.container.querySelector("button.chat-send"));
    assert.equal(textarea.value, "Keep this authored draft");
    assert.equal(rendered.container.querySelectorAll(".chat-attachments li").length, 1);
    assert.equal(rendered.container.querySelector(".lifecycle-retry"), null, "ready operation errors do not expose an unbound retry");
    assert.equal(rendered.container.querySelector(".lifecycle-next-action"), null, "ready operation errors do not announce an action without a bound control");
    assert.equal(rendered.container.querySelector(".production-operation-error")?.getAttribute("role"), "alert");
    assert.equal(announcementCallbacks.length, 0, "assertive operation error is not duplicated in the polite live region");

    let release;
    domain.sendFailure = null;
    domain.sendGate = new Promise((resolve) => { release = resolve; });
    await click(rendered, rendered.container.querySelector("button.chat-send"));
    await click(rendered, rendered.container.querySelector("button.chat-send"));
    assert.equal(domain.sent.length, 2, "one failed attempt plus one in-flight retry; double submit adds none");
    await setTextarea(rendered, textarea, "A new edit while enqueue is pending");
    await rendered.act(async () => { release(); await Promise.resolve(); });
    assert.equal(textarea.value, "A new edit while enqueue is pending", "successful old enqueue cannot clear a newer edit");
  } finally {
    await rendered.cleanup();
  }
});

test("two concurrent Attach clicks at cap one select exactly one unique descriptor", async () => {
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const createProductionChatStore = await loadProductionExport(
    "ProductionChatStore.ts",
    "createProductionChatStore",
  );
  const domain = new RenderedDomainChat();
  domain.caps = { ...domain.caps, maxAttachmentsPerMessage: 1 };
  const resolvers = [];
  let calls = 0;
  const staging = {
    isAvailable: () => true,
    pickAndStage() {
      calls += 1;
      return new Promise((resolve) => resolvers.push(resolve));
    },
  };
  const rendered = await renderComponent(ChatProduction, {
    store: createProductionChatStore(domain, staging),
  });
  try {
    const attach = rendered.container.querySelector("button.chat-attach");
    await click(rendered, attach);
    await click(rendered, attach);
    assert.equal(calls, 1, "the first native picker reserves the sole slot synchronously");
    await rendered.act(async () => {
      resolvers[0]({
        id: "opaque-only",
        mimeType: "application/pdf",
        sizeBytes: 100,
        expiresAt: "2026-08-11T12:00:00.000Z",
        state: "staged",
      });
      await Promise.resolve();
    });
    assert.equal(rendered.container.querySelectorAll(".chat-attachments li").length, 1);
    assert.equal(attach.disabled, true, "the reported cap is rechecked after completion");
  } finally {
    await rendered.cleanup();
  }
});

test("two sequential native picks with the same staged id leave one descriptor", async () => {
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const createProductionChatStore = await loadProductionExport(
    "ProductionChatStore.ts",
    "createProductionChatStore",
  );
  const domain = new RenderedDomainChat();
  const duplicate = {
    id: "opaque-duplicate",
    mimeType: "application/pdf",
    sizeBytes: 100,
    expiresAt: "2026-08-11T12:00:00.000Z",
    state: "staged",
  };
  const staging = {
    isAvailable: () => true,
    async pickAndStage() { return duplicate; },
  };
  const rendered = await renderComponent(ChatProduction, {
    store: createProductionChatStore(domain, staging),
  });
  try {
    const attach = rendered.container.querySelector("button.chat-attach");
    await click(rendered, attach);
    await click(rendered, attach);
    assert.equal(
      rendered.container.querySelectorAll(".chat-attachments li").length,
      1,
      "a repeated opaque staged id cannot enter the selected set twice",
    );
  } finally {
    await rendered.cleanup();
  }
});

test("canonical and expired attachment metadata render in newest and older messages", async () => {
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const createProductionChatStore = await loadProductionExport(
    "ProductionChatStore.ts",
    "createProductionChatStore",
  );
  const domain = new RenderedDomainChat();
  const newest = row("newest-human", "human", "Newest attachment");
  newest.attachments = [{
    id: "canonical-new",
    displayName: "normalized-new.pdf",
    mediaType: "application/pdf",
    sizeBytes: 321,
    contentReference: "opaque-content-new",
  }];
  const older = row("older-human", "human", "Older expired attachment");
  older.attachments = [{
    id: "canonical-old",
    displayName: "normalized-old.txt",
    mediaType: "text/plain",
    sizeBytes: 654,
    contentReference: null,
  }];
  domain.rows = [newest];
  domain.window = { hasOlder: true, olderCursor: "older-cursor" };
  domain.olderRows = [older];
  const rendered = await renderComponent(ChatProduction, {
    store: createProductionChatStore(domain),
  });
  try {
    let canonical = rendered.container.querySelector(".chat-message-attachments");
    assert.ok(canonical);
    assert.ok(canonical.textContent.includes("normalized-new.pdf"));
    assert.ok(canonical.textContent.includes("application/pdf"));
    assert.ok(canonical.textContent.includes("321"));
    await click(rendered, rendered.container.querySelector(".chat-history-controls button"));
    const lists = [...rendered.container.querySelectorAll(".chat-message-attachments")];
    assert.equal(lists.length, 2);
    assert.ok(lists[0].textContent.includes("normalized-old.txt"));
    assert.ok(lists[0].textContent.includes("text/plain"));
    assert.ok(lists[0].textContent.includes("654"));
    assert.ok(lists[0].textContent.includes(EN_MESSAGES["chat.attachmentContentUnavailable"]));
    assert.equal(lists[0].querySelector("a"), null);
    assert.equal(lists[0].querySelector("button"), null);
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
    assert.equal(failed.querySelector(".chat-failure-recovery"), null, "observer failure does not claim a provider retry path");

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
    const recovery = failed.querySelector(".chat-failure-recovery button");
    assert.ok(recovery, "retryable provider failure offers a truthful new-message recovery");
    assert.equal(failed.textContent.includes("does not rerun"), true);
    await click(rendered, recovery);
    const composer = rendered.container.querySelector("textarea.chat-draft");
    assert.equal(composer.value, "Question");
    assert.equal(rendered.window.document.activeElement, composer);
    assert.equal(domain.sent.length, 0, "recovery never silently resends or invents retry semantics");
    await setTextarea(rendered, composer, "   ");
    await click(rendered, recovery);
    assert.equal(composer.value, "   ", "recovery preserves even whitespace-only unsent drafts");
    await setTextarea(rendered, composer, "Keep this newer draft");
    await click(rendered, recovery);
    assert.equal(composer.value, "Keep this newer draft", "recovery never overwrites unsent composer work");
    await rendered.act(async () => {
      domain.deliveries = [{
        generationId: "provider-failed-unmatched",
        clientMessageId: "missing-human",
        terminal: { kind: "failed", error: { code: "provider_down", retryable: true } },
      }];
      domain.notify();
      await Promise.resolve();
    });
    assert.equal(
      rendered.container.querySelector(".chat-failure-recovery"),
      null,
      "a missing admitted human cannot render a recovery action that has no executable source",
    );
  } finally {
    await rendered.cleanup();
  }
});

test("unsupported native streaming renders bounded recovery guidance instead of an active run", async () => {
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const createProductionChatStore = await loadProductionExport(
    "ProductionChatStore.ts",
    "createProductionChatStore",
  );
  const domain = new RenderedDomainChat();
  domain.rows = [row("unsupported-human", "human", "Question")];
  domain.active = [{
    generationId: "unsupported-generation",
    clientMessageId: "unsupported-human",
    text: "",
    lastEventId: null,
    observationState: "failed",
    failure: "stream-unavailable",
  }];
  const rendered = await renderComponent(ChatProduction, {
    store: createProductionChatStore(domain),
  });
  try {
    const failed = rendered.container.querySelector(".chat-message.is-failed");
    assert.ok(failed);
    assert.equal(failed.getAttribute("aria-busy"), null);
    assert.equal(rendered.container.querySelector(".chat-message.is-streaming"), null);
    const recovery = failed.querySelector('[data-recovery="unsupported-stream"]');
    assert.ok(recovery, "unsupported native transport has an app-facing recovery state");
    assert.equal(recovery.textContent.includes(EN_MESSAGES["chat.liveUpdatesUnavailable"]), true);
    assert.equal(recovery.textContent.includes(EN_MESSAGES["chat.liveUpdatesUnavailableHint"]), true);
    assert.equal(recovery.querySelector("button"), null, "the UI does not invent a retry action the shell cannot perform");
  } finally {
    await rendered.cleanup();
  }
});

test("empty cancellation retains the human without fabricating a stopped assistant bubble", async () => {
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const createProductionChatStore = await loadProductionExport(
    "ProductionChatStore.ts",
    "createProductionChatStore",
  );
  const domain = new RenderedDomainChat();
  domain.rows = [row("cancelled-empty-human", "human", "Stop before content")];
  domain.deliveries = [{
    generationId: "cancelled-empty-generation",
    clientMessageId: "cancelled-empty-human",
    terminal: { kind: "cancelled", message: null },
  }];
  const rendered = await renderComponent(ChatProduction, {
    store: createProductionChatStore(domain),
  });
  try {
    const bubbles = [...rendered.container.querySelectorAll(".chat-message")];
    assert.equal(bubbles.length, 1);
    assert.equal(bubbles[0].dataset.delivery, "canonical");
    assert.equal(bubbles[0].classList.contains("is-user"), true);
    assert.equal(rendered.container.querySelector(".chat-message.is-assistant"), null);
    assert.equal(rendered.container.querySelector(".chat-message.is-cancelled"), null);
    assert.equal(rendered.container.textContent.includes(EN_MESSAGES["chat.stopped"]), false);
  } finally {
    await rendered.cleanup();
  }
});

test("Chat announces the latest terminal delivery without rereading the thread", async () => {
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const fixtureChatStore = await loadProductionExport("chat-fixtures.ts", "fixtureChatStore");
  const callbacks = [];
  const scheduler = {
    setTimeout(callback) { callbacks.push(callback); return callback; },
    clearTimeout() {},
  };
  const rendered = await renderComponent(ChatProduction, {
    store: fixtureChatStore("cancelled"),
    fixture: "cancelled",
    announcementScheduler: scheduler,
  });
  try {
    assert.equal(callbacks.length, 1);
    await rendered.act(async () => callbacks[0]());
    const announcement = rendered.container.querySelector('[data-live-region="true"]');
    assert.ok(announcement?.textContent?.includes(EN_MESSAGES["chat.stopped"]));
    assert.equal(announcement?.textContent?.includes(EN_MESSAGES["lifecycle.resultsCount"]), false);
  } finally {
    await rendered.cleanup();
  }
});

test("agent activity renders safe capability, context, two tools, approval status, recovery, usage, and terminal", async () => {
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const fixtureChatStore = await loadProductionExport("chat-fixtures.ts", "fixtureChatStore");
  const rendered = await renderComponent(ChatProduction, {
    store: fixtureChatStore("normal"),
    fixture: "normal",
  });
  try {
    const timeline = rendered.container.querySelector(".chat-agent-run");
    assert.ok(timeline);
    assert.equal(timeline.dataset.agentRunState, "complete");
    assert.ok(timeline.textContent.includes(EN_MESSAGES["chat.agentScripted"]));
    assert.equal(timeline.querySelectorAll('[data-agent-event="tool_request"]').length, 2);
    assert.equal(timeline.querySelectorAll('[data-agent-event="tool_result"]').length, 2);
    assert.equal(timeline.querySelectorAll('[data-agent-event="approval_requested"]').length, 1);
    assert.equal(timeline.querySelectorAll('[data-agent-event="recovery"]').length, 1);
    assert.equal(timeline.querySelectorAll('[data-agent-event="usage"]').length, 1);
    assert.equal(timeline.querySelectorAll('[data-agent-event="terminal"]').length, 1);
    assert.equal(timeline.querySelector("[data-approval-pending]"), null, "resolved approval does not keep Allow/Deny/Cancel");
    assert.doesNotMatch(
      timeline.textContent,
      /callId|approvalId|eventId|runId|opaque|rawArguments|chain.of.thought/iu,
    );
  } finally {
    await rendered.cleanup();
  }
});

test("successful gateway turn shows Context preview, a local test gateway, and no raw memory ids", async () => {
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const now = Date.UTC(2026, 7, 7, 12, 0, 0);
  const store = {
    status: () => status(),
    subscribe() { return () => {}; },
    async refresh() {},
    async history() {
      return {
        messages: [{
          role: "assistant",
          text: "Keep the review short.",
          delivery: {
            kind: "canonical",
            serverId: "gateway-success-assistant",
            clientMessageId: null,
            generationOutcome: "completed",
          },
          attachments: [],
          agentRun: {
            state: "complete",
            events: [
              {
                sequence: 1, createdAt: now, kind: "capability_receipt",
                safeSummary: "Loopback gateway declared",
                details: { tier: "unknown", adapter: "omi-llm-gateway", deterministic: false },
              },
              {
                sequence: 2, createdAt: now + 1, kind: "context_receipt",
                safeSummary: "Saved context selected",
                details: {
                  sourceKind: "memory",
                  redactedPreview: "Review checklist preference",
                  tokenEstimate: 18,
                  inclusionReason: "Relevant to the handoff question",
                  policyDecision: "included",
                },
              },
              {
                sequence: 3, createdAt: now + 2, kind: "terminal",
                safeSummary: "Response complete",
                details: {
                  terminalOutcome: "completed",
                  terminalCode: "completed",
                  retryable: false,
                  recoveryAction: null,
                },
              },
            ],
          },
        }],
        hasOlder: false,
        olderCursor: null,
      };
    },
    async loadOlder() { return { messages: [], hasOlder: false, olderCursor: null }; },
    async send() {},
    capabilities() {
      return { maxAttachmentsPerMessage: 2, maxAttachmentBytes: 10_000, allowedAttachmentMimeTypes: ["application/pdf"] };
    },
    stagingAvailable() { return false; },
    async stageAttachment() { return null; },
    async scanAttachment() { return "clean"; },
    async deadLetters() { return []; },
    async discardDeadLetter() {},
    async cancel() {},
    async resolveApproval() {},
  };
  const rendered = await renderComponent(ChatProduction, { store });
  try {
    const timeline = rendered.container.querySelector(".chat-agent-run");
    assert.ok(timeline);
    assert.ok(timeline.textContent.includes(EN_MESSAGES["chat.agentLocalTestGateway"]));
    assert.equal(timeline.textContent.includes(EN_MESSAGES["chat.agentUnknown"]), false);
    assert.equal(timeline.textContent.includes(EN_MESSAGES["chat.agentProvider"]), false);
    assert.equal(timeline.textContent.includes(EN_MESSAGES["chat.agentScripted"]), false);
    assert.ok(timeline.textContent.includes("Context: Review checklist preference"));
    assert.doesNotMatch(timeline.textContent, /mem1_|cit1_/u);
    assert.doesNotMatch(rendered.container.textContent, /mem1_|cit1_/u);
  } finally {
    await rendered.cleanup();
  }
});

test("pending approval shows Allow, Deny, and Cancel that call resolveApproval", async () => {
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const now = Date.UTC(2026, 7, 7, 12, 0, 0);
  const resolutions = [];
  let history = {
    messages: [{
      role: "assistant",
      text: "Waiting for a scoped approval.",
      delivery: {
        kind: "canonical",
        serverId: "approval-pending-assistant",
        clientMessageId: null,
        generationOutcome: null,
      },
      attachments: [],
      agentRun: {
        state: "observing",
        events: [
          {
            sequence: 1, createdAt: now, kind: "capability_receipt",
            safeSummary: "Loopback gateway declared",
            details: { tier: "unknown", adapter: "omi-llm-gateway", deterministic: false },
          },
          {
            sequence: 2, createdAt: now + 1, kind: "approval_requested",
            safeSummary: "Approval requested for a scoped write",
            details: { reason: "A scoped approval is required.", expiresAt: now + 60_000 },
          },
        ],
      },
    }],
    hasOlder: false,
    olderCursor: null,
  };
  const listeners = new Set();
  const store = {
    status: () => status(),
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    async refresh() {},
    async history() { return history; },
    async loadOlder() { return { messages: [], hasOlder: false, olderCursor: null }; },
    async send() {},
    capabilities() {
      return { maxAttachmentsPerMessage: 2, maxAttachmentBytes: 10_000, allowedAttachmentMimeTypes: ["application/pdf"] };
    },
    stagingAvailable() { return false; },
    async stageAttachment() { return null; },
    async scanAttachment() { return "clean"; },
    async deadLetters() { return []; },
    async discardDeadLetter() {},
    async cancel() {},
    async resolveApproval(resolution) {
      resolutions.push(resolution);
      const events = history.messages[0].agentRun.events;
      history = {
        ...history,
        messages: [{
          ...history.messages[0],
          agentRun: {
            state: "observing",
            events: [
              ...events,
              {
                sequence: 3, createdAt: now + 2, kind: "approval_resolved",
                safeSummary: "Approval resolved",
                details: { resolution },
              },
            ],
          },
        }],
      };
      for (const listener of listeners) listener();
    },
  };
  const rendered = await renderComponent(ChatProduction, { store });
  try {
    const pending = rendered.container.querySelector("[data-approval-pending]");
    assert.ok(pending);
    assert.equal(pending.querySelector('[data-approval-action="approved"]').textContent, EN_MESSAGES["chat.agentApprovalAllow"]);
    assert.equal(pending.querySelector('[data-approval-action="denied"]').textContent, EN_MESSAGES["chat.agentApprovalDeny"]);
    assert.equal(pending.querySelector('[data-approval-action="cancelled"]').textContent, EN_MESSAGES["common.cancel"]);
    await click(rendered, pending.querySelector('[data-approval-action="denied"]'));
    assert.deepEqual(resolutions, ["denied"]);
    assert.equal(rendered.container.querySelector("[data-approval-pending]"), null);
  } finally {
    await rendered.cleanup();
  }
});

test("retained dead send shows authored text and a safe attachment count with discard only", async () => {
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
    assert.ok(panel.textContent.includes("2 attachments"));
    assert.equal(panel.textContent.includes("opaque-one"), false);
    assert.equal(panel.textContent.includes("opaque-two"), false);
    assert.equal(panel.querySelector("code"), null);
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

function stagedDescriptor(id = "opaque-scan") {
  return {
    id,
    mimeType: "application/pdf",
    sizeBytes: 100,
    expiresAt: "2026-08-11T12:00:00.000Z",
    state: "staged",
  };
}

test("scanning attachments stay fail-closed, name the noop scanner, and remain removable", async () => {
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const createProductionChatStore = await loadProductionExport(
    "ProductionChatStore.ts",
    "createProductionChatStore",
  );
  const domain = new RenderedDomainChat();
  const staging = {
    isAvailable: () => true,
    async pickAndStage() { return stagedDescriptor(); },
  };
  let releaseScan;
  const store = createProductionChatStore(domain, staging);
  store.scanAttachment = () => new Promise((resolve) => {
    releaseScan = () => resolve("clean");
  });
  const rendered = await renderComponent(ChatProduction, { store });
  try {
    await click(rendered, rendered.container.querySelector("button.chat-attach"));
    const item = rendered.container.querySelector("[data-attachment-scan]");
    assert.ok(item);
    assert.equal(item.getAttribute("data-attachment-scan"), "scanning");
    assert.equal(item.getAttribute("data-attachment-scanner"), "dev-noop-scanner");
    assert.equal(item.querySelector(".chat-attachment-scan")?.textContent, EN_MESSAGES["chat.attachmentScanning"]);
    assert.equal(item.querySelector(".chat-attachment-scanner")?.textContent, "dev-noop-scanner");
    assert.equal(item.querySelector("[data-attachment-scan-retry]"), null);
    assert.ok(item.querySelector('[aria-label="' + EN_MESSAGES["chat.attachmentRemove"] + '"]'));
    const textarea = rendered.container.querySelector("textarea.chat-draft");
    await setTextarea(rendered, textarea, "Cannot send while scanning");
    assert.equal(rendered.container.querySelector("button.chat-send").disabled, true);
    assert.equal(/antivirus|\bmalware\b|\bvirus\b/i.test(rendered.container.textContent), false);

    await click(rendered, item.querySelector('[aria-label="' + EN_MESSAGES["chat.attachmentRemove"] + '"]'));
    assert.equal(rendered.container.querySelector(".chat-attachments"), null);
    await rendered.act(async () => {
      releaseScan();
      for (let index = 0; index < 8; index += 1) await Promise.resolve();
    });
    assert.equal(rendered.container.querySelector(".chat-attachments"), null, "a removed row ignores a late scan result");
  } finally {
    await rendered.cleanup();
  }
});

test("rejected, timed_out, and error scans retry into scanning and only clean can send", async () => {
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const createProductionChatStore = await loadProductionExport(
    "ProductionChatStore.ts",
    "createProductionChatStore",
  );
  const labels = {
    rejected: EN_MESSAGES["chat.attachmentRejected"],
    timed_out: EN_MESSAGES["chat.attachmentTimedOut"],
    error: EN_MESSAGES["chat.attachmentScanError"],
  };
  for (const failed of ["rejected", "timed_out", "error"]) {
    const domain = new RenderedDomainChat();
    const staging = {
      isAvailable: () => true,
      async pickAndStage() { return stagedDescriptor(`opaque-${failed}`); },
    };
    let nextOutcome = failed;
    let releaseScan;
    const store = createProductionChatStore(domain, staging);
    store.scanAttachment = () => {
      if (nextOutcome === "hold") {
        return new Promise((resolve) => {
          releaseScan = () => resolve("clean");
        });
      }
      return Promise.resolve(nextOutcome);
    };
    const rendered = await renderComponent(ChatProduction, { store });
    try {
      await click(rendered, rendered.container.querySelector("button.chat-attach"));
      const item = rendered.container.querySelector("[data-attachment-scan]");
      assert.ok(item, failed);
      assert.equal(item.getAttribute("data-attachment-scan"), failed);
      assert.equal(item.querySelector(".chat-attachment-scan")?.textContent, labels[failed]);
      assert.equal(item.querySelector(".chat-attachment-scanner")?.textContent, "dev-noop-scanner");
      const retry = item.querySelector("[data-attachment-scan-retry]");
      assert.ok(retry, `${failed} must offer retry`);
      const textarea = rendered.container.querySelector("textarea.chat-draft");
      await setTextarea(rendered, textarea, "Still blocked");
      assert.equal(rendered.container.querySelector("button.chat-send").disabled, true);
      assert.equal(domain.sent.length, 0);

      nextOutcome = "hold";
      await click(rendered, retry);
      assert.equal(
        rendered.container.querySelector("[data-attachment-scan]")?.getAttribute("data-attachment-scan"),
        "scanning",
      );
      assert.equal(rendered.container.querySelector("[data-attachment-scan-retry]"), null);
      await rendered.act(async () => {
        releaseScan();
        for (let index = 0; index < 8; index += 1) await Promise.resolve();
      });
      assert.equal(
        rendered.container.querySelector("[data-attachment-scan]")?.getAttribute("data-attachment-scan"),
        "clean",
      );
      assert.equal(rendered.container.querySelector("button.chat-send").disabled, false);
      await click(rendered, rendered.container.querySelector("button.chat-send"));
      assert.deepEqual(domain.sent, [{
        text: "Still blocked",
        attachmentIds: [`opaque-${failed}`],
      }]);
    } finally {
      await rendered.cleanup();
    }
  }
});

test("unknown scan outcomes fail closed as error and never claim a bind", async () => {
  const ChatProduction = await loadProductionExport("ChatProduction.tsx", "ChatProduction");
  const createProductionChatStore = await loadProductionExport(
    "ProductionChatStore.ts",
    "createProductionChatStore",
  );
  const domain = new RenderedDomainChat();
  const staging = {
    isAvailable: () => true,
    async pickAndStage() { return stagedDescriptor("opaque-unknown"); },
  };
  const store = createProductionChatStore(domain, staging);
  store.scanAttachment = async () => "antivirus-clean";
  const rendered = await renderComponent(ChatProduction, { store });
  try {
    await click(rendered, rendered.container.querySelector("button.chat-attach"));
    const item = rendered.container.querySelector("[data-attachment-scan]");
    assert.equal(item?.getAttribute("data-attachment-scan"), "error");
    assert.equal(item?.querySelector(".chat-attachment-scan")?.textContent, EN_MESSAGES["chat.attachmentScanError"]);
    const textarea = rendered.container.querySelector("textarea.chat-draft");
    await setTextarea(rendered, textarea, "Unknown scanner result");
    assert.equal(rendered.container.querySelector("button.chat-send").disabled, true);
    assert.equal(domain.sent.length, 0);
    assert.equal(rendered.container.textContent.includes("antivirus-clean"), false);
  } finally {
    await rendered.cleanup();
  }
});
