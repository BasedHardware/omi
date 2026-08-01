import { NextResponse } from 'next/server';
import Redis from 'ioredis';
import { authenticateRequest } from '@/lib/firebase-auth';

// Configure Redis client - credentials should be in environment variables
console.log('Initializing Redis client configuration...');
console.log(
  `REDIS_HOST: ${process.env.REDIS_HOST ? 'Loaded' : 'MISSING!'}, REDIS_PORT: ${
    process.env.REDIS_PORT ? 'Loaded' : 'MISSING!'
  }, REDIS_PASSWORD: ${process.env.REDIS_PASSWORD ? 'Set' : 'Not Set'}`,
);

const redisClient = new Redis({
  host: process.env.REDIS_HOST,
  port: parseInt(process.env.REDIS_PORT || '6379', 10),
  password: process.env.REDIS_PASSWORD,
  lazyConnect: true, // Connect only when needed
  showFriendlyErrorStack: process.env.NODE_ENV === 'development',
  retryStrategy(times) {
    const delay = Math.min(times * 50, 2000);
    console.warn(`Redis connection retry attempt ${times}, delaying for ${delay}ms`);
    return delay;
  },
  reconnectOnError(err) {
    console.warn('Redis reconnecting on error:', err.message);
    return true; // or 'attempts': 5
  },
});

redisClient.on('connect', () => console.log('Redis client connecting...'));
redisClient.on('ready', () => console.log('Redis client ready.'));
redisClient.on('error', (err) => console.error('Redis Client Global Error:', err));
redisClient.on('close', () => console.log('Redis client connection closed.'));
redisClient.on('reconnecting', () => console.log('Redis client reconnecting...'));
redisClient.on('end', () => console.log('Redis client connection ended.'));

export async function POST(req: Request) {
  console.log('[API /api/enable-plugins] Received POST request');
  let currentUid = 'unknown'; // For logging in catch block
  try {
    // Identity comes from the verified Firebase ID token only. Any `uid` in
    // the body is ignored, so a caller cannot force-enable apps on another
    // account or inject into the Redis key namespace.
    const auth = await authenticateRequest(req);
    if ('error' in auth) {
      return NextResponse.json({ error: auth.error }, { status: auth.status });
    }
    const uid = auth.uid;
    currentUid = uid;

    const key = `users:${uid}:enabled_plugins`;
    const pluginsToAdd = [
      '01JQJNSV0X8EN7HF0CP1JZ6MS4', // OMI App ID from .env.local
      '01JQ6XEB4SNXAN5642HGZ0CY4C', // The other specified ID
    ];

    console.log(
      `[API /api/enable-plugins] Executing SADD on key: ${key} with plugins: ${pluginsToAdd.join(
        ', ',
      )} for UID: ${uid}`,
    );
    const result = await redisClient.sadd(key, ...pluginsToAdd);
    console.log(
      `[API /api/enable-plugins] SADD result for key ${key}: ${result}. ${
        result > 0 ? 'Added' : 'Already existed or failed'
      }.`,
    );

    return NextResponse.json({ success: true, addedCount: result });
  } catch (err: any) {
    console.error(
      `[API /api/enable-plugins] Error processing request for UID: ${currentUid}. Error:`,
      err,
    );
    console.error('[API /api/enable-plugins] Error Stack:', err.stack);
    return NextResponse.json({ error: 'Failed to enable plugins' }, { status: 500 });
  }
}
