/**
 * IndexedDB cache layer for memories.
 *
 * Memory rows are scoped by Firebase owner and API backend. The scope is part
 * of every record and metadata key so a sign-out, account switch, or backend
 * switch can never reuse another session's persistent cache.
 */

import { openDB, type DBSchema, type IDBPDatabase } from 'idb';
import type { Memory } from '@/types/conversation';
import type { MemoryView } from './api';
import { memoryCacheScopeKey, type MemoryCacheScope } from './cache';

interface CachedMemory extends Memory {
  cacheKey: string;
  ownerId: string;
  backendScope: string;
  cachedAt: number;
  memoryView: MemoryView;
}

interface MemoryDB extends DBSchema {
  memories: {
    key: string;
    value: CachedMemory;
  };
  metadata: {
    key: string;
    value: number;
  };
}

const DB_NAME = 'omi-memories';
const DB_VERSION = 2;
const CACHE_TTL = 5 * 60 * 1000;

let dbPromise: Promise<IDBPDatabase<MemoryDB>> | null = null;

async function getDB(): Promise<IDBPDatabase<MemoryDB>> {
  if (!dbPromise) {
    dbPromise = openDB<MemoryDB>(DB_NAME, DB_VERSION, {
      upgrade(db) {
        // Version 1 used the memory id as a global key. Drop that store during
        // migration instead of exposing legacy unscoped rows to a new owner.
        if (db.objectStoreNames.contains('memories')) {
          db.deleteObjectStore('memories');
        }
        db.createObjectStore('memories', { keyPath: 'cacheKey' });
        if (!db.objectStoreNames.contains('metadata')) {
          db.createObjectStore('metadata');
        }
      },
    });
  }
  return dbPromise;
}

function metadataKey(scope: MemoryCacheScope): string {
  return `${memoryCacheScopeKey(scope)}:lastSync`;
}

function belongsToScope(memory: CachedMemory, scope: MemoryCacheScope): boolean {
  return memory.ownerId === scope.ownerId && memory.backendScope === scope.backendScope;
}

/** Cache a page for one owner/backend/view scope. */
export async function cacheMemories(
  memories: Memory[],
  memoryView: MemoryView = 'useful_now',
  scope: MemoryCacheScope,
): Promise<void> {
  try {
    const db = await getDB();
    const tx = db.transaction(['memories', 'metadata'], 'readwrite');
    const memoryStore = tx.objectStore('memories');
    const existing = await memoryStore.getAll();
    const now = Date.now();
    const scopePrefix = `${memoryCacheScopeKey(scope)}:${memoryView}:`;

    for (const memory of existing) {
      if (memory.cacheKey.startsWith(scopePrefix)) {
        await memoryStore.delete(memory.cacheKey);
      }
    }
    for (const memory of memories) {
      await memoryStore.put({
        ...memory,
        cacheKey: `${scopePrefix}${memory.id}`,
        ownerId: scope.ownerId,
        backendScope: scope.backendScope,
        cachedAt: now,
        memoryView,
      });
    }
    await tx.objectStore('metadata').put(now, metadataKey(scope));
    await tx.done;
  } catch (error) {
    console.error('[IndexedDB] Failed to cache memories:', error);
  }
}

/** Get a fresh page from one owner/backend/view scope. */
export async function getCachedMemories(
  memoryView: MemoryView = 'useful_now',
  scope: MemoryCacheScope,
): Promise<Memory[] | null> {
  try {
    const db = await getDB();
    const lastSync = await db.get('metadata', metadataKey(scope));
    if (!lastSync || Date.now() - lastSync > CACHE_TTL) return null;

    const cached = await db.getAll('memories');
    const scoped = cached.filter(
      (memory) =>
        belongsToScope(memory, scope) &&
        memory.memoryView === memoryView &&
        memory.cacheKey.startsWith(`${memoryCacheScopeKey(scope)}:${memoryView}:`),
    );
    if (scoped.length === 0) return null;

    return scoped.map(
      ({
        cacheKey: _cacheKey,
        ownerId: _ownerId,
        backendScope: _backendScope,
        cachedAt: _cachedAt,
        memoryView: _memoryView,
        ...memory
      }) => memory,
    );
  } catch (error) {
    console.error('[IndexedDB] Failed to load cached memories:', error);
    return null;
  }
}

export async function isCacheFresh(scope: MemoryCacheScope): Promise<boolean> {
  try {
    const db = await getDB();
    const lastSync = await db.get('metadata', metadataKey(scope));
    return Boolean(lastSync && Date.now() - lastSync <= CACHE_TTL);
  } catch {
    return false;
  }
}

/** Invalidate only the supplied owner/backend scope. */
export async function invalidateCache(scope: MemoryCacheScope): Promise<void> {
  try {
    const db = await getDB();
    const tx = db.transaction(['memories', 'metadata'], 'readwrite');
    const memoryStore = tx.objectStore('memories');
    const existing = await memoryStore.getAll();
    for (const memory of existing) {
      if (belongsToScope(memory, scope)) await memoryStore.delete(memory.cacheKey);
    }
    await tx.objectStore('metadata').delete(metadataKey(scope));
    await tx.done;
  } catch (error) {
    console.error('[IndexedDB] Failed to invalidate cache:', error);
  }
}

export async function getCacheStats(
  scope: MemoryCacheScope,
): Promise<{ count: number; lastSync: number | null; isFresh: boolean }> {
  try {
    const db = await getDB();
    const [cached, lastSync] = await Promise.all([
      db.getAll('memories'),
      db.get('metadata', metadataKey(scope)),
    ]);
    const scoped = cached.filter((memory) => belongsToScope(memory, scope));
    return {
      count: scoped.length,
      lastSync: lastSync || null,
      isFresh: Boolean(lastSync && Date.now() - lastSync <= CACHE_TTL),
    };
  } catch {
    return { count: 0, lastSync: null, isFresh: false };
  }
}
