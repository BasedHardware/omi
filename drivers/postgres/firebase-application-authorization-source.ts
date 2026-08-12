import { isProxy } from "node:util/types";

import type { SqlStatement } from "./connection";
import { authorizationStateDigest, type AuthorityStateRow } from "./transaction";

const MAX_COORDINATE_CODE_UNITS = 256;
const MAX_ACCOUNT_CODE_UNITS = 128;
const MAX_FIREBASE_UID_CODE_UNITS = 128;
const PRINTABLE_TOKEN = /^[\x21-\x7e]+$/;
const DIGEST = /^[a-f0-9]{64}$/;

export const LOOKUP_FIREBASE_APPLICATION_AUTHORIZATION: SqlStatement["text"] = `
SELECT *
FROM omi_memory.lookup_firebase_application_authorization($1, $2, $3, $4)
`;

export interface FirebaseApplicationAuthorizationQueryPort {
  query(statement: SqlStatement): Promise<readonly Record<string, unknown>[]>;
}

export interface PostgresFirebaseApplicationAuthorizationSource {
  load(request: unknown): Promise<unknown>;
}

type QueryMethod = FirebaseApplicationAuthorizationQueryPort["query"];
type DataDescriptors = Readonly<Record<string, PropertyDescriptor & { readonly value: unknown }>>;

const unavailable = Object.freeze({ status: "unavailable" as const });
const absent = Object.freeze({ status: "absent" as const });

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

const rowsArray = (value: unknown): readonly unknown[] | null => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype) return null;
  const keys = Reflect.ownKeys(value);
  if (keys.some((key) => key !== "length" && (typeof key !== "string" || !/^(0|[1-9][0-9]*)$/.test(key)))) {
    return null;
  }
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
    if (descriptor === undefined || !("value" in descriptor) || descriptor.enumerable !== true) return null;
  }
  return value;
};

const token = (value: unknown, max = MAX_COORDINATE_CODE_UNITS): value is string =>
  typeof value === "string"
  && value.length >= 1
  && value.length <= max
  && PRINTABLE_TOKEN.test(value);

const firebaseUid = (value: unknown): value is string =>
  typeof value === "string"
  && value.length >= 1
  && value.length <= MAX_FIREBASE_UID_CODE_UNITS
  && !/[\u0000-\u001f\u007f]/.test(value);

const counter = (value: unknown): number | undefined => {
  if (typeof value === "number" && Number.isSafeInteger(value) && value >= 0) return value;
  if (typeof value !== "string" || !/^(0|[1-9][0-9]*)$/.test(value)) return undefined;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : undefined;
};

const nullableCounter = (value: unknown): number | null | undefined =>
  value === null ? null : counter(value);
const nullableToken = (value: unknown): value is string | null => value === null || token(value);

const snapshotQuery = (value: unknown): Readonly<{
  readonly receiver: object;
  readonly method: QueryMethod;
}> | null => {
  const descriptors = exactDescriptors(value, ["query"]);
  const method = descriptors?.query?.value;
  if (descriptors === null || typeof method !== "function" || isProxy(method)) return null;
  return Object.freeze({ receiver: value as object, method: method as QueryMethod });
};

const REQUEST_KEYS = Object.freeze([
  "firebase_project_id",
  "firebase_uid",
  "application_id",
  "capability",
] as const);

interface RequestCoordinates {
  readonly firebase_project_id: string;
  readonly firebase_uid: string;
  readonly application_id: string;
  readonly capability: string;
}

const parseRequest = (value: unknown): RequestCoordinates | null => {
  const fields = exactDescriptors(value, REQUEST_KEYS);
  if (fields === null) return null;
  const projectId = fields.firebase_project_id!.value;
  const uid = fields.firebase_uid!.value;
  const applicationId = fields.application_id!.value;
  const capability = fields.capability!.value;
  if (!token(projectId) || !firebaseUid(uid) || !token(applicationId) || !token(capability)) return null;
  return Object.freeze({
    firebase_project_id: projectId,
    firebase_uid: uid,
    application_id: applicationId,
    capability,
  });
};

