import { describe, expect, test } from "bun:test";

import { ndcg, mrr, percentile, recallAtK } from "../src/metrics";

describe("metrics", () => {
  test("recall@K counts relevant hits in the top K", () => {
    const hits = [
      { id: "a", score: 0.9 },
      { id: "b", score: 0.8 },
      { id: "c", score: 0.7 },
    ];
    expect(recallAtK(hits, new Set(["a", "x"]), 3)).toBe(0.5);
    expect(recallAtK(hits, new Set(["a", "b"]), 1)).toBe(0.5);
    expect(recallAtK(hits, new Set(["c"]), 3)).toBe(1);
    expect(recallAtK(hits, new Set(["z"]), 3)).toBe(0);
  });

  test("mrr is reciprocal rank of first relevant hit", () => {
    const hits = [
      { id: "a", score: 0.9 },
      { id: "b", score: 0.8 },
      { id: "c", score: 0.7 },
    ];
    expect(mrr(hits, new Set(["b"]))).toBe(0.5);
    expect(mrr(hits, new Set(["a"]))).toBe(1);
    expect(mrr(hits, new Set(["z"]))).toBe(0);
  });

  test("nDCG normalizes discounted cumulative gain", () => {
    const hits = [
      { id: "a", score: 0.9 },
      { id: "b", score: 0.8 },
      { id: "c", score: 0.7 },
    ];
    expect(ndcg(hits, new Set(["b"]))).toBeCloseTo(1 / Math.log2(3), 6);
    expect(ndcg(hits, new Set(["a"]))).toBe(1);
    expect(ndcg(hits, new Set(["z"]))).toBe(0);
  });

  test("percentile uses nearest-rank over sorted samples", () => {
    const samples = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
    expect(percentile(samples, 50)).toBe(5);
    expect(percentile(samples, 95)).toBe(10);
    expect(percentile(samples, 99)).toBe(10);
    const small = [10, 20, 30, 40];
    expect(percentile(small, 50)).toBe(20);
    expect(percentile(small, 95)).toBe(40);
    expect(percentile(small, 99)).toBe(40);
    expect(percentile([7], 50)).toBe(7);
  });
});
