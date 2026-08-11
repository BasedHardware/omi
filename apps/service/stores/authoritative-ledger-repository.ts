import { isProxy } from "node:util/types";

import {
  parseFormationOutcomeEnvelope,
  type FormationOutcomeEnvelope,
} from "../../../core/consolidate/formation-outcome";
import {
  sha256CanonicalRedacted,
  validateAtomicGraphTransition,
  type AtomicGraphTransition,
  type CanonicalJson,
} from "../../../core/ledger";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";

const REPOSITORY_PORT: unique symbol = Symbol("authoritative-ledger-repository");
const TOKEN = /^[\x21-\x7e]{1,256}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const NON_FORMATION_REASONS = new Set(["repair", "manual_liveness", "historical_replay"] as const);
export type NonFormationAppendReason = "repair" | "manual_liveness" | "historical_replay";

export interface AppendAttempt {
  readonly idempotency_key: string;
  readonly expected_parent_commit: string | null;
  /** sha256-canonical-redacted-v1 over the complete transition and origin. */
  readonly request_digest: string;
}

export interface FormationAppendOrigin {
  readonly kind: "formation";
  /** The exact, total outcome for this work; parsing is part of port admission. */
  readonly outcome: FormationOutcomeEnvelope;
}

export interface NonFormationAppendOrigin {
  readonly kind: "non_formation";
  /** Accounting is explicit: callers cannot silently omit formation work. */
  readonly reason: NonFormationAppendReason;
}

export type AuthoritativeAppendOrigin = FormationAppendOrigin | NonFormationAppendOrigin;

export interface AuthoritativeLedgerAppend {
  readonly append_attempt: AppendAttempt;
  readonly origin: AuthoritativeAppendOrigin;
  readonly transition: AtomicGraphTransition;
}

export type AuthoritativeLedgerAppendOutcome =
  | { readonly kind: "committed"; readonly commit_id: string; readonly sequence: number }
  | { readonly kind: "replayed"; readonly commit_id: string; readonly sequence: number }
  | { readonly kind: "idempotency_conflict" }
  | { readonly kind: "stale_parent" }
  | { readonly kind: "stale_context"; readonly reason: "expired_context" | "stale_epoch" | "destination_inactive" | "lifecycle_inactive" }
  | { readonly kind: "authorization_denied"; readonly reason: "credential_inactive" | "grant_inactive" | "capability_denied" }
  | { readonly kind: "serialization_retryable" };

export interface AuthoritativeLedgerRepository {
  readonly [REPOSITORY_PORT]: true;
  append(
    context: AuthorizedLedgerWriteContext,
    request: AuthoritativeLedgerAppend,
  ): Promise<AuthoritativeLedgerAppendOutcome>;
}

export type AuthoritativeLedgerAppendImplementation = (
  context: AuthorizedLedgerWriteContext,
  request: AuthoritativeLedgerAppend,
) => Promise<AuthoritativeLedgerAppendOutcome>;

function fail(message: string): never {
  throw new TypeError(`authoritative ledger append ${message}`);
}

const exactDataRecord = (value: unknown, expected: readonly string[], label: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object") fail(`${label} must be an exact plain object`);
  if (Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Object.prototype) {
    fail(`${label} must be an exact plain object`);
  }
  const keys = Reflect.ownKeys(value);
  if (keys.some((key) => typeof key !== "string")) fail(`${label} rejects symbol keys`);
  const actual = (keys as string[]).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) fail(`${label} has an invalid shape`);
  for (const key of actual) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(`${label} requires enumerable own data properties`);
  }
  return value as Record<string, unknown>;
};

const token = (value: unknown, label: string): string => {
  if (typeof value !== "string") fail(`${label} must be a bounded printable token`);
  if (!TOKEN.test(value)) fail(`${label} must be a bounded printable token`);
  return value;
};

const nullableToken = (value: unknown, label: string): string | null => value === null ? null : token(value, label);

/** Stable coordinate that an adapter compares with the persisted receipt. */
export const authoritativeAppendRequestDigest = (
  transition: AtomicGraphTransition,
  origin: AuthoritativeAppendOrigin,
): string =>
  sha256CanonicalRedacted({
    contract_version: "authoritative-ledger-append-v1",
    origin: origin as unknown as CanonicalJson,
    transition: transition as unknown as CanonicalJson,
  });

