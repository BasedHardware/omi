const API_BASE = '/api';

export interface Memory {
  id: string;
  content: string;
  category: string;
  tags: string[];
  created_at: string;
  manually_added: boolean;
}

export interface Task {
  id: string;
  title: string;
  description: string | null;
  priority: 'low' | 'medium' | 'high' | 'urgent';
  status: 'pending' | 'in_progress' | 'completed' | 'cancelled';
  due_at: string | null;
  created_at: string;
  completed_at: string | null;
  tags: string[];
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatResponse {
  message: string;
  intent: string;
  actions_taken: string[];
  data: Record<string, unknown>;
}

export const api = {
  async chat(message: string, history: ChatMessage[] = []): Promise<ChatResponse> {
    const res = await fetch(`${API_BASE}/chat/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, conversation_history: history }),
    });
    if (!res.ok) throw new Error('Chat request failed');
    return res.json();
  },

  async getMemories(limit = 20, category?: string): Promise<Memory[]> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (category) params.append('category', category);
    const res = await fetch(`${API_BASE}/memories/?${params}`);
    if (!res.ok) throw new Error('Failed to fetch memories');
    return res.json();
  },

  async createMemory(content: string, category = 'manual', tags: string[] = []): Promise<Memory> {
    const res = await fetch(`${API_BASE}/memories/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, category, tags }),
    });
    if (!res.ok) throw new Error('Failed to create memory');
    return res.json();
  },

  async deleteMemory(id: string): Promise<void> {
    const res = await fetch(`${API_BASE}/memories/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete memory');
  },

  async searchMemories(query: string, limit = 10): Promise<string[]> {
    const res = await fetch(`${API_BASE}/memories/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, limit }),
    });
    if (!res.ok) throw new Error('Failed to search memories');
    const data = await res.json();
    return data.memories;
  },

  async getTasks(status = 'pending', limit = 20): Promise<Task[]> {
    const params = new URLSearchParams({ status, limit: String(limit) });
    const res = await fetch(`${API_BASE}/tasks/?${params}`);
    if (!res.ok) throw new Error('Failed to fetch tasks');
    return res.json();
  },

  async getTasksDueSoon(hours = 24): Promise<Task[]> {
    const res = await fetch(`${API_BASE}/tasks/due-soon?hours=${hours}`);
    if (!res.ok) throw new Error('Failed to fetch due soon tasks');
    return res.json();
  },

  async getOverdueTasks(): Promise<Task[]> {
    const res = await fetch(`${API_BASE}/tasks/overdue`);
    if (!res.ok) throw new Error('Failed to fetch overdue tasks');
    return res.json();
  },

  async createTask(title: string, description?: string, priority = 'medium', dueAt?: string, tags: string[] = []): Promise<Task> {
    const res = await fetch(`${API_BASE}/tasks/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, description, priority, due_at: dueAt, tags }),
    });
    if (!res.ok) throw new Error('Failed to create task');
    return res.json();
  },

  async completeTask(id: string): Promise<Task> {
    const res = await fetch(`${API_BASE}/tasks/${id}/complete`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to complete task');
    return res.json();
  },

  async deleteTask(id: string): Promise<void> {
    const res = await fetch(`${API_BASE}/tasks/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete task');
  },
};
