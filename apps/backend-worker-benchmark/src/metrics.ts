import type {
  LatencyPercentiles,
  MetricSample,
  QueryHit,
  RetrievalMetrics,
} from "./types";

export const recallAtK = (
  hits: readonly QueryHit[],
  relevant: ReadonlySet<string>,
  k: number
): number => {
  if (relevant.size === 0) return 0;
  let hit = 0;
  for (let i = 0; i < Math.min(k, hits.length); i++) {
    if (relevant.has(hits[i]!.id)) hit++;
  }
  return hit / relevant.size;
};

export const mrr = (
  hits: readonly QueryHit[],
  relevant: ReadonlySet<string>
): number => {
  for (let i = 0; i < hits.length; i++) {
    if (relevant.has(hits[i]!.id)) return 1 / (i + 1);
  }
  return 0;
};

export const ndcg = (
  hits: readonly QueryHit[],
  relevant: ReadonlySet<string>
): number => {
  let dcg = 0;
  for (let i = 0; i < hits.length; i++) {
    if (relevant.has(hits[i]!.id)) dcg += 1 / Math.log2(i + 2);
  }
  const idealHits = Math.min(hits.length, relevant.size);
  let idcg = 0;
  for (let i = 0; i < idealHits; i++) idcg += 1 / Math.log2(i + 2);
  if (idcg === 0) return 0;
  return dcg / idcg;
};

export const percentile = (samples: readonly number[], p: number): number => {
  if (samples.length === 0) return 0;
  const sorted = [...samples].sort((a, b) => a - b);
  const rank = Math.ceil((p / 100) * sorted.length);
  const index = Math.min(Math.max(rank, 1), sorted.length) - 1;
  return sorted[index]!;
};

const percentiles = (samples: readonly number[]): LatencyPercentiles => ({
  p50: percentile(samples, 50),
  p95: percentile(samples, 95),
  p99: percentile(samples, 99),
});

export const aggregateMetrics = (
  samples: readonly MetricSample[],
  k: number
): RetrievalMetrics => {
  if (samples.length === 0) {
    const zero = { p50: 0, p95: 0, p99: 0 };
    return { recallAtK: 0, mrr: 0, ndcg: 0, latency: zero, indexLag: zero };
  }
  let recallSum = 0;
  let mrrSum = 0;
  let ndcgSum = 0;
  const latencies: number[] = [];
  const lags: number[] = [];
  for (const sample of samples) {
    const relevant = new Set(sample.relevantDocIds);
    recallSum += recallAtK(sample.hits, relevant, k);
    mrrSum += mrr(sample.hits, relevant);
    ndcgSum += ndcg(sample.hits, relevant);
    latencies.push(sample.latencyMs);
    lags.push(sample.indexLagMs);
  }
  const n = samples.length;
  return {
    recallAtK: recallSum / n,
    mrr: mrrSum / n,
    ndcg: ndcgSum / n,
    latency: percentiles(latencies),
    indexLag: percentiles(lags),
  };
};
