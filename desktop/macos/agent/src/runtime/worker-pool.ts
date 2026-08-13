import type {
  AdapterBindingHandle,
  RuntimeAdapter,
} from "../adapters/interface.js";

export const DEFAULT_MAX_WORKERS = 8;
export const DEFAULT_PI_MONO_MAX_WORKERS = 2;

export function configuredMaxWorkers(env = process.env): number {
  const raw = env.OMI_AGENT_MAX_WORKERS;
  if (!raw) return DEFAULT_MAX_WORKERS;
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed) || parsed < 1) return DEFAULT_MAX_WORKERS;
  return parsed;
}

export function configuredPiMonoMaxWorkers(env = process.env): number {
  const raw = env.OMI_PI_MONO_MAX_WORKERS;
  if (!raw) return DEFAULT_PI_MONO_MAX_WORKERS;
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed) || parsed < 1) return DEFAULT_PI_MONO_MAX_WORKERS;
  return parsed;
}

export class AdapterWorker {
  readonly workerId: string;
  readonly adapter: RuntimeAdapter;
  private activeAttemptId: string | null = null;
  private activeBindingId: string | null = null;
  private pinnedBindingId: string | null = null;
  private unhealthy = false;

  constructor(workerId: string, adapter: RuntimeAdapter) {
    this.workerId = workerId;
    this.adapter = adapter;
  }

  get isBusy(): boolean {
    return this.activeAttemptId !== null;
  }

  canRun(binding?: AdapterBindingHandle): boolean {
    if (this.isBusy || this.unhealthy) return false;
    if (!this.adapter.capabilities.requiresPinnedWorker) return true;
    if (!this.pinnedBindingId) return true;
    return Boolean(binding?.bindingId && binding.bindingId === this.pinnedBindingId);
  }

  hasActiveBinding(bindingId: string): boolean {
    return this.activeBindingId === bindingId;
  }

  hasPinnedBinding(bindingId: string): boolean {
    return this.pinnedBindingId === bindingId;
  }

  get idlePinnedBindingId(): string | null {
    if (this.isBusy || this.unhealthy) return null;
    return this.pinnedBindingId;
  }

  get pinnedBindingIdForRecovery(): string | null {
    return this.pinnedBindingId;
  }

  markUnhealthy(): void {
    this.unhealthy = true;
  }

  releaseIdlePinnedBinding(): string | null {
    if (this.isBusy || !this.pinnedBindingId) {
      return null;
    }
    const bindingId = this.pinnedBindingId;
    this.pinnedBindingId = null;
    return bindingId;
  }

  pinBinding(binding: AdapterBindingHandle): void {
    if (!binding.bindingId) {
      throw new Error("Pinned adapter workers require a bindingId");
    }
    if (this.pinnedBindingId && this.pinnedBindingId !== binding.bindingId) {
      throw new Error(
        `Worker ${this.workerId} is already pinned to binding ${this.pinnedBindingId}`
      );
    }
    this.pinnedBindingId = binding.bindingId;
  }

