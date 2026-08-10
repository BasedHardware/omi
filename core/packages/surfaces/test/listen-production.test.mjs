import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import test, { after } from "node:test";
import { fileURLToPath } from "node:url";

import { createPlatformListenCaptureClient } from "@omi-core/adapters-platform";
import { EN_MESSAGES } from "@omi-core/i18n";
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
    delay(_ms, callback) {
      const pending = { active: true, callback };
      delayed.push(pending);
      return () => { pending.active = false; };
    },
  };
  const client = createPlatformListenCaptureClient({
    env,
    schema,
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
      const pending = delayed.find((entry) => entry.active);
      assert.ok(pending, "transport scheduled a reconnect");
      pending.active = false;
      pending.callback();
    },
  };
}

function stateStore(capture) {
  const status = {
    refresh: { phase: "ready", hasSavedData: false },
    queue: { phase: "idle", pendingCount: 0 },
  };
  return {
    status: () => status,
    subscribe: () => () => {},
    async refresh() {},
    captureState: () => capture,
    transcriptSegments: () => [],
    entitlementState: () => null,
    async start() {},
    async stop() {},
  };
}

function segment(id, text, start, end) {
  return { id, text, is_user: true, start, end };
}

test("each of the six capture states renders its named designed presentation", async () => {
  const ListenProduction = await loadProductionExport("ListenProduction.tsx", "ListenProduction");
  const cases = [
    [{ kind: "idle" }, "listen.stateIdle", false],
    [{ kind: "capturing", elapsedSeconds: 10 }, "listen.stateCapturing", false],
    [{ kind: "paused-for-entitlement", elapsedSeconds: 20, untranscribedSeconds: 30 }, "listen.statePausedEntitlement", false],
    [{ kind: "offline-buffering", elapsedSeconds: 40, bufferedSeconds: 10, untranscribedSeconds: 50 }, "listen.stateOfflineBuffering", false],
    [{ kind: "stopped-at-ceiling", untranscribedSeconds: 70 }, "listen.stateStoppedAtCeiling", true],
    [{ kind: "error", retryable: false }, "listen.errorTitle", true],
  ];
  const renderedTitles = [];

  for (const [capture, titleKey, loud] of cases) {
    const rendered = await renderComponent(ListenProduction, { store: stateStore(capture) });
    try {
      const panel = rendered.container.querySelector(".listen-state-panel");
      assert.ok(panel, `${capture.kind} renders a state panel`);
      assert.equal(panel.getAttribute("data-presentation"), capture.kind);
      assert.equal(panel.getAttribute("role"), loud ? "alert" : "status");
      assert.ok(panel.querySelector(".listen-state-glyph"), `${capture.kind} renders its designed state glyph`);
      const title = panel.querySelector(".listen-state-title")?.textContent;
      assert.equal(title, EN_MESSAGES[titleKey]);
      renderedTitles.push(title);
      const pauseControl = [...rendered.container.querySelectorAll("button")]
        .find((button) => /pause/i.test(`${button.textContent} ${button.getAttribute("aria-label") ?? ""}`));
      assert.equal(pauseControl, undefined, `${capture.kind} does not fabricate a pause control`);
    } finally {
      await rendered.cleanup();
    }
  }
  assert.equal(new Set(renderedTitles).size, 6);
  // red-proof: remove any state-specific data-presentation/glyph/title branch;
  // the rendered DOM assertion for that arm fails, even if describeCapture remains correct.
});

test("reconnect redelivery renders one row with the revision text", async () => {
  const ListenProduction = await loadProductionExport("ListenProduction.tsx", "ListenProduction");
  const wire = wireStore();
  await wire.store.start();
  wire.sockets[0].open();
  wire.sockets[0].message(JSON.stringify([segment("same", "draft", 0, 1)]));
  wire.sockets[0].serverClose(1001);
  wire.runReconnect();
  wire.sockets[1].open();
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

test("entitlement pause and ceiling stop stay distinct and neither renders idle", async () => {
  const ListenProduction = await loadProductionExport("ListenProduction.tsx", "ListenProduction");
  const paused = wireStore();
  await paused.store.start();
  paused.sockets[0].open();
  paused.sockets[0].message(JSON.stringify(entitlementPauseFrame));

  const stopped = wireStore();
  await stopped.store.start();
  stopped.sockets[0].open();
  stopped.sockets[0].serverClose(4020);

  const pausedRender = await renderComponent(ListenProduction, { store: paused.store });
  try {
    const panel = pausedRender.container.querySelector(".listen-state-panel");
    assert.equal(panel?.getAttribute("data-presentation"), "paused-for-entitlement");
    assert.equal(panel?.querySelector(".listen-state-title")?.textContent, EN_MESSAGES["listen.statePausedEntitlement"]);
    assert.notEqual(panel?.querySelector(".listen-state-title")?.textContent, EN_MESSAGES["listen.stateIdle"]);
    assert.equal(panel?.getAttribute("data-capturing"), "true", "entitlement pause keeps capture running");
  } finally {
    await pausedRender.cleanup();
  }

  const stoppedRender = await renderComponent(ListenProduction, { store: stopped.store });
  try {
    const panel = stoppedRender.container.querySelector(".listen-state-panel");
    assert.equal(panel?.getAttribute("data-presentation"), "stopped-at-ceiling");
    assert.equal(panel?.querySelector(".listen-state-title")?.textContent, EN_MESSAGES["listen.stateStoppedAtCeiling"]);
    assert.notEqual(panel?.querySelector(".listen-state-title")?.textContent, EN_MESSAGES["listen.stateIdle"]);
    assert.equal(panel?.getAttribute("role"), "alert");
    assert.equal(panel?.getAttribute("data-capturing"), "false");
  } finally {
    await stoppedRender.cleanup();
  }
  // red-proof: fold either branch to idle (or both to one generic limit state);
  // the two rendered data-presentations and named titles fail independently.
});
