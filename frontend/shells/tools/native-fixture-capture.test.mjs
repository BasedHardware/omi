import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const producer = path.join(root, "shells/tools/capture-native-fixture.mjs");
const coreSha = spawnSync("git", ["-C", root, "rev-parse", "HEAD"], { encoding: "utf8" }).stdout.trim();
const platformSha = "1".repeat(40);

function manifest(overrides = {}) {
  return {
    schema: "omi.polish.matrix-coordinate/v1", kind: "screenshot", domain: "memories", shell: "macos",
    state: "ready", theme: "light", width: "regular", accessibility: "none", run_id: "native-fixture-test",
    capture_class: "native_fixture", source_tier: "native_shell", source_shas: { core: coreSha, platform: platformSha },
    viewport: { width: 960, height: 671, scale: 2 }, ...overrides,
  };
}

test("native fixture producer rejects browser previews and mismatched provenance before launch", () => {
  const scratch = mkdtempSync(path.join(tmpdir(), "omi-native-fixture-producer-"));
  try {
    const browser = path.join(scratch, "browser.json");
    writeFileSync(browser, JSON.stringify(manifest({ capture_class: "core_browser_preview" })));
    const browserRun = spawnSync(process.execPath, [producer, "--manifest", browser], { encoding: "utf8" });
    assert.notEqual(browserRun.status, 0);
    assert.match(browserRun.stderr, /capture_class must be native_fixture/);
    const mismatch = path.join(scratch, "mismatch.json");
    writeFileSync(mismatch, JSON.stringify(manifest({ source_shas: { core: "2".repeat(40), platform: platformSha } })));
    const output = path.join(scratch, "should-not-exist.png");
    const mismatchRun = spawnSync(process.execPath, [producer, "--manifest", mismatch, "--output", output], { encoding: "utf8" });
    assert.notEqual(mismatchRun.status, 0);
    assert.match(mismatchRun.stderr, /does not match current core HEAD/);
    assert.equal(existsSync(output), false);
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});

test("native fixture producer source keeps backend and browser-preview claims out of capture contract", () => {
  const source = readFileSync(producer, "utf8");
  assert.match(source, /capture_class !== \"native_fixture\"/);
  assert.doesNotMatch(source, /OMI_API_TOKEN/);
  assert.match(source, /const query = new URLSearchParams/);
  assert.match(source, /source_tier/);
  assert.match(source, /WKWebView\.takeSnapshot/);
  assert.match(source, /xcrun simctl io screenshot/);
  assert.match(source, /allowedEnvironmentKeys/);
  assert.match(source, /PUB_CACHE/);
  assert.match(source, /const timeoutSeconds = 300/);
  assert.match(source, /timeout: timeoutSeconds \* 1000/);
  assert.match(source, /timeout_seconds: timeoutSeconds/);
  assert.doesNotMatch(source, /const env = \{ \.\.\.process\.env \}/);
});
