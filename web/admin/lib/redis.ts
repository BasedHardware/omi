import Redis from 'ioredis';

let _redis: Redis | null = null;

function getRedis(): Redis | null {
  if (_redis) return _redis;

  const host = process.env.REDIS_HOST;
  const port = parseInt(process.env.REDIS_PORT || '6379', 10);
  const password = process.env.REDIS_PASSWORD;

  if (!host) {
    console.warn('REDIS_HOST not set — cache invalidation will be skipped');
    return null;
  }

  _redis = new Redis({ host, port, password: password || undefined, lazyConnect: true });
  _redis.on('error', (err) => console.error('Redis error:', err.message));
  return _redis;
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
    console.error('Failed to invalidate enforcement cache:', err);
  }
}
