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
import type { ModelPort } from "./port";

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

/**
 * Caches `invoke` only. `render` and `compose` are the recall path: they carry a
 * per-run model_version rather than a pinned prompt contract, and their answers
 * are what the recall log grades, so silently replaying an earlier answer there
 * would corrupt an evaluation rather than speed one up.
 */
export class CachingModelPort implements ModelPort {
  readonly stats: CacheStats = { hits: 0, misses: 0, writes: 0, uncacheable: 0 };
  constructor(private readonly inner: ModelPort, private readonly store: VerdictStore, private readonly namespace: string) {}

  async invoke(request: { strategy: string; version: string; input: unknown }): Promise<unknown> {
    const key = verdictKey(this.namespace, request.strategy, request.version, request.input);
    const cached = this.store.get(key);
    if (cached !== undefined) {
      this.stats.hits += 1;
      return JSON.parse(cached);
    }
    this.stats.misses += 1;
    // Deliberately not wrapped in try/catch: a throw propagates uncached, so the
    // caller's retry and retryable-rejection machinery behaves exactly as it
    // does without the cache.
    const result = await this.inner.invoke(request);
    let encoded: string;
    try { encoded = JSON.stringify(result); } catch { this.stats.uncacheable += 1; return result; }
    if (encoded === undefined) { this.stats.uncacheable += 1; return result; }
    this.store.set(key, encoded);
    this.stats.writes += 1;
    return result;
  }

  render(request: { strategy: string; version: string; input: unknown }) { return this.inner.render(request); }
  compose(request: { strategy: string; version: string; input: unknown }) { return this.inner.compose(request); }
}

/** `OMI_VERDICT_CACHE` holds the cache db path; unset disables caching entirely. */
export const verdictCachePath = (): string | undefined => process.env.OMI_VERDICT_CACHE?.trim() || undefined;
