/**
 * Memoized model verdicts, keyed on byte-identical inputs.
 *
 * Doc 47 R2 #5: "Naming rejections are cycle-keyed => identical groups re-pay
 * adjudication+verification+naming every cycle. Production should memoize model
 * verdicts keyed by a stable hash of (strategy, version, input)." Measured on
 * the v7 GLM lane, a dream cycle issues >=320 model calls, 87% of them in the
 * two per-group phases, and re-issues them every cycle for clusters that did not
 * change.
 *
 * This is a cache and nothing more. D50 is untouched: the model still proposes
 * and the deterministic validator still admits, from the same bytes it would
 * have seen. `partition_hash` semantics are untouched -- the hash is computed
 * from admitted groups exactly as before, so a cached cycle and a cold cycle on
 * the same ledger produce the same hash.
 *
 * Two rules make it safe rather than merely fast:
 *
 * - **Successes only.** A throw is never cached. Transient model failures, and
 *   the retryable rejections built on them, must stay retryable (doc 47 R3);
 *   caching an error would convert a network blip into a permanent verdict.
 * - **The model identity is part of the key.** A GLM cache must never serve a
 *   codex result for the same prompt, and a prompt-version bump must miss.
 */
import { Database } from "bun:sqlite";
import { isProxy } from "node:util/types";
import type { ModelInitialPromptIdentity, ModelInvokeRequest, ModelPort, ModelPromptCoordinates } from "./port";

export interface VerdictStore {
  get(key: string): string | undefined;
  set(key: string, value: string): void;
  close(): void;
}

/** Recursively key-sorted JSON, so two structurally identical inputs that were
 * built in a different property order still hash the same. */
export const canonicalJson = (value: unknown): string => {
  if (value === null || typeof value !== "object") return JSON.stringify(value ?? null) ?? "null";
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const entries = Object.entries(value as Record<string, unknown>)
    .filter(([, item]) => item !== undefined)
    .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0));
  return `{${entries.map(([name, item]) => `${JSON.stringify(name)}:${canonicalJson(item)}`).join(",")}}`;
};

export const verdictKey = (namespace: string, strategy: string, version: string, input: unknown): string =>
  new Bun.CryptoHasher("sha256").update(canonicalJson({ namespace, strategy, version, input })).digest("hex");

/** Explicit owner-only scope for offline QA work with no reader projection. */
export interface QaOwnerOfflineCacheScope {
  readonly kind: "owner_offline";
  readonly owner_account_id: string;
  readonly policy_version: string;
}

/** Reader-facing QA work must bind both projected content and authorization. */
export interface QaReaderBoundCacheScope {
  readonly kind: "reader_bound";
  readonly owner_account_id: string;
  readonly policy_version: string;
  readonly reader_projection_digest: string;
  readonly authorization_digest: string;
}

export type QaModelCacheScope = QaOwnerOfflineCacheScope | QaReaderBoundCacheScope;

