import { describe, expect, test } from "bun:test";

import {
  createVectorizeRetrievalBoundary,
  DEFAULT_RETRIEVAL_EMBEDDING_MODEL,
  type CanonicalMemory,
  type CanonicalMemoryStore,
  type RetrievalEnv,
} from "../src/retrieval";

const FAKE_EMBEDDING = [1, 0, 0, 0];

const fakeAi = (embedding: number[] | null | "throw"): Ai =>
  ({
    run: async (model: string, inputs: Record<string, unknown>) => {
      void model;
      void inputs;
      if (embedding === "throw") throw new Error("embedding failed");
      if (embedding === null) return { data: undefined };
      return { data: [embedding] };
    },
  } as unknown as Ai);

const fakeVectorize = (
  matches: { readonly id: string; readonly score: number }[]
): Vectorize =>
  ({
    query: async () => ({ matches, count: matches.length }),
  } as unknown as Vectorize);

const trackingVectorize = (
  matches: { readonly id: string; readonly score: number }[],
  calls: { vector: number[] | Float32Array; options: VectorizeQueryOptions }[]
): Vectorize =>
  ({
    query: async (
      vector: number[] | Float32Array,
      options: VectorizeQueryOptions
    ) => {
      calls.push({ vector, options });
      return { matches, count: matches.length };
    },
  } as unknown as Vectorize);

const memoryStore = (
  records: Readonly<Record<string, CanonicalMemory>>
): CanonicalMemoryStore => ({
  load: async (accountId, ids) =>
    ids.map((id) => records[`${accountId}:${id}`] ?? null),
});

