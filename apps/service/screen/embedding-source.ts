// domain-pending(DIV-DOMAPPS-007)
// domain-pending(UNK-DOMAPPS-001)

import type { ScreenTextSearchHit } from "../stores/screen-store";

/**
 * Optional semantic-search seam for screen OCR.
 *
 * Keyword (FTS5) search is the live path. This interface exists so an embedding
 * engine can be configured later without changing the route. The default
 * adapter answers not_configured and must not invent ranking.
 */

export type ScreenEmbeddingSearchOutcome =
  | { readonly status: "not_configured" }
  | { readonly status: "ready"; readonly hits: readonly ScreenTextSearchHit[] };

export interface ScreenEmbeddingSource {
  search(input: {
    readonly accountId: string;
    readonly query: string;
    readonly limit: number;
  }): Promise<ScreenEmbeddingSearchOutcome>;
}

/** Default adapter. Semantic search is configuration, not a tonight engine. */
export const createUnconfiguredScreenEmbeddingSource = (): ScreenEmbeddingSource =>
  Object.freeze({
    search: async (): Promise<ScreenEmbeddingSearchOutcome> =>
      Object.freeze({ status: "not_configured" as const }),
  });
