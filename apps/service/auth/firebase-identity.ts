import { isProxy } from "node:util/types";

const MAX_PROJECT_ID_CODE_UNITS = 128;
const MAX_FIREBASE_UID_CODE_UNITS = 128;
const MAX_TOKEN_BYTES = 16_384;
const MAX_DECODED_CLAIMS = 128;
const JWT_PART = /^[A-Za-z0-9_-]+$/;
const PROJECT_ID = /^[A-Za-z0-9._:-]+$/;

export type FirebaseIdentityRuntimeMode = "deployed" | "local_test";
export type FirebaseIdentityVerificationSource = "firebase_production" | "firebase_auth_emulator";

export interface FirebaseIdTokenVerificationAdapter {
  readonly verification_source: FirebaseIdentityVerificationSource;
  verifyIdToken(token: string, checkRevoked: true): Promise<unknown>;
}

export interface FirebaseIdentityVerifierConfig {
  readonly project_id: string;
  readonly runtime_mode: FirebaseIdentityRuntimeMode;
  readonly adapter: FirebaseIdTokenVerificationAdapter;
}

export interface FirebaseIdentity {
  readonly firebase_project_id: string;
  readonly firebase_uid: string;
  readonly authentication_strength: "firebase-id-token";
  readonly expires_at_epoch_seconds: number;
}

export interface FirebaseIdentityVerifier {
  resolve(token: string, nowEpochSeconds: number): Promise<FirebaseIdentity | null>;
}

type DataDescriptors = Readonly<
  Record<string, PropertyDescriptor & { readonly value: unknown }>
>;

type Reject = (message: string) => never;

const configurationError: Reject = (message) => {
  throw new TypeError(message);
};

const exactDataDescriptors = (
  value: unknown,
  keys: readonly string[],
  reject: Reject,
): DataDescriptors => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) return reject("expected exact plain data");
  const ownKeys = Reflect.ownKeys(value);
  if (ownKeys.some((key) => typeof key !== "string")) return reject("symbol fields are forbidden");
  const actual = (ownKeys as string[]).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length
    || actual.some((key, index) => key !== expected[index])) return reject("unexpected fields");
  const descriptors = Object.getOwnPropertyDescriptors(value);
  for (const key of actual) {
    const descriptor = descriptors[key];
    if (descriptor === undefined || !("value" in descriptor) || descriptor.enumerable !== true) {
      return reject("accessors and hidden fields are forbidden");
    }
  }
  return descriptors as DataDescriptors;
};

const decodedDataDescriptors = (value: unknown): DataDescriptors | null => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) return null;
  const ownKeys = Reflect.ownKeys(value);
  if (ownKeys.length > MAX_DECODED_CLAIMS || ownKeys.some((key) => typeof key !== "string")) return null;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  for (const key of ownKeys as string[]) {
    const descriptor = descriptors[key];
    if (descriptor === undefined || !("value" in descriptor) || descriptor.enumerable !== true) return null;
  }
  return descriptors as DataDescriptors;
};

const safeEpoch = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;

const validProjectId = (value: unknown): value is string =>
  typeof value === "string"
  && value.length >= 1
  && value.length <= MAX_PROJECT_ID_CODE_UNITS
  && PROJECT_ID.test(value);

const validUid = (value: unknown): value is string =>
  typeof value === "string"
  && value.length >= 1
  && value.length <= MAX_FIREBASE_UID_CODE_UNITS
  && !/[\u0000-\u001f\u007f]/.test(value);

const validTokenShape = (
  token: unknown,
  allowUnsignedEmulator: boolean,
): token is string => {
  if (typeof token !== "string" || Buffer.byteLength(token, "utf8") > MAX_TOKEN_BYTES) return false;
  const parts = token.split(".");
  if (parts.length !== 3) return false;
  const [header, payload, signature] = parts as [string, string, string];
  return JWT_PART.test(header)
    && JWT_PART.test(payload)
    && (JWT_PART.test(signature) || (allowUnsignedEmulator && signature.length === 0));
};

const parseIdentity = (
  value: unknown,
  projectId: string,
  nowEpochSeconds: number,
): FirebaseIdentity | null => {
  const descriptors = decodedDataDescriptors(value);
  if (descriptors === null) return null;
  for (const required of ["aud", "iss", "sub", "uid", "exp", "iat", "auth_time"] as const) {
    if (descriptors[required] === undefined) return null;
  }
  const audience = descriptors.aud!.value;
  const issuer = descriptors.iss!.value;
  const subject = descriptors.sub!.value;
  const uid = descriptors.uid!.value;
  const expiresAt = descriptors.exp!.value;
  const issuedAt = descriptors.iat!.value;
  const authenticatedAt = descriptors.auth_time!.value;
  if (audience !== projectId
    || issuer !== `https://securetoken.google.com/${projectId}`
    || !validUid(subject)
    || uid !== subject
    || !safeEpoch(expiresAt) || expiresAt <= nowEpochSeconds
    || !safeEpoch(issuedAt) || issuedAt > nowEpochSeconds
    || !safeEpoch(authenticatedAt) || authenticatedAt > nowEpochSeconds) return null;

  return Object.freeze({
    firebase_project_id: projectId,
    firebase_uid: subject,
    authentication_strength: "firebase-id-token",
    expires_at_epoch_seconds: expiresAt,
  });
};

/**
 * Builds an identity-only Firebase verifier over an injected cryptographic and
 * revocation-checking adapter. It cannot map the Firebase uid to an account or
 * construct application authorization.
 */
export const createFirebaseIdentityVerifier = (
  configValue: FirebaseIdentityVerifierConfig,
): FirebaseIdentityVerifier => {
  const config = exactDataDescriptors(
    configValue,
    ["project_id", "runtime_mode", "adapter"],
    configurationError,
  );
  const projectId = config.project_id!.value;
  const runtimeMode = config.runtime_mode!.value;
  if (!validProjectId(projectId)
    || (runtimeMode !== "deployed" && runtimeMode !== "local_test")) {
    return configurationError("invalid Firebase identity configuration");
  }

  const adapter = exactDataDescriptors(
    config.adapter!.value,
    ["verification_source", "verifyIdToken"],
    configurationError,
  );
  const verificationSource = adapter.verification_source!.value;
  const verifyIdToken = adapter.verifyIdToken!.value;
  if ((verificationSource !== "firebase_production"
      && verificationSource !== "firebase_auth_emulator")
    || typeof verifyIdToken !== "function" || isProxy(verifyIdToken)) {
    return configurationError("invalid Firebase identity adapter");
  }
  if (runtimeMode === "deployed" && verificationSource !== "firebase_production") {
    return configurationError("deployed Firebase identity forbids the Auth emulator");
  }
  const allowUnsignedEmulator = runtimeMode === "local_test"
    && verificationSource === "firebase_auth_emulator";
  const adapterObject = config.adapter!.value as FirebaseIdTokenVerificationAdapter;
  const verify = verifyIdToken as FirebaseIdTokenVerificationAdapter["verifyIdToken"];

  return Object.freeze({
    async resolve(token: string, nowEpochSeconds: number): Promise<FirebaseIdentity | null> {
      if (!safeEpoch(nowEpochSeconds) || !validTokenShape(token, allowUnsignedEmulator)) return null;
      let decoded: unknown;
      try {
        decoded = await verify.call(adapterObject, token, true);
      } catch {
        return null;
      }
      return parseIdentity(decoded, projectId, nowEpochSeconds);
    },
  });
};
