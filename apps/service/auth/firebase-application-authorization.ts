import { isProxy } from "node:util/types";

import { isWellFormedAccountId } from "../../../core/control/account-control";
import {
  inspectApplicationAccountControl,
  type ApplicationAccountControlSource,
} from "../control/application-control-source";
import {
  AUTHORIZED_LEDGER_CONTEXT_VERSION,
  type AuthorizedLedgerWriteContext,
} from "./authorized-context";
import { createAuthorizedLedgerWriteContextIssuer } from "./authorized-context-internal";
import type { FirebaseIdentityVerifier } from "./firebase-identity";

const MAX_IDENTIFIER_CODE_UNITS = 256;
const MAX_FIREBASE_UID_CODE_UNITS = 128;
const MAX_CONTEXT_TTL_SECONDS = 300;
const PRINTABLE_TOKEN = /^[\x21-\x7e]+$/;
const DIGEST = /^[a-f0-9]{64}$/;

export interface FirebaseApplicationAuthorizationSourceRequest {
  readonly firebase_project_id: string;
  readonly firebase_uid: string;
  readonly application_id: string;
  readonly capability: string;
}

export interface FirebaseApplicationAuthorizationSource {
  load(request: FirebaseApplicationAuthorizationSourceRequest): Promise<unknown>;
}

export interface FirebaseApplicationAuthorizationConfig {
  readonly identity_verifier: FirebaseIdentityVerifier;
  readonly authorization_source: FirebaseApplicationAuthorizationSource;
  readonly control_source: ApplicationAccountControlSource;
  readonly application_id: string;
  readonly capability: string;
  readonly context_ttl_seconds: number;
}

export type FirebaseApplicationAuthorizationResult =
  | Readonly<{
      authorized: true;
      outcome: "authorized";
      context: AuthorizedLedgerWriteContext;
    }>
  | Readonly<{
      authorized: false;
      outcome: "authentication" | "authorization" | "stale_epoch" | "unavailable";
    }>;

export interface FirebaseApplicationAuthorizer {
  authorize(token: string, nowEpochSeconds: number): Promise<FirebaseApplicationAuthorizationResult>;
}

type DataDescriptors = Readonly<Record<string, PropertyDescriptor & { readonly value: unknown }>>;

interface CurrentAuthorization {
  readonly firebase_project_id: string;
  readonly firebase_uid: string;
  readonly principal_id: string;
  readonly account_id: string;
  readonly application_id: string;
  readonly credential_id: string;
  readonly credential_generation: number;
  readonly credential_lifecycle: "active";
  readonly authentication_strength: "firebase-id-token";
  readonly credential_expires_at_epoch_seconds: number | null;
  readonly capability: string;
  readonly grant_id: string;
  readonly grant_version: number;
  readonly grant_lifecycle: "active";
  readonly grant_enabled: true;
  readonly authorization_state_digest: string;
  readonly control_revision: number;
  readonly account_epoch: number;
  readonly destination_activation_revision: number;
}

const denyAuthentication = Object.freeze({ authorized: false, outcome: "authentication" as const });
const denyAuthorization = Object.freeze({ authorized: false, outcome: "authorization" as const });
const denyStaleEpoch = Object.freeze({ authorized: false, outcome: "stale_epoch" as const });
const denyUnavailable = Object.freeze({ authorized: false, outcome: "unavailable" as const });

const configurationError = (): never => {
  throw new TypeError("invalid Firebase application authorization configuration");
};

const descriptorsFor = (value: unknown): DataDescriptors | null => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) return null;
  const keys = Reflect.ownKeys(value);
  if (keys.some((key) => typeof key !== "string")) return null;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  for (const key of keys as string[]) {
    const descriptor = descriptors[key];
    if (descriptor === undefined || !("value" in descriptor) || descriptor.enumerable !== true) return null;
  }
  return descriptors as DataDescriptors;
};

const exactDescriptors = (value: unknown, keys: readonly string[]): DataDescriptors | null => {
  const descriptors = descriptorsFor(value);
  if (descriptors === null) return null;
  const actual = Object.keys(descriptors).sort();
  const expected = [...keys].sort();
  return actual.length === expected.length
    && actual.every((key, index) => key === expected[index])
    ? descriptors
    : null;
};

const boundedToken = (value: unknown): value is string =>
  typeof value === "string"
  && value.length >= 1
  && value.length <= MAX_IDENTIFIER_CODE_UNITS
  && PRINTABLE_TOKEN.test(value);

const firebaseUid = (value: unknown): value is string =>
  typeof value === "string"
  && value.length >= 1
  && value.length <= MAX_FIREBASE_UID_CODE_UNITS
  && !/[\u0000-\u001f\u007f]/.test(value);

const counter = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;

