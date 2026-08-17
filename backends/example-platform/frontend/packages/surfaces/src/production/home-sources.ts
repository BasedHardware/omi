import type { PlatformProductionStoreFactory } from "./ProductionStores.js";
import {
  mapHomeProjection,
  type HomeSearchSources,
  type SearchProjection,
} from "./HomeProduction.js";
import {
  homeConversationHitFromRecord,
  homeMemoryHitFromSynthesized,
  type HomeConversationHit,
  type HomeMemoryHit,
} from "./home-hits.js";

/**
 * Open Home's two search projections from the host's already-resolved
 * generation selection.
 *
 * Platform memories come from `openSynthesizedMemories()`. Platform
 * conversations come from `openPlatformConversations()`. Mapping to Home's
 * hit shape happens here, at the surface boundary. There is no legacy arm:
 * the retired generation is not served.
 */
export async function openHomeSearchSources(
  stores: PlatformProductionStoreFactory,
): Promise<{
  sources: HomeSearchSources;
  memoriesGeneration: "platform";
  conversationsGeneration: "platform";
}> {
  const [memories, conversations] = await Promise.all([
    openHomeMemoryProjection(stores),
    openHomeConversationProjection(stores),
  ]);
  return { sources: { memories, conversations }, memoriesGeneration: "platform", conversationsGeneration: "platform" };
}

async function openHomeMemoryProjection(
  stores: PlatformProductionStoreFactory,
): Promise<SearchProjection<HomeMemoryHit>> {
  const store = await stores.openSynthesizedMemories();
  return mapHomeProjection(store, homeMemoryHitFromSynthesized);
}

async function openHomeConversationProjection(
  stores: PlatformProductionStoreFactory,
): Promise<SearchProjection<HomeConversationHit>> {
  const store = await stores.openPlatformConversations();
  return mapHomeProjection(store, homeConversationHitFromRecord);
}
