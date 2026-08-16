/**
 * Generation selection — the knob a shell drives from outside the code.
 *
 * The invariant under test everywhere in this file is one sentence: an
 * unavailable or malformed request is REJECTED AND REPORTED, never silently
 * downgraded. A shell that believes it is exercising the new backend while
 * quietly running on the old one produces a green night that proves nothing,
 * and no test in this file would catch that if it only asserted the resolved
 * selection.
 *
 * Hermetic: pure functions over literal input. No transport, no clock.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import {
  LEGACY_ONLY_GENERATION,
  PRODUCTION_DOMAINS,
  PRODUCTION_GENERATION_AVAILABILITY,
  describeGenerationRejections,
  parseGenerationSelectionFromEntries,
  resolveGenerationSelection,
} from "@omi-core/domain";

test("no host configuration is legacy everywhere, with nothing rejected", () => {
  // red-proof: change the `requested === undefined` early return to seed
  // `PLATFORM_MEMORIES_GENERATION` instead of `LEGACY_ONLY_GENERATION`; an
  // unconfigured shell would silently move memories onto the new backend.
  // APPLIED 2026-08-08: observed  'platform' !== 'legacy'
  for (const requested of [undefined, null]) {
    const resolved = resolveGenerationSelection(requested);
    assert.deepEqual(resolved.selection, LEGACY_ONLY_GENERATION);
    assert.deepEqual(resolved.rejected, []);
  }
});

test("the availability table is the only thing that licenses a platform selection", () => {
  // red-proof: drop "platform" from `tasks` in PRODUCTION_GENERATION_AVAILABILITY
  // after David's 2026-08-16 park lift; the honoured request below becomes a
  // rejection and a shell that asked for platform tasks is silently legacy.
  assert.deepEqual(PRODUCTION_GENERATION_AVAILABILITY.memories, ["legacy", "platform"]);
  assert.deepEqual(PRODUCTION_GENERATION_AVAILABILITY.conversations, ["legacy", "platform"]);
  assert.deepEqual(PRODUCTION_GENERATION_AVAILABILITY.folders, ["legacy", "platform"]);
  assert.deepEqual(
    PRODUCTION_GENERATION_AVAILABILITY.tasks,
    ["legacy", "platform"],
    "tasks is ratified on platform after David's 2026-08-16 park lift",
  );

  const resolved = resolveGenerationSelection({ tasks: "platform" });
  assert.equal(resolved.rejected.length, 0, "an available platform request is not a rejection");
  assert.equal(resolved.selection.tasks, "platform");
});

test("an unavailable request is REPORTED, not just downgraded", () => {
  // red-proof: in the `unknown-generation` branch, drop the
  // `rejected.push(...)` and keep the `continue`. The selection is unchanged
  // — still correctly legacy — so a test that only asserted `selection` would
  // stay green while the shell lost every signal that its request was ignored.
  // That is the exact failure this test exists for.
  // APPLIED 2026-08-08: observed  AssertionError: silence here is the dangerous case ... 0 !== 1
  const resolved = resolveGenerationSelection({ memories: "platform", tasks: "sidecar" });
  assert.equal(resolved.selection.memories, "platform", "the available one is honored");
  assert.equal(resolved.selection.tasks, "legacy");
  assert.equal(resolved.rejected.length, 1, "silence here is the dangerous case");

  const lines = describeGenerationRejections(resolved.rejected);
  assert.equal(lines.length, 1);
  assert.match(lines[0]!, /tasks/);
  assert.match(lines[0]!, /sidecar/);
});

test("garbage from a host config is rejected per key, never coerced", () => {
  // red-proof: make `isBackendGeneration` return `true` for any string; the
  // typo below resolves to a bogus generation instead of being rejected.
  // APPLIED 2026-08-08: observed  'platfrom' !== 'legacy'
  const resolved = resolveGenerationSelection({
    memories: "platfrom", // typo a human will make
    tasks: 42,
    nonsense: "legacy",
    folders: null,
  });
  assert.deepEqual(resolved.selection, LEGACY_ONLY_GENERATION, "nothing malformed is ever honored");
  assert.equal(resolved.rejected.length, 4);
  const reasons = resolved.rejected.map((r) => `${r.domain ?? "<none>"}:${r.reason}:${r.requested}`).sort();
  assert.deepEqual(reasons, [
    "<none>:unknown-domain:nonsense",
    "folders:unknown-generation:null",
    "memories:unknown-generation:platfrom",
    "tasks:unknown-generation:42",
  ]);
  // A key that is not a domain is attributed to NO domain. Reporting it under
  // `memories` would put a domain name in the log that the host never wrote,
  // and grepping that log for "memories" is the first thing anyone does.
  const stray = resolved.rejected.find((r) => r.requested === "nonsense");
  assert.equal(stray?.domain, null);
});

test("a non-object host config is rejected whole rather than partially applied", () => {
  for (const bad of ["platform", 7, true, ["memories"]]) {
    const resolved = resolveGenerationSelection(bad);
    assert.deepEqual(resolved.selection, LEGACY_ONLY_GENERATION);
    assert.equal(resolved.rejected.length, 1, `"${JSON.stringify(bad)}" must be refused`);
    assert.equal(resolved.rejected[0]!.reason, "unknown-domain");
    assert.equal(resolved.rejected[0]!.domain, null);
  }
});

test("a launcher can drive selection from flat string entries", () => {
  // red-proof: drop the `generation.` prefix stripping so only bare keys work;
  // the namespaced form below stops selecting platform.
  // APPLIED 2026-08-08: observed  'legacy' !== 'platform'
  // This is the shape a shell actually has: argv pairs, env vars, a query
  // string. If this does not work, "repoint without a recompile" does not work.
  const namespaced = parseGenerationSelectionFromEntries([
    ["generation.memories", "platform"],
    ["route", "memories"],
  ]);
  assert.equal(namespaced.selection.memories, "platform");
  assert.deepEqual(namespaced.rejected, [], "unrelated launcher keys are not rejections");

  const bare = parseGenerationSelectionFromEntries([["memories", "platform"]]);
  assert.equal(bare.selection.memories, "platform");

  // Values arrive from a command line, so they arrive with whitespace.
  const spaced = parseGenerationSelectionFromEntries([["generation.memories", " platform "]]);
  assert.equal(spaced.selection.memories, "platform");
});

test("a blanket legacy request stays legacy on every domain, including tasks", () => {
  // red-proof: after the park lift, a `--generation legacy` launch must not
  // silently keep tasks on platform. The route still has a legacy arm.
  const resolved = parseGenerationSelectionFromEntries([["generation", "legacy"]]);
  assert.deepEqual(resolved.selection, LEGACY_ONLY_GENERATION);
  assert.deepEqual(resolved.rejected, []);
});

test("a blanket generation request takes what exists and claims nothing more", () => {
  // red-proof: make the broadcast branch skip the availability check and
  // assign `broadcast` to every domain. After the park lift that is a no-op
  // for today's table (every domain has platform); the assertion below still
  // names the exact selection so a later domain that lacks platform cannot
  // be invented by a convenience flag.
  const resolved = parseGenerationSelectionFromEntries([["generation", "platform"]]);
  assert.deepEqual(
    resolved.selection,
    {
      memories: "platform",
      conversations: "platform",
      folders: "platform",
      tasks: "platform",
    },
    "exactly the domains that HAVE a platform generation move",
  );
  assert.deepEqual(
    resolved.rejected,
    [],
    "asking for the best available is not asking for something unavailable",
  );
});

test("an explicit per-domain key beats a blanket one", () => {
  const resolved = parseGenerationSelectionFromEntries([
    ["generation", "platform"],
    ["generation.memories", "legacy"],
  ]);
  assert.equal(resolved.selection.memories, "legacy", "the specific instruction wins");
  assert.deepEqual(resolved.rejected, []);
});

test("a misspelled blanket value is reported instead of ignored", () => {
  const resolved = parseGenerationSelectionFromEntries([["generation", "platfrom"]]);
  assert.deepEqual(resolved.selection, LEGACY_ONLY_GENERATION);
  assert.equal(resolved.rejected.length, 1);
  assert.equal(resolved.rejected[0]!.reason, "unknown-generation");
  assert.equal(resolved.rejected[0]!.requested, "platfrom");
  assert.equal(resolved.rejected[0]!.domain, null, "a blanket value belongs to no single domain");
});

test("every production domain appears in the availability table", () => {
  // Guards the failure where a domain is added to the union and forgotten
  // here, which would make `resolveGenerationSelection` throw on a valid key.
  for (const domain of PRODUCTION_DOMAINS) {
    const available = PRODUCTION_GENERATION_AVAILABILITY[domain];
    assert.ok(Array.isArray(available) && available.length > 0, `${domain} has no generations`);
    assert.ok(available.includes("legacy"), `${domain} must always be servable by legacy`);
  }
  assert.equal(PRODUCTION_DOMAINS.length, 4);
});
