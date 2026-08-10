import assert from "node:assert/strict";
import test, { after } from "node:test";

import { JSDOM } from "jsdom";
import {
  closeRenderHarness,
  loadProductionExport,
} from "./render-harness.mjs";

after(closeRenderHarness);

function documentWith(attributes, body = "") {
  const pairs = Object.entries(attributes)
    .map(([name, value]) => `${name}=${JSON.stringify(value)}`)
    .join(" ");
  return new JSDOM(`<!doctype html><main ${pairs}>${body}</main>`).window.document;
}

test("rendered semantic observation accepts exactly the seven closed live routes", async () => {
  const read = await loadProductionExport(
    "consumer-observation.ts",
    "readRenderedConsumerObservation",
  );
  for (const route of ["memories", "tasks", "conversations", "folders", "listen", "chat", "settings"]) {
    const transcript = route === "listen" ? { "data-consumer-transcript": "rendered words" } : {};
    const observation = read(documentWith({
      "data-production-shell": "true",
      "data-route": route,
      "data-surface-state": "ready",
      "data-qa-fixture": "none",
      "data-consumer-semantic": `${route}:items:1`,
      ...transcript,
    }));
    assert.deepEqual(observation, route === "listen"
      ? { route, state: "ready", semantic: `${route}:items:1`, transcript: "rendered words" }
      : { route, state: "ready", semantic: `${route}:items:1` });
  }
  // red-proof: delete any route from the allowlist. Its rendered row becomes
  // unobservable even though the page is visibly ready.
});

test("rendered semantic observation rejects fixture, stale, malformed, and leaking claims", async () => {
  const read = await loadProductionExport(
    "consumer-observation.ts",
    "readRenderedConsumerObservation",
  );
  const base = {
    "data-production-shell": "true",
    "data-route": "chat",
    "data-surface-state": "ready",
    "data-qa-fixture": "none",
    "data-consumer-semantic": "chat:messages:1",
  };
  assert.equal(read(documentWith({ ...base, "data-qa-fixture": "normal" })), null);
  assert.equal(read(documentWith({ ...base, "data-surface-state": "refreshing" })), null);
  assert.equal(read(documentWith({ ...base, "data-consumer-semantic": "" })), null);
  assert.equal(read(documentWith({ ...base, "data-route": "home" })), null);
  assert.equal(read(documentWith({ ...base, "data-consumer-transcript": "leaked" })), null);

  const listen = { ...base, "data-route": "listen", "data-consumer-semantic": "listen:segments:0" };
  assert.equal(read(documentWith(listen)), null);
  assert.equal(read(documentWith({ ...listen, "data-consumer-transcript": "   " })), null);
  // red-proof: trust only state/route or permit a fixture marker. These rows
  // become non-null and can manufacture a native success from launch intent.
});

test("semantic and Listen transcript values are bounded", async () => {
  const read = await loadProductionExport(
    "consumer-observation.ts",
    "readRenderedConsumerObservation",
  );
  const base = {
    "data-production-shell": "true",
    "data-route": "memories",
    "data-surface-state": "ready",
    "data-qa-fixture": "none",
  };
  assert.equal(read(documentWith({ ...base, "data-consumer-semantic": "x".repeat(257) })), null);
  assert.equal(read(documentWith({
    ...base,
    "data-route": "listen",
    "data-consumer-semantic": "listen:segments:1",
    "data-consumer-transcript": "x".repeat(1025),
  })), null);
  // red-proof: remove either upper bound. A surface can then copy arbitrary DOM
  // text into the host-readable contract instead of one bounded semantic fact.
});
