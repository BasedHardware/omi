#!/usr/bin/env node
/**
 * R7's factory-flip tripwire, updated under David's 2026-08-16 Tasks park lift.
 *
 * **THIS IS A STATIC TRIPWIRE, NOT BEHAVIOURAL COVERAGE**, and it is labelled as
 * one because `AGENTS.md` requires that label: "Asserting that source strings
 * occur in a certain order is a static tripwire, not behavioral coverage."
 * It reads source text. It cannot prove what `openTasks()` returns at runtime.
 *
 * THE PARK WAS LIFTED. David ruled 2026-08-16: move Tasks to the platform
 * generation and unpark R7. Editing was why it was parked; the route now
 * branches to `openPlatformTasks()` the same way Home, Conversations, and
 * Folders already branch. This check is NOT deleted. A fence that now permits
 * everything was deleted with extra steps.
 *
 * WHAT IT STILL CATCHES after the lift:
 *   1. Repointing `openTasks()` inside `createPlatformProductionStoreFactory`
 *      (or the shared legacy factory) to `PlatformTasksStore.open` — the
 *      landmine the brief names. The route branches; the factory does not.
 *   2. Removing the `TasksStore.open` binding from `openTasks` (blanker
 *      desync or a silent rename) — R23's positive control.
 *   3. Removing `openPlatformTasks` so the named platform port is gone.
 *   4. A Tasks route that no longer branches on `selection.tasks` — serving
 *      legacy under a platform selection, or platform under a legacy one.
 *
 * The blanker, self-test fixtures, and R23 pairing are unchanged in kind.
 * WHEN THIS CHECK SHOULD BE DELETED: when `openTasks()` itself is the platform
 * store AND the legacy factory port is gone, which is the `adapters-legacy`
 * deletion lane, not this one.
 *
 * ── ROUND 2: PROSE IN A STRING WAS A FALSE POSITIVE ──────────────────────────
 *
 * The first version blanked COMMENTS and stopped there. A non-author audit went
 * straight past that and found the gap it left: **the identical prose was safe
 * in a comment and fatal in a string.** A plain string or template literal
 * carrying the flip pattern as illustrative text — not code, never evaluated —
 * failed the check.
 *
 * That is not hypothetical and was not cheap: a sibling lane was building a
 * rendering-parity harness whose test names, fixture labels and description
 * strings are *about* `openTasks` and both generations. That is precisely the
 * shape that trips it, and a guard that makes another lane reword its test names
 * around a bug is the routed-around guardrail this repo has already shipped once.
 *
 * So the blanker now covers comments, string literals AND template literals,
 * including `${…}` interpolation depth — rule 17's round-4 lesson, where an
 * unmatched backtick desynced a scanner that tracked templates but not depth.
 *
 * ── WHY OVER-BLANKING IS THE SAFE DIRECTION HERE, AND WHAT CATCHES IT ────────
 *
 * Blanking too much cannot hide a real flip, because a flip inside a string is
 * inert text that binds nothing. The dangerous failure is the opposite: a
 * desynced blanker eating REAL code, after which the negative check matches
 * nothing and passes while the flip is live.
 *
 * **That is fable's R23 exactly** — a negative assertion cannot tell you it has
 * stopped matching anything — so this check pairs its negative with a POSITIVE
 * CONTROL ON THE SAME SUBJECT: `openTasks` must still be seen binding
 * `TasksStore.open` in the blanked text. If the blanker ever eats the region
 * this check is about, the positive control fails loudly rather than the
 * negative one passing quietly. The two are checked against the same blanked
 * source so neither can be true of a different string than the other.
 *
 * ── THE FALSE-POSITIVE AUDIT IS NOW PERMANENT ────────────────────────────────
 *
 * `SELF_TEST_FIXTURES` runs on EVERY invocation, before the real file is read.
 * A rename or a reformat that defangs the blanker fails the self-test rather
 * than silently passing the real check. AUDIT's string case is fixture 3 and can
 * never be dropped without a visible edit here.
 *
 * ACCEPTED LIMIT, NAMED AND DATED (2026-08-09): regex literals are not lexed.
 * A regex containing an unbalanced quote or backtick could desync the blanker.
 * The target file contains none today, and the positive control above is what
 * turns that desync into a loud failure instead of a silent pass. Chasing it
 * further is the convergence-toward-a-real-lexer that rule 17's audit ruled is
 * not worth paying at a hatch; here it is worth even less, because the failure
 * is loud.
 *
 * PROVISIONAL per §8, and it stays that way: AUDIT verifies, the author does not
 * promote their own guard. If it fires on another lane that is a swarm-wide
 * blocker, never something to route around.
 *
 * WHEN THIS CHECK SHOULD BE DELETED: when `openTasks()` itself is the platform
 * store AND the legacy factory port is gone — the `adapters-legacy` deletion
 * lane, not this one. Deleting it is then part of that lane's own diff.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const TARGET = "packages/surfaces/src/production/ProductionStores.ts";
const ROUTE_TARGET = "packages/surfaces/src/production/task-sources.ts";

/**
 * Blanks every byte that is not code — comment bodies, string contents and
 * template contents — preserving newlines and overall length so a reported
 * position still means something.
 *
 * A single scanner with an explicit mode stack, rather than a chain of regex
 * replaces. The chain is what produced round 1's gap: `withoutComments` is
 * string-blind by construction, so blanking comments first and hoping told us
 * nothing about what was inside a quote.
 */
