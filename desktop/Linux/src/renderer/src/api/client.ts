import type {
  ChatSession,
  Folder,
  GeneratePromptResponse,
  Goal,
  KnowledgeGraphEdge,
  KnowledgeGraphNode,
  Persona,
  Person,
  ScoreResponse,
  ServerChatMessage,
  ServerConversation,
  ServerMemory,
  StagedTask,
  TaskActionItem,
  UserProfile,
  UsernameAvailableResponse
} from './types'

// Thin typed wrappers over the main-process API proxy, one per endpoint the Mac
// app's APIClient.swift exposes (Python backend unless noted).

class ApiError extends Error {
  constructor(
    public status: number,
    public body: string
  ) {
    super(`API ${status}: ${body.slice(0, 300)}`)
  }
}

async function py<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await window.omi.api.request({
    method,
    url,
    base: 'python',
    body: body === undefined ? null : JSON.stringify(body)
  })
  if (res.status < 200 || res.status >= 300) throw new ApiError(res.status, res.body)
  return (res.body ? JSON.parse(res.body) : null) as T
}

export const api = {
  // Conversations (processing,completed matches the Mac app + backend default, so a
  // just-finished recording shows up while it's still being post-processed)
  listConversations: (limit = 50, offset = 0, statuses = 'processing,completed') =>
    py<ServerConversation[]>(
      'GET',
      `v1/conversations?limit=${limit}&offset=${offset}&statuses=${statuses}&include_discarded=false`
    ),
  getConversation: (id: string) => py<ServerConversation>('GET', `v1/conversations/${id}`),
  deleteConversation: (id: string) => py<void>('DELETE', `v1/conversations/${id}`),
  setConversationStarred: (id: string, starred: boolean) =>
    py<void>('PATCH', `v1/conversations/${id}/starred?starred=${starred}`),
  setConversationTitle: (id: string, title: string) =>
    py<void>('PATCH', `v1/conversations/${id}/title?title=${encodeURIComponent(title)}`),
  searchConversations: (query: string, page = 1, perPage = 20) =>
    py<{ items: ServerConversation[]; current_page: number; total_pages: number }>(
      'POST',
      'v1/conversations/search',
      { query, page, per_page: perPage, include_discarded: false }
    ),
  forceProcessConversation: () => py<{ conversation?: ServerConversation }>('POST', 'v1/conversations', {}),

  // Memories
  listMemories: (limit = 100, offset = 0) => py<ServerMemory[]>('GET', `v3/memories?limit=${limit}&offset=${offset}`),
  createMemory: (content: string) =>
    py<{ id: string }>('POST', 'v3/memories', { content, visibility: 'private', manually_added: true }),
  editMemory: (id: string, value: string) => py<{ status: string }>('PATCH', `v3/memories/${id}`, { value }),
  deleteMemory: (id: string) => py<void>('DELETE', `v3/memories/${id}`),
  // Visibility (matches APIClient.swift: per-memory + bulk, body { value })
  updateMemoryVisibility: (id: string, visibility: 'private' | 'public') =>
    py<{ status: string }>('PATCH', `v3/memories/${id}/visibility`, { value: visibility }),
  updateAllMemoriesVisibility: (visibility: 'private' | 'public') =>
    py<{ status: string }>('PATCH', 'v3/memories/visibility', { value: visibility }),
  deleteAllMemories: () => py<void>('DELETE', 'v3/memories'),

  // Tasks (action items)
  listActionItems: (completed: boolean, limit = 100, offset = 0) =>
    py<{ items: TaskActionItem[]; has_more: boolean } | TaskActionItem[]>(
      'GET',
      `v1/action-items?limit=${limit}&offset=${offset}&completed=${completed}`
    ),
  createActionItem: (description: string, dueAt?: string) =>
    py<TaskActionItem>('POST', 'v1/action-items', { description, due_at: dueAt ?? null, source: 'manual' }),
  updateActionItem: (id: string, patch: Record<string, unknown>) =>
    py<TaskActionItem>('PATCH', `v1/action-items/${id}`, patch),
  deleteActionItem: (id: string) => py<void>('DELETE', `v1/action-items/${id}`),

  // Goals
  listGoals: () => py<Goal[]>('GET', 'v1/goals/all'),
  createGoal: (g: {
    title: string
    goal_type: 'boolean' | 'scale' | 'numeric'
    target_value: number
    current_value?: number
    min_value?: number
    max_value?: number
    unit?: string
  }) => py<Goal>('POST', 'v1/goals', { current_value: 0, min_value: 0, max_value: 10, ...g }),
  updateGoal: (id: string, patch: Partial<Goal>) => py<Goal>('PATCH', `v1/goals/${id}`, patch),
  setGoalProgress: (id: string, currentValue: number) =>
    py<Goal>('PATCH', `v1/goals/${id}/progress?current_value=${currentValue}`),
  deleteGoal: (id: string) => py<{ success: boolean }>('DELETE', `v1/goals/${id}`),

  // Scores (dashboard daily/weekly/overall)
  getScores: (date?: string) => py<ScoreResponse>('GET', `v1/scores${date ? `?date=${date}` : ''}`),

  // Staged (AI-proposed) tasks
  listStagedTasks: (limit = 50) =>
    py<{ items: StagedTask[]; has_more: boolean } | StagedTask[]>('GET', `v1/staged-tasks?limit=${limit}&offset=0`),
  deleteStagedTask: (id: string) => py<void>('DELETE', `v1/staged-tasks/${id}`),
  promoteStagedTask: () =>
    py<{ promoted: boolean; reason?: string; promoted_task?: TaskActionItem }>('POST', 'v1/staged-tasks/promote', {}),
  batchUpdateTaskOrder: (items: { id: string; sort_order?: number; indent_level?: number }[]) =>
    py<{ status: string }>('PATCH', 'v1/action-items/batch', { items }),

  // Folders
  listFolders: () => py<Folder[]>('GET', 'v1/folders'),
  createFolder: (name: string, color?: string) => py<Folder>('POST', 'v1/folders', { name, color }),
  updateFolder: (id: string, patch: Partial<Folder>) => py<Folder>('PATCH', `v1/folders/${id}`, patch),
  deleteFolder: (id: string, moveToFolderId?: string) =>
    py<void>('DELETE', `v1/folders/${id}${moveToFolderId ? `?move_to_folder_id=${moveToFolderId}` : ''}`),
  moveConversationToFolder: (convId: string, folderId: string | null) =>
    py<void>('PATCH', `v1/conversations/${convId}/folder`, { folder_id: folderId }),
  mergeConversations: (ids: string[]) =>
    py<{ id?: string }>('POST', 'v1/conversations/merge', { conversation_ids: ids, reprocess: false }),
  setConversationVisibility: (id: string, visibility: 'private' | 'shared' | 'public') =>
    py<void>('PATCH', `v1/conversations/${id}/visibility?visibility=${visibility}`),

  // Chat sessions
  createChatSession: (title?: string) => py<ChatSession>('POST', 'v2/chat-sessions', { title }),
  patchChatSession: (id: string, patch: { title?: string; starred?: boolean }) =>
    py<ChatSession>('PATCH', `v2/chat-sessions/${id}`, patch),
  generateSessionTitle: (sessionId: string, messages: { text: string; sender: string }[]) =>
    py<{ title: string }>('POST', 'v2/chat/generate-title', { session_id: sessionId, messages }),
  rateMessage: (messageId: string, rating: 1 | -1 | null) =>
    py<{ status: string }>('PATCH', `v2/desktop/messages/${messageId}/rating`, { rating: rating ?? 0 }),

  // Knowledge graph
  getKnowledgeGraph: () =>
    py<{ nodes: KnowledgeGraphNode[]; edges: KnowledgeGraphEdge[] }>('GET', 'v1/knowledge-graph'),
  rebuildKnowledgeGraph: () =>
    py<{ status: string }>('POST', 'v1/knowledge-graph/rebuild?limit=500', {}),

  // People (speaker naming)
  listPeople: () => py<Person[]>('GET', 'v1/users/people').catch(() => [] as Person[]),
  createPerson: (name: string) => py<Person>('POST', 'v1/users/people', { name }),

  // Chat sessions + history (Python backend)
  listChatSessions: (limit = 30) => py<ChatSession[]>('GET', `v2/chat-sessions?limit=${limit}&offset=0`),
  deleteChatSession: (id: string) => py<void>('DELETE', `v2/chat-sessions/${id}`),
  listSessionMessages: (sessionId: string, limit = 100) =>
    py<ServerChatMessage[]>('GET', `v2/desktop/messages?session_id=${sessionId}&limit=${limit}&offset=0`),
  listMessages: (limit = 100) => py<ServerChatMessage[]>('GET', `v2/desktop/messages?limit=${limit}&offset=0`),

  // Profile
  getProfile: () => py<UserProfile>('GET', 'v1/users/profile'),
  updateProfile: (patch: Partial<UserProfile>) => py<UserProfile>('PATCH', 'v1/users/profile', patch),

  // MCP integration keys
  createMcpKey: (name: string) => py<{ id: string; name: string; key: string }>('POST', 'v1/mcp/keys', { name }),

  // Persona / AI clone (matches APIClient.swift Persona API, Python backend).
  // GET v1/personas returns null when the user has no persona yet.
  getPersona: () => py<Persona | null>('GET', 'v1/personas'),
  createPersona: (name: string, username?: string) =>
    py<Persona>('POST', 'v1/personas', { name, username: username ?? null }),
  // PATCH v1/personas updates the existing persona (name/description/prompt/image).
  updatePersona: (patch: { name?: string; description?: string; persona_prompt?: string; image?: string }) =>
    py<Persona>('PATCH', 'v1/personas', patch),
  deletePersona: () => py<void>('DELETE', 'v1/personas'),
  // Regenerates the persona prompt from the user's current public memories.
  regeneratePersonaPrompt: () => py<GeneratePromptResponse>('POST', 'v1/personas/generate-prompt', {}),
  checkPersonaUsername: (username: string) =>
    py<UsernameAvailableResponse>('GET', `v1/personas/check-username?username=${encodeURIComponent(username)}`)
}

export { ApiError }
