/**
 * The PLATFORM TASKS OP-SENDER — the client half of `POST /v1/tasks/ops`
 * bound to the durable outbox, dark.
 *
 * `write-ops.ts` owns the two pure pieces of this wire (build an envelope,
 * classify a response). This file is the binding that drains journaled ops
 * through them: it is to `write-ops.ts` what `tasksTransport` in
 * `adapters-legacy` is to `sendTaskOp`. Tasks is the first — and today the
 * only — writable domain (COORD-write-path-rulings B6).
 *
 * ── WHAT THIS SENDER DELIBERATELY CANNOT DO ────────────────────────────────
 *
 * It cannot MINT a write id and it cannot STAMP an account epoch. Both are
 * read off the journaled op and neither has a fallback here. That is B1 made
 * structural: a send-time mint yields a different id on every replay, so the
 * server's registry never recognises the retry and a crash-replayed op applies
 * twice; a send-time epoch stamp re-dates an op into whatever generation is
 * current, which is exactly the straggler the account-epoch fence exists to
 * refuse. The stamps are taken once, at enqueue, by `@omi-core/sync`'s
 * `WriteStampSource`, in the same statement that appends to the journal.
 *
 * ── WHY A CLIENT-SIDE DEFECT IS `retryable`, NOT `permanent` ───────────────
 *
 * Every "we could not build the envelope" branch below reports
 * `retryable { unclassified: true }`. It looks generous — the op will retry a
 * request that cannot succeed until the client is fixed — and it is
 * deliberate. `permanent` DEAD-LETTERS the op, and dead-lettering is a
 * statement to a person that their edit will never be applied. When the cause
 * is our own composition bug, that statement is both false and destructive:
 * the edit becomes recoverable-by-hand-only for a defect a shipped fix would
 * have drained on its own. `contracts/src/errors.ts` prescribes exactly this —
 * an adapter that cannot classify reports `retryable` with `unclassified`, so
 * the fallback sink shows the taxonomy gap instead of a silent guess.
 *
 * ── W1: `control_unavailable` IS NOT A REFUSAL AND IS NEVER A DEAD LETTER ──
 *
 * `COORD-fable-rulings-wave2` W1 signed the fifth value because it carries a
 * client behaviour a bare 503 cannot instruct: **refresh control state, then
 * drain the op wherever authority actually lives.** After a rollback
 * (`backend:ADR-007` §6) authority is legacy's again, so an op retried in
 * place goes to a platform that can never say yes for the length of the
 * incident, while its real home is the other generation. This sender does the
 * one thing it is entitled to do about that — it tells the control binding, by
 * name, that a refresh is needed — and reports a failure kind that KEEPS the
 * op queued. It never maps the signal onto `stale_epoch`, which would make the
 * client permanently discard an op it should simply resend.
 */

import type { HttpClient, HttpResponse, TaskOp, WriteFailure } from "@omi-core/contracts";
import type { PendingOp, Transport, WriteStampSource } from "@omi-core/sync";
import {
  WRITE_ID_ENTROPY_BYTES,
  isTrustedWriteAccepted,
  mintWriteId,
  type WriteOp,
} from "@omi-core/ratified-contracts/write/ops";

import type { AccountEpochProvider } from "./account-epoch.js";
import { buildWriteOpEnvelope, classifyWriteOpsResponse, isControlUnavailable } from "./write-ops.js";

/**
 * 32 bytes of independent entropy, supplied by the shell.
 *
 * The ratified module takes entropy as a parameter and says why: a contract
 * that minted its own randomness would make every conformance run
 * irreproducible, and this package has no I/O. A shell binds
 * `crypto.getRandomValues`; a test binds a counter.
 */
export type WriteEntropySource = () => Uint8Array;

export interface PlatformWriteStampOptions {
  readonly entropy: WriteEntropySource;
  readonly epochs: AccountEpochProvider;
}

/**
 * Compose the outbox's stamp port from the two things only a binding has: an
 * entropy source and the account's epoch.
 *
 * `mintWriteId` returns `null` for a short or non-byte read rather than
 * silently shrinking the key space, and this preserves that `null` all the way
 * to the outbox, which refuses to journal rather than acknowledging a write it
 * could never send. A thrown entropy source is caught and reported the same
 * way, because "the shell's RNG threw" and "the shell's RNG returned 31 bytes"
 * are the same fact to everything downstream.
 */
