import type {
  PlatformProductionStoreFactory,
  ProductionConversationStore,
  ProductionFolderStore,
  ProductionPlatformConversationStore,
  ProductionPlatformFolderStore,
} from "./ProductionStores.js";

/**
 * Open the Conversations route's two stores from the host's already-resolved
 * generation selection.
 *
 * Platform conversations come from `openPlatformConversations()`, never from
 * `openConversations()` — that port stays the legacy writable store other
 * callers depend on. Folders on this route follow `selection.folders` the
 * same way. Mapping stays at this boundary; the shared factory is not
 * repointed.
 */
export async function openConversationRouteSources(
  stores: PlatformProductionStoreFactory,
): Promise<{
  store: ProductionConversationStore | ProductionPlatformConversationStore;
  foldersStore: ProductionFolderStore | ProductionPlatformFolderStore;
  conversationsGeneration: "legacy" | "platform";
  foldersGeneration: "legacy" | "platform";
}> {
  const conversationsGeneration = stores.selection.conversations;
  const foldersGeneration = stores.selection.folders;
  const [store, foldersStore] = await Promise.all([
    conversationsGeneration === "platform"
      ? stores.openPlatformConversations()
      : stores.openConversations(),
    foldersGeneration === "platform"
      ? stores.openPlatformFolders()
      : stores.openFolders(),
  ]);
  return { store, foldersStore, conversationsGeneration, foldersGeneration };
}
