import { isProxy } from "node:util/types";

import {
  composeFirebaseApplicationAuthorization,
  type FirebaseApplicationAuthorizationConfig,
  type FirebaseApplicationAuthorizationSource,
  type FirebaseApplicationAuthorizer,
} from "../auth/firebase-application-authorization";
import {
  createFirebaseIdentityVerifier,
  type FirebaseIdentityRuntimeMode,
  type FirebaseIdTokenVerificationAdapter,
} from "../auth/firebase-identity";
import type { ApplicationAccountControlSource } from "../control/application-control-source";

export interface FirebaseMemoryAuthorizationCompositionConfig {
  readonly project_id: string;
  readonly runtime_mode: FirebaseIdentityRuntimeMode;
  readonly id_token_adapter: FirebaseIdTokenVerificationAdapter;
  readonly authorization_source: FirebaseApplicationAuthorizationSource;
  readonly control_source: ApplicationAccountControlSource;
  readonly application_id: string;
  readonly capability: string;
  readonly context_ttl_seconds: number;
}

const fail = (): never => {
  throw new TypeError("invalid Firebase memory authorization composition");
};

const exactRecord = (
  value: unknown,
  expected: readonly string[],
): Readonly<Record<string, PropertyDescriptor & { readonly value: unknown }>> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail();
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const keys = Reflect.ownKeys(descriptors);
  if (keys.some((key) => typeof key !== "string")) fail();
  const actual = (keys as string[]).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length
    || actual.some((key, index) => key !== wanted[index])) fail();
  for (const key of actual) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail();
  }
  return descriptors as Readonly<Record<string, PropertyDescriptor & { readonly value: unknown }>>;
};

/**
 * The route-free identity -> application grant -> account-control assembly.
 * Driver creation and request-token extraction remain outside this boundary.
 */
export const composeFirebaseMemoryAuthorization = (
  configValue: FirebaseMemoryAuthorizationCompositionConfig,
): FirebaseApplicationAuthorizer => {
  const config = exactRecord(configValue, [
    "project_id", "runtime_mode", "id_token_adapter", "authorization_source",
    "control_source", "application_id", "capability", "context_ttl_seconds",
  ]);
  const identityVerifier = createFirebaseIdentityVerifier({
    project_id: config.project_id!.value as string,
    runtime_mode: config.runtime_mode!.value as FirebaseIdentityRuntimeMode,
    adapter: config.id_token_adapter!.value as FirebaseIdTokenVerificationAdapter,
  });
  const authorizationConfig: FirebaseApplicationAuthorizationConfig = {
    identity_verifier: identityVerifier,
    authorization_source: config.authorization_source!.value as FirebaseApplicationAuthorizationSource,
    control_source: config.control_source!.value as ApplicationAccountControlSource,
    application_id: config.application_id!.value as string,
    capability: config.capability!.value as string,
    context_ttl_seconds: config.context_ttl_seconds!.value as number,
  };
  return composeFirebaseApplicationAuthorization(authorizationConfig);
};
