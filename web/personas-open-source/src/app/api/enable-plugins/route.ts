import { NextResponse } from 'next/server';
import Redis from 'ioredis';

// Configure Redis client - credentials should be in environment variables
const redisClient = new Redis({
  host: process.env.REDIS_HOST,
  port: parseInt(process.env.REDIS_PORT || '6379', 10),
  password: process.env.REDIS_PASSWORD,
  lazyConnect: true, // Connect only when needed
  showFriendlyErrorStack: process.env.NODE_ENV === 'development',
});

redisClient.on('error', (err) => console.error('Redis Client Error:', err));

interface PostBody {
  uid: string;
}

export async function POST(req: Request) {
  try {
    await redisClient.connect(); // Ensure connection before command
    const { uid } = (await req.json()) as PostBody;

    if (!uid) {
      return NextResponse.json({ error: 'Missing uid' }, { status: 400 });
    }

    const key = `users:${uid}:enabled_plugins`;
    const pluginsToAdd = [
      '01JQJNSV0X8EN7HF0CP1JZ6MS4', // OMI App ID from .env.local
      '01JQ6XEB4SNXAN5642HGZ0CY4C'  // The other specified ID
    ];

    const result = await redisClient.sadd(key, ...pluginsToAdd);

    console.log(`Added ${result} plugins to ${key} for uid ${uid}`);

    await redisClient.quit(); // Disconnect after operation

    return NextResponse.json({ success: true, addedCount: result });

  } catch (err: any) {
    console.error('Error enabling plugins in Redis:', err);
    // Attempt to disconnect if an error occurred after connecting
    if (redisClient.status === 'ready' || redisClient.status === 'connecting') {
      await redisClient.quit().catch(quitErr => console.error('Error quitting Redis after error:', quitErr));
    }
    return NextResponse.json(
      { error: 'Failed to enable plugins', details: err.message },
      { status: 500 }
    );
  }
} 