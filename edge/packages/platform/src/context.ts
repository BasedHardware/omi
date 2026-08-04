/**
 * Runtime-agnostic app dependencies. Cloudflare / Node / Bun inject implementations.
 */

import type { EdgeFeatures } from "./features.js";

/** Minimal KV — Cloudflare KV or Map-backed memory. */
export type KvStore = {
  get(key: string, type?: "text" | "json"): Promise<string | unknown | null>;
  put(key: string, value: string): Promise<void>;
};

export type AppDeps = {
  features: EdgeFeatures;
  /** Optional control-plane KV for tenant map */
  tenantKv?: KvStore;
  /** Optional vector search (provider-specific adapter later) */
  memorySearch?: MemorySearchPort;
};

export type MemorySearchHit = {
  id: string;
  score: number;
  content?: string;
  metadata?: Record<string, unknown>;
};

export type MemorySearchPort = {
  search(input: {
    uid: string;
    query: string;
    limit?: number;
  }): Promise<MemorySearchHit[]>;
};

export function memoryKv(map: Map<string, string> = new Map()): KvStore {
  return {
    async get(key, type = "text") {
      const v = map.get(key);
      if (v === undefined) return null;
      if (type === "json") {
        try {
          return JSON.parse(v) as unknown;
        } catch {
          return null;
        }
      }
      return v;
    },
    async put(key, value) {
      map.set(key, value);
    },
  };
}
