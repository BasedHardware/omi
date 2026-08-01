import { appendFileSync, chmodSync, closeSync, lstatSync, mkdirSync, openSync, unlinkSync } from "fs";
import { homedir } from "os";
import { dirname, join } from "path";
import { sanitizeProcessDiagnostic } from "./failures.js";

/**
 * Write to ~/Library/Logs/Omi/agent-crash.log as fallback when stderr might be lost.
 * Hard-capped at CRASH_LOG_MAX_LINES per process to prevent runaway disk
 * fill (we shipped a build that wrote 100s of GBs into this file in a tight
 * EPIPE re-entry loop).
 */
const CRASH_LOG_MAX_LINES = 100;

export function crashLogPath(home: string = homedir()): string {
  return join(home, "Library", "Logs", "Omi", "agent-crash.log");
}

export const CRASH_LOG_PATH = crashLogPath();

let crashLogLineCount = 0;

export function ensureCrashLogOwnerOnly(path: string): boolean {
  try {
    mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
    let existing: ReturnType<typeof lstatSync> | null = null;
    try {
      existing = lstatSync(path);
    } catch (err) {
      if ((err as NodeJS.ErrnoException).code !== "ENOENT") return false;
    }
    if (existing) {
      const ownerUid = process.getuid?.();
      if (existing.isFile() && ownerUid !== undefined && existing.uid === ownerUid) {
        chmodSync(path, 0o600);
        return true;
      }
      unlinkSync(path);
    }
    closeSync(openSync(path, "a", 0o600));
    return true;
  } catch {
    return false;
  }
}

export function logCrashTo(path: string, msg: string): void {
  try {
    if (!ensureCrashLogOwnerOnly(path)) return;
    const ts = new Date().toISOString();
    appendFileSync(path, `[${ts}] ${sanitizeProcessDiagnostic(msg)}\n`, { mode: 0o600 });
  } catch {
    // ignore
  }
}

export function logCrash(msg: string): void {
  if (crashLogLineCount >= CRASH_LOG_MAX_LINES) return;
  crashLogLineCount += 1;
  logCrashTo(CRASH_LOG_PATH, msg);
}
