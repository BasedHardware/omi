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
      acknowledgesCancellation: false,
      requiresPinnedWorker: true,
      supportsModelSwitching: true,
      supportsArtifactEmission: false,
      supportsTools: true,
      restartBehavior: "process_local_bindings_stale",
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
  it("lets an unpinned idle worker open a first binding when capacity is one", async () => {
    const pool = new AdapterWorkerPool(() => pinnedAdapter(), 1);

    await expect(
      pool.runExclusiveQueued(undefined, "attempt-open-binding-1", async (worker) => {
        expect(worker.workerId).toBe("worker-1");
      }),
    ).resolves.toBeUndefined();

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
  });

  it("does not repin an idle worker to a different live binding", async () => {
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

    expect(pool.acquire({
      bindingId: "binding-2",
      sessionId: "session-2",
      adapterId: "pi-mono",
      adapterNativeSessionId: "native-2",
      resumeFidelity: "none",
      cwd: "/tmp",
    })).toBeNull();
    expect(pool.size).toBe(1);
  });

  it("rejects unbound first-binding waiters when all pinned workers are occupied by live bindings", async () => {
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

    await expect(pool.runExclusiveQueued(undefined, "attempt-new-binding", async () => {})).rejects.toThrow(
      "No adapter worker capacity available for a new binding",
    );
  });

  it("can release an idle pinned binding for process-local worker reassignment", async () => {
    const pool = new AdapterWorkerPool(() => pinnedAdapter(), 1);
    const binding = {
      bindingId: "binding-1",
      sessionId: "session-1",
      adapterId: "pi-mono",
      adapterNativeSessionId: "native-1",
      resumeFidelity: "none" as const,
      cwd: "/tmp",
    };

    await pool.runExclusiveQueued(binding, "attempt-1", async () => {});

    expect(pool.releaseIdlePinnedBinding()).toBe("binding-1");
    expect(pool.acquire(undefined)?.workerId).toBe("worker-1");
  });

  it("keeps a first-binding creation lease pinned before the execution lease", async () => {
    const pool = new AdapterWorkerPool(() => pinnedAdapter(), 2);
    const createdBinding = {
      bindingId: "binding-1",
      sessionId: "session-1",
      adapterId: "pi-mono",
      adapterNativeSessionId: "native-1",
      resumeFidelity: "none" as const,
      cwd: "/tmp",
    };
    const otherBinding = {
      bindingId: "binding-2",
      sessionId: "session-2",
      adapterId: "pi-mono",
      adapterNativeSessionId: "native-2",
      resumeFidelity: "none" as const,
      cwd: "/tmp",
    };

    await pool.runExclusiveQueued(undefined, "attempt-1:binding", async (worker) => {
      expect(worker.workerId).toBe("worker-1");
      worker.pinBinding(createdBinding);
    });

    const executionWorker = pool.acquire(createdBinding);
    expect(executionWorker?.workerId).toBe("worker-1");
    const otherWorker = pool.acquire(otherBinding);
    expect(otherWorker?.workerId).toBe("worker-2");
    expect(pool.size).toBe(2);
  });

  it("allows an explicit stale-binding replacement to move a worker pin", async () => {
    const pool = new AdapterWorkerPool(() => pinnedAdapter(), 1);
    const oldBinding = {
      bindingId: "binding-old",
      sessionId: "session-1",
      adapterId: "pi-mono",
      adapterNativeSessionId: "native-old",
      resumeFidelity: "none" as const,
      cwd: "/tmp",
    };
    const newBinding = {
      bindingId: "binding-new",
      sessionId: "session-1",
      adapterId: "pi-mono",
      adapterNativeSessionId: "native-new",
      resumeFidelity: "none" as const,
      cwd: "/tmp",
    };

    const worker = pool.acquire(oldBinding);
    expect(worker?.workerId).toBe("worker-1");
    worker!.replacePinnedBinding("binding-old", newBinding);

    expect(pool.acquire(oldBinding)).toBeNull();
    expect(pool.acquire(newBinding)?.workerId).toBe("worker-1");
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
