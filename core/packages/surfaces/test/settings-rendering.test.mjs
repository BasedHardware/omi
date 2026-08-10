import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test, { after } from "node:test";

import { EN_MESSAGES } from "@omi-core/i18n";
import {
  closeRenderHarness,
  loadProductionExport,
  renderComponent,
} from "./render-harness.mjs";

after(closeRenderHarness);

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const i18nDistCatalog = resolve(packageRoot, "../i18n/dist/catalog.js");

async function renderSettings(state, extra = {}) {
  const SettingsProduction = await loadProductionExport("SettingsProduction.tsx", "SettingsProduction");
  const fixtureSettingsStore = await loadProductionExport("settings-fixtures.ts", "fixtureSettingsStore");
  return renderComponent(SettingsProduction, {
    store: fixtureSettingsStore(state),
    fixture: state,
    locale: "en",
    ...extra,
  });
}

function textOf(rendered) {
  return rendered.container.textContent ?? "";
}

test("signed-out is a chosen state with sign-in, never error or entitlement-absence tone", async () => {
  const rendered = await renderSettings("signed-out");
  try {
    const account = rendered.container.querySelector('[data-settings-account="signed-out"]');
    assert.ok(account, "signed-out renders its designed account presentation");
    assert.ok(textOf(rendered).includes(EN_MESSAGES["settings.notSignedIn"]));
    assert.ok(rendered.container.querySelector('button.settings-sign-in[aria-label="' + EN_MESSAGES["settings.signIn"] + '"]'));
    assert.equal(rendered.container.querySelector('[data-settings-account="unavailable"]'), null);
    assert.equal(rendered.container.querySelector('[data-settings-plan="absent"]'), null);
    assert.equal(rendered.container.querySelector(".operation-error"), null);
    assert.equal(account.className.includes("is-error"), false);
    assert.equal(textOf(rendered).includes(EN_MESSAGES["lifecycle.unavailable"]), false);
    assert.equal(textOf(rendered).includes(EN_MESSAGES["settings.entitlementAbsentTitle"]), false);
  } finally {
    await rendered.cleanup();
  }
});

test("unmetered shows plan usage without a ceiling, fraction, or progress bar", async () => {
  const rendered = await renderSettings("unmetered");
  try {
    const plan = rendered.container.querySelector('[data-settings-plan="unmetered"]');
    assert.ok(plan, "unmetered renders its designed plan presentation");
    assert.ok(textOf(rendered).includes(EN_MESSAGES["settings.usageUnmetered"].replace("{used}", "7")));
    assert.equal(textOf(rendered).includes(" of "), false, "unmetered must not render a used/limit fraction");
    assert.equal(rendered.container.querySelector('[data-settings-plan="metered"]'), null);
    assert.equal(rendered.container.querySelector("progress, .settings-usage-meter, [role='progressbar']"), null);
    assert.equal(rendered.container.querySelector(".settings-limit-notice"), null);
  } finally {
    await rendered.cleanup();
  }
});

test("metered limitReached distinguishes upgradeAvailable from upgrade-unavailable", async () => {
  const upgradeable = await renderSettings("limit-reached", {
    onUpgrade: () => {},
  });
  try {
    const plan = upgradeable.container.querySelector('[data-settings-plan="metered"]');
    assert.ok(plan);
    assert.equal(plan.getAttribute("data-settings-limit"), "reached-upgrade");
    assert.ok(textOf(upgradeable).includes(EN_MESSAGES["settings.usageOf"].replace("{used}", "100").replace("{limit}", "100")));
    assert.ok(upgradeable.container.querySelector('button.settings-upgrade[aria-label="' + EN_MESSAGES["settings.upgrade"] + '"]'));
    assert.equal(textOf(upgradeable).includes(EN_MESSAGES["settings.upgradeUnavailable"]), false);
  } finally {
    await upgradeable.cleanup();
  }

  const blocked = await renderSettings("upgrade-unavailable", {
    onUpgrade: () => {},
  });
  try {
    const plan = blocked.container.querySelector('[data-settings-plan="metered"]');
    assert.ok(plan);
    assert.equal(plan.getAttribute("data-settings-limit"), "reached-no-upgrade");
    assert.ok(textOf(blocked).includes(EN_MESSAGES["settings.upgradeUnavailable"]));
    assert.equal(blocked.container.querySelector("button.settings-upgrade"), null);
  } finally {
    await blocked.cleanup();
  }
});

