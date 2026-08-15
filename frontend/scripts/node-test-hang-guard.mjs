#!/usr/bin/env node
// Per-file hang diagnosis for `node --test`.
//
// A leaked bundler/server handle after the test body finishes parks the file
// process in kevent at 0% CPU. `--test-timeout` does not cover that: it bounds
// an in-flight test, not the event loop after `after()` returns. This guard
// does. It must fail red with a named diagnosis — never skip, never green.
//
// The timer is unref'd so a clean file still exits immediately. That unref is
// not a leak fix: it only keeps the diagnostic from becoming the handle that
// holds the process. If anything else is still referenced (the actual hang),
// the timer fires, dumps active resources and child pids, and exits 1.

import { execFileSync } from "node:child_process";

export const TEST_FILE_HANG_MARKER = "TEST FILE HANG:";
export const DEFAULT_TEST_FILE_TIMEOUT_MS = 240_000;

function parseTimeoutMs() {
  const raw = process.env.OMI_TEST_FILE_TIMEOUT_MS;
  if (raw == null || raw === "") return DEFAULT_TEST_FILE_TIMEOUT_MS;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    process.stderr.write(
      `${TEST_FILE_HANG_MARKER} OMI_TEST_FILE_TIMEOUT_MS must be a positive number of milliseconds, got ${JSON.stringify(raw)}\n`,
    );
    process.exit(2);
  }
  return parsed;
}

function argvHas(flag) {
  return process.execArgv.includes(flag) || process.argv.includes(flag);
}

function shouldArm() {
  if (process.env.OMI_TEST_HANG_GUARD === "0") return false;
  if (process.env.OMI_TEST_HANG_GUARD === "1") return true;
  if (process.env.NODE_TEST_CONTEXT) return true;
  // isolation=none runs tests in this process; NODE_TEST_CONTEXT is unset.
  if (argvHas("--test") && process.execArgv.some((arg) => arg.includes("isolation=none"))) {
    return true;
  }
  const entry = process.argv[1];
  return typeof entry === "string" && /\.(test|spec)\.[cm]?js$/.test(entry);
}

function listDescendantProcesses(rootPid) {
  let rows = [];
  try {
    const out = execFileSync("/bin/ps", ["-axo", "pid=,ppid=,command="], {
      encoding: "utf8",
      timeout: 2_000,
    });
    rows = out
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const match = /^(\d+)\s+(\d+)\s+(.*)$/.exec(line);
        return match ? { pid: match[1], ppid: match[2], command: match[3] } : null;
      })
      .filter(Boolean);
  } catch {
    return [];
  }
  const children = [];
  const queue = [String(rootPid)];
  const seen = new Set(queue);
  while (queue.length > 0) {
    const current = queue.shift();
    for (const row of rows) {
      if (row.ppid !== current || seen.has(row.pid)) continue;
      seen.add(row.pid);
      children.push(row);
      queue.push(row.pid);
    }
  }
  return children;
}

export function formatHangDiagnosis({
  timeoutMs,
  pid = process.pid,
  argv = process.argv,
  resources = typeof process.getActiveResourcesInfo === "function"
    ? process.getActiveResourcesInfo()
    : [],
  children = listDescendantProcesses(pid),
} = {}) {
  const resourceLines = resources.length > 0 ? resources.join(", ") : "(none)";
  const childLines = children.length > 0
    ? children.map((child) => `    ${child.pid} ${child.command}`).join("\n")
    : "    (none)";
  return [
    `${TEST_FILE_HANG_MARKER} test file still alive after ${timeoutMs}ms`,
    `  pid: ${pid}`,
    `  argv: ${argv.join(" ")}`,
    `  activeResources: ${resourceLines}`,
    "  childProcesses:",
    childLines,
    "",
  ].join("\n");
}

export function diagnoseHangAndExit(timeoutMs) {
  process.stderr.write(formatHangDiagnosis({ timeoutMs }));
  process.exit(1);
}

if (shouldArm()) {
  const timeoutMs = parseTimeoutMs();
  const timer = setTimeout(() => diagnoseHangAndExit(timeoutMs), timeoutMs);
  // Diagnostic only — see file comment. Do not unref bundler/server handles.
  timer.unref();
}
