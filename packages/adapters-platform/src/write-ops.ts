/**
 * The client half of `POST /v1/{domain}/ops` — COORD-write-path-rulings.
 *
 * This module owns exactly two things, and deliberately nothing else:
 *
 *   1. building the wire envelope from a journaled `PendingOp`, and
 *   2. turning a write response into the client's `WriteFailure` taxonomy.
 *
 * WHY (2) IS NOT `classifyStatus`. `@omi-core/kernel`'s `classifyStatus` is
 * "the one place an HTTP status becomes taxonomy", and it stays that. But the
 * write route deliberately puts TWO outcome classes on 409 (`stale_epoch` and
 * `conflict`) and two on 403 (`authorization` and `entitlement`), because
 * `backend:ADR-010` §3 requires a write refusal to distinguish class while
 * still never leaking inner reason. A status-only classifier therefore cannot
 * tell them apart, and the way it fails is specific and bad:
 *
 *     409 stale_epoch  ->  classifyStatus  ->  permanent/conflict
 *
 * which is a dead letter telling a person their saved edit conflicted, when in
 * fact the server refused an op authored in a superseded account generation.
 * That is a false report about a user's own content, and B2 rules it out by
 * name. So this function reads the refusal CLASS off the body first, and falls
 * through to `classifyStatus` for everything the write contract does not
 * define. It adds a mapping above the status taxonomy; it does not fork it.
 *
 * WHAT THIS MODULE DOES NOT DO. It does not decide whether an epoch is stale.
 * That is the server-owned account-control projection (`backend:ADR-010`),
 * which is landing separately; there is one epoch mechanism and it is not
 * here. This module only reads the fence's answer off the wire.
 */

import type { HttpResponse, WriteFailure } from "@omi-core/contracts";
import { classifyStatus } from "@omi-core/kernel";
import {
  isWritableDomain,
  parseWriteId,
  readWriteRefusalOutcome,
  writeOpsPath,
  type WritableDomain,
  type WriteOp,
  type WriteOpEnvelope,
} from "@omi-core/ratified-contracts/write/ops";

/**
 * The subset of the outbox's journaled op this adapter needs. Structural on
 * purpose: `@omi-core/sync`'s `PendingOp` is client-private and must not
 * become a dependency of the wire-facing adapter, which is the same
 * separation that keeps the word-slug `opId` off the wire (backend:RISK-015).
 */
export interface JournaledWriteOp {
  readonly domain: string;
  /**
   * B1. The write id MINTED when the op was enqueued and journaled WITH it.
   * Optional in the type only because journals written before this field
   * existed have none — see `buildWriteOpEnvelope`, which refuses those rather
   * than minting a replacement.
   */
  readonly writeId?: string;
  readonly op: WriteOp;
}

export type EnvelopeBuildFailure =
  | { readonly reason: "no-journaled-write-id" }
  | { readonly reason: "unwritable-domain"; readonly domain: string }
  | { readonly reason: "malformed-write-id" };

export type EnvelopeBuild =
  | { readonly ok: true; readonly path: string; readonly envelope: WriteOpEnvelope }
  | { readonly ok: false; readonly failure: EnvelopeBuildFailure };

/**
 * B1, made structural rather than cultural.
 *
 * An op with no journaled `writeId` CANNOT be sent. The obvious convenience —
 * mint one here, at send time — is the exact bug the ruling rejects: a
 * send-time mint produces a different id on every replay, so the server's
 * dedupe registry never recognises the retry and a crash-replayed op applies
 * twice. Deriving one from the op's content has the same defect in a subtler
 * form. There is no correct thing to do here except refuse, so this refuses,
 * and the refusal is a value the caller must handle rather than a silent
 * fallback.
 */
export function buildWriteOpEnvelope(
  journaled: JournaledWriteOp,
  accountEpoch: number,
): EnvelopeBuild {
  if (journaled.writeId === undefined) {
    return { ok: false, failure: { reason: "no-journaled-write-id" } };
  }
  if (parseWriteId(journaled.writeId) === null) {
    return { ok: false, failure: { reason: "malformed-write-id" } };
  }
  if (!isWritableDomain(journaled.domain)) {
    return { ok: false, failure: { reason: "unwritable-domain", domain: journaled.domain } };
  }
  const domain: WritableDomain = journaled.domain;
  return {
    ok: true,
    path: writeOpsPath(domain),
    envelope: {
      write_id: journaled.writeId,
      account_epoch: accountEpoch,
      domain,
      op: journaled.op,
    },
  };
}

/**
 * Turn a write-ops response into the client taxonomy.
 *
 * `detail` is diagnostic text for the dead-letter surface. It never carries a
 * server-supplied string: the refusal bodies are fixed and contain no reason,
 * and inventing detail from them would manufacture specificity the wire
 * deliberately withholds.
 */
export function classifyWriteOpsResponse(response: HttpResponse, detail: string): WriteFailure | null {
  if (response.status === 200) return null;

  const body = response.text;
  const outcome = body === undefined ? null : readWriteRefusalOutcome(response.status, body);
  switch (outcome) {
    case "authentication":
      // The outbox PAUSES, never drops. Re-auth then replays under the same
      // journaled write_id, which the registry recognises.
      return { kind: "auth-invalid", detail };
    case "authorization":
      // Also auth-invalid: from the client's side an authorization refusal and
      // an authentication refusal are the same instruction — stop, re-establish
      // identity, replay. Which of the two it was is server-internal, and the
      // wire keeps them separate only so the SERVER's outcome record is honest.
      return { kind: "auth-invalid", detail };
    case "entitlement":
      return { kind: "permanent", reason: "entitlement", detail };
    case "stale_epoch":
      // B2. Never `conflict`. Never `gone`.
      return { kind: "permanent", reason: "stale_epoch", detail };
    case null:
      break;
  }

  // Not a refusal class. `write_id_reuse` is a 409 that means the adapter
  // laundered two different ops through one key — a client defect, permanent,
  // and specifically NOT a conflict: nothing raced.
  if (body !== undefined && response.status === 409 && body === '{"error":"write_id_reuse"}') {
    return { kind: "permanent", reason: "validation", detail };
  }
  // 503 maintenance is backpressure. `classifyStatus` already maps 5xx to
  // retryable, which is correct here; the surface-level maintenance notice is
  // a separate concern owned by the shell (ADR-007), not a taxonomy kind.
  return classifyStatus(response, detail);
}
