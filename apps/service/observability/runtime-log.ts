import {
  appendFileSync,
  mkdirSync,
  renameSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { join } from "node:path";

export const RUNTIME_LOG_PROCS = Object.freeze([
  "service",
  "gateway",
  "chat",
  "shell",
  "surface",
] as const);

export const RUNTIME_LOG_LEVELS = Object.freeze([
  "debug",
  "info",
  "warn",
  "error",
] as const);

export const RUNTIME_LOG_FILES = Object.freeze({
  service: "service.jsonl",
  gateway: "gateway.jsonl",
  chat: "chat.jsonl",
  shell: "shell.jsonl",
  surface: "surface-console.jsonl",
} as const);

export const DEFAULT_RUNTIME_LOG_MAX_BYTES = 32 * 1024 * 1024;

export type RuntimeLogProc = (typeof RUNTIME_LOG_PROCS)[number];
export type RuntimeLogLevel = (typeof RUNTIME_LOG_LEVELS)[number];

export type RuntimeLogScalar = string | number | boolean | null;
export type RuntimeLogValue = RuntimeLogScalar | readonly string[];

export interface RuntimeLogRecord {
  readonly ts: string;
  readonly proc: RuntimeLogProc;
  readonly level: RuntimeLogLevel;
  readonly event: string;
  readonly [field: string]: RuntimeLogValue | RuntimeLogProc | RuntimeLogLevel;
}

export interface RuntimeLogInput {
  readonly proc: RuntimeLogProc;
  readonly level: RuntimeLogLevel;
  readonly event: string;
  readonly ts?: string;
  readonly [field: string]: RuntimeLogValue | RuntimeLogProc | RuntimeLogLevel | undefined;
}

export interface RuntimeLogSink {
  readonly write: (input: RuntimeLogInput) => void;
}

export interface RuntimeLogSinkOptions {
  readonly proc: RuntimeLogProc;
  readonly dir?: string;
  readonly maxBytes?: number;
  readonly nowIso?: () => string;
  readonly onFallback?: (line: string, reason: string) => void;
}

const DEFAULT_RUNDIR = "/tmp/omi-dev-stack";
const MAX_EVENT_CHARS = 64;
const MAX_STRING_CHARS = 256;
const MAX_ARRAY_LENGTH = 32;
const EVENT_SLUG = /^[a-z][a-z0-9._-]{0,62}[a-z0-9]$/;
const FORBIDDEN_KEY = /token|secret|password|authorization|bearer|api[_-]?key|cookie|prompt|transcript|payload|ocr|pixel/i;
const FORBIDDEN_EXACT = new Set([
  "body",
  "content",
  "message",
  "raw",
  "raw_text",
  "frame",
  "frames",
  "pixels",
]);

const writers = new Map<string, RuntimeLogSink>();

export const isRuntimeLogProc = (value: unknown): value is RuntimeLogProc =>
  typeof value === "string" && (RUNTIME_LOG_PROCS as readonly string[]).includes(value);

export const isRuntimeLogLevel = (value: unknown): value is RuntimeLogLevel =>
  typeof value === "string" && (RUNTIME_LOG_LEVELS as readonly string[]).includes(value);

export const resolveRuntimeLogDirectory = (dir?: string): string => {
  if (typeof dir === "string" && dir.length > 0) return dir;
  const rundir = process.env.OMI_DEV_STACK_RUNDIR;
  return join(
    typeof rundir === "string" && rundir.length > 0 ? rundir : DEFAULT_RUNDIR,
    "logs",
  );
};

export const runtimeLogPath = (proc: RuntimeLogProc, dir?: string): string =>
  join(resolveRuntimeLogDirectory(dir), RUNTIME_LOG_FILES[proc]);

export const sanitizeRuntimeLogText = (input: string, redactions: readonly string[] = []): string => {
  let safe = input;
  for (const value of redactions.filter((item) => item.length > 0)) {
    safe = safe.split(value).join("[redacted]");
  }
  return safe
    .replace(/https?:\/\/[^\s)'"\]]+/gu, "[redacted-origin]")
    .replace(/(authorization:\s*bearer\s+)[^\s]+/giu, "$1[redacted]")
    .replace(/(\bOMI_API_TOKEN\s*=\s*)[^\s]+/gu, "$1[redacted]")
    .replace(/((?:dev[\s_-]*)?token\s*[:=]\s*)[^\s]+/giu, "$1[redacted]")
    .replace(/\bBearer\s+[^\s"]+/giu, "Bearer [redacted]");
};

const clip = (value: string, max = MAX_STRING_CHARS): string =>
  value.length <= max ? value : value.slice(0, max);

const isForbiddenKey = (key: string): boolean =>
  FORBIDDEN_EXACT.has(key) || FORBIDDEN_KEY.test(key);

const asScalar = (value: unknown): RuntimeLogScalar | undefined => {
  if (value === null) return null;
  if (typeof value === "boolean") return value;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") return clip(sanitizeRuntimeLogText(value));
  return undefined;
};

export const normalizeRuntimeLogRecord = (input: RuntimeLogInput, nowIso: () => string): RuntimeLogRecord | null => {
  if (!isRuntimeLogProc(input.proc) || !isRuntimeLogLevel(input.level)) return null;
  if (typeof input.event !== "string" || !EVENT_SLUG.test(input.event)) return null;
  const record: Record<string, RuntimeLogValue> = {
    ts: typeof input.ts === "string" && input.ts.length > 0 ? clip(input.ts, 40) : nowIso(),
    proc: input.proc,
    level: input.level,
    event: clip(input.event, MAX_EVENT_CHARS),
  };
  for (const [key, value] of Object.entries(input)) {
    if (key === "ts" || key === "proc" || key === "level" || key === "event" || key === "dir") continue;
    if (isForbiddenKey(key) || value === undefined) continue;
    if (Array.isArray(value)) {
      const items: string[] = [];
      for (const item of value) {
        if (typeof item !== "string" || items.length >= MAX_ARRAY_LENGTH) continue;
        items.push(clip(sanitizeRuntimeLogText(item), 64));
      }
      record[key] = Object.freeze(items);
      continue;
    }
    const scalar = asScalar(value);
    if (scalar !== undefined) record[key] = scalar;
  }
  return record as RuntimeLogRecord;
};

const encodeLine = (record: RuntimeLogRecord): string =>
  `${sanitizeRuntimeLogText(JSON.stringify(record))}\n`;

const fallbackWrite = (
  line: string,
  reason: string,
  onFallback: RuntimeLogSinkOptions["onFallback"],
): void => {
  try {
    if (onFallback) {
      onFallback(line, reason);
      return;
    }
    process.stderr.write(`omi runtime-log: ${reason}\n${line}`);
  } catch {
    // Logging must never throw.
  }
};

export const createRuntimeLogSink = (options: RuntimeLogSinkOptions): RuntimeLogSink => {
  const dir = resolveRuntimeLogDirectory(options.dir);
  const path = join(dir, RUNTIME_LOG_FILES[options.proc]);
  const maxBytes = Number.isSafeInteger(options.maxBytes) && (options.maxBytes ?? 0) > 0
    ? options.maxBytes as number
    : DEFAULT_RUNTIME_LOG_MAX_BYTES;
  const nowIso = options.nowIso ?? (() => new Date().toISOString());
  let warned = false;
  let prepared = false;

  const fail = (line: string, reason: string): void => {
    if (!warned) {
      warned = true;
      fallbackWrite("", `cannot write ${path} (${reason}); logging to stderr`, options.onFallback);
    }
    fallbackWrite(line, reason, options.onFallback);
  };

  const prepare = (): boolean => {
    if (prepared) return true;
    try {
      mkdirSync(dir, { recursive: true });
      prepared = true;
      return true;
    } catch (error) {
      fail("", error instanceof Error ? error.message : "mkdir failed");
      return false;
    }
  };

  const rotateIfNeeded = (lineBytes: number): boolean => {
    try {
      const size = statSync(path).size;
      if (size + lineBytes <= maxBytes) return true;
      renameSync(path, `${path}.1`);
      return true;
    } catch (error) {
      const code = error instanceof Error && "code" in error
        ? (error as NodeJS.ErrnoException).code
        : undefined;
      if (code === "ENOENT") return true;
      fail("", error instanceof Error ? error.message : "rotate failed");
      return false;
    }
  };

  return Object.freeze({
    write(input: RuntimeLogInput): void {
      try {
        const record = normalizeRuntimeLogRecord({ ...input, proc: options.proc }, nowIso);
        if (record === null) return;
        const line = encodeLine(record);
        if (!prepare() || !rotateIfNeeded(Buffer.byteLength(line))) {
          fallbackWrite(line, "write skipped", options.onFallback);
          return;
        }
        try {
          appendFileSync(path, line, { encoding: "utf8", mode: 0o600 });
        } catch {
          try {
            writeFileSync(path, line, { encoding: "utf8", flag: "a", mode: 0o600 });
          } catch (error) {
            fail(line, error instanceof Error ? error.message : "append failed");
          }
        }
      } catch (error) {
        fallbackWrite(
          "",
          error instanceof Error ? error.message : "log failed",
          options.onFallback,
        );
      }
    },
  });
};

export const runtimeLogSink = (proc: RuntimeLogProc, dir?: string): RuntimeLogSink => {
  const resolved = resolveRuntimeLogDirectory(dir);
  const key = `${resolved}\0${proc}`;
  const existing = writers.get(key);
  if (existing !== undefined) return existing;
  const created = createRuntimeLogSink({ proc, dir: resolved });
  writers.set(key, created);
  return created;
};

export const appendRuntimeLog = (input: RuntimeLogInput & { readonly dir?: string }): void => {
  const { dir, ...event } = input;
  runtimeLogSink(event.proc, typeof dir === "string" ? dir : undefined).write(event);
};

const flag = (argv: readonly string[], name: string): string | null => {
  const index = argv.indexOf(name);
  return index === -1 ? null : argv[index + 1] ?? null;
};

const runCli = (argv: readonly string[]): number => {
  if (!argv.includes("--append")) {
    process.stderr.write("usage: runtime-log.ts --append --proc <proc> --level <level> --event <slug> [--dir <path>] [--field k=v]...\n");
    return 2;
  }
  const proc = flag(argv, "--proc");
  const level = flag(argv, "--level");
  const event = flag(argv, "--event");
  if (!isRuntimeLogProc(proc) || !isRuntimeLogLevel(level) || typeof event !== "string") {
    process.stderr.write("runtime-log.ts: --proc, --level, and --event are required\n");
    return 2;
  }
  const fields: Record<string, string> = {};
  for (const [index, token] of argv.entries()) {
    if (token !== "--field" && token !== "--reason") continue;
    const raw = argv[index + 1];
    if (typeof raw !== "string") continue;
    if (token === "--reason") {
      fields.reason = raw;
      continue;
    }
    const split = raw.indexOf("=");
    if (split < 1) continue;
    fields[raw.slice(0, split)] = raw.slice(split + 1);
  }
  appendRuntimeLog({
    proc,
    level,
    event,
    ...(flag(argv, "--dir") === null ? {} : { dir: flag(argv, "--dir") as string }),
    ...fields,
  });
  return 0;
};

if (import.meta.main) {
  process.exit(runCli(process.argv.slice(2)));
}
