import { describe, expect, test } from "bun:test";

import { buildSyntheticCorpus } from "../src/corpus";
import { runWorkload } from "../src/harness";
import { evaluateGates } from "../src/gates";
import { aggregateMetrics } from "../src/metrics";
import { createVectorizeProvider } from "../src/providers/vectorize";
import { createAISearchProvider } from "../src/providers/aisearch";
import type { RetrievalProvider } from "../src/types";

const accountDocs = (corpus: ReturnType<typeof buildSyntheticCorpus>) => {
  const merged = new Map<string, ReadonlySet<string>>();
  for (const doc of corpus.docs) {
    const existing = merged.get(doc.accountId) ?? new Set<string>();
    const next = new Set<string>(existing);
    next.add(doc.id);
    merged.set(doc.accountId, next);
  }
  return merged;
};

const exerciseProvider = async (provider: RetrievalProvider) => {
  const corpus = buildSyntheticCorpus();
  const { samples, revokedIds } = await runWorkload(provider, corpus, {
    k: 5,
    deleteCount: 2,
  });
  return { corpus, samples, revokedIds };
};

describe("harness workload", () => {
  test("exercises both account scopes with queries and mutations", async () => {
    const { corpus, samples, revokedIds } = await exerciseProvider(
      createVectorizeProvider()
    );
    const scopesTouched = new Set(samples.map((s) => s.scope.accountId));
    expect(scopesTouched.has("acct-synthetic-alpha")).toBe(true);
    expect(scopesTouched.has("acct-synthetic-beta")).toBe(true);
    expect(corpus.scopes.length).toBe(2);
    expect(revokedIds.size).toBe(4);
    const phases = new Set(samples.map((s) => s.queryId.split("#")[1]));
    expect(phases.has("lag")).toBe(true);
    expect(phases.has("steady")).toBe(true);
    expect(phases.has("postdelete")).toBe(true);
  });

  test("steady-state queries retrieve relevant docs (recall > 0)", async () => {
    const { samples } = await exerciseProvider(createVectorizeProvider());
    const steady = samples.filter((s) => s.queryId.endsWith("#steady"));
    const metrics = aggregateMetrics(steady, 5);
    expect(metrics.recallAtK).toBeGreaterThan(0);
    expect(metrics.mrr).toBeGreaterThan(0);
    expect(metrics.ndcg).toBeGreaterThan(0);
  });

  test("lag-phase samples report non-zero index lag, steady samples zero", async () => {
    const { samples } = await exerciseProvider(createVectorizeProvider());
    const lag = samples.filter((s) => s.queryId.endsWith("#lag"));
    const steady = samples.filter((s) => s.queryId.endsWith("#steady"));
    expect(lag.every((s) => s.indexLagMs > 0)).toBe(true);
    expect(steady.every((s) => s.indexLagMs === 0)).toBe(true);
  });

  test("latency percentiles are ordered p50 <= p95 <= p99", async () => {
    const { samples } = await exerciseProvider(createVectorizeProvider());
    const metrics = aggregateMetrics(samples, 5);
    expect(metrics.latency.p50).toBeLessThanOrEqual(metrics.latency.p95);
    expect(metrics.latency.p95).toBeLessThanOrEqual(metrics.latency.p99);
  });

  test("both providers pass the hard gates", async () => {
    for (const provider of [
      createVectorizeProvider(),
      createAISearchProvider(),
    ]) {
      const { corpus, samples } = await exerciseProvider(provider);
      const result = evaluateGates(samples, accountDocs(corpus));
      expect(result.passed).toBe(true);
    }
  });

  test("both providers produce a full metric report", async () => {
    for (const provider of [
      createVectorizeProvider(),
      createAISearchProvider(),
    ]) {
      const { samples } = await exerciseProvider(provider);
      const metrics = aggregateMetrics(samples, 5);
      expect(Number.isFinite(metrics.recallAtK)).toBe(true);
      expect(Number.isFinite(metrics.mrr)).toBe(true);
      expect(Number.isFinite(metrics.ndcg)).toBe(true);
      expect(Number.isFinite(metrics.latency.p50)).toBe(true);
      expect(Number.isFinite(metrics.latency.p95)).toBe(true);
      expect(Number.isFinite(metrics.latency.p99)).toBe(true);
      expect(Number.isFinite(metrics.indexLag.p50)).toBe(true);
    }
  });
});
