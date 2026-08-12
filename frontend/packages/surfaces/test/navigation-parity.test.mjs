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
  for (const [destination, label] of [["apps", "Apps"], ["rewind", "Rewind"], ["brain-map", "Brain Map"]]) {
    const rendered = await renderComponent(DeferredDestinationProduction, { destination, locale: "en" });
    try {
      const shell = rendered.container.querySelector("[data-production-shell='true']");
      assert.equal(shell?.getAttribute("data-route"), destination);
      assert.equal(shell?.getAttribute("data-surface-state"), "unavailable");
      assert.match(shell?.textContent ?? "", new RegExp(label));
      assert.match(shell?.textContent ?? "", /not available in this build yet/);
      assert.doesNotMatch(shell?.textContent ?? "", /sample|demo|placeholder/iu);
      assert.ok(rendered.container.querySelector(`[aria-current="page"][href*="route=${destination}"]`));
    } finally {
      await rendered.cleanup();
    }
  }
});
