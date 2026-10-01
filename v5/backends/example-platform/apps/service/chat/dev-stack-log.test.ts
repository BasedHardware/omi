import { afterEach, expect, test } from "bun:test";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  appendDevStackLog,
  logLineHasSecret,
  resolveDevStackLogDir,
} from "./dev-stack-log";

const originalRunDir = process.env.OMI_DEV_STACK_RUNDIR;
let runDir = "";

afterEach(() => {
  if (originalRunDir === undefined) delete process.env.OMI_DEV_STACK_RUNDIR;
  else process.env.OMI_DEV_STACK_RUNDIR = originalRunDir;
  if (runDir.length > 0) rmSync(runDir, { recursive: true, force: true });
  runDir = "";
});

test("dev-stack JSONL is append-only, shaped, and drops secrets", () => {
  runDir = mkdtempSync(join(tmpdir(), "omi-dev-stack-log-"));
  process.env.OMI_DEV_STACK_RUNDIR = runDir;
  appendDevStackLog("chat", "info", "generation_admitted", {
    generationId: "g1",
    authorization: "Bearer super-secret",
    prompt: "never log this",
    attempt: 1,
  });
  appendDevStackLog("gateway", "info", "upstream_status", {
    status: 200,
    token: "also-secret",
    elapsedMs: 12,
  });
  const chat = readFileSync(join(resolveDevStackLogDir(), "chat.jsonl"), "utf8");
  const gateway = readFileSync(join(resolveDevStackLogDir(), "gateway.jsonl"), "utf8");
  expect(JSON.parse(chat)).toMatchObject({
    proc: "chat",
    level: "info",
    event: "generation_admitted",
    generationId: "g1",
    attempt: 1,
  });
  expect(JSON.parse(gateway)).toMatchObject({
    proc: "gateway",
    event: "upstream_status",
    status: 200,
    elapsedMs: 12,
  });
  expect(logLineHasSecret(chat + gateway, ["Bearer super-secret", "never log this", "also-secret"])).toBe(false);
  expect(chat).not.toContain("authorization");
  expect(gateway).not.toContain("token");
});
