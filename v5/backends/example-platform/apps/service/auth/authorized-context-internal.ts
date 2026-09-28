import { isProxy } from "node:util/types";

/**
 * The authenticated, exact-grant write authority presented to an authoritative
 * memory repository.
 *
 * This is a service-boundary capability, not a client payload and not a
 * substitute for the repository's transaction-time recheck.  The factory lives
 * in auth composition so routes and model payloads cannot select an account,
 * grant, or epoch for themselves.  The eventual PostgreSQL adapter must still
 * lock and revalidate every coordinate before it returns a replay or commits.
 */

const CONTEXT_VERSION = "authorized-ledger-write-context-v1" as const;
const MAX_ACCOUNT_ID_LENGTH = 128;
const MAX_IDENTIFIER_LENGTH = 256;
const TOKEN = /^[\x21-\x7e]+$/;
const DIGEST = /^[a-f0-9]{64}$/;

const CONTEXT_KEYS = Object.freeze([
  "account_epoch",
  "account_id",
  "application_id",
  "authentication_strength",
  "authorization_state_digest",
  "capability",
  "context_version",
  "credential_generation",
  "credential_id",
  "deletion_epoch",
  "destination_activation_revision",
  "expires_at_epoch_seconds",
  "grant_id",
  "grant_version",
  "issued_at_epoch_seconds",
  "lifecycle_state",
  "principal_id",
] as const);

export interface AuthorizedLedgerWriteContextInput {
  readonly context_version: typeof CONTEXT_VERSION;
  readonly principal_id: string;
  readonly account_id: string;
  readonly application_id: string;
  readonly credential_id: string;
  readonly credential_generation: number;
  readonly capability: string;
  readonly grant_id: string;
  readonly grant_version: number;
  readonly account_epoch: number;
  readonly destination_activation_revision: number;
  readonly lifecycle_state: "active";
  readonly deletion_epoch: null;
  readonly authentication_strength: string;
  readonly issued_at_epoch_seconds: number;
  readonly expires_at_epoch_seconds: number;
  readonly authorization_state_digest: string;
}

/**
 * Opaque at runtime as well as in TypeScript: copying these visible fields does
 * not mint authority.  `assertAuthorizedLedgerWriteContext` accepts only a
 * frozen value issued by the auth-composition factory below.
 */
export type AuthorizedLedgerWriteContext = Readonly<AuthorizedLedgerWriteContextInput>;

export interface AuthorizedRestoreReleaseBinding {
  readonly database_generation_digest: string;
  readonly restore_release_revision: number;
  readonly restore_release_content_hash: string;
}

const issuedContexts = new WeakSet<object>();
const restoreReleaseBindings = new WeakMap<object, Readonly<AuthorizedRestoreReleaseBinding>>();
const AUTHORIZED_LEDGER_CONTEXT_ISSUER: unique symbol = Symbol("authorized-ledger-context-issuer");

/**
 * An injected auth-composition capability.  Routes, model adapters, and
 * repositories receive an issuer or an already-issued context; they do not
 * assemble authority fields.  This is a construction seam, not a replacement
 * for the PostgreSQL transaction's DB-clock and row-lock revalidation.
 */
export interface AuthorizedLedgerWriteContextIssuer {
  readonly [AUTHORIZED_LEDGER_CONTEXT_ISSUER]: true;
  issue(input: AuthorizedLedgerWriteContextInput, nowEpochSeconds: number): AuthorizedLedgerWriteContext;
  issueRestored(
    input: AuthorizedLedgerWriteContextInput,
    binding: AuthorizedRestoreReleaseBinding,
    nowEpochSeconds: number,
  ): AuthorizedLedgerWriteContext;
}

function fail(message: string): never {
  throw new TypeError(`authorized ledger context ${message}`);
}

const exactDataRecord = (value: unknown, expected: readonly string[]): Record<string, unknown> => {
  if (value === null || typeof value !== "object") fail("must be an exact plain object");
  if (Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Object.prototype) {
    fail("must be an exact plain object");
  }
  const keys = Reflect.ownKeys(value);
  if (keys.some((key) => typeof key !== "string")) fail("rejects symbol keys");
  const actual = (keys as string[]).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) fail("has an invalid shape");
  for (const key of actual) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail("requires enumerable own data properties");
  }
  return value as Record<string, unknown>;
};

const token = (value: unknown, label: string, maxLength = MAX_IDENTIFIER_LENGTH): string => {
  if (typeof value !== "string") fail(`${label} must be a bounded printable token`);
  if (value.length === 0 || value.length > maxLength || !TOKEN.test(value)) {
    fail(`${label} must be a bounded printable token`);
  }
  return value;
};

const counter = (value: unknown, label: string): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 0) fail(`${label} must be a non-negative safe integer`);
  return value as number;
};

const time = (value: unknown, label: string): number => counter(value, label);

const requireNow = (value: unknown): number => time(value, "validation time");

const restoreReleaseBinding = (value: unknown): Readonly<AuthorizedRestoreReleaseBinding> => {
  const fields = exactDataRecord(value, [
    "database_generation_digest", "restore_release_revision", "restore_release_content_hash",
  ]);
  const generation = fields["database_generation_digest"];
  const contentHash = fields["restore_release_content_hash"];
  if (typeof generation !== "string" || !DIGEST.test(generation)
    || typeof contentHash !== "string" || !DIGEST.test(contentHash)) {
    fail("restore release binding requires SHA-256 digests");
  }
  return Object.freeze({
    database_generation_digest: generation,
    restore_release_revision: counter(fields["restore_release_revision"], "restore_release_revision"),
    restore_release_content_hash: contentHash,
  });
};

