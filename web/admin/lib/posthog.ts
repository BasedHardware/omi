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

// PostHog's query API fills `LIMIT 100` into any HogQL query (and each UNION
// arm) that carries none, then truncates silently — a grouped query returning
// >100 rows loses the overflow with no error. This is the highest row count
// PostHog will actually serve: `LIMIT 100000` returns exactly 50000 rows (the
// ad-hoc 100000/500000 limits scattered across routes overstate what they get).
export const POSTHOG_MAX_ROWS = 50_000;

/**
 * Guard a LIMIT-less HogQL query against PostHog's silent 100-row cap.
 *
 * A trailing `LIMIT` binds to the last arm of a `UNION` only (verified:
 * `SELECT 1 UNION ALL SELECT 2 LIMIT 1` returns 2 rows), so appending a limit
 * is unsafe. We always wrap the query as a subquery with one outer limit, which
 * caps the whole result regardless of unions or grouping. Callers whose query
 * already pins its own limit are unaffected — the inner limit binds first and
 * the outer high cap is a no-op.
 */
export function withPosthogRowLimit(
  query: string,
  limit: number = POSTHOG_MAX_ROWS,
): string {
  const inner = query.trim().replace(/;\s*$/, "");
  return `SELECT * FROM (\n${inner}\n) LIMIT ${limit}`;
}

const CACHE_COLLECTION = "admin_stats_cache";
const SOFT_TTL_MS = 30 * 60 * 1000; // serve cached without re-querying for 30 min

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
    if (payload.length > 900_000) {
      // Firestore field cap ~1 MB; skip oversized. Log it — silently skipping
      // means the heaviest queries lose caching + stale-on-throttle fallback
      // exactly when they grow large, with no signal that it happened.
      console.warn(
        `PostHog result too large to cache (${payload.length} bytes, ${results.length} rows) — skipping cache write`,
        { key },
      );
      return;
    }
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
      body: JSON.stringify({ query: { kind: "HogQLQuery", query } }),
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
    // PostHog fills LIMIT 100 into any HogQL (sub)query that has none and
    // truncates silently — exactly 100 rows from a LIMIT-less query is the
    // signature of that cap (it cut the newest days off response-reliability).
    if (results.length === 100 && !/\blimit\b/i.test(query)) {
      console.warn(
        "PostHog returned exactly 100 rows for a query without LIMIT — likely truncated by the default cap",
        {
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
