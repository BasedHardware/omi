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
  } finally {
    await rendered.cleanup();
  }
});

test("sign-out replay stays quiet: second revoke does not surface an operation error", async () => {
  const rendered = await renderSettings("signed-in");
  try {
    const signOut = rendered.container.querySelector('button.settings-sign-out[aria-label="' + EN_MESSAGES["settings.signOut"] + '"]');
    assert.ok(signOut);
    await rendered.act(async () => {
      signOut.click();
      await Promise.resolve();
    });
    assert.ok(rendered.container.querySelector('[data-settings-account="signed-out"]'));
    const again = rendered.container.querySelector('button.settings-sign-in');
    assert.ok(again || rendered.container.querySelector('[data-settings-account="signed-out"]'));
    // Replay revoke through the store after identity is already null.
    const SettingsProduction = await loadProductionExport("SettingsProduction.tsx", "SettingsProduction");
    void SettingsProduction;
    const fixtureSettingsStore = await loadProductionExport("settings-fixtures.ts", "fixtureSettingsStore");
    const store = fixtureSettingsStore("signed-out");
    await store.signOut();
    await store.signOut();
    const replayed = await renderComponent(
      await loadProductionExport("SettingsProduction.tsx", "SettingsProduction"),
      { store, fixture: "signed-out", locale: "en" },
    );
    try {
      assert.equal(replayed.container.querySelector(".operation-error"), null);
      assert.ok(replayed.container.querySelector('[data-settings-account="signed-out"]'));
    } finally {
      await replayed.cleanup();
    }
  } finally {
    await rendered.cleanup();
  }
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
  ]) {
    assert.match(catalogSource, new RegExp(`"${key.replace(/\./g, "\\.")}"`), `${key} must land in i18n dist`);
  }
});
