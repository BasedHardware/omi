import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

test("LoopbackServer binds requiredLocalEndpoint to IPv4 loopback, not NWListener(using:on:)", async () => {
  const source = await read("shell/Sources/OmiShell/LoopbackServer.swift");
  assert.match(source, /requiredLocalEndpoint\s*=/);
  assert.match(source, /\.ipv4\(\.loopback\)/);
  // The trap: NWListener(using:on:) binds all interfaces silently.
  assert.doesNotMatch(source, /NWListener\s*\(\s*using\s*:[^,)]+\s*,\s*on\s*:/);
  // red-proof: deleting requiredLocalEndpoint and constructing
  // NWListener(using: params, on: NWEndpoint.Port(...)) reddens this.
});
