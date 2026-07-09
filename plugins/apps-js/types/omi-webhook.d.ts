export interface OmiActionItem {
  description: string;
  completed?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  due_at?: string | null;
  completed_at?: string | null;
  conversation_id?: string | null;
  [key: string]: unknown;
}

export interface OmiEvent {
  title: string;
  description?: string;
  start: string;
  duration?: number;
  created?: boolean;
  [key: string]: unknown;
}

export interface OmiStructured {
  title: string;
  overview: string;
  emoji?: string;
  category?: string;
  action_items?: OmiActionItem[];
  events?: OmiEvent[];
  [key: string]: unknown;
}

export interface OmiTranscriptSegment {
  id?: string | null;
  text: string;
  speaker?: string | null;
  speaker_id?: number | null;
  is_user: boolean;
  person_id?: string | null;
  start: number;
  end: number;
  [key: string]: unknown;
}

export interface OmiConversationPhoto {
  id?: string | null;
  base64?: string;
  description?: string | null;
  created_at?: string | null;
  discarded?: boolean;
  data_protection_level?: string | null;
  [key: string]: unknown;
}

export interface OmiAppResult {
  app_id?: string | null;
  content: string;
  [key: string]: unknown;
}

export interface OmiPluginResult {
  plugin_id?: string | null;
  content: string;
  [key: string]: unknown;
}

export interface OmiConversationWebhook {
  id?: string;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  discarded?: boolean;
  structured: OmiStructured;
  transcript_segments: OmiTranscriptSegment[];
  photos?: OmiConversationPhoto[];
  apps_results?: OmiAppResult[];
  plugins_results?: OmiPluginResult[];
  [key: string]: unknown;
}
