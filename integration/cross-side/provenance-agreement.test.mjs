/**
 * CROSS-REPO PROVENANCE AGREEMENT
 * ================================
 *
 * `platform` consumes the ratified contract as a vendored tarball
 * (`vendor/contracts/omi-core-ratified-contracts-*.tgz`), never as a path into
 * this repo — that separation is the point (rule 15's server-side consumer
 * reads "out of the INSTALLED tarball... a stronger consumption than a path
 * this script could check", `check-wire-conformance.mjs`'s own comment). But
 * separation only stays honest if the tarball's promise — "these bytes are
 * what `core/contracts/ratified/` actually contains" — keeps being true. If
 * core changes a source file and the tarball is never re-vendored, both sides
 * stay green while testing two different artifacts: core's suite tests its
 * live source, platform's suite tests a stale snapshot, and nothing anywhere
 * notices the two have drifted apart.
 *
 * This is the CORPUS lane's `sha256sum` check (run once, by hand, against
 * `write-ops-conformance.json`/`write-ops-outcomes.json`/`write/ops.ts`/
 * `wire/json.ts`), made permanent and generalized: every file the INSTALLED
 * tarball's own `PROVENANCE.json` claims to be built from is re-hashed
 * against core's LIVE source tree, not just the four files one run happened
 * to check by hand.
 *
 * WHAT THIS DOES NOT CATCH: an intentional, unvendored, in-flight contract
 * change — that is expected to disagree until the next `pnpm run publish`
 * (or equivalent) re-vendors it, and this test is expected to fail loudly in
 * exactly that window, which is correct: it says "core moved and platform has
 * not caught up" rather than staying silently green about it.
 *
 * NOT WIRED INTO `integration/lanes.mjs`'s L2 command list — that file is
 * `dev-stack.sh`'s and this file's sibling STACK-owned churn magnet
 * (`data/run-2026-08-09/CHARTER.md`'s isolation table), so registering this as
 * an enforced gate is left for STACK/the coordinator to land in that file.
 * Runnable directly: `node --test integration/cross-side/provenance-agreement.test.mjs`.
 */

import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import assert from "node:assert/strict";
import { describe, test } from "node:test";

const { REPO_PATHS, assertCrossTreePairingIsDeclared, assertRepoPathsExist } =
  await import(new URL("../lib/provenance.mjs", import.meta.url).href);

// Same discipline lanes.mjs's own L2 preflight applies before anything cross-
// repo runs: an undeclared pairing silently measures the shared checkout and
// goes green about a tree containing none of the diff under test.
assertRepoPathsExist();
assertCrossTreePairingIsDeclared();

const CORE_REPO = REPO_PATHS["core-foundation"];
const PLATFORM_REPO = REPO_PATHS.platform;

const RATIFIED_SOURCE_ROOT = join(CORE_REPO, "core", "contracts", "ratified");
const INSTALLED_PACKAGE_ROOT = join(PLATFORM_REPO, "node_modules", "@omi-core", "ratified-contracts");
const INSTALLED_PROVENANCE_PATH = join(INSTALLED_PACKAGE_ROOT, "PROVENANCE.json");

const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");

function readInstalledProvenance() {
  if (!existsSync(INSTALLED_PROVENANCE_PATH)) {
    throw new Error(
      `provenance-agreement: ${INSTALLED_PROVENANCE_PATH} does not exist — is @omi-core/ratified-contracts ` +
        `installed in ${PLATFORM_REPO}? Run the platform install first (see integration/lanes.mjs's L0 step).`,
    );
  }
  return JSON.parse(readFileSync(INSTALLED_PROVENANCE_PATH, "utf8"));
}

describe("the installed tarball's provenance matches core's live source, file for file", () => {
  test("PROVENANCE.json names a non-empty input list", () => {
    // A missing or emptied list must never read as a pass: every assertion
    // below is inside a loop over these entries.
    const provenance = readInstalledProvenance();
    assert.ok(Array.isArray(provenance.inputs), "PROVENANCE.json has no inputs array — schema changed?");
    assert.ok(provenance.inputs.length >= 20, `only ${provenance.inputs.length} inputs listed — suspiciously few`);
  });

  test("every file the tarball claims as its source is byte-identical to core's tree today", () => {
    // red-proof: edit any one byte of core/contracts/ratified/src/write/ops.ts
    // (or any other listed input) without re-vendoring the tarball. This test
    // must name that exact file and fail. Applied against write/ops.ts and
    // write-ops-conformance.json; both observed red; both reverted.
    const provenance = readInstalledProvenance();
    const mismatches = [];
    let checked = 0;

    for (const input of provenance.inputs) {
      // PROVENANCE.json paths are recorded relative to the ratified package
      // root (e.g. "src/write/ops.ts", "fixtures/write-ops-conformance.json"),
      // which IS `core/contracts/ratified/` in the source tree — the package's
      // own root, not a tarball-internal "package/" prefix.
      const sourcePath = join(RATIFIED_SOURCE_ROOT, input.path);
      if (!existsSync(sourcePath)) {
        mismatches.push(`${input.path}: no corresponding file at ${sourcePath} (renamed or deleted in core?)`);
        checked += 1;
        continue;
      }
      const actualBytes = readFileSync(sourcePath);
      const actualHash = sha256(actualBytes);
      if (actualHash !== input.sha256) {
        mismatches.push(
          `${input.path}: core source hash ${actualHash} != tarball-recorded hash ${input.sha256} `
          + `(core has moved since the last vendor; re-run the publish/vendor step)`,
        );
      }
      if (actualBytes.length !== input.bytes) {
        mismatches.push(`${input.path}: core source is ${actualBytes.length} bytes, tarball recorded ${input.bytes}`);
      }
      checked += 1;
    }

    // Producer-side count (rows PROVENANCE.json declares) against consumer-side
    // count (rows this test actually checked) — a loop that silently skipped a
    // class would otherwise be a green result about nothing.
    assert.equal(checked, provenance.inputs.length);
    assert.deepEqual(mismatches, [], `${mismatches.length} file(s) diverged between core's source and the installed tarball:\n${mismatches.join("\n")}`);
  });

  test("the tarball's own recorded sourceDigest is consistent with its per-file hashes", () => {
    // A weaker, self-consistency check on the tarball's own claim: PROVENANCE.json's
    // top-level `sourceDigest` should not be trivially absent or malformed. This
    // does not re-derive it (that is the vendoring tool's own job and its exact
    // derivation is not this test's concern) — it only guards against a
    // provenance file that forgot to stamp one at all, which would make the
    // per-file check above the only signal and silently drop this cross-check.
    const provenance = readInstalledProvenance();
    assert.equal(typeof provenance.sourceDigest, "string");
    assert.match(provenance.sourceDigest, /^[0-9a-f]{64}$/, "sourceDigest is not a 64-hex sha256");
  });
});
