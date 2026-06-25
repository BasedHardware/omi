import type { RuntimeAdapter } from "../adapters/interface.js";
import { AdapterWorkerPool, configuredMaxWorkers } from "./worker-pool.js";

export type RuntimeAdapterFactory = () => RuntimeAdapter;

export class AdapterRegistry {
  private readonly pools = new Map<string, AdapterWorkerPool>();

  register(
    adapterId: string,
    factory: RuntimeAdapterFactory,
    maxWorkers = configuredMaxWorkers()
  ): AdapterWorkerPool {
    if (this.pools.has(adapterId)) {
      throw new Error(`Adapter already registered: ${adapterId}`);
    }
    const pool = new AdapterWorkerPool(factory, maxWorkers);
    this.pools.set(adapterId, pool);
    return pool;
  }

  get(adapterId: string): AdapterWorkerPool {
    const pool = this.pools.get(adapterId);
    if (!pool) {
      throw new Error(`Adapter not registered: ${adapterId}`);
    }
    return pool;
  }

  capacity(adapterId: string): number {
    return this.get(adapterId).capacity;
  }

  has(adapterId: string): boolean {
    return this.pools.has(adapterId);
  }
}
