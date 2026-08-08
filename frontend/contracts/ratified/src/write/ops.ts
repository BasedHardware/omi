/**
 * The client-facing WRITE wire — `POST /v1/{domain}/ops`.
 *
 * Ratified by `COORD-write-path-rulings` (B1, B2, B4, B5, B6), which decided
 * this shape after the two spikes recorded in `SPIKE-write-path-contract.md`.
 * Nothing here is a proposal; each rule below names the ruling it carries.
 *
 * WHY THIS MODULE EXISTS AT ALL. The client has had a durable offline write
 * queue for a long time, and its durability argument ended in a sentence about
 * the server: "opId idempotency on the server absorbs the replay". No server
 * ever did that. This module is the wire on which that sentence becomes true,
 * and `writeId` is the field that carries it.
 *
 * ── B1. `write_id` is MINTED, never DERIVED ────────────────────────────────
 * 64 lowercase hex, minted from 32 bytes of independent entropy and journaled
 * WITH the op. It is deliberately NOT `sha256(opId)`. Deriving it would make
 * the client's private `opId` *stability* load-bearing for a shared wire, so a
 * journal migration that re-minted opIds would silently reset idempotency —
 * a correctness argument terminating in another component's private behaviour.
 * `mintWriteId` therefore takes entropy as a parameter: this package has no
 * clock, no randomness and no I/O, and the entropy source belongs to the shell.
 *
 * The grammar is fixed hex and belongs to no identifier-legibility scheme, so
 * `backend:RISK-015`'s bar on word slugs in a shared contract is not tripped.
 * `opId` stays client-private and never appears on this wire.
 *
 * ── B2. `stale_epoch` is its OWN refusal outcome ───────────────────────────
 * Four refusal classes, each with a FIXED body: authentication, authorization,
 * entitlement, stale_epoch (`backend:ADR-010` §3). A straggler refused by the
 * account epoch fence is never reported as `conflict` or `gone` — mapping it
 * onto an existing reason tells the user something false about their own edit,
 * which is the failure class this program exists to eliminate.
 *
 * Class is distinguished; inner reason never is. `missing_grant` and
 * `grant_scope_mismatch` produce byte-identical 403s, exactly as the read
 * route already does. No denial reason, exception text, or identifier ever
 * reaches the wire.
 *
 * ── B4. One envelope per request ───────────────────────────────────────────
 * `POST /v1/{domain}/ops`, one op per request. This matches the outbox's
 * one-in-flight drain and keys the server-side dedupe registry uniformly;
 * per-verb REST would multiply idempotency surfaces for nothing.
 *
 * ── B6. Domain-generic ─────────────────────────────────────────────────────
 * Tasks is the first writable domain (Memories is read-only by ratified
 * design). The envelope names its domain rather than hard-coding one, and
 * `WRITABLE_DOMAINS` is the allowlist a new writable domain is added to.
 *
 * ── WHAT THIS MODULE DOES NOT DECIDE ───────────────────────────────────────
 * - **Whether an epoch is stale.** That comparison belongs to the server-owned
 *   account-control projection (`backend:ADR-010`), which is a separate
 *   landing. This module supplies the envelope's `account_epoch` stamp and the
 *   refusal body the fence returns; it does not implement, duplicate, or
 *   approximate the fence. There is exactly one epoch mechanism and it is not
 *   here.
 * - **What a user is TOLD when a stale-epoch dead letter appears.** That copy
 *   is owner-signed and is owed to David; it is deliberately absent. This
 *   module carries the machine-readable outcome only.
 * - **How long a refused straggler envelope is retained server-side.** Also
 *   owner-signed and owed to David (`COORD-write-path-rulings` B3).
 */

import { isPlainJsonDataGraph, parseCanonicalJson } from "../wire/json.js";

declare const WriteIdBrand: unique symbol;

/** A minted, opaque, 64-hex client write identifier. Never derived from `opId`. */
export type WriteId = string & { readonly [WriteIdBrand]: true };

/**
 * The wire grammar. Fixed hex, lowercase, no separators, no scheme — there is
 * nothing in a `write_id` for a reader to interpret, which is the point.
 */
export const WRITE_ID_PATTERN = /^[0-9a-f]{64}$/;

/** Exactly this many bytes of entropy, so a short read cannot silently shrink the key space. */
export const WRITE_ID_ENTROPY_BYTES = 32;

export const MAX_WRITE_ENVELOPE_JSON_CODE_UNITS = 1_000_000;

export function parseWriteId(raw: string): WriteId | null {
  return typeof raw === "string" && WRITE_ID_PATTERN.test(raw) ? (raw as WriteId) : null;
}

/**
 * Hex-encode 32 caller-supplied random bytes into a `WriteId`.
 *
 * Returns `null` rather than throwing on a wrong-length or non-byte input:
 * a caller that got its entropy source wrong must be able to observe that as
 * a value, not as an exception unwinding through a write path.
 *
 * The caller owns the entropy. This package is hermetic by construction, and
 * — more importantly — a contract that minted its own randomness would make
 * every conformance run non-reproducible.
 */
