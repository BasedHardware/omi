import { describe, expect, it } from "vitest";

import {
  classifyError,
  ERROR_CATEGORIES,
  isExpectedAbort,
  logEvent,
  markOwnedAbort,
  retryDelayMs,
  USER_MESSAGES,
  withRetry,
} from "../errors.mjs";

describe("classifyError", () => {
  it("maps the observed error corpus to bounded categories", () => {
    expect(classifyError(new Error("429 rate limit exceeded")).category).toBe("transient");
    expect(classifyError(new Error("fetch failed: ECONNRESET")).category).toBe("transient");
    expect(classifyError(new Error('401 "invalid_token"')).category).toBe("auth");
    expect(classifyError(new Error("413 length limit exceeded")).category).toBe("invalid_request");
    expect(classifyError(new Error("undefined is not a function")).category).toBe("internal");
  });

  it("only transient is retryable", () => {
    expect(classifyError(new Error("529 overloaded")).retryable).toBe(true);
    expect(classifyError(new Error("401 unauthorized")).retryable).toBe(false);
  });
});

describe("owned aborts", () => {
  it("treats abort-shaped errors inside the grace window as expected, outside as not", () => {
    const abortErr = new Error("Operation aborted");
    markOwnedAbort(1_000_000);
    expect(isExpectedAbort(abortErr, 1_000_000 + 4_999)).toBe(true);
    expect(isExpectedAbort(abortErr, 1_000_000 + 5_001)).toBe(false);
    // Non-abort errors are never "expected aborts" even inside the window.
    expect(isExpectedAbort(new Error("boom"), 1_000_000 + 1)).toBe(false);
  });
});

describe("retryDelayMs", () => {
  it("doubles with a cap and bounded jitter", () => {
    const noJitter = () => 0.5;
    expect(retryDelayMs(1, noJitter)).toBe(500);
    expect(retryDelayMs(2, noJitter)).toBe(1000);
    expect(retryDelayMs(10, noJitter)).toBe(32_000);
  });
});

describe("withRetry", () => {
  it("retries transient errors and eventually succeeds", async () => {
    let calls = 0;
    const result = await withRetry(
      async () => {
        calls += 1;
        if (calls < 3) throw new Error("ETIMEDOUT connecting");
        return "ok";
      },
      { attempts: 3, onRetry: () => {} },
    );
    expect(result).toBe("ok");
    expect(calls).toBe(3);
  }, 15_000);

  it("does not retry non-retryable categories", async () => {
    let calls = 0;
    await expect(
      withRetry(async () => {
        calls += 1;
        throw new Error("401 unauthorized");
      }),
    ).rejects.toThrow("401");
    expect(calls).toBe(1);
  });
});

describe("logEvent", () => {
  it("emits one JSON line with full error detail", () => {
    const lines = [];
    const err = new Error("kaboom");
    err.code = "E_TEST";
    logEvent("error", "unit_test", { error: err, turnId: "t1" }, (l) => lines.push(l));
    const parsed = JSON.parse(lines[0]);
    expect(parsed.event).toBe("unit_test");
    expect(parsed.turnId).toBe("t1");
    expect(parsed.error.message).toBe("kaboom");
    expect(parsed.error.code).toBe("E_TEST");
    expect(parsed.error.stack).toContain("kaboom");
  });

  it("never throws on an unserializable (circular) record", () => {
    // logEvent runs inside catch blocks and the unhandledRejection handler; a
    // circular ref must degrade to a fallback line, not raise a fresh error.
    const lines = [];
    const err = new Error("loop");
    err.self = err; // circular
    expect(() => logEvent("error", "circular", { error: err }, (l) => lines.push(l))).not.toThrow();
    const parsed = JSON.parse(lines[0]);
    expect(parsed.event).toBe("circular");
    expect(parsed.log_error).toBe("record not serializable");
  });
});

describe("USER_MESSAGES", () => {
  it("has calm copy for every error category (no fallthrough to internal)", () => {
    for (const category of ERROR_CATEGORIES) {
      expect(typeof USER_MESSAGES[category], `missing copy for '${category}'`).toBe("string");
      expect(USER_MESSAGES[category].length).toBeGreaterThan(0);
    }
  });
});
