import type {
  PlatformProductionStoreFactory,
  ProductionFolderStore,
  ProductionPlatformFolderStore,
} from "./ProductionStores.js";

/**
 * Open the Folders route store from the host's already-resolved generation
 * selection.
 *
 * Platform folders come from `openPlatformFolders()`, never from
 * `openFolders()` — that port stays the legacy store writable callers depend
 * on. The route does not repoint the shared factory.
 */
export async function openFolderRouteSource(
  stores: PlatformProductionStoreFactory,
): Promise<{
  store: ProductionFolderStore | ProductionPlatformFolderStore;
  foldersGeneration: "legacy" | "platform";
}> {
  const foldersGeneration = stores.selection.folders;
  const store = foldersGeneration === "platform"
    ? await stores.openPlatformFolders()
    : await stores.openFolders();
  return { store, foldersGeneration };
}
