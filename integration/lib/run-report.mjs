// LIFECYCLE: permanent
//
// The L3 run report: one machine-readable object per run, and the named
// assertions evaluated over it.
//
// WHY THIS IS NOT IN BASH. dev-stack.sh gathers FACTS — ports, pids, exit
// statuses, log lines, HTTP bodies. This module turns facts into a VERDICT. The
// split matters because the verdict logic is the part that has been wrong: a
// shell counted requests at dispatch and called it PASS; a launcher read the
// previous run's `status=PASS` out of a stale log. Verdict logic in a testable
// module can be red-proofed. Verdict logic spread across a 500-line bash script
// cannot.
//
// ── WHAT AN ASSERTION IS HERE ──────────────────────────────────────────────
// Every assertion names its ARBITER: `{claim, measuredBy, corroboratedBy}`.
//
// That triple is the entire lesson of this program. Every false green in its
// history came from ONE measurement answering a question slightly different from
// the one being asked, with nothing to contradict it:
//
//   - `servedCount=4 status=PASS` while the backend served 0 — the shell
//     measured DISPATCHES, the claim was about OUTCOMES. Both numbers accurate.
//   - `generation=platform` honored, then never used, because the route
//     defaulted to home and took the legacy branch. Nothing was rejected.
//   - "window should be open now" for a process killed seconds earlier.
//
// So an assertion with `corroboratedBy: null` is not forbidden — some things
// genuinely have one arbiter — but it is TYPED as `singleMeasurement: true` and
// says so in its own output. A reader can then see exactly which claims rest on
// one number, which is the information that was missing every time this failed.
//
// ── WHAT IS DELIBERATELY NOT ASSERTED ──────────────────────────────────────
// Rendered CONTENT. Not row text, not row counts, not fixture values. The system
// is still moving; an assertion on the third row's text costs more in churn than
// it catches, and row-count assertions are the canonical decorative shape called
// out in core/AGENTS.md rule 14. What is asserted are INVARIANTS: the selection
// that was honored is the one that rendered, the traffic was served to THIS run,
// the artifacts were built from THIS tree, the window is alive.

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import {
  REPO_PATHS,
  formatStamp,
  readStampFile,
  short,
  verifyArtifact,
  workspaceStamps,
} from "./provenance.mjs";

export const RUN_REPORT_SCHEMA_VERSION = 1;

const SURFACES_DIST = join(REPO_PATHS["core-foundation"], "core", "packages", "surfaces", "dist");

/**
 * The assertion registry. Adding an assertion means adding a row, not editing
 * the evaluator — the same registry shape `core/scripts/check-wire-conformance.mjs`
 * uses for seams, for the same reason: a table can be read and audited, and
 * scattered `if` statements cannot.
 *
 * `applies(report)` keeps an assertion from firing where it is meaningless — a
 * platform-generation assertion on a legacy run would be a guaranteed red that
 * teaches people to pass `|| true`.
 */
/**
 * Assertions that say something about what the APP DID, as opposed to what is
 * merely true of the machine. A run in which none of these ran is inconclusive
 * however green the rest looks — see the guard at the bottom of buildReport.
 */
export const PROVES_BEHAVIOR = new Set([
  "served_reads_by_this_run", "no_generation_mismatch", "window_alive", "write_journey",
]);

