const { redis, isConnected } = require('../utils/redisUtils');
const { STATE_EXPIRY_SECONDS, STATE_CACHE_TTL, REDIS_OPERATION_TIMEOUT } = require('../config/constants');

// Add a cache for recently used states to reduce Redis lookups
const stateCache = new Map();

/**
 * Load session state with retries and cache
 * @param {string} sessionId - The session ID
 * @returns {object|null} The session state or null if not found
 */
async function loadSessionState(sessionId) {
  const stateKey = `email_state:${sessionId}`;
  
  // Try cache first for performance
  const cachedState = stateCache.get(stateKey);
  if (cachedState && (Date.now() - cachedState.timestamp) < STATE_CACHE_TTL) {
    console.log(`[${sessionId}] Using cached state (age: ${(Date.now() - cachedState.timestamp)/1000}s)`);
    return JSON.parse(JSON.stringify(cachedState.data)); // Create a deep copy
  }
  
  // Try Redis with retries
  let retryCount = 0;
  const maxRetries = 2;
  
  while (retryCount <= maxRetries) {
    try {
      if (await isConnected()) {
        const stateString = await Promise.race([
          redis.get(stateKey),
          new Promise((_, reject) => 
            setTimeout(() => reject(new Error('Redis get timeout')), 
            REDIS_OPERATION_TIMEOUT * 1.5) // Extended timeout for reliability
          )
        ]);
        
        if (stateString) {
          const state = JSON.parse(stateString);
          
          // Update cache for future access
          stateCache.set(stateKey, {
            data: JSON.parse(JSON.stringify(state)),
            timestamp: Date.now(),
            source: 'redis'
          });
          
          console.log(`[${sessionId}] Loaded state from Redis (${state.collectedData?.length || 0} segments)`);
          return state;
        }
      }
      
      // If we reach here, either Redis isn't connected or the key doesn't exist
      return null;
    } catch (error) {
      retryCount++;
      if (retryCount <= maxRetries) {
        console.warn(`[${sessionId}] Retry ${retryCount}/${maxRetries} fetching state`);
        await new Promise(resolve => setTimeout(resolve, 500 * retryCount)); // Exponential backoff
      } else {
        console.error(`[${sessionId}] Failed to load state after ${maxRetries} retries`);
        return null;
      }
    }
  }
  
  return null;
}

/**
 * Save session state with retries
 * @param {string} sessionId - The session ID
 * @param {object} state - The state object to save
 * @returns {boolean} Success status
 */
async function saveSessionState(sessionId, state) {
  const stateKey = `email_state:${sessionId}`;
  
  // Always update cache first
  stateCache.set(stateKey, {
    data: JSON.parse(JSON.stringify(state)),
    timestamp: Date.now(),
    source: 'saveOperation'
  });
  
  // Try Redis with retries
  let retryCount = 0;
  const maxRetries = 2;
  
  while (retryCount <= maxRetries) {
    try {
      if (await isConnected()) {
        await redis.set(stateKey, JSON.stringify(state), 'EX', STATE_EXPIRY_SECONDS);
        console.log(`[${sessionId}] Saved state to Redis and cache (${state.collectedData?.length || 0} segments)`);
        return true;
      } else {
        console.log(`[${sessionId}] Saved state to cache only (Redis not connected)`);
        return true;
      }
    } catch (error) {
      retryCount++;
      if (retryCount <= maxRetries) {
        console.warn(`[${sessionId}] Retry ${retryCount}/${maxRetries} saving state`);
        await new Promise(resolve => setTimeout(resolve, 500 * retryCount)); // Exponential backoff
      } else {
        console.error(`[${sessionId}] Failed to save state after ${maxRetries} retries`);
        return false;
      }
    }
  }
  
  return false;
}

/**
 * Clear session state
 * @param {string} sessionId - The session ID
 * @returns {boolean} Success status
 */
async function clearSessionState(sessionId) {
  const stateKey = `email_state:${sessionId}`;
  
  // Clear from cache
  stateCache.delete(stateKey);
  
  // Clear from Redis
  try {
    if (await isConnected()) {
      await redis.del(stateKey);
      console.log(`[${sessionId}] Cleared state from Redis and cache`);
      return true;
    }
  } catch (error) {
    console.error(`[${sessionId}] Error clearing state from Redis:`, error);
  }
  
  return true; // Cache was cleared at least
}

module.exports = {
  loadSessionState,
  saveSessionState,
  clearSessionState
}; 