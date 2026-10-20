import { createHash } from "crypto";
import {
  computeWall,
  defaultWallSources,
  emptyWallMetrics,
  WallPayload,
} from "./wall-metrics";
import { DEFINITION_VERSION, isoDay, utcDay } from "./qualified-activity";
import {
  WallJobCache,
  WALL_SOURCE_TTL,
  WALL_RETRY_COOLDOWN,
} from "./wall-job-cache";
import type { Query } from "./wall-posthog";
import {
  firestoreSeriesStore,
  INSTANCE_ID,
  LEASE_MS,
  LegDoc,
  memorySeriesStore,
  SeriesStore,
  StoredRead,
} from "./wall-series-store";

/** The v2 snapshot, shared across Cloud Run instances like the series legs.
 *
 * The last good payload lives in the shared store (`wall-series-store`, leg
 * `snapshot`), so any instance serves it at once: a recycled or new instance
 * never blanks the TV. One instance refreshes it at a time under a fenced
 * lease, retained with after() (the admin deploy pins --no-cpu-throttling);
 * the day's PostHog reads are persisted as they complete, so a refresh that
 * moves to another instance reuses reads younger than the source TTL. A
 * failing source keeps its previous good metric, labelled stale, for 24h.
 * Only when the shared store keeps failing does an instance refresh from
 * process memory, still single-flight.
 */
const TTL = WALL_SOURCE_TTL;
const MAX_AGE = 24 * 60 * 60_000;
const COLD_WAIT = 5_000;
const SHARED_READ_MS = 10_000;
const STORE_WAIT = 2_000;
/** A fresh process's first store read also opens the Firestore channel; it
 * gets longer so a new revision serves the last good instead of "—". */
export const COLD_STORE_WAIT = 4_500;
const STORE_FAIL_LIMIT = 5;
const STORE_FAIL_WINDOW = 10 * 60_000;
export const SNAPSHOT_LEG = "snapshot";
/** The routes' shared store: Firestore on Cloud Run only, so a local dev
 * server (missing production source keys) never overwrites the TV's snapshot. */
export const wallSnapshotStore = (): SeriesStore | undefined =>
  process.env.K_REVISION ? firestoreSeriesStore : undefined;

interface SnapshotEntry {
  day: string;
  at: number;
  payload: WallPayload;
}
let cached: SnapshotEntry | null = null;
let flight: Promise<unknown> | null = null;
let retryAfter = 0;
let refreshError: string | undefined;
let lastFailure: WallPayload | null = null;
let jobs = new WallJobCache();
let localStore = memorySeriesStore();
let sharedRead: Promise<void> | null = null;
let sharedReadAt = -Infinity;
/** Another instance holds the refresh lease until then. */
let busyUntil = 0;
let storeFailures: number[] = [];
const computeCachedWall: typeof computeWall = (sources, now) =>
  computeWall(sources, now, jobs);

class StoreTimeout extends Error {}
class LeaseLost extends Error {}
function withTimeout<T>(work: Promise<T>, wait = STORE_WAIT): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return Promise.race([
    work,
    new Promise<T>(
      (_, reject) =>
        (timer = setTimeout(() => reject(new StoreTimeout()), wait))
    ),
  ]).finally(() => clearTimeout(timer));
}
function storeFailed(now: number) {
  storeFailures = [
    ...storeFailures.filter((t) => now - t < STORE_FAIL_WINDOW),
    now,
  ];
}
const storeDown = (now: number) =>
  storeFailures.filter((t) => now - t < STORE_FAIL_WINDOW).length >=
  STORE_FAIL_LIMIT;
const sqlHash = (sql: string) =>
  createHash("sha1").update(sql).digest("hex").slice(0, 16);

function fresh(entry: SnapshotEntry | null, now: number, day: string) {
  return (
    entry != null &&
    entry.day === day &&
    now - entry.at <
      (entry.payload.retryableFailures ? WALL_RETRY_COOLDOWN : TTL) &&
    now < (entry.payload.sourceRefreshAfter ?? Infinity)
  );
}
/** Take a newer shared payload with the current definitions. */
function adopt(entry: SnapshotEntry | null | undefined) {
  if (
    entry?.payload?.definitionVersion === DEFINITION_VERSION &&
    (!cached || entry.at > cached.at)
  )
    cached = entry;
}
/** Single-flight, throttled read of the shared snapshot doc. */
function syncShared(store: SeriesStore, now: number) {
  if (!sharedRead || now - sharedReadAt >= SHARED_READ_MS) {
    sharedReadAt = now;
    sharedRead = withTimeout(
      store.read<SnapshotEntry>(SNAPSHOT_LEG),
      cached ? STORE_WAIT : COLD_STORE_WAIT
    ).then(
      (doc) => {
        storeFailures = [];
        adopt(doc?.entry);
      },
      () => storeFailed(now)
    );
  }
  return sharedRead;
}

