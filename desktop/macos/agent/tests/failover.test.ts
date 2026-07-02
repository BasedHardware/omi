import { describe, expect, it } from "vitest";
import { runAgentChain, type RunAgentChainDeps } from "../src/runtime/failover.js";
import type { HandleQueryOutcome } from "../src/runtime/compatibility-facade.js";

interface Recorder {
  ensured: string[];
  ran: Array<{ adapterId: string; suppress: boolean }>;
  failovers: string[];
  errors: string[];
}

function fail(message: string): HandleQueryOutcome {
  return { failed: true, errorMessage: { type: "error", message } };
}

function makeDeps(
  chain: string[],
  behavior: {
    ensureFails?: Record<string, string>;
    runOutcome?: Record<string, HandleQueryOutcome>;
    /** adapterId whose run() is treated as having streamed answer content. */
    emittedAfter?: string;
    /** adapterIds that must not be failed over from once running (side effects). */
    blockRunFailover?: string[];
  },
  rec: Recorder
): RunAgentChainDeps {
  let emitted = false;
  return {
    chain,
    ensure: async (id) => {
      rec.ensured.push(id);
      const msg = behavior.ensureFails?.[id];
      if (msg) throw new Error(msg);
    },
    run: async (id, suppress) => {
      rec.ran.push({ adapterId: id, suppress });
      if (behavior.emittedAfter === id) emitted = true;
      return behavior.runOutcome?.[id] ?? { failed: false };
    },
    hasEmitted: () => emitted,
    blockRunFailover: (id) => (behavior.blockRunFailover ?? []).includes(id),
    onFailover: (m) => rec.failovers.push(m),
    onError: (m) => rec.errors.push(m),
    log: () => {},
  };
}

function recorder(): Recorder {
  return { ensured: [], ran: [], failovers: [], errors: [] };
}

describe("runAgentChain failover", () => {
  it("runs the primary and stops when it succeeds", async () => {
    const rec = recorder();
    const result = await runAgentChain(makeDeps(["codex", "acp"], {}, rec));
    expect(result.failed).toBe(false);
    expect(result.handoffs).toBe(0);
    expect(rec.ensured).toEqual(["codex"]);
    expect(rec.ran).toEqual([{ adapterId: "codex", suppress: true }]);
    expect(rec.failovers).toEqual([]);
    expect(rec.errors).toEqual([]);
  });

  it("hands off to the next agent on a retryable run failure", async () => {
    const rec = recorder();
    const result = await runAgentChain(
      makeDeps(["codex", "acp"], { runOutcome: { codex: fail("stream closed unexpectedly") } }, rec)
    );
    expect(result.failed).toBe(false);
    expect(result.handoffs).toBe(1);
    // codex tried with suppression, acp (last) without.
    expect(rec.ran).toEqual([
      { adapterId: "codex", suppress: true },
      { adapterId: "acp", suppress: false },
    ]);
    expect(rec.failovers).toHaveLength(1);
    expect(rec.failovers[0]).toContain("Codex");
    expect(rec.failovers[0]).toContain("Claude Code");
    expect(rec.errors).toEqual([]);
  });

  it("hands off when the primary fails to start", async () => {
    const rec = recorder();
    const result = await runAgentChain(
      makeDeps(["codex", "acp"], { ensureFails: { codex: "codex binary not found" } }, rec)
    );
    expect(result.failed).toBe(false);
    expect(result.handoffs).toBe(1);
    expect(rec.ensured).toEqual(["codex", "acp"]);
    // codex never ran (startup failed); acp ran as the last resort.
    expect(rec.ran).toEqual([{ adapterId: "acp", suppress: false }]);
    expect(rec.failovers).toHaveLength(1);
  });

  it("does not fail over on a user-actionable (non-retryable) failure", async () => {
    const rec = recorder();
    const result = await runAgentChain(
      makeDeps(["codex", "acp"], { runOutcome: { codex: fail("authentication required") } }, rec)
    );
    expect(result.failed).toBe(true);
    expect(result.handoffs).toBe(0);
    // never advanced to acp
    expect(rec.ran).toEqual([{ adapterId: "codex", suppress: true }]);
    expect(rec.failovers).toEqual([]);
    expect(rec.errors).toEqual(["authentication required"]);
  });

  it("never retries once answer content has streamed to the user", async () => {
    const rec = recorder();
    const result = await runAgentChain(
      makeDeps(
        ["codex", "acp"],
        { runOutcome: { codex: fail("crashed mid-answer") }, emittedAfter: "codex" },
        rec
      )
    );
    expect(result.failed).toBe(true);
    expect(result.handoffs).toBe(0);
    expect(rec.failovers).toEqual([]);
    // the suppressed error is surfaced instead of a silent swap
    expect(rec.errors).toEqual(["crashed mid-answer"]);
    expect(rec.ran).toEqual([{ adapterId: "codex", suppress: true }]);
  });

  it("lets the last-resort agent emit its own error (no double emit)", async () => {
    const rec = recorder();
    const result = await runAgentChain(
      makeDeps(
        ["codex", "acp"],
        { runOutcome: { codex: fail("boom-1"), acp: fail("boom-2") } },
        rec
      )
    );
    expect(result.failed).toBe(true);
    expect(result.handoffs).toBe(1);
    expect(rec.ran).toEqual([
      { adapterId: "codex", suppress: true },
      { adapterId: "acp", suppress: false },
    ]);
    // acp ran with suppress=false, so the facade already emitted; onError not called.
    expect(rec.errors).toEqual([]);
    expect(rec.failovers).toHaveLength(1);
  });

  it("does not fail over a side-effecting adapter after it started running", async () => {
    const rec = recorder();
    const result = await runAgentChain(
      makeDeps(
        ["codex", "acp"],
        { runOutcome: { codex: fail("exited non-zero") }, blockRunFailover: ["codex"] },
        rec
      )
    );
    expect(result.failed).toBe(true);
    expect(result.handoffs).toBe(0);
    // codex ran and failed; we must not re-run the task on acp (files may be edited)
    expect(rec.ran).toEqual([{ adapterId: "codex", suppress: true }]);
    expect(rec.failovers).toEqual([]);
    expect(rec.errors).toEqual(["exited non-zero"]);
  });

  it("still fails over a side-effecting adapter that fails to START", async () => {
    const rec = recorder();
    const result = await runAgentChain(
      makeDeps(
        ["codex", "acp"],
        { ensureFails: { codex: "codex binary not found" }, blockRunFailover: ["codex"] },
        rec
      )
    );
    // startup precedes any side effect, so failing over is safe
    expect(result.failed).toBe(false);
    expect(result.handoffs).toBe(1);
    expect(rec.ran).toEqual([{ adapterId: "acp", suppress: false }]);
  });

  it("surfaces the error when every agent fails to start", async () => {
    const rec = recorder();
    const result = await runAgentChain(
      makeDeps(["codex", "acp"], { ensureFails: { codex: "e1", acp: "e2" } }, rec)
    );
    expect(result.failed).toBe(true);
    expect(rec.ensured).toEqual(["codex", "acp"]);
    expect(rec.ran).toEqual([]);
    expect(rec.failovers).toHaveLength(1);
    expect(rec.errors).toEqual(["e2"]);
  });
});
