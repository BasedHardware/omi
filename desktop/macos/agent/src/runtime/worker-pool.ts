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
  private pinnedBindingId: string | null = null;

  constructor(workerId: string, adapter: RuntimeAdapter) {
    this.workerId = workerId;
    this.adapter = adapter;
  }

  get isBusy(): boolean {
    return this.activeAttemptId !== null;
  }

  canRun(binding?: AdapterBindingHandle): boolean {
    if (this.isBusy) return false;
    if (!this.adapter.capabilities.requiresPinnedWorker) return true;
    if (!this.pinnedBindingId) return true;
    return Boolean(binding?.bindingId && binding.bindingId === this.pinnedBindingId);
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

  async runExclusive<T>(attemptId: string, work: () => Promise<T>): Promise<T> {
    if (this.activeAttemptId) {
      throw new Error(
        `Worker ${this.workerId} already has active attempt ${this.activeAttemptId}`
      );
    }
    this.activeAttemptId = attemptId;
    try {
      return await work();
    } finally {
      this.activeAttemptId = null;
    }
  }
}

type AdapterFactory = () => RuntimeAdapter;

export class AdapterWorkerPool {
  private readonly maxWorkers: number;
  private readonly adapterFactory: AdapterFactory;
  private readonly workers: AdapterWorker[] = [];
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
}
