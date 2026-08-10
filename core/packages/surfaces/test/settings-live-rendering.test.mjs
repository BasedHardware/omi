import assert from "node:assert/strict";
import test, { after } from "node:test";

import { EN_MESSAGES } from "@omi-core/i18n";
import {
  closeRenderHarness,
  loadProductionExport,
  renderComponent,
} from "./render-harness.mjs";

after(closeRenderHarness);

class Preference {
  value = null;
  async readAppearance() { return this.value; }
  async writeAppearance(value) { this.value = value; }
}

class HttpScript {
  calls = [];
  responses = [];
  respond(...responses) { this.responses.push(...responses); }
  async request(method, path, body) {
    this.calls.push(body === undefined ? { method, path } : { method, path, body });
    const response = this.responses.shift();
    if (response instanceof Promise) return response;
    return response ?? { status: 500, json: null };
  }
}

const signedIn = (entitlement = null) => ({
  identity: { displayName: "Live Alex", email: "live@example.com" },
  entitlement,
});

async function liveSurface(http) {
  const SettingsProduction = await loadProductionExport("SettingsProduction.tsx", "SettingsProduction");
  const createStore = await loadProductionExport(
    "createPlatformSettingsStore.ts",
    "createPlatformProductionSettingsStore",
  );
  const store = await createStore(http, new Preference());
  const rendered = await renderComponent(SettingsProduction, { store, locale: "en" });
  return { rendered, store };
}

test("real adapter-shaped Settings store renders loading then signed-in entitlement absence", async () => {
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  const http = new HttpScript();
  http.respond(pending);
  const { rendered } = await liveSurface(http);
  try {
    assert.ok(rendered.container.querySelector('[data-settings-account="loading"]'));
    await rendered.act(async () => {
      release({ status: 200, json: signedIn(null) });
      await pending;
      await Promise.resolve();
    });
    assert.ok(rendered.container.querySelector('[data-settings-account="signed-in"]'));
    assert.ok(rendered.container.querySelector('[data-settings-plan="absent"]'));
    assert.match(rendered.container.textContent ?? "", /Live Alex/);
  } finally {
    await rendered.cleanup();
  }
});

test("live Settings distinguishes host signed-out, invalid auth blackout, and unmetered", async () => {
  const cases = [
    {
      response: { status: 401, json: null, transportFailureReason: "not-authenticated" },
      selector: '[data-settings-account="signed-out"]',
    },
    {
      response: { status: 401, json: { error: "unauthorized" } },
      selector: '[data-settings-account="unavailable"]',
    },
    {
      response: {
        status: 200,
        json: signedIn({
          planLabel: "Omi Plus",
          limitKey: "memories",
          used: 7,
          limit: null,
          limitReached: false,
          upgradeAvailable: true,
        }),
      },
      selector: '[data-settings-plan="unmetered"]',
    },
  ];
  for (const row of cases) {
    const http = new HttpScript();
    http.respond(row.response);
    const { rendered } = await liveSurface(http);
    try {
      await rendered.act(async () => { await Promise.resolve(); await Promise.resolve(); });
      assert.ok(rendered.container.querySelector(row.selector), row.selector);
      if (row.selector.includes("unavailable")) {
        assert.equal(rendered.container.querySelector('[data-settings-account="signed-out"]'), null);
      }
    } finally {
      await rendered.cleanup();
    }
  }
});

test("live Settings sign-out reaches the user-observed completion state", async () => {
  const http = new HttpScript();
  http.respond({ status: 200, json: signedIn(null) }, { status: 204, json: null });
  const { rendered } = await liveSurface(http);
  try {
    await rendered.act(async () => { await Promise.resolve(); await Promise.resolve(); });
    const button = rendered.container.querySelector("button.settings-sign-out");
    assert.ok(button);
    await rendered.act(async () => {
      button.click();
      await Promise.resolve();
      await Promise.resolve();
    });
    assert.ok(rendered.container.querySelector('[data-settings-account="signed-out"]'));
    assert.equal(
      rendered.container.querySelector(".settings-sign-out-notice")?.textContent,
      EN_MESSAGES["settings.signedOutNotice"],
    );
    assert.deepEqual(http.calls.at(-1), { method: "DELETE", path: "/v1/session/current" });
  } finally {
    await rendered.cleanup();
  }
});
