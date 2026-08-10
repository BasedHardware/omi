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
// cover, and which independent arbiter evidence a passing receipt must carry.
// L0/L1 are static/unit — no external system to disagree with, so no
// arbiters. L3 drives the real service and joins its producer observations to
// exact rendered observations from both shells. The shell's own PASS line and
// the service's readiness line are inputs, never the final proof.

import { createHash, randomUUID } from "node:crypto";
import {
  existsSync,
  linkSync,
  mkdirSync,
  readdirSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { join } from "node:path";
import {
  REPO_PATHS,
  WORKSPACE_ROOT,
  worktreeStamp,
  verifyArtifact,
  readStampFile,
  short,
} from "./provenance.mjs";

/** Bumped when the receipt shape changes in a way a consumer must notice. */
export const RECEIPTS_SCHEMA_VERSION = 3;

// ── WHY SCHEMA 2: ONE SLOT PER LANE WAS A FALSE-MEASUREMENT GENERATOR ────────
//
// Schema 1 wrote every receipt to `<workspace>/.omi/receipts/<lane>.json` — one
// slot per lane id, in the workspace root, shared by every lane worktree on the
// machine. Six lanes ran against it concurrently all night. Last writer won,
// silently.
//
// MEASURED, twice, during the wave-3 run (see
// `data/run-2026-08-09/blocked/CLIENT-lane-receipts-share-one-slot-per-lane-id.md`):
//
//   - A lane ran L1, saw PASS, and read back a receipt stamped
//     `branch: "lane/read"` — a sibling's tree, in the file it had just written.
//   - A lane ran L0, L1 and L2 in one command, all three printed PASS, and the
//     L0/L1 receipts named the SHARED checkout at a two-day-old commit while L2's
//     named the lane's own worktree.
//
// THE SHAPE OF THE DEFECT, which is why it belongs in a comment and not just a
// changelog: **stdout was truthful and only the durable artifact was wrong.**
// The lane genuinely ran, genuinely passed, and genuinely printed so. The
// corruption is therefore invisible to whoever ran the lane and visible only to
// whoever reads the file afterwards — the exact inversion of a useful failure,
// sitting inside the verification system itself. And §4 leans on this file
// directly: *"a commit claiming a lane must carry a receipt matching the tree it
// lands as, so nobody can integrate on a stale measurement."* Under concurrency
// that sentence was not true.
//
// THE FIX HAS TWO HALVES AND NEITHER IS SUFFICIENT ALONE.
//
//  1. **The path carries the measurement key.** A receipt's whole purpose is to
//     be tree-hash-keyed, and `<lane>.json` threw that away at the last step.
//     The filename is now `<lane>-<key>.json`, where the key digests the lane
//     plus, for every repo the lane declares, that repo's NAME, ABSOLUTE ROOT
//     and TREE HASH. Two lanes measuring two trees write two files; a reader
//     computes the key from the tree it is standing in and can only ever open a
//     receipt written for that tree. Cross-lane read-back stops being something
//     to detect and becomes something that cannot be addressed.
//
//  2. **The receipt is self-describing enough to catch its own mismatch.** Each
//     stamp now records the `repoRoot` it measured, and the receipt records its
//     own `key` and `path`. `verifyReceiptObject()` will judge a receipt handed
//     to it from ANYWHERE — read off disk by hand, pasted into a report, quoted
//     in a commit message — against the tree the reader actually cares about.
//     Half 1 protects the lookup; half 2 protects everything that does not go
//     through the lookup, which is how this defect reached a human in the first
//     place.
//
// SCHEMA 3: THE KEY IS A HISTORY, NOT A SLOT. Schema 2 separated different
// lane+tree measurements, but still wrote every rerun of the SAME measurement
// to `<lane>-<key>.json`. A later pass could therefore erase an earlier fail.
// Schema 3 uses `<lane>-<key>/<append-id>.json`: one immutable file per run.
// There is no mutable `current` pointer; readers derive current from the newest
// append id. A schema-2 flat file remains readable as the oldest history entry
// so this upgrade does not invalidate existing current-receipt callers.
//
// ACCEPTED LIMIT, named and dated (2026-08-09): receipts are never pruned. One
// file per RUN accumulates for the life of the workspace, a few KB each.
// Count-based pruning was considered and rejected — the directory is shared,
// so "keep the newest N" deletes valid evidence and reintroduces the evidence
// destruction this change exists to remove. `make lane-sweep` or removing the
// local `.omi/receipts` directory is the explicit disposal path.

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
    // Receipt schema stays immutable; the L3 arbiter payload becomes exact.
    // One aggregate number cannot stand in for a shell/domain coordinate.
    requiredArbiters: Object.freeze(["runId", "evidenceMatrix"]),
    description: "the full stack via integration/dev-stack.sh.",
  }),
});

