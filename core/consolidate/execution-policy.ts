import { isProxy } from "node:util/types";

import { sha256CanonicalContent } from "../retrieve/content-digest";
import type { DurableMemoryWorkKind } from "./state-machine";

export const DURABLE_MEMORY_WORK_EXECUTION_POLICY_VERSION =
  "durable-memory-work-execution-policy-v1" as const;

export interface DurableMemoryWorkExecutionPolicyInput {
  readonly version: typeof DURABLE_MEMORY_WORK_EXECUTION_POLICY_VERSION;
  readonly policy_id: string;
  readonly work_kind: DurableMemoryWorkKind;
  readonly execution_contract_digest: string;
  readonly max_attempts: number;
  readonly lease_duration_seconds: number;
  readonly retry_delays_seconds: readonly number[];
}

export interface RegisteredDurableMemoryWorkExecutionPolicy
  extends DurableMemoryWorkExecutionPolicyInput {
  readonly policy_digest: string;
}

const TOKEN = /^[\x21-\x7e]{1,256}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const WORK_KINDS = new Set<DurableMemoryWorkKind>([
  "formation", "promotion", "identity_cluster", "predicate_batch",
]);
const MAX_ATTEMPTS = 100;
const MAX_LEASE_SECONDS = 3_600;
const MAX_RETRY_DELAY_SECONDS = 86_400;

const fail = (code: string): never => {
  throw new TypeError(`durable work execution policy ${code}`);
};

const exactRecord = (value: unknown, keys: readonly string[]): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_policy");
  const ownKeys = Reflect.ownKeys(value);
  if (ownKeys.some((key) => typeof key !== "string")) fail("invalid_policy");
  const actual = (ownKeys as string[]).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length
    || actual.some((key, index) => key !== expected[index])) fail("invalid_policy");
  for (const key of actual) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail("invalid_policy");
  }
  return value as Record<string, unknown>;
};

const exactArray = (value: unknown, maximum: number): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Array.prototype || value.length > maximum) {
    fail("invalid_policy");
  }
  const keys = Reflect.ownKeys(value);
  if (keys.length !== value.length + 1
    || keys.some((key) => typeof key !== "string"
      || (key !== "length" && (!/^(0|[1-9]\d*)$/.test(key) || Number(key) >= value.length)))) {
    fail("invalid_policy");
  }
  const output: unknown[] = [];
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail("invalid_policy");
    output.push(descriptor.value);
  }
  return output;
};

const boundedPositive = (value: unknown, maximum: number): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 1 || (value as number) > maximum) {
    fail("invalid_policy");
  }
  return value as number;
};

const normalize = (value: unknown): Readonly<DurableMemoryWorkExecutionPolicyInput> => {
  const input = exactRecord(value, [
    "version", "policy_id", "work_kind", "execution_contract_digest",
    "max_attempts", "lease_duration_seconds", "retry_delays_seconds",
  ]);
  if (input["version"] !== DURABLE_MEMORY_WORK_EXECUTION_POLICY_VERSION
    || typeof input["policy_id"] !== "string" || !TOKEN.test(input["policy_id"])
    || typeof input["work_kind"] !== "string"
    || !WORK_KINDS.has(input["work_kind"] as DurableMemoryWorkKind)
    || typeof input["execution_contract_digest"] !== "string"
    || !DIGEST.test(input["execution_contract_digest"])) fail("invalid_policy");
  const maxAttempts = boundedPositive(input["max_attempts"], MAX_ATTEMPTS);
  const retryDelays = exactArray(input["retry_delays_seconds"], MAX_ATTEMPTS - 1)
    .map((delay) => boundedPositive(delay, MAX_RETRY_DELAY_SECONDS));
  if (retryDelays.length !== maxAttempts - 1) fail("invalid_policy");
  return Object.freeze({
    version: DURABLE_MEMORY_WORK_EXECUTION_POLICY_VERSION,
    policy_id: input["policy_id"],
    work_kind: input["work_kind"] as DurableMemoryWorkKind,
    execution_contract_digest: input["execution_contract_digest"],
    max_attempts: maxAttempts,
    lease_duration_seconds: boundedPositive(input["lease_duration_seconds"], MAX_LEASE_SECONDS),
    retry_delays_seconds: Object.freeze(retryDelays),
  });
};

export const durableMemoryWorkExecutionPolicyDigest = (
  value: DurableMemoryWorkExecutionPolicyInput,
): string => sha256CanonicalContent(normalize(value));

export const registerDurableMemoryWorkExecutionPolicy = (
  value: DurableMemoryWorkExecutionPolicyInput,
): Readonly<RegisteredDurableMemoryWorkExecutionPolicy> => {
  const policy = normalize(value);
  return Object.freeze({
    ...policy,
    policy_digest: sha256CanonicalContent(policy),
  });
};

export const parseRegisteredDurableMemoryWorkExecutionPolicy = (
  value: unknown,
): Readonly<RegisteredDurableMemoryWorkExecutionPolicy> => {
  const input = exactRecord(value, [
    "version", "policy_id", "work_kind", "execution_contract_digest",
    "max_attempts", "lease_duration_seconds", "retry_delays_seconds", "policy_digest",
  ]);
  const policy = normalize({
    version: input["version"], policy_id: input["policy_id"], work_kind: input["work_kind"],
    execution_contract_digest: input["execution_contract_digest"],
    max_attempts: input["max_attempts"], lease_duration_seconds: input["lease_duration_seconds"],
    retry_delays_seconds: input["retry_delays_seconds"],
  });
  if (typeof input["policy_digest"] !== "string" || !DIGEST.test(input["policy_digest"])
    || input["policy_digest"] !== sha256CanonicalContent(policy)) fail("policy_digest_mismatch");
  return Object.freeze({ ...policy, policy_digest: input["policy_digest"] });
};

/** Delay after a failed 1-based attempt, or null when the budget is exhausted. */
export const durableMemoryWorkRetryDelaySeconds = (
  policyValue: RegisteredDurableMemoryWorkExecutionPolicy,
  failedAttempt: number,
): number | null => {
  const policy = parseRegisteredDurableMemoryWorkExecutionPolicy(policyValue);
  if (!Number.isSafeInteger(failedAttempt) || failedAttempt < 1
    || failedAttempt > policy.max_attempts) fail("invalid_attempt");
  return failedAttempt === policy.max_attempts
    ? null
    : policy.retry_delays_seconds[failedAttempt - 1]!;
};
