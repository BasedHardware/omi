/**
 * Generation selection — the knob a shell drives from outside the code.
 *
 * The invariant under test everywhere in this file is one sentence: an
 * unavailable or malformed request is REJECTED AND REPORTED, never silently
 * downgraded. A shell that believes it is exercising a generation nothing can
 * serve, while quietly running on another, produces a green night that proves
 * nothing, and no test in this file would catch that if it only asserted the
 * resolved selection.
 *
 * Hermetic: pure functions over literal input. No transport, no clock.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import {
  PLATFORM_ONLY_GENERATION,
  PRODUCTION_DOMAINS,
  PRODUCTION_GENERATION_AVAILABILITY,
  describeGenerationRejections,
  parseGenerationSelectionFromEntries,
  resolveGenerationSelection,
} from "@omi-core/domain";

test("no host configuration is platform everywhere, with nothing rejected", () => {
  // red-proof: change the `requested === undefined` early return to seed a
  // mixed or empty selection instead of `PLATFORM_ONLY_GENERATION`; an
  // unconfigured shell would silently leave a domain unserved.
  for (const requested of [undefined, null]) {
    const resolved = resolveGenerationSelection(requested);
    assert.deepEqual(resolved.selection, PLATFORM_ONLY_GENERATION);
    assert.deepEqual(resolved.rejected, []);
  }
});

test("the availability table is the only thing that licenses a platform selection", () => {
  // red-proof: drop "platform" from `tasks` in PRODUCTION_GENERATION_AVAILABILITY;
  // the honoured request below becomes a rejection and a shell that asked for
  // platform tasks is silently left on a generation nothing can serve.
  assert.deepEqual(PRODUCTION_GENERATION_AVAILABILITY.memories, ["platform"]);
  assert.deepEqual(PRODUCTION_GENERATION_AVAILABILITY.conversations, ["platform"]);
  assert.deepEqual(PRODUCTION_GENERATION_AVAILABILITY.folders, ["platform"]);
  assert.deepEqual(
    PRODUCTION_GENERATION_AVAILABILITY.tasks,
    ["platform"],
    "tasks is ratified on platform; legacy is retired",
  );

  const resolved = resolveGenerationSelection({ tasks: "platform" });
  assert.equal(resolved.rejected.length, 0, "an available platform request is not a rejection");
  assert.equal(resolved.selection.tasks, "platform");
});

test("an unavailable generation is REPORTED and is not served", () => {
  // red-proof: in the `generation-unavailable` branch, drop the
  // `rejected.push(...)` and keep the `continue`. The selection is unchanged
  // — still correctly platform — so a test that only asserted `selection`
  // would stay green while the shell lost every signal that its request was
  // ignored. That is the exact failure this test exists for.
  const resolved = resolveGenerationSelection({ memories: "legacy", tasks: "platform" });
  assert.equal(resolved.selection.tasks, "platform", "the available one is honored");
  assert.equal(resolved.selection.memories, "platform", "unavailable is not assigned");
  assert.equal(resolved.rejected.length, 1, "silence here is the dangerous case");
  assert.equal(resolved.rejected[0]!.domain, "memories");
  assert.equal(resolved.rejected[0]!.requested, "legacy");
  assert.equal(resolved.rejected[0]!.reason, "generation-unavailable");

  const lines = describeGenerationRejections(resolved.rejected);
  assert.equal(lines.length, 1);
  assert.match(lines[0]!, /memories/);
  assert.match(lines[0]!, /legacy/);
  assert.doesNotMatch(lines[0]!, /[Ff]alling back/);
});

test("garbage from a host config is rejected per key, never coerced", () => {
  // red-proof: make `isBackendGeneration` return `true` for any string; the
  // typo below resolves to a bogus generation instead of being rejected.
  const resolved = resolveGenerationSelection({
    memories: "platfrom", // typo a human will make
    tasks: 42,
    nonsense: "legacy",
    folders: null,
  });
  assert.deepEqual(resolved.selection, PLATFORM_ONLY_GENERATION, "nothing malformed is ever honored");
  assert.equal(resolved.rejected.length, 4);
  const reasons = resolved.rejected.map((r) => `${r.domain ?? "<none>"}:${r.reason}:${r.requested}`).sort();
  assert.deepEqual(reasons, [
    "<none>:unknown-domain:nonsense",
    "folders:unknown-generation:null",
    "memories:unknown-generation:platfrom",
    "tasks:unknown-generation:42",
  ]);
  const stray = resolved.rejected.find((r) => r.requested === "nonsense");
  assert.equal(stray?.domain, null);
});

test("a non-object host config is rejected whole rather than partially applied", () => {
  for (const bad of ["platform", 7, true, ["memories"]]) {
    const resolved = resolveGenerationSelection(bad);
    assert.deepEqual(resolved.selection, PLATFORM_ONLY_GENERATION);
    assert.equal(resolved.rejected.length, 1, `"${JSON.stringify(bad)}" must be refused`);
    assert.equal(resolved.rejected[0]!.reason, "unknown-domain");
    assert.equal(resolved.rejected[0]!.domain, null);
  }
});

test("a launcher can drive selection from flat string entries", () => {
  // red-proof: drop the `generation.` prefix stripping so only bare keys work;
  // the namespaced form below stops selecting platform.
  const namespaced = parseGenerationSelectionFromEntries([
    ["generation.memories", "platform"],
    ["route", "memories"],
  ]);
  assert.equal(namespaced.selection.memories, "platform");
  assert.deepEqual(namespaced.rejected, [], "unrelated launcher keys are not rejections");

  const bare = parseGenerationSelectionFromEntries([["memories", "platform"]]);
  assert.equal(bare.selection.memories, "platform");

  const spaced = parseGenerationSelectionFromEntries([["generation.memories", " platform "]]);
  assert.equal(spaced.selection.memories, "platform");
});

test("a blanket legacy request is rejected on every domain and serves none of it", () => {
  // red-proof: restore the availability skip so a blanket `legacy` assigns
  // nothing and reports nothing — the silent fallback this ruling forbids.
  const resolved = parseGenerationSelectionFromEntries([["generation", "legacy"]]);
  assert.deepEqual(resolved.selection, PLATFORM_ONLY_GENERATION, "legacy is not assigned");
  assert.equal(resolved.rejected.length, PRODUCTION_DOMAINS.length);
  for (const domain of PRODUCTION_DOMAINS) {
    const row = resolved.rejected.find((r) => r.domain === domain);
    assert.equal(row?.requested, "legacy", `${domain} must name the generation that could not be served`);
    assert.equal(row?.reason, "generation-unavailable");
  }
  const lines = describeGenerationRejections(resolved.rejected);
  assert.ok(lines.every((line) => line.includes("legacy")));
  assert.ok(lines.some((line) => line.includes("memories")));
});

test("a blanket platform request is honored on every domain", () => {
  const resolved = parseGenerationSelectionFromEntries([["generation", "platform"]]);
  assert.deepEqual(resolved.selection, PLATFORM_ONLY_GENERATION);
  assert.deepEqual(resolved.rejected, []);
});

test("an explicit per-domain key beats a blanket one", () => {
  const resolved = parseGenerationSelectionFromEntries([
    ["generation", "platform"],
    ["generation.memories", "legacy"],
  ]);
  assert.equal(resolved.selection.memories, "platform", "unavailable explicit key is not honored");
  assert.equal(resolved.rejected.length, 1);
  assert.equal(resolved.rejected[0]!.domain, "memories");
  assert.equal(resolved.rejected[0]!.requested, "legacy");
  assert.equal(resolved.rejected[0]!.reason, "generation-unavailable");
});

test("a misspelled blanket value is reported instead of ignored", () => {
  const resolved = parseGenerationSelectionFromEntries([["generation", "platfrom"]]);
  assert.deepEqual(resolved.selection, PLATFORM_ONLY_GENERATION);
  assert.equal(resolved.rejected.length, 1);
  assert.equal(resolved.rejected[0]!.reason, "unknown-generation");
  assert.equal(resolved.rejected[0]!.requested, "platfrom");
  assert.equal(resolved.rejected[0]!.domain, null, "a blanket value belongs to no single domain");
});

test("every production domain appears in the availability table as platform-only", () => {
  // Guards the failure where a domain is added to the union and forgotten
  // here, which would make `resolveGenerationSelection` throw on a valid key.
  for (const domain of PRODUCTION_DOMAINS) {
    const available = PRODUCTION_GENERATION_AVAILABILITY[domain];
    assert.ok(Array.isArray(available) && available.length > 0, `${domain} has no generations`);
    assert.ok(available.includes("platform"), `${domain} must be servable by platform`);
    assert.equal(available.includes("legacy"), false, `${domain} must not advertise a retired generation`);
  }
  assert.equal(PRODUCTION_DOMAINS.length, 4);
});
