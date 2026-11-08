import Redis from "ioredis";

let _redis: Redis | null = null;
let _warnedUnset = false;
let _lastErrorMessage: string | null = null;

/**
 * Shared best-effort Redis client. Redis is optional: when REDIS_HOST is
 * unset or unreachable, callers fall back to their source of truth.
 */
export function getRedis(): Redis | null {
  if (_redis) return _redis;

  const host = process.env.REDIS_HOST;
  const port = parseInt(process.env.REDIS_PORT || "6379", 10);
  const password = process.env.REDIS_PASSWORD;

  if (!host) {
    if (!_warnedUnset) {
      _warnedUnset = true;
      console.warn("REDIS_HOST not set — Redis cache and invalidation disabled");
    }
    return null;
  }

  _redis = new Redis({
    host,
    port,
    password: password || undefined,
    lazyConnect: true,
    // Best-effort invalidation must release durable writes during a blackhole.
    connectTimeout: 100,
    commandTimeout: 100,
    maxRetriesPerRequest: 0,
    autoResendUnfulfilledCommands: false,
  });
  _redis.on("ready", () => {
    _lastErrorMessage = null;
  });
  // ioredis keeps retrying an unreachable host about every 2s. Log the first
  // failure for each distinct message, then stay quiet until the link recovers.
  _redis.on("error", (err) => {
    if (err.message === _lastErrorMessage) return;
    _lastErrorMessage = err.message;
    console.error("Redis unavailable, using fallbacks:", err.message);
  });
  return _redis;
}

/**
 * Read a JSON value from Redis. Returns null if Redis is unavailable,
 * the key is missing, or the stored value can't be parsed. Errors are
 * logged but never thrown — callers should treat this as a best-effort
 * cache read and fall back to the source of truth.
 */
export async function getJsonCache<T>(key: string): Promise<T | null> {
  const redis = getRedis();
  if (!redis) return null;
  try {
    const raw = await redis.get(key);
    if (!raw) return null;
    return JSON.parse(raw) as T;
  } catch (err) {
    console.error(`Redis get ${key} failed:`, err);
    return null;
  }
}

/**
 * Write a JSON value to Redis with a TTL (in seconds). Fail-open: any
 * serialization or transport error is logged and swallowed.
 */
export async function setJsonCache(
  key: string,
  value: unknown,
  ttlSeconds: number
): Promise<void> {
  const redis = getRedis();
  if (!redis) return;
  try {
    await redis.set(key, JSON.stringify(value), "EX", ttlSeconds);
  } catch (err) {
    console.error(`Redis set ${key} failed:`, err);
  }
}

/**
 * Delete the enforcement stage cache for a user.
 * Matches backend's invalidate_enforcement_cache() in utils/fair_use.py.
 * Fail-open: errors are logged but do not block the admin action.
 */
export async function invalidateEnforcementCache(uid: string): Promise<void> {
  const redis = getRedis();
  if (!redis) return;

  try {
    await redis.del(`fair_use:stage:${uid}`);
  } catch (err) {
    console.error("Failed to invalidate enforcement cache:", err);
  }
}