test("entitlement authoritatively absent is deliberate and distinct from signed-out and unmetered", async () => {
  const rendered = await renderSettings("entitlement-absent");
  try {
    assert.ok(rendered.container.querySelector('[data-settings-account="signed-in"]'));
    const plan = rendered.container.querySelector('[data-settings-plan="absent"]');
    assert.ok(plan, "signed-in with null entitlement renders deliberate absence");
    assert.ok(textOf(rendered).includes(EN_MESSAGES["settings.entitlementAbsentTitle"]));
    assert.ok(textOf(rendered).includes(EN_MESSAGES["settings.entitlementAbsentBody"]));
    assert.equal(rendered.container.querySelector('[data-settings-account="signed-out"]'), null);
    assert.equal(rendered.container.querySelector('[data-settings-plan="unmetered"]'), null);
    assert.equal(textOf(rendered).includes(EN_MESSAGES["settings.notSignedIn"]), false);
    assert.equal(textOf(rendered).includes(" of "), false);
  } finally {
    await rendered.cleanup();
  }
});

test("503 blackout shows unavailable with retry and never leaks identity", async () => {
  const rendered = await renderSettings("unavailable");
  try {
    const blackout = rendered.container.querySelector('[data-settings-account="unavailable"]');
    assert.ok(blackout, "unavailable renders the designed blackout presentation");
    assert.ok(textOf(rendered).includes(EN_MESSAGES["settings.unavailableTitle"]));
    assert.ok(textOf(rendered).includes(EN_MESSAGES["settings.unavailableBody"]));
    const retry = rendered.container.querySelector('button[aria-label="' + EN_MESSAGES["common.retry"] + '"]');
    assert.ok(retry, "blackout exposes a retry path");
    assert.equal(textOf(rendered).includes("alex@example.com"), false, "blackout must not leak email");
    assert.equal(textOf(rendered).includes("Alex Rivera"), false, "blackout must not leak display name");
    assert.equal(rendered.container.querySelector('[data-settings-account="signed-in"]'), null);
    assert.equal(rendered.container.querySelector('[data-settings-account="signed-out"]'), null);
    assert.equal(rendered.container.querySelector('[data-settings-plan]'), null);
  } finally {
    await rendered.cleanup();
  }
});

test("loading never claims signed-out, empty, or unavailable copy", async () => {
  const rendered = await renderSettings("loading");
  try {
    const loading = rendered.container.querySelector('[data-settings-account="loading"]');
    assert.ok(loading, "loading renders its designed presentation");
    assert.ok(textOf(rendered).includes(EN_MESSAGES["common.loading"]));
    assert.equal(textOf(rendered).includes(EN_MESSAGES["settings.notSignedIn"]), false);
    assert.equal(textOf(rendered).includes(EN_MESSAGES["settings.identityUnavailable"]), false);
    assert.equal(textOf(rendered).includes(EN_MESSAGES["settings.entitlementAbsentTitle"]), false);
    assert.equal(textOf(rendered).includes(EN_MESSAGES["lifecycle.empty"]), false);
    assert.equal(rendered.container.querySelector('[data-settings-account="signed-out"]'), null);
    assert.equal(rendered.container.querySelector('[data-settings-plan="absent"]'), null);
    // Appearance must not claim a selected value while snapshot data is unproven.
    // Compare booleans — assert.equal on a live Element hangs serializing the DOM on failure.
    assert.equal(rendered.container.querySelector(".settings-appearance-section") == null, true);
    assert.equal(textOf(rendered).includes(EN_MESSAGES["settings.appearanceLocalNote"]), false);
  } finally {
    await rendered.cleanup();
  }
});

test("ready store with unresolved snapshot never claims signed-out", async () => {
  // red-proof: treating null snapshot identity as signed-out while phase is ready
  // makes this assertion fail — the DOM must not say "You are not signed in" before
  // the snapshot that will prove signed-in has resolved.
  const SettingsProduction = await loadProductionExport("SettingsProduction.tsx", "SettingsProduction");
  let releaseSnapshot;
  const snapshotGate = new Promise((resolve) => { releaseSnapshot = resolve; });
  const pendingIdentity = { displayName: "Alex Rivera", email: "alex@example.com" };
  const store = {
    async snapshot() {
      await snapshotGate;
      return {
        identity: pendingIdentity,
        appearance: "system",
        entitlement: { planLabel: "Omi Plus", limitKey: "memories", used: 1, limit: 100, limitReached: false, upgradeAvailable: true },
      };
    },
    status() {
      return {
        refresh: { phase: "ready", hasSavedData: true },
        queue: { phase: "idle", pendingCount: 0 },
      };
    },
    async deadLetters() { return []; },
    subscribe() { return () => {}; },
    async refresh() {},
    async patch() {},
    async signOut() {},
    async discardDeadLetter() {},
  };
  const rendered = await renderComponent(SettingsProduction, {
    store,
    fixture: "ready-pending-snapshot",
    locale: "en",
  });
  try {
    assert.equal(
      rendered.container.querySelector('[data-settings-account="signed-out"]') == null,
      true,
      "pending snapshot must not render the signed-out panel",
    );
    assert.equal(
      textOf(rendered).includes(EN_MESSAGES["settings.notSignedIn"]),
      false,
      "pending snapshot must not claim the user is signed out",
    );
    assert.equal(
      rendered.container.querySelector('[data-settings-account="loading"]') != null,
      true,
      "ready-with-pending-snapshot presents as loading until the snapshot lands",
    );
    await rendered.act(async () => {
      releaseSnapshot();
      await Promise.resolve();
      await Promise.resolve();
    });
    assert.equal(rendered.container.querySelector('[data-settings-account="signed-in"]') != null, true);
    assert.ok(textOf(rendered).includes("Alex Rivera"));
    assert.equal(rendered.container.querySelector('[data-settings-account="signed-out"]') == null, true);
  } finally {
    releaseSnapshot?.();
    await rendered.cleanup();
  }
});

