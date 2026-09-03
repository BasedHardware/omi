import { describe, expect, it } from "vitest";
import {
  adoptOnIdentity,
  backendOutboxRetryAtMs,
  decideAttempt,
  drainIsolated,
  JOURNAL_OUTBOX_POLICY,
  oldestReadyAgeMs,
  type ProcessOutcome,
} from "../src/runtime/durable-queue.js";

describe("durable-queue substrate", () => {
  it("one poison item does not block the item behind it", () => {
    const processed: string[] = [];
    const results = drainIsolated(["poison", "healthy"], (item) => {
      processed.push(item);
      if (item === "poison") throw new Error("canonical hash mismatch");
      return { kind: "ack" };
    });
    expect(processed).toEqual(["poison", "healthy"]);
    expect(results[0]?.outcome.kind).toBe("reject");
    expect(results[0]?.raised).toBe(true);
    expect(results[0]?.outcome.kind === "reject" && results[0].outcome.errorText).toContain("canonical hash mismatch");
    expect(results[1]?.outcome.kind).toBe("ack");
  });

  it("poison reaches the dead letter within the attempt budget with its error text", () => {
    const rejected = decideAttempt({
      attemptCount: 1,
      outcome: { kind: "reject", errorText: "canonical hash mismatch", reason: "malformed" },
      policy: JOURNAL_OUTBOX_POLICY,
      nowMs: 1_000,
    });
    expect(rejected.terminal).toBe(true);
    expect(rejected.status).toBe("dead_letter");
    expect(rejected.errorText).toBe("canonical hash mismatch");

    const lastRetry = decideAttempt({
      attemptCount: 5,
      outcome: { kind: "retry", errorText: "backend_sync_failed", reason: "backend_sync_failed" },
      policy: JOURNAL_OUTBOX_POLICY,
      nowMs: 1_000,
    });
    expect(lastRetry.terminal).toBe(true);
    expect(lastRetry.errorText).toBe("backend_sync_failed");
  });

  it("a duplicate by identity is adopted, not raised", () => {
    expect(adoptOnIdentity(undefined, "turn-1")).toEqual({ adopted: false });
    expect(adoptOnIdentity("turn-1", "turn-1")).toEqual({ adopted: true });
    expect(() => adoptOnIdentity("turn-other", "turn-1")).toThrow(/identity mismatch/);
  });

  it("the age gauge reflects the oldest ready item", () => {
    expect(oldestReadyAgeMs([8_000, 3_000, 9_000], 10_000)).toBe(7_000);
    expect(oldestReadyAgeMs([], 10_000)).toBeNull();
  });

  it("retryable backend codes stay retrying and 4xx-class codes dead-letter", () => {
    expect(backendOutboxRetryAtMs({
      attemptCount: 1,
      errorCode: "backend_sync_failed",
      nowMs: 0,
    })).toBe(1_000);
    expect(backendOutboxRetryAtMs({
      attemptCount: 1,
      errorCode: "backend_sync_http_4xx",
      nowMs: 0,
    })).toBeUndefined();
  });

  it("failures are never acked", () => {
    const outcome: ProcessOutcome = { kind: "reject", errorText: "hard fail", reason: "conflict" };
    expect(drainIsolated(["x"], () => outcome)[0]?.outcome.kind).not.toBe("ack");
  });
});
