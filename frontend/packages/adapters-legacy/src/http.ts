/**
 * The injected HTTP seam. Shells bind this to their privileged transport
 * (bridge on mobile/macOS, net module on Windows); tests bind a script.
 * Adapters never construct absolute URLs or touch tokens — auth is the
 * transport binding's job (ADR-008 §3 / ADR-009 §3).
 */

export interface HttpResponse {
  status: number;
  /** Parsed JSON body, or null when the body was empty/unparseable. */
  json: unknown;
  /** Retry-After in milliseconds when the server sent one. */
  retryAfterMs?: number;
}

export interface HttpClient {
  request(method: "GET" | "POST" | "PATCH" | "DELETE", path: string, body?: unknown): Promise<HttpResponse>;
}

import type { WriteFailure } from "@omi-core/contracts";

/**
 * The one place legacy HTTP statuses become taxonomy. Adapters call this and
 * never invent their own mapping — a status this function does not know is
 * `retryable { unclassified: true }`, which telemetry surfaces as a taxonomy
 * gap instead of a silent guess.
 */
export function classifyStatus(res: HttpResponse, detail: string): WriteFailure {
  const s = res.status;
  if (s === 401 || s === 403) return { kind: "auth-invalid", detail };
  if (s === 429) return { kind: "rate-limited", retryAfterMs: res.retryAfterMs ?? 30_000, detail };
  if (s === 404 || s === 410) return { kind: "permanent", reason: "gone", detail };
  if (s === 409) return { kind: "permanent", reason: "conflict", detail };
  if (s === 402) return { kind: "permanent", reason: "entitlement", detail };
  if (s === 413) return { kind: "permanent", reason: "oversize", detail };
  if (s === 400 || s === 422) return { kind: "permanent", reason: "validation", detail };
  if (s >= 500 || s === 408) return { kind: "retryable", detail };
  return { kind: "retryable", unclassified: true, detail: `unmapped status ${s}: ${detail}` };
}
