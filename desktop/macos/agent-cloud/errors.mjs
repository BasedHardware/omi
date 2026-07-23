// Two-plane error handling for the VM agent.
//
// Contract (2026-07-22 design, from the claude-code withRetry/errors port):
// every catch site classifies first; the category decides what the USER event
// says (fixed calm copy, never raw detail) and whether we retry. The raw error
// always goes to the INTERNAL plane whole (structured JSON line on stdout —
// journald captures it; no new sink).

/** Bounded category set — the cross-language contract (mirrored in Python). */
export const ERROR_CATEGORIES = /** @type {const} */ ([
  "transient",
  "auth",
  "invalid_request",
  "unavailable",
  "aborted",
  "interrupted",
  "internal",
]);

/** Fixed user-plane copy per category. Never interpolate error text into these. */
export const USER_MESSAGES = {
  transient: "Taking longer than usual — retrying…",
  transient_final: "The AI service didn't respond after several tries. Please try again in a moment.",
  auth: "Please reconnect your account in Settings, then try again.",
  invalid_request: "That request couldn't be processed. Try rephrasing or removing large attachments.",
  unavailable: "Your agent is starting up — one moment.",
  aborted: "Stopped.",
  interrupted: "Stopped.",
  internal: "Something went wrong on our side.",
};

const TRANSIENT_RE =
  /\b(429|529|50[0234]|rate.?limit|overloaded|timeout|timed out|ETIMEDOUT|ECONNRESET|ECONNREFUSED|EPIPE|ENOTFOUND|EAI_AGAIN|socket hang up|fetch failed)\b/i;
const AUTH_RE = /\b(401|403|invalid_token|authentication|unauthorized|forbidden|token expired|revoked)\b/i;
const INVALID_RE = /\b(400|413|422|invalid_request|length limit exceeded|too large)\b/i;

export function classifyError(err) {
  const msg = `${err?.name ?? ""} ${err?.message ?? String(err)} ${err?.code ?? ""}`;
  if (isAbortShaped(err)) return { category: isExpectedAbort(err) ? "aborted" : "internal", retryable: false };
  if (AUTH_RE.test(msg)) return { category: "auth", retryable: false };
  if (TRANSIENT_RE.test(msg)) return { category: "transient", retryable: true };
  if (INVALID_RE.test(msg)) return { category: "invalid_request", retryable: false };
  return { category: "internal", retryable: false };
}

// claude-code's getRetryDelay: base 500ms, x2 per attempt, cap 32s, 25% jitter.
export function retryDelayMs(attempt, random = Math.random) {
  const base = Math.min(500 * 2 ** Math.max(0, attempt - 1), 32_000);
  return Math.round(base * (1 + (random() - 0.5) * 0.5));
}

/**
 * Foreground retry loop: retries `transient` only, honors an abort signal,
 * reports each retry so callers can surface progress to the user plane.
 * Background work must NOT use this — fail fast instead (retry-by-visibility).
 */
export async function withRetry(fn, { attempts = 3, signal, onRetry } = {}) {
  let lastErr;
  for (let attempt = 1; attempt <= attempts; attempt++) {
    if (signal?.aborted) throw lastErr ?? new Error("aborted before attempt");
    try {
      return await fn(attempt);
    } catch (err) {
      lastErr = err;
      const { retryable } = classifyError(err);
      if (!retryable || attempt === attempts) throw err;
      const delay = retryDelayMs(attempt);
      onRetry?.(err, attempt, delay);
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }
  throw lastErr;
}

// --- Owned aborts -----------------------------------------------------------
// We control every cancellation in this process (query.interrupt / our
// AbortControllers). The SDK's abort rejections don't carry the originating
// signal, so exact attribution is impossible from outside.
// ponytail: time-boxed grace window, not per-signal tracking; upgrade path is
// a per-turn flag cleared on `result`.
const ABORT_GRACE_MS = 5000;
let ownedAbortUntil = 0;

export function markOwnedAbort(now = Date.now()) {
  ownedAbortUntil = now + ABORT_GRACE_MS;
}

export function isAbortShaped(err) {
  return err?.name === "AbortError" || /\baborted\b/i.test(err?.message ?? "");
}

export function isExpectedAbort(err, now = Date.now()) {
  return isAbortShaped(err) && now < ownedAbortUntil;
}

// --- Internal plane ---------------------------------------------------------

/** One structured JSON line per event; maximum detail, never truncated. */
export function logEvent(level, event, fields = {}, write = (line) => console.log(line)) {
  const record = { ts: new Date().toISOString(), level, event, ...fields };
  if (fields.error instanceof Error) {
    const err = fields.error;
    record.error = {
      name: err.name,
      message: err.message,
      stack: err.stack,
      ...Object.fromEntries(Object.getOwnPropertyNames(err).map((k) => [k, err[k]])),
    };
  }
  try {
    write(JSON.stringify(record));
  } catch {
    // A circular reference (e.g. a socket on err.cause) must not turn a logged
    // error into a fresh unhandled one — logEvent runs inside catch blocks and
    // the unhandledRejection handler.
    write(JSON.stringify({ ts: record.ts, level, event, log_error: "record not serializable" }));
  }
}
