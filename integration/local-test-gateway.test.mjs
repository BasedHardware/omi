import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const here = dirname(fileURLToPath(import.meta.url));
const script = join(here, "local-test-gateway.mjs");
const stack = readFileSync(join(here, "dev-stack.sh"), "utf8");
const source = readFileSync(script, "utf8");

test("local test gateway is disclosed and never a production or scripted source", () => {
  assert.match(source, /local test gateway/);
  assert.match(source, /never a production model/);
  assert.doesNotMatch(source, /https:\/\/api\.omi\.me/);
  assert.doesNotMatch(source, /createScriptedChatGenerationSource/);
  assert.match(source, /\/v1\/chat\/completions/);
  assert.match(source, /data: \[DONE\]/);
  assert.match(stack, /local-test-gateway\.mjs/);
  assert.match(stack, /OMI_LLM_GATEWAY_URL=/);
  assert.match(stack, /OMI_LLM_GATEWAY_SERVICE_TOKEN=/);
  assert.match(stack, /local test gateway/);
  assert.doesNotMatch(stack, /https:\/\/api\.omi\.me/);
  assert.doesNotMatch(stack, /createScriptedChatGenerationSource/);
  assert.match(stack, /never a production model/);
});

test("loopback gateway answers the authenticated SSE contract", async () => {
  const bun = spawnSync("bun", ["--version"], { encoding: "utf8" });
  if (bun.status !== 0) {
    assert.ok(true, "bun is required to spawn the local test gateway");
    return;
  }
  const scratch = mkdtempSync(join(tmpdir(), "omi-local-test-gateway-"));
  const readyPath = join(scratch, "ready.json");
  const child = spawn("bun", [script], {
    env: {
      ...process.env,
      OMI_LOCAL_TEST_GATEWAY_PORT: "0",
      OMI_LOCAL_TEST_GATEWAY_TOKEN: "local-test-gateway-token",
      OMI_LOCAL_TEST_GATEWAY_READY: readyPath,
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  try {
    const deadline = Date.now() + 5_000;
    let ready = null;
    while (Date.now() < deadline) {
      try {
        ready = JSON.parse(readFileSync(readyPath, "utf8"));
        break;
      } catch {
        await new Promise((resolve) => setTimeout(resolve, 25));
      }
    }
    assert.ok(ready, "gateway wrote a readiness record");
    assert.equal(ready.disclosure, "local test gateway");
    assert.equal(ready.production_model, false);
    assert.match(ready.url, /^http:\/\/127\.0\.0\.1:\d+$/);
    const denied = await fetch(`${ready.url}/v1/chat/completions`, { method: "POST" });
    assert.equal(denied.status, 401);
    const allowed = await fetch(`${ready.url}/v1/chat/completions`, {
      method: "POST",
      headers: { authorization: "Bearer local-test-gateway-token" },
    });
    assert.equal(allowed.status, 200);
    const body = await allowed.text();
    assert.match(body, /Local test gateway /);
    assert.match(body, /data: \[DONE\]/);
    assert.doesNotMatch(body, /mem1_|cit1_|https:\/\/api\.omi\.me/);
  } finally {
    child.kill("SIGTERM");
    rmSync(scratch, { recursive: true, force: true });
  }
});
