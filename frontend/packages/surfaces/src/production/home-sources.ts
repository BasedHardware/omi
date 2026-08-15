import type { PlatformProductionStoreFactory } from "./ProductionStores.js";
import {
  mapHomeProjection,
  type HomeSearchSources,
  type SearchProjection,
} from "./HomeProduction.js";
import {
  homeConversationHitFromRecord,
  homeMemoryHitFromLegacy,
  homeMemoryHitFromSynthesized,
  type HomeConversationHit,
  type HomeMemoryHit,
} from "./home-hits.js";

/**
 * Open Home's two search projections from the host's already-resolved
 * generation selection.
 *
 * Platform memories come from `openSynthesizedMemories()`, never from
 * `openMemories()` — that port stays the legacy editable store. Platform
 * conversations come from `openPlatformConversations()` by the same rule.
 * Mapping to Home's hit shape happens here, at the surface boundary.
 */
export async function openHomeSearchSources(
  stores: PlatformProductionStoreFactory,
): Promise<{
  sources: HomeSearchSources;
  memoriesGeneration: "legacy" | "platform";
  conversationsGeneration: "legacy" | "platform";
}> {
  const memoriesGeneration = stores.selection.memories;
  const conversationsGeneration = stores.selection.conversations;
  const [memories, conversations] = await Promise.all([
    openHomeMemoryProjection(stores),
    openHomeConversationProjection(stores),
  ]);
  return { sources: { memories, conversations }, memoriesGeneration, conversationsGeneration };
}

async function openHomeMemoryProjection(
  stores: PlatformProductionStoreFactory,
): Promise<SearchProjection<HomeMemoryHit>> {
  if (stores.selection.memories === "platform") {
    const store = await stores.openSynthesizedMemories();
    return mapHomeProjection(store, homeMemoryHitFromSynthesized);
  }
  const store = await stores.openMemories();
  return mapHomeProjection(store, homeMemoryHitFromLegacy);
}

async function openHomeConversationProjection(
  stores: PlatformProductionStoreFactory,
): Promise<SearchProjection<HomeConversationHit>> {
  if (stores.selection.conversations === "platform") {
    const store = await stores.openPlatformConversations();
    return mapHomeProjection(store, homeConversationHitFromRecord);
  }
  const store = await stores.openConversations();
  return mapHomeProjection(store, homeConversationHitFromRecord);
}