export function mintWriteId(entropy: Uint8Array): WriteId | null {
  if (!(entropy instanceof Uint8Array) || entropy.length !== WRITE_ID_ENTROPY_BYTES) return null;
  let hex = "";
  for (const byte of entropy) {
    if (!Number.isInteger(byte) || byte < 0 || byte > 255) return null;
    hex += byte.toString(16).padStart(2, "0");
  }
  return hex as WriteId;
}

/**
 * Domains that accept client writes. Memories is absent on purpose: it is
 * read-only by ratified design (board PR-2 — propositions are generated, not
 * edited), and an envelope naming it must be refused as validation, not
 * silently applied.
 */
export const WRITABLE_DOMAINS = ["tasks"] as const;
export type WritableDomain = (typeof WRITABLE_DOMAINS)[number];

const WRITABLE_DOMAIN_SET = new Set<unknown>(WRITABLE_DOMAINS);

export function isWritableDomain(value: unknown): value is WritableDomain {
  return WRITABLE_DOMAIN_SET.has(value);
}

/** B4: the one route shape. Built, never hand-spelled at a call site. */
export function writeOpsPath(domain: WritableDomain): string {
  return `/v1/${domain}/ops`;
}

/** Matches any path this route family can produce, for a server-side router assertion. */
export const WRITE_OPS_PATH_PATTERN = /^\/v1\/[a-z][a-z0-9]*(?:-[a-z0-9]+)*\/ops$/;

/**
 * `base_revision` is an OPTIONAL precondition, not the idempotency mechanism.
 *
 * The spike measured why it cannot be the idempotency mechanism: an op that
 * APPLIED, then crashed before its tombstone, then saw an interleaved write
 * from another device, replays as a CONFLICT — a false failure for an
 * operation that succeeded, producing a dead letter that tells the user a
 * saved edit failed. The registry keyed on `write_id` answers that replay
 * idempotently; `base_revision` adds lost-update detection on top and covers
 * the registry's own blind spot (silent last-write-wins). The two are
 * orthogonal and both are needed.
 */
export type WriteOp =
  | { readonly op: "create"; readonly record_id: string; readonly content: Readonly<Record<string, unknown>> }
  | { readonly op: "patch"; readonly record_id: string; readonly patch: Readonly<Record<string, unknown>>; readonly base_revision?: string }
  | { readonly op: "delete"; readonly record_id: string; readonly base_revision?: string };

export interface WriteOpEnvelope {
  /** B1. Minted, journaled with the op, stable across every replay of that op. */
  readonly write_id: string;
  /**
   * The account epoch the op was CREATED under — the straggler stamp. The
   * server compares it against its own account-control projection; this
   * module never does.
   */
  readonly account_epoch: number;
  readonly domain: WritableDomain;
  readonly op: WriteOp;
}

const RECORD_ID_PATTERN = /^[\x21-\x7e]{1,256}$/;
const REVISION_PATTERN = /^[0-9a-f]{64}$/;

const ENVELOPE_KEYS = ["write_id", "account_epoch", "domain", "op"] as const;

function hasExactKeys(value: unknown, expected: readonly string[]): value is Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const actual = Object.keys(value).sort();
  return actual.length === expected.length && [...expected].sort().every((key, index) => key === actual[index]);
}