const positiveCounter = (value: unknown): value is number => counter(value) && value > 0;

const snapshotMethod = <Method extends (...args: never[]) => unknown>(
  value: unknown,
  methodName: string,
): Readonly<{ readonly receiver: object; readonly method: Method }> | null => {
  const descriptors = descriptorsFor(value);
  const descriptor = descriptors?.[methodName];
  if (descriptors === null || descriptor === undefined || typeof descriptor.value !== "function"
    || isProxy(descriptor.value)) return null;
  return Object.freeze({ receiver: value as object, method: descriptor.value as Method });
};

const parseIdentity = (value: unknown, now: number): Readonly<{
  readonly firebase_project_id: string;
  readonly firebase_uid: string;
  readonly expires_at_epoch_seconds: number;
}> | null => {
  const fields = exactDescriptors(
    value,
    ["firebase_project_id", "firebase_uid", "authentication_strength", "expires_at_epoch_seconds"],
  );
  if (fields === null) return null;
  const projectId = fields.firebase_project_id!.value;
  const uid = fields.firebase_uid!.value;
  const expiresAt = fields.expires_at_epoch_seconds!.value;
  if (!boundedToken(projectId) || !firebaseUid(uid)
    || fields.authentication_strength!.value !== "firebase-id-token"
    || !counter(expiresAt) || expiresAt <= now) return null;
  return Object.freeze({
    firebase_project_id: projectId,
    firebase_uid: uid,
    expires_at_epoch_seconds: expiresAt,
  });
};

const CURRENT_KEYS = Object.freeze([
  "status",
  "firebase_project_id",
  "firebase_uid",
  "principal_id",
  "account_id",
  "application_id",
  "credential_id",
  "credential_generation",
  "credential_lifecycle",
  "authentication_strength",
  "credential_expires_at_epoch_seconds",
  "capability",
  "grant_id",
  "grant_version",
  "grant_lifecycle",
  "grant_enabled",
  "authorization_state_digest",
  "control_revision",
  "account_epoch",
  "destination_activation_revision",
] as const);

const parseAuthorizationSource = (
  value: unknown,
  request: FirebaseApplicationAuthorizationSourceRequest,
  now: number,
): "absent" | "unavailable" | "invalid" | CurrentAuthorization => {
  const descriptors = descriptorsFor(value);
  const status = descriptors?.status?.value;
  if (status === "absent" || status === "unavailable") {
    return exactDescriptors(value, ["status"]) === null ? "invalid" : status;
  }
  if (status !== "current") return "invalid";
  const fields = exactDescriptors(value, CURRENT_KEYS);
  if (fields === null) return "invalid";

  const credentialExpiry = fields.credential_expires_at_epoch_seconds!.value;
  const normalizedCredentialExpiry = credentialExpiry === null
    ? null
    : counter(credentialExpiry) && credentialExpiry > now ? credentialExpiry : undefined;
  if (normalizedCredentialExpiry === undefined
    || fields.firebase_project_id!.value !== request.firebase_project_id
    || fields.firebase_uid!.value !== request.firebase_uid
    || !boundedToken(fields.principal_id!.value)
    || !isWellFormedAccountId(fields.account_id!.value)
    || fields.application_id!.value !== request.application_id
    || !boundedToken(fields.credential_id!.value)
    || !counter(fields.credential_generation!.value)
    || fields.credential_lifecycle!.value !== "active"
    || fields.authentication_strength!.value !== "firebase-id-token"
    || fields.capability!.value !== request.capability
    || !boundedToken(fields.grant_id!.value)
    || !counter(fields.grant_version!.value)
    || fields.grant_lifecycle!.value !== "active"
    || fields.grant_enabled!.value !== true
    || typeof fields.authorization_state_digest!.value !== "string"
    || !DIGEST.test(fields.authorization_state_digest!.value)
    || !counter(fields.control_revision!.value)
    || !counter(fields.account_epoch!.value)
    || !counter(fields.destination_activation_revision!.value)) return "invalid";

  return Object.freeze({
    firebase_project_id: request.firebase_project_id,
    firebase_uid: request.firebase_uid,
    principal_id: fields.principal_id!.value as string,
    account_id: fields.account_id!.value as string,
    application_id: request.application_id,
    credential_id: fields.credential_id!.value as string,
    credential_generation: fields.credential_generation!.value as number,
    credential_lifecycle: "active",
    authentication_strength: "firebase-id-token",
    credential_expires_at_epoch_seconds: normalizedCredentialExpiry,
    capability: request.capability,
    grant_id: fields.grant_id!.value as string,
    grant_version: fields.grant_version!.value as number,
    grant_lifecycle: "active",
    grant_enabled: true,
    authorization_state_digest: fields.authorization_state_digest!.value as string,
    control_revision: fields.control_revision!.value as number,
    account_epoch: fields.account_epoch!.value as number,
    destination_activation_revision: fields.destination_activation_revision!.value as number,
  });
};