test("sign-out announces completion in a polite live region without error tone", async () => {
  const rendered = await renderSettings("signed-in");
  try {
    const signOut = rendered.container.querySelector('button.settings-sign-out[aria-label="' + EN_MESSAGES["settings.signOut"] + '"]');
    assert.ok(signOut);
    await rendered.act(async () => {
      signOut.click();
      await Promise.resolve();
      await Promise.resolve();
    });
    assert.equal(rendered.container.querySelector('[data-settings-account="signed-out"]') != null, true);
    const notice = rendered.container.querySelector(".settings-sign-out-notice[role='status']");
    assert.equal(notice != null, true, "successful sign-out must emit a polite status notice");
    assert.equal(notice?.textContent, EN_MESSAGES["settings.signedOutNotice"]);
    assert.equal(rendered.container.querySelector(".operation-error"), null);
    assert.equal(notice?.getAttribute("role"), "status");
  } finally {
    await rendered.cleanup();
  }
});

test("sign-out replay through the mounted store stays quiet", async () => {
  // Render-layer proof: the same store the surface subscribed to is revoked
  // again after the UI already reached signed-out. Replay must not surface an
  // operation error on the live tree.
  const SettingsProduction = await loadProductionExport("SettingsProduction.tsx", "SettingsProduction");
  const fixtureSettingsStore = await loadProductionExport("settings-fixtures.ts", "fixtureSettingsStore");
  const store = fixtureSettingsStore("signed-in");
  const rendered = await renderComponent(SettingsProduction, {
    store,
    fixture: "signed-in",
    locale: "en",
  });
  try {
    const signOut = rendered.container.querySelector('button.settings-sign-out[aria-label="' + EN_MESSAGES["settings.signOut"] + '"]');
    assert.ok(signOut);
    await rendered.act(async () => {
      signOut.click();
      await Promise.resolve();
      await Promise.resolve();
    });
    assert.equal(rendered.container.querySelector('[data-settings-account="signed-out"]') != null, true);
    await rendered.act(async () => {
      await store.signOut();
      await Promise.resolve();
    });
    assert.equal(rendered.container.querySelector(".operation-error"), null);
    assert.equal(rendered.container.querySelector('[data-settings-account="signed-out"]') != null, true);
  } finally {
    await rendered.cleanup();
  }
});

test("fixture store sign-out replay is a quiet success by contract", async () => {
  // Store-contract altitude: revoke twice with no surface mounted. The render
  // suite covers the mounted interaction separately.
  const fixtureSettingsStore = await loadProductionExport("settings-fixtures.ts", "fixtureSettingsStore");
  const store = fixtureSettingsStore("signed-out");
  await store.signOut();
  await store.signOut();
  assert.equal((await store.snapshot()).identity, null);
});

test("appearance stays visibly shell-local, not an accidental server omission", async () => {
  const rendered = await renderSettings("signed-in");
  try {
    const appearance = rendered.container.querySelector('[data-appearance-scope="shell-local"]');
    assert.ok(appearance, "appearance section declares shell-local scope");
    assert.ok(textOf(rendered).includes(EN_MESSAGES["settings.appearanceLocalNote"]));
    assert.ok(rendered.container.querySelector('select[aria-label="' + EN_MESSAGES["appearance.title"] + '"]'));
  } finally {
    await rendered.cleanup();
  }
});

test("settings catalog keys used by the surface exist in the built i18n artifact", async () => {
  const catalogSource = await readFile(i18nDistCatalog, "utf8");
  for (const key of [
    "settings.notSignedIn",
    "settings.entitlementAbsentTitle",
    "settings.entitlementAbsentBody",
    "settings.unavailableTitle",
    "settings.unavailableBody",
    "settings.appearanceLocalNote",
    "settings.usageUnmetered",
    "settings.usageOf",
    "settings.upgrade",
    "settings.upgradeUnavailable",
    "settings.limitReachedTitle",
    "settings.signedOutNotice",
  ]) {
    assert.match(catalogSource, new RegExp(`"${key.replace(/\./g, "\\.")}"`), `${key} must land in i18n dist`);
  }
});
