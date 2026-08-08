import { describe, it, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  LANE_REGISTRY,
  writeReceipt,
  readReceipt,
  listReceipts,
  verifyReceipt,
  receiptPath,
  parseLaneClaims,
  parseLaneClaimOverride,
} from "./receipts.mjs";
import { checkLaneClaims } from "../check-lane-claims.mjs";

// Every test in this file uses its own scratch workspace root, passed
// explicitly via { workspaceRoot }. The receipt FILES are hermetic; the tree
// HASHES inside them are not (worktreeStamp() genuinely reads this checkout's
// git state via REPO_PATHS, which is the entire point — a receipt system that
// faked its own tree hash would prove nothing). Nothing here mutates the real
// repo; staleness is always simulated by hand-editing the receipt's stamp.
let workspaceRoot;
beforeEach(() => {
  workspaceRoot = mkdtempSync(join(tmpdir(), "omi-receipts-test-"));
});
afterEach(() => {
  rmSync(workspaceRoot, { recursive: true, force: true });
});

describe("writeReceipt / readReceipt round trip", () => {
  // red-proof: in writeReceipt(), stop putting `arbiters` on the written
  // object (delete the `arbiters,` line from the receipt literal) — the
  // round trip then silently drops data instead of returning what was written.
  it("returns on read exactly what was written, keyed by the current tree", () => {
    const inputArbiters = { customCounter: 7 };
    const written = writeReceipt({
      lane: "L1",
      result: "pass",
      durationMs: 1234,
      arbiters: inputArbiters,
      notes: "ran pnpm verify",
      command: "pnpm verify",
      workspaceRoot,
    });
    const read = readReceipt("L1", { workspaceRoot });

    assert.deepEqual(read, written);
    assert.equal(read.lane, "L1");
    assert.equal(read.result, "pass");
    assert.equal(read.durationMs, 1234);
    assert.equal(read.notes, "ran pnpm verify");
    // Checked against the ORIGINAL input, not just internal self-consistency
    // between `written` and `read` — a field dropped from the receipt object
    // before both of those are produced would otherwise go unnoticed.
    assert.deepEqual(read.arbiters, inputArbiters);
    assert.ok(read.stamps["core-foundation"], "L1 receipt must carry a core-foundation stamp");
    assert.ok(read.stamps["core-foundation"].treeHash, "stamp must carry a real tree hash");
    // L2 declares platform too; L1 must NOT, per LANE_REGISTRY.L1.repos.
    assert.equal(read.stamps.platform, undefined);
  });

  it("readReceipt returns null, not throw, when nothing was written", () => {
    assert.equal(readReceipt("L0", { workspaceRoot }), null);
  });

  it("listReceipts finds every written lane and ignores unknown-lane files", () => {
    writeReceipt({ lane: "L0", result: "pass", durationMs: 10, workspaceRoot });
    writeReceipt({ lane: "L1", result: "fail", durationMs: 20, workspaceRoot });
    // A stray file for a lane the registry doesn't know about — must not surface.
    writeFileSync(join(workspaceRoot, ".omi", "receipts", "bogus.json"), "{}\n");

    const listed = listReceipts({ workspaceRoot }).map((e) => e.lane).sort();
    assert.deepEqual(listed, ["L0", "L1"]);
  });
});