/**
 * The single ADR-010 composition. It emits no authority until Firebase,
 * application grant, and coherent account-control coordinates all agree.
 */
export const composeFirebaseApplicationAuthorization = (
  configValue: FirebaseApplicationAuthorizationConfig,
): FirebaseApplicationAuthorizer => {
  const config = exactDescriptors(configValue, [
    "identity_verifier",
    "authorization_source",
    "control_source",
    "application_id",
    "capability",
    "context_ttl_seconds",
  ]);
  if (config === null) return configurationError();
  const applicationId = config.application_id!.value;
  const capability = config.capability!.value;
  const ttl = config.context_ttl_seconds!.value;
  const identity = snapshotMethod<FirebaseIdentityVerifier["resolve"]>(
    config.identity_verifier!.value,
    "resolve",
  );
  const authorization = snapshotMethod<FirebaseApplicationAuthorizationSource["load"]>(
    config.authorization_source!.value,
    "load",
  );
  const control = snapshotMethod<ApplicationAccountControlSource["load"]>(
    config.control_source!.value,
    "load",
  );
  if (!boundedToken(applicationId) || !boundedToken(capability)
    || !positiveCounter(ttl) || ttl > MAX_CONTEXT_TTL_SECONDS
    || identity === null || authorization === null || control === null) return configurationError();

  const controlSource: ApplicationAccountControlSource = Object.freeze({
    load(accountId: string): Promise<unknown> {
      return control.method.call(control.receiver, accountId);
    },
  });
  const issuer = createAuthorizedLedgerWriteContextIssuer();

  return Object.freeze({
    async authorize(token: string, nowEpochSeconds: number): Promise<FirebaseApplicationAuthorizationResult> {
      if (typeof token !== "string" || !counter(nowEpochSeconds)
        || nowEpochSeconds > Number.MAX_SAFE_INTEGER - ttl) return denyAuthentication;

      let rawIdentity: unknown;
      try {
        rawIdentity = await identity.method.call(identity.receiver, token, nowEpochSeconds);
      } catch {
        return denyAuthentication;
      }
      const verified = parseIdentity(rawIdentity, nowEpochSeconds);
      if (verified === null) return denyAuthentication;

      const request = Object.freeze({
        firebase_project_id: verified.firebase_project_id,
        firebase_uid: verified.firebase_uid,
        application_id: applicationId,
        capability,
      });
      let rawAuthorization: unknown;
      try {
        rawAuthorization = await authorization.method.call(authorization.receiver, request);
      } catch {
        return denyUnavailable;
      }
      const selected = parseAuthorizationSource(rawAuthorization, request, nowEpochSeconds);
      if (selected === "unavailable") return denyUnavailable;
      if (selected === "absent" || selected === "invalid") return denyAuthorization;

      const controlInspection = await inspectApplicationAccountControl(controlSource, selected.account_id);
      if (!controlInspection.admitted) {
        if (controlInspection.reason === "control_source_unavailable") return denyUnavailable;
        if (controlInspection.reason === "control_source_stale") return denyStaleEpoch;
        return denyAuthorization;
      }
      if (controlInspection.account_epoch !== selected.account_epoch
        || controlInspection.control_revision !== selected.control_revision
        || controlInspection.destination_activation_revision
          !== selected.destination_activation_revision) return denyStaleEpoch;

      const expiresAt = Math.min(
        verified.expires_at_epoch_seconds,
        selected.credential_expires_at_epoch_seconds ?? verified.expires_at_epoch_seconds,
        nowEpochSeconds + ttl,
      );
      if (expiresAt <= nowEpochSeconds) return denyAuthorization;
      try {
        const context = issuer.issue({
          context_version: AUTHORIZED_LEDGER_CONTEXT_VERSION,
          principal_id: selected.principal_id,
          account_id: selected.account_id,
          application_id: applicationId,
          credential_id: selected.credential_id,
          credential_generation: selected.credential_generation,
          capability,
          grant_id: selected.grant_id,
          grant_version: selected.grant_version,
          account_epoch: selected.account_epoch,
          destination_activation_revision: selected.destination_activation_revision,
          lifecycle_state: "active",
          deletion_epoch: null,
          authentication_strength: "firebase-id-token",
          issued_at_epoch_seconds: nowEpochSeconds,
          expires_at_epoch_seconds: expiresAt,
          authorization_state_digest: selected.authorization_state_digest,
        }, nowEpochSeconds);
        return Object.freeze({ authorized: true, outcome: "authorized", context });
      } catch {
        return denyUnavailable;
      }
    },
  });
};
