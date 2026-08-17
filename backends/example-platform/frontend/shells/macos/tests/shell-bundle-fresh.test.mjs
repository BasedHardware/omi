import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { bundledSurfaceDir, freshness, hashTree, shellStampPath, shortHash } from "../scripts/shell-bundle-fresh.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function scratch() {
  return mkdtempSync(join(tmpdir(), "omi-shell-fresh-"));
}

function writeTree(dir, files) {
  for (const [rel, body] of Object.entries(files)) {
    const path = join(dir, rel);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, body);
  }
}

test("hashTree is content-addressed: same bytes agree, one-byte or extra-file change does not", () => {
  const a = scratch();
  const b = scratch();
  try {
    writeTree(a, { "index.html": "<html>ok</html>", "assets/app.js": "console.log(1)\n" });
    writeTree(b, { "index.html": "<html>ok</html>", "assets/app.js": "console.log(1)\n" });
    assert.equal(hashTree(a), hashTree(b));

    writeFileSync(join(b, "index.html"), "<html>OK</html>");
    assert.notEqual(hashTree(a), hashTree(b), "one-byte change must not match");

    writeFileSync(join(b, "index.html"), "<html>ok</html>");
    writeFileSync(join(b, "extra.txt"), "nope");
    assert.notEqual(hashTree(a), hashTree(b), "extra file must not match");
  } finally {
    rmSync(a, { recursive: true, force: true });
    rmSync(b, { recursive: true, force: true });
  }
});

test("hashTree does not consult mtimes: rewrite identical bytes still matches", () => {
  const dir = scratch();
  try {
    writeTree(dir, { "index.html": "same" });
    const first = hashTree(dir);
    writeFileSync(join(dir, "index.html"), "same");
    assert.equal(hashTree(dir), first);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

function fakeVerify(agree, reason = "") {
  return () => ({ agree, reason });
}

test("freshness refuses when the app, stamp, or bundled surface is missing", () => {
  const dir = scratch();
  try {
    const app = join(dir, "omi-on-fresh.app");
    const dist = join(dir, "dist");
    writeTree(dist, { "index.html": "d" });
    const readStampFile = () => null;
    const verifyArtifact = fakeVerify(false, "no stamp — the artifact was built before stamping existed, or not built at all");

    assert.equal(freshness({ app, dist, readStampFile, verifyArtifact }).fresh, false);

    mkdirSync(app, { recursive: true });
    const missingStamp = freshness({ app, dist, readStampFile, verifyArtifact });
    assert.equal(missingStamp.fresh, false);
    assert.match(missingStamp.reason, /no stamp|rebuild/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("freshness refuses an unavailable or disagreeing macos-app stamp even when surfaces match", () => {
  const dir = scratch();
  try {
    const app = join(dir, "omi-on-fresh.app");
    const dist = join(dir, "dist");
    writeTree(dist, { "index.html": "surface" });
    writeTree(join(app, "Contents/Resources/surface"), { "index.html": "surface" });
    writeFileSync(shellStampPath(app), JSON.stringify({ unavailable: "node unavailable at build time" }));

    const unavailable = freshness({
      app,
      dist,
      readStampFile: () => ({ unavailable: "node unavailable at build time" }),
      verifyArtifact: fakeVerify(false, "artifact was built without provenance (node unavailable at build time)"),
    });
    assert.equal(unavailable.fresh, false);
    assert.match(unavailable.reason, /without provenance|rebuild/);

    const stale = freshness({
      app,
      dist,
      readStampFile: () => ({ treeHash: "a".repeat(40) }),
      verifyArtifact: fakeVerify(
        false,
        "built from tree aaaaaaaaaaaa, working tree is bbbbbbbbbbbb — rebuild it",
      ),
    });
    assert.equal(stale.fresh, false);
    assert.match(stale.reason, /working tree is bbbbbbbbbbbb/);
    assert.equal(hashTree(dist), hashTree(bundledSurfaceDir(app)), "surfaces matching must not override a stale Swift stamp");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("freshness refuses when macos-app stamp agrees but bundled surfaces do not match dist", () => {
  // red-proof: a Swift-only hash would return fresh here. The surfaces copy
  // is an input that lands in the bundle; changing it must rebuild.
  const dir = scratch();
  try {
    const app = join(dir, "omi-on-fresh.app");
    const dist = join(dir, "dist");
    writeTree(dist, { "index.html": "NEW-DIST-MARKER" });
    writeTree(join(app, "Contents/Resources/surface"), { "index.html": "OLD-BUNDLED" });
    const stamp = { treeHash: "c".repeat(40), artifact: "macos-app" };
    const result = freshness({
      app,
      dist,
      readStampFile: () => stamp,
      verifyArtifact: fakeVerify(true),
    });
    assert.equal(result.fresh, false);
    assert.match(result.reason, /bundled surfaces/);
    assert.match(result.reason, /working dist/);
    assert.match(result.reason, /rebuild it/);
    assert.notEqual(hashTree(dist), hashTree(bundledSurfaceDir(app)));
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("freshness skips only on exact stamp agreement AND exact surfaces content hash", () => {
  const dir = scratch();
  try {
    const app = join(dir, "omi-on-fresh.app");
    const dist = join(dir, "dist");
    writeTree(dist, { "index.html": "<html>ok</html>", "assets/x.js": "1" });
    writeTree(join(app, "Contents/Resources/surface"), { "index.html": "<html>ok</html>", "assets/x.js": "1" });
    const stamp = { treeHash: "d".repeat(40), artifact: "macos-app" };
    const result = freshness({
      app,
      dist,
      readStampFile: () => stamp,
      verifyArtifact: fakeVerify(true),
    });
    assert.equal(result.fresh, true);
    assert.match(result.reason, new RegExp(`macos-app tree ${shortHash(stamp.treeHash)} matches`));
    assert.match(result.reason, /surfaces sha256=/);
    assert.match(result.reason, /matches bundled copy/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("run-shell.sh skips build-shell.sh only after an exact freshness match; build-shell.sh itself never skips", async () => {
  const run = readFileSync(join(root, "scripts/run-shell.sh"), "utf8");
  const build = readFileSync(join(root, "scripts/build-shell.sh"), "utf8");
  assert.match(run, /shell-bundle-fresh\.mjs/);
  assert.match(run, /"\$here\/scripts\/build-shell\.sh"/);
  const freshIdx = run.indexOf("shell-bundle-fresh.mjs");
  const buildIdx = run.indexOf('"$here/scripts/build-shell.sh"');
  assert.ok(freshIdx !== -1 && buildIdx !== -1 && freshIdx < buildIdx);
  assert.match(run, /if \[\[ -x "\$executable" \]\] && node/);
  assert.doesNotMatch(build, /shell-bundle-fresh/);
  assert.doesNotMatch(build, /^cached:/m);
  // red-proof: deleting the freshness check and restoring a bare
  // `"$here/scripts/build-shell.sh"` makes freshIdx > buildIdx (or -1) and
  // reddens the ordered-index assertion. Putting the skip inside
  // build-shell.sh reddens the doesNotMatch on that file — verification
  // lanes that call build-shell.sh must keep compiling.
});