export const LANE_IDS = Object.freeze(Object.keys(LANE_REGISTRY));

function receiptsDir(workspaceRoot = WORKSPACE_ROOT) {
  return join(workspaceRoot, ".omi", "receipts");
}

/**
 * Stamp every repo a lane declares, recording the ROOT each stamp measured.
 *
 * `worktreeStamp` records repo, branch, commit and tree hash but not the path
 * it read them from, and the path is exactly what distinguishes two lanes: two
 * worktrees of one repo have the same `repo` name and different roots. Without
 * it a receipt cannot say which of six trees it is about, which is the question
 * a reader is actually asking.
 */
function stampDeclaredRepos(row) {
  const stamps = {};
  for (const repo of row.repos) {
    const repoRoot = REPO_PATHS[repo];
    if (!repoRoot) {
      throw new Error(
        `receipts: lane ${row.id} declares repo "${repo}" which is not in provenance.REPO_PATHS.`,
      );
    }
    stamps[repo] = { ...worktreeStamp({ repo, repoRoot, artifact: "worktree" }), repoRoot };
  }
  return stamps;
}

/**
 * The measurement key: what makes two receipts the same measurement.
 *
 * Digests the lane id plus, per declared repo, `<repo>\0<root>\0<treeHash>`,
 * sorted so the key does not depend on object insertion order.
 *
 * ROOT IS IN THE KEY DELIBERATELY, even though two identical trees produce
 * identical hashes and are, for the lane's purposes, the same source. Keeping
 * the root makes the key answer "which tree did this measure", not merely "what
 * did it contain" — and attribution is the property that failed. A lane worktree
 * whose content happens to equal the shared checkout's still gets its own
 * receipt, and the cost of that conservatism is one extra file.
 *
 * Truncated to 16 hex characters: this is a filename disambiguator among a
 * handful of concurrent trees on one machine, not a security boundary. 64 bits
 * is far past collision for that population, and a short name stays readable in
 * the runner's output, which people do read.
 */
export function receiptKey(lane, stamps) {
  const parts = Object.keys(stamps)
    .sort()
    .map((repo) => {
      const stamp = stamps[repo] ?? {};
      // NUL as the field separator, written as an ESCAPE rather than as a
      // literal byte. The separator must be a character that cannot occur in a
      // repo name, an absolute path or a hex hash, or two different tuples
      // could join to one string and collide. The first draft of this line
      // carried real NUL bytes in the source, which made `grep` treat this
      // whole file as binary and silently skip it — a control character you
      // cannot see is a tooling hazard even when the runtime behaviour is
      // identical.
      return [repo, stamp.repoRoot ?? "", stamp.treeHash ?? ""].join("\u0000");
    });
  return createHash("sha256").update([lane, ...parts].join("")).digest("hex").slice(0, 16);
}

function receiptHistoryDir(lane, key, workspaceRoot = WORKSPACE_ROOT) {
  return join(receiptsDir(workspaceRoot), `${lane}-${key}`);
}

function schema2ReceiptPath(lane, key, workspaceRoot = WORKSPACE_ROOT) {
  return join(receiptsDir(workspaceRoot), `${lane}-${key}.json`);
}

function historyEntryPaths(lane, key, workspaceRoot = WORKSPACE_ROOT) {
  const dir = receiptHistoryDir(lane, key, workspaceRoot);
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((file) => file.endsWith(".json"))
    .sort()
    .map((file) => join(dir, file));
}

/**
 * Where the CURRENT receipt for `lane` measuring the current tree lives.
 *
 * Takes no key argument on purpose. A caller that could pass its own key could
 * pass someone else's, which is the door this change closes — so the key is
 * always derived from the tree the caller is standing in. `stamps` exists only
 * so `writeReceipt` can reuse the stamps it already took rather than shelling
 * out to git a second time. Before any receipt exists, returns the history
 * directory (which also makes an absent-receipt diagnostic useful).
 */
