#!/usr/bin/env node
// LIFECYCLE: permanent
// Persist diagnostic shape, never credentials or backend origins. Service logs
// are sanitized before the first byte reaches disk: raw service output exists
// only in the kernel pipe while this process waits for the readiness token.

import { existsSync, readFileSync, writeFileSync } from "node:fs";

import { validateServiceReadiness } from "./evidence-matrix.mjs";
import { commandMatchesService, processSnapshot } from "./process-owner.mjs";

export function sanitizeLogText(input, redactions = []) {
  let safe = input;
  for (const value of redactions.filter(Boolean)) safe = safe.split(value).join("[redacted]");
  return safe
    .replace(/https?:\/\/[^\s)'"\]]+/gu, "[redacted-origin]")
    .replace(/(authorization:\s*bearer\s+)[^\s]+/giu, "$1[redacted]")
    .replace(/(\bOMI_API_TOKEN\s*=\s*)[^\s]+/gu, "$1[redacted]")
    .replace(/((?:dev[\s_-]*)?token\s*[:=]\s*)[^\s]+/giu, "$1[redacted]");
}

const argv = process.argv.slice(2);
const flag = (name) => {
  const index = argv.indexOf(name);
  return index === -1 ? null : argv[index + 1];
};
const output = flag("--out");
const redactions = argv.flatMap((value, index) => value === "--redact" && argv[index + 1] ? [argv[index + 1]] : []);

function fileMode() {
  const input = flag("--in");
  if (!input || !output) {
    process.stderr.write("usage: sanitize-log.mjs --in <raw> --out <safe> [--redact <value>]...\n");
    process.exitCode = 2;
    return;
  }
  writeFileSync(output, sanitizeLogText(readFileSync(input, "utf8"), redactions), { mode: 0o600 });
}

function streamMode() {
  const readinessPath = flag("--readiness");
  const readyOut = flag("--ready-out");
  const expectedRunId = flag("--run-id");
  const expectedExecutable = flag("--executable");
  const expectedBaseUrl = flag("--base-url");
  const expectedDatabase = flag("--database");
  const expectedPid = Number(flag("--pid"));
  const expectedStartIdentity = flag("--process-start-identity");
  if (!output || !readinessPath || !readyOut || !expectedRunId || !expectedExecutable
    || !expectedBaseUrl || !expectedDatabase || !Number.isSafeInteger(expectedPid) || expectedPid <= 0
    || !expectedStartIdentity) {
    process.stderr.write("usage: sanitize-log.mjs --stream --out <safe> --readiness <record> --ready-out <path> --run-id <raw> --executable <relative> --base-url <origin> --database <absolute> --pid <positive> --process-start-identity <kernel-start>\n");
    process.exitCode = 2;
    return;
  }

  writeFileSync(output, "", { mode: 0o600 });
  let pending = "";
  let activated = false;
  let ended = false;
  let finished = false;
  let timer;

  const serviceSnapshot = () => {
    const snapshot = processSnapshot(expectedPid);
    if (snapshot === null || snapshot.startIdentity !== expectedStartIdentity) return null;
    return snapshot;
  };

  const flush = (all = false) => {
    const boundary = all ? pending.length : pending.lastIndexOf("\n") + 1;
    if (boundary <= 0) return;
    const raw = pending.slice(0, boundary);
    pending = pending.slice(boundary);
    writeFileSync(output, sanitizeLogText(raw, redactions), { flag: "a", mode: 0o600 });
  };

  const activate = () => {
    if (activated || !existsSync(readinessPath)) return false;
    try {
      const readiness = JSON.parse(readFileSync(readinessPath, "utf8"));
      const validation = validateServiceReadiness(readiness, {
        runId: expectedRunId,
        executable: expectedExecutable,
        baseUrl: expectedBaseUrl,
        databasePath: expectedDatabase,
        pid: expectedPid,
      });
      const snapshot = serviceSnapshot();
      if (!validation.ok || snapshot === null || !commandMatchesService(snapshot.command)) return false;
      redactions.push(readiness.devToken, readiness.baseUrl);
      activated = true;
      flush(false);
      writeFileSync(readyOut, "sanitizer-ready\n", { flag: "wx", mode: 0o600 });
      return true;
    } catch {
      return false;
    }
  };

  const finish = () => {
    if (finished) return;
    finished = true;
    if (!activated) {
      // Without the independent token coordinate there is no safe way to
      // prove arbitrary output clean. Fail closed and persist only our own
      // diagnostic, never the buffered service bytes.
      pending = "";
      writeFileSync(output, "service diagnostics withheld: readiness identity unavailable\n", { flag: "a", mode: 0o600 });
    } else {
      flush(true);
    }
    if (timer) clearInterval(timer);
  };

  process.stdin.setEncoding("utf8");
  process.stdin.on("data", (chunk) => {
    pending += chunk;
    if (pending.length > 4 * 1024 * 1024 && !activated) {
      pending = "";
      process.stderr.write("service log sanitizer refused more than 4 MiB before readiness\n");
      process.exitCode = 1;
      process.stdin.destroy();
      return;
    }
    if (activate()) return;
    if (activated) flush(false);
  });
  process.stdin.on("end", () => { ended = true; finish(); });
  process.stdin.on("close", () => { if (!ended) finish(); });
  timer = setInterval(() => {
    const snapshot = serviceSnapshot();
    if (snapshot === null || (activated && !commandMatchesService(snapshot.command))) {
      finish();
      process.stdin.destroy();
      return;
    }
    if (activate() && ended) finish();
  }, 20);
}

if (argv.includes("--stream")) streamMode();
else fileMode();