describe("vectorize retrieval boundary", () => {
  test("returns degraded projection_unavailable when VECTORIZE is unbound", async () => {
    const env = { AI: fakeAi(FAKE_EMBEDDING) } as RetrievalEnv;
    const boundary = createVectorizeRetrievalBoundary(env, memoryStore({}));
    const result = await boundary.query({
      accountId: "acct-synthetic-alpha",
      queryText: "schedule",
      topK: 2,
    });
    expect(result.status).toBe("degraded");
    expect(result.reasons).toEqual(["projection_unavailable"]);
    expect(result.hits).toEqual([]);
  });

  test("returns degraded projection_unavailable when AI embedding fails", async () => {
    const env = { AI: fakeAi("throw"), VECTORIZE: fakeVectorize([]) };
    const boundary = createVectorizeRetrievalBoundary(env, memoryStore({}));
    const result = await boundary.query({
      accountId: "acct-synthetic-alpha",
      queryText: "schedule",
      topK: 2,
    });
    expect(result.status).toBe("degraded");
    expect(result.reasons).toEqual(["projection_unavailable"]);
    expect(result.hits).toEqual([]);
  });

  test("queries Vectorize with an account-scoped metadata filter", async () => {
    const calls: {
      vector: number[] | Float32Array;
      options: VectorizeQueryOptions;
    }[] = [];
    const index = trackingVectorize(
      [
        { id: "memory-1", score: 0.95 },
        { id: "memory-2", score: 0.85 },
      ],
      calls
    );
    const store = memoryStore({
      "acct-synthetic-alpha:memory-1": {
        id: "memory-1",
        accountId: "acct-synthetic-alpha",
        text: "Alpha schedule",
      },
      "acct-synthetic-alpha:memory-2": {
        id: "memory-2",
        accountId: "acct-synthetic-alpha",
        text: "Alpha task",
      },
    });
    const env = { AI: fakeAi(FAKE_EMBEDDING), VECTORIZE: index };
    const boundary = createVectorizeRetrievalBoundary(env, store);
    const result = await boundary.query({
      accountId: "acct-synthetic-alpha",
      queryText: "schedule",
      topK: 2,
    });
    expect(result.status).toBe("complete");
    expect(result.reasons).toEqual([]);
    expect(result.hits).toEqual([
      { id: "memory-1", score: 0.95, text: "Alpha schedule" },
      { id: "memory-2", score: 0.85, text: "Alpha task" },
    ]);
    expect(calls.length).toBe(1);
    const call = calls[0]!;
    expect(call.options.topK).toBe(2);
    expect(call.options.filter).toEqual({
      account_id: { $eq: "acct-synthetic-alpha" },
    });
  });

  test("drops hits missing from canonical and reports projection_stale", async () => {
    const index = fakeVectorize([
      { id: "memory-1", score: 0.95 },
      { id: "deleted-1", score: 0.8 },
    ]);
    const store = memoryStore({
      "acct-synthetic-alpha:memory-1": {
        id: "memory-1",
        accountId: "acct-synthetic-alpha",
        text: "Alpha schedule",
      },
    });
    const env = { AI: fakeAi(FAKE_EMBEDDING), VECTORIZE: index };
    const boundary = createVectorizeRetrievalBoundary(env, store);
    const result = await boundary.query({
      accountId: "acct-synthetic-alpha",
      queryText: "schedule",
      topK: 2,
    });
    expect(result.status).toBe("degraded");
    expect(result.reasons).toEqual(["projection_stale"]);
    expect(result.hits).toEqual([
      { id: "memory-1", score: 0.95, text: "Alpha schedule" },
    ]);
  });

  test("loads text from canonical, never from Vectorize metadata", async () => {
    const index = fakeVectorize([{ id: "memory-1", score: 0.95 }]);
    const store = memoryStore({
      "acct-synthetic-alpha:memory-1": {
        id: "memory-1",
        accountId: "acct-synthetic-alpha",
        text: "right text",
      },
    });
    const env = { AI: fakeAi(FAKE_EMBEDDING), VECTORIZE: index };
    const boundary = createVectorizeRetrievalBoundary(env, store);
    const result = await boundary.query({
      accountId: "acct-synthetic-alpha",
      queryText: "schedule",
      topK: 1,
    });
    expect(result.hits).toEqual([
      { id: "memory-1", score: 0.95, text: "right text" },
    ]);
  });

  test("returns degraded projection_unavailable when Vectorize query throws", async () => {
    const index = {
      query: async () => {
        throw new Error("vectorize unavailable");
      },
    } as unknown as Vectorize;
    const env = { AI: fakeAi(FAKE_EMBEDDING), VECTORIZE: index };
    const boundary = createVectorizeRetrievalBoundary(env, memoryStore({}));
    const result = await boundary.query({
      accountId: "acct-synthetic-alpha",
      queryText: "schedule",
      topK: 2,
    });
    expect(result.status).toBe("degraded");
    expect(result.reasons).toEqual(["projection_unavailable"]);
    expect(result.hits).toEqual([]);
  });

  test("uses the configured embedding model and falls back to the default", async () => {
    const calls: { model: string; text: string }[] = [];
    const index = fakeVectorize([]);
    const ai = {
      run: async (model: string, inputs: Record<string, unknown>) => {
        calls.push({ model, text: String(inputs["text"]) });
        return { data: [FAKE_EMBEDDING] };
      },
    } as unknown as Ai;
    const env = { AI: ai, VECTORIZE: index };
    const boundary = createVectorizeRetrievalBoundary(env, memoryStore({}));
    await boundary.query({
      accountId: "acct-synthetic-alpha",
      queryText: "schedule",
      topK: 1,
    });
    expect(calls[0]?.model).toBe(DEFAULT_RETRIEVAL_EMBEDDING_MODEL);

    const explicit = {
      AI: ai,
      VECTORIZE: index,
      EMBEDDING_MODEL: "custom-model",
    };
    const explicitBoundary = createVectorizeRetrievalBoundary(
      explicit,
      memoryStore({})
    );
    await explicitBoundary.query({
      accountId: "acct-synthetic-alpha",
      queryText: "task",
      topK: 1,
    });
    expect(calls[1]?.model).toBe("custom-model");
  });
});