export function receiptPath(lane, { workspaceRoot = WORKSPACE_ROOT, stamps } = {}) {
  const row = LANE_REGISTRY[lane];
  if (!row) {
    throw new Error(`receiptPath: unknown lane "${lane}". Known lanes: ${LANE_IDS.join(", ")}.`);
  }
  const resolved = stamps ?? stampDeclaredRepos(row);
  const key = receiptKey(lane, resolved);
  const entries = historyEntryPaths(lane, key, workspaceRoot);
  if (entries.length > 0) return entries.at(-1);
  const schema2Path = schema2ReceiptPath(lane, key, workspaceRoot);
  if (existsSync(schema2Path)) return schema2Path;
  return receiptHistoryDir(lane, key, workspaceRoot);
}

/** Every immutable run for the current lane+tree, oldest first. */
export function readReceiptHistory(lane, { workspaceRoot = WORKSPACE_ROOT } = {}) {
  const row = LANE_REGISTRY[lane];
  if (!row) {
    throw new Error(
      `readReceiptHistory: unknown lane "${lane}". Known lanes: ${LANE_IDS.join(", ")}.`,
    );
  }
  const stamps = stampDeclaredRepos(row);
  const key = receiptKey(lane, stamps);
  const receipts = [];

  // A schema-2 receipt is the pre-upgrade current value. Preserve it as the
  // oldest known run; all schema-3 writes go only to immutable history files.
  const schema2Receipt = readStampFile(schema2ReceiptPath(lane, key, workspaceRoot));
  if (schema2Receipt) receipts.push(schema2Receipt);
  for (const path of historyEntryPaths(lane, key, workspaceRoot)) {
    const receipt = readStampFile(path);
    if (receipt) receipts.push(receipt);
  }
  return receipts;
}

/** Has this lane+tree ever recorded anything other than a pass? */
export function hasNonPassReceipt(lane, { workspaceRoot = WORKSPACE_ROOT } = {}) {
  return readReceiptHistory(lane, { workspaceRoot }).some(
    (receipt) => receipt.result !== "pass",
  );
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
  // PRESENCE OF A KEY IS NOT PRESENCE OF A COUNTER.
  //
  // This filter used to be `!(key in arbiters)`, and `"totalRequests" in
  // { totalRequests: null }` is TRUE — so a receipt recording
  // A null arbiter once satisfied a guard whose own comment says it exists to
  // stop a caller laundering a bare exit code into cross-checked evidence.
  //
  // Reachable, not hypothetical. `lanes.mjs`'s L3 arbiter read is
  // `report.backend?.status?.served?.totalRequests ?? null` over a JSON report from a
  // shared default directory, so a report that is absent, foreign, or merely
  // shaped differently yields `null` for every counter — and the receipt
  // recorded a PASS carrying nulls where the two independent measurements
  // belong. AUDIT found the read side (a lane can ingest another lane's or a
  // fabricated report); this is the half that lives in this file, and it is
  // the half that decides whether such a report can become a green receipt.
  //
  // `null` and `undefined` are refused. The L3-specific validator below then
  // requires a complete 14-coordinate producer/consumer matrix.
  const unobservedArbiters = row.requiredArbiters.filter(
    (key) => !(key in arbiters) || arbiters[key] === null || arbiters[key] === undefined,
  );
  if (result === "pass" && unobservedArbiters.length > 0) {
    throw new Error(
      `writeReceipt: lane ${lane} requires OBSERVED arbiter counter(s) [${unobservedArbiters.join(", ")}] ` +
        `on a pass — each must be present AND non-null. A null counter means the lane did not ` +
        `read one, which is not a pass: supply the real values, or write result: "fail".`,
    );
  }
  if (result === "pass" && lane === "L3") {
    const matrix = arbiters.evidenceMatrix;
    const rows = matrix?.rows;
    const coordinates = Array.isArray(rows)
      ? new Set(rows.map((entry) => `${entry?.shell}/${entry?.domain}`))
      : new Set();
    if (
      matrix?.schema !== "omi.shell-domain-matrix.v1"
      || matrix?.result !== "pass"
      || matrix?.rowCount !== 14
      || !Array.isArray(rows)
      || rows.length !== 14
      || coordinates.size !== 14
      || rows.some((entry) => entry?.consumer === null || typeof entry?.consumer !== "object"
        || entry?.producer === null || typeof entry?.producer !== "object")
    ) {
      throw new Error(
        "writeReceipt: lane L3 requires the passing exact 14-row producer/consumer evidenceMatrix; "
        + "ios:null or an aggregate counter is not a coordinate.",
      );
    }
  }

  const stamps = stampDeclaredRepos(row);
  const key = receiptKey(lane, stamps);
  // `hrtime` is system-monotonic across the short-lived lane processes used by
  // the runner. Padding makes lexicographic order equal append-start order;
  // PID plus UUID makes the filename unique even for two processes racing in
  // the same nanosecond. The exclusive link below is the final collision fence.
  const appendId = [
    process.hrtime.bigint().toString().padStart(20, "0"),
    String(process.pid).padStart(10, "0"),
    randomUUID(),
  ].join("-");
  const historyDir = receiptHistoryDir(lane, key, workspaceRoot);
  const path = join(historyDir, `${appendId}.json`);

  const receipt = {
    schema: RECEIPTS_SCHEMA_VERSION,
    lane,
    result,
    timestamp: now.toISOString(),
    durationMs,
    stamps,
    // The receipt names its own identity and location. A receipt quoted out of
    // its directory — pasted into a report, echoed in a commit message — still
    // says which measurement it is, which is what lets a reader check it rather
    // than trust it.
    key,
    appendId,
    path,
    arbiters,
    notes,
    command,
  };

  mkdirSync(historyDir, { recursive: true });
  const temporaryPath = join(historyDir, `.${appendId}.tmp`);
  writeFileSync(temporaryPath, `${JSON.stringify(receipt, null, 2)}\n`, { flag: "wx" });
  try {
    // Link publishes a fully written entry atomically and refuses EEXIST. It
    // cannot replace an earlier run, unlike rename/writeFile on a shared slot.
    linkSync(temporaryPath, path);
  } finally {
    unlinkSync(temporaryPath);
  }
  return receipt;
}

