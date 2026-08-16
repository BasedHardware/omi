import type {
  PlatformProductionStoreFactory,
  ProductionPlatformTaskStore,
  ProductionTaskStore,
} from "./ProductionStores.js";

/**
 * Open the Tasks route store from the host's already-resolved generation
 * selection.
 *
 * Platform tasks come from `openPlatformTasks()`, never from `openTasks()` —
 * that port stays the legacy writable store other callers depend on. The
 * route does not repoint the shared factory. David's 2026-08-16 ruling
 * lifted the R7 park; the factory-level flip stays forbidden.
 */
export async function openTaskRouteSource(
  stores: PlatformProductionStoreFactory,
): Promise<{
  store: ProductionTaskStore | ProductionPlatformTaskStore;
  tasksGeneration: "legacy" | "platform";
}> {
  const tasksGeneration = stores.selection.tasks;
  const store = tasksGeneration === "platform"
    ? await stores.openPlatformTasks()
    : await stores.openTasks();
  return { store, tasksGeneration };
}
