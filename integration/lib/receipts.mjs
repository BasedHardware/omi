// LIFECYCLE: permanent
//
// The receipt system — the thing that lets an agent claim "L2 passed" and
// have that claim be checkable instead of taken on faith.
//
// THE GOVERNING PRINCIPLE (see integration/check-lane-claims.mjs for the
// enforcement side): an agent may only claim a lane at the level it actually
// ran it. Seven false-greens in one night shared the same root cause —
// something claimed a result the underlying mechanism never produced — and
// every one was caught by comparing two independent measurements, never by
// reading code or by a green suite. A receipt IS the independent measurement:
// it is written by the lane runner, not by the agent narrating about the
// lane runner, and it is keyed by tree hash so it cannot outlive the tree it
// describes.
//
// WHY TREE-HASH KEYING KILLS STALE EVIDENCE. A receipt records
// `worktreeStamp()` for every repo its lane covers. The moment you edit a
// declared source root, the tree hash changes and every existing receipt for
// that repo stops matching — there is no "mostly still valid" state. That is
// the same mechanism `integration/lib/provenance.mjs` uses for built
// artifacts; this module is provenance applied to *lane runs* instead of
// *build outputs*, and it deliberately reuses `worktreeStamp` /
// `verifyArtifact` rather than re-deriving tree hashing.
//
// REGISTRY-DRIVEN, LIKE THE WIRE-CONFORMANCE SEAM REGISTRY
// (core/scripts/check-wire-conformance.mjs). Adding a lane is a new row in
// LANE_REGISTRY, not a new branch of logic: which repos its tree hash must
// cover, and which arbiter counters a passing receipt is expected to carry.
// L0/L1 are static/unit — no external system to disagree with, so no
// arbiters. L3 drives the real backend, and the backend's own served-read
// counters are the arbiter (see integration/dev-stack.sh's `servedReads`
// cross-check) — the same lesson as that script's big comment: "the shell's
// own PASS line" is not proof, "did the backend's independent counter move"
// is.

import { existsSync, mkdirSync, readdirSync } from "node:fs";
import { join } from "node:path";
import {
  REPO_PATHS,
  WORKSPACE_ROOT,
  worktreeStamp,
  verifyArtifact,
  readStampFile,
  writeStampFile,
  short,
} from "./provenance.mjs";

/** Bumped when the receipt shape changes in a way a consumer must notice. */
export const RECEIPTS_SCHEMA_VERSION = 1;

/**
 * The lane registry. Adding a lane means adding a row here — deliberately a
 * small, boring edit, mirroring WIRE_SEAMS in check-wire-conformance.mjs.
 *
 *   repos            which repos' tree hashes a receipt for this lane must
 *                    cover. verifyReceipt() rejects a receipt missing a stamp
 *                    for any declared repo, or whose stamp for that repo does
 *                    not match the CURRENT working tree.
 *   requiredArbiters independent counters a PASSING receipt must carry.
 *                    Empty for lanes with nothing external to cross-check
 *                    (L0 static, L1 hermetic unit); L2/L3 name the counters
 *                    that prove traffic actually flowed rather than a runner
 *                    merely exiting 0.
 */
export const LANE_REGISTRY = Object.freeze({
  L0: Object.freeze({
    id: "L0",
    name: "reflex",
    budgetMs: 1000,
    // BOTH repos: the import fence and contract-drift halves of L0 run in
    // `platform`, the wire-conformance and codegen halves in `core-foundation`.
    // A receipt keyed on only one of them would go on validating after the other
    // repo changed underneath it — a stale receipt that still looks fresh, which
    // is the precise thing tree-hash keying exists to prevent.
    repos: Object.freeze(["core-foundation", "platform"]),
    requiredArbiters: Object.freeze([]),
    description:
      "static only: import fence, contract drift, wire conformance, codegen drift.",
  }),
  L1: Object.freeze({
    id: "L1",
    name: "unit",
    budgetMs: 5000,
    repos: Object.freeze(["core-foundation"]),
    requiredArbiters: Object.freeze([]),
    description: "`pnpm verify` in core-foundation/core.",
  }),
  L2: Object.freeze({
    id: "L2",
    name: "hermetic integration",
    budgetMs: 25000,
    repos: Object.freeze(["core-foundation", "platform"]),
    requiredArbiters: Object.freeze([]),
    description:
      "`bun test` + `bun test integration/` in platform, plus the cross-side wire-agreement test.",
  }),
  L3: Object.freeze({
    id: "L3",
    name: "real integration",
    budgetMs: 90000,
    repos: Object.freeze(["core-foundation", "platform"]),
    // Named after integration/dev-stack.sh's own arbiter: the backend's
    // /qa/stats counters, cross-checked before/after driving the apps. A
    // shell-reported PASS with these absent or unchanged is exactly the
    // false-green shape dev-stack.sh's comments describe.
    requiredArbiters: Object.freeze(["servedRequests", "servedReads"]),
    description: "the full stack via integration/dev-stack.sh.",
  }),
});

