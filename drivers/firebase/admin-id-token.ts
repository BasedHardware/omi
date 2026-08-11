import { isProxy } from "node:util/types";

import {
  applicationDefault,
  deleteApp,
  initializeApp,
  type App,
} from "firebase-admin/app";
import { getAuth, type Auth } from "firebase-admin/auth";

const MAX_PROJECT_ID_CODE_UNITS = 128;
const MAX_APP_NAME_CODE_UNITS = 128;
const SAFE_COORDINATE = /^[A-Za-z0-9._:-]+$/;
const EMULATOR_ENV = "FIREBASE_AUTH_EMULATOR_HOST";

export type FirebaseAdminRuntimeMode = "deployed" | "local_test";
export type FirebaseAdminVerificationSource = "firebase_production" | "firebase_auth_emulator";

export interface FirebaseAdminIdTokenAdapterConfig {
  readonly project_id: string;
  readonly app_name: string;
  readonly runtime_mode: FirebaseAdminRuntimeMode;
}

export interface FirebaseAdminIdTokenAdapter {
  readonly verification_source: FirebaseAdminVerificationSource;
  verifyIdToken(token: string, checkRevoked: true): Promise<unknown>;
}

export interface FirebaseAdminIdTokenAdapterHandle {
  readonly adapter: FirebaseAdminIdTokenAdapter;
  close(): Promise<void>;
}

type DataDescriptors = Readonly<Record<string, PropertyDescriptor & { readonly value: unknown }>>;

const invalidConfiguration = (message: string): never => {
  throw new TypeError(message);
};

const exactDataDescriptors = (value: unknown, keys: readonly string[]): DataDescriptors => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) {
    return invalidConfiguration("invalid Firebase Admin adapter configuration");
  }
  const ownKeys = Reflect.ownKeys(value);
  if (ownKeys.some((key) => typeof key !== "string")) {
    return invalidConfiguration("invalid Firebase Admin adapter configuration");
  }
  const actual = (ownKeys as string[]).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length
    || actual.some((key, index) => key !== expected[index])) {
    return invalidConfiguration("invalid Firebase Admin adapter configuration");
  }
  const descriptors = Object.getOwnPropertyDescriptors(value);
  for (const key of actual) {
    const descriptor = descriptors[key];
    if (descriptor === undefined || !("value" in descriptor) || descriptor.enumerable !== true) {
      return invalidConfiguration("invalid Firebase Admin adapter configuration");
    }
  }
  return descriptors as DataDescriptors;
};

const validCoordinate = (value: unknown, max: number): value is string =>
  typeof value === "string"
  && value.length >= 1
  && value.length <= max
  && SAFE_COORDINATE.test(value);

const closedFailure = (): Error => new Error("firebase_admin_identity_unavailable");

const emulatorCoordinate = (): Readonly<{ readonly present: boolean; readonly value: string | null }> => {
  const present = Object.prototype.hasOwnProperty.call(process.env, EMULATOR_ENV);
  return Object.freeze({
    present,
    value: present ? process.env[EMULATOR_ENV] ?? null : null,
  });
};

/**
 * Creates one inert official Firebase Admin ID-token adapter. Firebase remains
 * identity-only: this driver has no account, grant, control, or route surface.
 */
export const createFirebaseAdminIdTokenAdapter = async (
  configValue: FirebaseAdminIdTokenAdapterConfig,
): Promise<FirebaseAdminIdTokenAdapterHandle> => {
  const config = exactDataDescriptors(
    configValue,
    ["project_id", "app_name", "runtime_mode"],
  );
  const projectId = config.project_id!.value;
  const appName = config.app_name!.value;
  const runtimeMode = config.runtime_mode!.value;
  if (!validCoordinate(projectId, MAX_PROJECT_ID_CODE_UNITS)
    || !validCoordinate(appName, MAX_APP_NAME_CODE_UNITS)
    || (runtimeMode !== "deployed" && runtimeMode !== "local_test")) {
    return invalidConfiguration("invalid Firebase Admin adapter configuration");
  }

  const emulator = emulatorCoordinate();
  if (runtimeMode === "deployed" && emulator.present) {
    return invalidConfiguration("deployed Firebase Admin adapter forbids the Auth emulator");
  }
  const verificationSource: FirebaseAdminVerificationSource = emulator.present
    ? "firebase_auth_emulator"
    : "firebase_production";

  let app: App | null = null;
  let auth: Auth;
  try {
    app = initializeApp({
      credential: applicationDefault(),
      projectId,
    }, appName);
    auth = getAuth(app);
  } catch {
    if (app !== null) {
      try {
        await deleteApp(app);
      } catch {
        // The public failure remains closed even if cleanup also fails.
      }
    }
    throw closedFailure();
  }

  let closed = false;
  const adapter: FirebaseAdminIdTokenAdapter = Object.freeze({
    verification_source: verificationSource,
    async verifyIdToken(token: string, checkRevoked: true): Promise<unknown> {
      const currentEmulator = emulatorCoordinate();
      if (closed || checkRevoked !== true
        || currentEmulator.present !== emulator.present
        || currentEmulator.value !== emulator.value) throw closedFailure();
      try {
        return await auth.verifyIdToken(token, true);
      } catch {
        throw closedFailure();
      }
    },
  });

  return Object.freeze({
    adapter,
    async close(): Promise<void> {
      if (closed) return;
      closed = true;
      try {
        await deleteApp(app);
      } catch {
        throw closedFailure();
      }
    },
  });
};
