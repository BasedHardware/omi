import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import test, { after } from "node:test";
import { fileURLToPath } from "node:url";

import { createPlatformListenCaptureClient } from "@omi-core/adapters-platform";
import { EN_MESSAGES, formatDuration, t } from "@omi-core/i18n";
import { createPlatformProductionListenStore } from "../src/production/createPlatformListenStore.ts";
import {
  closeRenderHarness,
  loadProductionExport,
  renderComponent,
} from "./render-harness.mjs";

after(closeRenderHarness);

const HERE = dirname(fileURLToPath(import.meta.url));
const CORE_ROOT = resolve(HERE, "../../..");
const schema = JSON.parse(await readFile(
  resolve(CORE_ROOT, "contracts/wire/listen/listen-protocol.schema.json"),
  "utf8",
));
const corpus = JSON.parse(await readFile(
  resolve(CORE_ROOT, "packages/wire-listen/fixtures/corpus.json"),
  "utf8",
));
const entitlementPauseFrame = corpus.scenarios
  .find((scenario) => scenario.name === "entitlement-paused-capture-continues")
  .frames.find((frame) => frame.json?.type === "entitlement").json;
const readyFrame = corpus.scenarios
  .flatMap((scenario) => scenario.frames)
  .find((frame) => frame.json?.type === "service_status" && frame.json.status === "ready").json;

class FakeSocket {
  #listeners = new Map();

  addEventListener(type, listener) {
    const listeners = this.#listeners.get(type) ?? [];
    listeners.push(listener);
    this.#listeners.set(type, listeners);
  }

  #emit(type, event = {}) {
    for (const listener of this.#listeners.get(type) ?? []) listener(event);
  }