  replacePinnedBinding(replacesBindingId: string, binding: AdapterBindingHandle): void {
    if (!binding.bindingId) {
      throw new Error("Pinned adapter workers require a bindingId");
    }
    if (this.pinnedBindingId && this.pinnedBindingId !== replacesBindingId) {
      throw new Error(
        `Worker ${this.workerId} is pinned to binding ${this.pinnedBindingId}, not replacement source ${replacesBindingId}`
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

interface WorkerLeaseOptions {
  onIdlePinnedBindingEvicted?: (bindingId: string) => void;
  protectPinnedBindingAfterWork?: boolean;
  recycleWorkerOnError?: boolean;
  shouldRecycleWorkerOnError?: (error: unknown) => boolean;
  onWorkerBindingInvalidated?: (bindingId: string | null) => void;
  onWorkerRecycled?: (
    bindingId: string | null,
    outcome: { stopSucceeded: boolean; bindingInvalidationSucceeded: boolean }
  ) => void;
}

export class AdapterWorkerRecycledError extends Error {
  readonly bindingId: string | null;
  readonly stopSucceeded: boolean;
  readonly bindingInvalidationSucceeded: boolean;
  readonly originalError: unknown;

  constructor(
    originalError: unknown,
    bindingId: string | null,
    stopSucceeded: boolean,
    bindingInvalidationSucceeded: boolean
  ) {
    super(originalError instanceof Error ? originalError.message : String(originalError));
    this.name = "AdapterWorkerRecycledError";
    this.bindingId = bindingId;
    this.stopSucceeded = stopSucceeded;
    this.bindingInvalidationSucceeded = bindingInvalidationSucceeded;
    this.originalError = originalError;
  }
}

interface PendingWorkerLease {
  binding?: AdapterBindingHandle;
  attemptId: string;
  options?: WorkerLeaseOptions;
  resolve: WorkerLeaseResolver;
  reject: (error: Error) => void;
}

export class AdapterWorkerPool {
  private readonly maxWorkers: number;
  private readonly adapterFactory: AdapterFactory;
  private readonly workers: AdapterWorker[] = [];
  private readonly waiters: PendingWorkerLease[] = [];
  private readonly protectedPinnedBindingIds = new Set<string>();
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

  get requiresPinnedWorkers(): boolean {
    return this.workers.some((worker) => worker.adapter.capabilities.requiresPinnedWorker);
  }

  releaseIdlePinnedBinding(): string | null {
    for (const worker of this.workers) {
      const idlePinnedBindingId = worker.idlePinnedBindingId;
      if (idlePinnedBindingId && this.protectedPinnedBindingIds.has(idlePinnedBindingId)) {
        continue;
      }
      const bindingId = worker.releaseIdlePinnedBinding();
      if (bindingId) {
        return bindingId;
      }
    }
    return null;
  }

  protectPinnedBinding(bindingId: string | null | undefined): void {
    if (bindingId) {
      this.protectedPinnedBindingIds.add(bindingId);
    }
  }

  unprotectPinnedBinding(bindingId: string | null | undefined): void {
    if (bindingId) {
      this.protectedPinnedBindingIds.delete(bindingId);
      this.drainWaiters();
    }
  }

  acquire(binding?: AdapterBindingHandle): AdapterWorker | null {
    const bindingId = binding?.bindingId;
    if (bindingId) {
      if (this.workers.some((worker) => worker.hasActiveBinding(bindingId))) {
        return null;
      }
    }

    const pinnedIdle = bindingId
      ? this.workers.find((worker) => worker.canRun(binding) && worker.hasPinnedBinding(bindingId))
      : undefined;
    const idle = pinnedIdle ?? this.workers.find((worker) => worker.canRun(binding));
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
    work: (worker: AdapterWorker) => Promise<T>,
    options?: WorkerLeaseOptions
  ): Promise<T> {
    const worker = await this.acquireQueued(binding, attemptId, options);
    let succeeded = false;
    try {
      const result = await worker.runExclusive(attemptId, binding, () => work(worker));
      succeeded = true;
      return result;
    } catch (error) {
      if (
        !options?.recycleWorkerOnError
        || options.shouldRecycleWorkerOnError?.(error) === false
      ) throw error;
      const bindingId = worker.pinnedBindingIdForRecovery;
      // Poison synchronously before the finally block drains waiters. Otherwise
      // a queued lease can reacquire this process-local worker after its throw.
      worker.markUnhealthy();
      const index = this.workers.indexOf(worker);
      if (index >= 0) this.workers.splice(index, 1);
      if (bindingId) this.protectedPinnedBindingIds.delete(bindingId);
      this.rejectWaitersForRecycledBinding(bindingId);
      let bindingInvalidationSucceeded = true;
      try {
        options.onWorkerBindingInvalidated?.(bindingId);
      } catch {
        bindingInvalidationSucceeded = false;
        // Keep this bounded: persistence exceptions may contain database paths.
        console.error("[agent-runtime] worker recovery binding invalidation failed");
      }
      let stopSucceeded = true;
      try {
        await worker.adapter.stop();
      } catch {
        stopSucceeded = false;
      }
      try {
        options.onWorkerRecycled?.(bindingId, {
          stopSucceeded,
          bindingInvalidationSucceeded,
        });
      } catch {
        // Telemetry must not prevent deterministic worker cleanup. The thrown
        // recovery error still carries both bounded lifecycle outcomes.
        console.error("[agent-runtime] worker recovery event persistence failed");
      }
      throw new AdapterWorkerRecycledError(
        error,
        bindingId,
        stopSucceeded,
        bindingInvalidationSucceeded
      );
    } finally {
      if (succeeded && options?.protectPinnedBindingAfterWork) {
        this.protectPinnedBinding(worker.idlePinnedBindingId);
      }
      this.drainWaiters();
    }
  }

  private rejectWaitersForRecycledBinding(bindingId: string | null): void {
    if (!bindingId) return;
    for (let i = this.waiters.length - 1; i >= 0; i -= 1) {
      const waiter = this.waiters[i]!;
      if (waiter.binding?.bindingId !== bindingId) continue;
      this.waiters.splice(i, 1);
      const error = new Error(`Adapter binding was recycled: ${bindingId}`);
      error.name = "StaleAdapterBindingError";
      waiter.reject(error);
    }
  }

  private acquireQueued(
    binding: AdapterBindingHandle | undefined,
    attemptId: string,
    options?: WorkerLeaseOptions
  ): Promise<AdapterWorker> {
    const worker = this.acquire(binding) ?? this.acquireByEvictingIdlePinnedBinding(binding, options);
    if (worker) {
      worker.reserve(attemptId, binding);
      return Promise.resolve(worker);
    }
    if (!this.canEventuallyAcquire(binding, options)) {
      return Promise.reject(this.noCapacityError(binding));
    }
    return new Promise((resolve, reject) => {
      this.waiters.push({ binding, attemptId, options, resolve, reject });
    });
  }

  private drainWaiters(): void {
    for (let i = 0; i < this.waiters.length;) {
      const waiter = this.waiters[i]!;
      let worker: AdapterWorker | null;
      try {
        worker = this.acquire(waiter.binding) ?? this.acquireByEvictingIdlePinnedBinding(waiter.binding, waiter.options);
      } catch (error) {
        this.waiters.splice(i, 1);
        waiter.reject(error instanceof Error ? error : new Error(String(error)));
        continue;
      }
      if (!worker) {
        i += 1;
        continue;
      }
      this.waiters.splice(i, 1);
      worker.reserve(waiter.attemptId, waiter.binding);
      waiter.resolve(worker);
    }
    for (let i = 0; i < this.waiters.length;) {
      const waiter = this.waiters[i]!;
      if (this.canEventuallyAcquire(waiter.binding, waiter.options)) {
        i += 1;
        continue;
      }
      this.waiters.splice(i, 1);
      waiter.reject(this.noCapacityError(waiter.binding));
    }
  }

  private acquireByEvictingIdlePinnedBinding(
    binding: AdapterBindingHandle | undefined,
    options: WorkerLeaseOptions | undefined
  ): AdapterWorker | null {
    if (binding || !options?.onIdlePinnedBindingEvicted) {
      return null;
    }
    for (const worker of this.workers) {
      const evictedBindingId = worker.idlePinnedBindingId;
      if (!evictedBindingId) continue;
      if (this.protectedPinnedBindingIds.has(evictedBindingId)) continue;
      const releasedBindingId = worker.releaseIdlePinnedBinding();
      if (releasedBindingId !== evictedBindingId) {
        throw new Error(`Worker ${worker.workerId} failed to release pinned binding ${evictedBindingId}`);
      }
      options.onIdlePinnedBindingEvicted(evictedBindingId);
      return worker;
    }
    return null;
  }

  private canEventuallyAcquire(binding?: AdapterBindingHandle, options?: WorkerLeaseOptions): boolean {
    if (this.workers.length < this.maxWorkers) return true;
    const bindingId = binding?.bindingId;
    return this.workers.some((worker) => {
      if (!worker.adapter.capabilities.requiresPinnedWorker) return true;
      if (!bindingId && options?.onIdlePinnedBindingEvicted) return true;
      return Boolean(bindingId && worker.hasPinnedBinding(bindingId));
    });
  }

  private noCapacityError(binding?: AdapterBindingHandle): Error {
    const bindingLabel = binding?.bindingId ? `binding ${binding.bindingId}` : "a new binding";
    return new Error(`No adapter worker capacity available for ${bindingLabel}`);
  }
}
