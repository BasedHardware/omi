import { appendFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";

export type DevStackLogProc = "chat" | "gateway";
export type DevStackLogLevel = "info" | "warn" | "error";
export type DevStackLogFields = Readonly<Record<string, unknown>>;

export const DEFAULT_DEV_STACK_RUNDIR = "/tmp/omi-dev-stack";

const FORBIDDEN_FIELD = /^(?:authorization|headers|body|content|prompt|message|messages|text|api[_-]?key|bearer|token|password|secret|credential|jwt)$/iu;
const SECRET_KEY = /(?:^|[^a-z0-9])(?:authorization|api[_-]?key|bearer|token|password|secret|credential|jwt)(?:[^a-z0-9]|$)/iu;
const SECRET_VALUE = /(?:sk-[A-Za-z0-9]+|Bearer\s+\S+|api[_-]?key\s*[:=]\s*\S+)/u;
const SAFE_EVENT = /^[a-z][a-z0-9_]{0,63}$/u;

export const resolveDevStackLogDir = (runDir = process.env.OMI_DEV_STACK_RUNDIR): string => {
  const root = typeof runDir === "string" && runDir.trim().length > 0
    ? runDir.trim()
    : DEFAULT_DEV_STACK_RUNDIR;
  return join(root, "logs");
};

const sanitize = (fields: DevStackLogFields): Record<string, unknown> => {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(fields)) {
    if (FORBIDDEN_FIELD.test(key) || SECRET_KEY.test(key)) continue;
    if (typeof value === "string" && SECRET_VALUE.test(value)) continue;
    if (value !== null && typeof value === "object") continue;
    if (typeof value === "string" && value.length > 256) {
      out[key] = value.slice(0, 256);
      continue;
    }
    out[key] = value;
  }
  return out;
};

export const appendDevStackLog = (
  proc: DevStackLogProc,
  level: DevStackLogLevel,
  event: string,
  fields: DevStackLogFields = {},
  options?: {
    readonly now?: () => Date;
    readonly write?: (path: string, line: string) => void;
    readonly runDir?: string;
  },
): void => {
  try {
    if (proc !== "chat" && proc !== "gateway") return;
    if (level !== "info" && level !== "warn" && level !== "error") return;
    if (!SAFE_EVENT.test(event)) return;
    const record = Object.freeze({
      ts: (options?.now ?? (() => new Date()))().toISOString(),
      proc,
      level,
      event,
      ...sanitize(fields),
    });
    const line = `${JSON.stringify(record)}\n`;
    const path = join(resolveDevStackLogDir(options?.runDir), `${proc}.jsonl`);
    if (options?.write !== undefined) {
      options.write(path, line);
      return;
    }
    mkdirSync(resolveDevStackLogDir(options?.runDir), { recursive: true });
    appendFileSync(path, line, "utf8");
  } catch {
    // Observability must never change generation admission or completion.
  }
};

export const chatLog = (
  level: DevStackLogLevel,
  event: string,
  fields: DevStackLogFields = {},
): void => appendDevStackLog("chat", level, event, fields);

export const gatewayLog = (
  level: DevStackLogLevel,
  event: string,
  fields: DevStackLogFields = {},
): void => appendDevStackLog("gateway", level, event, fields);

export const logLineHasSecret = (line: string, needles: readonly string[]): boolean => {
  if (SECRET_VALUE.test(line)) return true;
  return needles.some((needle) => needle.length > 0 && line.includes(needle));
};
