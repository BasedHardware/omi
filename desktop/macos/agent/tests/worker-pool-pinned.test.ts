import { describe, expect, it } from "vitest";
import type {
  AdapterAttemptContext,
  RuntimeAdapter,
} from "../src/adapters/interface.js";
import { AdapterWorkerPool } from "../src/runtime/worker-pool.js";

function pinnedAdapter(): RuntimeAdapter {
  return {
    adapterId: "pi-mono",
    capabilities: {
      resumeFidelity: "none",
      supportsNativeResume: false,
      supportsCancellation: true,
      requiresPinnedWorker: true,
    },
    start: async () => {},
    stop: async () => {},
    openBinding: async (input) => ({
      sessionId: input.sessionId,
      adapterId: "pi-mono",
      adapterNativeSessionId: `${input.sessionId}-native`,
      resumeFidelity: "none",
      cwd: input.cwd,
    }),
    resumeBinding: async (input) => ({
      sessionId: input.sessionId,
      adapterId: "pi-mono",
      adapterNativeSessionId: input.adapterNativeSessionId,
      resumeFidelity: "none",
      cwd: input.cwd,
    }),
    executeAttempt: async (context: AdapterAttemptContext) => ({
      text: "done",
      sessionId: context.binding.adapterNativeSessionId,
      adapterSessionId: context.binding.adapterNativeSessionId,
      terminalStatus: "succeeded",
    }),
    cancelAttempt: async () => ({
      accepted: true,
      dispatchAttempted: true,
      adapterAcknowledged: false,
    }),
  };
}

describe("AdapterWorkerPool pinned workers", () => {
  it("lets an idle pinned worker open a new binding when capacity is one", async () => {
    const pool = new AdapterWorkerPool(() => pinnedAdapter(), 1);

    await pool.runExclusiveQueued(
      {
        bindingId: "binding-1",
        sessionId: "session-1",
        adapterId: "pi-mono",
        adapterNativeSessionId: "native-1",
        resumeFidelity: "none",
        cwd: "/tmp",
      },
      "attempt-1",
      async (worker) => {
        expect(worker.workerId).toBe("worker-1");
      },
    );

    await expect(
      pool.runExclusiveQueued(undefined, "attempt-open-binding-2", async (worker) => {
        expect(worker.workerId).toBe("worker-1");
      }),
    ).resolves.toBeUndefined();
  });

  it("repins an idle worker for a later binding without creating a second worker", async () => {
    const pool = new AdapterWorkerPool(() => pinnedAdapter(), 1);

    await pool.runExclusiveQueued(
      {
        bindingId: "binding-1",
        sessionId: "session-1",
        adapterId: "pi-mono",
        adapterNativeSessionId: "native-1",
        resumeFidelity: "none",
        cwd: "/tmp",
      },
      "attempt-1",
      async () => {},
    );

    await pool.runExclusiveQueued(
      {
        bindingId: "binding-2",
        sessionId: "session-2",
        adapterId: "pi-mono",
        adapterNativeSessionId: "native-2",
        resumeFidelity: "none",
        cwd: "/tmp",
      },
      "attempt-2",
      async (worker) => {
        expect(worker.workerId).toBe("worker-1");
      },
    );

    expect(pool.size).toBe(1);
  });

  it("prefers the idle worker already pinned to a requested binding", async () => {
    const pool = new AdapterWorkerPool(() => pinnedAdapter(), 2);
    const binding1 = {
      bindingId: "binding-1",
      sessionId: "session-1",
      adapterId: "pi-mono",
      adapterNativeSessionId: "native-1",
      resumeFidelity: "none" as const,
      cwd: "/tmp",
    };
    const binding2 = {
      bindingId: "binding-2",
      sessionId: "session-2",
      adapterId: "pi-mono",
      adapterNativeSessionId: "native-2",
      resumeFidelity: "none" as const,
      cwd: "/tmp",
    };
    const worker1 = pool.acquire(binding1);
    expect(worker1?.workerId).toBe("worker-1");

    let release!: () => void;
    const active = worker1!.runExclusive(
      "attempt-1",
      binding1,
      async () => new Promise<void>((resolve) => {
        release = resolve;
      }),
    );

    const worker2 = pool.acquire(binding2);
    expect(worker2?.workerId).toBe("worker-2");

    release();
    await active;

    const reused = pool.acquire(binding2);
    expect(reused?.workerId).toBe("worker-2");
    expect(pool.size).toBe(2);
  });
});
