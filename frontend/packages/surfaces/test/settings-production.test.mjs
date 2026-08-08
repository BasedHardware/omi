import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import {
  entitlementNotice,
  mergeSettingsPatch,
  usageLabelArgs,
} from "../src/production/settings-merge.ts";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

const baseSnapshot = {
  identity: { displayName: "Alex Rivera", email: "alex@example.com" },
  appearance: "dark",
  entitlement: null,
};

test("empty patch leaves appearance and identity untouched", () => {
  const result = mergeSettingsPatch(baseSnapshot, {});
  assert.equal(result.appearance, "dark");
  assert.equal(result.identity?.displayName, "Alex Rivera");
  assert.equal(result.identity?.email, "alex@example.com");
  // red-proof: rewriting mergeSettingsPatch as `{...DEFAULTS, ...patch}` flips
  // appearance to the default and fails this assertion.
});

test("explicit appearance key applies even when switching to default", () => {
  const result = mergeSettingsPatch(baseSnapshot, { appearance: "default" });
  assert.equal(result.appearance, "default");
  assert.equal(result.identity?.email, "alex@example.com");
  // Explicit undefined is a no-op: Object.hasOwn alone must not write undefined.
  const ignored = mergeSettingsPatch(baseSnapshot, { appearance: undefined });
  assert.equal(ignored.appearance, "dark");
  // red-proof: `patch.appearance || current.appearance` would still pass the
  // default case but would also treat explicit undefined as unchanged only by
  // accident; substituting `limit ?? 0` in usageLabelArgs is tested separately.
});

test("upgrade never routes when the payload forbids it", () => {
  const result = entitlementNotice({
    planLabel: "Omi Plus",
    limitKey: "memories",
    used: 100,
    limit: 100,
    limitReached: true,
    upgradeAvailable: false,
  }, true);
  assert.equal(result.upgrade, "unavailable");
  // red-proof: routing from canRoute alone (ignoring upgradeAvailable) fails this.
});

test("upgrade never routes when the host has no flow", () => {
  const result = entitlementNotice({
    planLabel: "Omi Plus",
    limitKey: "memories",
    used: 100,
    limit: 100,
    limitReached: true,
    upgradeAvailable: true,
  }, false);
  assert.equal(result.upgrade, "unavailable");
  // red-proof: ignoring canRoute and routing whenever upgradeAvailable is true fails this.
});

test("unmetered limits never render a fraction denominator", () => {
  const result = usageLabelArgs({
    planLabel: "Omi Plus",
    limitKey: "memories",
    used: 7,
    limit: null,
    limitReached: false,
    upgradeAvailable: true,
  });
  assert.deepEqual(result, { used: 7 });
  assert.equal("limit" in (result ?? {}), false);
  // red-proof: substituting `limit ?? 0` adds a limit key and fails this shape check.
});

test("settings surface does not invent checkout or payment UI", async () => {
  const source = await read("src/production/SettingsProduction.tsx");
  assert.doesNotMatch(source, /\$/);
  assert.doesNotMatch(source, /\bprice\b/i);
  assert.doesNotMatch(source, /\bcheckout\b/i);
  assert.doesNotMatch(source, /\bcard\b/i);
  assert.doesNotMatch(source, /<input[^>]+type="password"/i);
});
