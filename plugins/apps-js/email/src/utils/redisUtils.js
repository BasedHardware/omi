   // ./src/utils/redisUtils.js
   const Redis = require('ioredis');

   let redisClient = null;
   let isRedisConnected = false;

   const REDIS_RECONNECT_TIMEOUT = 5000; // 5 seconds
   const MAX_RECONNECT_ATTEMPTS = 5;

   // Redis configuration for Upstash using separate credentials
   const redisConfig = {
     host: process.env.UPSTASH_REDIS_HOST,
     port: process.env.UPSTASH_REDIS_PORT || 6379,
     password: process.env.UPSTASH_REDIS_PASSWORD,
     tls: true, // Required for Upstash
     retryStrategy(times) {
       if (times > MAX_RECONNECT_ATTEMPTS) {
         console.error('Max Redis reconnection attempts reached, giving up');
         return null; // Stop retrying
       }
       const delay = Math.min(times * 500, REDIS_RECONNECT_TIMEOUT);
       console.log(`Retrying Redis connection in ${delay}ms...`);
       return delay;
     }
   };

   async function initializeRedis() {
     try {
       if (redisClient) {
         console.log('Redis client already exists, checking connection...');
         if (isRedisConnected) {
           return true;
         }
         // If not connected, close existing client and create new one
         await closeRedisConnection();
       }

       console.log('Initializing Redis client...');
       redisClient = new Redis(redisConfig);

       // Handle connection events
       redisClient.on('connect', () => {
         console.log('Redis client connecting...');
       });

       redisClient.on('ready', () => {
         console.log('Redis client connected and ready');
         isRedisConnected = true;
       });

       redisClient.on('error', (err) => {
         console.error('Redis client error:', err);
         isRedisConnected = false;
       });

       redisClient.on('close', () => {
         console.log('Redis connection closed');
         isRedisConnected = false;
       });

       redisClient.on('reconnecting', () => {
         console.log('Redis client reconnecting...');
       });

       // Test connection
       await redisClient.ping();
       console.log('Redis connection test successful');
       isRedisConnected = true;
       return true;
     } catch (error) {
       console.error('Failed to initialize Redis:', error);
       isRedisConnected = false;
       return false;
     }
   }

   async function closeRedisConnection() {
     if (redisClient) {
       try {
         console.log('Closing Redis connection...');
         await redisClient.quit();
         redisClient = null;
         isRedisConnected = false;
         console.log('Redis connection closed successfully');
       } catch (error) {
         console.error('Error closing Redis connection:', error);
         // Force disconnect if quit fails
         redisClient.disconnect();
         redisClient = null;
         isRedisConnected = false;
       }
     }
   }

   async function isConnected() {
     if (!redisClient || !isRedisConnected) {
       return false;
     }
     
     try {
       await redisClient.ping();
       return true;
     } catch (error) {
       console.error('Redis connection check failed:', error);
       isRedisConnected = false;
       return false;
     }
   }

   // Wrapper for Redis operations with retries
   async function redisOperation(operation) {
     let attempts = 0;
     const maxAttempts = 3;

     while (attempts < maxAttempts) {
       try {
         if (!isRedisConnected) {
           await initializeRedis();
         }
         return await operation(redisClient);
       } catch (error) {
         attempts++;
         console.error(`Redis operation failed (attempt ${attempts}):`, error);
         
         if (attempts === maxAttempts) {
           throw error;
         }
         
         // Wait before retry
         await new Promise(resolve => setTimeout(resolve, 1000 * attempts));
       }
     }
   }

   // Enhanced Redis interface with list operations
   const redis = {
     get: async (key) => redisOperation(async (client) => await client.get(key)),
     set: async (key, value, ...args) => redisOperation(async (client) => await client.set(key, value, ...args)),
     del: async (key) => redisOperation(async (client) => await client.del(key)),
     exists: async (key) => redisOperation(async (client) => await client.exists(key)),
     expire: async (key, seconds) => redisOperation(async (client) => await client.expire(key, seconds)),
     ttl: async (key) => redisOperation(async (client) => await client.ttl(key)),
     // Add list operations
     lpush: async (key, value) => redisOperation(async (client) => await client.lpush(key, value)),
     rpush: async (key, value) => redisOperation(async (client) => await client.rpush(key, value)),
     ltrim: async (key, start, stop) => redisOperation(async (client) => await client.ltrim(key, start, stop)),
     lrange: async (key, start, stop) => redisOperation(async (client) => await client.lrange(key, start, stop))
   };

   module.exports = {
     redis,
     initializeRedis,
     closeRedisConnection,
     isConnected
   };