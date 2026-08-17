import type {
  PlatformProductionStoreFactory,
  ProductionPlatformTaskStore,
} from "./ProductionStores.js";

/**
 * Open the Tasks route store. Platform tasks come from `openPlatformTasks()`.
 * There is no legacy arm: the retired generation is not served.
 */
export async function openTaskRouteSource(
  stores: PlatformProductionStoreFactory,
): Promise<{
  store: ProductionPlatformTaskStore;
  tasksGeneration: "platform";
}> {
  const store = await stores.openPlatformTasks();
  return { store, tasksGeneration: "platform" };
}
