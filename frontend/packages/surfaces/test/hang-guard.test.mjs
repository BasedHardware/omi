import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const guard = resolve(here, "../../../scripts/node-test-hang-guard.mjs");
const fixture = resolve(here, "fixtures/leaked-handle-fixture.mjs");
const hangMarker = "TEST FILE HANG:";

function runLeakedFixture(timeoutMs) {
  return new Promise((resolvePromise, rejectPromise) => {
    const env = { ...process.env, OMI_TEST_FILE_TIMEOUT_MS: String(timeoutMs) };
    delete env.NODE_TEST_CONTEXT;
    const child = spawn(
      process.execPath,
      [
        "--import",
        pathToFileURL(guard).href,
        "--experimental-test-isolation=process",
        "--test",
        fixture,
      ],
      {
        env,
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    const started = Date.now();
    const killTimer = setTimeout(() => {
      child.kill("SIGKILL");
      rejectPromise(new Error(`hang guard did not exit within ${timeoutMs + 5_000}ms`));
    }, timeoutMs + 5_000);
    child.on("error", (error) => {
      clearTimeout(killTimer);
      rejectPromise(error);
    });
    child.on("exit", (code, signal) => {
      clearTimeout(killTimer);
      resolvePromise({ code, signal, stdout, stderr, durationMs: Date.now() - started });
    });
  });
}

test("a leaked listen handle fails red with TEST FILE HANG diagnosis inside the budget", async () => {
  // red-proof: delete the hang-guard --import or raise the fixture timeout to
  // Infinity; this test then hits the outer kill and never sees the named marker.
  const result = await runLeakedFixture(2_000);
  const output = `${result.stdout}\n${result.stderr}`;
  assert.equal(result.signal, null, "the hang guard must exit, not be killed by the outer watchdog");
  assert.notEqual(result.code, 0, `a timeout must be red, never green\n${output}`);
  assert.match(output, new RegExp(hangMarker.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  assert.match(output, /activeResources:/);
  assert.match(output, /TCPServerWrap|PipeWrap|Timeout/);
  assert.match(output, /childProcesses:/);
  assert.ok(result.durationMs < 8_000, `guard must fail inside the budget, took ${result.durationMs}ms`);
  assert.doesNotMatch(output, /^# skipped [1-9]/m);
  assert.doesNotMatch(output, /\bskip(?:ped)?: true\b/i);
});
