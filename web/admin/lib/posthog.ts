// Shared PostHog HogQL access with 429 backoff + Firestore result caching.
//
// PostHog's query endpoint is aggressively rate-limited. The dashboard fires
// ~8 HogQL queries on every load; without caching, reloads + SWR retries blow
// the personal-API-key quota and every panel 429s.
//
// Cache backend = Firestore. The admin service's configured Redis
// (light-eel-27878.upstash.io) is dead — the logs are flooded with
// "Redis error: getaddrinfo ENOTFOUND" — so Redis caching was a silent no-op
// and every load re-queried PostHog. Firestore is always reachable here via
// firebase-admin (same path macos-versions already uses). Results are stored
// JSON-stringified to sidestep Firestore's no-nested-arrays rule.
//
// `posthogResults` caches each query's result, so a given query hits PostHog at
// most once per soft-TTL window instead of on every load. On throttle/error it
// serves the last good cached value rather than failing the panel.

import { createHash } from "crypto";
import { getDb } from "@/lib/firebase/admin";

const CACHE_COLLECTION = "admin_stats_cache";
const SOFT_TTL_MS = 30 * 60 * 1000; // serve cached without re-querying for 30 min

// PostHog's query API fills `LIMIT 100` into any HogQL (sub)query that carries
// none and truncates silently — this cut the newest days off the
// response-reliability charts (#10191) and drops per-version rows on the
// releases panel (#10190). 50_000 is PostHog's served maximum (verified live:
// `LIMIT 100000` returns exactly 50000 rows).
export const POSTHOG_SERVED_MAX_ROWS = 50_000;

// Guard against the silent default cap by binding one explicit outer LIMIT to
// the whole result. Wrapping in a subquery is required for correctness with
// `UNION ALL`, where a trailing `LIMIT` binds to the last arm only (verified:
// `SELECT 1 UNION ALL SELECT 2 LIMIT 1` returns 2 rows). Wrapping only ever
// adds a ceiling: a caller's tighter inner `LIMIT` still wins, so this never
// widens an intentionally small query.
export function withRowLimit(
  query: string,
  max: number = POSTHOG_SERVED_MAX_ROWS,
): string {
  return `SELECT * FROM (\n${query}\n) AS _row_limit_guard\nLIMIT ${max}`;
}

type CacheDoc = { payload: string; freshAt: number };

async function readCache(
  key: string,
): Promise<{ results: unknown[]; freshAt: number } | null> {
  try {
    const snap = await getDb().collection(CACHE_COLLECTION).doc(key).get();
    if (!snap.exists) return null;
    const d = snap.data() as CacheDoc;
    if (!d?.payload) return null;
    return { results: JSON.parse(d.payload), freshAt: d.freshAt ?? 0 };
  } catch {
    return null; // best-effort cache read
  }
}

async function writeCache(key: string, results: unknown[]): Promise<void> {
  try {
    const payload = JSON.stringify(results);
    if (payload.length > 900_000) return; // Firestore field cap ~1 MB; skip oversized
    await getDb()
      .collection(CACHE_COLLECTION)
      .doc(key)
      .set({ payload, freshAt: Date.now() });
  } catch {
    // best-effort cache write; never block the response
  }
}

export async function posthogFetch(
  host: string,
  projectId: string,
  apiKey: string,
  query: string,
  { maxRetries = 2 }: { maxRetries?: number } = {},
): Promise<Response> {
  const url = `${host}/api/projects/${projectId}/query/`;
  let res!: Response;
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    res = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        query: { kind: "HogQLQuery", query: withRowLimit(query) },
      }),
    });
    if (res.status !== 429 || attempt === maxRetries) return res;
    const waitMs = 800 * (attempt + 1) + Math.floor(Math.random() * 300);
    await new Promise((r) => setTimeout(r, waitMs));
  }
  return res;
}

/**
 * Drop-in replacement for `fetch(<posthog query endpoint>, {...})` that adds
 * Firestore result caching + stale-on-throttle, returning a `Response` whose
 * body is always `{ results: [...] }`. Lets routes with many inline query
 * fetches (notifications, floating-bar-usage, message-ratings) get caching
 * without restructuring — just swap the `fetch(...)` call for this and keep the
 * existing `.ok` / `.json()` handling.
 */
export async function cachedPosthogFetch(
  host: string,
  projectId: string,
  apiKey: string,
  query: string,
  opts: { softTtlMs?: number } = {},
): Promise<Response> {
  const softTtlMs = opts.softTtlMs ?? SOFT_TTL_MS;
  const key = createHash("sha1").update(`${projectId}|${query}`).digest("hex");
  const hit = (results: unknown[]) =>
    new Response(JSON.stringify({ results }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });

  const cached = await readCache(key);
  if (cached && Date.now() - cached.freshAt < softTtlMs)
    return hit(cached.results);

  const res = await posthogFetch(host, projectId, apiKey, query);
  if (res.ok) {
    try {
      const raw = await res.clone().json();
      const results = Array.isArray(raw.results) ? raw.results : [];
      await writeCache(key, results);
    } catch {
      // ignore caching errors; return the live response below
    }
    return res;
  }
  if (cached) return hit(cached.results); // serve last good through the throttle
  return res; // no cache to fall back on — surface the error
}

/**
 * Run a HogQL query and return its `results` array, cached in Firestore.
 * - Fresh cache (< soft TTL): returned without touching PostHog.
 * - Stale/miss: query PostHog (with 429 backoff); on success refresh the cache.
 * - On PostHog error/throttle: fall back to the last good cached value if any,
 *   otherwise throw so the route surfaces the failure.
 */
export async function posthogResults(
  host: string,
  projectId: string,
  apiKey: string,
  query: string,
  opts: { softTtlMs?: number } = {},
): Promise<unknown[]> {
  const softTtlMs = opts.softTtlMs ?? SOFT_TTL_MS;
  const key = createHash("sha1").update(`${projectId}|${query}`).digest("hex");

  const cached = await readCache(key);
  if (cached && Date.now() - cached.freshAt < softTtlMs) return cached.results;

  try {
    const res = await posthogFetch(host, projectId, apiKey, query);
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`PostHog API error: ${res.status} ${text.slice(0, 160)}`);
    }
    const raw = await res.json();
    const results = Array.isArray(raw.results) ? raw.results : [];
    // posthogFetch now binds an explicit LIMIT of POSTHOG_SERVED_MAX_ROWS to
    // every query, so the silent default-100 cap can no longer truncate. The
    // remaining ceiling is PostHog's served maximum: a result at that count is
    // itself truncated and the caller should widen its window or paginate.
    if (results.length >= POSTHOG_SERVED_MAX_ROWS) {
      console.warn(
        "PostHog returned the served-max row count — result is truncated at the ceiling",
        {
          servedMax: POSTHOG_SERVED_MAX_ROWS,
          querySnippet: query.replace(/\s+/g, " ").trim().slice(0, 160),
        },
      );
    }
    await writeCache(key, results);
    return results;
  } catch (err) {
    if (cached) return cached.results; // serve last good value through the throttle
    throw err;
  }
}