const assertPlainTransition = (value: unknown, accountId: string): AtomicGraphTransition => {
  const active = new WeakSet<object>();
  const inspect = (node: unknown): void => {
    if (node === null || typeof node === "string" || typeof node === "boolean") return;
    if (typeof node === "number") {
      if (!Number.isFinite(node)) fail("transition rejects non-finite numbers");
      return;
    }
    if (typeof node !== "object") fail("transition must be plain tree data");
    if (isProxy(node) || active.has(node)) fail("transition must be plain tree data");
    active.add(node);
    if (Array.isArray(node)) {
      if (Object.getPrototypeOf(node) !== Array.prototype) fail("transition must be plain tree data");
      const keys = Reflect.ownKeys(node);
      if (keys.some((key) => typeof key !== "string")) fail("transition rejects symbol keys");
      const expectedKeys = [
        ...Array.from({ length: node.length }, (_, index) => String(index)),
        "length",
      ];
      if (keys.length !== expectedKeys.length || expectedKeys.some((key) => !keys.includes(key))) {
        fail("transition arrays must be dense and undecorated");
      }
      for (let index = 0; index < node.length; index += 1) {
        const descriptor = Object.getOwnPropertyDescriptor(node, String(index));
        if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) {
          fail("transition arrays require enumerable own data elements");
        }
        inspect(descriptor.value);
      }
      active.delete(node);
      return;
    }
    if (Object.getPrototypeOf(node) !== Object.prototype) fail("transition must be plain tree data");
    for (const key of Reflect.ownKeys(node)) {
      if (typeof key !== "string") fail("transition rejects symbol keys");
      const descriptor = Object.getOwnPropertyDescriptor(node, key);
      if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail("transition requires enumerable own data properties");
      if (key === "owner_account_id" && descriptor.value !== accountId) fail("contains an owner outside the authorized account");
      inspect(descriptor.value);
    }
    active.delete(node);
  };
  inspect(value);
  try {
    validateAtomicGraphTransition(value as AtomicGraphTransition);
  } catch {
    // The core validator may describe payload-derived coordinates. Keep the
    // service boundary content-safe; detailed validation remains test-local.
    throw new TypeError("authoritative ledger append transition is invalid");
  }
  return value as AtomicGraphTransition;
};

const assertFormationTransitionAccounting = (
  outcome: FormationOutcomeEnvelope,
  transition: AtomicGraphTransition,
): void => {
  const revisionsById = new Map(transition.revisions.map((revision) => [revision.revision_id, revision]));
  const acceptedIds = outcome.extraction_outcomes
    .filter((item): item is Extract<FormationOutcomeEnvelope["extraction_outcomes"][number], { kind: "accepted" }> => item.kind === "accepted")
    .map((item) => item.claim_revision_id);
  for (const claimRevisionId of acceptedIds) {
    const revision = revisionsById.get(claimRevisionId);
    if (!revision || revision.kind !== "claim" || revision.claim.lifecycle !== "provisional") {
      fail("formation accepted provisional claim is absent from the transition");
    }
  }
  const acceptedIdSet = new Set(acceptedIds);
  const transitionProvisionalIds = transition.revisions
    .filter((revision) => revision.kind === "claim" && revision.claim.lifecycle === "provisional")
    .map((revision) => revision.revision_id);
  if (acceptedIdSet.size !== transitionProvisionalIds.length
    || transitionProvisionalIds.some((revisionId) => !acceptedIdSet.has(revisionId))) {
    fail("formation provisional revisions do not exactly match accepted extraction outcomes");
  }
  const admittedCanonicalIds = new Set(outcome.placement_outcomes
    .filter((item): item is Extract<FormationOutcomeEnvelope["placement_outcomes"][number], { kind: "admitted" }> => item.kind === "admitted")
    .map((item) => item.canonical_claim_revision_id));
  const transitionCanonicalIds = new Set(transition.revisions
    .filter((revision) => revision.kind === "claim" && revision.placement_status === "canonical")
    .map((revision) => revision.revision_id));
  if (admittedCanonicalIds.size !== transitionCanonicalIds.size
    || [...admittedCanonicalIds].some((revisionId) => !transitionCanonicalIds.has(revisionId))) {
    fail("formation canonical allocations do not exactly match admitted outcomes");
  }
};

/**
 * Validates the boundary shape before an adapter can borrow a database client.
 * The PostgreSQL adapter rechecks all authority rows and transaction-local state;
 * this guard only ensures a caller cannot smuggle a second owner or omit work
 * accounting from the typed repository contract.
 */