describe("verifyReceipt: staleness is keyed by tree hash", () => {
  // red-proof: in verifyReceipt(), replace the `if (!agree) { return {...} }`
  // branch's condition with `if (false)` (i.e. never report staleness) — a
  // hand-edited, obviously-wrong tree hash then still verifies as `ok: true`.
  it("a receipt whose stamp no longer matches the working tree is stale, not valid", () => {
    writeReceipt({ lane: "L0", result: "pass", durationMs: 5, workspaceRoot });

    // Simulate "edited after the receipt was written" WITHOUT touching the
    // real repo: hand-edit the receipt's own stamp, per the brief. A real
    // edit would change worktreeStamp()'s output the same way; forging the
    // stamp file is the deterministic way to produce that without depending
    // on this checkout's actual git state.
    const p = receiptPath("L0", { workspaceRoot });
    const receipt = JSON.parse(readFileSync(p, "utf8"));
    const real = receipt.stamps["core-foundation"].treeHash;
    const forged = (real.slice(0, -4) === "dead" ? "beef" : "dead") + real.slice(4);
    receipt.stamps["core-foundation"].treeHash = forged;
    writeFileSync(p, `${JSON.stringify(receipt, null, 2)}\n`);

    const outcome = verifyReceipt("L0", { workspaceRoot });
    assert.equal(outcome.ok, false);
    assert.equal(outcome.kind, "stale");
    // Both hashes named, short form — the brief's precision requirement.
    assert.match(outcome.reason, /receipt tree [0-9a-f]{8,}/);
    assert.match(outcome.reason, /current tree [0-9a-f]{8,}/);
    assert.doesNotMatch(outcome.reason, new RegExp(forged), "the reported receipt hash should be the short form, not the full forged hash verbatim");
  });

  it("a freshly written receipt for the untouched tree verifies ok", () => {
    writeReceipt({ lane: "L0", result: "pass", durationMs: 5, workspaceRoot });
    const outcome = verifyReceipt("L0", { workspaceRoot });
    assert.deepEqual(outcome, { ok: true, kind: "ok", reason: "" });
  });

  it("verifyReceipt distinguishes absent from unknown-lane", () => {
    const absent = verifyReceipt("L2", { workspaceRoot });
    assert.equal(absent.ok, false);
    assert.equal(absent.kind, "absent");

    const unknown = verifyReceipt("L9", { workspaceRoot });
    assert.equal(unknown.ok, false);
    assert.equal(unknown.kind, "unknown-lane");
    assert.match(unknown.reason, /L0.*L1.*L2.*L3|not a known lane/);
  });
});

describe("verifyReceipt: a failed run is never valid evidence", () => {
  // red-proof: in verifyReceipt(), delete the `if (receipt.result !== "pass")`
  // early-return block entirely — a receipt recording result: "fail" then
  // falls through to the tree-hash check and, since the tree is untouched,
  // verifies as `ok: true`.
  it("result: fail never validates, even against the exact current tree", () => {
    writeReceipt({ lane: "L1", result: "fail", durationMs: 999, notes: "tsc errors", workspaceRoot });
    const outcome = verifyReceipt("L1", { workspaceRoot });
    assert.equal(outcome.ok, false);
    assert.equal(outcome.kind, "failed");
    assert.match(outcome.reason, /result="fail"/);
  });
});

describe("writeReceipt: required arbiters are a registry-driven gate", () => {
  it("L3 refuses a pass receipt missing its required arbiter counters", () => {
    assert.throws(
      () => writeReceipt({ lane: "L3", result: "pass", durationMs: 90000, arbiters: {}, workspaceRoot }),
      /requires arbiter counter/,
    );
  });

  it("L3 accepts a fail receipt with no arbiters (nothing to cross-check when it never ran)", () => {
    const receipt = writeReceipt({ lane: "L3", result: "fail", durationMs: 500, arbiters: {}, workspaceRoot });
    assert.equal(receipt.result, "fail");
  });

  it("L0/L1 need no arbiters at all — the registry says so", () => {
    assert.deepEqual(LANE_REGISTRY.L0.requiredArbiters, []);
    assert.deepEqual(LANE_REGISTRY.L1.requiredArbiters, []);
    assert.ok(LANE_REGISTRY.L3.requiredArbiters.length > 0);
  });
});

