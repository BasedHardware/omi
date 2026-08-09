#!/usr/bin/env node
/**
 * R7's parked flip, pinned mechanically.
 *
 * **THIS IS A STATIC TRIPWIRE, NOT BEHAVIOURAL COVERAGE**, and it is labelled as
 * one because `AGENTS.md` requires that label: "Asserting that source strings
 * occur in a certain order is a static tripwire, not behavioral coverage."
 * It reads source text. It cannot prove what `openTasks()` returns at runtime.
 *
 * WHY A TRIPWIRE IS THE STRONGEST THING AVAILABLE AT THIS SEAM.
 * `createPlatformProductionStoreFactory` lives in `@omi-core/surfaces`, which
 * compiles to a Vite bundle and has no unit-test seam of its own — the same
 * reason that package's own header gives for why the generation SELECTOR was
 * moved into `@omi-core/domain`. A behavioural pin would mean either adding a
 * bundle dependency to the unit suite or moving the factory, and moving the
 * factory at 4am to make a guard convenient is how a guard ends up shaping the
 * code it guards.
 *
 * WHAT IT PROTECTS. Fable pre-ruled the `openTasks()` flip PARKED for the
 * wave-3 run (R7), with reasoning that does not reverse by ruling:
 *
 *   1. every platform-generation write in production denies today — nothing
 *      mints control state and no legacy publisher exists, so the fence refuses
 *      fail-closed; and
 *   2. no ratified path puts a real account's existing tasks behind the platform
 *      generation, so the platform read would serve an empty task list.
 *
 * A flip today is therefore not a product event, it is an outage: an empty list
 * and every write refused. `openTasks()` stays legacy at wake REGARDLESS of what
 * the fixture-venue parity evidence shows.
 *
 * The flip is one line, which is exactly what makes this necessary. D2's full
 * field parity was ratified precisely so the flip WOULD be a one-line factory
 * change — and a one-line change is one an agent can make at 4am believing it is
 * finishing the job. A ruling that lives only in a document is a ruling that can
 * be undone by accident. This makes undoing it a red build and a deliberate act.
 *
 * WHEN THIS CHECK SHOULD BE DELETED: when David ratifies the ingestion/data path
 * the flip depends on. Deleting it is then part of the flip's own diff, and the
 * diff that deletes it is the diff a human should be reading anyway.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const TARGET = "packages/surfaces/src/production/ProductionStores.ts";
const failures = [];

let source;
try {
  source = readFileSync(join(ROOT, TARGET), "utf8");
} catch (error) {
  failures.push(`cannot read ${TARGET} — ${error.message}. If this file moved, this check must move with it, not be deleted.`);
}

if (source !== undefined) {
  // Comments are stripped first. This repo has already shipped a fence that
  // banned an ordinary English word and fired on prose while catching no real
  // reference; the file below DISCUSSES the parked flip at length, and a check
  // that fired on its own rationale would be that defect again.
  const code = source
    .replace(/\/\*[\s\S]*?\*\//g, (match) => match.replace(/[^\n]/g, " "))
    .replace(/\/\/[^\n]*/g, "");

  const legacyBinding = /openTasks:\s*\(\)\s*=>\s*TasksStore\.open\(/;
  if (!legacyBinding.test(code)) {
    failures.push(
      `${TARGET}: \`openTasks\` no longer binds \`TasksStore.open\`. If this is the ratified flip, `
      + "it needs David's ingestion/data-path ruling and this check is deleted in the same diff "
      + "(fable R7). If it is a refactor, keep the binding textually recognisable — this tripwire "
      + "is all that stands between a one-line edit and an outage.",
    );
  }

  // The platform read store must NOT be reachable through `openTasks`. Checked
  // separately from the positive match because a file could plausibly contain
  // both during a botched edit, and the dangerous half is this one.
  const flipped = /openTasks:\s*\(\)\s*=>\s*PlatformTasksStore\.open\(/;
  if (flipped.test(code)) {
    failures.push(
      `${TARGET}: \`openTasks\` is bound to \`PlatformTasksStore.open\` — the flip fable PARKED (R7). `
      + "Production has no control-state publisher, so every platform-generation write denies, and no "
      + "ratified path puts a real account's tasks behind the platform generation: this serves an empty "
      + "list and refuses every write.",
    );
  }

  // And the opt-in path must still exist, or a surface has no way to reach the
  // platform read model and the parking would have quietly become a removal.
  if (!/openPlatformTasks\s*:/.test(code)) {
    failures.push(
      `${TARGET}: \`openPlatformTasks\` is gone. The platform tasks read model must stay reachable BY NAME; `
      + "removing it turns a parked flip into a deleted feature.",
    );
  }
}

if (failures.length) {
  console.error(`core/ openTasks parked-flip check FAILED (${failures.length}):`);
  for (const failure of failures) console.error("  " + failure);
  process.exit(1);
}
console.log("core/ openTasks parked-flip check passed (R7: the flip stays parked).");
