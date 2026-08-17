import { mkdirSync } from "node:fs";
import { describe, expect, test } from "bun:test";

const scratch = `/tmp/folders-proofs-${process.pid}`;
mkdirSync(scratch, { recursive: true });
let number = 0;
const path = (label: string): string => `${scratch}/${++number}-${label}`;

const restartProof = new URL("./folders-restart-proof.ts", import.meta.url).pathname;
const atomicityProof = new URL("./folders-delete-crash-proof.ts", import.meta.url).pathname;

describe("folder restart persistence proof", () => {
  const run = (databasePath: string) => Bun.spawnSync({
    cmd: [process.execPath, "run", restartProof, databasePath],
    stdout: "pipe",
    stderr: "pipe",
  });

  test(":memory: loses the folder across the process restart", () => {
    const result = run(":memory:");
    expect(result.exitCode).not.toBe(0);
    expect(result.stderr.toString()).toContain("folder restart persistence proof failed");
    expect(result.stderr.toString()).toContain('"found": false');
  });

  test("a file preserves the folder across the process restart", () => {
    const result = run(path("restart.sqlite"));
    expect(result.exitCode, result.stderr.toString()).toBe(0);
    expect(result.stdout.toString()).toBe([
      "write folder in first process: complete",
      "kill first process: complete",
      "start second process: complete",
      'read folder in second process: found id="folder-persistent" name="Persistent folder"',
      "",
    ].join("\n"));
  });
});

describe("folder deletion atomicity proof", () => {
  test("SIGKILL between reassignment and delete leaves neither write", () => {
    const result = Bun.spawnSync({
      cmd: [
        process.execPath,
        "run",
        atomicityProof,
        path("atomic.sqlite"),
        path("atomic.marker"),
      ],
      stdout: "pipe",
      stderr: "pipe",
    });
    expect(result.exitCode, result.stderr.toString()).toBe(0);
    expect(result.stdout.toString()).toBe([
      "child reached boundary: conversations reassigned, folder not deleted",
      "kill child: SIGKILL",
      "restart child: complete",
      "after crash: source_folder=present target_folder=present conversation.folder_id=folder-source",
      "folder delete atomicity proof: PASS",
      "",
    ].join("\n"));
  });
});
