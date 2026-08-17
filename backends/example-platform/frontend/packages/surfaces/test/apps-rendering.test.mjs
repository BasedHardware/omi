import assert from "node:assert/strict";
import test, { after } from "node:test";

import { EN_MESSAGES } from "@omi-core/i18n";
import {
  closeRenderHarness,
  loadProductionExport,
  renderComponent,
} from "./render-harness.mjs";

after(closeRenderHarness);

function visibleText(root) {
  return (root?.textContent ?? "").replace(/\s+/g, " ").trim();
}

function count(haystack, needle) {
  if (!needle) return 0;
  let found = 0;
  let from = 0;
  while (from < haystack.length) {
    const at = haystack.indexOf(needle, from);
    if (at < 0) return found;
    found += 1;
    from = at + needle.length;
  }
  return found;
}

test("Apps is a ready empty catalog, not three unavailable notices", async () => {
  // red-proof: restore DeferredDestinationProduction for route=apps. That
  // surface prints destination.unavailable, lifecycle.unavailable, and
  // destination.waitForSource as a Next line — the triple dead-end David saw.
  // Inventing Calendar/Gmail/Notion rows without a backend catalog is the
  // same class of lie as Listen's canned transcript.
  const AppsProduction = await loadProductionExport("AppsProduction.tsx", "AppsProduction");
  const rendered = await renderComponent(AppsProduction, { locale: "en" });
  try {
    const shell = rendered.container.querySelector("[data-production-shell='true']");
    assert.equal(shell?.getAttribute("data-route"), "apps");
    assert.equal(shell?.getAttribute("data-surface-state"), "ready");
    assert.equal(shell?.getAttribute("data-qa-fixture"), "none");
    assert.equal(shell?.getAttribute("data-consumer-semantic"), "apps:visible:0:total:0");

    const text = visibleText(shell);
    assert.match(text, new RegExp(EN_MESSAGES["nav.apps"]));
    assert.ok(text.includes(EN_MESSAGES["apps.subtitle"]));
    assert.ok(text.includes(EN_MESSAGES["apps.emptyTitle"]));
    assert.ok(text.includes(EN_MESSAGES["apps.emptyDetail"]));

    assert.equal(text.includes(EN_MESSAGES["destination.unavailable"]), false);
    assert.equal(text.includes(EN_MESSAGES["destination.waitForSource"]), false);
    assert.equal(text.includes(EN_MESSAGES["lifecycle.unavailable"]), false);
    assert.equal(text.includes("Next:"), false);
    assert.equal(count(text, EN_MESSAGES["apps.emptyTitle"]), 1);
    assert.equal(count(text, EN_MESSAGES["apps.emptyDetail"]), 1);

    const empty = shell.querySelector('[data-empty-kind="empty-projection"] .production-empty-state');
    assert.ok(empty, "ready zero-catalog renders the shared empty region");
    assert.equal(empty.querySelector("h2")?.textContent, EN_MESSAGES["apps.emptyTitle"]);
    assert.equal(empty.querySelector("p")?.textContent, EN_MESSAGES["apps.emptyDetail"]);
    assert.equal(empty.querySelector("button, a"), null, "empty catalog has no fake Connect action");

    const lifecycle = shell.querySelector(".production-lifecycle-region");
    assert.equal(lifecycle?.getAttribute("data-phase"), "ready");
    assert.equal(shell.querySelector(".status-notice"), null);

    assert.doesNotMatch(text, /Calendar|Gmail|Apple Notes|Notion|Obsidian/i);
    assert.doesNotMatch(text, /sample|demo|placeholder/iu);

    assert.ok(rendered.container.querySelector(`[aria-current="page"][href*="route=apps"]`));
  } finally {
    await rendered.cleanup();
  }
});
