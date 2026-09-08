import type { Memory, MemoryCategory } from '@/types/conversation';

/**
 * Normalize a memory's raw category to one of the product categories.
 *
 * Ported from the Electron desktop app
 * (`desktop/windows/src/renderer/src/lib/memoryFilters.ts`): anything
 * unrecognized or absent reads as `interesting`, matching the backend's own
 * "unknown → interesting" default so the two never disagree.
 */
export function categoryOf(memory: Pick<Memory, 'category'>): MemoryCategory {
  const category = memory.category;
  if (
    category === 'manual' ||
    category === 'system' ||
    category === 'interesting' ||
    category === 'workflow'
  ) {
    return category;
  }
  return 'interesting';
}

/**
 * Client-side category filter.
 *
 * `/v3/memories` takes no `categories` parameter — FastAPI drops the unknown
 * query param — so category selection has to be applied here, the same way
 * desktop does it.
 */
export function matchesCategories(
  memory: Pick<Memory, 'category'>,
  categories: readonly MemoryCategory[],
): boolean {
  if (categories.length === 0) return true;
  return categories.includes(categoryOf(memory));
}
