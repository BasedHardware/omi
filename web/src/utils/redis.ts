import { createClient } from 'redis';

const redisClient = createClient({
  url: `redis://${process.env.REDIS_DB_HOST}:${process.env.REDIS_DB_PORT || 6379}`,
  password: process.env.REDIS_DB_PASSWORD,
});

redisClient.on('error', (err) => console.error('Redis Client Error', err));

const connectRedis = async () => {
  await redisClient.connect();
};

connectRedis().catch(console.error);

export default redisClient;