describe("parseLaneClaims: structured trailer only, never prose", () => {
  // red-proof: in receipts.mjs, change `const LANES_TRAILER = /^Lanes:\s*(\S.*)$/`
  // to drop the `^` anchor (`/Lanes:\s*(\S.*)$/`) — a sentence that merely
  // CONTAINS "Lanes: ..." then registers as a real claim.
  it("a commit message that talks about lanes, but has no trailer, claims nothing", () => {
    const message = [
      "fix: stabilize the memory read path",
      "",
      "We ran L0, L1 and L2 tonight and everything came back green. Lanes are",
      "looking solid overall; see the runbook section on Lanes: how to read them.",
      "",
      "Filed as part of the reflex work.",
    ].join("\n");
    assert.deepEqual(parseLaneClaims(message), []);
  });

  it("an exact `Lanes:` trailer line is the only thing that claims anything", () => {
    const message = "fix: x\n\nSome body text.\n\nLanes: L0,L1,L2\n";
    assert.deepEqual(parseLaneClaims(message), ["L0", "L1", "L2"]);
  });

  it("tolerates whitespace and ignores a trailing blank claim", () => {
    assert.deepEqual(parseLaneClaims("Lanes:  L0 , L1 ,,L2 \n"), ["L0", "L1", "L2"]);
  });

  it("the last `Lanes:` line wins when more than one is present (amend convention)", () => {
    const message = "Lanes: L0\n\n...\n\nLanes: L0,L1\n";
    assert.deepEqual(parseLaneClaims(message), ["L0", "L1"]);
  });

  it("a file path or word containing L1/L2 in prose is not a claim", () => {
    const message = "fix: rename packages/L1-legacy to packages/L2-shim\n\nNo Lanes trailer here.\n";
    assert.deepEqual(parseLaneClaims(message), []);
  });
});

describe("the override hatch requires a non-empty reason", () => {
  // red-proof: in parseLaneClaimOverride(), change
  // `valid: reason.length > 0` to `valid: true` — an empty
  // `Lane-Claim-Override:` trailer (no reason at all) then reports as a valid
  // override, and checkLaneClaims below would silently bypass every failure.
  it("an override with no reason is present but invalid", () => {
    const outcome = parseLaneClaimOverride("fix: x\n\nLane-Claim-Override:\n");
    assert.equal(outcome.present, true);
    assert.equal(outcome.reason, "");
    assert.equal(outcome.valid, false);
  });

  it("an override with a reason is present and valid", () => {
    const outcome = parseLaneClaimOverride("fix: x\n\nLane-Claim-Override: L0 checker is down, see OMI-9999\n");
    assert.equal(outcome.present, true);
    assert.equal(outcome.reason, "L0 checker is down, see OMI-9999");
    assert.equal(outcome.valid, true);
  });

  it("no override trailer at all is simply absent, not invalid", () => {
    const outcome = parseLaneClaimOverride("fix: x\n\nno override here\n");
    assert.equal(outcome.present, false);
    assert.equal(outcome.valid, false);
  });
});

describe("checkLaneClaims: end to end against real receipts", () => {
  it("claims with no matching receipts fail, and each failure names a next action", () => {
    const message = "fix: x\n\nLanes: L0,L1\n";
    const result = checkLaneClaims(message, { workspaceRoot });
    assert.equal(result.ok, false);
    assert.equal(result.failures.length, 2);
    for (const f of result.failures) {
      assert.equal(f.kind, "absent");
      assert.ok(f.nextAction && f.nextAction.length > 0);
    }
  });

  it("claims backed by fresh, passing receipts succeed", () => {
    writeReceipt({ lane: "L0", result: "pass", durationMs: 5, workspaceRoot });
    const result = checkLaneClaims("fix: x\n\nLanes: L0\n", { workspaceRoot });
    assert.equal(result.ok, true);
    assert.deepEqual(result.failures, []);
  });

  it("a failing claim bypassed by a valid override still reports the underlying failure", () => {
    const message = "fix: x\n\nLanes: L1\n\nLane-Claim-Override: L1 runner is broken, tracked in OMI-4242\n";
    const result = checkLaneClaims(message, { workspaceRoot });
    assert.equal(result.ok, true);
    assert.equal(result.overridden, true);
    assert.equal(result.failures.length, 1);
    assert.equal(result.failures[0].lane, "L1");
    assert.equal(result.override.reason, "L1 runner is broken, tracked in OMI-4242");
  });

  it("an override with an empty reason does not bypass the failure", () => {
    const message = "fix: x\n\nLanes: L1\n\nLane-Claim-Override:\n";
    const result = checkLaneClaims(message, { workspaceRoot });
    assert.equal(result.ok, false);
    assert.ok(result.overrideError, "an empty-reason override must be reported as an error, not silently ignored");
  });

  it("prose mentioning lanes with no trailer claims nothing and always passes", () => {
    const message = "fix: x\n\nRan L0 L1 L2 by hand, all good.\n";
    const result = checkLaneClaims(message, { workspaceRoot });
    assert.equal(result.ok, true);
    assert.deepEqual(result.claims, []);
  });
});
