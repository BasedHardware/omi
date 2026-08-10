import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { readdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");
const distStampPath = resolve(root, "dist/omi-build-stamp.json");
const distAssetsPath = resolve(root, "dist/assets");

test("vite.config.ts and main.tsx wire the build stamp end to end", async () => {
  const config = await read("vite.config.ts");
  const main = await read("src/production/main.tsx");

  // The plugin must define __OMI_BUILD_STAMP__ for the bundle and also write it to disk,
  // because the L2 lane checks dist freshness from plain node — it never boots a browser
  // to read a `define`d global.
  assert.match(config, /__OMI_BUILD_STAMP__/);
  assert.match(config, /writeStampFile/);
  assert.match(config, /omi-build-stamp\.json/);
  assert.match(config, /worktreeStamp/);
  // red-proof: dropping the try/catch around worktreeStamp and letting it throw makes a
  // git-unavailable checkout (a tarball, a shallow CI clone) fail to build at all, instead
  // of producing a distinguishable `unavailable` stamp.
  assert.match(config, /unavailable/);

  // main.tsx must surface the stamp both on the in-page runtime state and in the
  // OMI_PRODUCTION_READY log line, so a shell (reads runtime state) and a log-scraper
  // (reads stdout only) can each verify the artifact they're looking at without the other.
  assert.match(main, /stamp: __OMI_BUILD_STAMP__/);
  assert.match(main, /stamp=\$\{stampSummary\(runtimeState\.stamp\)\}/);
  // red-proof: moving `stamp=` before `mismatch=` in emitReady's template literal shifts
  // every field position a log-scraper parses by fixed offset from the end of the line.
  const mismatchIndex = main.indexOf("mismatch=${runtimeState.mismatch");
  const stampIndex = main.indexOf("stamp=${stampSummary(runtimeState.stamp)}");
  assert.ok(mismatchIndex !== -1 && stampIndex !== -1 && mismatchIndex < stampIndex);
});

// This test needs an actual `vite build` to have run (it reads the emitted dist/ file).
// Skip cleanly rather than fail when nobody has built yet — a CI lane that only runs
// `node --test` without building first should not see a red result here; the L2 lane
// that cares about dist freshness runs the build itself before this ever executes.
test(
  "built dist/omi-build-stamp.json carries a usable provenance stamp",
  { skip: !existsSync(distStampPath) ? "dist/ not built — run `vite build` first" : false },
  async () => {
    const raw = await readFile(distStampPath, "utf8");
    const stamp = JSON.parse(raw);

    assert.equal(typeof stamp.schema, "number");
    assert.equal(stamp.repo, "core-foundation");

    if ("unavailable" in stamp) {
      // Distinguishable-failure path: git was unavailable at build time. Still a valid
      // stamp shape, just not a usable treeHash — never assert a fabricated one here.
      assert.equal(typeof stamp.unavailable, "string");
      assert.ok(stamp.unavailable.length > 0);
    } else {
      // Deliberately NOT asserting an exact hash value: the tree is still moving and a
      // pinned hash would break on the next unrelated commit. Only the SHAPE is the
      // invariant — a real git tree object id is 40 hex characters.
      assert.match(stamp.treeHash, /^[0-9a-f]{40}$/);
      assert.match(stamp.commit, /^[0-9a-f]{40}$/);
      assert.equal(stamp.artifact, "surfaces-dist");
    }
  },
);

test(
  "the built Listen artifact contains runtime catalog copy and the ratified wire",
  { skip: !existsSync(distAssetsPath) ? "dist/ not built — run `vite build` first" : false },
  async () => {
    const assets = (await readdir(distAssetsPath)).filter((name) => name.endsWith(".js"));
    const bundle = (await Promise.all(
      assets.map((name) => readFile(resolve(distAssetsPath, name), "utf8")),
    )).join("\n");

    for (const runtimeValue of [
      "listen.statePausedEntitlement",
      "Transcription paused — plan limit reached",
      "listen.stateStoppedAtCeiling",
      "Capture stopped — storage ceiling reached",
      "/v4/listen",
      "listen-realtime-protocol/0.3.0.json",
    ]) {
      assert.ok(bundle.includes(runtimeValue), `built Listen artifact contains ${runtimeValue}`);
    }
    // red-proof: drop the raw schema import or bypass the catalog at runtime;
    // the emitted artifact loses the corresponding exact bytes.
  },
);
