// LIFECYCLE: permanent

import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { test } from "node:test";

test("launcher logs retain diagnostics but remove credentials and every base URL", () => {
  const scratch = mkdtempSync(join(tmpdir(), "omi-sanitize-log-"));
  try {
    const input = join(scratch, "raw.log");
    const output = join(scratch, "safe.log");
    writeFileSync(input, "launch http://127.0.0.1:4851/path token-marker Authorization: Bearer another-secret\nkept diagnostic\n");
    const cli = new URL("./sanitize-log.mjs", import.meta.url).pathname;
    const result = spawnSync(process.execPath, [cli, "--in", input, "--out", output, "--redact", "token-marker"], { encoding: "utf8" });
    assert.equal(result.status, 0, result.stderr);
    const safe = readFileSync(output, "utf8");
    assert.match(safe, /kept diagnostic/);
    assert.doesNotMatch(safe, /127\.0\.0\.1|token-marker|another-secret/);
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});

test("service output is sanitized before persistence using the independent readiness record", () => {
  const scratch = mkdtempSync(join(tmpdir(), "omi-stream-sanitize-log-"));
  try {
    const token = "stream-secret-token";
    const readiness = join(scratch, "readiness.json");
    const output = join(scratch, "service.log");
    const readyOut = join(scratch, "sanitizer-ready");
    writeFileSync(readiness, `${JSON.stringify({ devToken: token, baseUrl: "http://127.0.0.1:4851" })}\n`);
    const cli = new URL("./sanitize-log.mjs", import.meta.url).pathname;
    const result = spawnSync(process.execPath, [
      cli, "--stream", "--out", output, "--readiness", readiness, "--ready-out", readyOut,
    ], {
      encoding: "utf8",
      input: `service http://127.0.0.1:4851 token=${token}\nAuthorization: Bearer ${token}\nkept diagnostic\n`,
    });
    assert.equal(result.status, 0, result.stderr);
    assert.equal(existsSync(readyOut), true);
    assert.equal(statSync(output).mode & 0o777, 0o600);
    const safe = readFileSync(output, "utf8");
    assert.match(safe, /kept diagnostic/);
    assert.doesNotMatch(safe, /127\.0\.0\.1|stream-secret-token/);
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});

test("service output fails closed when no readiness identity exists", () => {
  const scratch = mkdtempSync(join(tmpdir(), "omi-stream-sanitize-fail-"));
  try {
    const output = join(scratch, "service.log");
    const cli = new URL("./sanitize-log.mjs", import.meta.url).pathname;
    const result = spawnSync(process.execPath, [
      cli, "--stream", "--out", output,
      "--readiness", join(scratch, "absent.json"), "--ready-out", join(scratch, "never-ready"),
    ], { encoding: "utf8", input: "raw-unproven-secret diagnostics\n" });
    assert.equal(result.status, 0, result.stderr);
    const safe = readFileSync(output, "utf8");
    assert.match(safe, /diagnostics withheld/);
    assert.doesNotMatch(safe, /raw-unproven-secret/);
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});
