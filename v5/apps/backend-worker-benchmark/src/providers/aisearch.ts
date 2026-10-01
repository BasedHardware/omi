import type {
  AccountScope,
  IndexAck,
  QueryHit,
  QueryResult,
  RetrievalProvider,
  SyntheticDoc,
  SyntheticQuery,
} from "../types";
import {
  cosine,
  deterministicJitter,
  InMemoryStore,
  type StoredDoc,
  termOverlap,
} from "./store";

const BASE_LATENCY_MS = 12;
const JITTER_MS = 8;
const LAG_PER_DOC_MS = 15;
const VECTOR_WEIGHT = 0.6;
const TERM_WEIGHT = 0.4;

const score = (q: SyntheticQuery, doc: StoredDoc): number =>
  VECTOR_WEIGHT * cosine(q.embedding, doc.embedding) +
  TERM_WEIGHT * termOverlap(q.terms, doc.terms);

export const createAISearchProvider = (): RetrievalProvider => {
  const store = new InMemoryStore(LAG_PER_DOC_MS);
  return {
    name: "cloudflare-ai-search",
    upsert: async (
      scope: AccountScope,
      doc: SyntheticDoc
    ): Promise<IndexAck> => {
      store.upsertPending(scope, doc);
      return { accepted: true, visibleAfterMs: LAG_PER_DOC_MS };
    },
    delete: async (scope: AccountScope, docId: string): Promise<IndexAck> => {
      store.delete(scope, docId);
      return { accepted: true, visibleAfterMs: LAG_PER_DOC_MS };
    },
    query: async (
      scope: AccountScope,
      q: SyntheticQuery,
      k: number
    ): Promise<QueryResult> => {
      const candidates = store.visibleDocs(scope).filter((doc) => !doc.revoked);
      const hits: QueryHit[] = candidates
        .map((doc) => ({ id: doc.id, score: score(q, doc) }))
        .sort((a, b) => b.score - a.score)
        .slice(0, k);
      const latencyMs = BASE_LATENCY_MS + deterministicJitter(q.id, JITTER_MS);
      return { hits, latencyMs };
    },
    flush: async (scope: AccountScope): Promise<void> => {
      store.flush(scope);
    },
    pendingLagMs: (scope: AccountScope): number => store.pendingLagMs(scope),
  };
};
