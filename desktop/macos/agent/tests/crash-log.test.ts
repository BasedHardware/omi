import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { lstatSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import { crashLogPath, ensureCrashLogOwnerOnly, logCrashTo } from "../src/runtime/crash-log.js";

describe("agent crash log", () => {
  let root: string;

  beforeEach(() => {
    root = mkdtempSync(join(tmpdir(), "omi-crash-log-"));
  });

  afterEach(() => {
    rmSync(root, { recursive: true, force: true });
  });

  it("resolves under the owner-only Omi log directory, not /tmp", () => {
    expect(crashLogPath("/Users/example")).toBe("/Users/example/Library/Logs/Omi/agent-crash.log");
    expect(crashLogPath("/Users/example")).not.toContain("/tmp");
  });

  it("creates the log directory 0700 and the log file 0600", () => {
    const path = join(root, "Library", "Logs", "Omi", "agent-crash.log");

    logCrashTo(path, "boom");

    expect(lstatSync(path).mode & 0o777).toBe(0o600);
    expect(lstatSync(join(root, "Library", "Logs", "Omi")).mode & 0o777).toBe(0o700);
    expect(readFileSync(path, "utf8")).toContain("boom");
  });

  it("tightens an owner-owned log left world-readable by an older build", () => {
    const path = join(root, "agent-crash.log");
    writeFileSync(path, "existing\n", { mode: 0o644 });

    expect(ensureCrashLogOwnerOnly(path)).toBe(true);
    expect(lstatSync(path).mode & 0o777).toBe(0o600);
    expect(readFileSync(path, "utf8")).toBe("existing\n");
  });

  it("replaces a pre-existing symlink instead of appending through it", () => {
    const victim = join(root, "zshenv-victim");
    const path = join(root, "agent-crash.log");
    writeFileSync(victim, "original\n", { mode: 0o600 });
    symlinkSync(victim, path);

    logCrashTo(path, "boom");

    expect(lstatSync(path).isSymbolicLink()).toBe(false);
    expect(lstatSync(path).isFile()).toBe(true);
    expect(lstatSync(path).mode & 0o777).toBe(0o600);
    expect(readFileSync(victim, "utf8")).toBe("original\n");
    expect(readFileSync(path, "utf8")).toContain("boom");
  });

  it("sanitizes secrets out of crash text before it reaches disk", () => {
    const path = join(root, "agent-crash.log");

    logCrashTo(path, "Uncaught exception: Authorization: Bearer abc123DEF456 failed");

    const contents = readFileSync(path, "utf8");
    expect(contents).toContain("Bearer [redacted]");
    expect(contents).not.toContain("abc123DEF456");
  });

  it("never throws when the log path cannot be materialized", () => {
    const blocked = join(root, "blocked");
    writeFileSync(blocked, "not-a-directory\n");

    expect(() => logCrashTo(join(blocked, "agent-crash.log"), "boom")).not.toThrow();
  });
});