export const ASSERTIONS = [
  {
    name: "backend_reachable",
    claim: "the backend under test answers on its own control plane",
    measuredBy: "launcher: GET /qa/stats",
    corroboratedBy: null,
    applies: () => true,
    evaluate: (report) =>
      report.backend.reachable
        ? { result: "pass", detail: `${report.backend.url} answered /qa/stats` }
        : { result: "fail", detail: `no answer from ${report.backend.url}/qa/stats` },
  },
  {
    name: "stamps_agree",
    claim: "every artifact in this run was built from the source that is checked out right now",
    measuredBy: "stamp files written at build time into dist/, the .app bundle, and the backend process",
    corroboratedBy: "git: the tree hash of the working tree, recomputed at each artifact's own declared scope",
    applies: (report) => Object.keys(report.provenance.artifacts).length > 0,
    evaluate: (report) => {
      const stale = Object.entries(report.provenance.artifacts).filter(([, a]) => !a.agree);
      return stale.length === 0
        ? { result: "pass", detail: `${Object.keys(report.provenance.artifacts).length} artifact stamp(s) match the working tree` }
        : {
            result: "fail",
            detail: stale.map(([name, a]) => `${name}: ${a.reason}`).join("; "),
          };
    },
  },
  {
    name: "served_reads_by_this_run",
    claim: "the app THIS run launched read the backend at least once",
    measuredBy: "backend: servedReadsByClient[<this run's client id>]",
    corroboratedBy: "macOS shell: ACCEPTANCE succeeded=N, the host-observed count of 2xx responses",
    // Only meaningful when something was actually pointed at the new backend.
    applies: (report) => report.run.generation === "platform" && (report.apps.macos !== null || report.apps.ios !== null),
    evaluate: (report) => {
      const mine = report.backend.readsByThisRun;
      const succeeded = report.apps.macos?.acceptance?.succeeded ?? null;
      if (mine > 0 && (succeeded === null || succeeded > 0)) {
        return { result: "pass", detail: `backend served ${mine} read(s) to client ${report.run.clientId}; shell observed ${succeeded ?? "n/a"} success(es)` };
      }
      if (mine === 0) {
        return {
          result: "fail",
          detail:
            `backend served ZERO reads to client ${report.run.clientId}`
            + ` (global delta was ${report.backend.readsDelta}, which ANY client could have produced — that is why this is keyed by client id)`,
        };
      }
      return { result: "fail", detail: `backend counted ${mine} read(s) for this run but the shell observed ${succeeded} success(es) — the two arbiters disagree` };
    },
  },
  {
    name: "no_generation_mismatch",
    claim: "the backend generation the host SELECTED is the one that actually RENDERED",
    measuredBy: "surface: __OMI_RUNTIME_STATE__.mismatch, read out of the live webview",
    corroboratedBy: "backend: reads served for this run's client id on the platform route",
    /**
     * Fires whenever a macOS app was DRIVEN — not only when its runtime state
     * happened to be readable.
     *
     * The earlier `applies: runtimeState != null` guard meant that losing the
     * evidence made the assertion quietly disappear, and the run still reported
     * PASS. An assertion that opts out when it cannot measure is worse than no
     * assertion: it converts "we do not know" into "we checked". If we cannot
     * read what the app rendered, that is a failure to measure, and it is
     * reported as one.
     */
    applies: (report) => report.apps.macos !== null,
    evaluate: (report) => {
      const state = report.apps.macos.runtimeState;
      if (state == null) {
        return {
          result: "fail",
          detail: "could not read __OMI_RUNTIME_STATE__ from the app (no PROBE_JS line) — the run cannot say which generation rendered, so it does not get to claim one",
        };
      }
      if (state.mismatch != null) {
        return { result: "fail", detail: `${state.mismatch} — the selection was honored and then never used` };
      }
      if (state.rendered === null) {
        return { result: "fail", detail: "the surface never recorded what it rendered (rendered=null) — nothing was constructed" };
      }
      const rejected = Array.isArray(state.rejected) ? state.rejected : [];
      if (rejected.length > 0) {
        return { result: "fail", detail: `generation selection rejected: ${JSON.stringify(rejected)}` };
      }
      return { result: "pass", detail: `selected memories=${state.selected?.memories}, rendered ${state.rendered.surface} (${state.rendered.memoriesGeneration})` };
    },
  },
  {
    /**
     * THE WRITE JOURNEY, folded into the run's verdict.
     *
     * The journey judges itself (`write-journey.mjs`) and this row does not
     * re-judge it — a second judgement could disagree with the first, and only
     * one of the two would be in the report. What this row adds is the one
     * thing the journey cannot know: whether its result is allowed to redden
     * L3 for six lanes on a shared trunk tonight.
     *
     * Charter R11 excludes the stage-(a) journey from the green gate. That
     * exclusion is DERIVED, not declared: `gating` is true exactly when
     * `/v1/tasks/ops` has a WIRE_PATH_REGISTRY row, so it retires itself the
     * moment OPS's route lands. Until then a journey failure is reported in
     * full, in the same object, and this lane gates on it through
     * `dev-stack.sh`'s own exit status — it is excluded from L3's verdict, not
     * from anybody's attention.
     */
    name: "write_journey",
    claim: "the scripted write journey — create, applied, idempotent replay, forced stale epoch, dead letter — holds against a live write door",
    measuredBy: "server: the fence's own decision counter, joined to this run's id",
    corroboratedBy: "wire + client: the bytes this run received, read by the shipped classifyWriteOpsResponse",
    applies: (report) => report.writeJourney !== null,
    evaluate: (report) => {
      const j = report.writeJourney;
      const failed = j.assertions.filter((a) => a.result === "fail");
      if (failed.length > 0 && j.gating !== true) {
        // `advisory`, NOT `pass`. Returning "pass" here would have been the
        // exact move this file already criticises two rows down: converting "we
        // do not know" into "we checked". An advisory result does not fail the
        // run and does not count toward the behavioural guard either, so a
        // broken stage-(a) journey can neither redden six lanes' trunk nor
        // silently satisfy the "this run proved something" test.
        return {
          result: "advisory",
          detail:
            `journey ${j.result.toUpperCase()} at stage (${j.stage}) with ${failed.length} failing step(s)`
            + ` — NOT GATING L3 (${j.gatingNote}).`
            + ` Failing: ${failed.map((a) => `${a.name}: ${a.detail}`).join(" | ")}`,
        };
      }
      if (failed.length > 0) {
        return { result: "fail", detail: failed.map((a) => `${a.name}: ${a.detail}`).join(" | ") };
      }
      const pendingNames = j.pending ?? [];
      return {
        result: "pass",
        detail:
          `stage (${j.stage}) door ${j.door.url}: ${j.assertions.filter((a) => a.result === "pass").length} step(s) green`
          + (pendingNames.length > 0 ? `, ${pendingNames.length} PENDING on a door that does not exist yet (${pendingNames.join(", ")})` : "")
          + (j.gating === true ? "" : ` — not gating L3 (${j.gatingNote})`),
      };
    },
  },
  {
    name: "window_alive",
    // Worded for BOTH display modes. Runs are headless by default now, so
    // "there is a window a human could QA" would be false on the default path —
    // and a claim that is routinely false is how a summary line stops being
    // read. What is actually verified is that the app is alive and serving; in
    // headed mode that same app is the window in front of you.
    claim: "the app this run launched is alive and serving its surface (in --headed mode, that is the window in front of you)",
    measuredBy: "launcher: the pid the launcher recorded is still alive",
    corroboratedBy: "launcher: that same shell's loopback still answers HTTP",
    applies: (report) => report.apps.macos !== null && report.apps.macos.windowed === true,
    evaluate: (report) => {
      const m = report.apps.macos;
      if (!m.pidAlive) return { result: "fail", detail: `pid ${m.pid ?? "unknown"} is gone — there is NO window to QA` };
      if (!m.surfaceAnswers) return { result: "fail", detail: `pid ${m.pid} is alive but its surface on ${m.port} does not answer — useless to QA` };
      return { result: "pass", detail: `pid ${m.pid} alive and serving http://127.0.0.1:${m.port}/` };
    },
  },
];