/**
 * The only minting operation.  Auth composition supplies a caller-provided
 * clock value so this module never acquires wall-clock authority.
 */
const mintAuthorizedLedgerWriteContext = (
  input: AuthorizedLedgerWriteContextInput,
  nowEpochSeconds: number,
): AuthorizedLedgerWriteContext => {
  const fields = exactDataRecord(input, CONTEXT_KEYS);
  const now = requireNow(nowEpochSeconds);
  if (fields["context_version"] !== CONTEXT_VERSION) fail("has an unsupported context_version");
  if (fields["lifecycle_state"] !== "active" || fields["deletion_epoch"] !== null) fail("must be active without a deletion epoch");
  const issuedAt = time(fields["issued_at_epoch_seconds"], "issued_at_epoch_seconds");
  const expiresAt = time(fields["expires_at_epoch_seconds"], "expires_at_epoch_seconds");
  if (issuedAt > now || expiresAt <= now || expiresAt <= issuedAt) fail("is expired or has an invalid lifetime");
  const authorizationStateDigest = fields["authorization_state_digest"];
  if (typeof authorizationStateDigest !== "string" || !DIGEST.test(authorizationStateDigest)) {
    fail("authorization_state_digest must be a SHA-256 digest");
  }

  const context = Object.freeze({
    context_version: CONTEXT_VERSION,
    principal_id: token(fields["principal_id"], "principal_id"),
    account_id: token(fields["account_id"], "account_id", MAX_ACCOUNT_ID_LENGTH),
    application_id: token(fields["application_id"], "application_id"),
    credential_id: token(fields["credential_id"], "credential_id"),
    credential_generation: counter(fields["credential_generation"], "credential_generation"),
    capability: token(fields["capability"], "capability"),
    grant_id: token(fields["grant_id"], "grant_id"),
    grant_version: counter(fields["grant_version"], "grant_version"),
    account_epoch: counter(fields["account_epoch"], "account_epoch"),
    destination_activation_revision: counter(fields["destination_activation_revision"], "destination_activation_revision"),
    lifecycle_state: "active" as const,
    deletion_epoch: null,
    authentication_strength: token(fields["authentication_strength"], "authentication_strength"),
    issued_at_epoch_seconds: issuedAt,
    expires_at_epoch_seconds: expiresAt,
    authorization_state_digest: authorizationStateDigest,
  });
  issuedContexts.add(context);
  return context;
};

/**
 * Construct this once at authentication/authorization composition, then inject
 * the issuer into that composition.  The raw mint function is deliberately not
 * exported, so ordinary routes have no field-level construction API.
 */
export const createAuthorizedLedgerWriteContextIssuer = (): AuthorizedLedgerWriteContextIssuer =>
  Object.freeze({
    [AUTHORIZED_LEDGER_CONTEXT_ISSUER]: true as const,
    issue(input: AuthorizedLedgerWriteContextInput, nowEpochSeconds: number): AuthorizedLedgerWriteContext {
      return mintAuthorizedLedgerWriteContext(input, nowEpochSeconds);
    },
    issueRestored(
      input: AuthorizedLedgerWriteContextInput,
      binding: AuthorizedRestoreReleaseBinding,
      nowEpochSeconds: number,
    ): AuthorizedLedgerWriteContext {
      const normalizedBinding = restoreReleaseBinding(binding);
      const context = mintAuthorizedLedgerWriteContext(input, nowEpochSeconds);
      restoreReleaseBindings.set(context, normalizedBinding);
      return context;
    },
  });

/** Runtime brand check for repository adapters and sealed service ports. */
export const assertAuthorizedLedgerWriteContext = (value: unknown): AuthorizedLedgerWriteContext => {
  if (value === null || typeof value !== "object" || !issuedContexts.has(value) || !Object.isFrozen(value)) {
    return fail("was not issued by auth composition");
  }
  return value as AuthorizedLedgerWriteContext;
};

/**
 * A driver supplies its authoritative transaction/DB clock here.  It must run
 * this recheck after locking current credential/grant/control rows and before
 * it returns a replay or writes anything.
 */
export const assertAuthorizedLedgerWriteContextCurrentAt = (
  value: unknown,
  nowEpochSeconds: number,
): AuthorizedLedgerWriteContext => {
  const context = assertAuthorizedLedgerWriteContext(value);
  const now = requireNow(nowEpochSeconds);
  if (now < context.issued_at_epoch_seconds || now >= context.expires_at_epoch_seconds) {
    return fail("is expired at the authoritative validation time");
  }
  return context;
};

/** Hidden restore-generation authority carried only by a genuinely issued context. */
export const authorizedRestoreReleaseBinding = (
  value: unknown,
): Readonly<AuthorizedRestoreReleaseBinding> | null => {
  const context = assertAuthorizedLedgerWriteContext(value);
  return restoreReleaseBindings.get(context) ?? null;
};

export const AUTHORIZED_LEDGER_CONTEXT_VERSION = CONTEXT_VERSION;
