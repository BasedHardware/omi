/**
 * Shared caching infrastructure for API data
 *
 * Features:
 * - Typed cache entries by domain (conversations, memories, etc.)
 * - Stale-while-revalidate support
 * - Event-based cache invalidation
 * - Request deduplication
 */

// Cache TTL constants
export const CACHE_TTL = {
  SHORT: 60 * 1000,        // 1 minute - user-specific frequently changing data
  MEDIUM: 5 * 60 * 1000,   // 5 minutes - lists that update occasionally
  LONG: 60 * 60 * 1000,    // 1 hour - static/reference data
} as const;

// Cache entry with metadata
interface CacheEntry<T> {
  data: T;
  timestamp: number;
  ttl: number;
}

// In-flight request tracking for deduplication
const pendingRequests = new Map<string, Promise<unknown>>();

// Main cache storage
const cache = new Map<string, CacheEntry<unknown>>();

// Keys that should persist to sessionStorage for instant loads
const PERSISTENT_KEYS = ['memories:', 'conversations:', 'actionItems', 'folders'];

// Try to hydrate cache from sessionStorage on module load
if (typeof window !== 'undefined') {
  try {
    const stored = sessionStorage.getItem('omi_cache');
    if (stored) {
      const parsed = JSON.parse(stored) as Record<string, CacheEntry<unknown>>;
      for (const [key, entry] of Object.entries(parsed)) {
        // Only restore if not expired (check against original TTL)
        if (Date.now() - entry.timestamp < entry.ttl) {
          cache.set(key, entry);
        }
      }
    }
  } catch {
    // Ignore parse errors
  }
}

// Persist cache to sessionStorage (debounced)
let persistTimeout: ReturnType<typeof setTimeout> | null = null;
function persistCache(): void {
  if (typeof window === 'undefined') return;
  if (persistTimeout) clearTimeout(persistTimeout);

  persistTimeout = setTimeout(() => {
    try {
      const toStore: Record<string, CacheEntry<unknown>> = {};
      for (const [key, entry] of cache.entries()) {
        // Only persist certain keys to avoid bloating storage
        if (PERSISTENT_KEYS.some(pattern => key.includes(pattern))) {
          toStore[key] = entry;
        }
      }
      sessionStorage.setItem('omi_cache', JSON.stringify(toStore));
    } catch {
      // Ignore storage errors (quota exceeded, etc.)
    }
  }, 100); // Debounce 100ms
}

// Event listeners for invalidation
type InvalidationListener = (pattern: string) => void;
const invalidationListeners = new Set<InvalidationListener>();

/**
 * Get cached data
 * @returns { data, isStale } or null if not in cache
 */
export function getCache<T>(key: string): { data: T; isStale: boolean } | null {
  const entry = cache.get(key) as CacheEntry<T> | undefined;
  if (!entry) return null;

  const isStale = Date.now() - entry.timestamp > entry.ttl;
  return { data: entry.data, isStale };
}

/**
 * Set cache data
 */
export function setCache<T>(key: string, data: T, ttl: number = CACHE_TTL.MEDIUM): void {
  cache.set(key, { data, timestamp: Date.now(), ttl });
  persistCache();
}

/**
 * Update cache data in place (for optimistic updates)
 */
export function updateCache<T>(key: string, updater: (data: T) => T): void {
  const entry = cache.get(key) as CacheEntry<T> | undefined;
  if (entry) {
    entry.data = updater(entry.data);
    entry.timestamp = Date.now(); // Refresh timestamp on update
    persistCache();
  }
}

/**
 * Delete specific cache entry
 */
export function deleteCache(key: string): void {
  cache.delete(key);
  persistCache();
}

/**
 * Invalidate cache entries matching a pattern
 * @param pattern - String pattern to match against cache keys
 */
export function invalidateCache(pattern: string): void {
  const keysToDelete: string[] = [];

  for (const key of cache.keys()) {
    if (key.includes(pattern)) {
      keysToDelete.push(key);
    }
  }

  keysToDelete.forEach(key => cache.delete(key));
  persistCache();

  // Notify listeners
  invalidationListeners.forEach(listener => listener(pattern));
}

/**
 * Subscribe to cache invalidation events
 * @returns Unsubscribe function
 */
export function onCacheInvalidation(listener: InvalidationListener): () => void {
  invalidationListeners.add(listener);
  return () => invalidationListeners.delete(listener);
}

/**
 * Deduplicated fetch - prevents multiple identical requests
 * If a request with the same key is already in flight, returns the existing promise
 */
export async function deduplicatedFetch<T>(
  key: string,
  fetcher: () => Promise<T>
): Promise<T> {
  // Check if request is already in flight
  const pending = pendingRequests.get(key);
  if (pending) {
    return pending as Promise<T>;
  }

  // Start new request
  const promise = fetcher().finally(() => {
    pendingRequests.delete(key);
  });

  pendingRequests.set(key, promise);
  return promise;
}

/**
 * Fetch with cache - returns cached data immediately if available,
 * then optionally revalidates in background
 */
export async function fetchWithCache<T>(
  key: string,
  fetcher: () => Promise<T>,
  options: {
    ttl?: number;
    forceRefresh?: boolean;
    onStaleData?: (data: T) => void;
  } = {}
): Promise<T> {
  const { ttl = CACHE_TTL.MEDIUM, forceRefresh = false, onStaleData } = options;

  // Check cache first
  if (!forceRefresh) {
    const cached = getCache<T>(key);
    if (cached) {
      if (!cached.isStale) {
        // Fresh data - return immediately
        return cached.data;
      } else if (onStaleData) {
        // Stale data - return immediately and revalidate in background
        onStaleData(cached.data);
        // Background revalidation
        deduplicatedFetch(key, fetcher).then(freshData => {
          setCache(key, freshData, ttl);
        }).catch(console.error);
        return cached.data;
      }
    }
  }

  // Fetch fresh data
  const data = await deduplicatedFetch(key, fetcher);
  setCache(key, data, ttl);
  return data;
}

/**
 * Clear all cache entries (useful for logout)
 */
export function clearAllCache(): void {
  cache.clear();
  pendingRequests.clear();
  if (typeof window !== 'undefined') {
    try {
      sessionStorage.removeItem('omi_cache');
    } catch {
      // Ignore storage errors
    }
  }
}

// Cache key generators for consistency
export const cacheKeys = {
  conversations: (folderId?: string, startDate?: string, endDate?: string) =>
    `conversations:${folderId || 'all'}:${startDate || ''}:${endDate || ''}`,

  conversation: (id: string) => `conversation:${id}`,

  memories: (categories: string[]) =>
    `memories:${categories.length === 0 ? 'all' : [...categories].sort().join(',')}`,

  memory: (id: string) => `memory:${id}`,

  recaps: (offset: number) => `recaps:${offset}`,

  actionItems: () => 'actionItems',

  folders: () => 'folders',

  knowledgeGraph: () => 'knowledgeGraph',

  search: (type: string, query: string) => `search:${type}:${query}`,

  apps: (tab: string, filters?: string) => `apps:${tab}:${filters || ''}`,
};

// Invalidation patterns for mutations
export const invalidationPatterns = {
  conversations: 'conversations',
  memories: 'memories',
  actionItems: 'actionItems',
  folders: 'folders',
  apps: 'apps',
};
