/**
 * TWO LANES, ONE RECEIPTS DIRECTORY — the defect that produced schema 2.
 *
 * `receipts.test.mjs` covers the receipt system's behaviour for ONE lane. It
 * cannot see this defect, and it did not: every one of its assertions stayed
 * green all night while the live workspace was handing lanes each other's
 * receipts. A single-writer test literally cannot express "the other writer
 * clobbered me", which is why this file exists beside it rather than inside it.
 *
 * WHAT IS CONSTRUCTED HERE, NOT REASONED ABOUT. Two real git repositories with
 * genuinely different contents stand in for two lane worktrees, and each lane
 * is a REAL CHILD PROCESS with its own `OMI_PLATFORM_ROOT` — because that is
 * what a lane is. Both processes share ONE receipts directory, as six lanes
 * share one workspace root, and they are started together and awaited together
 * so "concurrently" describes what ran rather than being a word in a comment.
 *
 * The first draft of this file loaded the module twice in-process with a
 * cache-busting query string instead, and it FAILED — correctly, and
 * informatively. `receipts.mjs` imports `provenance.mjs` without that query, so
 * one shared `provenance.mjs` resolved `REPO_PATHS` once, at first load, and
 * both "lanes" measured one tree. The precondition assertion caught it rather
 * than the test passing for the wrong reason, which is the only reason that
 * draft is worth mentioning: a concurrency test that quietly degrades into a
 * single-writer test is exactly the false green this file exists to prevent.
 *
 * The measured claim: after both lanes write, each reads back ITS OWN receipt,
 * and neither can obtain the other's through the read path — including when the
 * two lanes' trees are BYTE-IDENTICAL, which is the ordinary case (two
 * worktrees, same trunk commit, clean) and the only one in which the key's root
 * component does any work.
 *
 * RED-PROOFS, applied against real source, observed red, reverted:
 *
 *   - Revert `receiptPath()` to schema 1's shape, `<lane>.json`. Both lanes
 *     address one file, the second write erases the first, and four of these
 *     tests fail — the exact artifact that was quoted as a lane's own result
 *     during the wave-3 run.
 *   - Drop `repoRoot` from the stamps: same four fail, because a receipt that
 *     cannot say which tree it measured cannot be attributed to one.
 *   - Neutralise the root check, the schema-1 check, or the lane-id check in
 *     `verifyReceiptObject`: one test each, by name.
 *   - Drop `repoRoot` from the KEY (leaving it on the stamp): only the
 *     identical-trees test below fails. It was added FOR that mutation —
 *     without it the clause was unproven and, by §5, did not count. That is
 *     recorded here rather than quietly fixed, because "the red-proof that
 *     stayed green" is the finding, not the patch.
 */

import { describe, it, before, after } from "node:test";
import assert from "node:assert/strict";
import { execFile, execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync, readdirSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const HERE = dirname(fileURLToPath(import.meta.url));
const RECEIPTS_MODULE = join(HERE, "receipts.mjs");

/** A real repo, because worktreeStamp() runs git and a fake would prove nothing. */
function makeRepo(root, contents) {
  mkdirSync(join(root, "apps"), { recursive: true });
  const git = (args) =>
    execFileSync("git", args, { cwd: root, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] });
  git(["init", "--quiet", "--initial-branch", "main"]);
  git(["config", "user.email", "lane@example.test"]);
  git(["config", "user.name", "Lane"]);
  writeFileSync(join(root, "apps", "marker.txt"), contents);
  git(["add", "-A"]);
  git(["commit", "--quiet", "-m", "seed"]);
  return root;
}

/**
 * The lane driver: one short-lived process that imports the REAL receipts
 * module and performs one operation. Written to disk once and reused, so the
 * thing under test is the shipped module rather than a re-typed copy of it.
 */
