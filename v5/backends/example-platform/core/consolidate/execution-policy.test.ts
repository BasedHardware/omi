import { describe, expect, test } from "bun:test";

import {
  DURABLE_MEMORY_WORK_EXECUTION_POLICY_VERSION,
  durableMemoryWorkExecutionPolicyDigest,
  durableMemoryWorkRetryDelaySeconds,
  parseRegisteredDurableMemoryWorkExecutionPolicy,
  registerDurableMemoryWorkExecutionPolicy,
  type DurableMemoryWorkExecutionPolicyInput,
} from "./execution-policy";

const policy = (overrides: Partial<DurableMemoryWorkExecutionPolicyInput> = {}) => ({
  version: DURABLE_MEMORY_WORK_EXECUTION_POLICY_VERSION,
  policy_id: "execution-policy:formation:v1",
  work_kind: "formation" as const,
  execution_contract_digest: "a".repeat(64),
  max_attempts: 3,
  lease_duration_seconds: 60,
  retry_delays_seconds: [10, 30],
  ...overrides,
});

describe("durable memory work execution policy", () => {
  test("registers one exact bounded policy with no implicit timing default", () => {
    const registered = registerDurableMemoryWorkExecutionPolicy(policy());
    expect(registered.policy_digest).toBe(durableMemoryWorkExecutionPolicyDigest(policy()));
    expect(parseRegisteredDurableMemoryWorkExecutionPolicy(structuredClone(registered)))
      .toEqual(registered);
    expect(Object.isFrozen(registered)).toBe(true);
    expect(Object.isFrozen(registered.retry_delays_seconds)).toBe(true);
    expect(durableMemoryWorkRetryDelaySeconds(registered, 1)).toBe(10);
    expect(durableMemoryWorkRetryDelaySeconds(registered, 2)).toBe(30);
    expect(durableMemoryWorkRetryDelaySeconds(registered, 3)).toBeNull();
  });

  test("every scheduling and strategy coordinate changes immutable policy identity", () => {
    const baseline = durableMemoryWorkExecutionPolicyDigest(policy());
    for (const changed of [
      policy({ policy_id: "execution-policy:formation:v2" }),
      policy({ work_kind: "promotion" }),
      policy({ execution_contract_digest: "b".repeat(64) }),
      policy({ max_attempts: 2, retry_delays_seconds: [10] }),
      policy({ lease_duration_seconds: 61 }),
      policy({ retry_delays_seconds: [11, 30] }),
    ]) expect(durableMemoryWorkExecutionPolicyDigest(changed)).not.toBe(baseline);
  });

  test("attempt budgets and all timing values are explicit and bounded", () => {
    for (const invalid of [
      policy({ max_attempts: 0, retry_delays_seconds: [] }),
      policy({ max_attempts: 101, retry_delays_seconds: Array(100).fill(1) }),
      policy({ max_attempts: 1, retry_delays_seconds: [1] }),
      policy({ max_attempts: 2, retry_delays_seconds: [] }),
      policy({ lease_duration_seconds: 0 }),
      policy({ lease_duration_seconds: 3_601 }),
      policy({ retry_delays_seconds: [0, 30] }),
      policy({ retry_delays_seconds: [10, 86_401] }),
    ]) expect(() => registerDurableMemoryWorkExecutionPolicy(invalid)).toThrow("invalid_policy");
  });

  test("hostile containers and forged digests fail before policy use", () => {
    expect(() => registerDurableMemoryWorkExecutionPolicy({
      ...policy(), extra: true,
    } as never)).toThrow("invalid_policy");
    expect(() => registerDurableMemoryWorkExecutionPolicy(new Proxy(policy(), {}) as never))
      .toThrow("invalid_policy");
    const accessor = policy() as unknown as Record<string, unknown>;
    Object.defineProperty(accessor, "policy_id", {
      enumerable: true, get: () => { throw new Error("must not execute"); },
    });
    expect(() => registerDurableMemoryWorkExecutionPolicy(accessor as never))
      .toThrow("invalid_policy");
    const registered = registerDurableMemoryWorkExecutionPolicy(policy());
    expect(() => parseRegisteredDurableMemoryWorkExecutionPolicy({
      ...registered, policy_digest: "b".repeat(64),
    })).toThrow("policy_digest_mismatch");
    expect(() => durableMemoryWorkRetryDelaySeconds(registered, 0)).toThrow("invalid_attempt");
  });
});
