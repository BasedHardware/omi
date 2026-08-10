import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  generationMismatch,
  resolveProductionRoute,
} from "../src/production/production-routing.ts";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

const route = (requestedRoute, requestedQa, memoriesGeneration) =>
  resolveProductionRoute({ requestedRoute, requestedQa, memoriesGeneration });

// ---------------------------------------------------------------------------
// The regression this module exists for.
// ---------------------------------------------------------------------------

test("a platform memories selection with no route named lands on the surface that reads it", () => {
  assert.equal(route(null, null, "platform"), "memories");
  // red-proof: returning "home" here reproduces the exact failure the documented launcher
  // hit. `dev-stack.sh --generation platform` passes `generation=platform` and NO route;
  // Home reads memories through the LEGACY store, so the new backend serves zero reads
  // while the app looks perfect and logs no rejection — because the selection was honored,
  // just never used. Measured: servedReads 0 -> 0 before this, 0 -> 2 after.
});

test("with no platform selection the default is unchanged", () => {
  assert.equal(route(null, null, "legacy"), "home");
  // red-proof: routing to memories regardless of generation changes the product's landing
  // surface for every existing launch.
});

test("an explicit route always beats the platform default", () => {
  assert.equal(route("home", null, "platform"), "home");
  assert.equal(route("tasks", null, "platform"), "tasks");
  assert.equal(route("conversations", null, "platform"), "conversations");
  assert.equal(route("listen", null, "platform"), "listen");
  // red-proof: dropping the "host named nothing" guard makes the first case return
  // "memories". I shipped exactly that for one build: `?generation=platform&route=home`
  // served 2 platform reads instead of 0, i.e. a host that asked for Home silently got
  // Memories. It is the same bug as the one above, mirrored.
});

test("an explicit fixture selector also counts as the host naming a destination", () => {
  assert.equal(route(null, "tasks", "platform"), "tasks");
  assert.equal(route(null, "conversation-detail", "platform"), "conversations");
  assert.equal(route(null, "memories-platform", "platform"), "memories");
  // red-proof: checking only `requestedRoute` for the "named nothing" guard sends
  // `?qa=tasks&generation=platform` to Memories, hijacking a fixture review.
});

test("every explicit destination resolves the same whatever the generation is", () => {
  for (const generation of ["legacy", "platform"]) {
    assert.equal(route("tasks", null, generation), "tasks");
    assert.equal(route("memories", null, generation), "memories");
    assert.equal(route("conversations", null, generation), "conversations");
    assert.equal(route("home", null, generation), "home");
    assert.equal(route("listen", null, generation), "listen");
  }
  // red-proof: making any explicit branch depend on the generation reintroduces a
  // route that changes under the host's feet.
});

// ---------------------------------------------------------------------------
// The alarm that was missing.
// ---------------------------------------------------------------------------

test("rendering legacy memories while platform was selected is a mismatch", () => {
  assert.equal(generationMismatch("platform", "legacy"), true);
  // red-proof: returning false here restores the silent failure. This is the ONLY signal
  // that distinguishes "the host asked for platform and got it" from "the host asked for
  // platform and is looking at legacy records that render perfectly".
});

test("every honest combination is not a mismatch", () => {
  assert.equal(generationMismatch("platform", "platform"), false);
  assert.equal(generationMismatch("legacy", "legacy"), false);
  // Legacy selected, platform rendered cannot happen through the bootstrap, but if it ever
  // did it would not be the silent-wrong-data failure this alarm is for.
  assert.equal(generationMismatch("legacy", "platform"), false);
  // red-proof: a mismatch that fires on the happy path is noise, and noise gets muted.
});

// ---------------------------------------------------------------------------
// Bootstrap wiring: supplementary source checks.
// ---------------------------------------------------------------------------

test("the bootstrap resolves selection through FE-CORE's parser, before routing", async () => {
  const main = await read("src/production/main.tsx");

  // The hand-rolled `{ memories: "platform" }` object could not express a per-domain
  // request and could not report a rejection. FE-CORE's parser does both.
  assert.match(main, /parseGenerationSelectionFromEntries\(query\.entries\(\)\)/);
  // Match the expression, not prose about it: an earlier version of this assertion
  // tripped on the comment above that explains why the hand-rolled object was removed.
  assert.doesNotMatch(main, /query\.get\("generation"\)\s*===\s*"platform"\s*\?/);

  // Selection must be resolved BEFORE the route is computed, or the route cannot depend
  // on it — which was the whole defect.
  assert.ok(
    main.indexOf("const generationSelection") < main.indexOf("const route = resolveProductionRoute"),
    "generation selection must be resolved before the route that depends on it",
  );
  // red-proof: moving the selection below the route resolution makes this fail; so does
  // reinstating the hand-rolled object, which silently loses per-domain requests.
});

test("what actually rendered is observable from outside the bundle", async () => {
  const main = await read("src/production/main.tsx");
  // A script or shell must be able to tell these three apart. Before this, it could not.
  assert.match(main, /__OMI_RUNTIME_STATE__/);
  assert.match(main, /dataset\["generationMemories"\]/);
  assert.match(main, /dataset\["renderedMemoriesGeneration"\]/);
  assert.match(main, /OMI_GENERATION_MISMATCH/);
  assert.match(main, /OMI_GENERATION_REJECTED/);
  // The ready line carries the same facts for log scrapers.
  assert.match(main, /OMI_PRODUCTION_READY route=\$\{route\} state=\$\{state\}/);
  assert.match(main, /rendered\.memoriesGeneration/);

  // Every live render records what it rendered — otherwise `rendered` stays null and the
  // mismatch alarm can never fire.
  for (const marker of [
    'markRendered("memories-platform", "platform")',
    'markRendered("home", "legacy")',
    'markRendered("tasks", "legacy")',
    'markRendered("conversations", "legacy")',
    'markRendered("listen", "platform")',
    'markRendered("memories-legacy", "legacy")',
  ]) {
    assert.ok(main.includes(marker), `bootstrap does not record ${marker}`);
  }
  assert.match(main, /createProductionListenHostSocketFactory/);
  assert.doesNotMatch(
    main,
    /createPlatformListenBrowserSocketFactory\([\s\S]*?location\.origin/,
    "production Listen never targets the UI render origin",
  );
  // red-proof: deleting any markRendered call leaves `rendered: null` for that route, so a
  // launcher asserting on it cannot tell a legacy render from a crash.
});