export function createPlatformWriteStamps(options: PlatformWriteStampOptions): WriteStampSource {
  return {
    mintWriteId: (): string | null => {
      let bytes: Uint8Array;
      try {
        bytes = options.entropy();
      } catch {
        return null;
      }
      return mintWriteId(bytes);
    },
    currentAccountEpoch: () => options.epochs.currentAccountEpoch(),
  };
}

/**
 * The journaled client op → the ratified wire op.
 *
 * WHAT IS AND IS NOT DECIDED HERE. `FABLE-overnight-scope-rulings` R6 is
 * explicit: 0.5.0's `create.content` and `patch.patch` are OPAQUE field bags,
 * the server applies them opaquely with revision tracking and claims nothing
 * about field meaning, and **no ruling exists on task field vocabulary**. So
 * this function is not agreeing a vocabulary with the server — there is
 * nothing to agree with tonight. It carries the client's own ratified domain
 * field names (`contracts/src/domain/tasks.ts`) into the bag unchanged, which
 * is the only choice that invents no third spelling. When field semantics are
 * ratified, this is the one place the mapping lives; if the serving side ever
 * spells a bag key differently, the standing precedence rule gives it the
 * spelling and the reversal is a rename in this function.
 *
 * The client-private `opId` deliberately does NOT cross: `write_id` is the
 * idempotency key on this wire (B1), and `backend:RISK-015` keeps word slugs
 * off a shared contract. `at` does not cross either — the server timestamps
 * what it applies; a client clock is not evidence.
 *
 * Returns `null` for anything that is not a well-formed journaled `TaskOp`,
 * so the caller reports a client-side gap rather than shipping a malformed
 * envelope the server would answer with `invalid_envelope`.
 */
export function taskOpToWriteOp(domainOp: TaskOp): WriteOp | null {
  if (typeof domainOp !== "object" || domainOp === null) return null;
  if (typeof (domainOp as { id?: unknown }).id !== "string" || domainOp.id === "") return null;
  switch (domainOp.op) {
    case "create": {
      if (typeof domainOp.description !== "string") return null;
      const content: Record<string, unknown> = { description: domainOp.description, source: domainOp.source };
      if (domainOp.dueAt !== undefined) content["dueAt"] = domainOp.dueAt;
      return { op: "create", record_id: domainOp.id, content };
    }
    case "patch": {
      if (typeof domainOp.patch !== "object" || domainOp.patch === null) return null;
      // The keyed-patch guarantee is the whole point of the domain contract:
      // an absent key means "leave unchanged", never "reset to default". It
      // survives this mapping only if absent keys stay absent, so the bag is
      // built from the patch's own keys and never from a field list.
      return { op: "patch", record_id: domainOp.id, patch: { ...domainOp.patch } };
    }
    case "delete":
      return { op: "delete", record_id: domainOp.id };
    default:
      return null;
  }
}

export interface PlatformTasksOpSenderOptions {
  /**
   * The contracts-native transport. It SHOULD supply `HttpResponse.text`; see
   * `sendPlatformTaskOp` for what happens when it does not, and why that is
   * not a detail.
   */
  readonly http: HttpClient;
  /**
   * W1's client behaviour, named by the binding that owns `backend:ADR-007`'s
   * control path. Required, not optional: an optional hook is one a binding
   * forgets, and the way it fails is a rollback that silently becomes a
   * retry-forever loop against a server that can never accept the op.
   */
  readonly onControlUnavailable: (op: PendingOp) => void;
}

export type PlatformWriteSendResult =
  | { readonly ok: true; readonly serverRevision?: string }
  | { readonly ok: false; readonly failure: WriteFailure };

const unclassified = (detail: string): PlatformWriteSendResult => ({
  ok: false,
  failure: { kind: "retryable", unclassified: true, detail },
});