  open() { this.#emit("open"); }
  message(data) { this.#emit("message", { data }); }
  error() { this.#emit("error"); }
  serverClose(code) { this.#emit("close", { code }); }
  close(code = 1000) { this.#emit("close", { code }); }
}

function wireStore() {
  let now = 0;
  let random = 0;
  const sockets = [];
  const paths = [];
  const delayed = [];
  const sink = { record() {} };
  const env = {
    fallbackSink: sink,
    now: () => now,
    random: () => ((random += 0.03125) % 1),
    delay(ms, callback) {
      const pending = { active: true, callback, ms };
      delayed.push(pending);
      return () => { pending.active = false; };
    },
  };
  const client = createPlatformListenCaptureClient({
    env,
    schema,
    reconnectDelayMs: 2_000,
    openSocket(path) {
      paths.push(path);
      const socket = new FakeSocket();
      sockets.push(socket);
      return socket;
    },
  });
  return {
    env,
    store: createPlatformProductionListenStore(client, env),
    sockets,
    paths,
    setNow(value) { now = value; },
    runReconnect() {
      const pending = delayed.find((entry) => entry.active && entry.ms === 2_000);
      assert.ok(pending, "transport scheduled a reconnect");
      pending.active = false;
      pending.callback();
    },
    runTick() {
      const pending = delayed.find((entry) => entry.active && entry.ms === 1_000);
      assert.ok(pending, "surface store scheduled an observable clock tick");
      pending.active = false;
      pending.callback();
    },
  };
}

function stateStore(capture, options = {}) {
  const status = options.status ?? {
    refresh: { phase: "ready", hasSavedData: false },
    queue: { phase: "idle", pendingCount: 0 },
  };
  let refreshes = 0;
  return {
    status: () => status,
    subscribe: () => () => {},
    async refresh() { refreshes += 1; },
    captureState: () => capture,
    transcriptSegments: () => options.segments ?? [],
    entitlementState: () => options.entitlement ?? null,
    async start() {},
    async stop() {},
    refreshes: () => refreshes,
  };
}

function segment(id, text, start, end) {
  return { id, text, is_user: true, start, end };
}

test("each capture state renders state-specific copy, glyph, and interpolated measurements", async () => {
  const ListenProduction = await loadProductionExport("ListenProduction.tsx", "ListenProduction");
  const cases = [
    [{ kind: "idle" }, "listen.stateIdle", false],
    [{ kind: "capturing", elapsedSeconds: 10 }, "listen.stateCapturing", false],
    [{ kind: "paused-for-entitlement", elapsedSeconds: 20, untranscribedSeconds: 30 }, "listen.statePausedEntitlement", false],
    [{ kind: "offline-buffering", elapsedSeconds: 40, bufferedSeconds: 10, untranscribedSeconds: 50 }, "listen.stateOfflineBuffering", false],
    [{ kind: "stopped-at-ceiling", untranscribedSeconds: 70 }, "listen.stateStoppedAtCeiling", true],
    [{ kind: "error", retryable: false, untranscribedSeconds: 80 }, "listen.errorTitle", true],
  ];
  const renderedTitles = [];

  for (const [capture, titleKey, loud] of cases) {
    const rendered = await renderComponent(ListenProduction, { store: stateStore(capture) });
    try {
      const panel = rendered.container.querySelector(".listen-state-panel");
      assert.ok(panel, `${capture.kind} renders a state panel`);
      assert.equal(panel.getAttribute("data-presentation"), capture.kind);
      assert.equal(panel.getAttribute("role"), null, "elapsed/buffered counters are not a live region");
      const announcement = rendered.container.querySelector('[data-live-region="true"]');
      assert.ok(announcement, "capture state has one deduplicated live announcement");
      assert.equal(announcement.getAttribute("role"), "status");
      assert.ok(panel.querySelector(`.listen-state-glyph.is-${capture.kind}`), `${capture.kind} renders its designed state glyph`);
      const title = panel.querySelector(".listen-state-title")?.textContent;
      assert.equal(title, EN_MESSAGES[titleKey]);
      renderedTitles.push(title);
      const pauseControl = [...rendered.container.querySelectorAll("button")]
        .find((button) => /pause/i.test(`${button.textContent} ${button.getAttribute("aria-label") ?? ""}`));
      assert.equal(pauseControl, undefined, `${capture.kind} does not fabricate a pause control`);
      if ("elapsedSeconds" in capture) {
        assert.equal(
          panel.querySelector(".listen-elapsed")?.textContent,
          t("en", "listen.elapsed", { duration: formatDuration(capture.elapsedSeconds, "en") }),
        );
      }
      if (capture.kind === "offline-buffering") {
        assert.equal(
          panel.querySelector(".listen-buffered")?.textContent,
          t("en", "listen.buffered", { duration: formatDuration(capture.bufferedSeconds, "en") }),
        );
      }
      if ("untranscribedSeconds" in capture) {
        assert.equal(
          panel.querySelector(".listen-backlog-value")?.textContent,
          t("en", "listen.backlogHours", { hours: 1 }),
        );
      }
    } finally {
      await rendered.cleanup();
    }
  }
  assert.equal(new Set(renderedTitles).size, 6);
  // red-proof: remove any state-specific data-presentation/glyph/title branch;
  // the rendered DOM assertion for that arm fails, even if describeCapture remains correct.
});

test("Listen batches transcript text into the single state announcement", async () => {
  const ListenProduction = await loadProductionExport("ListenProduction.tsx", "ListenProduction");
  const callbacks = [];
  const scheduler = {
    setTimeout(callback) { callbacks.push(callback); return callback; },
    clearTimeout() {},
  };
  const rendered = await renderComponent(ListenProduction, {
    store: stateStore({ kind: "capturing", elapsedSeconds: 4 }, {
      segments: [segment("one", "A short transcript", 0, 1), segment("two", "with a second phrase", 1, 2)],
    }),
    announcementScheduler: scheduler,
  });
  try {
    assert.equal(callbacks.length, 1, "the initial state and transcript are one debounced update");
    await rendered.act(async () => callbacks[0]());
    const announcement = rendered.container.querySelector('[data-live-region="true"]');
    assert.ok(announcement?.textContent?.includes("A short transcript with a second phrase"));
    assert.equal(rendered.container.querySelector(".listen-state-panel")?.getAttribute("role"), null);
  } finally {
    await rendered.cleanup();
  }
});

test("reconnect redelivery renders one row with the revision text", async () => {
  const ListenProduction = await loadProductionExport("ListenProduction.tsx", "ListenProduction");
  const wire = wireStore();
  await wire.store.start();
  wire.sockets[0].open();
  wire.sockets[0].message(JSON.stringify(readyFrame));
  wire.sockets[0].message(JSON.stringify([segment("same", "draft", 0, 1)]));
  wire.sockets[0].serverClose(1001);
  wire.runReconnect();
  wire.sockets[1].open();
  wire.sockets[1].message(JSON.stringify(readyFrame));
  wire.sockets[1].message(JSON.stringify([segment("same", "final wording", 0, 1.5)]));

  const firstResumeId = new URL(`http://local${wire.paths[0]}`).searchParams.get("client_conversation_id");
  const secondResumeId = new URL(`http://local${wire.paths[1]}`).searchParams.get("client_conversation_id");
  assert.match(wire.paths[0], /^\/v4\/listen\?/);
  assert.equal(new URL(`http://local${wire.paths[0]}`).searchParams.get("token"), null);
  assert.equal(new URL(`http://local${wire.paths[0]}`).searchParams.get("uid"), null);
  assert.equal(firstResumeId, secondResumeId, "reconnect keeps the logical capture resume id");

  const rendered = await renderComponent(ListenProduction, { store: wire.store });
  try {
    const rows = rendered.container.querySelectorAll("[data-segment-id='same']");
    assert.equal(rows.length, 1, "same segment id renders once after redelivery");
    assert.equal(rows[0].querySelector(".listen-transcript-text")?.textContent, "final wording");
  } finally {
    await rendered.cleanup();
  }
  // red-proof: render arrivals directly instead of the typed port snapshot;
  // rows.length becomes 2 and the revision is not the sole rendered text.
});

test("out-of-order wire segments paint in content order", async () => {
  const ListenProduction = await loadProductionExport("ListenProduction.tsx", "ListenProduction");
  const wire = wireStore();
  await wire.store.start();
  wire.sockets[0].open();
  wire.sockets[0].message(JSON.stringify(readyFrame));
  wire.sockets[0].message(JSON.stringify([segment("later", "Second in the conversation", 4, 5)]));
  wire.sockets[0].message(JSON.stringify([segment("earlier", "First in the conversation", 0, 1)]));

  const rendered = await renderComponent(ListenProduction, { store: wire.store });
  try {
    const rows = [...rendered.container.querySelectorAll(".listen-transcript-row")];
    assert.deepEqual(
      rows.map((row) => row.getAttribute("data-segment-id")),
      ["earlier", "later"],
    );
    assert.deepEqual(
      rows.map((row) => row.querySelector(".listen-transcript-text")?.textContent),
      ["First in the conversation", "Second in the conversation"],
    );
  } finally {
    await rendered.cleanup();
  }
  // red-proof: render arrival order; both DOM arrays reverse.
});

test("rendered Listen evidence bounds four non-ASCII segments by UTF-8 bytes without splitting scalars", async () => {
  const boundedRenderedTranscript = await loadProductionExport(
    "consumer-observation.ts",
    "boundedRenderedTranscript",
  );
  const segments = ["😀", "界", "é", "🧭"].map((value) => ({ text: value.repeat(300) }));
  const transcript = boundedRenderedTranscript(segments);
  assert.notEqual(transcript, "");
  assert.ok(Buffer.byteLength(transcript, "utf8") <= 1_024);
  assert.doesNotMatch(transcript, /\uFFFD/u, "UTF-8 truncation must not split a Unicode scalar");
  for (const value of ["😀", "界", "é", "🧭"]) {
    assert.ok(transcript.includes(value), `bounded evidence retains the ${value} segment`);
  }

  assert.equal(
    boundedRenderedTranscript([
      { text: " ignored because only the last four survive " },
      { text: " alpha   beta " },
      { text: "gamma" },
      { text: "delta" },
      { text: "x".repeat(300) },
    ]),
    `alpha beta gamma delta ${"x".repeat(240)}`,
    "ASCII evidence remains byte-identical",
  );
});

test("entitlement pause and ceiling stop stay distinct and neither renders idle", async () => {
  const ListenProduction = await loadProductionExport("ListenProduction.tsx", "ListenProduction");
  const paused = wireStore();
  await paused.store.start();
  paused.sockets[0].open();
  paused.sockets[0].message(JSON.stringify(readyFrame));
  paused.sockets[0].message(JSON.stringify(entitlementPauseFrame));
  paused.sockets[0].serverClose(4020);

  const stopped = wireStore();
  await stopped.store.start();
  stopped.sockets[0].open();
  stopped.sockets[0].serverClose(4020);

  const pausedRender = await renderComponent(ListenProduction, { store: paused.store });
  try {
    const panel = pausedRender.container.querySelector(".listen-state-panel");
    assert.equal(panel?.getAttribute("data-presentation"), "stopped-at-ceiling");
    assert.equal(panel?.querySelector(".listen-state-title")?.textContent, EN_MESSAGES["listen.stateStoppedAtCeiling"]);
    assert.notEqual(panel?.querySelector(".listen-state-title")?.textContent, EN_MESSAGES["listen.stateIdle"]);
    assert.equal(panel?.getAttribute("data-capturing"), "false", "terminal close invalidates a stale continuing pause");
  } finally {
    await pausedRender.cleanup();
  }

  const stoppedRender = await renderComponent(ListenProduction, { store: stopped.store });
  try {
    const panel = stoppedRender.container.querySelector(".listen-state-panel");
    assert.equal(panel?.getAttribute("data-presentation"), "stopped-at-ceiling");
    assert.equal(panel?.querySelector(".listen-state-title")?.textContent, EN_MESSAGES["listen.stateStoppedAtCeiling"]);
    assert.notEqual(panel?.querySelector(".listen-state-title")?.textContent, EN_MESSAGES["listen.stateIdle"]);
    assert.equal(panel?.getAttribute("role"), null);
    assert.equal(panel?.getAttribute("data-capturing"), "false");
  } finally {
    await stoppedRender.cleanup();
  }
  // red-proof: fold either branch to idle (or both to one generic limit state);
  // the two rendered data-presentations and named titles fail independently.
});

test("reconnect content waits for protocol ready before leaving offline buffering", async () => {
  const ListenProduction = await loadProductionExport("ListenProduction.tsx", "ListenProduction");
  const wire = wireStore();
  await wire.store.start();
  wire.sockets[0].open();
  wire.sockets[0].message(JSON.stringify(readyFrame));
  wire.sockets[0].message(JSON.stringify([segment("before", "Before disconnect", 0, 1)]));
  wire.sockets[0].serverClose(1001);
  wire.runReconnect();
  wire.sockets[1].open();
  wire.sockets[1].message(JSON.stringify([segment("too-early", "Must not render yet", 2, 3)]));

  const rendered = await renderComponent(ListenProduction, { store: wire.store });
  try {
    assert.equal(rendered.container.querySelector(".listen-state-panel")?.getAttribute("data-presentation"), "offline-buffering");
    assert.equal(rendered.container.querySelector("[data-segment-id='too-early']"), null);
    await rendered.act(async () => {
      wire.sockets[1].message(JSON.stringify(readyFrame));
      wire.sockets[1].message(JSON.stringify([segment("after-ready", "Safe to render", 3, 4)]));
    });
    assert.equal(rendered.container.querySelector(".listen-state-panel")?.getAttribute("data-presentation"), "capturing");
    assert.equal(rendered.container.querySelector("[data-segment-id='after-ready'] .listen-transcript-text")?.textContent, "Safe to render");
  } finally {
    await rendered.cleanup();
  }
  // red-proof: set the transport active on socket open or accept transcript_batch
  // before service_status:ready; the first presentation/row assertions fail.
});

test("a permanent protocol close strands backlog and exposes no working Retry", async () => {
  const ListenProduction = await loadProductionExport("ListenProduction.tsx", "ListenProduction");
  const wire = wireStore();
  await wire.store.start();
  wire.sockets[0].open();
  wire.sockets[0].message(JSON.stringify(readyFrame));
  wire.sockets[0].message(JSON.stringify([segment("partial", "Only ten seconds transcribed", 0, 10)]));
  wire.setNow(70_000);
  wire.sockets[0].serverClose(1008);

  const rendered = await renderComponent(ListenProduction, { store: wire.store });
  try {
    assert.equal(rendered.container.querySelector(".listen-state-panel")?.getAttribute("data-presentation"), "error");
    assert.equal(
      rendered.container.querySelector(".listen-backlog-value")?.textContent,
      t("en", "listen.backlogHours", { hours: 1 }),
    );
    const retry = [...rendered.container.querySelectorAll("button")]
      .find((button) => button.textContent === EN_MESSAGES["common.retry"]);
    assert.equal(retry, undefined, "non-retryable close does not expose Retry");
    await rendered.act(async () => wire.store.refresh());
    assert.equal(wire.sockets.length, 1, "refresh cannot reopen a protocol-refused capture");
  } finally {
    await rendered.cleanup();
  }
  // red-proof: render the generic refresh Retry or zero the error backlog;
  // the rendered button/backlog assertions fail, and an unguarded refresh opens socket 2.
});

test("elapsed and buffered clocks tick while live, then ceiling backlog freezes", async () => {
  const ListenProduction = await loadProductionExport("ListenProduction.tsx", "ListenProduction");
  const wire = wireStore();
  await wire.store.start();
  wire.sockets[0].open();
  wire.sockets[0].message(JSON.stringify(readyFrame));
  const rendered = await renderComponent(ListenProduction, { store: wire.store });
  try {
    wire.setNow(60_000);
    await rendered.act(async () => wire.runTick());
    assert.equal(
      rendered.container.querySelector(".listen-elapsed")?.textContent,
      t("en", "listen.elapsed", { duration: formatDuration(60, "en") }),
    );

    await rendered.act(async () => wire.sockets[0].serverClose(1001));
    wire.setNow(72_000);
    await rendered.act(async () => wire.runTick());
    assert.equal(
      rendered.container.querySelector(".listen-buffered")?.textContent,
      t("en", "listen.buffered", { duration: formatDuration(12, "en") }),
    );

    await rendered.act(async () => {
      wire.runReconnect();
      wire.sockets[1].open();
      wire.sockets[1].message(JSON.stringify(readyFrame));
    });
    wire.setNow(75_000);
    await rendered.act(async () => wire.sockets[1].serverClose(4020));
    const frozen = rendered.container.querySelector(".listen-backlog-value")?.textContent;
    wire.setNow(7_275_000);
    assert.throws(() => wire.runTick(), /observable clock tick/, "terminal ceiling cancels its clock");
    await rendered.act(async () => wire.store.refresh());
    assert.equal(rendered.container.querySelector(".listen-backlog-value")?.textContent, frozen);
  } finally {
    await rendered.cleanup();
  }
  // red-proof: remove store-owned ticks or the terminal stoppedAt snapshot;
  // elapsed/buffered stay stale or the backlog changes after the ceiling.
});

test("socket error without close renders offline buffering and schedules recovery", async () => {
  const ListenProduction = await loadProductionExport("ListenProduction.tsx", "ListenProduction");
  const wire = wireStore();
  await wire.store.start();
  wire.sockets[0].open();
  wire.sockets[0].message(JSON.stringify(readyFrame));
  wire.sockets[0].error();
  const rendered = await renderComponent(ListenProduction, { store: wire.store });
  try {
    assert.equal(rendered.container.querySelector(".listen-state-panel")?.getAttribute("data-presentation"), "offline-buffering");
    await rendered.act(async () => wire.runReconnect());
    assert.equal(wire.sockets.length, 2);
  } finally {
    await rendered.cleanup();
  }
  // red-proof: leave the error listener as a retryability-only write;
  // the rendered presentation remains capturing and no reconnect exists.
});

test("loading and unknown entitlement limits make distinct honest claims", async () => {
  const ListenProduction = await loadProductionExport("ListenProduction.tsx", "ListenProduction");
  const loadingStore = stateStore(
    { kind: "idle" },
    { status: { refresh: { phase: "refreshing", hasSavedData: false }, queue: { phase: "idle", pendingCount: 0 } } },
  );
  const loading = await renderComponent(ListenProduction, { store: loadingStore });
  try {
    assert.equal(loading.container.querySelector(".listen-state-panel")?.getAttribute("data-presentation"), "loading");
    assert.equal(loading.container.querySelector(".listen-state-title")?.textContent, EN_MESSAGES["listen.stateLoading"]);
    assert.notEqual(loading.container.querySelector(".listen-state-title")?.textContent, EN_MESSAGES["listen.stateIdle"]);
  } finally {
    await loading.cleanup();
  }

  const entitlement = {
    source: "entitlement",
    status: "approaching_limit",
    captureContinuing: true,
    remaining: null,
    usage: { amount: 90, unit: "seconds" },
    limit: { kind: "unknown" },
    reason: null,
    upgradeTarget: null,
    suggestedAction: null,
  };
  const unknown = await renderComponent(ListenProduction, {
    store: stateStore({ kind: "capturing", elapsedSeconds: 90 }, { entitlement }),
  });
  try {
    const label = unknown.container.querySelector(".listen-entitlement-usage")?.textContent;
    assert.equal(label, t("en", "listen.usageUnknownLimit", { used: formatDuration(90, "en") }));
    assert.notEqual(label, t("en", "settings.usageUnmetered", { used: formatDuration(90, "en") }));
  } finally {
    await unknown.cleanup();
  }
  // red-proof: fall loading through to idle or group unknown with unmetered;
  // the rendered title/usage assertions fail independently.
});
