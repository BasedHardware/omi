#!/usr/bin/env bun
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import {
  isRuntimeLogLevel,
  isRuntimeLogProc,
  resolveRuntimeLogDirectory,
  RUNTIME_LOG_FILES,
  RUNTIME_LOG_LEVELS,
  RUNTIME_LOG_PROCS,
  type RuntimeLogLevel,
  type RuntimeLogProc,
  type RuntimeLogRecord,
} from "../apps/service/observability/runtime-log";

export const DEFAULT_LOG_LIMIT = 50;

export interface DevLogsQuery {
  readonly dir?: string;
  readonly limit?: number;
  readonly since?: string;
  readonly proc?: RuntimeLogProc;
  readonly level?: RuntimeLogLevel;
  readonly event?: string;
  readonly errors?: boolean;
}

const LEVEL_RANK: Readonly<Record<RuntimeLogLevel, number>> = Object.freeze({
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
});

const isRecord = (value: unknown): value is RuntimeLogRecord => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  return typeof record.ts === "string"
    && isRuntimeLogProc(record.proc)
    && isRuntimeLogLevel(record.level)
    && typeof record.event === "string";
};

const logFilesFor = (dir: string, proc?: RuntimeLogProc): readonly string[] => {
  const procs = proc === undefined ? RUNTIME_LOG_PROCS : [proc];
  const files: string[] = [];
  for (const name of procs) {
    const current = join(dir, RUNTIME_LOG_FILES[name]);
    files.push(`${current}.1`, current);
  }
  return files;
};

const parseLine = (line: string): RuntimeLogRecord | null => {
  if (line.length === 0) return null;
  try {
    const parsed: unknown = JSON.parse(line);
    return isRecord(parsed) ? parsed : null;
  } catch {
    return null;
  }
};

const compareRecords = (left: RuntimeLogRecord, right: RuntimeLogRecord): number => {
  if (left.ts !== right.ts) return left.ts < right.ts ? -1 : 1;
  if (left.proc !== right.proc) return left.proc < right.proc ? -1 : 1;
  if (left.event !== right.event) return left.event < right.event ? -1 : 1;
  const leftId = typeof left.request_id === "string" ? left.request_id : "";
  const rightId = typeof right.request_id === "string" ? right.request_id : "";
  if (leftId !== rightId) return leftId < rightId ? -1 : 1;
  return 0;
};

const matchesSince = (ts: string, since: string | undefined): boolean => {
  if (since === undefined) return true;
  return ts >= since;
};

export const readRuntimeLogs = (query: DevLogsQuery = {}): readonly RuntimeLogRecord[] => {
  const dir = resolveRuntimeLogDirectory(query.dir);
  const records: RuntimeLogRecord[] = [];
  for (const path of logFilesFor(dir, query.proc)) {
    if (!existsSync(path)) continue;
    let text = "";
    try {
      text = readFileSync(path, "utf8");
    } catch {
      continue;
    }
    for (const line of text.split("\n")) {
      const record = parseLine(line);
      if (record === null) continue;
      if (query.proc !== undefined && record.proc !== query.proc) continue;
      if (query.event !== undefined && record.event !== query.event) continue;
      if (query.errors === true && LEVEL_RANK[record.level] < LEVEL_RANK.warn) continue;
      if (query.level !== undefined && record.level !== query.level) continue;
      if (!matchesSince(record.ts, query.since)) continue;
      records.push(record);
    }
  }
  records.sort(compareRecords);
  const limit = Number.isSafeInteger(query.limit) && (query.limit ?? 0) > 0
    ? query.limit as number
    : DEFAULT_LOG_LIMIT;
  return records.length <= limit ? records : records.slice(records.length - limit);
};

const fieldText = (record: RuntimeLogRecord, key: string): string | null => {
  const value = record[key];
  if (typeof value === "string" && value.length > 0) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return null;
};

export const formatRuntimeLogLine = (record: RuntimeLogRecord): string => {
  const parts = [record.ts, record.proc, record.level, record.event];
  const method = fieldText(record, "method");
  const path = fieldText(record, "path");
  if (method !== null && path !== null) {
    parts.push(method, path);
    const status = fieldText(record, "status");
    if (status !== null) parts.push(status);
    const duration = fieldText(record, "duration_ms");
    if (duration !== null) parts.push(`${duration}ms`);
  } else {
    for (const key of ["reason", "persona", "stt_engine", "gateway_kind", "gateway_model", "port"]) {
      const value = fieldText(record, key);
      if (value !== null) parts.push(`${key}=${value}`);
    }
  }
  return parts.join(" ");
};

export interface DevLogsCliResult {
  readonly code: number;
  readonly stdout: string;
  readonly stderr: string;
}

const usage = "usage: bun run logs [--since <iso>] [--proc <proc>] [--level <level>] [--event <slug>] [--errors] [--json] [--limit <n>] [--dir <path>]\n";

const readFlag = (argv: readonly string[], name: string): string | null => {
  const index = argv.indexOf(name);
  return index === -1 ? null : argv[index + 1] ?? null;
};

export const runDevLogsCli = (argv: readonly string[]): DevLogsCliResult => {
  if (argv.includes("--help") || argv.includes("-h")) {
    return { code: 0, stdout: usage, stderr: "" };
  }
  const procFlag = readFlag(argv, "--proc");
  if (procFlag !== null && !isRuntimeLogProc(procFlag)) {
    return {
      code: 2,
      stdout: "",
      stderr: `omi logs: --proc must be one of ${RUNTIME_LOG_PROCS.join("|")}\n`,
    };
  }
  const levelFlag = readFlag(argv, "--level");
  if (levelFlag !== null && !isRuntimeLogLevel(levelFlag)) {
    return {
      code: 2,
      stdout: "",
      stderr: `omi logs: --level must be one of ${RUNTIME_LOG_LEVELS.join("|")}\n`,
    };
  }
  const since = readFlag(argv, "--since");
  if (since !== null && Number.isNaN(Date.parse(since))) {
    return { code: 2, stdout: "", stderr: "omi logs: --since must be an ISO-8601 timestamp\n" };
  }
  const limitFlag = readFlag(argv, "--limit");
  let limit: number | undefined;
  if (limitFlag !== null) {
    if (!/^[0-9]{1,6}$/.test(limitFlag) || Number(limitFlag) < 1) {
      return { code: 2, stdout: "", stderr: "omi logs: --limit must be a positive integer\n" };
    }
    limit = Number(limitFlag);
  }
  const records = readRuntimeLogs({
    ...(readFlag(argv, "--dir") === null ? {} : { dir: readFlag(argv, "--dir") as string }),
    ...(limit === undefined ? {} : { limit }),
    ...(since === null ? {} : { since }),
    ...(procFlag === null ? {} : { proc: procFlag }),
    ...(levelFlag === null ? {} : { level: levelFlag }),
    ...(readFlag(argv, "--event") === null ? {} : { event: readFlag(argv, "--event") as string }),
    ...(argv.includes("--errors") ? { errors: true } : {}),
  });
  if (argv.includes("--json")) {
    return { code: 0, stdout: `${JSON.stringify(records)}\n`, stderr: "" };
  }
  return {
    code: 0,
    stdout: records.map((record) => formatRuntimeLogLine(record)).join("\n") + (records.length > 0 ? "\n" : ""),
    stderr: "",
  };
};

if (import.meta.main) {
  const result = runDevLogsCli(process.argv.slice(2));
  if (result.stdout.length > 0) process.stdout.write(result.stdout);
  if (result.stderr.length > 0) process.stderr.write(result.stderr);
  process.exit(result.code);
}
