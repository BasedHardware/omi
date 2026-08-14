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
  PLATFORM_MEMORIES_GENERATION,
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
  // red-proof: add "platform" to `tasks` in PRODUCTION_GENERATION_AVAILABILITY
  // without an adapter existing; the rejection below disappears and a shell
  // gets pointed at a route nobody wrote.
  // APPLIED 2026-08-08: observed  AssertionError: tasks has no platform generation tonight ... 0 !== 1
  assert.deepEqual(PRODUCTION_GENERATION_AVAILABILITY.memories, ["legacy", "platform"]);
  for (const domain of ["conversations", "folders", "tasks"] as const) {
    assert.deepEqual(
      PRODUCTION_GENERATION_AVAILABILITY[domain],
      ["legacy"],
      `${domain} is not ratified and must not offer a platform generation`,
    );
  }

  const resolved = resolveGenerationSelection({ tasks: "platform" });
  assert.equal(resolved.rejected.length, 1, "tasks has no platform generation tonight");
  assert.equal(resolved.rejected[0]!.reason, "generation-unavailable");
  assert.equal(resolved.rejected[0]!.domain, "tasks");
  assert.equal(
    resolved.selection.tasks,
    "legacy",
    "and it falls back to the generation that can actually serve it",
  );
});

test("an unavailable request is REPORTED, not just downgraded", () => {
  // red-proof: in the `generation-unavailable` branch, drop the
  // `rejected.push(...)` and keep the `continue`. The selection is unchanged
  // — still correctly legacy — so a test that only asserted `selection` would
  // stay green while the shell lost every signal that its request was ignored.
  // That is the exact failure this test exists for.
  // APPLIED 2026-08-08: observed  AssertionError: silence here is the dangerous case ... 0 !== 1
  const resolved = resolveGenerationSelection({ memories: "platform", conversations: "platform" });
  assert.equal(resolved.selection.memories, "platform", "the available one is honored");
  assert.equal(resolved.selection.conversations, "legacy");
  assert.equal(resolved.rejected.length, 1, "silence here is the dangerous case");

  const lines = describeGenerationRejections(resolved.rejected);
  assert.equal(lines.length, 1);
  // Content, not count: the log line must name the domain, what was asked for,
  // and that this run is NOT exercising it. A generic "some config ignored"
  // would satisfy a row-count assertion and help nobody at 3am.
  assert.match(lines[0]!, /conversations/);
  assert.match(lines[0]!, /platform/);
  assert.match(lines[0]!, /NOT exercising/);
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

test("a blanket generation request takes what exists and claims nothing more", () => {
  // red-proof: make the broadcast branch skip the availability check and
  // assign `broadcast` to every domain. `tasks` becomes "platform" — a shell
  // pointed at a nonexistent tasks route by a single convenience flag.
  // APPLIED 2026-08-08: observed  AssertionError: a blanket request must not invent a tasks platform ... 'platform' !== 'legacy'
  const resolved = parseGenerationSelectionFromEntries([["generation", "platform"]]);
  assert.deepEqual(
    resolved.selection,
    PLATFORM_MEMORIES_GENERATION,
    "exactly the domains that HAVE a platform generation move",
  );
  assert.equal(resolved.selection.tasks, "legacy", "a blanket request must not invent a tasks platform");
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