/**
 * The receipt for `lane` measuring the tree the caller is standing in, or null.
 *
 * There is deliberately NO fallback to schema 1's `<lane>.json`. A fallback
 * would re-open the shared slot on the read side and hand back exactly the
 * ambiguous artifact this change removes — and it would do so on the path that
 * looks like it succeeded. A legacy file is reported by `listReceipts()` as
 * `legacy: true` and is never returned as evidence.
 */
export function readReceipt(lane, { workspaceRoot = WORKSPACE_ROOT } = {}) {
  return readReceiptHistory(lane, { workspaceRoot }).at(-1) ?? null;
}

/**
 * Every receipt file on disk, for known lanes, with its attribution judged.
 *
 * Returns `{ lane, key, legacy, file, receipt, attribution }`. `attribution` is
 * `verifyReceiptObject`'s verdict for the CURRENT tree — so a listing shows at a
 * glance which receipts describe the tree you are in and which describe a
 * sibling's, instead of presenting six files as if they were interchangeable.
 * That indistinguishability is what let a two-day-old stamp be quoted as a
 * lane's own result.
 */
export function listReceipts({ workspaceRoot = WORKSPACE_ROOT } = {}) {
  const dir = receiptsDir(workspaceRoot);
  if (!existsSync(dir)) return [];
  const out = [];
  const entries = readdirSync(dir, { withFileTypes: true }).sort((a, b) =>
    a.name.localeCompare(b.name),
  );
  for (const entry of entries) {
    const file = entry.name;
    const base = file.endsWith(".json") ? file.slice(0, -".json".length) : file;
    const dash = base.indexOf("-");
    const lane = dash === -1 ? base : base.slice(0, dash);
    if (!(lane in LANE_REGISTRY)) continue;
    let paths = [];
    if (entry.isDirectory()) {
      paths = readdirSync(join(dir, file))
        .filter((name) => name.endsWith(".json"))
        .sort()
        .map((name) => join(dir, file, name));
    } else if (file.endsWith(".json")) {
      paths = [join(dir, file)];
    }
    for (const path of paths) {
      const receipt = readStampFile(path);
      if (receipt === null) continue;
      out.push({
        lane,
        key: receipt.key ?? (dash === -1 ? null : base.slice(dash + 1)),
        legacy: dash === -1,
        file: path,
        receipt,
        attribution: verifyReceiptObject(lane, receipt),
      });
    }
  }
  return out;
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
        `The lane has not been run against THIS tree, or ran without calling writeReceipt(). ` +
        `A sibling lane's receipt for a different tree is a different file and is never read here.`,
    };
  }

  return verifyReceiptObject(lane, receipt);
}