function isFieldBag(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isWriteOp(value: unknown): value is WriteOp {
  if (!isFieldBag(value)) return false;
  const op = value as Record<string, unknown>;
  if (typeof op["record_id"] !== "string" || !RECORD_ID_PATTERN.test(op["record_id"])) return false;
  const base = op["base_revision"];
  const baseOk = base === undefined || (typeof base === "string" && REVISION_PATTERN.test(base));
  switch (op["op"]) {
    case "create":
      // A create carries no precondition: there is nothing to be a revision OF.
      return hasExactKeys(value, ["op", "record_id", "content"]) && isFieldBag(op["content"]);
    case "patch":
      return baseOk
        && isFieldBag(op["patch"])
        && (hasExactKeys(value, ["op", "record_id", "patch"]) || hasExactKeys(value, ["op", "record_id", "patch", "base_revision"]));
    case "delete":
      return baseOk
        && (hasExactKeys(value, ["op", "record_id"]) || hasExactKeys(value, ["op", "record_id", "base_revision"]));
    default:
      return false;
  }
}

/** Strict predicate over already-parsed trusted JSON. Not a hostile-object boundary. */
export function isTrustedWriteOpEnvelope(value: unknown): value is WriteOpEnvelope {
  if (!isPlainJsonDataGraph(value)) return false;
  if (!hasExactKeys(value, ENVELOPE_KEYS)) return false;
  const envelope = value as Record<string, unknown>;
  if (typeof envelope["write_id"] !== "string" || !WRITE_ID_PATTERN.test(envelope["write_id"])) return false;
  const epoch = envelope["account_epoch"];
  if (typeof epoch !== "number" || !Number.isSafeInteger(epoch) || epoch < 0) return false;
  if (!isWritableDomain(envelope["domain"])) return false;
  return isWriteOp(envelope["op"]);
}

/** Authoritative no-execution boundary for untrusted canonical JSON request bodies. */
export function parseWriteOpEnvelopeJson(raw: string): WriteOpEnvelope | null {
  return parseCanonicalJson(raw, MAX_WRITE_ENVELOPE_JSON_CODE_UNITS, isTrustedWriteOpEnvelope);
}

/**
 * The refusal OUTCOME classes. `backend:ADR-010` §3 amends ADR-004 §4 for the
 * write path: unlike the read door, a write refusal must distinguish class,
 * because "retry after re-auth", "buy the thing", and "this can never be
 * accepted" are different instructions to a client. It still never
 * distinguishes inner reason.
 */
export type WriteRefusalOutcome = "authentication" | "authorization" | "entitlement" | "stale_epoch";

export const WRITE_REFUSAL_OUTCOMES = ["authentication", "authorization", "entitlement", "stale_epoch"] as const;

export interface WriteRefusal {
  readonly status: number;
  /** The exact response body. Byte-identical per class; never interpolated. */
  readonly body: string;
}

/**
 * The fixed refusal bodies, as literal strings rather than objects, because
 * "byte-identical" is the property being asserted and a serializer sits
 * between an object and its bytes.
 *
 * `authorization` and `entitlement` are BOTH 403 and are deliberately NOT
 * byte-identical to each other: entitlement is a distinct outcome class the
 * client must act on differently. What must stay byte-identical is every
 * inner reason WITHIN the authorization class.
 */
export const WRITE_REFUSALS: Readonly<Record<WriteRefusalOutcome, WriteRefusal>> = Object.freeze({
  authentication: Object.freeze({ status: 401, body: '{"error":"unauthorized","refusal_outcome":"authentication"}' }),
  authorization: Object.freeze({ status: 403, body: '{"error":"forbidden","refusal_outcome":"authorization"}' }),
  entitlement: Object.freeze({ status: 403, body: '{"error":"forbidden","refusal_outcome":"entitlement"}' }),
  stale_epoch: Object.freeze({ status: 409, body: '{"error":"stale_epoch","refusal_outcome":"stale_epoch"}' }),
});

/**
 * Non-refusal error bodies. These are NOT refusal outcomes: a refusal is a
 * decision about the principal, these are decisions about the request.
 *
 * `maintenance` is backpressure, not evidence — a fenced account gets it and
 * NOTHING is recorded server-side. It must reach the product surface as the
 * maintenance notice, never as a bare retryable, or the queue silently buffers
 * through a migration window.
 */
export const WRITE_ERRORS = Object.freeze({
  /** Malformed envelope, unknown domain, or a domain that is not writable. */
  validation: Object.freeze({ status: 422, body: '{"error":"invalid_envelope"}' }),
  /** Same `write_id` seen before with DIFFERENT content — a buggy adapter laundering two ops through one key. */
  write_id_reuse: Object.freeze({ status: 409, body: '{"error":"write_id_reuse"}' }),
  /** `base_revision` precondition failed: a genuine concurrent edit. */
  conflict: Object.freeze({ status: 409, body: '{"error":"conflict"}' }),
  /** Migration window or missing control state. Carries `retry-after`. */
  maintenance: Object.freeze({ status: 503, body: '{"error":"maintenance"}' }),
});

/**
 * The one success shape. `idempotent: true` means the registry answered from a
 * recorded outcome rather than applying again — the crash-replay case. It is
 * a SUCCESS: the user's edit is in the record, and reporting anything else
 * would be the false-failure this contract exists to prevent.
 */
export interface WriteAccepted {
  readonly applied: { readonly record_id: string; readonly revision: string | null };
  readonly idempotent: boolean;
}

export function isTrustedWriteAccepted(value: unknown): value is WriteAccepted {
  if (!isPlainJsonDataGraph(value)) return false;
  if (!hasExactKeys(value, ["applied", "idempotent"])) return false;
  const accepted = value as { applied: unknown; idempotent: unknown };
  if (typeof accepted.idempotent !== "boolean") return false;
  if (!hasExactKeys(accepted.applied, ["record_id", "revision"])) return false;
  const applied = accepted.applied as { record_id: unknown; revision: unknown };
  if (typeof applied.record_id !== "string" || !RECORD_ID_PATTERN.test(applied.record_id)) return false;
  return applied.revision === null || (typeof applied.revision === "string" && REVISION_PATTERN.test(applied.revision));
}

/**
 * Read the refusal class off a response body, without trusting the status.
 *
 * Two outcome classes share status 403 and two share 409, so a client that
 * branches on status alone cannot tell `stale_epoch` from `conflict`. That
 * mis-branch is exactly the demonstrated failure: a straggler reported to the
 * user as a conflict on an edit that may well have applied. Returns `null`
 * when the body is not one of the fixed refusal bodies — the caller then falls
 * back to its status taxonomy rather than guessing a class.
 */
export function readWriteRefusalOutcome(status: number, body: string): WriteRefusalOutcome | null {
  for (const outcome of WRITE_REFUSAL_OUTCOMES) {
    const refusal = WRITE_REFUSALS[outcome];
    if (refusal.status === status && refusal.body === body) return outcome;
  }
  return null;
}
