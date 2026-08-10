#!/usr/bin/env node
// LIFECYCLE: permanent
//
// The lane runner: one entry point per verification lane, wrapping the commands
// that already exist.
//
// This is PLUMBING. It invents no checks, changes no thresholds, and enforces no
// budgets. Every command below is one you could type yourself, and typing it
// yourself is still correct — the lane exists so that "which lane did you run?"
// has a mechanical answer instead of a remembered one.
//
// ── THE LANE MODEL ──────────────────────────────────────────────────────────
// L0 reflex (<1s)  static only: import fence, contract drift, wire conformance,
//                  codegen drift. No build, no server, no app.
// L1 unit (<5s)    `pnpm verify` — build + unit tests + the static checks.
// L2 hermetic      backend suite + integration/ + cross-side wire agreement.
//    (<25s)        Real loopback HTTP, own ports, no shells, no simulator.
//                  Safe to run alongside a live stack.
// L3 real (~90s)   the whole stack, headless and assert-based.
//
// THE RULE THIS ENCODES: **an agent may only claim something works at the lane
// it actually ran.** L1 green means "the unit holds". It does not mean "the app
// works", and the receipt written here records which lane it was so the claim
// cannot quietly inflate later.
//
// ── WHY THIS IS NOT IN .github/checks-manifest.yaml (yet) ───────────────────
// It should be, and the rows below are deliberately shaped like manifest rows
// (id / command / triggers / reason) so the move is mechanical. It is not there
// yet for one concrete reason: `.github/scripts/run_checks.py` REQUIRES every
// check to declare BOTH the `local` and `ci` lanes —
//
//     missing_lanes = sorted({"local", "ci"} - set(check.lanes))
//     if missing_lanes: errors.append(f"{check.id}: missing required lanes: ...")
//
// — and there is no CI lane for the `core/` world yet: that manifest drives the
// OLD tree's CI, which has neither a pnpm/bun toolchain for `core/` nor the
// sibling `platform` checkout that L2 needs, and L3 needs a macOS host with
// free ports and a simulator. Registering these rows there today would not give
// us a CI lane; it would give us four checks that fail in CI on every PR.
//
// So: same shape, same vocabulary, local-only, in one file, until `core/` has a
// CI lane worth registering. When it does, these rows move over as-is.

import { execSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import {
  REPO_PATHS,
  assertCrossTreePairingIsDeclared,
  assertRepoPathsExist,
  WORKSPACE_ROOT,
  readStampFile,
  verifyArtifact,
} from "./lib/provenance.mjs";

const CORE_REPO = REPO_PATHS["core-foundation"];
const PLATFORM_REPO = REPO_PATHS.platform;

/** Loaded at the bottom; null when the receipt system is unavailable. */
let receiptsModule = null;

/**
 * `preflight` runs before the lane's commands and can refuse to start. It is
 * where a lane states the things that would make its own result meaningless.
 */
export const LANES = {
  L0: {
    name: "reflex — static only",
    budgetNote: "<1s",
    reason: "the four checks that can contradict a green build without running anything: import fence, contract drift, wire conformance, codegen drift",
    /**
     * NOTE — `bun run qa:contracts` IS NOT AN L0 CHECK, despite being described
     * as one. Measured: 18.6s, because `scripts/qa-contracts.ts` line 281 runs
     * `bun test` — the ENTIRE 630-test backend suite — after verifying the
     * vendored contract tarball. Putting it in a "<1s reflex" lane would have
     * made the fast lane twenty times over budget and, worse, made L0 and L2
     * near-duplicates while both claimed to be different questions.
     *
     * The contract-DRIFT part is the two contract-tests files, which take 21ms.
     * That is what belongs here. The full `qa:contracts` runs in L2, where its
     * cost is already paid.
     */
    steps: [
      { cwd: PLATFORM_REPO, command: "bun run lint:imports" },
      { cwd: PLATFORM_REPO, command: "bun test contract-tests/ratified-contracts.test.ts contract-tests/qa-contracts.test.ts" },
      { cwd: join(CORE_REPO, "core"), command: "node scripts/check-wire-conformance.mjs" },
      { cwd: join(CORE_REPO, "core"), command: "pnpm codegen:check" },
    ],
  },
  L1: {
    name: "unit — frontend",
    budgetNote: "<5s",
    reason: "pnpm verify is the Definition of Done for core/: build + unit tests + eight static checks",
    steps: [{ cwd: join(CORE_REPO, "core"), command: "pnpm verify" }],
  },
  L2: {
    name: "hermetic integration",
    budgetNote: "<25s",
    reason: "real loopback HTTP on its own ports, both sides of the wire, no shells and no simulator — the strongest thing that can run while a stack is live",
    /**
     * L2 SPANS TWO REPOS AND THREE COMMANDS, and it now has ONE entry point.
     *
     * The preflight is not ceremony. `integration/cross-side/wire-agreement.test.mjs`
     * imports the BUILT `core/packages/adapters-platform/dist/index.js`. A stale
     * dist means that test exercises YESTERDAY'S CLIENT and passes — a green
     * result about code that is no longer in the tree. That is the same
     * "measured artifact is not the edited artifact" failure this whole program
     * exists to eliminate, sitting inside the lane meant to catch it.
     */
    preflight: () => {
      const distIndex = join(CORE_REPO, "core", "packages", "adapters-platform", "dist", "index.js");
      if (!existsSync(distIndex)) {
        return { ok: false, reason: "adapters-platform is not built — the cross-side test would import nothing", action: `cd ${join(CORE_REPO, "core")} && pnpm -r build` };
      }
      const stamp = verifyArtifact(readStampFile(join(CORE_REPO, "core", "packages", "surfaces", "dist", "omi-build-stamp.json")));
      if (!stamp.agree) {
        return { ok: false, reason: `surfaces dist is stale — ${stamp.reason}`, action: `cd ${join(CORE_REPO, "core")} && pnpm -r build` };
      }
      return { ok: true };
    },
    // `qa:contracts` subsumes `bun test` and `lint:imports` (see its lines
    // 280-282), so running it here instead of alongside them keeps the suite
    // from executing twice. It also re-verifies the vendored contract tarball
    // against contracts.lock.json, which is the seam this lane is really about.
    /**
     * THE FOURTH STEP IS NOT NEW COVERAGE — IT IS COVERAGE THAT RAN NOWHERE.
     *
     * `integration/lib/*.test.mjs` are the red-proofs for L3's own assertion
     * path: the file that exists because the seventh failure of that night was
     * inside the acceptance path built to catch the other six. They were run by
     * no lane. `pnpm verify` is scoped to `core/` and these live outside it, so
     * "an assertion that has never been seen red does not count" was being
     * enforced by a suite nobody executed — the rule applied to product code and
     * exempting the machinery that judges product code.
     *
     * They belong in L2 and not L1: they are outside `core/`, they are the
     * companion of the cross-side test already in this lane, and they are
     * hermetic — no ports, no servers, safe alongside a live stack.
     */
    steps: [
      { cwd: PLATFORM_REPO, command: "bun run qa:contracts" },
      { cwd: PLATFORM_REPO, command: "bun test integration/" },
      // EVERY cross-side file, by directory rather than by list. Three of these
      // arrived from three different lanes and each ran in NO gate until
      // someone remembered this line — CORPUS's rendering-parity harness and
      // the provenance-agreement check were both sitting on trunk ungated. A
      // hand-maintained list makes registration a thing to remember, and the
      // measured failure mode of "a thing to remember" in this program is a
      // test that exists and guards nothing.
      //
      // The rendering-parity harness belongs HERE and not in the unit step
      // below: it boots `platform/integration/control/live-service.ts`, so its
      // resource profile is a cross-side test's, not an in-process one, and its
      // cost should be visible next to its peers rather than hidden in a step
      // labelled as unit tests.
      { cwd: CORE_REPO, command: "node --test integration/cross-side/*.test.mjs" },
      // `receipts-concurrency.test.mjs` is here for the same reason as the rest
      // of this step: CLIENT landed it with the receipts schema-2 fix and
      // correctly did not touch this file, so until this line it ran in no
      // gate — a measurement nobody reads, guarding a defect that made stdout
      // truthful while the durable artifact described the wrong tree.
      //
      // Worth knowing what it covers, because its own red-proof is the
      // interesting part: dropping `repoRoot` from the receipt KEY (leaving it
      // on the stamp) left the suite GREEN, because every lane in the fixture
      // had different content and the tree hash was already separating them.
      // The clause exists for the case a tree hash CANNOT separate — two
      // worktrees, same trunk commit, both clean, byte-identical at different
      // paths — which is the ordinary configuration every lane in this run has
      // been in, mine included. That case is now constructed explicitly, and it
      // asserts the two tree hashes really are equal first, or it would pass
      // vacuously the moment the fixtures drifted — the same shape as the
      // mutation that stayed green.
      { cwd: CORE_REPO, command: "node --test integration/lib/receipts.test.mjs integration/lib/receipts-concurrency.test.mjs integration/lib/run-report.test.mjs integration/lib/write-journey.test.mjs" },
    ],
  },
  L3: {
    name: "real integration — the whole stack",
    budgetNote: "~90s headless",
    reason: "the only lane entitled to the claim 'the app works'; headless and assert-based by default, headed only for a human",
    steps: [
      {
        cwd: CORE_REPO,
        command: "integration/dev-stack.sh --no-ios --generation platform --up --assert",
      },
    ],
  },
};

/**
 * ── A ROOT THAT IS BEHIND ITS OWN REMOTE IS NOT A ROOT ANYONE CHOSE ─────────
 *
 * `assertCrossTreePairingIsDeclared` made a lane state WHICH trees it measures.
 * It cannot see WHEN. The shared `platform` checkout spent this run many commits
 * behind its trunk while lanes declared it and measured it, and the failure is
 * the one this repo keeps paying for: every individual number accurate, the
 * conclusion wrong, because the tree measured was not the tree anyone means.
 * A coordinator counted a lane's tests against it and got a wrong answer; a lane
 * (this one) drove the retired fence harness out of it for an hour after the
 * real write door had landed.
 *
 * A shared checkout has no owner and nothing updates it. So this refuses, and
 * the refusal names the one command that fixes it. It is deliberately narrow:
 *
 *  - Only when the remote-tracking ref EXISTS and is strictly ahead. No network
 *    call, no fetch — a lane at 4am on a flaky link must not be blocked by a
 *    check about freshness, and a stale remote ref simply makes this quiet.
 *  - `git rev-list --count HEAD..<upstream>`, so a root that is ahead (a lane
 *    with unpushed commits — the normal case) is untouched.
 *  - A DIRTY tree still refuses, but says the fix is not a pull, because
 *    somebody is working in it and `--ff-only` will not run.
 *
 * ── SHARED CHECKOUTS ONLY, AND THAT SCOPE WAS FOUND BY THE GUARD ITSELF ────
 *
 * The first version checked every declared root and immediately refused this
 * lane's OWN worktree: trunk had moved while the lane worked, which is the
 * ordinary state of a lane between rebases and is exactly what §4's
 * rebase-and-re-verify step exists to resolve. Refusing it would have made the
 * mandated loop unrunnable — §10's defect, committed by a guard written to
 * prevent a different one.
 *
 * A LANE worktree behind its trunk is normal and has an owner who will rebase.
 * A SHARED checkout behind its trunk has no owner, nothing updates it, and
 * every lane that declares it measures a tree nobody is on. Only the second is
 * refused, and that is the case the coordinator actually hit.
 *
 * §8: this is a new guard and lands PROVISIONAL. If it fires on another lane
 * that is a swarm-wide blocker, not something to route around — the answer is
 * to update the checkout, which is what the message says.
 *
 * red-proof: `git -C <a root> reset --hard HEAD~1` and run any lane. It must
 * refuse and print that root, the count, and the pull command; `git merge
 * --ff-only` then makes it pass. Applied and observed red before this landed.
 */
export function assertDeclaredRootsAreCurrent() {
  const behind = [];
  for (const [repo, path] of Object.entries(REPO_PATHS)) {
    // Shared checkouts only. See the scope note above.
    if (path !== join(WORKSPACE_ROOT, repo)) continue;
    let upstream = "";
    try {
      upstream = execSync("git rev-parse --abbrev-ref --symbolic-full-name @{upstream}", {
        cwd: path, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"],
      }).trim();
    } catch {
      continue; // no upstream configured — nothing to be behind of
    }
    if (upstream === "") continue;
    let count = 0;
    try {
      count = Number(execSync(`git rev-list --count HEAD..${upstream}`, {
        cwd: path, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"],
      }).trim());
    } catch {
      continue;
    }
    if (!Number.isFinite(count) || count <= 0) continue;
    let dirty = false;
    try {
      dirty = execSync("git status --porcelain", { cwd: path, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim() !== "";
    } catch {
      dirty = false;
    }
    behind.push({ repo, path, upstream, count, dirty });
  }
  if (behind.length === 0) return;
  const lines = behind.map((b) =>
    `  ${b.repo.padEnd(16)} ${b.path}\n`
    + `    ${b.count} commit(s) behind ${b.upstream}${b.dirty ? " — and the tree is DIRTY" : ""}\n`
    + `    ${b.dirty
        ? "somebody is working in this checkout. Do NOT pull it. Point your root elsewhere, or ask them."
        : `git -C ${b.path} pull --ff-only`}`);
  throw new Error(
    "refusing to measure a root that is behind its own remote.\n\n"
    + lines.join("\n")
    + "\n\nEvery number from a stale root is accurate about a tree nobody is on."
    + " That is not a slower failure than a red lane; it is a silent wrong answer,"
    + " and this run has already paid for it twice.",
  );
}

function runLane(laneId, { json = false } = {}) {
  const lane = LANES[laneId];
  if (!lane) {
    process.stderr.write(`unknown lane: ${laneId}. Known: ${Object.keys(LANES).join(", ")}\n`);
    process.exit(2);
  }
  const started = Date.now();
  const results = [];
  let ok = true;

  if (lane.preflight) {
    const pre = lane.preflight();
    if (!pre.ok) {
      const payload = { lane: laneId, result: "fail", error: `preflight: ${pre.reason}`, next_actions: [pre.action] };
      if (json) process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
      else {
        process.stderr.write(`✗ ${laneId} preflight refused to start: ${pre.reason}\n`);
        process.stderr.write(`    ${pre.action}\n`);
      }
      process.exit(1);
    }
  }

  if (!json) {
    process.stdout.write(`▸ ${laneId} — ${lane.name} (${lane.budgetNote})\n`);
    // WHICH TREES, AND WHAT IS CHECKED OUT IN THEM, every run, before any of them
    // are measured. The receipt has carried this all along and nobody read it; a
    // lane read its own green L2 as a statement about its diff while the platform
    // stamp named the shared checkout. Evidence nobody looks at is not evidence.
    //
    // The BRANCH is here because a shared checkout has no owner: mid-audit, the
    // shared `platform` was found sitting on `main` — the branch BRANCHES.md
    // records as stale — switched by another session. Every lane pointing at it
    // would have measured the wrong tree and passed. One line of output turns
    // that from something someone has to notice into something nobody can miss.
    for (const [repo, path] of Object.entries(REPO_PATHS)) {
      let at = "";
      try {
        const branch = execSync("git rev-parse --abbrev-ref HEAD", { cwd: path, encoding: "utf8" }).trim();
        const commit = execSync("git rev-parse --short HEAD", { cwd: path, encoding: "utf8" }).trim();
        at = `  (${branch} @ ${commit})`;
      } catch {
        at = "  (not a git checkout)";
      }
      process.stdout.write(`  ${repo.padEnd(16)} ${path}${at}\n`);
    }
  }
  for (const step of lane.steps) {
    const stepStart = Date.now();
    let status = 0;
    let output = "";
    try {
      output = execSync(step.command, { cwd: step.cwd, encoding: "utf8", stdio: json ? "pipe" : "inherit" }) ?? "";
    } catch (error) {
      status = error.status ?? 1;
      output = `${error.stdout ?? ""}${error.stderr ?? ""}`;
      ok = false;
    }
    const durationMs = Date.now() - stepStart;
    results.push({ command: step.command, cwd: step.cwd, status, durationMs, ...(json && status !== 0 ? { output: output.slice(-4000) } : {}) });
    // Durations are PRINTED, never enforced. A time budget that fails a lane
    // turns a slow machine into a red build and teaches people to skip the lane;
    // the number is here to be noticed by a human, not to gate anything.
    if (!json) process.stdout.write(`  ${status === 0 ? "✓" : "✗"} ${step.command}  (${durationMs}ms)\n`);
    if (status !== 0) break;
  }

  const durationMs = Date.now() - started;
  const receipt = { lane: laneId, result: ok ? "pass" : "fail", durationMs, steps: results };

  // Arbiter counters. L3's registry row REQUIRES them, and requiring them is the
  // point: a receipt that says only "the runner exited 0" is the false-green
  // shape restated in bookkeeping form. L3's arbiters come from the backend's
  // own counters via the run report, not from the launcher's opinion of itself.
  const arbiters = { steps: results.map((r) => ({ command: r.command, status: r.status, durationMs: r.durationMs })) };
  if (laneId === "L3") {
    try {
      const report = JSON.parse(readFileSync(join(process.env["OMI_DEV_STACK_RUNDIR"] ?? "/tmp/omi-dev-stack", "last-run.json"), "utf8"));
      arbiters.totalRequests = report.backend?.status?.served?.totalRequests ?? null;
      arbiters.domainReadsServed = report.backend?.status?.served?.domainReadsServed ?? null;
      arbiters.readsByThisRun = report.backend?.readsByThisRun ?? null;
      arbiters.runId = report.run?.id ?? null;
      arbiters.assertions = (report.assertions ?? []).map((a) => ({ name: a.name, result: a.result }));
    } catch {
      // Absent counters must not be silently replaced by zeros: writeReceipt
      // refuses a `pass` whose required arbiters are missing, which is exactly
      // the behaviour we want. Leave them absent and let it refuse.
      ok = false;
      receipt.result = "fail";
    }
  }

  let receiptFile = null;
  try {
    // The lane must still RUN if the receipt system is absent or broken — a
    // verification lane that cannot execute without its own bookkeeping is a
    // gate with no hatch.
    if (receiptsModule) {
      receiptsModule.writeReceipt({
        lane: laneId,
        result: receipt.result,
        durationMs,
        command: lane.steps.map((s) => s.command).join(" && "),
        arbiters,
      });
      receiptFile = receiptsModule.receiptPath(laneId);
    }
  } catch (error) {
    if (!json) process.stderr.write(`  ! receipt not written: ${error.message}\n`);
  }

  if (json) process.stdout.write(`${JSON.stringify({ ...receipt, arbiters, receiptPath: receiptFile }, null, 2)}\n`);
  else process.stdout.write(`  ${receipt.result.toUpperCase()} in ${durationMs}ms${receiptFile ? ` — receipt ${receiptFile}` : ""}\n`);
  return receipt.result === "pass" ? 0 : 1;
}

const argv = process.argv.slice(2);
const laneArg = argv.find((a) => !a.startsWith("--"));
if (!laneArg || argv.includes("--help")) {
  process.stdout.write(
    `usage: integration/lanes.mjs <L0|L1|L2|L3> [--json]\n\n${
      Object.entries(LANES)
        .map(([id, l]) => `  ${id}  ${l.name.padEnd(34)} ${l.budgetNote}\n      ${l.reason}`)
        .join("\n")
    }\n`,
  );
  // `--help` is a successful request for help, not a usage error. Exiting
  // nonzero here made `make lanes` fail, which is the kind of small lie that
  // makes a wrapper feel untrustworthy.
  process.exit(argv.includes("--help") ? 0 : 2);
}
// Before anything spawns: state which repo is missing and how to point at it.
// A lane that cannot see a repo must say so, not fail later inside git.
try {
  assertRepoPathsExist();
  // ...and refuse a lane/shared pairing nobody chose. See provenance.mjs.
  assertCrossTreePairingIsDeclared();
  // ...and refuse a root that is BEHIND its own remote. See below.
  assertDeclaredRootsAreCurrent();
} catch (err) {
  process.stderr.write(`${err.message}\n`);
  process.exit(2);
}

try {
  receiptsModule = await import("./lib/receipts.mjs");
} catch {
  receiptsModule = null;
}
process.exit(runLane(laneArg.toUpperCase(), { json: argv.includes("--json") }));
