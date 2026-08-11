#!/usr/bin/env node
// LIFECYCLE: permanent
// Durable ownership for the one direct platform service process. A PID is not
// identity: every signal is gated by the run, command, owner token, and kernel
// process-start identity recorded after launch.

import { execFileSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync, readFileSync, unlinkSync, writeFileSync } from "node:fs";
import { isAbsolute } from "node:path";
import { fileURLToPath } from "node:url";

import { SERVICE_EXECUTABLE, rawRunIdFailure, validateServiceReadiness } from "./evidence-matrix.mjs";

export const PROCESS_OWNER_SCHEMA = "omi.dev-stack-owner.v1";
export const EXPECTED_COMMAND = `bun ${SERVICE_EXECUTABLE}`;
const OWNER_KEYS = Object.freeze([
  "schema",
  "runId",
  "pid",
  "expectedExecutable",
  "expectedCommand",
  "ownerToken",
  "processStartIdentity",
  "databasePath",
  "readinessPath",
]);

const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const exactKeys = (value, expected) => isObject(value)
  && Object.keys(value).sort().join("\0") === [...expected].sort().join("\0");

export function processSnapshot(pid) {
  if (!Number.isSafeInteger(pid) || pid <= 0) return null;
  try {
    process.kill(pid, 0);
    const state = execFileSync("ps", ["-p", String(pid), "-o", "state="], { encoding: "utf8" }).trim();
    if (state.startsWith("Z")) return null;
    const startIdentity = execFileSync("ps", ["-p", String(pid), "-o", "lstart="], { encoding: "utf8" }).trim();
    const command = execFileSync("ps", ["-p", String(pid), "-o", "command="], { encoding: "utf8" }).trim();
    if (startIdentity === "" || command === "") return null;
    return Object.freeze({ pid, startIdentity, command });
  } catch {
    return null;
  }
}

export function commandMatchesService(command) {
  return typeof command === "string"
    && /(?:^|\/)bun(?:\s|$)/u.test(command)
    && command.includes(SERVICE_EXECUTABLE);
}

export function validateOwnerRecord(record) {
  const failures = [];
  if (!exactKeys(record, OWNER_KEYS)) failures.push("owner record keys are not exact");
  const runFailure = rawRunIdFailure(record?.runId);
  if (runFailure) failures.push(runFailure);
  if (!Number.isSafeInteger(record?.pid) || record.pid <= 0) failures.push("owner pid must be a positive integer");
  if (record?.schema !== PROCESS_OWNER_SCHEMA) failures.push(`owner schema must be ${PROCESS_OWNER_SCHEMA}`);
  if (record?.expectedExecutable !== SERVICE_EXECUTABLE) failures.push("owner executable is unknown");
  if (record?.expectedCommand !== EXPECTED_COMMAND) failures.push("owner command is unknown");
  if (typeof record?.ownerToken !== "string" || !/^[0-9a-f]{32}$/u.test(record.ownerToken)) failures.push("owner token is invalid");
  if (typeof record?.processStartIdentity !== "string" || record.processStartIdentity.trim() === "") failures.push("owner process start identity is missing");
  if (typeof record?.databasePath !== "string" || !isAbsolute(record.databasePath)) failures.push("owner database path must be absolute");
  if (typeof record?.readinessPath !== "string" || !isAbsolute(record.readinessPath)) failures.push("owner readiness path must be absolute");
  return Object.freeze({ ok: failures.length === 0, failures: Object.freeze(failures) });
}

export function inspectOwner(record) {
  const validation = validateOwnerRecord(record);
  const snapshot = processSnapshot(record?.pid);
  const failures = [...validation.failures];
  if (validation.ok) {
    try {
      const readiness = JSON.parse(readFileSync(record.readinessPath, "utf8"));
      const readinessResult = validateServiceReadiness(readiness, {
        runId: record.runId,
        databasePath: record.databasePath,
        pid: record.pid,
      });
      failures.push(...readinessResult.failures.map((failure) => `owner readiness mismatch: ${failure}`));
    } catch (error) {
      failures.push(`owner readiness record is unavailable: ${error.message}`);
    }
  }
  if (snapshot === null) failures.push("owner process is not alive");
  else {
    if (snapshot.startIdentity !== record.processStartIdentity) failures.push("owner PID was reused or has a stale start identity");
    if (!commandMatchesService(snapshot.command)) failures.push("owner PID has an unknown executable or command");
  }
  return Object.freeze({ ok: failures.length === 0, alive: snapshot !== null, failures: Object.freeze(failures), snapshot });
}