export const LANE_IDS = Object.freeze(Object.keys(LANE_REGISTRY));

function receiptsDir(workspaceRoot = WORKSPACE_ROOT) {
  return join(workspaceRoot, ".omi", "receipts");
}

export function receiptPath(lane, { workspaceRoot = WORKSPACE_ROOT } = {}) {
  return join(receiptsDir(workspaceRoot), `${lane}.json`);
}

/**
 * Write a receipt for `lane`. Stamps every repo the lane's registry row
 * declares via `worktreeStamp()` — the tree hash IS the receipt's key.
 *
 * Refuses to write a "pass" receipt missing a required arbiter: a pass
 * receipt is a claim that the lane's independent counters moved, and a
 * receipt that skips recording them would let a caller launder a bare exit
 * code into what looks like cross-checked evidence.
 */
export function writeReceipt({
  lane,
  result,
  durationMs,
  arbiters = {},
  notes = "",
  command = "",
  workspaceRoot = WORKSPACE_ROOT,
  now = new Date(),
} = {}) {
  const row = LANE_REGISTRY[lane];
  if (!row) {
    throw new Error(
      `writeReceipt: unknown lane "${lane}". Known lanes: ${LANE_IDS.join(", ")}.`,
    );
  }
  if (result !== "pass" && result !== "fail") {
    throw new Error(
      `writeReceipt: result must be "pass" or "fail", got ${JSON.stringify(result)}.`,
    );
  }
  if (typeof durationMs !== "number" || !Number.isFinite(durationMs) || durationMs < 0) {
    throw new Error("writeReceipt: durationMs must be a non-negative finite number.");
  }
  const missingArbiters = row.requiredArbiters.filter((key) => !(key in arbiters));
  if (result === "pass" && missingArbiters.length > 0) {
    throw new Error(
      `writeReceipt: lane ${lane} requires arbiter counter(s) [${missingArbiters.join(", ")}] ` +
        `on a pass — pass them in \`arbiters\`, or write result: "fail" if the lane did not ` +
        `actually observe them.`,
    );
  }

  const stamps = {};
  for (const repo of row.repos) {
    const repoRoot = REPO_PATHS[repo];
    if (!repoRoot) {
      throw new Error(
        `writeReceipt: lane ${lane} declares repo "${repo}" which is not in provenance.REPO_PATHS.`,
      );
    }
    stamps[repo] = worktreeStamp({ repo, repoRoot, artifact: "worktree" });
  }

  const receipt = {
    schema: RECEIPTS_SCHEMA_VERSION,
    lane,
    result,
    timestamp: now.toISOString(),
    durationMs,
    stamps,
    arbiters,
    notes,
    command,
  };

  mkdirSync(receiptsDir(workspaceRoot), { recursive: true });
  writeStampFile(receiptPath(lane, { workspaceRoot }), receipt);
  return receipt;
}

/** Returns null rather than throwing: no receipt is a normal finding. */
export function readReceipt(lane, { workspaceRoot = WORKSPACE_ROOT } = {}) {
  return readStampFile(receiptPath(lane, { workspaceRoot }));
}

/** Every receipt currently on disk, for known lanes only. */
export function listReceipts({ workspaceRoot = WORKSPACE_ROOT } = {}) {
  const dir = receiptsDir(workspaceRoot);
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((f) => f.endsWith(".json"))
    .map((f) => f.slice(0, -".json".length))
    .filter((lane) => lane in LANE_REGISTRY)
    .map((lane) => ({ lane, receipt: readReceipt(lane, { workspaceRoot }) }))
    .filter((entry) => entry.receipt !== null);
}

