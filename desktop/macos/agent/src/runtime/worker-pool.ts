import type {
  AdapterBindingHandle,
  RuntimeAdapter,
} from "../adapters/interface.js";

export const DEFAULT_MAX_WORKERS = 8;

export function configuredMaxWorkers(env = process.env): number {
  const raw = env.OMI_AGENT_MAX_WORKERS;
  if (!raw) return DEFAULT_MAX_WORKERS;
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed) || parsed < 1) return DEFAULT_MAX_WORKERS;
  return parsed;
}

export class AdapterWorker {
  readonly workerId: string;
  readonly adapter: RuntimeAdapter;
  private activeAttemptId: string | null = null;
  private activeBindingId: string | null = null;
  private pinnedBindingId: string | null = null;

  constructor(workerId: string, adapter: RuntimeAdapter) {
    this.workerId = workerId;
    this.adapter = adapter;
  }

  get isBusy(): boolean {
    return this.activeAttemptId !== null;
  }

  canRun(_binding?: AdapterBindingHandle): boolean {
    if (this.isBusy) return false;
    if (!this.adapter.capabilities.requiresPinnedWorker) return true;
    // Pinned adapters retain process-local state only while busy. Once idle,
    // the worker can be assigned to another binding and pinBinding records it.
    return true;
  }

  hasActiveBinding(bindingId: string): boolean {
    return this.activeBindingId === bindingId;
  }

  pinBinding(binding: AdapterBindingHandle): void {
    if (!binding.bindingId) {
      throw new Error("Pinned adapter workers require a bindingId");
    }
    if (this.activeAttemptId && this.pinnedBindingId && this.pinnedBindingId !== binding.bindingId) {
      throw new Error(
        `Worker ${this.workerId} is already pinned to binding ${this.pinnedBindingId}`
      );
    }
    this.pinnedBindingId = binding.bindingId;
  }

  async runExclusive<T>(attemptId: string, binding: AdapterBindingHandle | undefined, work: () => Promise<T>): Promise<T> {
    if (this.activeAttemptId && this.activeAttemptId !== attemptId) {
      throw new Error(
        `Worker ${this.workerId} already has active attempt ${this.activeAttemptId}`
      );
    }
    if (!this.activeAttemptId) {
      this.reserve(attemptId, binding);
    } else if (binding?.bindingId && this.activeBindingId !== binding.bindingId) {
      throw new Error(
        `Worker ${this.workerId} has active binding ${this.activeBindingId ?? "(none)"}`
      );
    }
    try {
      return await work();
    } finally {
      this.activeAttemptId = null;
      this.activeBindingId = null;
    }
  }

  reserve(attemptId: string, binding?: AdapterBindingHandle): void {
    if (this.activeAttemptId) {
      throw new Error(
        `Worker ${this.workerId} already has active attempt ${this.activeAttemptId}`
      );
    }
    this.activeAttemptId = attemptId;
    this.activeBindingId = binding?.bindingId ?? null;
  }
}

type AdapterFactory = () => RuntimeAdapter;
type WorkerLeaseResolver = (worker: AdapterWorker) => void;

interface PendingWorkerLease {
  binding?: AdapterBindingHandle;
  attemptId: string;
  resolve: WorkerLeaseResolver;
}

export class AdapterWorkerPool {
  private readonly maxWorkers: number;
  private readonly adapterFactory: AdapterFactory;
  private readonly workers: AdapterWorker[] = [];
  private readonly waiters: PendingWorkerLease[] = [];
  private nextWorkerId = 1;

  constructor(adapterFactory: AdapterFactory, maxWorkers = configuredMaxWorkers()) {
    if (maxWorkers < 1) {
      throw new Error("AdapterWorkerPool maxWorkers must be at least 1");
    }
    this.adapterFactory = adapterFactory;
    this.maxWorkers = maxWorkers;
  }

  get size(): number {
    return this.workers.length;
  }

  get capacity(): number {
    return this.maxWorkers;
  }

  acquire(binding?: AdapterBindingHandle): AdapterWorker | null {
    const bindingId = binding?.bindingId;
    if (bindingId) {
      if (this.workers.some((worker) => worker.hasActiveBinding(bindingId))) {
        return null;
      }
    }

    const idle = this.workers.find((worker) => worker.canRun(binding));
    if (idle) {
      if (binding && idle.adapter.capabilities.requiresPinnedWorker) {
        idle.pinBinding(binding);
      }
      return idle;
    }

    if (this.workers.length >= this.maxWorkers) {
      return null;
    }

    const adapter = this.adapterFactory();
    const worker = new AdapterWorker(`worker-${this.nextWorkerId++}`, adapter);
    if (binding && adapter.capabilities.requiresPinnedWorker) {
      worker.pinBinding(binding);
    }
    this.workers.push(worker);
    return worker;
  }

  async runExclusiveQueued<T>(
    binding: AdapterBindingHandle | undefined,
    attemptId: string,
    work: (worker: AdapterWorker) => Promise<T>
  ): Promise<T> {
    const worker = await this.acquireQueued(binding, attemptId);
    try {
      return await worker.runExclusive(attemptId, binding, () => work(worker));
    } finally {
      this.drainWaiters();
    }
  }

  private acquireQueued(binding: AdapterBindingHandle | undefined, attemptId: string): Promise<AdapterWorker> {
    const worker = this.acquire(binding);
    if (worker) {
      worker.reserve(attemptId, binding);
      return Promise.resolve(worker);
    }
    return new Promise((resolve) => {
      this.waiters.push({ binding, attemptId, resolve });
    });
  }

  private drainWaiters(): void {
    for (let i = 0; i < this.waiters.length;) {
      const waiter = this.waiters[i]!;
      const worker = this.acquire(waiter.binding);
      if (!worker) {
        i += 1;
        continue;
      }
      this.waiters.splice(i, 1);
      worker.reserve(waiter.attemptId, waiter.binding);
      waiter.resolve(worker);
    }
  }
}
