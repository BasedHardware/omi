import { expect, test } from "bun:test";
import { CachingModelPort, MemoryVerdictStore, SqliteVerdictStore, canonicalJson, qaPromptCacheKey, verdictKey, type QaModelCacheScope, type QaOwnerOfflineCacheScope, type QaReaderBoundCacheScope, type VerdictStore } from "./verdict-cache";
import { GlmModel } from "./glm";
import type { ModelInitialPromptIdentity, ModelInvocationSuccess, ModelPort, ModelPromptCoordinates } from "./port";

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

const coordinates = (strategy = request.strategy, prompt = request.version): ModelPromptCoordinates => ({
  provider_version: "fixture-provider-v1", model_version: "fixture-model-v1", adapter_version: "fixture-adapter-v1",
  strategy_version: strategy, prompt_version: prompt, parser_schema_version: "fixture-parser-v1",
  policy_version: "fixture-policy-v1", retry_version: "fixture-retry-v1", sampling_tool_version: "fixture-sampling-v1",
  cache_format_version: "qa-model-verdict-cache-v2",
});
const cacheScope = (owner = "owner-1"): QaOwnerOfflineCacheScope => ({ kind: "owner_offline", owner_account_id: owner, policy_version: "fixture-policy-v1" });
const readerScope = (projection = "b".repeat(64), authorization = "c".repeat(64)): QaReaderBoundCacheScope => ({
  kind: "reader_bound", owner_account_id: "owner-1", policy_version: "fixture-policy-v1",
  reader_projection_digest: projection, authorization_digest: authorization,
});
const promptAware = (digest: string, result: unknown, options: { attempt?: number; successfulDigest?: string; delay?: Promise<void> } = {}) => {
  const port = {
    calls: 0,
    async invoke() { port.calls += 1; return result; },
    initialPromptIdentity(candidate: typeof request): ModelInitialPromptIdentity {
      return { prompt_digest: digest, coordinates: coordinates(candidate.strategy, candidate.version) };
    },
    async invokeWithMetadata(): Promise<ModelInvocationSuccess> {
      port.calls += 1;
      await options.delay;
      return { result, successful_prompt_digest: options.successfulDigest ?? digest, attempt: options.attempt ?? 1 };
    },
    validateCachedResult(_candidate: typeof request, value: unknown) {
      return value && typeof value === "object" && !Array.isArray(value) ? { ok: true as const, result: value } : { ok: false as const };
    },
    async render() { return { summary_text: "s", citations: [] }; },
    async compose() { return { answer_text: "a", citations: [], assertions: [] }; },
  };
  return port;
};

class CapturingStore implements VerdictStore {
  readonly entries = new Map<string, string>();
  gets = 0;
  sets = 0;
  get(key: string) { this.gets += 1; return this.entries.get(key); }
  set(key: string, value: string) { this.sets += 1; this.entries.set(key, value); }
  close() { this.entries.clear(); }
}

class ThrowingStore implements VerdictStore {
  constructor(private readonly failGet: boolean, private readonly failSet: boolean) {}
  get() { if (this.failGet) throw new Error("raw-store-read-sentinel"); return undefined; }
  set() { if (this.failSet) throw new Error("raw-store-write-sentinel"); }
  close() {}
}

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

