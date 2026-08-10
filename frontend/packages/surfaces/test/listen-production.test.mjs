import assert from "node:assert/strict";
import test, { after } from "node:test";
import { backlogHours, describeCapture } from "../src/production/capture-state.ts";
import {
  closeRenderHarness,
  loadProductionExport,
  renderComponent,
} from "./render-harness.mjs";

after(closeRenderHarness);

test("ceiling stop is loud and is not idle", () => {
  // red-proof: mapping stopped-at-ceiling to idle copy, or setting loud:false, must fail this
  const described = describeCapture({ kind: "stopped-at-ceiling", untranscribedSeconds: 7200 });
  assert.equal(described.loud, true);
  assert.equal(described.capturing, false);
  assert.equal(described.titleKey, "listen.stateStoppedAtCeiling");
  assert.notEqual(described.titleKey, "listen.stateIdle");
});

test("entitlement pause still reports capture running and reports the backlog", () => {
  // red-proof: treating the entitlement pause as a stop (capturing:false) must fail this
  const described = describeCapture({
    kind: "paused-for-entitlement",
    elapsedSeconds: 600,
    untranscribedSeconds: 10800,
  });
  assert.equal(described.capturing, true);
  assert.equal(described.backlogSeconds, 10800);
  assert.equal(described.titleKey, "listen.statePausedEntitlement");
});

test("offline buffering is distinguishable from capturing and ceiling", () => {
  // red-proof: collapsing offline into plain capturing must fail this
  const described = describeCapture({
    kind: "offline-buffering",
    elapsedSeconds: 900,
    bufferedSeconds: 300,
    untranscribedSeconds: 3600,
  });
  assert.equal(described.capturing, true);
  assert.equal(described.titleKey, "listen.stateOfflineBuffering");
  assert.notEqual(described.titleKey, "listen.stateCapturing");
  assert.notEqual(described.titleKey, "listen.stateStoppedAtCeiling");
});

test("a non-zero backlog never renders as nothing", () => {
  // red-proof: Math.floor(seconds/3600) must fail this
  const hours = backlogHours(60);
  assert.ok(hours > 0);
  assert.equal(hours, 1);
});

test("every capture kind is handled with a distinct non-empty title key", () => {
  // red-proof: omitting a kind's mapping (so describeCapture throws) or
  // returning an empty titleKey must fail this
  const samples = [
    { kind: "idle" },
    { kind: "capturing", elapsedSeconds: 10 },
    { kind: "paused-for-entitlement", elapsedSeconds: 20, untranscribedSeconds: 30 },
    { kind: "offline-buffering", elapsedSeconds: 40, bufferedSeconds: 50, untranscribedSeconds: 60 },
    { kind: "stopped-at-ceiling", untranscribedSeconds: 70 },
    { kind: "error", retryable: false },
  ];
  const titleKeys = samples.map((sample) => {
    const described = describeCapture(sample);
    assert.equal(typeof described.titleKey, "string");
    assert.notEqual(described.titleKey, "");
    return described.titleKey;
  });
  assert.equal(new Set(titleKeys).size, titleKeys.length);
});

test("ListenProduction announces loud states and renders no pause control", async () => {
  const ListenProduction = await loadProductionExport("ListenProduction.tsx", "ListenProduction");
  const fixtureListenStore = await loadProductionExport("listen-fixtures.ts", "fixtureListenStore");
  const expectedLoudness = {
    idle: false,
    capturing: false,
    "paused-for-entitlement": false,
    "offline-buffering": false,
    "stopped-at-ceiling": true,
    "error-retryable": false,
    "error-permanent": true,
    unavailable: false,
  };

  for (const [state, loud] of Object.entries(expectedLoudness)) {
    const rendered = await renderComponent(ListenProduction, {
      store: fixtureListenStore(state),
      fixture: state,
    });
    try {
      const panel = rendered.container.querySelector(".listen-state-panel");
      assert.ok(panel, `${state} renders the capture-state panel`);
      assert.equal(panel.getAttribute("data-loud"), String(loud), `${state} renders its required loudness`);
      assert.equal(panel.getAttribute("role"), loud ? "alert" : "status", `${state} renders its required live-region role`);
      const pauseControl = [...rendered.container.querySelectorAll("button")]
        .find((button) => /pause/i.test(`${button.textContent} ${button.getAttribute("aria-label") ?? ""}`));
      assert.equal(pauseControl, undefined, `${state} does not fabricate a pause control`);
    } finally {
      await rendered.cleanup();
    }
  }
  // red-proof: rendering stopped-at-ceiling with data-loud=false and
  // role=status must fail both exact mapping assertions above.
});
