import type {
  AccountScope,
  IndexAck,
  QueryHit,
  QueryResult,
  RetrievalProvider,
  SyntheticDoc,
  SyntheticQuery,
} from "../types";
import { cosine, deterministicJitter, InMemoryStore } from "./store";

const BASE_LATENCY_MS = 4;
const JITTER_MS = 3;
const LAG_PER_DOC_MS = 5;

export const createBadProvider = (): RetrievalProvider => {
  const store = new InMemoryStore(LAG_PER_DOC_MS);
  return {
    name: "intentionally-bad",
    upsert: async (
      scope: AccountScope,
      doc: SyntheticDoc
    ): Promise<IndexAck> => {
      store.upsertPending(scope, doc);
      return { accepted: true, visibleAfterMs: LAG_PER_DOC_MS };
    },
    delete: async (_scope: AccountScope, _docId: string): Promise<IndexAck> => {
      return { accepted: true, visibleAfterMs: LAG_PER_DOC_MS };
    },
    query: async (
      _scope: AccountScope,
      q: SyntheticQuery,
      k: number
    ): Promise<QueryResult> => {
      const candidates = store.allVisibleDocs();
      const hits: QueryHit[] = candidates
        .map((doc) => ({
          id: doc.id,
          score: cosine(q.embedding, doc.embedding),
        }))
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