function parseJsonSafe(text) {
  if (typeof text !== "string" || text.trim() === "") return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/**
 * `PROBE_JS: {"route":...}` — the shell's existing JS probe seam prints the
 * evaluated value on one line. Reusing it (rather than adding a new channel)
 * is deliberate: it is already the shell's way of reporting what the page
 * thinks, and a second channel is a second thing that can silently stop working.
 */
export function parseProbeJs(raw) {
  if (typeof raw !== "string") return null;
  const line = raw.split("\n").reverse().find((l) => l.includes("PROBE_JS:"));
  if (!line) return null;
  const payload = line.slice(line.indexOf("PROBE_JS:") + "PROBE_JS:".length).trim().replace(/\s+error:\s+.*$/, "");
  // evaluateJavaScript hands back a JS string, so the value arrives already
  // JSON-encoded once; it may or may not be quoted depending on the bridge.
  const direct = parseJsonSafe(payload);
  if (direct && typeof direct === "object") return direct;
  if (typeof direct === "string") return parseJsonSafe(direct);
  return null;
}

/** `ACCEPTANCE phase=x bridge=y dispatched=N succeeded=N ... status=PASS` */
export function parseAcceptanceLine(raw) {
  if (typeof raw !== "string" || !raw.includes("ACCEPTANCE")) return null;
  const line = raw.split("\n").reverse().find((l) => l.includes("ACCEPTANCE ")) ?? raw;
  const field = (name) => {
    const m = line.match(new RegExp(`\\b${name}=([^\\s]+)`));
    return m ? m[1] : null;
  };
  const num = (name) => {
    const v = field(name);
    return v === null ? null : Number.parseInt(v, 10);
  };
  return {
    line: line.trim(),
    phase: field("phase"),
    bridge: field("bridge"),
    dispatched: num("dispatched"),
    succeeded: num("succeeded"),
    httpError: num("httpError"),
    transportFailure: num("transportFailure"),
    servedCount: num("servedCount"),
    status: field("status"),
    shellStamp: field("shellStamp"),
    surfaceStamp: field("surfaceStamp"),
    clientId: field("clientId"),
  };
}

function readsFor(stats, clientId) {
  const byClient = stats?.servedReadsByClient;
  if (byClient == null || typeof byClient !== "object") return null;
  return Number(byClient[clientId] ?? 0);
}

/**
 * Build the report from the raw facts dev-stack.sh collected.
 *
 * Provenance is gathered HERE rather than passed in, so a caller cannot hand the
 * report a stamp it invented.
 */
export function buildReport(facts) {
  const statsBefore = parseJsonSafe(facts.backendStatsBefore) ?? {};
  const statsAfter = parseJsonSafe(facts.backendStatsAfter) ?? {};
  const reachable = typeof statsAfter.servedRequests === "number";

  const artifacts = {};
  // Checked whenever the stamp exists, INCLUDING in attach mode. Attach does not
  // build the dist, but the dist is still what the running app is serving —
  // "I did not build it" is not a reason to stop asking whether it is current.
  const distStampPath = join(SURFACES_DIST, "omi-build-stamp.json");
  if (existsSync(distStampPath)) {
    artifacts["surfaces-dist"] = { ...verifyArtifact(readStampFile(distStampPath)), path: distStampPath };
  }
  if (facts.macos?.buildDir && facts.macos?.appName) {
    const appStampPath = join(facts.macos.buildDir, `${facts.macos.appName}.app`, "Contents", "Resources", "omi-build-stamp.json");
    if (existsSync(appStampPath)) {
      artifacts["macos-app"] = { ...verifyArtifact(readStampFile(appStampPath)), path: appStampPath };
    }
  }
  if (statsAfter.stamp) {
    artifacts["backend-process"] = { ...verifyArtifact(statsAfter.stamp), path: `${facts.backendUrl}/qa/stats` };
  }

  const readsBefore = Number(statsBefore.servedReads ?? 0);
  const readsAfter = Number(statsAfter.servedReads ?? 0);
  const readsByThisRun = readsFor(statsAfter, facts.clientId);

  const macos = facts.macos
    ? {
        port: facts.macos.port ?? null,
        pid: facts.macos.pid ?? null,
        windowed: facts.macos.windowed === true,
        pidAlive: facts.macos.pidAlive === true,
        surfaceAnswers: facts.macos.surfaceAnswers === true,
        launchStatus: facts.macos.launchStatus ?? null,
        acceptance: parseAcceptanceLine(facts.macos.acceptanceLog ?? facts.macos.acceptanceLine),
        runtimeState: parseProbeJs(facts.macos.acceptanceLog),
      }
    : null;

  const report = {
    schema: RUN_REPORT_SCHEMA_VERSION,
    run: {
      id: facts.runId,
      mode: facts.mode,
      startedAt: facts.startedAt,
      finishedAt: new Date().toISOString(),
      durationMs: facts.startedAt ? Date.now() - Date.parse(facts.startedAt) : null,
      generation: facts.generation,
      clientId: facts.clientId,
      attached: facts.attach === true,
    },
    provenance: { worktree: workspaceStamps(), artifacts },
    backend: {
      url: facts.backendUrl,
      reachable,
      stats: statsAfter,
      readsBefore,
      readsAfter,
      readsDelta: readsAfter - readsBefore,
      // null (not 0) when the backend predates per-client counting: "the backend
      // cannot answer this question" and "the answer is zero" are different
      // findings and must never collapse into one number.
      readsByThisRun,
    },
    apps: { macos, ios: facts.ios ?? null },
    // The verdict the journey wrote about itself, carried verbatim. Not
    // re-judged here: two judgements of one journey can disagree, and only one
    // of them would end up in this object.
    writeJourney: facts.writeJourney ?? null,
    writeJourneyPath: facts.writeJourneyPath ?? null,
    assertions: [],
    result: "pass",
  };

  report.assertions = ASSERTIONS.filter((a) => a.applies(report)).map((a) => {
    const outcome = a.evaluate(report);
    return {
      name: a.name,
      claim: a.claim,
      measuredBy: a.measuredBy,
      corroboratedBy: a.corroboratedBy,
      singleMeasurement: a.corroboratedBy === null,
      result: outcome.result,
      detail: outcome.detail,
    };
  });
  report.result = report.assertions.some((a) => a.result === "fail") ? "fail" : "pass";
  /**
   * A run that DROVE NOTHING has not proven that anything works, and must not
   * say "pass". `--only-backend --assert` can therefore only ever report
   * `inconclusive`: a server answering its own control plane is true, and a
   * build stamp matching the working tree is true, and neither is evidence that
   * the app does anything.
   *
   * This guard has now been wrong twice, and both corrections came from applying
   * a mutation rather than reading it:
   *   1. `assertions.length === 0` — unreachable dead code, because
   *      `backend_reachable` always applies. Its test passed with the branch
   *      mutated to "pass": rule 14's decorative-test shape exactly.
   *   2. "no corroborated assertion ran" — broke the moment `stamps_agree`
   *      started applying without an app, because static provenance IS
   *      corroborated and still says nothing about behavior.
   *
   * So the criterion is the honest one: did any assertion about the app's actual
   * BEHAVIOR run? That is the property "an agent may only claim something works
   * at the lane it actually ran" is really about.
   */
  // `advisory` results are excluded: an assertion the run chose not to gate on
  // has not established behaviour either. Counting it would let a suppressed
  // row supply the very evidence its suppression says it cannot supply.
  const behavioral = report.assertions.filter((a) => PROVES_BEHAVIOR.has(a.name) && a.result !== "advisory");
  if (report.result === "pass" && behavioral.length === 0) {
    report.result = "inconclusive";
  }
  return report;
}

export function formatHuman(report) {
  const out = [];
  const w = report.provenance.worktree;
  out.push(`run ${report.run.id}  mode=${report.run.mode}  generation=${report.run.generation}`);
  for (const [repo, stamp] of Object.entries(w)) out.push(`  tree  ${repo.padEnd(16)} ${formatStamp(stamp)}`);
  for (const [name, a] of Object.entries(report.provenance.artifacts)) {
    out.push(`  built ${name.padEnd(16)} ${a.agree ? "matches working tree" : `STALE — ${a.reason}`}`);
  }
  out.push("");
  out.push(`  backend ${report.backend.url}  servedReads ${report.backend.readsBefore} -> ${report.backend.readsAfter}`
    + `  (this run's client ${report.run.clientId}: ${report.backend.readsByThisRun ?? "not counted by this backend"})`);
  out.push("");
  for (const a of report.assertions) {
    const mark = { pass: "PASS", fail: "FAIL", advisory: "ADVS" }[a.result] ?? "FAIL";
    out.push(`  [${mark}] ${a.name}`);
    out.push(`         claim:  ${a.claim}`);
    out.push(`         by:     ${a.measuredBy}`);
    out.push(`         vs:     ${a.corroboratedBy ?? "(nothing — SINGLE MEASUREMENT, treat as weaker evidence)"}`);
    out.push(`         ${a.result === "pass" ? "saw" : "why"}:    ${a.detail}`);
  }
  out.push("");
  out.push(`  result: ${report.result.toUpperCase()}`);
  return out.join("\n");
}

/** JSON errors are `{error, next_actions[]}` — the fixit() idiom, machine-readable. */
export function nextActions(report) {
  const actions = [];
  for (const a of report.assertions.filter((x) => x.result === "fail")) {
    if (a.name === "stamps_agree") {
      actions.push("rebuild the stale artifact: cd core && pnpm --filter @omi-core/surfaces build (surfaces), or re-run the launcher (macOS app / backend)");
    }
    if (a.name === "served_reads_by_this_run") {
      actions.push("check integration/dev-stack.sh logs for OMI_GENERATION_REJECTED, and that the shell got OMI_API_BASE_URL + OMI_SURFACE_QUERY (generation alone leaves route=home, which takes the legacy branch)");
    }
    if (a.name === "no_generation_mismatch") {
      actions.push("the host asked for one generation and the surface rendered another: inspect resolveProductionRoute / resolveGenerationSelection in core/packages/surfaces/src/production/");
    }
    if (a.name === "window_alive") {
      actions.push("inspect the macOS shell log for an early exit; two runs sharing one build dir used to kill each other (see run-shell.sh)");
    }
    if (a.name === "backend_reachable") {
      actions.push("start the backend: integration/dev-stack.sh --only-backend --up, or unset OMI_BACKEND_URL if you pointed at someone else's");
    }
    if (a.name === "write_journey") {
      actions.push(`read the full journey verdict: node core-foundation/integration/lib/write-journey.mjs --format ${report.writeJourneyPath ?? "<the run's write-journey json>"}`);
    }
  }
  // An advisory row is not a failure and must still be actionable, or the
  // suppression quietly becomes silence.
  for (const a of report.assertions.filter((x) => x.result === "advisory")) {
    actions.push(`${a.name} was reported and NOT gated: ${a.detail.slice(0, 200)}`);
  }
  if (report.result === "inconclusive") {
    actions.push("this run asserted NOTHING — it proves nothing. Check that the mode you ran actually launched an app.");
  }
  return [...new Set(actions)];
}

if (process.argv[1] && process.argv[1].endsWith("run-report.mjs")) {
  const argv = process.argv.slice(2);
  const flag = (name) => (argv.indexOf(name) === -1 ? undefined : argv[argv.indexOf(name) + 1]);
  const facts = JSON.parse(readFileSync(flag("--facts"), "utf8"));
  // ONE report object per run, rendered twice at most. Building it twice —
  // once for the human and once for the machine — would let the two renderings
  // disagree, which is the whole failure class in miniature.
  const report = buildReport(facts);
  const actions = nextActions(report);
  const json = `${JSON.stringify(actions.length > 0 ? { ...report, next_actions: actions } : report, null, 2)}\n`;
  const out = flag("--out");
  if (out) writeFileSync(out, json);
  if (argv.includes("--json")) {
    process.stdout.write(json);
  } else {
    process.stdout.write(`${formatHuman(report)}\n`);
    for (const action of actions) process.stdout.write(`  next: ${action}\n`);
  }
  if (argv.includes("--assert") && report.result !== "pass") process.exit(1);
}