function readRecord(path) {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch (error) {
    throw new Error(`owner record is unreadable: ${error.message}`);
  }
}

function sameRecordOnDisk(path, record) {
  try {
    return JSON.stringify(JSON.parse(readFileSync(path, "utf8"))) === JSON.stringify(record);
  } catch {
    return false;
  }
}

function waitBriefly() {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 100);
}

export function stopOwnedProcess(path) {
  if (!existsSync(path)) return Object.freeze({ stopped: false, skipped: true, detail: "no owner record" });
  const record = readRecord(path);
  const inspected = inspectOwner(record);
  if (!inspected.ok) {
    if (!inspected.alive && sameRecordOnDisk(path, record)) unlinkSync(path);
    return Object.freeze({ stopped: false, skipped: true, detail: inspected.failures.join("; "), pid: record.pid });
  }

  process.kill(record.pid, "SIGTERM");
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (processSnapshot(record.pid) === null) break;
    waitBriefly();
  }
  const afterTerm = processSnapshot(record.pid);
  if (afterTerm !== null) {
    if (afterTerm.startIdentity !== record.processStartIdentity || !commandMatchesService(afterTerm.command)) {
      return Object.freeze({ stopped: false, skipped: true, detail: "process identity changed before escalation; SIGKILL skipped", pid: record.pid });
    }
    process.kill(record.pid, "SIGKILL");
  }
  if (sameRecordOnDisk(path, record)) unlinkSync(path);
  return Object.freeze({ stopped: true, skipped: false, detail: "verified owner stopped", pid: record.pid });
}

function flag(argv, name) {
  const index = argv.indexOf(name);
  return index === -1 ? null : argv[index + 1];
}

function print(value) {
  process.stdout.write(`${JSON.stringify(value)}\n`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const argv = process.argv.slice(2);
  const command = argv.shift();
  const path = flag(argv, "--record");
  try {
    if (command === "new-token") {
      process.stdout.write(`${randomBytes(16).toString("hex")}\n`);
    } else if (command === "snapshot") {
      const snapshot = processSnapshot(Number(flag(argv, "--pid")));
      if (snapshot === null) throw new Error("process is not alive");
      print(snapshot);
    } else if (command === "prepare") {
      if (!path) throw new Error("prepare needs --record");
      if (!existsSync(path)) print({ ok: true, detail: "owner slot is empty" });
      else {
        const record = readRecord(path);
        const inspected = inspectOwner(record);
        if (inspected.alive) throw new Error(`owner slot belongs to live pid ${record.pid}: ${inspected.failures.join("; ") || "verified owner"}`);
        if (sameRecordOnDisk(path, record)) unlinkSync(path);
        print({ ok: true, detail: `removed stale dead owner record for pid ${record.pid}` });
      }
    } else if (command === "write") {
      if (!path) throw new Error("write needs --record");
      const record = {
        schema: PROCESS_OWNER_SCHEMA,
        runId: flag(argv, "--run-id"),
        pid: Number(flag(argv, "--pid")),
        expectedExecutable: SERVICE_EXECUTABLE,
        expectedCommand: EXPECTED_COMMAND,
        ownerToken: flag(argv, "--owner-token"),
        processStartIdentity: flag(argv, "--start-identity"),
        databasePath: flag(argv, "--database"),
        readinessPath: flag(argv, "--readiness"),
      };
      const inspected = inspectOwner(record);
      if (!inspected.ok) throw new Error(inspected.failures.join("; "));
      writeFileSync(path, `${JSON.stringify(record, null, 2)}\n`, { flag: "wx", mode: 0o600 });
      print({ ok: true, pid: record.pid, runId: record.runId });
    } else if (command === "stop") {
      if (!path) throw new Error("stop needs --record");
      const result = stopOwnedProcess(path);
      print(result);
      if (result.skipped && result.detail !== "no owner record") process.exitCode = 3;
    } else {
      throw new Error("usage: process-owner.mjs <new-token|snapshot|prepare|write|stop> ...");
    }
  } catch (error) {
    process.stderr.write(`ERROR: ${error.message}\n`);
    process.exitCode = 1;
  }
}
