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

import { REPO_PATHS, readStampFile, verifyArtifact } from "./lib/provenance.mjs";

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
    steps: [
      { cwd: PLATFORM_REPO, command: "bun run qa:contracts" },
      { cwd: PLATFORM_REPO, command: "bun test integration/" },
      { cwd: CORE_REPO, command: "node --test integration/cross-side/wire-agreement.test.mjs" },
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

  if (!json) process.stdout.write(`▸ ${laneId} — ${lane.name} (${lane.budgetNote})\n`);
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
      arbiters.servedRequests = report.backend?.stats?.servedRequests ?? null;
      arbiters.servedReads = report.backend?.stats?.servedReads ?? null;
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
try {
  receiptsModule = await import("./lib/receipts.mjs");
} catch {
  receiptsModule = null;
}
process.exit(runLane(laneArg.toUpperCase(), { json: argv.includes("--json") }));
