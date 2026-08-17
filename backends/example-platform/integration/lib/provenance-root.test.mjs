import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import test from "node:test";

const HERE = dirname(fileURLToPath(import.meta.url));
const PROVENANCE = join(HERE, "provenance.mjs");

function runPaths(overrides) {
  const env = { ...process.env };
  for (const [key, value] of Object.entries(overrides)) {
    if (value === undefined) delete env[key];
    else env[key] = value;
  }
  return spawnSync(process.execPath, [PROVENANCE, "--paths"], {
    encoding: "utf8",
    env,
  });
}

test("unset roots default to this git toplevel and agree", () => {
  const result = runPaths({ OMI_CORE_ROOT: undefined, OMI_PLATFORM_ROOT: undefined });
  assert.equal(result.status, 0, result.stderr);
  const parsed = JSON.parse(result.stdout);
  assert.equal(parsed["core-foundation"], parsed.platform);
  assert.equal(typeof parsed.platform, "string");
  assert.notEqual(parsed.platform, "");
});

test("RED-PROOF differing OMI_CORE_ROOT and OMI_PLATFORM_ROOT are refused", () => {
  const result = runPaths({
    OMI_CORE_ROOT: "/declared/core-repository",
    OMI_PLATFORM_ROOT: "/declared/platform-repository",
  });
  assert.notEqual(result.status, 0);
  const output = `${result.stdout}${result.stderr}`;
  assert.match(output, /OMI_CORE_ROOT and OMI_PLATFORM_ROOT must be the same path/);
  assert.match(output, /OMI_CORE_ROOT=\/declared\/core-repository/);
  assert.match(output, /OMI_PLATFORM_ROOT=\/declared\/platform-repository/);
});

test("one declared root is used for both names", () => {
  const result = runPaths({
    OMI_CORE_ROOT: "/declared/one-repo",
    OMI_PLATFORM_ROOT: undefined,
  });
  assert.equal(result.status, 0, result.stderr);
  const parsed = JSON.parse(result.stdout);
  assert.equal(parsed["core-foundation"], "/declared/one-repo");
  assert.equal(parsed.platform, "/declared/one-repo");
});