const DRIVER = `
import { readFileSync } from "node:fs";
const mod = await import(process.env.OMI_RECEIPTS_MODULE);
const req = JSON.parse(readFileSync(process.env.OMI_DRIVER_REQUEST, "utf8"));
const { op, lane, workspaceRoot } = req;
let out;
if (op === "write") {
  out = mod.writeReceipt({ lane, result: "pass", durationMs: req.durationMs, notes: req.notes, workspaceRoot });
} else if (op === "read") {
  out = mod.readReceipt(lane, { workspaceRoot });
} else if (op === "history") {
  out = mod.readReceiptHistory(lane, { workspaceRoot });
} else if (op === "verify") {
  out = mod.verifyReceipt(lane, { workspaceRoot });
} else if (op === "verifyObject") {
  out = mod.verifyReceiptObject(lane, req.receipt);
} else if (op === "list") {
  out = mod.listReceipts({ workspaceRoot });
} else if (op === "schema") {
  out = { schema: mod.RECEIPTS_SCHEMA_VERSION };
} else {
  throw new Error("unknown op " + op);
}
process.stdout.write(JSON.stringify(out ?? null));
`;

let scratch;
let workspaceRoot;
let driverPath;
const lanes = {};

/** Run one operation AS a lane: its own process, its own OMI_PLATFORM_ROOT. */
async function asLane(tag, request) {
  const requestPath = join(scratch, `req-${tag}-${Math.random().toString(36).slice(2)}.json`);
  writeFileSync(requestPath, JSON.stringify({ workspaceRoot, ...request }));
  const { stdout } = await execFileAsync(process.execPath, [driverPath], {
    env: {
      ...process.env,
      OMI_PLATFORM_ROOT: lanes[tag],
      OMI_RECEIPTS_MODULE: RECEIPTS_MODULE,
      OMI_DRIVER_REQUEST: requestPath,
    },
    encoding: "utf8",
  });
  return JSON.parse(stdout);
}

/** Both lanes, started together and awaited together. */
const bothWrite = (notesA, notesB, durationA = 100, durationB = 200) =>
  Promise.all([
    asLane("a", { op: "write", lane: "L2", durationMs: durationA, notes: notesA }),
    asLane("b", { op: "write", lane: "L2", durationMs: durationB, notes: notesB }),
  ]);

before(() => {
  scratch = mkdtempSync(join(tmpdir(), "omi-receipts-concurrency-"));
  workspaceRoot = join(scratch, "workspace");
  mkdirSync(workspaceRoot, { recursive: true });
  driverPath = join(scratch, "lane-driver.mjs");
  writeFileSync(driverPath, DRIVER);
  lanes.a = makeRepo(join(scratch, "lane-a-platform"), "lane A content\n");
  lanes.b = makeRepo(join(scratch, "lane-b-platform"), "lane B content — deliberately different\n");
  // Lane C is byte-identical to lane A at a DIFFERENT path. Two worktrees of
  // one repo sitting on the same commit with clean trees is the ordinary case,
  // not a contrived one, and it is the only case in which the root component
  // of the key does any work at all.
  lanes.c = makeRepo(join(scratch, "lane-c-platform"), "lane A content\n");
});

after(() => {
  rmSync(scratch, { recursive: true, force: true });
});

const receiptsDir = () => join(workspaceRoot, ".omi", "receipts");
const clearReceipts = () => rmSync(receiptsDir(), { recursive: true, force: true });

