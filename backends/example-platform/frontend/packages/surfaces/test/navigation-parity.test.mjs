import assert from "node:assert/strict";
import test, { after } from "node:test";

import {
  closeRenderHarness,
  loadProductionExport,
  renderComponent,
} from "./render-harness.mjs";

after(closeRenderHarness);

test("unconnected shipped destinations stay reachable without fabricated content", async () => {
  const DeferredDestinationProduction = await loadProductionExport(
    "DeferredDestinationProduction.tsx",
    "DeferredDestinationProduction",
  );
  const rendered = await renderComponent(DeferredDestinationProduction, { destination: "brain-map", locale: "en" });
  try {
    const shell = rendered.container.querySelector("[data-production-shell='true']");
    assert.equal(shell?.getAttribute("data-route"), "brain-map");
    assert.equal(shell?.getAttribute("data-surface-state"), "unavailable");
    assert.match(shell?.textContent ?? "", /Brain Map/);
    assert.match(shell?.textContent ?? "", /not available in this build yet/);
    assert.doesNotMatch(shell?.textContent ?? "", /sample|demo|placeholder/iu);
    assert.ok(rendered.container.querySelector(`[aria-current="page"][href*="route=brain-map"]`));
  } finally {
    await rendered.cleanup();
  }
});

test("Rewind is a live production destination with capture history, not a deferred placeholder", async () => {
  const ScreenProduction = await loadProductionExport("ScreenProduction.tsx", "ScreenProduction");
  const fixtureScreenStore = await loadProductionExport("screen-fixtures.ts", "fixtureScreenStore");
  const rendered = await renderComponent(ScreenProduction, {
    store: fixtureScreenStore("ready"),
    locale: "en",
  });
  try {
    const shell = rendered.container.querySelector("[data-production-shell='true']");
    assert.equal(shell?.getAttribute("data-route"), "screen");
    assert.notEqual(shell?.getAttribute("data-surface-state"), "unavailable");
    assert.match(shell?.textContent ?? "", /Rewind/);
    assert.match(shell?.textContent ?? "", /Harborline Cafe/);
    assert.doesNotMatch(shell?.textContent ?? "", /not available in this build yet/);
    assert.ok(rendered.container.querySelector(`[aria-current="page"][href*="route=rewind"]`));
  } finally {
    await rendered.cleanup();
  }
});
