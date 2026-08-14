/**
 * The one place an HTTP status becomes taxonomy.
 *
 * Lives in the kernel rather than in `adapters-legacy` because it is not legacy
 * at all: every transport binding — the privileged bridge, the DEV harness, a
 * future desktop net module — needs the same mapping, and `adapters-legacy` is
 * explicitly the graveyard that gets deleted when the rewritten service lands.
 * It cannot live in `contracts/` either: nothing in contracts executes.
 *
 * Kernel is the right home on the other axis too — this is a pure function of
 * its input, with no clock, no randomness, and no I/O.
 */

import type { HttpResponse, WriteFailure } from "@omi-core/contracts";

/**
 * Adapters and bindings call this and never invent their own mapping — a status
 * this function does not know is `retryable { unclassified: true }`, which
 * telemetry surfaces as a taxonomy gap instead of a silent guess.
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