function keepGoodMetrics(
  payload: WallPayload,
  previous: WallPayload | undefined
) {
  const prior = new Map(previous?.metrics.map((m) => [m.id, m]));
  return {
    ...payload,
    metrics: payload.metrics.map((m) => {
      const old = prior.get(m.id);
      const failure = m.sourceFailure || m.retryableFailure;
      if (!failure || m.value != null || old?.value == null) return m;
      const retainedSince = old.retainedSince || new Date().toISOString();
      if (Date.now() - Date.parse(retainedSince) >= MAX_AGE) return m;
      return {
        ...old,
        stale: true,
        partial: true,
        retainedSince,
        retryableFailure: m.retryableFailure,
        sourceFailure: failure,
      };
    }),
  };
}

function loading(
  reason = "Initial source refresh running; updates automatically"
): WallPayload {
  const metrics = Object.values(emptyWallMetrics()).map((m) => ({
    ...m,
    reason,
  }));
  return {
    definitionVersion: DEFINITION_VERSION,
    retryableFailures: 0,
    generatedAt: new Date().toISOString(),
    metrics,
    partial: true,
    refreshing: true,
  };
}

function log(fields: Record<string, unknown>) {
  // Aggregates only: outcome, timings and counts.
  console.log(
    JSON.stringify({
      event: "wall_snapshot_refresh",
      instance: INSTANCE_ID,
      ...fields,
    })
  );
}

async function refresh(
  store: SeriesStore,
  compute: typeof computeWall,
  now: Date,
  day: string
) {
  const nowMs = now.getTime();
  const started = Date.now();
  const clock = () => nowMs + (Date.now() - started);
  const shared = store !== localStore;
  const fillStore = shared && storeDown(nowMs) ? localStore : store;
  const attempt = fillStore.acquire(SNAPSHOT_LEG, INSTANCE_ID, nowMs);
  const lease = await withTimeout(attempt).catch(() => {
    // Unknown outcome: never ownership. A late grant is handed back.
    attempt.then((late) => {
      if (late.status === "acquired")
        void fillStore.release(SNAPSHOT_LEG, late.token);
    });
    return { status: "unavailable" as const };
  });
  if (fillStore === store && shared)
    lease.status === "unavailable" ? storeFailed(nowMs) : (storeFailures = []);
  if (lease.status === "contended") {
    busyUntil = lease.until;
    return;
  }
  if (lease.status !== "acquired") return;
  const token = lease.token;
  // Re-read under the lease: another holder may have just finished.
  let doc: LegDoc<SnapshotEntry> | null;
  try {
    doc = await withTimeout(fillStore.read<SnapshotEntry>(SNAPSHOT_LEG));
  } catch {
    if (fillStore === store && shared) storeFailed(nowMs);
    void fillStore.release(SNAPSHOT_LEG, token);
    return;
  }
  adopt(doc?.entry);
  if (fresh(cached, nowMs, day)) {
    void fillStore.release(SNAPSHOT_LEG, token);
    return;
  }
  const reads: Record<string, StoredRead> =
    doc?.reads?.day === day ? { ...doc.reads.rows } : {};
  let lost = false;
  let saving: Promise<unknown> = Promise.resolve();
  let posthogReads = 0;
  const query: Query = async (sql) => {
    if (lost) throw new LeaseLost();
    const key = sqlHash(sql);
    const hit = reads[key];
    if (hit && Date.now() - hit.at < TTL)
      return Object.assign(
        hit.rows.map((r) => [...r]),
        { sourceRefreshedAt: hit.refreshedAt }
      );
    posthogReads++;
    const rows = await defaultWallSources.query(sql);
    const read: StoredRead = {
      rows: rows.map((r) => [...r]),
      refreshedAt: rows.sourceRefreshedAt ?? null,
      at: Date.now(),
    };
    reads[key] = read;
    // Persist progress (fenced, merged) so another instance can reuse it.
    saving = saving
      .then(() =>
        fillStore.write(
          SNAPSHOT_LEG,
          token,
          { reads: { day, rows: { [key]: read } } },
          clock()
        )
      )
      .then(
        (written) => {
          if (written !== "written") lost = true;
        },
        () => {
          lost = true;
        }
      );
    return rows;
  };
  const renew = setInterval(() => {
    fillStore.renew(SNAPSHOT_LEG, token, clock()).then(
      (ok) => {
        if (!ok) lost = true;
      },
      () => {
        lost = true;
      }
    );
  }, LEASE_MS / 3);
  let outcome = "ok";
  try {
    let payload = await compute({ ...defaultWallSources, query }, now).finally(
      async () => {
        clearInterval(renew);
        await saving;
      }
    );
    if (lost) {
      // Another holder owns the refresh: drop this result and its job receipts.
      outcome = "lease_lost";
      jobs = new WallJobCache();
      sharedReadAt = -Infinity;
      return;
    }
    if (payload.metrics.every((m) => m.value == null)) {
      outcome = "all_failed";
      lastFailure = payload;
      refreshError = "All wall aggregate sources failed; retry pending";
      retryAfter = Date.now() + WALL_RETRY_COOLDOWN;
      return;
    }
    const previous =
      cached && Date.now() - cached.at < MAX_AGE ? cached.payload : undefined;
    payload = keepGoodMetrics(payload, previous);
    const entry = { day, at: Date.now(), payload };
    cached = entry;
    refreshError = undefined;
    lastFailure = null;
    retryAfter = 0;
    const written = await fillStore
      .write(
        SNAPSHOT_LEG,
        token,
        { entry, reads: { day, rows: reads } },
        clock()
      )
      .catch(() => "unavailable" as const);
    if (written !== "written") outcome = `store_${written}`;
  } catch {
    outcome = "error";
    refreshError = "Wall refresh failed; retry pending";
    retryAfter = Date.now() + WALL_RETRY_COOLDOWN;
  } finally {
    clearInterval(renew);
    await fillStore.release(SNAPSHOT_LEG, token);
    log({
      outcome,
      duration_ms: Date.now() - started,
      posthog_reads: posthogReads,
      null_metrics: cached?.payload.metrics.filter((m) => m.value == null)
        .length,
      stale_metrics: cached?.payload.metrics.filter((m) => m.retainedSince)
        .length,
      store: fillStore === localStore && shared ? "process" : "shared",
    });
  }
}

