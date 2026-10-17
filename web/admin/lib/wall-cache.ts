import { computeWall, emptyWallMetrics, WallPayload } from "./wall-metrics";
import { DEFINITION_VERSION, isoDay, utcDay } from "./qualified-activity";
import {
  WallJobCache,
  WALL_SOURCE_TTL,
  WALL_RETRY_COOLDOWN,
} from "./wall-job-cache";

const TTL = WALL_SOURCE_TTL;
const MAX_AGE = 24 * 60 * 60_000;
const COLD_WAIT = 5_000;
// Process-local, disposable single flight. The route retains work with after().
// Cloud Run production must supply CPU after HTTP completion: the code-owned
// admin deploy contract pins --no-cpu-throttling. This is not a durable job/cache.
let cached: { day: string; at: number; payload: WallPayload } | null = null;
let flight: Promise<WallPayload> | null = null;
let retryAfter = 0;
let refreshError: string | undefined;
let lastFailure: WallPayload | null = null;
let jobs = new WallJobCache();
const computeCachedWall: typeof computeWall = (sources, now) =>
  computeWall(sources, now, jobs);

function keepGoodMetrics(
  payload: WallPayload,
  previous: WallPayload | undefined
) {
  const prior = new Map(previous?.metrics.map((m) => [m.id, m]));
  return {
    ...payload,
    metrics: payload.metrics.map((m) => {
      const old = prior.get(m.id);
      if (!m.retryableFailure || m.value != null || old?.value == null)
        return m;
      const retainedSince = old.retainedSince || new Date().toISOString();
      if (Date.now() - Date.parse(retainedSince) >= MAX_AGE) return m;
      return {
        ...old,
        stale: true,
        partial: true,
        retainedSince,
        retryableFailure: m.retryableFailure,
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
export async function wallPayload(
  now = new Date(),
  compute = computeCachedWall,
  retain: (work: Promise<unknown>) => void = () => {}
): Promise<WallPayload> {
  const day = isoDay(utcDay(now));
  const age = cached ? now.getTime() - cached.at : Infinity;
  if (
    cached?.day === day &&
    age < (cached.payload.retryableFailures ? WALL_RETRY_COOLDOWN : TTL) &&
    now.getTime() < (cached.payload.sourceRefreshAfter ?? Infinity)
  )
    return cached.payload;
  const usable = cached && age < MAX_AGE ? cached : null;
  if (!flight && now.getTime() >= retryAfter) {
    const promise = compute(undefined, now)
      .then((payload) => {
        if (payload.metrics.every((m) => m.value == null)) {
          lastFailure = payload;
          refreshError = "All wall aggregate sources failed; retry pending";
          retryAfter = Date.now() + WALL_RETRY_COOLDOWN;
          return payload;
        }
        payload = keepGoodMetrics(payload, usable?.payload);
        cached = { day, at: Date.now(), payload };
        refreshError = undefined;
        lastFailure = null;
        retryAfter = 0;
        return payload;
      })
      .catch(() => {
        refreshError = "Wall refresh failed; retry pending";
        retryAfter = Date.now() + WALL_RETRY_COOLDOWN;
        return {
          ...(lastFailure || loading(refreshError)),
          refreshing: false,
          refreshError,
        };
      })
      .finally(() => {
        if (flight === promise) flight = null;
      });
    flight = promise;
    retain(promise);
  }
  if (usable)
    return {
      ...usable.payload,
      refreshing: Boolean(flight),
      cacheStale: usable.day !== day || Boolean(refreshError),
      refreshError,
    };
  if (!flight)
    return {
      ...(lastFailure || loading(refreshError)),
      refreshing: false,
      refreshError,
    };
  // A truly cold process returns honest loading cards before Infinity's 60s
  // timeout, while after() completes the single shared refresh. No fake zeros.
  const work = flight;
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      work,
      new Promise<WallPayload>((resolve) => {
        timer = setTimeout(() => resolve(loading()), COLD_WAIT);
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
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
}
