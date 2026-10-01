import type { SynthesizedRecallReason } from "@omi-core/contracts";

/**
 * Workers-first derived retrieval boundary.
 *
 * This boundary uses Vectorize because its account-metadata filter and
 * delete/tombstone mechanics have synthetic staging smoke evidence. The local
 * benchmark simulates both Vectorize and AI Search, but does not establish a
 * hosted quality or latency winner. AI Search remains unselected until a
 * provisioned synthetic-only instance proves an equivalent per-account
 * isolation and deletion path.
 *
 * The boundary is fail-closed: no VECTORIZE binding, no AI embedding, or a
 * Vectorize failure all degrade to projection_unavailable. The index is not
 * authoritative: every returned id is revalidated against the canonical
 * D1/R2 memory store, and any id the canonical store cannot confirm is
 * treated as a stale derived index entry.
 */
export const DEFAULT_RETRIEVAL_EMBEDDING_MODEL =
  "@cf/baai/bge-small-en-v1.5" as const;

export type RetrievalQuery = {
  readonly accountId: string;
  readonly queryText: string;
  readonly topK: number;
};

export type RetrievalHit = {
  readonly id: string;
  readonly score: number;
  readonly text: string;
};

export type RetrievalStatus =
  | "complete"
  | "degraded"
  | "partial"
  | "incomplete";

export type RetrievalResult = {
  readonly status: RetrievalStatus;
  readonly reasons: readonly SynthesizedRecallReason[];
  readonly hits: readonly RetrievalHit[];
};

export type CanonicalMemory = {
  readonly id: string;
  readonly accountId: string;
  readonly text: string;
};

export interface CanonicalMemoryStore {
  load(
    accountId: string,
    ids: readonly string[]
  ): Promise<readonly (CanonicalMemory | null)[]>;
}

/** No D1 memory table exists. Every id fails revalidation. */
export const noCanonicalMemoryStore: CanonicalMemoryStore = {
  load: async (_accountId, ids) => ids.map(() => null),
};

export interface RetrievalEnv {
  readonly AI: Ai;
  readonly VECTORIZE?: Vectorize;
  readonly EMBEDDING_MODEL?: string;
}

export interface RetrievalBoundary {
  query(request: RetrievalQuery): Promise<RetrievalResult>;
}

const embedQuery = async (
  ai: Ai,
  model: string,
  text: string
): Promise<number[] | null> => {
  try {
    const result = (await ai.run(model, { text, pooling: "mean" } as Record<
      string,
      unknown
    >)) as Record<string, unknown>;
    if (!Array.isArray(result["data"]) || result["data"].length === 0)
      return null;
    const first = result["data"][0];
    if (!Array.isArray(first) || !first.every((v) => typeof v === "number"))
      return null;
    return first as number[];
  } catch {
    return null;
  }
};

export const createVectorizeRetrievalBoundary = (
  env: RetrievalEnv,
  canonical: CanonicalMemoryStore
): RetrievalBoundary => {
  const index = env.VECTORIZE;
  return {
    query: async (request): Promise<RetrievalResult> => {
      if (index === undefined) {
        return {
          status: "degraded",
          reasons: ["projection_unavailable"],
          hits: [],
        };
      }
      const embedding = await embedQuery(
        env.AI,
        env.EMBEDDING_MODEL ?? DEFAULT_RETRIEVAL_EMBEDDING_MODEL,
        request.queryText
      );
      if (embedding === null) {
        return {
          status: "degraded",
          reasons: ["projection_unavailable"],
          hits: [],
        };
      }
      try {
        const matches = await index.query(embedding, {
          topK: request.topK,
          filter: { account_id: { $eq: request.accountId } },
        });
        const ids = matches.matches.map((match) => match.id);
        const rows = await canonical.load(request.accountId, ids);
        const hits: RetrievalHit[] = [];
        let stale = false;
        for (let i = 0; i < matches.matches.length; i++) {
          const match = matches.matches[i]!;
          const row = rows[i];
          if (
            row !== null &&
            row !== undefined &&
            row.id === match.id &&
            row.accountId === request.accountId
          ) {
            hits.push({ id: match.id, score: match.score, text: row.text });
          } else {
            stale = true;
          }
        }
        if (stale) {
          return {
            status: "degraded",
            reasons: ["projection_stale"],
            hits,
          };
        }
        return { status: "complete", reasons: [], hits };
      } catch {
        return {
          status: "degraded",
          reasons: ["projection_unavailable"],
          hits: [],
        };
      }
    },
  };
};
