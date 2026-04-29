/**
 * Regression tests for the destructive-bash gate regex.
 *
 * Run with Node's built-in test runner (Node >= 20):
 *   cd src-tauri/sidecar/pi-agent
 *   node --test ./extensions/nooto-permissions/index.test.js
 *
 * DUPLICATION NOTE: DESTRUCTIVE_RE is defined in both index.ts and
 * destructive-patterns.js.  When you update the regex in index.ts you MUST
 * update destructive-patterns.js to match, otherwise this test will silently
 * become stale.  The canonical source of truth is index.ts; this file is
 * the regression harness.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { DESTRUCTIVE_RE } from "./destructive-patterns.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function matches(cmd) {
  return DESTRUCTIVE_RE.test(cmd);
}

// ---------------------------------------------------------------------------
// Must match — destructive commands that must be blocked
// ---------------------------------------------------------------------------

describe("DESTRUCTIVE_RE — must match (blocked)", () => {
  it("blocks rm -rf /tmp/foo", () => {
    assert.ok(matches("rm -rf /tmp/foo"), "expected match");
  });

  it("blocks rm -fr /tmp/foo", () => {
    assert.ok(matches("rm -fr /tmp/foo"), "expected match");
  });

  it("blocks rm -rf . (unsafe relative delete)", () => {
    assert.ok(matches("rm -rf ."), "expected match");
  });

  it("blocks rm -rf ~ (home dir)", () => {
    assert.ok(matches("rm -rf ~"), "expected match");
  });

  it("blocks git push --force", () => {
    assert.ok(matches("git push --force"), "expected match");
  });

  it("blocks git push -f origin main", () => {
    assert.ok(matches("git push -f origin main"), "expected match");
  });

  it("blocks git push origin main --force", () => {
    assert.ok(matches("git push origin main --force"), "expected match");
  });

  it("blocks git push --force-with-lease", () => {
    assert.ok(matches("git push --force-with-lease"), "expected match");
  });

  it("blocks git reset --hard HEAD~1", () => {
    assert.ok(matches("git reset --hard HEAD~1"), "expected match");
  });

  it("blocks dd if=/dev/zero of=/dev/sda", () => {
    assert.ok(matches("dd if=/dev/zero of=/dev/sda"), "expected match");
  });

  it("blocks fork bomb :(){:|:&};:", () => {
    assert.ok(matches(":(){:|:&};:"), "expected match");
  });

  it("blocks redirect to /etc/passwd", () => {
    assert.ok(matches("echo evil > /etc/passwd"), "expected match");
  });

  it("blocks mkfs.ext4", () => {
    assert.ok(matches("mkfs.ext4 /dev/sdb"), "expected match");
  });
});

// ---------------------------------------------------------------------------
// Must NOT match — safe commands that must be allowed
// ---------------------------------------------------------------------------

describe("DESTRUCTIVE_RE — must NOT match (allowed)", () => {
  it("allows ls -la", () => {
    assert.ok(!matches("ls -la"), "unexpected match");
  });

  it("allows git push origin main (no force flags)", () => {
    assert.ok(!matches("git push origin main"), "unexpected match");
  });

  it("allows git reset (no --hard)", () => {
    assert.ok(!matches("git reset"), "unexpected match");
  });

  it("allows echo hello > /tmp/out.txt (redirect inside /tmp is safe)", () => {
    assert.ok(!matches("echo hello > /tmp/out.txt"), "unexpected match");
  });

  it("allows cat README.md", () => {
    assert.ok(!matches("cat README.md"), "unexpected match");
  });

  it("allows rm -r build/ (no -f flag)", () => {
    // -r without -f is not covered by the pattern; user can delete their own build dir.
    assert.ok(!matches("rm -r build/"), "unexpected match");
  });

  it("allows npm run build", () => {
    assert.ok(!matches("npm run build"), "unexpected match");
  });
});