test("a malformed legacy cache value is a miss, never a model-path failure", async () => {
  const store = new CapturingStore();
  store.entries.set(verdictKey("fixture", request.strategy, request.version, request.input), "{not json}");
  const inner = counting(() => ({ same_groups: [] }));
  const cache = new CachingModelPort(inner, store, "fixture");
  await expect(cache.invoke(request)).resolves.toEqual({ same_groups: [] });
  expect(inner.calls).toBe(1);
  expect(cache.stats).toMatchObject({ hits: 0, misses: 1, writes: 1 });
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

test("the identity budget cost is computed from the same view the prompt sends", async () => {
  const { identityAdjudicationCost, identityAdjudicationView } = await import("./glm");
  const profile = {
    mention_id: "mention:very-long-identifier-that-never-reaches-the-model",
    claim_revision_id: "provisional:8f166a27-fc41-463b-b95b-f9c3830b1969:evidence:8f166a27:0:25:use",
    source_identity_ref: { namespace_instance_ref: "namespace:x", local_key: "k", producer: { producer_ref: "p", contract_ref: "c" }, asserted_identity: { domain: "person", scope_ref: "owner:djz" } },
    discriminating_claims: [{
      predicate: "use", role: "user", polarity: "positive",
      other_arguments: [{ role: "instrument", value: { kind: "source_local_ref", ref: "source-local:8f166a27-fc41-463b-b95b-f9c3830b1969:evidence:8f166a27:32:43" } }],
      evidence_context: [{ evidence_ref: "evidence:8f166a27:8f166a27-e134", excerpt: "I was using Proposers.", capture_session_id: "8f166a27", event_time: null, source_sequence: 1 }],
      cooccurring_predicates: ["prefer"], observed_at: null, evidence_refs: ["evidence:8f166a27:8f166a27-e134"],
    }],
  };
  const profiles = [profile, { ...profile, mention_id: "mention:second" }] as never;
  const cost = identityAdjudicationCost(profiles);
  expect(cost).toBe(JSON.stringify(identityAdjudicationView(profiles)).length);
  // The point of the change: ids and source-local values are most of the stored
  // bytes and none of them are sent, so the storage size badly over-counts.
  expect(cost).toBeLessThan(JSON.stringify(profiles).length);
  const sent = JSON.stringify(identityAdjudicationView(profiles));
  for (const leaked of ["mention:very-long-identifier", "source-local:", "provisional:", "evidence:8f166a27:8f166a27-e134"]) expect(sent).not.toContain(leaked);
  expect(sent).toContain("I was using Proposers.");
});

test("GLM prompt identity hashes exact initial bytes rather than the caller object", () => {
  const model = new GlmModel({ apiKey: "fixture", model: "fixture-model" });
  const left = model.initialPromptIdentity({ strategy: "grounded-extraction", version: "v1", input: { prompt: "exact bytes", ignored: "left-secret" } });
  const right = model.initialPromptIdentity({ strategy: "grounded-extraction", version: "v1", input: { prompt: "exact bytes", ignored: "right-secret" } });
  expect(left?.prompt_digest).toBe(right?.prompt_digest);
  expect(JSON.stringify(left)).not.toContain("exact bytes");
  expect(JSON.stringify(left)).not.toContain("left-secret");
  expect(model.initialPromptIdentity({ strategy: "grounded-extraction", version: "v1", input: { prompt: "changed bytes" } })?.prompt_digest).not.toBe(left?.prompt_digest);
});

test("every explicit prompt and authorization coordinate separates QA cache identity", () => {
  const baseIdentity = { prompt_digest: "a".repeat(64), coordinates: coordinates() };
  const baseScope = readerScope();
  const base = qaPromptCacheKey("fixture", baseScope, baseIdentity);
  expect(qaPromptCacheKey("fixture", { ...baseScope, owner_account_id: "owner-2" }, baseIdentity)).not.toBe(base);
  expect(qaPromptCacheKey("fixture", { ...baseScope, policy_version: "scope-policy-v2" }, baseIdentity)).not.toBe(base);
  expect(qaPromptCacheKey("fixture", { ...baseScope, reader_projection_digest: "d".repeat(64) }, baseIdentity)).not.toBe(base);
  expect(qaPromptCacheKey("fixture", { ...baseScope, authorization_digest: "e".repeat(64) }, baseIdentity)).not.toBe(base);
  expect(qaPromptCacheKey("fixture", cacheScope(), baseIdentity)).not.toBe(base);
  expect(qaPromptCacheKey("fixture", baseScope, { ...baseIdentity, prompt_digest: "f".repeat(64) })).not.toBe(base);
  for (const key of ["provider_version", "model_version", "adapter_version", "strategy_version", "prompt_version", "parser_schema_version", "policy_version", "retry_version", "sampling_tool_version"] as const) {
    expect(qaPromptCacheKey("fixture", baseScope, { ...baseIdentity, coordinates: { ...baseIdentity.coordinates, [key]: `${key}-changed` } })).not.toBe(base);
  }
  expect(() => qaPromptCacheKey("fixture", baseScope, { ...baseIdentity, coordinates: { ...baseIdentity.coordinates, cache_format_version: "wrong" } as never })).toThrow("invalid QA model cache identity");
});

test("scoped cache shares prompt-equivalent inputs, including concurrent misses", async () => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const inner = promptAware("a".repeat(64), { same_groups: [] }, { delay: gate });
  const cache = new CachingModelPort(inner, new MemoryVerdictStore(), "fixture", cacheScope());
  const first = cache.invoke({ ...request, input: { promptEquivalent: "left" } });
  const second = cache.invoke({ ...request, input: { promptEquivalent: "right" } });
  await Promise.resolve();
  expect(inner.calls).toBe(1);
  release();
  expect(await first).toEqual({ same_groups: [] });
  expect(await second).toEqual({ same_groups: [] });
  expect(await cache.invoke(request)).toEqual({ same_groups: [] });
  expect(inner.calls).toBe(1);
});

test("scoped cache is owner-separated and never stores repaired-attempt results", async () => {
  const store = new MemoryVerdictStore();
  const firstInner = promptAware("a".repeat(64), { verdict: "same" });
  const secondInner = promptAware("a".repeat(64), { verdict: "same" });
  await new CachingModelPort(firstInner, store, "fixture", cacheScope("owner-1")).invoke(request);
  await new CachingModelPort(secondInner, store, "fixture", cacheScope("owner-2")).invoke(request);
  expect(firstInner.calls).toBe(1);
  expect(secondInner.calls).toBe(1);

  const repaired = promptAware("b".repeat(64), { verdict: "same" }, { attempt: 2, successfulDigest: "c".repeat(64) });
  const cache = new CachingModelPort(repaired, new MemoryVerdictStore(), "fixture", cacheScope());
  await cache.invoke(request);
  await cache.invoke(request);
  expect(repaired.calls).toBe(2);
  expect(cache.stats).toMatchObject({ writes: 0, uncacheable: 2 });
});

test("reader-bound cache misses when either reader projection or authorization changes", async () => {
  const store = new MemoryVerdictStore();
  const first = promptAware("a".repeat(64), { verdict: "same" });
  const projectionChanged = promptAware("a".repeat(64), { verdict: "same" });
  const authorizationChanged = promptAware("a".repeat(64), { verdict: "same" });
  await new CachingModelPort(first, store, "fixture", readerScope()).invoke(request);
  await new CachingModelPort(projectionChanged, store, "fixture", readerScope("d".repeat(64), "c".repeat(64))).invoke(request);
  await new CachingModelPort(authorizationChanged, store, "fixture", readerScope("b".repeat(64), "e".repeat(64))).invoke(request);
  expect([first.calls, projectionChanged.calls, authorizationChanged.calls]).toEqual([1, 1, 1]);
});

test("malformed or parser-invalid scoped records are misses; accepted empty verdicts cache", async () => {
  const digest = "a".repeat(64);
  const inner = promptAware(digest, {});
  const store = new CapturingStore();
  const identity = inner.initialPromptIdentity(request);
  const key = qaPromptCacheKey("fixture", cacheScope(), identity);
  store.entries.set(key, "{not json}");
  const cache = new CachingModelPort(inner, store, "fixture", cacheScope());
  expect(await cache.invoke(request)).toEqual({});
  expect(await cache.invoke(request)).toEqual({});
  expect(inner.calls).toBe(1);
  expect(cache.stats).toMatchObject({ hits: 1, misses: 1, writes: 1 });

  const arbitrary = { arbitrary: "shape" };
  const encodedResult = canonicalJson(arbitrary);
  const resultDigest = new Bun.CryptoHasher("sha256").update(encodedResult).digest("hex");
  store.entries.set(key, JSON.stringify({ cache_format_version: "qa-model-verdict-cache-v2", cache_identity: key, result_digest: resultDigest, result: arbitrary }));
  const rejecting = promptAware(digest, {});
  rejecting.validateCachedResult = () => ({ ok: false as const });
  await new CachingModelPort(rejecting, store, "fixture", cacheScope()).invoke(request);
  expect(rejecting.calls).toBe(1);
});

test("scoped mode fails closed for invalid identity and unsupported versions without touching the store", async () => {
  const invalid = promptAware("not-a-digest", {});
  invalid.initialPromptIdentity = () => ({ prompt_digest: "not-a-digest", coordinates: coordinates() });
  const invalidStore = new CapturingStore();
  await new CachingModelPort(invalid, invalidStore, "fixture", cacheScope()).invoke(request);
  expect(invalid.calls).toBe(1);
  expect(invalidStore.gets).toBe(0);
  expect(invalidStore.sets).toBe(0);

  const unsupportedStore = new CapturingStore();
  const unsupported = new CachingModelPort(new GlmModel({ apiKey: "fixture" }), unsupportedStore, "fixture", cacheScope());
  await expect(unsupported.invoke({ strategy: "identity-adjudication", version: "unsupported", input: {} })).rejects.toThrow("version mismatch");
  expect(unsupportedStore.gets).toBe(0);
  expect(unsupportedStore.sets).toBe(0);
});

test("reader-bound scope requires both digests and malformed scope never touches the store", async () => {
  // @ts-expect-error reader-bound scope cannot be constructed without projection state
  const missingProjection: QaModelCacheScope = { kind: "reader_bound", owner_account_id: "owner-1", policy_version: "fixture-policy-v1", authorization_digest: "c".repeat(64) };
  // @ts-expect-error reader-bound scope cannot be constructed without authorization state
  const missingAuthorization: QaModelCacheScope = { kind: "reader_bound", owner_account_id: "owner-1", policy_version: "fixture-policy-v1", reader_projection_digest: "b".repeat(64) };
  const identity = { prompt_digest: "a".repeat(64), coordinates: coordinates() };
  expect(() => qaPromptCacheKey("fixture", missingProjection, identity)).toThrow("invalid QA model cache identity");
  expect(() => qaPromptCacheKey("fixture", missingAuthorization, identity)).toThrow("invalid QA model cache identity");

  const store = new CapturingStore();
  const first = promptAware("a".repeat(64), {});
  const second = promptAware("a".repeat(64), {});
  await new CachingModelPort(first, store, "fixture", missingProjection).invoke(request);
  await new CachingModelPort(second, store, "fixture", missingAuthorization).invoke(request);
  expect([first.calls, second.calls]).toEqual([1, 1]);
  expect(store.gets).toBe(0);
  expect(store.sets).toBe(0);
});

test("QA cache records contain neither caller prompt bytes nor owner ids", async () => {
  const store = new CapturingStore();
  const inner = promptAware("a".repeat(64), {});
  await new CachingModelPort(inner, store, "fixture", cacheScope("owner-secret-sentinel")).invoke({ ...request, input: { prompt: "raw-prompt-sentinel" } });
  const stored = [...store.entries.entries()].flat().join("\n");
  expect(stored).not.toContain("raw-prompt-sentinel");
  expect(stored).not.toContain("owner-secret-sentinel");
});

test("cache store failures are contained in legacy and scoped QA modes", async () => {
  for (const scoped of [false, true]) {
    const readInner = scoped ? promptAware("a".repeat(64), { verdict: "same" }) : counting(() => ({ verdict: "same" }));
    const readCache = new CachingModelPort(readInner, new ThrowingStore(true, false), "fixture", scoped ? cacheScope() : undefined);
    await expect(readCache.invoke(request)).resolves.toEqual({ verdict: "same" });
    expect(readCache.stats).toMatchObject({ hits: 0, misses: 1, writes: 1, uncacheable: 0 });

    const writeInner = scoped ? promptAware("b".repeat(64), { verdict: "same" }) : counting(() => ({ verdict: "same" }));
    const writeCache = new CachingModelPort(writeInner, new ThrowingStore(false, true), "fixture", scoped ? cacheScope() : undefined);
    await expect(writeCache.invoke(request)).resolves.toEqual({ verdict: "same" });
    expect(writeCache.stats).toMatchObject({ hits: 0, misses: 1, writes: 0, uncacheable: 1 });
  }
});