export function blankNonCode(text) {
  const out = [...text];
  const blankAt = (index) => { if (out[index] !== "\n") out[index] = " "; };
  /** Mode stack. `${…}` inside a template pushes a nested code frame. */
  const modes = ["code"];
  const braceDepths = [0];
  let i = 0;

  while (i < text.length) {
    const mode = modes[modes.length - 1];
    const c = text[i];
    const n = text[i + 1];

    if (mode === "template") {
      if (c === "\\") { blankAt(i); i += 1; if (i < text.length) { blankAt(i); i += 1; } continue; }
      if (c === "`") { modes.pop(); i += 1; continue; }
      if (c === "$" && n === "{") { modes.push("code"); braceDepths.push(0); i += 2; continue; }
      blankAt(i); i += 1;
      continue;
    }

    // mode === "code"
    if (c === "/" && n === "/") {
      while (i < text.length && text[i] !== "\n") { blankAt(i); i += 1; }
      continue;
    }
    if (c === "/" && n === "*") {
      blankAt(i); blankAt(i + 1); i += 2;
      while (i < text.length && !(text[i] === "*" && text[i + 1] === "/")) { blankAt(i); i += 1; }
      if (i < text.length) blankAt(i);
      if (i + 1 < text.length) blankAt(i + 1);
      i += 2;
      continue;
    }
    if (c === "'" || c === '"') {
      const quote = c;
      i += 1;
      while (i < text.length && text[i] !== quote && text[i] !== "\n") {
        if (text[i] === "\\") { blankAt(i); i += 1; if (i < text.length) { blankAt(i); i += 1; } continue; }
        blankAt(i); i += 1;
      }
      if (i < text.length && text[i] === quote) i += 1;
      continue;
    }
    if (c === "`") { modes.push("template"); i += 1; continue; }
    if (c === "{") { braceDepths[braceDepths.length - 1] += 1; i += 1; continue; }
    if (c === "}") {
      if (braceDepths[braceDepths.length - 1] === 0 && modes.length > 1) {
        braceDepths.pop();
        modes.pop(); // back to the template that opened this `${`
        i += 1;
        continue;
      }
      if (braceDepths[braceDepths.length - 1] > 0) braceDepths[braceDepths.length - 1] -= 1;
      i += 1;
      continue;
    }
    i += 1;
  }
  return out.join("");
}

