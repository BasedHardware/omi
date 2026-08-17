import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

test("?rig=dev does not load a live client and never names the production host", async () => {
  const source = await read("src/production/main.tsx");
  // The old live-fetch harness lived at src/dev/main.tsx and defaulted a
  // base URL. It is gone. `?rig=dev` must refuse in-place without importing
  // a client that can issue requests.
  assert.match(source, /query\.get\("rig"\) === "dev"/);
  assert.match(source, /unsupportedRoute\(\)/);
  assert.doesNotMatch(source, /api\.omi\.me/);
  assert.doesNotMatch(source, /src\/dev\/main/);
  // red-proof: restoring the live-fetch harness (or navigating ?rig=dev into
  // a client that talks to production) reintroduces a swarm-wide blocker.
});
