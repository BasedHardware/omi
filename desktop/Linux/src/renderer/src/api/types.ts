// Server models, field-for-field with APIClient.swift's Codable types (snake_case JSON).

export interface ActionItem {
  description: string
  completed?: boolean
}

export interface StructuredSummary {
  title?: string
  overview?: string
  emoji?: string
  category?: string
  action_items?: ActionItem[]
}

export interface ServerTranscriptSegment {
  id?: string
  text: string
  speaker?: string
  speaker_id?: number
  is_user?: boolean
  person_id?: string | null
  start?: number
  end?: number
}

export interface ServerConversation {
  id: string
  created_at: string
  started_at?: string
  finished_at?: string
  structured?: StructuredSummary
  transcript_segments?: ServerTranscriptSegment[]
  source?: string
  language?: string
  status?: string
  discarded?: boolean
  starred?: boolean
  folder_id?: string | null
}

export interface ServerMemory {
  id: string
  content: string
  category?: string
  created_at?: string
  updated_at?: string
  conversation_id?: string
  visibility?: string
  manually_added?: boolean
  source?: string
  is_read?: boolean
  is_dismissed?: boolean
  tags?: string[]
  headline?: string
  reasoning?: string
}

export interface TaskActionItem {
  id: string
  description: string
  completed: boolean
  deleted?: boolean
  due_at?: string | null
  priority?: string | null
  category?: string | null
  source?: string | null
  created_at?: string
  updated_at?: string
  conversation_id?: string
  sort_order?: number
  indent_level?: number
}

export interface Goal {
  id: string
  title: string
  description?: string
  goal_type?: 'boolean' | 'scale' | 'numeric'
  target_value?: number
  current_value?: number
  min_value?: number
  max_value?: number
  unit?: string
  is_active?: boolean
  completed_at?: string | null
}

export interface ScoreData {
  score: number
  completedTasks?: number
  totalTasks?: number
}

export interface ScoreResponse {
  daily?: ScoreData
  weekly?: ScoreData
  overall?: ScoreData
  defaultTab?: string
  date?: string
}

export interface StagedTask {
  id: string
  description: string
  due_at?: string | null
  priority?: string | null
  category?: string | null
  source?: string | null
  relevance_score?: number
}

export interface Folder {
  id: string
  name: string
  description?: string
  color?: string
  order?: number
}

export interface KnowledgeGraphNode {
  id: string
  label?: string
  node_type?: string
  aliases?: string[]
  memory_ids?: string[]
}

export interface KnowledgeGraphEdge {
  id: string
  source_id: string
  target_id: string
  label?: string
}

export interface Person {
  id: string
  name: string
}

export interface ChatSession {
  id: string
  title?: string
  app_id?: string | null
  created_at?: string
  starred?: boolean
}

export interface ServerChatMessage {
  id: string
  text: string
  created_at: string
  sender: 'ai' | 'human' | string
  type?: string
  session_id?: string
}

export interface UserProfile {
  name?: string
  motivation?: string
  use_case?: string
  job?: string
  company?: string
}

// AI Persona / clone, field-for-field with the Persona Codable in APIClient.swift.
export interface Persona {
  id: string
  uid: string
  name: string
  username?: string | null
  description: string
  image: string
  category: string
  capabilities: string[]
  persona_prompt?: string | null
  approved?: boolean
  status: string
  private?: boolean
  author?: string
  email?: string | null
  created_at: string
  updated_at: string
  public_memories_count?: number | null
}

// Response from POST v1/personas/generate-prompt.
export interface GeneratePromptResponse {
  persona_prompt: string
  description: string
  memories_used: number
}

// Response from GET v1/personas/check-username.
export interface UsernameAvailableResponse {
  available: boolean
  username: string
}