describe("two lanes writing receipts concurrently", () => {
  it("two appends racing on the SAME lane+tree both survive", async () => {
    clearReceipts();
    const [first, second] = await Promise.all([
      asLane("a", { op: "write", lane: "L2", durationMs: 31, notes: "same-key A" }),
      asLane("a", { op: "write", lane: "L2", durationMs: 32, notes: "same-key B" }),
    ]);

    assert.equal(first.key, second.key, "this test must race two writers on the same key");
    assert.notEqual(
      first.path,
      second.path,
      "each append must publish a distinct immutable file",
    );
    const history = await asLane("a", { op: "history", lane: "L2" });
    assert.equal(
      history.length,
      2,
      `both same-key appends must survive: ${JSON.stringify(history)}`,
    );
    assert.deepEqual(
      history.map((receipt) => receipt.notes).sort(),
      ["same-key A", "same-key B"],
    );
  });

  it("gives each lane a distinct file, and neither can read back the other's", async () => {
    clearReceipts();
    // Preconditions, asserted rather than assumed. If either became false this
    // test would pass for a reason with nothing to do with the fix — which is
    // how the in-process draft failed, and it is worth keeping the guard.
    assert.notEqual(lanes.a, lanes.b, "the two lanes must be different trees");

    const [writtenA, writtenB] = await bothWrite("lane A", "lane B");

    assert.notEqual(
      writtenA.stamps.platform.treeHash,
      writtenB.stamps.platform.treeHash,
      "the two lanes must measure genuinely different trees for this test to mean anything",
    );
    assert.notEqual(writtenA.key, writtenB.key, "different measurements must have different keys");
    assert.notEqual(writtenA.path, writtenB.path, "and therefore different files");

    // BOTH survive. Under schema 1 exactly one file existed at this point.
    const files = readdirSync(receiptsDir());
    assert.equal(files.length, 2, `expected two receipt files, found ${JSON.stringify(files)}`);

    // THE ASSERTION THIS FILE EXISTS FOR: each lane reads back its own.
    const [readA, readB] = await Promise.all([
      asLane("a", { op: "read", lane: "L2" }),
      asLane("b", { op: "read", lane: "L2" }),
    ]);
    assert.equal(readA.notes, "lane A", "lane A must not read lane B's receipt");
    assert.equal(readB.notes, "lane B", "lane B must not read lane A's receipt");
    assert.equal(readA.stamps.platform.repoRoot, lanes.a);
    assert.equal(readB.stamps.platform.repoRoot, lanes.b);
    assert.equal(readA.durationMs, 100);
    assert.equal(readB.durationMs, 200);
  });

  it("each lane's own claim check passes, and the sibling's receipt is refused by name", async () => {
    clearReceipts();
    await bothWrite("A", "B");

    // Each lane's verdict for itself is ok — the evidence survived the sibling.
    const [verdictA, verdictB] = await Promise.all([
      asLane("a", { op: "verify", lane: "L2" }),
      asLane("b", { op: "verify", lane: "L2" }),
    ]);
    assert.equal(verdictA.ok, true, verdictA.reason);
    assert.equal(verdictB.ok, true, verdictB.reason);

    // And handed the SIBLING's receipt object directly — the path by which this
    // defect actually reached a person, since a file read with JSON.parse
    // bypasses every lookup — lane A must refuse it, naming attribution rather
    // than staleness. Lane B's tree is perfectly current; it is simply not
    // lane A's, and "rerun because you edited something" would be a false
    // diagnosis.
    const siblingReceipt = await asLane("b", { op: "read", lane: "L2" });
    const crossVerdict = await asLane("a", { op: "verifyObject", lane: "L2", receipt: siblingReceipt });
    assert.equal(crossVerdict.ok, false);
    assert.equal(crossVerdict.kind, "misattributed", crossVerdict.reason);
    assert.match(crossVerdict.reason, /different tree's receipt, not a stale one/);
  });

  it("a schema-1 receipt is unattributable, not silently accepted", async () => {
    // The live workspace is full of these. One that happens to match the
    // current tree hash is still a file six lanes were overwriting, so it is
    // refused by kind rather than accepted by luck.
    const stamp = (repo, branch, roots) => ({
      schema: 1, repo, artifact: "worktree", branch,
      commit: "0".repeat(40), treeHash: "1".repeat(40), roots,
    });
    const legacy = {
      schema: 1,
      lane: "L2",
      result: "pass",
      timestamp: new Date().toISOString(),
      durationMs: 1,
      // Schema 1 stamps carried no repoRoot anywhere. That absence IS the defect.
      stamps: {
        "core-foundation": stamp("core-foundation", "lane/read", ["core"]),
        platform: stamp("platform", "main", ["apps"]),
      },
      arbiters: {},
    };
    const verdict = await asLane("a", { op: "verifyObject", lane: "L2", receipt: legacy });
    assert.equal(verdict.ok, false);
    assert.equal(verdict.kind, "misattributed", verdict.reason);
    assert.match(verdict.reason, /records no repoRoot/);
  });

  it("a receipt for another lane id is refused even when the trees match", async () => {
    clearReceipts();
    const [writtenA] = await bothWrite("A", "B");
    const verdict = await asLane("a", { op: "verifyObject", lane: "L1", receipt: writtenA });
    assert.equal(verdict.ok, false);
    assert.equal(verdict.kind, "misattributed", verdict.reason);
    assert.match(verdict.reason, /is L2's, not L1's/);
  });

  it("listReceipts labels which files describe the reader's tree", async () => {
    clearReceipts();
    await bothWrite("A", "B");
    // A legacy file dropped in by hand, as the live workspace has.
    mkdirSync(receiptsDir(), { recursive: true });
    writeFileSync(
      join(receiptsDir(), "L1.json"),
      JSON.stringify({ schema: 1, lane: "L1", result: "pass", timestamp: "x", durationMs: 1, stamps: {} }),
    );

    const listed = await asLane("a", { op: "list" });
    const mine = listed.filter((entry) => entry.attribution.ok);
    assert.equal(mine.length, 1, `exactly one listed receipt describes lane A's tree: ${JSON.stringify(listed.map((e) => e.file))}`);
    assert.equal(mine[0].receipt.notes, "A");
    assert.equal(mine[0].legacy, false);

    const legacyEntry = listed.find((entry) => entry.legacy);
    assert.ok(legacyEntry, "the schema-1 file is still listed — invisible is worse than labelled");
    assert.equal(legacyEntry.attribution.ok, false);
    assert.equal(legacyEntry.key, null);

    // Every listed file carries a verdict; none is presented as interchangeable
    // with the others, which is the indistinguishability the defect rode in on.
    for (const entry of listed) {
      assert.equal(typeof entry.attribution.ok, "boolean");
      assert.ok(typeof entry.file === "string" && entry.file.length > 0);
    }
  });

  it("two lanes with IDENTICAL trees at different roots still get their own receipts", async () => {
    clearReceipts();
    // The case the tree hash alone cannot separate. Lane A and lane C have the
    // same content, so the same tree hash — under a content-only key they share
    // one file and the second write erases the first, which is the original
    // defect surviving in the one configuration lanes are most likely to be in:
    // two worktrees, same trunk commit, clean.
    const [writtenA, writtenC] = await Promise.all([
      asLane("a", { op: "write", lane: "L2", durationMs: 11, notes: "lane A" }),
      asLane("c", { op: "write", lane: "L2", durationMs: 22, notes: "lane C" }),
    ]);
    assert.equal(
      writtenA.stamps.platform.treeHash,
      writtenC.stamps.platform.treeHash,
      "this test is only meaningful while the two trees are byte-identical",
    );
    assert.notEqual(writtenA.stamps.platform.repoRoot, writtenC.stamps.platform.repoRoot);

    assert.notEqual(writtenA.key, writtenC.key, "identical content at different roots is a different measurement");
    assert.equal(readdirSync(receiptsDir()).length, 2, "neither lane's receipt was erased by the other");

    const [readA, readC] = await Promise.all([
      asLane("a", { op: "read", lane: "L2" }),
      asLane("c", { op: "read", lane: "L2" }),
    ]);
    assert.equal(readA.notes, "lane A");
    assert.equal(readC.notes, "lane C");
  });

  it("the receipt names its own identity, so a quoted receipt can still be checked", async () => {
    clearReceipts();
    const written = await asLane("a", { op: "write", lane: "L2", durationMs: 5, notes: "solo" });
    // The three facts a reader needs when a receipt arrives detached from its
    // directory — which measurement, which file, which trees.
    assert.match(written.key, /^[0-9a-f]{16}$/);
    assert.ok(written.path.includes(`L2-${written.key}/`));
    assert.ok(written.path.endsWith(`${written.appendId}.json`));
    for (const repo of ["core-foundation", "platform"]) {
      assert.ok(written.stamps[repo].repoRoot, `${repo} stamp must record the root it measured`);
      assert.ok(written.stamps[repo].branch, `${repo} stamp must record the branch it measured`);
      assert.ok(written.stamps[repo].commit, `${repo} stamp must record the commit it measured`);
    }
    // And the file on disk says the same thing as the returned object.
    const onDisk = JSON.parse(readFileSync(written.path, "utf8"));
    assert.equal(onDisk.key, written.key);
    assert.equal(onDisk.path, written.path);
    const { schema } = await asLane("a", { op: "schema" });
    assert.equal(onDisk.schema, schema);
    assert.equal(schema, 3, "schema 3 is the append-only history shape");
  });
});
