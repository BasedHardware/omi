import { expect, test } from "bun:test";

import {
  DURABLE_MEMORY_WORK_VERSION,
  DurableMemoryWorkTransitionError,
  acceptDurableMemoryWork,
  acceptedDurableMemoryWorkDigest,
  expireDurableMemoryWorkLease,
  failDurableMemoryWork,
  leaseDurableMemoryWork,
  ownsDurableMemoryWorkLease,
  parseDurableMemoryWorkJob,
  succeedDurableMemoryWork,
  type AcceptedDurableMemoryWork,
} from "./state-machine";

const accepted = (overrides: Partial<AcceptedDurableMemoryWork> = {}): AcceptedDurableMemoryWork => ({
  version: DURABLE_MEMORY_WORK_VERSION,
  job_id: "job:formation:one",
  owner_account_id: "account:alice",
  account_epoch: 7,
  lifecycle_state: "active",
  deletion_epoch: null,
  work_kind: "formation",
  input_frontier: "frontier:one",
  input_digest: "1".repeat(64),
  execution_contract_digest: "2".repeat(64),
  accepted_at_event_time: 100,
  max_attempts: 3,
  ...overrides,
});

const expectCode = (code: DurableMemoryWorkTransitionError["code"]) => ({ code, message: code });

test("P3 accepted work is exact, frozen, digest-bound, and contains no raw output/error fields", () => {
  const job = acceptDurableMemoryWork(accepted());
  expect(job).toMatchObject({ state: "pending", attempt: 0, lease_fence: 0, lease: null, outcome: null });
  expect(Object.isFrozen(job)).toBe(true);
  expect(job.accepted_work_digest).toBe(acceptedDurableMemoryWorkDigest(accepted()));
  expect(Object.keys(job)).not.toContain("model_output");
  expect(Object.keys(job)).not.toContain("last_error");
  expect(() => acceptDurableMemoryWork({ ...accepted(), extra: true } as never)).toThrow(expectCode("invalid_job"));
  expect(() => acceptDurableMemoryWork({ ...accepted(), input_digest: "raw transcript" })).toThrow(expectCode("invalid_job"));
  expect(() => acceptDurableMemoryWork({ ...accepted(), max_attempts: 0 })).toThrow(expectCode("invalid_job"));
  const accessor = accepted() as unknown as Record<string, unknown>;
  Object.defineProperty(accessor, "job_id", { enumerable: true, get: () => { throw new Error("must not run"); } });
  expect(() => acceptDurableMemoryWork(accessor as never)).toThrow(expectCode("invalid_job"));
  expect(() => acceptDurableMemoryWork(new Proxy(accepted(), {}) as never)).toThrow(expectCode("invalid_job"));
});

test("P3 every accepted authority/input/contract coordinate changes the work digest", () => {
  const base = acceptedDurableMemoryWorkDigest(accepted());
  for (const changed of [
    accepted({ owner_account_id: "account:bob" }),
    accepted({ account_epoch: 8 }),
    accepted({ input_frontier: "frontier:two" }),
    accepted({ input_digest: "3".repeat(64) }),
    accepted({ execution_contract_digest: "4".repeat(64) }),
    accepted({ work_kind: "promotion" }),
    accepted({ accepted_at_event_time: 101 }),
    accepted({ max_attempts: 4 }),
  ]) expect(acceptedDurableMemoryWorkDigest(changed)).not.toBe(base);
});

test("P3 leases are half-open, fenced, and reclaim only after recording worker loss", () => {
  const first = leaseDurableMemoryWork(acceptDurableMemoryWork(accepted()), "worker:one", 100, 10);
  expect(first).toMatchObject({ state: "leased", attempt: 1, lease_fence: 1, lease: { fence: 1, leased_at_event_time: 100, expires_at_event_time: 110 } });
  expect(ownsDurableMemoryWorkLease(first, { worker_id: "worker:one", fence: 1 }, 109)).toBe(true);
  expect(ownsDurableMemoryWorkLease(first, { worker_id: "worker:one", fence: 1 }, 110)).toBe(false);
  expect(ownsDurableMemoryWorkLease(first, { worker_id: "worker:two", fence: 1 }, 109)).toBe(false);
  expect(() => leaseDurableMemoryWork(first, "worker:two", 109, 10)).toThrow(expectCode("not_yet_eligible"));
  expect(() => leaseDurableMemoryWork(first, "worker:two", 110, 10)).toThrow(expectCode("expired_lease_requires_recovery"));
  const lost = expireDurableMemoryWorkLease(first, 110, 111);
  const reclaimed = leaseDurableMemoryWork(lost, "worker:two", 111, 10);
  expect(reclaimed).toMatchObject({ state: "leased", attempt: 2, lease_fence: 2, lease: { worker_id: "worker:two", fence: 2 } });
  expect(ownsDurableMemoryWorkLease(reclaimed, { worker_id: "worker:one", fence: 1 }, 110)).toBe(false);
  expect(() => leaseDurableMemoryWork(acceptDurableMemoryWork(accepted()), "worker:one", 99, 10)).toThrow(expectCode("not_yet_eligible"));
});

