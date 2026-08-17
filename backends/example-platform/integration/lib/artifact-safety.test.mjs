// LIFECYCLE: permanent

import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { retainedArtifactFailures } from "./artifact-safety.mjs";

test("retained diagnostic and evidence artifacts contain no token, bearer credential, or base URL", () => {
  const scratch = mkdtempSync(join(tmpdir(), "omi-artifact-safety-"));
  try {
    const token = "secret-readiness-token";
    const safe = join(scratch, "safe.log");
    writeFileSync(safe, "service listening at [redacted-origin]\nAuthorization: Bearer [redacted]\nkept diagnostic\n");
    assert.deepEqual(retainedArtifactFailures({ paths: [scratch], secrets: [token] }), []);

    const unsafe = join(scratch, "unsafe.log");
    for (const content of [
      `token=${token}\n`,
      "Authorization: Bearer leaked-credential\n",
      "curl http://127.0.0.1:4851/ready\n",
      "OMI_API_TOKEN=leaked-credential\n",
    ]) {
      writeFileSync(unsafe, content);
      const failures = retainedArtifactFailures({ paths: [scratch], secrets: [token] });
      assert.ok(failures.some((failure) => failure.includes(unsafe)), content);
    }
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});
