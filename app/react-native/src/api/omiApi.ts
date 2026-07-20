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

export interface Paginated<T> {
  results: T[];
  count: number;
  limit: number;
  offset: number;
}

/** Lightweight helpers matching the desktop/linux usage patterns. */
export async function getMemories(limit = 200, offset = 0) {
  return omiApi.get<Paginated<Memory>>('/v3/memories', { params: { limit, offset } });
}

export async function createMemory(content: string, tags: string[] = []) {
  return omiApi.post<Memory>('/v3/memories', { content, tags });
}

export async function listConversations(limit = 50, offset = 0) {
  return omiApi.get<Paginated<Conversation>>('/v1/conversations', { params: { limit, offset } });
}

export async function getConversation(id: string) {
  return omiApi.get<Conversation>(`/v1/conversations/${id}`);
}

export async function getActionItems(limit = 50, offset = 0) {
  return omiApi.get<Paginated<ActionItem>>('/v1/action-items', { params: { limit, offset } });
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