const LEGACY_BINDING = /openTasks:\s*\(\)\s*=>\s*TasksStore\.open\(/;
const FLIPPED_BINDING = /openTasks:\s*\(\)\s*=>\s*PlatformTasksStore\.open\(/;
const OPT_IN = /openPlatformTasks\s*:/;
const ROUTE_BRANCH = /tasksGeneration ===/;
const ROUTE_PLATFORM_CALL = /openPlatformTasks\s*\(/;
const ROUTE_LEGACY_CALL = /openTasks\s*\(/;

/** Pure analysis over one factory source text. Returns a list of failure strings. */
export function analyze(source, label = TARGET) {
  const failures = [];
  const code = blankNonCode(source);

  // R23's POSITIVE CONTROL, checked first and on the same blanked text as the
  // negative below. If the blanker ever eats this region, this fires — which is
  // the only thing standing between a desync and a silent pass.
  if (!LEGACY_BINDING.test(code)) {
    failures.push(
      `${label}: \`openTasks\` is not seen binding \`TasksStore.open\`. The Tasks route `
      + "branches at the route (David's 2026-08-16 park lift); the factory must keep the "
      + "legacy port. If the blanker desynced and ate the binding, that is the other "
      + "failure this positive control exists for (R23).",
    );
  }

  if (FLIPPED_BINDING.test(code)) {
    failures.push(
      `${label}: \`openTasks\` is bound to \`PlatformTasksStore.open\` — the factory-level `
      + "flip R7 still forbids after David's 2026-08-16 park lift. Branch at the route; "
      + "do not repoint the shared factory.",
    );
  }

  if (!OPT_IN.test(code)) {
    failures.push(
      `${label}: \`openPlatformTasks\` is gone. The platform tasks store must stay reachable BY NAME; `
      + "removing it turns a route branch into a missing port.",
    );
  }

  return failures;
}

/** Pure analysis over the Tasks route source. Returns a list of failure strings. */
export function analyzeRoute(source, label = ROUTE_TARGET) {
  const failures = [];
  const code = blankNonCode(source);

  if (!ROUTE_BRANCH.test(code)) {
    failures.push(
      `${label}: the Tasks route does not branch on \`tasksGeneration ===\`. `
      + "A platform selection would silently open the legacy store.",
    );
  }
  if (!ROUTE_PLATFORM_CALL.test(code)) {
    failures.push(
      `${label}: the Tasks route never calls \`openPlatformTasks()\`. The park lift is a route branch, not a factory flip.`,
    );
  }
  if (!ROUTE_LEGACY_CALL.test(code)) {
    failures.push(
      `${label}: the Tasks route never calls \`openTasks()\`. \`--generation legacy\` would have nowhere to go.`,
    );
  }
  if (FLIPPED_BINDING.test(code)) {
    failures.push(
      `${label}: the Tasks route binds \`openTasks\` to \`PlatformTasksStore.open\` — factory-flip shape in the route file.`,
    );
  }
  return failures;
}

/**
 * The false-positive audit, run on every invocation so it cannot be silently
 * defanged by a later rename or reformat.
 *
 * `clean` is the minimal shape of the real file. Each fixture states what it is
 * and whether the check must pass on it.
 */
const clean = `
export function createPlatformProductionStoreFactory(bridge, env, transports) {
  return {
    openTasks: () => TasksStore.open(bridge, env, http),
    openPlatformTasks: () => PlatformTasksStore.open(bridge, env, transports.platformHttp),
  };
}
`;

const SELF_TEST_FIXTURES = [
  { name: "the ordinary correct shape", mustPass: true, source: clean },
  {
    name: "the flip discussed in a line comment",
    mustPass: true,
    source: clean.replace("  return {", "  // openTasks: () => PlatformTasksStore.open(bridge, env, http)\n  return {"),
  },
  {
    // AUDIT'S CASE — round 2. Prose in a STRING, not a comment. This is the
    // fixture that must never be dropped: it is the one the first version failed.
    name: "the flip quoted as illustrative text in a string",
    mustPass: true,
    source: `${clean}\nconst note = "the flip would read openTasks: () => PlatformTasksStore.open(bridge, env, http)";\n`,
  },
  {
    name: "the flip quoted in a template literal",
    mustPass: true,
    source: `${clean}\nconst note = \`not code: openTasks: () => PlatformTasksStore.open(bridge, env, http)\`;\n`,
  },
  {
    name: "the flip quoted in a template literal carrying an interpolation",
    mustPass: true,
    source: `${clean}\nconst note = \`\${label}: openTasks: () => PlatformTasksStore.open(bridge, env, http)\`;\n`,
  },
  {
    name: "a reformatted but correct binding",
    mustPass: true,
    source: clean.replace("openTasks: () => TasksStore.open(", "openTasks: ()  =>\n      TasksStore.open("),
  },
  {
    name: "an ACTUAL flip",
    mustPass: false,
    source: clean.replace("openTasks: () => TasksStore.open(", "openTasks: () => PlatformTasksStore.open("),
  },
  {
    name: "the legacy binding renamed away",
    mustPass: false,
    source: clean.replace("openTasks: () => TasksStore.open(", "openTasks: () => SomethingElse.open("),
  },
  {
    name: "the opt-in path removed",
    mustPass: false,
    source: clean.replace(/\n\s*openPlatformTasks:[^\n]*\n/, "\n"),
  },
];

const cleanRoute = `
export async function openTaskRouteSource(stores) {
  const tasksGeneration = stores.selection.tasks;
  const store = tasksGeneration === "platform"
    ? await stores.openPlatformTasks()
    : await stores.openTasks();
  return { store, tasksGeneration };
}
`;

const ROUTE_SELF_TEST_FIXTURES = [
  { name: "the ordinary correct route branch", mustPass: true, source: cleanRoute },
  {
    name: "the factory flip quoted as illustrative text in the route file",
    mustPass: true,
    source: `${cleanRoute}\nconst note = "the flip would read openTasks: () => PlatformTasksStore.open(bridge, env, http)";\n`,
  },
  {
    name: "a route that never opens the platform store",
    mustPass: false,
    source: cleanRoute.replace("await stores.openPlatformTasks()", "await stores.openTasks()"),
  },
  {
    name: "a route that never opens the legacy store",
    mustPass: false,
    source: cleanRoute.replace("await stores.openTasks()", "await stores.openPlatformTasks()"),
  },
  {
    name: "a route that does not branch on tasksGeneration",
    mustPass: false,
    source: cleanRoute.replace("tasksGeneration === \"platform\"", "false"),
  },
];

function runSelfTest() {
  const broken = [];
  for (const fixture of SELF_TEST_FIXTURES) {
    const failures = analyze(fixture.source, `self-test/${fixture.name}`);
    const passed = failures.length === 0;
    if (passed !== fixture.mustPass) {
      broken.push(
        `self-test "${fixture.name}": expected the check to ${fixture.mustPass ? "PASS" : "FAIL"}, `
        + `it ${passed ? "passed" : "failed"}${passed ? "" : ` — ${failures[0]}`}`,
      );
    }
  }
  for (const fixture of ROUTE_SELF_TEST_FIXTURES) {
    const failures = analyzeRoute(fixture.source, `self-test/${fixture.name}`);
    const passed = failures.length === 0;
    if (passed !== fixture.mustPass) {
      broken.push(
        `self-test "${fixture.name}": expected the check to ${fixture.mustPass ? "PASS" : "FAIL"}, `
        + `it ${passed ? "passed" : "failed"}${passed ? "" : ` — ${failures[0]}`}`,
      );
    }
  }
  return broken;
}

const selfTestFailures = runSelfTest();
if (selfTestFailures.length) {
  console.error(`core/ openTasks parked-flip check IS ITSELF BROKEN (${selfTestFailures.length}):`);
  for (const failure of selfTestFailures) console.error("  " + failure);
  console.error("  The guard's own false-positive audit failed. Fix the guard; do not reword the code it guards.");
  process.exit(1);
}

let source;
const failures = [];
try {
  source = readFileSync(join(ROOT, TARGET), "utf8");
} catch (error) {
  failures.push(`cannot read ${TARGET} — ${error.message}. If this file moved, this check must move with it, not be deleted.`);
}
if (source !== undefined) failures.push(...analyze(source));

let routeSource;
try {
  routeSource = readFileSync(join(ROOT, ROUTE_TARGET), "utf8");
} catch (error) {
  failures.push(`cannot read ${ROUTE_TARGET} — ${error.message}. If this file moved, this check must move with it, not be deleted.`);
}
if (routeSource !== undefined) failures.push(...analyzeRoute(routeSource));

if (failures.length) {
  console.error(`core/ openTasks parked-flip check FAILED (${failures.length}):`);
  for (const failure of failures) console.error("  " + failure);
  process.exit(1);
}
console.log(
  `core/ openTasks parked-flip check passed (R7: factory flip stays forbidden after David's 2026-08-16 Tasks park lift; `
  + `the route branches; ${SELF_TEST_FIXTURES.length + ROUTE_SELF_TEST_FIXTURES.length} self-test fixtures green).`,
);
