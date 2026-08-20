import { describe, expect, it } from 'vitest';
import { categoryOf, matchesCategories } from '@/lib/memoryCategory';
import type { MemoryCategory } from '@/types/conversation';

/**
 * Ported from the Electron desktop app's `lib/memoryFilters.ts`. Category
 * selection has to be applied client-side: `/v3/memories` takes no
 * `categories` parameter, so the query string web used to send was dropped by
 * FastAPI and the filter silently returned everything.
 */

const memory = (category?: string) =>
  ({ category }) as unknown as { category: MemoryCategory };

describe('categoryOf', () => {
  it('passes through the four product categories', () => {
    for (const category of ['manual', 'system', 'interesting', 'workflow']) {
      expect(categoryOf(memory(category))).toBe(category);
    }
  });

  it('reads an absent category as interesting, matching the backend default', () => {
    expect(categoryOf(memory(undefined))).toBe('interesting');
  });

  it('reads an unrecognised category as interesting rather than dropping it', () => {
    // The backend's MemoryCategory union is wider than the product filter, so
    // anything outside the four must still be reachable under some chip.
    expect(categoryOf(memory('hobbies'))).toBe('interesting');
    expect(categoryOf(memory('auto'))).toBe('interesting');
  });
});

describe('matchesCategories', () => {
  it('matches everything when nothing is selected', () => {
    expect(matchesCategories(memory('manual'), [])).toBe(true);
    expect(matchesCategories(memory(undefined), [])).toBe(true);
  });

  it('keeps only the selected categories', () => {
    expect(matchesCategories(memory('manual'), ['manual'])).toBe(true);
    expect(matchesCategories(memory('system'), ['manual'])).toBe(false);
  });

  it('accepts more than one selected category', () => {
    const selected: MemoryCategory[] = ['manual', 'system'];

    expect(matchesCategories(memory('system'), selected)).toBe(true);
    expect(matchesCategories(memory('interesting'), selected)).toBe(false);
  });

  it('normalises before comparing, so an odd category lands under Insights', () => {
    expect(matchesCategories(memory('hobbies'), ['interesting'])).toBe(true);
    expect(matchesCategories(memory(undefined), ['interesting'])).toBe(true);
  });
});
