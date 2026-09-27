export interface Person {
  id: string;
  name: string;
  created_at: Date;
  updated_at: Date;
  speech_samples: string[];
}

export interface Memory {
  id: string;
  created_at: Date;
  started_at?: Date | string | null;
  finished_at?: Date | string | null;
  source: string;
  language: string;
  structured: Structured;
  transcript_segments: TranscriptSegment[];
  geolocation: null;
  photos: string[];
  apps_results: AppsResult[];
  external_data: ExternalData | null;
  postprocessing: Postprocessing;
  discarded: boolean;
  deleted: boolean;
  people?: Person[];
}

export interface ExternalData {
  request_id: string;
  source: string;
  text: string;
  timestamp_range: TimestampRange;
}

export interface TimestampRange {
  start: number;
  end: number;
}

export interface AppsResult {
  app_id: string;
  content: string;
}

export interface Postprocessing {
  status: string;
  model: string;
}

export interface Structured {
  title: string;
  overview: string;
  emoji: string;
  category: string;
  action_items: ActionItems[];
  events: Events[];
  sections?: StructuredSection[] | null;
  participants?: Participant[] | null;
  meeting_type?: MeetingType | null;
  insights?: StructuredInsight[] | null;
}

export type MeetingType =
  | 'interview'
  | 'intro'
  | 'sales'
  | 'customer'
  | 'one_on_one'
  | 'team_sync'
  | 'planning'
  | 'demo'
  | 'social'
  | 'other';

export interface StructuredSection {
  heading?: string | null;
  body_markdown?: string | null;
  kind?: 'main' | 'side_notes' | null;
  source_segment_ids?: string[] | null;
}

export interface Participant {
  name?: string | null;
  email?: string | null;
  organization?: string | null;
  role?: string | null;
  is_ai_agent?: boolean | null;
  source?: 'roster' | 'transcript' | null;
}

export type InsightKind = 'prior_meeting' | 'goal' | 'memory' | 'person';

export interface StructuredInsight {
  text?: string | null;
  kind?: InsightKind | null;
}

export interface ActionItems {
  completed: boolean;
  description: string;
  owner_name?: string | null;
  context?: string | null;
  due_at?: string | Date | null;
}

export interface Events {
  created: boolean;
  description: string;
  duration: number;
  start: Date;
  title: string;
}

export interface TranscriptSegment {
  text: string;
  speaker: string;
  speaker_id: number;
  is_user: boolean;
  person_id: string | null;
  start: number;
  end: number;
}
