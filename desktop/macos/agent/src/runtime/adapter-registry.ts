import {
  assertAdapterAttemptResultContract,
  assertAdapterBindingContract,
  isProductionAdapterId,
  isPlaceholderAdapterId,
} from "../adapters/interface.js";
import type { RuntimeAdapter } from "../adapters/interface.js";
import { AdapterWorkerPool, configuredMaxWorkers } from "./worker-pool.js";
import { assertProductionAdapterScopeDeclared } from "./execution-policy.js";

export type RuntimeAdapterFactory = () => RuntimeAdapter;

export class AdapterRegistry {
  private readonly pools = new Map<string, AdapterWorkerPool>();

  register(
    adapterId: string,
    factory: RuntimeAdapterFactory,
    maxWorkers = configuredMaxWorkers()
  ): AdapterWorkerPool {
    if (isPlaceholderAdapterId(adapterId)) {
      throw new Error(
        `Adapter ${adapterId} is a placeholder and cannot be registered as a production adapter without an implementation factory`
      );
    }
    if (isProductionAdapterId(adapterId)) {
      assertProductionAdapterScopeDeclared(adapterId);
    }
    if (this.pools.has(adapterId)) {
      throw new Error(`Adapter already registered: ${adapterId}`);
    }
    const pool = new AdapterWorkerPool(() => contractCheckedAdapter(factory()), maxWorkers);
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

  adapterIds(): string[] {
    return [...this.pools.keys()].sort();
  }
}

function contractCheckedAdapter(adapter: RuntimeAdapter): RuntimeAdapter {
  return {
    adapterId: adapter.adapterId,
    capabilities: adapter.capabilities,
    start: () => adapter.start(),
    stop: () => adapter.stop(),
    openBinding: async (input) => {
      const binding = await adapter.openBinding(input);
      assertAdapterBindingContract(binding, `${adapter.adapterId}.openBinding`);
      return binding;
    },
    resumeBinding: async (input) => {
      const binding = await adapter.resumeBinding(input);
      assertAdapterBindingContract(binding, `${adapter.adapterId}.resumeBinding`);
      return binding;
    },
    executeAttempt: async (context, sink, signal) => {
      const result = await adapter.executeAttempt(context, sink, signal);
      assertAdapterAttemptResultContract(context, result, `${adapter.adapterId}.executeAttempt`);
      return result;
    },
    cancelAttempt: (context) => adapter.cancelAttempt(context),
    closeBinding: adapter.closeBinding ? (binding) => adapter.closeBinding!(binding) : undefined,
    effectiveMcpServers: adapter.effectiveMcpServers
      ? (mcpServers) => adapter.effectiveMcpServers!(mcpServers)
      : undefined,
  };
}