const ROW_KEYS = Object.freeze([
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
  "control_revision",
  "account_epoch",
  "destination_activation_revision",
  "destination_activation_epoch",
  "control_conflict_reason",
  "control_conflict_at_revision",
  "lifecycle_state",
  "deletion_epoch",
  "account_generation",
  "control_content_hash",
  "credential_content_hash",
  "grant_content_hash",
] as const);

const AUTHORITY_LIFECYCLES = new Set(["active", "inactive", "revoked"]);
const ACCOUNT_LIFECYCLES = new Set(["active", "deletion_pending", "deleted"]);
const ACCOUNT_GENERATIONS = new Set(["legacy", "migrating", "new", "rolled_back_stranded"]);

const parseCurrent = (value: unknown, request: RequestCoordinates): unknown | null => {
  const fields = exactDescriptors(value, ROW_KEYS);
  if (fields === null) return null;
  const get = (key: (typeof ROW_KEYS)[number]): unknown => fields[key]!.value;
  const projectId = get("firebase_project_id");
  const uid = get("firebase_uid");
  const principalId = get("principal_id");
  const accountId = get("account_id");
  const applicationId = get("application_id");
  const credentialId = get("credential_id");
  const credentialGeneration = get("credential_generation");
  const credentialLifecycle = get("credential_lifecycle");
  const authenticationStrength = get("authentication_strength");
  const credentialExpiry = get("credential_expires_at_epoch_seconds");
  const capability = get("capability");
  const grantId = get("grant_id");
  const grantVersion = get("grant_version");
  const grantLifecycle = get("grant_lifecycle");
  const grantEnabled = get("grant_enabled");
  const controlRevision = get("control_revision");
  const accountEpoch = get("account_epoch");
  const destinationActivationRevision = get("destination_activation_revision");
  const destinationActivationEpoch = get("destination_activation_epoch");
  const conflictReason = get("control_conflict_reason");
  const conflictAt = get("control_conflict_at_revision");
  const lifecycleState = get("lifecycle_state");
  const deletionEpoch = get("deletion_epoch");
  const accountGeneration = get("account_generation");
  const controlHash = get("control_content_hash");
  const credentialHash = get("credential_content_hash");
  const grantHash = get("grant_content_hash");
  const credentialGenerationValue = counter(credentialGeneration);
  const credentialExpiryValue = nullableCounter(credentialExpiry);
  const grantVersionValue = counter(grantVersion);
  const controlRevisionValue = counter(controlRevision);
  const accountEpochValue = nullableCounter(accountEpoch);
  const destinationActivationRevisionValue = nullableCounter(destinationActivationRevision);
  const destinationActivationEpochValue = nullableCounter(destinationActivationEpoch);
  const conflictAtValue = nullableCounter(conflictAt);
  const deletionEpochValue = nullableCounter(deletionEpoch);

  if (projectId !== request.firebase_project_id
    || uid !== request.firebase_uid
    || applicationId !== request.application_id
    || capability !== request.capability
    || !token(principalId)
    || !token(accountId, MAX_ACCOUNT_CODE_UNITS)
    || !token(credentialId)
    || credentialGenerationValue === undefined
    || typeof credentialLifecycle !== "string" || !AUTHORITY_LIFECYCLES.has(credentialLifecycle)
    || !token(authenticationStrength)
    || credentialExpiryValue === undefined
    || !token(grantId)
    || grantVersionValue === undefined
    || typeof grantLifecycle !== "string" || !AUTHORITY_LIFECYCLES.has(grantLifecycle)
    || typeof grantEnabled !== "boolean"
    || controlRevisionValue === undefined
    || accountEpochValue === undefined
    || destinationActivationRevisionValue === undefined
    || destinationActivationEpochValue === undefined
    || !nullableToken(conflictReason)
    || conflictAtValue === undefined
    || (conflictReason === null) !== (conflictAtValue === null)
    || typeof lifecycleState !== "string" || !ACCOUNT_LIFECYCLES.has(lifecycleState)
    || deletionEpochValue === undefined
    || (lifecycleState === "active") !== (deletionEpochValue === null)
    || typeof accountGeneration !== "string" || !ACCOUNT_GENERATIONS.has(accountGeneration)
    || typeof controlHash !== "string" || !DIGEST.test(controlHash)
    || typeof credentialHash !== "string" || !DIGEST.test(credentialHash)
    || typeof grantHash !== "string" || !DIGEST.test(grantHash)) return null;

  const digestRow: AuthorityStateRow = {
    account_id: accountId,
    principal_id: principalId,
    application_id: applicationId,
    credential_id: credentialId,
    credential_generation: credentialGenerationValue,
    capability,
    grant_id: grantId,
    grant_version: grantVersionValue,
    account_epoch: accountEpochValue,
    control_conflict_reason: conflictReason,
    control_conflict_at_revision: conflictAtValue,
    destination_activation_epoch: destinationActivationEpochValue,
    destination_activation_revision: destinationActivationRevisionValue,
    lifecycle_state: lifecycleState as AuthorityStateRow["lifecycle_state"],
    deletion_epoch: deletionEpochValue,
    account_generation: accountGeneration as AuthorityStateRow["account_generation"],
    credential_lifecycle: credentialLifecycle as AuthorityStateRow["credential_lifecycle"],
    grant_lifecycle: grantLifecycle as AuthorityStateRow["grant_lifecycle"],
    grant_enabled: grantEnabled,
    authentication_strength: authenticationStrength,
    credential_expires_at_epoch_seconds: credentialExpiryValue,
    control_revision: controlRevisionValue,
    control_content_hash: controlHash,
    credential_content_hash: credentialHash,
    grant_content_hash: grantHash,
    db_now_epoch_seconds: 0,
  };

  return Object.freeze({
    status: "current" as const,
    firebase_project_id: projectId,
    firebase_uid: uid,
    principal_id: principalId,
    account_id: accountId,
    application_id: applicationId,
    credential_id: credentialId,
    credential_generation: credentialGenerationValue,
    credential_lifecycle: credentialLifecycle,
    authentication_strength: authenticationStrength,
    credential_expires_at_epoch_seconds: credentialExpiryValue,
    capability,
    grant_id: grantId,
    grant_version: grantVersionValue,
    grant_lifecycle: grantLifecycle,
    grant_enabled: grantEnabled,
    authorization_state_digest: authorizationStateDigest(digestRow),
    control_revision: controlRevisionValue,
    account_epoch: accountEpochValue,
    destination_activation_revision: destinationActivationRevisionValue,
  });
};

