import { mkdirSync } from "node:fs";
import { expect, test } from "bun:test";

const proof = new URL("./conversations-restart-proof.ts", import.meta.url).pathname;
const scratch = `/tmp/conversations-restart-${process.pid}`;
mkdirSync(scratch, { recursive: true });

const run = (path: string) => Bun.spawnSync({
  cmd: [process.execPath, "run", proof, path],
  stdout: "pipe",
  stderr: "pipe",
});

test("a conversation survives a real stop and restart in separate processes", () => {
  const result = run(`${scratch}/proof.sqlite`);
  expect(result.exitCode, result.stderr.toString()).toBe(0);
  expect(result.stdout.toString()).toBe([
    "write conversation in first process: complete",
    "stop first process: complete",
    "start second process: complete",
    'read conversation in second process: found title="Persistent after mutation" revision=1',
    "",
  ].join("\n"));
});

test(":memory: mutation makes the separate-process persistence proof fail", () => {
  const result = run(":memory:");
  expect(result.exitCode).not.toBe(0);
  expect(result.stderr.toString()).toContain("conversation restart persistence proof failed");
});
