// Source-contract tests for the iOS shell. These are deliberately source
// assertions, not runtime tests: the things they protect (a frozen origin, the
// absence of a swizzle) are structural properties of the host that a passing
// Flutter widget test would happily keep violating.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

test("the surface origin is frozen at omi-ui://local", async () => {
  const source = await read("app/ios/Runner/AppDelegate.swift");
  assert.match(source, /static let scheme = "omi-ui"/);
  // ADR-009: IndexedDB is origin-keyed, so the origin is a storage-correctness
  // invariant, not a naming preference. A per-launch or per-version origin is a
  // silent user-data wipe that no functional test would notice.
  // red-proof: changing the scheme literal, or deriving any part of the origin
  // from a bundle version / ephemeral port, fails this test.
  assert.doesNotMatch(source, /omi-ui-\\\(/);
});

test("the host serves static assets only and never proxies a remote origin", async () => {
  const source = await read("app/ios/Runner/AppDelegate.swift");
  // ADR-009 §3: the scheme handler is a static-asset reader. Domain traffic
  // goes over the privileged HTTP bridge, which holds the credential; a scheme
  // handler that could fetch would put the origin back in the page's reach.
  assert.doesNotMatch(source, /URLSession|dataTask|\.load\(/);
  // red-proof: adding a URLSession fetch inside the scheme handler fails here.
});
