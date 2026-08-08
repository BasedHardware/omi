// The acceptance verdict must not be satisfiable by requests that FAILED.
//
// This is the single most expensive lesson on record here: a bridge reported
// itself active, passed every custody probe, and delivered zero usable domain
// data while the UI sat empty — and the tests stayed green. It recurred on this
// branch: the shell printed `servedCount=4 status=PASS` while the app rendered
// "0 loaded items / No results", because servedCount increments at DISPATCH,
// before the response exists.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

test("the bridge counts response outcomes, not just dispatches", async () => {
  const source = await read("shell/Sources/OmiShell/BridgeHttp.swift");
  assert.match(source, /private\(set\) var succeededCount = 0/);
  assert.match(source, /private\(set\) var httpErrorCount = 0/);
  assert.match(source, /private\(set\) var transportFailureCount = 0/);
  // A 2xx check must gate the success counter.
  assert.match(source, /\(200\.\.<300\)\.contains\(http\.statusCode\)/);
  // red-proof: deleting the succeededCount increment, or incrementing it
  // unconditionally alongside servedCount, fails this test.
});

test("acceptance PASS keys on succeeded traffic, never on dispatched traffic", async () => {
  const source = await read("shell/Sources/OmiShell/main.swift");
  assert.match(source, /acceptancePassed = succeeded > 0/);
  // The old, false-green form must not come back.
  assert.doesNotMatch(source, /acceptancePassed = served > 0/);
  // The bounded-wait path must also wait on successes, otherwise a run whose
  // requests all 401 would short-circuit to a verdict before the retry window.
  assert.match(source, /httpHandler\?\.succeededCount \?\? 0\) == 0/);
  // red-proof: restoring `acceptancePassed = served > 0` reddens this test —
  // that exact line reported PASS on a visibly empty app.
});
