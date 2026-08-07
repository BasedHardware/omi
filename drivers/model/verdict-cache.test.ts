import { expect, test } from "bun:test";
import { CachingModelPort, MemoryVerdictStore, SqliteVerdictStore, canonicalJson, verdictKey } from "./verdict-cache";
import type { ModelPort } from "./port";

const counting = (respond: (n: number) => unknown): ModelPort & { calls: number } => {
  const port = {
    calls: 0,
    async invoke() { port.calls += 1; return respond(port.calls); },
    async render() { port.calls += 1; return { summary_text: "s", citations: [] }; },
    async compose() { port.calls += 1; return { answer_text: "a", citations: [], assertions: [] }; },
  };
  return port as ModelPort & { calls: number };
};

const request = { strategy: "identity-adjudication", version: "dream-identity-v1", input: { profiles: [{ id: "r1" }] } };

test("an identical request is answered from cache without a second model call", async () => {
  const inner = counting(() => ({ same_groups: [["r1", "r2"]] }));
  const cache = new CachingModelPort(inner, new MemoryVerdictStore(), "glm:glm-4.7");
  const first = await cache.invoke(request);
  const second = await cache.invoke(request);
  expect(second).toEqual(first);
  expect(inner.calls).toBe(1);
  expect(cache.stats).toEqual({ hits: 1, misses: 1, writes: 1, uncacheable: 0 });
});

test("a throw is never cached, so transient failures stay retryable", async () => {
  let attempt = 0;
  const inner = counting(() => { attempt += 1; if (attempt === 1) throw new Error("The operation timed out."); return { same_groups: [] }; });
  const cache = new CachingModelPort(inner, new MemoryVerdictStore(), "glm:glm-4.7");
  await expect(cache.invoke(request)).rejects.toThrow("timed out");
  // The retry must reach the model, not a cached error.
  await expect(cache.invoke(request)).resolves.toEqual({ same_groups: [] });
  expect(inner.calls).toBe(2);
  expect(cache.stats.hits).toBe(0);
});

test("strategy, version, input and model identity all separate cache entries", async () => {
  const base = verdictKey("glm:glm-4.7", request.strategy, request.version, request.input);
  expect(verdictKey("codex:gpt-5.3-codex-spark:medium", request.strategy, request.version, request.input)).not.toBe(base);
  expect(verdictKey("glm:glm-4.7", "identity-verification", request.version, request.input)).not.toBe(base);
  expect(verdictKey("glm:glm-4.7", request.strategy, "dream-identity-v2", request.input)).not.toBe(base);
  expect(verdictKey("glm:glm-4.7", request.strategy, request.version, { profiles: [{ id: "r2" }] })).not.toBe(base);
  // A GLM cache serving a codex verdict is the failure this key shape prevents.
  const store = new MemoryVerdictStore();
  const glm = new CachingModelPort(counting(() => "from-glm"), store, "glm:glm-4.7");
  const codex = new CachingModelPort(counting(() => "from-codex"), store, "codex:gpt-5.3-codex-spark:medium");
  expect(await glm.invoke(request)).toBe("from-glm");
  expect(await codex.invoke(request)).toBe("from-codex");
});

test("structurally identical inputs hash the same regardless of property order", () => {
  expect(canonicalJson({ b: 1, a: [{ y: 2, x: 1 }] })).toBe(canonicalJson({ a: [{ x: 1, y: 2 }], b: 1 }));
  expect(verdictKey("n", "s", "v", { b: 1, a: 2 })).toBe(verdictKey("n", "s", "v", { a: 2, b: 1 }));
  // Order inside an array is meaningful and must NOT be normalised away.
  expect(canonicalJson([1, 2])).not.toBe(canonicalJson([2, 1]));
});

test("render and compose are never served from cache", async () => {
  const inner = counting(() => "x");
  const cache = new CachingModelPort(inner, new MemoryVerdictStore(), "glm:glm-4.7");
  await cache.render(request);
  await cache.render(request);
  await cache.compose(request);
  await cache.compose(request);
  expect(inner.calls).toBe(4);
  expect(cache.stats.hits).toBe(0);
});

test("the sqlite store survives reopening, so a later run reuses an earlier run's verdicts", async () => {
  const path = `/tmp/omi-verdict-cache-test-${Bun.hash(String(Math.random()))}.sqlite`;
  const first = new SqliteVerdictStore(path);
  const inner = counting(() => ({ decision: "accept_ltm" }));
  expect(await new CachingModelPort(inner, first, "glm:glm-4.7").invoke(request)).toEqual({ decision: "accept_ltm" });
  first.close();

  const reopened = new SqliteVerdictStore(path);
  const warm = new CachingModelPort(inner, reopened, "glm:glm-4.7");
  expect(await warm.invoke(request)).toEqual({ decision: "accept_ltm" });
  expect(inner.calls).toBe(1);
  expect(warm.stats.hits).toBe(1);
  reopened.close();
  await Bun.$`rm -f ${path} ${path}-wal ${path}-shm`.quiet();
});
