import type {
  PlatformProductionStoreFactory,
  ProductionPlatformConversationStore,
  ProductionPlatformFolderStore,
} from "./ProductionStores.js";

/**
 * Open the Conversations route's two stores.
 *
 * Platform conversations come from `openPlatformConversations()`. Folders on
 * this route come from `openPlatformFolders()`. There is no legacy arm: the
 * retired generation is not served.
 */
export async function openConversationRouteSources(
  stores: PlatformProductionStoreFactory,
): Promise<{
  store: ProductionPlatformConversationStore;
  foldersStore: ProductionPlatformFolderStore;
  conversationsGeneration: "platform";
  foldersGeneration: "platform";
}> {
  const [store, foldersStore] = await Promise.all([
    stores.openPlatformConversations(),
    stores.openPlatformFolders(),
  ]);
  return {
    store,
    foldersStore,
    conversationsGeneration: "platform",
    foldersGeneration: "platform",
  };
}
