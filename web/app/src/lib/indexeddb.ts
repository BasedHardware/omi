/**
 * IndexedDB Cache Layer for Memories
 *
 * Provides persistent caching of memories in the browser's IndexedDB.
 * This dramatically improves load times for subsequent visits.
 *
 * Benefits:
 * - First visit: Network fetch (slow)
 * - Subsequent visits: Instant load from IndexedDB (~50ms)
 * - Background sync keeps data fresh
 * - Works offline
 */

import { openDB, type DBSchema, type IDBPDatabase } from 'idb';
import type { Memory } from '@/types/conversation';

// Database schema
interface MemoryDB extends DBSchema {
  memories: {
    key: string;
    value: Memory & { cachedAt: number };
  };
  metadata: {
    key: string;
    value: number;
  };
}

const DB_NAME = 'omi-memories';
const DB_VERSION = 1;
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes - after this, data is considered stale

let dbPromise: Promise<IDBPDatabase<MemoryDB>> | null = null;

/**
 * Get or create the IndexedDB database instance
 */
async function getDB(): Promise<IDBPDatabase<MemoryDB>> {
  if (!dbPromise) {
    dbPromise = openDB<MemoryDB>(DB_NAME, DB_VERSION, {
      upgrade(db) {
        // Create object stores on first initialization
        if (!db.objectStoreNames.contains('memories')) {
          db.createObjectStore('memories', { keyPath: 'id' });
        }
        if (!db.objectStoreNames.contains('metadata')) {
          db.createObjectStore('metadata');
        }
      },
    });
  }
  return dbPromise;
}

/**
 * Cache memories to IndexedDB
 *
 * @param memories - Array of memories to cache
 */
export async function cacheMemories(memories: Memory[]): Promise<void> {
  try {
    const db = await getDB();
    const tx = db.transaction('memories', 'readwrite');
    const now = Date.now();

    // Store all memories with timestamp
    await Promise.all([
      ...memories.map((m) => tx.store.put({ ...m, cachedAt: now })),
      tx.done,
    ]);

    // Update last sync time
    await db.put('metadata', now, 'lastSync');

    console.log(`[IndexedDB] Cached ${memories.length} memories`);
  } catch (error) {
    console.error('[IndexedDB] Failed to cache memories:', error);
    // Don't throw - caching is a nice-to-have, not critical
  }
}

/**
 * Get cached memories from IndexedDB
 *
 * @returns Cached memories if fresh, null if stale or not found
 */
export async function getCachedMemories(): Promise<Memory[] | null> {
  try {
    const db = await getDB();
    const lastSync = await db.get('metadata', 'lastSync');

    // Check if cache is stale
    if (!lastSync || Date.now() - lastSync > CACHE_TTL) {
      console.log('[IndexedDB] Cache is stale or not found');
      return null;
    }

    // Get all cached memories
    const cached = await db.getAll('memories');

    if (cached.length === 0) {
      return null;
    }

    // Remove the cachedAt timestamp before returning
    const memories = cached.map(({ cachedAt, ...memory }) => memory as Memory);

    console.log(`[IndexedDB] Loaded ${memories.length} memories from cache`);
    return memories;
  } catch (error) {
    console.error('[IndexedDB] Failed to load cached memories:', error);
    return null;
  }
}

/**
 * Check if cache exists and is fresh
 */
export async function isCacheFresh(): Promise<boolean> {
  try {
    const db = await getDB();
    const lastSync = await db.get('metadata', 'lastSync');
    return lastSync ? Date.now() - lastSync <= CACHE_TTL : false;
  } catch (error) {
    return false;
  }
}

/**
 * Invalidate (clear) the cache
 *
 * Useful for testing or when user explicitly wants fresh data
 */
export async function invalidateCache(): Promise<void> {
  try {
    const db = await getDB();
    const tx = db.transaction(['memories', 'metadata'], 'readwrite');

    await Promise.all([tx.objectStore('memories').clear(), tx.objectStore('metadata').clear(), tx.done]);

    console.log('[IndexedDB] Cache invalidated');
  } catch (error) {
    console.error('[IndexedDB] Failed to invalidate cache:', error);
  }
}

/**
 * Get cache statistics
 */
export async function getCacheStats(): Promise<{
  count: number;
  lastSync: number | null;
  isFresh: boolean;
}> {
  try {
    const db = await getDB();
    const [count, lastSync] = await Promise.all([db.count('memories'), db.get('metadata', 'lastSync')]);

    return {
      count,
      lastSync: lastSync || null,
      isFresh: lastSync ? Date.now() - lastSync <= CACHE_TTL : false,
    };
  } catch (error) {
    return { count: 0, lastSync: null, isFresh: false };
  }
}