export const assertAuthoritativeLedgerAppend = (
  context: AuthorizedLedgerWriteContext,
  value: unknown,
): AuthoritativeLedgerAppend => {
  const authorized = assertAuthorizedLedgerWriteContext(context);
  const root = exactDataRecord(value, ["append_attempt", "origin", "transition"], "request");
  const attempt = exactDataRecord(root["append_attempt"], ["expected_parent_commit", "idempotency_key", "request_digest"], "append_attempt");
  const idempotencyKey = token(attempt["idempotency_key"], "append_attempt.idempotency_key");
  const expectedParent = nullableToken(attempt["expected_parent_commit"], "append_attempt.expected_parent_commit");
  const requestDigest = attempt["request_digest"];
  if (typeof requestDigest !== "string" || !DIGEST.test(requestDigest)) fail("append_attempt.request_digest must be a SHA-256 digest");
  const transition = assertPlainTransition(root["transition"], authorized.account_id);
  if (transition.derivation.attempt.owner_account_id !== authorized.account_id
    || transition.derivation.commit.owner_account_id !== authorized.account_id) {
    fail("derivation owner does not match the authorized account");
  }
  if (transition.derivation.commit.parent_commit !== expectedParent) fail("expected parent does not match the transition");
  if (transition.derivation.commit.idempotency_key !== idempotencyKey) fail("idempotency key does not match the transition");
  const rootOrigin = root["origin"];
  if (rootOrigin === null || typeof rootOrigin !== "object") {
    fail("origin must be an exact plain object");
  }
  if (Array.isArray(rootOrigin) || isProxy(rootOrigin) || Object.getPrototypeOf(rootOrigin) !== Object.prototype) {
    fail("origin must be an exact plain object");
  }
  const kindDescriptor = Object.getOwnPropertyDescriptor(rootOrigin, "kind");
  if (!kindDescriptor || !("value" in kindDescriptor) || !kindDescriptor.enumerable) {
    fail("origin requires an enumerable own kind");
  }
  const origin = kindDescriptor.value === "formation"
    ? exactDataRecord(rootOrigin, ["kind", "outcome"], "origin")
    : exactDataRecord(rootOrigin, ["kind", "reason"], "origin");
  if (origin["kind"] === "formation") {
    const outcome = parseFormationOutcomeEnvelope(origin["outcome"]);
    if (outcome.owner_account_id !== authorized.account_id) fail("formation outcome owner does not match the authorized account");
    assertFormationTransitionAccounting(outcome, transition);
    const normalizedOrigin = Object.freeze({ kind: "formation" as const, outcome });
    if (authoritativeAppendRequestDigest(transition, normalizedOrigin) !== requestDigest) {
      fail("request digest does not match the transition and formation outcome");
    }
    return Object.freeze({
      append_attempt: Object.freeze({ idempotency_key: idempotencyKey, expected_parent_commit: expectedParent, request_digest: requestDigest }),
      origin: normalizedOrigin,
      transition,
    });
  }
  if (origin["kind"] === "non_formation") {
    const reason = origin["reason"];
    if (typeof reason !== "string" || !NON_FORMATION_REASONS.has(reason as NonFormationAppendReason)) {
      fail("origin.reason is unsupported");
    }
    const normalizedOrigin = Object.freeze({ kind: "non_formation" as const, reason: reason as NonFormationAppendReason });
    if (authoritativeAppendRequestDigest(transition, normalizedOrigin) !== requestDigest) {
      fail("request digest does not match the transition and non-formation origin");
    }
    return Object.freeze({
      append_attempt: Object.freeze({ idempotency_key: idempotencyKey, expected_parent_commit: expectedParent, request_digest: requestDigest }),
      origin: normalizedOrigin,
      transition,
    });
  }
  return fail("origin.kind is unsupported");
};

/**
 * The only constructor for the async authority port.  Adapters receive a
 * runtime-minted context and a normalized, accounted transition; they still
 * own transaction-local revalidation, receipt reservation, and database I/O.
 */
export const defineAuthoritativeLedgerRepository = (
  implementation: AuthoritativeLedgerAppendImplementation,
): AuthoritativeLedgerRepository => Object.freeze({
  [REPOSITORY_PORT]: true as const,
  async append(context: AuthorizedLedgerWriteContext, request: AuthoritativeLedgerAppend): Promise<AuthoritativeLedgerAppendOutcome> {
    const authorized = assertAuthorizedLedgerWriteContext(context);
    return implementation(authorized, assertAuthoritativeLedgerAppend(authorized, request));
  },
});