/** What a request sees now: last good, honest loading, or the last failure. */
function view(day: string, now: number): WallPayload {
  const refreshing = Boolean(flight) || now < busyUntil;
  if (cached && now - cached.at < MAX_AGE)
    return {
      ...cached.payload,
      refreshing,
      cacheStale: cached.day !== day || Boolean(refreshError),
      refreshError,
    };
  if (refreshing) return loading();
  return {
    ...(lastFailure || loading(refreshError)),
    refreshing: false,
    refreshError,
  };
}

export async function wallPayload(
  now = new Date(),
  compute = computeCachedWall,
  retain: (work: Promise<unknown>) => void = () => {},
  /** Shared cross-instance state; process memory when absent (tests). */
  store: SeriesStore = localStore
): Promise<WallPayload> {
  const day = isoDay(utcDay(now));
  const nowMs = now.getTime();
  if (fresh(cached, nowMs, day)) return cached!.payload;
  await syncShared(store, nowMs);
  if (fresh(cached, nowMs, day)) {
    busyUntil = 0;
    return cached!.payload;
  }
  if (!flight && nowMs >= retryAfter && nowMs >= busyUntil) {
    const promise: Promise<unknown> = refresh(store, compute, now, day).finally(
      () => {
        if (flight === promise) flight = null;
      }
    );
    flight = promise;
    retain(promise);
  }
  if (!flight || (cached && nowMs - cached.at < MAX_AGE))
    return view(day, nowMs);
  // A truly cold instance (no last good anywhere) returns honest loading cards
  // before Infinity's 60s timeout, while after() completes the one refresh.
  const work = flight;
  let timer: ReturnType<typeof setTimeout> | undefined;
  await Promise.race([
    work,
    new Promise((resolve) => (timer = setTimeout(resolve, COLD_WAIT))),
  ]);
  if (timer) clearTimeout(timer);
  return fresh(cached, nowMs, day) ? cached!.payload : view(day, nowMs);
}
/** Resolves once no snapshot refresh is running; background series reads yield to it. */
export function wallRefreshSettled(): Promise<unknown> {
  return flight ? flight.catch(() => undefined) : Promise.resolve();
}
export function resetWallCache() {
  cached = null;
  flight = null;
  retryAfter = 0;
  refreshError = undefined;
  lastFailure = null;
  jobs = new WallJobCache();
  localStore = memorySeriesStore();
  sharedRead = null;
  sharedReadAt = -Infinity;
  busyUntil = 0;
  storeFailures = [];
}
