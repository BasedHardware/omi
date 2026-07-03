import { describe, expect, it, vi } from "vitest";
import { executeWithFallback } from "../src/runtime/agent-fallback.js";
import type { RoutableAgentId } from "../src/runtime/agent-router.js";

const retryAll = () => true;

describe("executeWithFallback", () => {
  it("returns the first agent that succeeds", async () => {
    const order: RoutableAgentId[] = ["openclaw", "acp"];
    const result = await executeWithFallback(order, {
      runOne: async (agent) => `ran ${agent}`,
      isRetryable: retryAll,
    });
    expect(result.ok).toBe(true);
    expect(result.agent).toBe("openclaw");
    expect(result.value).toBe("ran openclaw");
    expect(result.attempts).toHaveLength(1);
  });

  // Demo case d: primary fails -> fallback triggers and the next agent runs.
  it("advances to the next agent when the primary fails retryably", async () => {
    const order: RoutableAgentId[] = ["openclaw", "hermes", "acp"];
    const log = vi.fn();
    const result = await executeWithFallback(order, {
      runOne: async (agent) => {
        if (agent === "openclaw") throw new Error("openclaw crashed");
        return `ran ${agent}`;
      },
      isRetryable: retryAll,
      log,
    });
    expect(result.ok).toBe(true);
    expect(result.agent).toBe("hermes");
    expect(result.attempts.map((a) => a.agent)).toEqual(["openclaw", "hermes"]);
    expect(result.attempts[0]).toMatchObject({ ok: false, retryable: true });
    // Fallback reason is logged.
    expect(log).toHaveBeenCalledWith(expect.stringContaining("falling back to hermes"));
  });

  it("stops immediately on a non-retryable failure", async () => {
    const order: RoutableAgentId[] = ["openclaw", "acp"];
    const result = await executeWithFallback(order, {
      runOne: async () => {
        throw new Error("bad request — user error");
      },
      isRetryable: () => false,
    });
    expect(result.ok).toBe(false);
    expect(result.attempts).toHaveLength(1); // did not try acp
    expect(result.attempts[0].retryable).toBe(false);
  });

  it("fails cleanly when every agent fails", async () => {
    const order: RoutableAgentId[] = ["openclaw", "hermes"];
    const result = await executeWithFallback(order, {
      runOne: async (agent) => {
        throw new Error(`${agent} down`);
      },
      isRetryable: retryAll,
    });
    expect(result.ok).toBe(false);
    expect(result.attempts).toHaveLength(2);
    expect(String((result.error as Error).message)).toContain("hermes down");
  });

  it("handles an empty plan without throwing", async () => {
    const result = await executeWithFallback([], {
      runOne: async () => "never",
      isRetryable: retryAll,
    });
    expect(result.ok).toBe(false);
    expect(result.attempts).toHaveLength(0);
  });
});
