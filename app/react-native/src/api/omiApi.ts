import axios, { AxiosInstance } from 'axios';
import { ENV } from '@/config/env';

/**
 * Omi REST client. Reuses the exact endpoints the desktop/linux port uses:
 *   /v3/memories, /v1/conversations, /v1/goals, /v1/action-items, /v1/knowledge-graph
 *
 * The Firebase ID token is attached as a Bearer token on every request; when a
 * dev API key is set (DevApiKeyProvider equivalent) it is used instead.
 */
let authToken: string | null = null;
let devApiKey: string | null = null;

export function setAuthToken(token: string | null) {
  authToken = token;
}
export function setDevApiKey(key: string | null) {
  devApiKey = key;
}

export const omiApi: AxiosInstance = axios.create({
  baseURL: ENV.apiBaseUrl,
  timeout: 30000,
});

omiApi.interceptors.request.use((config) => {
  if (devApiKey) {
    config.headers.set('Authorization', `Bearer ${devApiKey}`);
  } else if (authToken) {
    config.headers.set('Authorization', `Bearer ${authToken}`);
  }
  return config;
});

/**
 * Normalize a list response into a plain array.
 *
 * The Omi backend returns *bare arrays* for `/v3/memories` and
 * `/v1/conversations`, and an `{ action_items: [...] }` envelope for
 * `/v1/action-items`. Some endpoints have historically returned a
 * `{ results: [...] }` shape. Accept every supported envelope so callers never
 * crash on a successful response (the prior `res.data.results` read broke the
 * Home/Goals flows on the array payloads).
 */
export function asList<T>(data: unknown, key?: string): T[] {
  if (Array.isArray(data)) return data as T[];
  if (data && typeof data === 'object') {
    const obj = data as Record<string, unknown>;
    const candidates = key ? [obj[key], obj.results] : [obj.results];
    for (const c of candidates) {
      if (Array.isArray(c)) return c as T[];
    }
  }
  return [];
}

/** Lightweight helpers matching the desktop/linux usage patterns. */
export async function getMemories(limit = 200, offset = 0): Promise<Memory[]> {
  const res = await omiApi.get<Memory[]>('/v3/memories', { params: { limit, offset } });
  return asList<Memory>(res.data);
}

export async function createMemory(content: string, tags: string[] = []): Promise<Memory> {
  const res = await omiApi.post<Memory>('/v3/memories', { content, tags });
  return res.data;
}

export async function listConversations(limit = 50, offset = 0): Promise<Conversation[]> {
  const res = await omiApi.get<Conversation[]>('/v1/conversations', { params: { limit, offset } });
  return asList<Conversation>(res.data);
}

export async function getConversation(id: string): Promise<Conversation> {
  const res = await omiApi.get<Conversation>(`/v1/conversations/${id}`);
  return res.data;
}

export async function getActionItems(limit = 50, offset = 0): Promise<ActionItem[]> {
  const res = await omiApi.get<{ action_items?: ActionItem[] }>('/v1/action-items', {
    params: { limit, offset },
  });
  return asList<ActionItem>(res.data, 'action_items');
}

/** POST /v1/action-items — create a task the account can see across surfaces. */
export async function createActionItem(
  description: string,
  opts: { due_at?: string | null } = {},
): Promise<ActionItem> {
  const res = await omiApi.post<ActionItem>('/v1/action-items', {
    description,
    ...(opts.due_at ? { due_at: opts.due_at } : {}),
  });
  return res.data;
}

export interface ActionItem {
  id: string;
  description: string;
  completed?: boolean;
  due_date?: string | null;
  created_at?: string;
  priority?: string;
}

export interface Memory {
  id: string;
  content: string;
  created_at: string;
  tags: string[];
  category?: string;
  visibility?: string;
}

export interface Conversation {
  id: string;
  title?: string;
  created_at: string;
  started_at?: string;
  transcript?: TranscriptSegment[];
  transcript_segments?: TranscriptSegment[];
  geolocation?: { lat: number; lon: number } | null;
  photos?: string[];
  visibility?: string;
}

export interface TranscriptSegment {
  text: string;
  speaker_id?: string;
  speaker?: string | null;
  start: number;
  end: number;
  is_user?: boolean;
}
