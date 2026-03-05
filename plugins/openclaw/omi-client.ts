import { TTLCache } from "./cache.js";

export type OmiMemory = {
  id: string;
  content: string;
  category?: string;
  visibility?: "private" | "public";
  created_at: string;
  updated_at: string;
};

export type OmiConversation = {
  id: string;
  created_at: string;
  updated_at: string;
  started_at?: string;
  finished_at?: string;
  transcript?: Array<{
    speaker: string;
    text: string;
    timestamp?: string;
  }>;
  summary?: string;
  structured?: {
    title?: string;
    overview?: string;
    action_items?: string[];
  };
};

export type OmiActionItem = {
  id: string;
  description: string;
  completed: boolean;
  due_at?: string;
  created_at: string;
  updated_at: string;
};

export class OmiClient {
  private baseUrl: string;
  private apiKey: string;
  private cache: TTLCache<unknown>;

  constructor(apiKey: string, baseUrl = "https://api.omi.me", cacheTtlMs = 300000) {
    this.apiKey = apiKey;
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.cache = new TTLCache(cacheTtlMs);
  }

  private async request<T>(
    method: string,
    path: string,
    options?: {
      body?: unknown;
      params?: Record<string, string | number | boolean | undefined>;
      skipCache?: boolean;
    },
  ): Promise<T> {
    const url = new URL(`${this.baseUrl}${path}`);
    
    if (options?.params) {
      for (const [key, value] of Object.entries(options.params)) {
        if (value !== undefined && value !== null) {
          url.searchParams.append(key, String(value));
        }
      }
    }

    const cacheKey = `${method}:${url.toString()}`;
    
    if (method === "GET" && !options?.skipCache) {
      const cached = this.cache.get(cacheKey);
      if (cached !== undefined) {
        return cached as T;
      }
    }

    const headers: Record<string, string> = {
      "Authorization": `Bearer ${this.apiKey}`,
      "Content-Type": "application/json",
    };

    const init: RequestInit = {
      method,
      headers,
    };

    if (options?.body) {
      init.body = JSON.stringify(options.body);
    }

    const response = await fetch(url.toString(), init);

    if (!response.ok) {
      const errorText = await response.text().catch(() => "Unknown error");
      throw new Error(`Omi API error (${response.status}): ${errorText}`);
    }

    const data = await response.json();

    if (method === "GET" && !options?.skipCache) {
      this.cache.set(cacheKey, data);
    }

    return data as T;
  }

  async getMemories(params?: {
    limit?: number;
    offset?: number;
    categories?: string[];
  }): Promise<OmiMemory[]> {
    const queryParams: Record<string, string | number | undefined> = {
      limit: params?.limit,
      offset: params?.offset,
    };

    if (params?.categories && params.categories.length > 0) {
      queryParams.categories = params.categories.join(",");
    }

    return this.request<OmiMemory[]>("GET", "/v1/dev/user/memories", { params: queryParams });
  }

  async createMemory(data: {
    content: string;
    category?: string;
    visibility?: "private" | "public";
  }): Promise<OmiMemory> {
    return this.request<OmiMemory>("POST", "/v1/dev/user/memories", {
      body: data,
      skipCache: true,
    });
  }

  async createMemoriesBatch(memories: Array<{
    content: string;
    category?: string;
    visibility?: "private" | "public";
  }>): Promise<{ created: OmiMemory[] }> {
    return this.request<{ created: OmiMemory[] }>("POST", "/v1/dev/user/memories/batch", {
      body: { memories },
      skipCache: true,
    });
  }

  async updateMemory(
    id: string,
    data: {
      content?: string;
      category?: string;
      visibility?: "private" | "public";
    },
  ): Promise<OmiMemory> {
    return this.request<OmiMemory>("PATCH", `/v1/dev/user/memories/${id}`, {
      body: data,
      skipCache: true,
    });
  }

  async deleteMemory(id: string): Promise<void> {
    await this.request<void>("DELETE", `/v1/dev/user/memories/${id}`, {
      skipCache: true,
    });
  }

  async getConversations(params?: {
    limit?: number;
    offset?: number;
    start_date?: string;
    end_date?: string;
    include_transcript?: boolean;
  }): Promise<OmiConversation[]> {
    return this.request<OmiConversation[]>("GET", "/v1/dev/user/conversations", {
      params: params as Record<string, string | number | boolean | undefined>,
    });
  }

  async getConversation(
    id: string,
    includeTranscript = false,
  ): Promise<OmiConversation> {
    return this.request<OmiConversation>("GET", `/v1/dev/user/conversations/${id}`, {
      params: { include_transcript: includeTranscript },
    });
  }

  async getActionItems(params?: {
    limit?: number;
    offset?: number;
    completed?: boolean;
    start_date?: string;
    end_date?: string;
  }): Promise<OmiActionItem[]> {
    return this.request<OmiActionItem[]>("GET", "/v1/dev/user/action-items", {
      params: params as Record<string, string | number | boolean | undefined>,
    });
  }

  async createActionItem(data: {
    description: string;
    due_at?: string;
  }): Promise<OmiActionItem> {
    return this.request<OmiActionItem>("POST", "/v1/dev/user/action-items", {
      body: data,
      skipCache: true,
    });
  }

  async createActionItemsBatch(actionItems: Array<{
    description: string;
    due_at?: string;
  }>): Promise<{ created: OmiActionItem[] }> {
    return this.request<{ created: OmiActionItem[] }>("POST", "/v1/dev/user/action-items/batch", {
      body: { action_items: actionItems },
      skipCache: true,
    });
  }

  async updateActionItem(
    id: string,
    data: {
      description?: string;
      completed?: boolean;
      due_at?: string;
    },
  ): Promise<OmiActionItem> {
    return this.request<OmiActionItem>("PATCH", `/v1/dev/user/action-items/${id}`, {
      body: data,
      skipCache: true,
    });
  }

  async deleteActionItem(id: string): Promise<void> {
    await this.request<void>("DELETE", `/v1/dev/user/action-items/${id}`, {
      skipCache: true,
    });
  }

  clearCache(): void {
    this.cache.clear();
  }
}
