export interface Memory {
  id: string;
  created_at: Date;
  started_at: Date;
  finished_at: Date;
  source: string;
  language: string;
  structured: Structured;
  transcript_segments: TranscriptSegment[];
  geolocation: null;
  photos: string[];
  plugins_results: PluginsResult[];
  external_data: ExternalData | null;
  postprocessing: Postprocessing;
  discarded: boolean;
  deleted: boolean;
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

export interface PluginsResult {
  plugin_id: string;
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
}

export interface ActionItems {
  completed: boolean;
  description: string;
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
  person_id: null;
  start: number;
  end: number;
}
