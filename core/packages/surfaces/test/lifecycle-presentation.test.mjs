/**
 * Shared RefreshPhase → lifecycle catalog-key presenter.
 *
 * Every production surface that shows a refresh notice must route through
 * `refreshPhaseNoticeKey`. The behavioural pin below is the red-proof for a
 * wrong key; compile-time exhaustiveness (tsc fails when RefreshPhase grows)
 * is the red-proof for a silent `default: return null`.
 */

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { EN_MESSAGES } from "@omi-core/i18n";
import { refreshPhaseNoticeKey } from "../src/production/lifecycle-presentation.ts";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

const EXPECTED = {
  "initial-loading": "lifecycle.loading",
  refreshing: "lifecycle.refreshing",
  "saved-but-refresh-failed": "lifecycle.savedFailed",
  unavailable: "lifecycle.unavailable",
  ready: null,
};

test("refreshPhaseNoticeKey maps every known phase to the existing lifecycle keys", () => {
  for (const [phase, key] of Object.entries(EXPECTED)) {
    assert.equal(refreshPhaseNoticeKey(phase), key);
  }
  assert.equal(EN_MESSAGES["lifecycle.savedFailed"], "Showing saved data. Couldn't refresh.");
  for (const key of ["lifecycle.loading", "lifecycle.refreshing", "lifecycle.savedFailed", "lifecycle.unavailable"]) {
    assert.equal(typeof EN_MESSAGES[key], "string");
    assert.ok(EN_MESSAGES[key].length > 0);
  }
  // red-proof: change saved-but-refresh-failed → "lifecycle.loading" in
  // lifecycle-presentation.ts — EXPECTED["saved-but-refresh-failed"] fails.
});

test("production surfaces consume the shared presenter, not a local switch", async () => {
  const presenter = await read("src/production/lifecycle-presentation.ts");
  for (const key of Object.values(EXPECTED).filter(Boolean)) {
    assert.match(presenter, new RegExp(`"${key}"`));
  }

  const consumers = [
    "src/production/MemoriesProduction.tsx",
    "src/production/MemoriesPlatformProduction.tsx",
    "src/production/ConversationsProduction.tsx",
    "src/production/TasksProduction.tsx",
    "src/production/HomeProduction.tsx",
    "src/production/SettingsProduction.tsx",
    "src/production/ListenProduction.tsx",
    "src/production/ChatProduction.tsx",
  ];
  for (const relative of consumers) {
    const source = await read(relative);
    assert.match(source, /refreshPhaseNoticeKey/, `${relative} must call the shared presenter`);
    assert.doesNotMatch(
      source,
      /case "initial-loading":\s*return (?:t\(|translate\()/,
      `${relative} still has a local phase→key switch`,
    );
  }
  // STATIC TRIPWIRE — labelled as such (AGENTS.md): reading source is not
  // behavioural coverage; the behavioural half is the map pin above.
});