/**
 * Inert fixed-query adapter for the strict service-owned authorization source.
 * A future runtime may provide the narrow query port only after PostgreSQL is
 * ratified; this module does not construct a pool or activate a route.
 */
export const createPostgresFirebaseApplicationAuthorizationSource = (
  queryPort: FirebaseApplicationAuthorizationQueryPort,
): PostgresFirebaseApplicationAuthorizationSource => {
  const query = snapshotQuery(queryPort);
  if (query === null) throw new TypeError("invalid Firebase authorization query port");

  return Object.freeze({
    async load(requestValue: unknown): Promise<unknown> {
      const request = parseRequest(requestValue);
      if (request === null) return unavailable;
      let rawRows: unknown;
      try {
        const statement: SqlStatement = Object.freeze({
          name: "firebase_authorization.lookup_current",
          text: LOOKUP_FIREBASE_APPLICATION_AUTHORIZATION,
          values: Object.freeze([
            request.firebase_project_id,
            request.firebase_uid,
            request.application_id,
            request.capability,
          ]),
        });
        rawRows = await query.method.call(query.receiver, statement);
      } catch {
        return unavailable;
      }
      const rows = rowsArray(rawRows);
      if (rows === null || rows.length > 1) return unavailable;
      if (rows.length === 0) return absent;
      return parseCurrent(rows[0], request) ?? unavailable;
    },
  });
};
