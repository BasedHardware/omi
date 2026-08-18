export type AccountScope = { readonly accountId: string };

export type SyntheticDoc = {
  readonly id: string;
  readonly accountId: string;
  readonly embedding: readonly number[];
  readonly terms: readonly string[];
  readonly revoked: boolean;
  readonly synthetic: true;
};

export type SyntheticQuery = {
  readonly id: string;
  readonly accountId: string;
  readonly embedding: readonly number[];
  readonly terms: readonly string[];
  readonly relevantDocIds: readonly string[];
};

export type QueryHit = { readonly id: string; readonly score: number };

export type QueryResult = {
  readonly hits: readonly QueryHit[];
  readonly latencyMs: number;
};

export type IndexAck = {
  readonly accepted: boolean;
  readonly visibleAfterMs: number;
};

export interface RetrievalProvider {
  readonly name: string;
  upsert(scope: AccountScope, doc: SyntheticDoc): Promise<IndexAck>;
  delete(scope: AccountScope, docId: string): Promise<IndexAck>;
  query(
    scope: AccountScope,
    q: SyntheticQuery,
    k: number
  ): Promise<QueryResult>;
  flush(scope: AccountScope): Promise<void>;
  pendingLagMs(scope: AccountScope): number;
}

export type MetricSample = {
  readonly queryId: string;
  readonly scope: AccountScope;
  readonly relevantDocIds: readonly string[];
  readonly hits: readonly QueryHit[];
  readonly latencyMs: number;
  readonly indexLagMs: number;
  readonly revokedIdsAtQueryTime: ReadonlySet<string>;
};

export type LatencyPercentiles = {
  readonly p50: number;
  readonly p95: number;
  readonly p99: number;
};

export type RetrievalMetrics = {
  readonly recallAtK: number;
  readonly mrr: number;
  readonly ndcg: number;
  readonly latency: LatencyPercentiles;
  readonly indexLag: LatencyPercentiles;
};

export type ValidationResult = { ok: true } | { ok: false; reasons: string[] };

export type RawDoc = Readonly<Record<string, unknown>>;
export type RawQuery = Readonly<Record<string, unknown>>;