/**
 * Is `lane`'s receipt valid evidence for the CURRENT working tree, right now?
 *
 * Returns `{ ok, reason, kind }`. `kind` is the machine-readable category —
 * check-lane-claims.mjs branches on it instead of parsing `reason` prose, so
 * the human-facing message can stay precise without becoming load-bearing
 * string content elsewhere.
 *
 *   "unknown-lane"  lane is not in LANE_REGISTRY
 *   "absent"        no receipt file for this lane
 *   "failed"        receipt exists but result !== "pass"
 *   "stale"         receipt exists, passed, but its tree hash for some
 *                   declared repo no longer matches the working tree
 *   "ok"            valid evidence for the tree as it stands right now
 */
export function verifyReceipt(lane, { workspaceRoot = WORKSPACE_ROOT } = {}) {
  const row = LANE_REGISTRY[lane];
  if (!row) {
    return {
      ok: false,
      kind: "unknown-lane",
      reason: `"${lane}" is not a known lane. Known lanes: ${LANE_IDS.join(", ")}.`,
    };
  }

  const receipt = readReceipt(lane, { workspaceRoot });
  if (!receipt) {
    return {
      ok: false,
      kind: "absent",
      reason:
        `no receipt for ${lane} (${row.name}) — ${receiptPath(lane, { workspaceRoot })} does not exist. ` +
        `The lane has not been run, or ran without calling writeReceipt().`,
    };
  }

  if (receipt.result !== "pass") {
    return {
      ok: false,
      kind: "failed",
      reason: `${lane}'s last receipt recorded result="${receipt.result}" at ${receipt.timestamp}.`,
    };
  }

  for (const repo of row.repos) {
    const stamp = receipt.stamps?.[repo];
    if (!stamp) {
      return {
        ok: false,
        kind: "stale",
        reason: `${lane}'s receipt has no stamp for repo "${repo}" (required by LANE_REGISTRY.${lane}.repos).`,
      };
    }
    // Recomputes the working-tree hash using the STAMP's own repo/roots
    // rather than a scope this function picks — the same discipline
    // provenance.mjs documents for `verifyArtifact`: two accurate
    // measurements of different questions is the original sin.
    const { agree, reason, worktree } = verifyArtifact(stamp);
    if (!agree) {
      return {
        ok: false,
        kind: "stale",
        reason:
          `${lane}'s receipt is stale for ${repo}: receipt tree ${short(stamp.treeHash)}, ` +
          `current tree ${short(worktree?.treeHash ?? stamp.treeHash)} — ${reason || "tree hash mismatch"}.`,
      };
    }
  }

  return { ok: true, kind: "ok", reason: "" };
}

// ── Claims parsing ──────────────────────────────────────────────────────────
// Lives here (not in check-lane-claims.mjs) so it is a plain, unit-testable
// function: the structured-trailer-only rule is an invariant of what counts
// as a "claim", not a detail of the CLI that happens to enforce it.
//
// WHY STRUCTURED-ONLY. platform/scripts/lint-import-graph.ts's corpus fence
// once matched the bare English word "corpora" in a comment and failed a
// green build over ordinary prose; the fix was to require a path shape, not
// a word. The lesson generalizes: a checker that fires on honest prose gets
// routed around, and once routed around it protects nothing — for anyone,
// not just the agent who first worked around it. So a lane claim exists only
// as an exact trailer line, matched at column 0. "We ran L2 and it passed",
// a file path containing "L1", or the word "Lanes" in a sentence are all
// prose and are never inspected.

const LANES_TRAILER = /^Lanes:\s*(\S.*)$/;
const OVERRIDE_TRAILER = /^Lane-Claim-Override:\s*(.*)$/;

/**
 * Extract the claimed lanes from a commit message. Only a line matching
 * `^Lanes:\s*(\S.*)$` counts — no other text in the message is inspected.
 * If more than one such line is present, the LAST one wins (ordinary git
 * trailer convention: later assignments override earlier ones, e.g. after
 * a `git commit --amend` that appended a corrected trailer).
 *
 * Returns the raw comma-separated tokens, trimmed and with blanks dropped —
 * NOT filtered against LANE_REGISTRY, so callers can distinguish "claimed
 * nothing" from "claimed something unknown".
 */
