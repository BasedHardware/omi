// LIFECYCLE: permanent

import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
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
