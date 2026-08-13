import { describe, expect, it } from "vitest";
import type {
  AdapterAttemptContext,
  RuntimeAdapter,
} from "../src/adapters/interface.js";
import { AdapterWorkerPool, AdapterWorkerRecycledError } from "../src/runtime/worker-pool.js";

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
      text: "done",      adapterSessionId: context.binding.adapterNativeSessionId,
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

  it("rejects unbound first-binding waiters without an explicit pin eviction path", async () => {
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

  it("queues unbound first-binding waiters while a pinned worker is busy, then evicts the idle pin", async () => {
    const pool = new AdapterWorkerPool(() => pinnedAdapter(), 1);
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

    let release!: () => void;
    const active = pool.runExclusiveQueued(
      binding1,
      "attempt-1",
      async () => new Promise<void>((resolve) => {
        release = resolve;
      }),
    );
    const evictedBindingIds: string[] = [];
    let queuedRan = false;
    const queued = pool.runExclusiveQueued(
      undefined,
      "attempt-new-binding",
      async (worker) => {
        queuedRan = true;
        expect(evictedBindingIds).toEqual(["binding-1"]);
        expect(worker.workerId).toBe("worker-1");
        worker.pinBinding(binding2);
      },
      {
        onIdlePinnedBindingEvicted: (bindingId) => {
          evictedBindingIds.push(bindingId);
        },
      },
    );

    await Promise.resolve();
    expect(queuedRan).toBe(false);
    expect(evictedBindingIds).toEqual([]);

    release();
    await active;
    await queued;

    expect(pool.acquire(binding1)).toBeNull();
    expect(pool.acquire(binding2)?.workerId).toBe("worker-1");
  });

  it("releases an idle pinned binding before reporting eviction callback failures", async () => {
    const pool = new AdapterWorkerPool(() => pinnedAdapter(), 1);
    const binding1 = {
      bindingId: "binding-1",
      sessionId: "session-1",
      adapterId: "pi-mono",
      adapterNativeSessionId: "native-1",
      resumeFidelity: "none" as const,
      cwd: "/tmp",
    };

    const worker = pool.acquire(binding1);
    expect(worker?.workerId).toBe("worker-1");

    await expect(
      pool.runExclusiveQueued(
        undefined,
        "attempt-new-binding",
        async () => {},
        {
          onIdlePinnedBindingEvicted: () => {
            throw new Error("eviction callback failed");
          },
        },
      ),
    ).rejects.toThrow("eviction callback failed");

    expect(pool.acquire(undefined)?.workerId).toBe("worker-1");
  });

  it("does not evict protected idle pinned bindings", async () => {
    const pool = new AdapterWorkerPool(() => pinnedAdapter(), 1);
    const binding1 = {
      bindingId: "binding-1",
      sessionId: "session-1",
      adapterId: "pi-mono",
      adapterNativeSessionId: "native-1",
      resumeFidelity: "none" as const,
      cwd: "/tmp",
    };

    const worker = pool.acquire(binding1);
    expect(worker?.workerId).toBe("worker-1");
    pool.protectPinnedBinding("binding-1");
    let evictedBindingId: string | undefined;

    const queued = pool.runExclusiveQueued(
      undefined,
      "attempt-new-binding",
      async (leasedWorker) => {
        expect(leasedWorker.workerId).toBe("worker-1");
      },
      {
        onIdlePinnedBindingEvicted: (bindingId) => {
          evictedBindingId = bindingId;
        },
      },
    );

    await Promise.resolve();
    expect(evictedBindingId).toBeUndefined();
    pool.unprotectPinnedBinding("binding-1");
    await queued;
    expect(evictedBindingId).toBe("binding-1");
  });

  it("does not protect an idle pinned binding after failed work", async () => {
    const pool = new AdapterWorkerPool(() => pinnedAdapter(), 1);
    const binding1 = {
      bindingId: "binding-1",
      sessionId: "session-1",
      adapterId: "pi-mono",
      adapterNativeSessionId: "native-1",
      resumeFidelity: "none" as const,
      cwd: "/tmp",
    };
    let evictedBindingId: string | undefined;

    await expect(
      pool.runExclusiveQueued(
        binding1,
        "attempt-failing-binding-resolution",
        async () => {
          throw new Error("binding resolution failed");
        },
        { protectPinnedBindingAfterWork: true },
      ),
    ).rejects.toThrow("binding resolution failed");

    await pool.runExclusiveQueued(
      undefined,
      "attempt-replacement-binding",
      async (leasedWorker) => {
        expect(leasedWorker.workerId).toBe("worker-1");
      },
      {
        onIdlePinnedBindingEvicted: (bindingId) => {
          evictedBindingId = bindingId;
        },
      },
    );
    expect(evictedBindingId).toBe("binding-1");
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

  it("poisons and removes a failed process-local worker before draining same-binding waiters", async () => {
    let stopCount = 0;
    let factoryCount = 0;
    const pool = new AdapterWorkerPool(() => {
      factoryCount += 1;
      return { ...pinnedAdapter(), stop: async () => { stopCount += 1; } };
    }, 1);
    const binding = {
      bindingId: "binding-poisoned",
      sessionId: "session-1",
      adapterId: "pi-mono",
      adapterNativeSessionId: "native-1",
      resumeFidelity: "none" as const,
      cwd: "/tmp",
    };
    let release!: () => void;
    const active = pool.runExclusiveQueued(binding, "attempt-failing", async () => {
      await new Promise<void>((resolve) => { release = resolve; });
      throw new Error("adapter wedged");
    }, { recycleWorkerOnError: true });
    const queued = pool.runExclusiveQueued(binding, "attempt-queued", async () => {
      throw new Error("queued work must not reach the poisoned worker");
    });

    await new Promise<void>((resolve) => setImmediate(resolve));
    release();
    await expect(active).rejects.toMatchObject({
      name: "AdapterWorkerRecycledError",
      bindingId: "binding-poisoned",
      stopSucceeded: true,
    } satisfies Partial<AdapterWorkerRecycledError>);
    await expect(queued).rejects.toMatchObject({ name: "StaleAdapterBindingError" });
    expect(stopCount).toBe(1);
    expect(pool.size).toBe(0);

    expect(pool.acquire(undefined)?.workerId).toBe("worker-2");
    expect(factoryCount).toBe(2);
  });

  it("still removes a poisoned worker when recovery bookkeeping and stop fail", async () => {
    let stopCount = 0;
    let reportedOutcome: { stopSucceeded: boolean; bindingInvalidationSucceeded: boolean } | undefined;
    const pool = new AdapterWorkerPool(() => ({
      ...pinnedAdapter(),
      stop: async () => {
        stopCount += 1;
        throw new Error("stop failed");
      },
    }), 1);

    await expect(pool.runExclusiveQueued(undefined, "attempt-failing", async () => {
      throw new Error("adapter wedged");
    }, {
      recycleWorkerOnError: true,
      onWorkerBindingInvalidated: () => { throw new Error("persistence failed"); },
      onWorkerRecycled: (_bindingId, outcome) => { reportedOutcome = outcome; },
    })).rejects.toMatchObject({
      name: "AdapterWorkerRecycledError",
      stopSucceeded: false,
      bindingInvalidationSucceeded: false,
    });
    expect(stopCount).toBe(1);
    expect(reportedOutcome).toEqual({
      stopSucceeded: false,
      bindingInvalidationSucceeded: false,
    });
    expect(pool.size).toBe(0);
  });

  it("does not recycle errors rejected by the dispatch predicate", async () => {
    let stopCount = 0;
    const pool = new AdapterWorkerPool(() => ({
      ...pinnedAdapter(),
      stop: async () => { stopCount += 1; },
    }), 1);

    await expect(pool.runExclusiveQueued(undefined, "attempt-cancelled", async () => {
      throw new Error("cancelled_before_adapter_dispatch");
    }, {
      recycleWorkerOnError: true,
      shouldRecycleWorkerOnError: () => false,
    })).rejects.toThrow("cancelled_before_adapter_dispatch");
    expect(stopCount).toBe(0);
    expect(pool.size).toBe(1);
  });
});