export function parseLaneClaims(message) {
  const lines = String(message ?? "").split(/\r?\n/);
  let matched = null;
  for (const line of lines) {
    const m = LANES_TRAILER.exec(line);
    if (m) matched = m[1];
  }
  if (matched === null) return [];
  return matched
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

/**
 * Extract the override trailer, if present. Mirrors the fence's
 * `// storage-provenance-ok(<reason>)` idiom: an escape hatch that is
 * accepted, reported loudly by the caller, and requires a non-empty reason.
 *
 * Returns `{ present, reason, valid }`:
 *   present  a `Lane-Claim-Override:` line exists (last one wins, as above)
 *   reason   its trimmed value ("" if none)
 *   valid    present AND reason is non-empty
 */
export function parseLaneClaimOverride(message) {
  const lines = String(message ?? "").split(/\r?\n/);
  let matched = null;
  for (const line of lines) {
    const m = OVERRIDE_TRAILER.exec(line);
    if (m) matched = m[1];
  }
  if (matched === null) return { present: false, reason: "", valid: false };
  const reason = matched.trim();
  return { present: true, reason, valid: reason.length > 0 };
}

// ── CLI ─────────────────────────────────────────────────────────────────────
// `node integration/lib/receipts.mjs <write|read|verify|list> [flags]`
// A thin manual-testing surface, not the enforcement path — that is
// check-lane-claims.mjs. See --help for flags.
import { fileURLToPath } from "node:url";

function printHelp() {
  process.stdout.write(
    [
      "node integration/lib/receipts.mjs <command> [flags]",
      "",
      "Commands:",
      '  write --lane <L0|L1|L2|L3> --result <pass|fail> [--duration-ms N]',
      "         [--arbiters '<json>'] [--notes <text>] [--command <text>]",
      "  read --lane <lane>",
      "  verify --lane <lane>",
      "  list",
      "  --help",
      "",
      "Writes/reads under <workspace>/.omi/receipts/<lane>.json.",
    ].join("\n") + "\n",
  );
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const argv = process.argv.slice(2);
  const flag = (name) => {
    const i = argv.indexOf(name);
    return i === -1 ? undefined : argv[i + 1];
  };
  const cmd = argv[0];

  if (cmd === undefined || cmd === "--help" || cmd === "-h") {
    printHelp();
    process.exit(0);
  } else if (cmd === "write") {
    const lane = flag("--lane");
    const result = flag("--result");
    const durationMs = Number(flag("--duration-ms") ?? "0");
    const arbitersRaw = flag("--arbiters");
    let arbiters = {};
    if (arbitersRaw) {
      try {
        arbiters = JSON.parse(arbitersRaw);
      } catch (err) {
        process.stderr.write(`--arbiters must be valid JSON: ${err.message}\n`);
        process.exit(2);
      }
    }
    try {
      const receipt = writeReceipt({
        lane,
        result,
        durationMs,
        arbiters,
        notes: flag("--notes") ?? "",
        command: flag("--command") ?? "",
      });
      process.stdout.write(`${JSON.stringify(receipt, null, 2)}\n`);
    } catch (err) {
      process.stderr.write(`${err.message}\n`);
      process.exit(1);
    }
  } else if (cmd === "read") {
    const lane = flag("--lane");
    const receipt = readReceipt(lane);
    process.stdout.write(`${JSON.stringify(receipt, null, 2)}\n`);
    if (receipt === null) process.exit(1);
  } else if (cmd === "verify") {
    const lane = flag("--lane");
    const outcome = verifyReceipt(lane);
    process.stdout.write(`${JSON.stringify(outcome, null, 2)}\n`);
    process.exit(outcome.ok ? 0 : 1);
  } else if (cmd === "list") {
    process.stdout.write(`${JSON.stringify(listReceipts(), null, 2)}\n`);
  } else {
    process.stderr.write(`unknown command "${cmd}". Try --help.\n`);
    process.exit(2);
  }
}