test("P3 retry remains durable work and becomes dead exactly at the attempt budget", () => {
  const first = leaseDurableMemoryWork(acceptDurableMemoryWork(accepted({ max_attempts: 2 })), "worker:one", 100, 10);
  const retry = failDurableMemoryWork(first, { worker_id: "worker:one", fence: 1 }, 105, "model_timeout", 120);
  expect(retry).toMatchObject({ state: "retryable_failed", attempt: 1, outcome: { kind: "retryable_error", error_code: "model_timeout", next_eligible_event_time: 120 } });
  expect(JSON.stringify(retry)).not.toContain("abstain");
  expect(JSON.stringify(retry)).not.toContain("delete");
  expect(() => leaseDurableMemoryWork(retry, "worker:two", 119, 10)).toThrow(expectCode("not_yet_eligible"));
  const second = leaseDurableMemoryWork(retry, "worker:two", 120, 10);
  const dead = failDurableMemoryWork(second, { worker_id: "worker:two", fence: 2 }, 125, "model_response_invalid", null);
  expect(dead).toMatchObject({ state: "dead_letter", attempt: 2, outcome: { kind: "dead_letter", attempts: 2, error_code: "model_response_invalid" } });
  expect(() => leaseDurableMemoryWork(dead, "worker:three", 1_000, 10)).toThrow(expectCode("ineligible_state"));
});

test("P3 stale and expired workers can neither succeed nor fail", () => {
  const leased = leaseDurableMemoryWork(acceptDurableMemoryWork(accepted()), "worker:one", 100, 10);
  expect(() => succeedDurableMemoryWork(leased, { worker_id: "worker:two", fence: 1 }, 105, "successful", "3".repeat(64), "4".repeat(64)))
    .toThrow(expectCode("stale_lease"));
  expect(() => failDurableMemoryWork(leased, { worker_id: "worker:one", fence: 1 }, 110, "worker_lost", 120))
    .toThrow(expectCode("stale_lease"));
  expect(() => succeedDurableMemoryWork(leased, { worker_id: "worker:one", fence: 1 }, 105, "successful", "raw", "4".repeat(64)))
    .toThrow(expectCode("invalid_transition"));
});

test("P3 an expired final worker becomes dead work instead of a stranded lease", () => {
  const finalLease = leaseDurableMemoryWork(
    acceptDurableMemoryWork(accepted({ max_attempts: 1 })),
    "worker:one",
    100,
    10,
  );
  expect(() => expireDurableMemoryWorkLease(finalLease, 109, null)).toThrow(expectCode("not_yet_eligible"));
  const dead = expireDurableMemoryWorkLease(finalLease, 110, null);
  expect(dead).toMatchObject({
    state: "dead_letter",
    lease: null,
    outcome: { kind: "dead_letter", error_code: "worker_lost", attempts: 1 },
  });
  const retryLease = leaseDurableMemoryWork(
    acceptDurableMemoryWork(accepted({ max_attempts: 2 })),
    "worker:one",
    100,
    10,
  );
  expect(expireDurableMemoryWorkLease(retryLease, 110, 120)).toMatchObject({
    state: "retryable_failed",
    outcome: { kind: "retryable_error", error_code: "worker_lost", next_eligible_event_time: 120 },
  });
});

test("P3 successful-empty is a terminal durable result and persisted rows revalidate", () => {
  const leased = leaseDurableMemoryWork(acceptDurableMemoryWork(accepted()), "worker:one", 100, 10);
  const succeeded = succeedDurableMemoryWork(
    leased,
    { worker_id: "worker:one", fence: 1 },
    105,
    "successful_empty",
    "3".repeat(64),
    "4".repeat(64),
  );
  expect(succeeded).toMatchObject({ state: "succeeded", lease: null, outcome: { kind: "succeeded", result_kind: "successful_empty" } });
  expect(parseDurableMemoryWorkJob(structuredClone(succeeded))).toEqual(succeeded);
  expect(() => leaseDurableMemoryWork(succeeded, "worker:two", 200, 10)).toThrow(expectCode("ineligible_state"));
  expect(() => parseDurableMemoryWorkJob({ ...succeeded, accepted_work_digest: "5".repeat(64) })).toThrow(expectCode("invalid_job"));
  expect(() => parseDurableMemoryWorkJob({ ...succeeded, outcome: { ...succeeded.outcome, raw_error: "secret" } })).toThrow(expectCode("invalid_job"));
});
