// User Settings Types

export interface UserProfile {
  uid: string;
  email: string;
  name: string;
  created_at?: string;
}

export interface DailySummarySettings {
  enabled: boolean;
  hour: number; // 0-23
}

export interface TranscriptionPreferences {
  language: string;
  vocabulary: string[];
  single_language_mode: boolean;
}

export interface WebhookSettings {
  url: string;
  enabled: boolean;
}

export interface DeveloperWebhooks {
  memory_created?: WebhookSettings;
  transcript_received?: WebhookSettings;
  audio_bytes?: WebhookSettings;
  day_summary?: WebhookSettings;
}

export interface RecordingPermission {
  enabled: boolean;
}

export interface PrivateCloudSync {
  enabled: boolean;
}

export interface UserUsage {
  conversations_count: number;
  total_duration_seconds: number;
  period: string;
}

export interface UserSubscription {
  plan: string;
  status: string;
  is_unlimited: boolean;
}

export interface Person {
  id: string;
  name: string;
  created_at: string;
  speech_samples_count: number;
}

export interface Language {
  code: string;
  name: string;
}

// Available languages for transcription
export const SUPPORTED_LANGUAGES: Language[] = [
  { code: 'en', name: 'English' },
  { code: 'es', name: 'Spanish' },
  { code: 'fr', name: 'French' },
  { code: 'de', name: 'German' },
  { code: 'it', name: 'Italian' },
  { code: 'pt', name: 'Portuguese' },
  { code: 'nl', name: 'Dutch' },
  { code: 'pl', name: 'Polish' },
  { code: 'ru', name: 'Russian' },
  { code: 'ja', name: 'Japanese' },
  { code: 'ko', name: 'Korean' },
  { code: 'zh', name: 'Chinese' },
  { code: 'ar', name: 'Arabic' },
  { code: 'hi', name: 'Hindi' },
  { code: 'tr', name: 'Turkish' },
  { code: 'vi', name: 'Vietnamese' },
  { code: 'th', name: 'Thai' },
  { code: 'id', name: 'Indonesian' },
  { code: 'uk', name: 'Ukrainian' },
  { code: 'cs', name: 'Czech' },
  { code: 'ro', name: 'Romanian' },
  { code: 'el', name: 'Greek' },
  { code: 'hu', name: 'Hungarian' },
  { code: 'sv', name: 'Swedish' },
  { code: 'da', name: 'Danish' },
  { code: 'fi', name: 'Finnish' },
  { code: 'no', name: 'Norwegian' },
  { code: 'he', name: 'Hebrew' },
];