/**
 * Send ONE journaled op over the ratified write wire.
 *
 * THE `text` REQUIREMENT IS LOAD-BEARING, not defensive plumbing. Two refusal
 * classes share HTTP 409 — `stale_epoch` and `conflict` — and they are
 * distinguished by body bytes and never by status. A binding that hands over
 * only a pre-parsed `json` leaves `classifyWriteOpsResponse` with nothing to
 * read, so it falls through to the status taxonomy and 409 becomes
 * `permanent/conflict`: a straggler reported to a person as "another edit won
 * a race", about an edit where nothing raced. That is the false report B2
 * forbids by name. So a write response with no raw body is not classified at
 * all — it is reported as an unclassified gap, which keeps the op and makes
 * the binding defect visible, instead of guessing the one wrong answer.
 */
export async function sendPlatformTaskOp(
  options: PlatformTasksOpSenderOptions,
  journaled: PendingOp,
): Promise<PlatformWriteSendResult> {
  if (journaled.accountEpoch === undefined) {
    return unclassified(`platform write op ${journaled.opId} was journaled without an account epoch`);
  }

  let domainOp: TaskOp;
  try {
    domainOp = JSON.parse(journaled.payload) as TaskOp;
  } catch {
    return unclassified(`platform write op ${journaled.opId} has an unparseable journaled payload`);
  }
  const op = taskOpToWriteOp(domainOp);
  if (op === null) {
    return unclassified(`platform write op ${journaled.opId} is not a well-formed task op`);
  }

  const built = buildWriteOpEnvelope(
    { domain: journaled.domain, ...(journaled.writeId === undefined ? {} : { writeId: journaled.writeId }), op },
    journaled.accountEpoch,
  );
  if (!built.ok) {
    return unclassified(`platform write op ${journaled.opId} is unsendable: ${built.failure.reason}`);
  }

  let response: HttpResponse;
  try {
    response = await options.http.request("POST", built.path, built.envelope);
  } catch (error) {
    return { ok: false, failure: { kind: "retryable", detail: `platform write transport: ${String(error)}` } };
  }

  const detail = `${journaled.domain}/${journaled.recordId}`;

  if (response.status === 200) {
    if (!isTrustedWriteAccepted(response.json)) {
      // A 200 whose body is not `WriteAccepted` may well have applied. Saying
      // "confirmed" on a body we cannot read would be the false-confirm class;
      // retrying is safe precisely because the registry is keyed on the
      // journaled `write_id`, so the replay is answered idempotently.
      return unclassified(`platform write accepted an op with an unreadable body: ${detail}`);
    }
    const revision = response.json.applied.revision;
    return revision === null ? { ok: true } : { ok: true, serverRevision: revision };
  }

  if (response.text === undefined) {
    return unclassified(`platform write response ${response.status} carried no raw body: ${detail}`);
  }

  if (isControlUnavailable(response)) {
    // W1. Tell the control binding, keep the op, never dead-letter it, and
    // never let it reach `stale_epoch`'s permanent arm.
    options.onControlUnavailable(journaled);
    return { ok: false, failure: { kind: "retryable", detail: `control unavailable: ${detail}` } };
  }

  const failure = classifyWriteOpsResponse(response, detail);
  if (failure === null) {
    // `classifyWriteOpsResponse` returns null only for 200, which is handled
    // above. Reaching here means the two disagree about what success is.
    return unclassified(`platform write status ${response.status} classified as success: ${detail}`);
  }
  return { ok: false, failure };
}

/**
 * Bind the op-sender to `@omi-core/sync`'s `Transport`, which is what an
 * `Outbox` drains through.
 *
 * There is deliberately no store here. `openTasks()` stays legacy tonight
 * (FABLE-wave3-review-rulings R7) and the platform tasks READ store is another
 * lane's seam; a second construction site for the same domain ports is the
 * two-doors defect rule 16 exists to prevent. This exports the transport and
 * the stamps, and the composition — `Outbox.open(bridge, env, transport,
 * "tasks", stamps)` — is one line at whichever binding owns the queue.
 */
export function platformTasksTransport(options: PlatformTasksOpSenderOptions): Transport {
  return { send: (op: PendingOp) => sendPlatformTaskOp(options, op) };
}

/** Re-exported so a shell binding can size its entropy buffer from one place. */
export { WRITE_ID_ENTROPY_BYTES };
