import envConfig from '@/src/constants/envConfig';

export const MEMORY_PLATFORM_LIMITS = {
  maxQueryLength: 500,
  minLimit: 1,
  maxLimit: 500,
  defaultLimit: 100,
  minOffset: 0,
  maxOffset: 100000,
} as const;

export interface MemoryPlatformCapability {
  authority?: string;
  canonical_collection?: string;
  surfaces?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface PlatformMemoryItem {
  id?: string;
  content?: string;
  category?: string;
  created_at?: string;
}

export interface PlatformSearchResponse {
  memories?: PlatformMemoryItem[];
  [key: string]: unknown;
}

function apiBase(): string {
  return envConfig.API_URL ?? '';
}

async function authorizedJson<T>(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${apiBase()}${path}`, {
    ...init,
    headers: {
      ...(init.headers ?? {}),
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    cache: 'no-store',
  });
  if (!response.ok) {
    throw new Error(`${init.method ?? 'GET'} ${path} failed: ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function getMemoryPlatformCapability(token: string) {
  return authorizedJson<MemoryPlatformCapability>('/v1/memory/platform', token);
}

export function searchMemoryPlatform(
  token: string,
  params: { query?: string; limit?: number; offset?: number } = {},
) {
  const query = (params.query ?? '').slice(0, MEMORY_PLATFORM_LIMITS.maxQueryLength);
  const limit = Math.min(
    Math.max(
      params.limit ?? MEMORY_PLATFORM_LIMITS.defaultLimit,
      MEMORY_PLATFORM_LIMITS.minLimit,
    ),
    MEMORY_PLATFORM_LIMITS.maxLimit,
  );
  const offset = Math.min(
    Math.max(params.offset ?? 0, MEMORY_PLATFORM_LIMITS.minOffset),
    MEMORY_PLATFORM_LIMITS.maxOffset,
  );
  const search = new URLSearchParams({
    query,
    limit: String(limit),
    offset: String(offset),
  });
  return authorizedJson<PlatformSearchResponse>(
    `/v1/memory/platform/search?${search.toString()}`,
    token,
  );
}

export function ingestMemoryPlatform(
  token: string,
  payload: { content: string; category?: string },
) {
  return authorizedJson<{ memory_id: string }>('/v1/memory/platform/ingest', token, {
    method: 'POST',
    body: JSON.stringify({
      content: payload.content,
      category: payload.category ?? 'manual',
    }),
  });
}