/**
 * Judge a receipt OBJECT — from wherever it came — against the tree the reader
 * is standing in.
 *
 * `verifyReceipt` reads by key, so the receipt it gets is already the right
 * measurement and this mostly re-confirms it. That redundancy is the point.
 * The defect that produced this function reached a person through a path with
 * no lookup at all: a receipt read straight off disk with `JSON.parse`,
 * carrying another lane's branch and commit, quoted as this lane's result. Any
 * reader that obtains a receipt by any means can call this and be told whether
 * it describes their tree, which is the property the schema-1 file could not
 * offer at all.
 *
 * Extra `kind` over `verifyReceipt`'s set:
 *
 *   "misattributed"  the receipt is internally fine but measured a DIFFERENT
 *                    root than the reader's — a sibling lane's worktree, or the
 *                    shared checkout. Distinguished from "stale" on purpose:
 *                    stale means *your* tree moved and the answer is to rerun;
 *                    misattributed means this was never about your tree and
 *                    rerunning changes nothing about the file you were reading.
 */
export function verifyReceiptObject(lane, receipt) {
  const row = LANE_REGISTRY[lane];
  if (!row) {
    return {
      ok: false,
      kind: "unknown-lane",
      reason: `"${lane}" is not a known lane. Known lanes: ${LANE_IDS.join(", ")}.`,
    };
  }
  if (receipt === null || typeof receipt !== "object") {
    return { ok: false, kind: "absent", reason: `no receipt object for ${lane}.` };
  }
  if (receipt.lane !== undefined && receipt.lane !== lane) {
    return {
      ok: false,
      kind: "misattributed",
      reason: `this receipt is ${receipt.lane}'s, not ${lane}'s.`,
    };
  }

  if (receipt.result !== "pass") {
    return {
      ok: false,
      kind: "failed",
      reason: `${lane}'s receipt recorded result="${receipt.result}" at ${receipt.timestamp}.`,
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
    // ATTRIBUTION BEFORE STALENESS, and the order matters. A receipt that
    // measured a sibling's worktree is not stale — its own tree may be
    // perfectly current — so checking staleness first would either accept it
    // (when the two trees happen to match) or blame the reader's tree for a
    // file that was never about it. Root equality is the question "is this
    // mine", and it is asked first.
    const readerRoot = REPO_PATHS[repo];
    if (stamp.repoRoot !== undefined && readerRoot !== undefined && stamp.repoRoot !== readerRoot) {
      return {
        ok: false,
        kind: "misattributed",
        reason:
          `${lane}'s receipt measured ${repo} at ${stamp.repoRoot} (${stamp.branch} @ ${short(stamp.commit)}), ` +
          `but this reader's ${repo} is ${readerRoot}. It is a different tree's receipt, not a stale one.`,
      };
    }
    if (stamp.repoRoot === undefined) {
      // Schema 1. It cannot say which tree it measured, so it cannot be
      // attributed — and an unattributable receipt is not weaker evidence, it
      // is no evidence. Reported as its own kind rather than silently
      // tree-hash-checked, because a schema-1 file that happens to match is
      // still a file six lanes were overwriting.
      return {
        ok: false,
        kind: "misattributed",
        reason:
          `${lane}'s receipt predates schema ${RECEIPTS_SCHEMA_VERSION} and records no repoRoot for ${repo}, ` +
          `so it cannot be attributed to a tree. Rerun ${lane}.`,
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
// `node integration/lib/receipts.mjs <write|read|history|has-non-pass|verify|list> [flags]`
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
      "  history --lane <lane>",
      "  has-non-pass --lane <lane>",
      "  verify --lane <lane>",
      "  list",
      "  --help",
      "",
      "Writes/reads immutable history under <workspace>/.omi/receipts/<lane>-<key>/.",
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
  } else if (cmd === "history") {
    const lane = flag("--lane");
    process.stdout.write(`${JSON.stringify(readReceiptHistory(lane), null, 2)}\n`);
  } else if (cmd === "has-non-pass") {
    const lane = flag("--lane");
    process.stdout.write(`${JSON.stringify({ lane, hasNonPass: hasNonPassReceipt(lane) }, null, 2)}\n`);
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