const DIGEST = /^[a-f0-9]{64}$/;
const COORDINATE_KEYS = [
  "provider_version", "model_version", "adapter_version", "strategy_version",
  "prompt_version", "parser_schema_version", "policy_version", "retry_version",
  "sampling_tool_version", "cache_format_version",
] as const;
const plainRecord = (value: unknown): value is Record<string, unknown> => {
  if (typeof value !== "object" || value === null || Array.isArray(value) || isProxy(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) return false;
  return Reflect.ownKeys(Object.getOwnPropertyDescriptors(value)).every((key) => {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    return typeof key === "string" && descriptor?.enumerable === true && Object.hasOwn(descriptor, "value");
  });
};
const exactKeys = (value: object, expected: readonly string[]): boolean => {
  const keys = Reflect.ownKeys(value);
  return keys.length === expected.length && keys.every((key) => typeof key === "string" && expected.includes(key));
};
const boundedCoordinate = (value: unknown): value is string =>
  typeof value === "string" && value.length >= 1 && value.length <= 256 && !/[\u0000-\u001f\u007f]/.test(value);
const validCoordinates = (value: unknown): value is ModelPromptCoordinates => {
  if (!plainRecord(value) || !exactKeys(value, COORDINATE_KEYS)) return false;
  return COORDINATE_KEYS.every((key) => key === "cache_format_version"
    ? value[key] === "qa-model-verdict-cache-v2"
    : boundedCoordinate(value[key]));
};
const validIdentity = (value: unknown): value is ModelInitialPromptIdentity =>
  plainRecord(value) && exactKeys(value, ["prompt_digest", "coordinates"])
    && typeof value.prompt_digest === "string" && DIGEST.test(value.prompt_digest)
    && validCoordinates(value.coordinates);
const validScope = (value: unknown): value is QaModelCacheScope => {
  if (!plainRecord(value)) return false;
  if (!boundedCoordinate(value.owner_account_id) || !boundedCoordinate(value.policy_version)) return false;
  if (value.kind === "owner_offline") return exactKeys(value, ["kind", "owner_account_id", "policy_version"]);
  return value.kind === "reader_bound"
    && exactKeys(value, ["kind", "owner_account_id", "policy_version", "reader_projection_digest", "authorization_digest"])
    && typeof value.reader_projection_digest === "string" && DIGEST.test(value.reader_projection_digest)
    && typeof value.authorization_digest === "string" && DIGEST.test(value.authorization_digest);
};

export const qaPromptCacheKey = (namespace: string, scope: QaModelCacheScope, identity: ModelInitialPromptIdentity): string => {
  if (!boundedCoordinate(namespace) || !validScope(scope) || !validIdentity(identity)) throw new TypeError("invalid QA model cache identity");
  return verdictKey(namespace, identity.coordinates.strategy_version, identity.coordinates.prompt_version, {
    cache_scope: scope.kind === "reader_bound" ? {
      kind: scope.kind,
      owner_account_id: scope.owner_account_id,
      policy_version: scope.policy_version,
      reader_projection_digest: scope.reader_projection_digest,
      authorization_digest: scope.authorization_digest,
    } : {
      kind: scope.kind,
      owner_account_id: scope.owner_account_id,
      policy_version: scope.policy_version,
    },
    prompt_digest: identity.prompt_digest,
    coordinates: identity.coordinates,
  });
};

export class SqliteVerdictStore implements VerdictStore {
  private readonly db: Database;
  constructor(path: string) {
    this.db = new Database(path);
    this.db.exec("PRAGMA busy_timeout = 5000;");
    this.db.query("PRAGMA journal_mode = WAL;").get();
    this.db.exec("CREATE TABLE IF NOT EXISTS model_verdicts (key TEXT PRIMARY KEY, value TEXT NOT NULL, created_at TEXT NOT NULL);");
  }
  get(key: string): string | undefined {
    return (this.db.query("SELECT value FROM model_verdicts WHERE key = ?").get(key) as { value: string } | null)?.value;
  }
  set(key: string, value: string): void {
    this.db.query("INSERT OR REPLACE INTO model_verdicts (key, value, created_at) VALUES (?, ?, ?)").run(key, value, new Date().toISOString());
  }
  close(): void { this.db.close(); }
}

/** In-memory store, for tests and single-process runs. */
export class MemoryVerdictStore implements VerdictStore {
  private readonly entries = new Map<string, string>();
  get(key: string): string | undefined { return this.entries.get(key); }
  set(key: string, value: string): void { this.entries.set(key, value); }
  close(): void { this.entries.clear(); }
}

export interface CacheStats { hits: number; misses: number; writes: number; uncacheable: number }

interface QaCacheRecord {
  cache_format_version: "qa-model-verdict-cache-v2";
  cache_identity: string;
  result_digest: string;
  result: unknown;
}

const resultDigest = (result: unknown): string =>
  new Bun.CryptoHasher("sha256").update(canonicalJson(result)).digest("hex");

const readQaCacheRecord = (encoded: string, expectedIdentity: string): QaCacheRecord | null => {
  try {
    const value = JSON.parse(encoded) as unknown;
    if (!value || typeof value !== "object" || Array.isArray(value)) return null;
    const keys = Object.keys(value).sort();
    if (keys.join("\u0000") !== ["cache_format_version", "cache_identity", "result", "result_digest"].sort().join("\u0000")) return null;
    const record = value as Record<string, unknown>;
    if (record.cache_format_version !== "qa-model-verdict-cache-v2" || record.cache_identity !== expectedIdentity
      || typeof record.result_digest !== "string" || !/^[a-f0-9]{64}$/.test(record.result_digest)) return null;
    if (resultDigest(record.result) !== record.result_digest) return null;
    return record as unknown as QaCacheRecord;
  } catch {
    return null;
  }
};

/**
 * Caches `invoke` only. `render` and `compose` are the recall path: they carry a
 * per-run model_version rather than a pinned prompt contract, and their answers
 * are what the recall log grades, so silently replaying an earlier answer there
 * would corrupt an evaluation rather than speed one up.
 */
export class CachingModelPort implements ModelPort {
  readonly stats: CacheStats = { hits: 0, misses: 0, writes: 0, uncacheable: 0 };
  private readonly inFlight = new Map<string, Promise<unknown>>();
  constructor(
    private readonly inner: ModelPort,
    private readonly store: VerdictStore,
    private readonly namespace: string,
    private readonly scope?: QaModelCacheScope,
  ) {}

  async invoke(request: ModelInvokeRequest): Promise<unknown> {
    if (request.signal !== undefined) {
      if (request.signal.aborted) throw request.signal.reason;
      this.stats.uncacheable += 1;
      return this.inner.invoke(request);
    }
    if (this.scope) {
      const identity = validScope(this.scope) ? this.inner.initialPromptIdentity?.(request) : undefined;
      // Scoped mode is fail-closed. It never falls through to the legacy
      // raw-input cache when identity or parser-validation metadata is absent.
      if (!validScope(this.scope) || !validIdentity(identity) || !this.inner.invokeWithMetadata || !this.inner.validateCachedResult) {
        this.stats.uncacheable += 1;
        return this.inner.invoke(request);
      }
      const key = qaPromptCacheKey(this.namespace, this.scope, identity);
      const existing = this.inFlight.get(key);
      if (existing) return existing;
      const pending = this.invokePromptScoped(request, identity, key);
      this.inFlight.set(key, pending);
      try { return await pending; } finally { this.inFlight.delete(key); }
    }

    // Compatibility path for the existing offline harness. New prompt-identity
    // use must supply an explicit owner scope; this legacy raw-input cache is
    // deliberately not a production cache contract.
    const key = verdictKey(this.namespace, request.strategy, request.version, request.input);
    let cached: string | undefined;
    try { cached = this.store.get(key); } catch { cached = undefined; }
    if (cached !== undefined) {
      try {
        const parsed = JSON.parse(cached) as unknown;
        this.stats.hits += 1;
        return parsed;
      } catch {
        // A cache is never request authority. Corrupt legacy QA bytes are a
        // miss; the model path remains exactly as available as cache-off.
      }
    }
    this.stats.misses += 1;
    // Deliberately not wrapped in try/catch: a throw propagates uncached, so the
    // caller's retry and retryable-rejection machinery behaves exactly as it
    // does without the cache.
    const result = await this.inner.invoke(request);
    let encoded: string;
    try { encoded = JSON.stringify(result); } catch { this.stats.uncacheable += 1; return result; }
    if (encoded === undefined) { this.stats.uncacheable += 1; return result; }
    try { this.store.set(key, encoded); } catch { this.stats.uncacheable += 1; return result; }
    this.stats.writes += 1;
    return result;
  }

  private async invokePromptScoped(request: ModelInvokeRequest, identity: ModelInitialPromptIdentity, key: string): Promise<unknown> {
    let cached: string | undefined;
    try { cached = this.store.get(key); } catch { cached = undefined; }
    if (cached !== undefined) {
      const record = readQaCacheRecord(cached, key);
      if (record) {
        const validated = this.inner.validateCachedResult!(request, record.result);
        if (validated.ok) {
          this.stats.hits += 1;
          return validated.result;
        }
      }
    }
    this.stats.misses += 1;

    // Without exact successful-attempt metadata, serving the result from an
    // initial-prompt key on a later run would overclaim equivalence. Execute it
    // normally and leave it uncached.
    if (!this.inner.invokeWithMetadata) {
      this.stats.uncacheable += 1;
      return this.inner.invoke(request);
    }
    const success = await this.inner.invokeWithMetadata(request);
    if (!Number.isSafeInteger(success.attempt) || success.attempt !== 1
      || !DIGEST.test(success.successful_prompt_digest) || success.successful_prompt_digest !== identity.prompt_digest) {
      this.stats.uncacheable += 1;
      return success.result;
    }
    const validated = this.inner.validateCachedResult!(request, success.result);
    if (!validated.ok || canonicalJson(validated.result) !== canonicalJson(success.result)) {
      this.stats.uncacheable += 1;
      return success.result;
    }
    let record: QaCacheRecord;
    let encoded: string | undefined;
    try {
      record = {
        cache_format_version: "qa-model-verdict-cache-v2",
        cache_identity: key,
        result_digest: resultDigest(validated.result),
        result: validated.result,
      };
      encoded = JSON.stringify(record);
    } catch {
      this.stats.uncacheable += 1;
      return success.result;
    }
    if (encoded === undefined) {
      this.stats.uncacheable += 1;
      return success.result;
    }
    try { this.store.set(key, encoded); } catch { this.stats.uncacheable += 1; return success.result; }
    this.stats.writes += 1;
    return success.result;
  }

  initialPromptIdentity(request: ModelInvokeRequest): ModelInitialPromptIdentity | undefined {
    return this.inner.initialPromptIdentity?.(request);
  }

  render(request: ModelInvokeRequest) { return this.inner.render(request); }
  compose(request: ModelInvokeRequest) { return this.inner.compose(request); }
}

/** `OMI_VERDICT_CACHE` holds the cache db path; unset disables caching entirely. */
export const verdictCachePath = (): string | undefined => process.env.OMI_VERDICT_CACHE?.trim() || undefined;
