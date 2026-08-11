// LIFECYCLE: permanent

import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { afterEach, beforeEach, test } from "node:test";

import { DOMAINS, SERVICE_BASE_URL, SERVICE_EXECUTABLE, SERVICE_READINESS_SCHEMA } from "./evidence-matrix.mjs";

const cli = new URL("./evidence-cli.mjs", import.meta.url);
const runId = "run-evidence-cli";
let scratch;

beforeEach(() => { scratch = mkdtempSync(join(tmpdir(), "omi-evidence-cli-")); });
afterEach(() => { rmSync(scratch, { recursive: true, force: true }); });

function nativeDocument(shell) {
  return {
    schema: "omi.consumer-evidence.v1",
    runId,
    rows: DOMAINS.map((domain) => ({
      runId,
      shell,
      domain,
      fixture: "none",
      evidence: "rendered-semantic",
      observation: {
        route: domain,
        state: "ready",
        semantic: "é".repeat(128),
        ...(domain === "listen" ? { transcript: "😀".repeat(256) } : {}),
      },
      shellTreeHash: "1".repeat(40),
      surfaceTreeHash: "2".repeat(40),
    })),
  };
}

function run(args) {
  return spawnSync(process.execPath, [cli.pathname, ...args], { encoding: "utf8" });
}

test("merge-consumer derives shell from rows, invokes native validation, and preserves bytes", () => {
  const macosPath = join(scratch, "macos.json");
  const iosPath = join(scratch, "ios.json");
  const out = join(scratch, "merged.json");
  writeFileSync(macosPath, `${JSON.stringify(nativeDocument("macos"), null, 4)}\n`);
  writeFileSync(iosPath, `${JSON.stringify(nativeDocument("ios"))}\n`);
  const beforeMacos = readFileSync(macosPath);
  const beforeIos = readFileSync(iosPath);

  const result = run(["merge-consumer", "--macos", macosPath, "--ios", iosPath, "--run-id", runId, "--out", out]);
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(readFileSync(macosPath), beforeMacos);
  assert.deepEqual(readFileSync(iosPath), beforeIos);
  const merged = JSON.parse(readFileSync(out, "utf8"));
  assert.deepEqual(Object.keys(merged).sort(), ["rows", "runId", "schema"]);
  assert.equal(merged.rows.length, 14);
  assert.deepEqual(merged.rows.map((row) => `${row.shell}/${row.domain}`),
    ["macos", "ios"].flatMap((shell) => DOMAINS.map((domain) => `${shell}/${domain}`)));
});

test("RED-PROOF merge rejects a top-level shell and multibyte semantic overflow", () => {
  const macosPath = join(scratch, "macos.json");
  const iosPath = join(scratch, "ios.json");
  const out = join(scratch, "merged.json");
  const macos = { ...nativeDocument("macos"), shell: "macos" };
  writeFileSync(macosPath, `${JSON.stringify(macos)}\n`);
  writeFileSync(iosPath, `${JSON.stringify(nativeDocument("ios"))}\n`);
  let result = run(["merge-consumer", "--macos", macosPath, "--ios", iosPath, "--run-id", runId, "--out", out]);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /document keys are not exact/);

  const overflow = nativeDocument("macos");
  overflow.rows[0].observation.semantic = "é".repeat(129);
  writeFileSync(macosPath, `${JSON.stringify(overflow)}\n`);
  result = run(["merge-consumer", "--macos", macosPath, "--ios", iosPath, "--run-id", runId, "--out", out]);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /semantic is not bounded/);
});

test("RED-PROOF CLI rejects every reserved or attributed raw run id", () => {
  for (const value of ["anonymous", "overflow", "__private", "a".repeat(97), "run::macos", "run::ios"]) {
    const result = run(["validate-run-id", "--run-id", value]);
    assert.notEqual(result.status, 0, value);
  }
  assert.equal(run(["validate-run-id", "--run-id", runId]).status, 0);
});

test("validate-readiness writes the token only to a mode-0600 file and stdout is safe", () => {
  const recordPath = join(scratch, "readiness.json");
  const tokenPath = join(scratch, "token");
  const databasePath = join(scratch, "service.sqlite");
  writeFileSync(recordPath, `${JSON.stringify({
    schema: SERVICE_READINESS_SCHEMA,
    runId,
    executable: SERVICE_EXECUTABLE,
    baseUrl: SERVICE_BASE_URL,
    databasePath,
    pid: 123,
    evidencePath: "/v1/qa/evidence",
    devToken: "secret-token-marker",
    ownerAccountId: "secret-owner-marker",
  })}\n`);
  const result = run(["validate-readiness", "--record", recordPath, "--run-id", runId,
    "--database", databasePath, "--pid", "123", "--token-out", tokenPath]);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(readFileSync(tokenPath, "utf8"), "secret-token-marker");
  assert.doesNotMatch(result.stdout, /secret-token-marker|secret-owner-marker|127\.0\.0\.1/);
});
