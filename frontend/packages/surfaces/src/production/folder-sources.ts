import type {
  PlatformProductionStoreFactory,
  ProductionPlatformFolderStore,
} from "./ProductionStores.js";

/**
 * Open the Folders route store from `openPlatformFolders()`. There is no
 * legacy arm: the retired generation is not served.
 */
export async function openFolderRouteSource(
  stores: PlatformProductionStoreFactory,
): Promise<{
  store: ProductionPlatformFolderStore;
  foldersGeneration: "platform";
}> {
  const store = await stores.openPlatformFolders();
  return { store, foldersGeneration: "platform" };
}
