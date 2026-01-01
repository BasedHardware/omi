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

// Usage stats for a period
export interface UsageStats {
  transcription_seconds: number;
  words_transcribed: number;
  insights_gained: number;
  memories_created: number;
}

// Full usage response from API
export interface UserUsageResponse {
  today?: UsageStats;
  monthly?: UsageStats;
  yearly?: UsageStats;
  all_time?: UsageStats;
  history?: Array<{
    date: string;
    transcription_seconds: number;
    words_transcribed: number;
    insights_gained: number;
    memories_created: number;
  }>;
}

// Subscription details
export interface Subscription {
  plan: 'basic' | 'unlimited';
  status: 'active' | 'inactive';
  current_period_end?: number;
  stripe_subscription_id?: string;
  current_price_id?: string;
  features: string[];
  cancel_at_period_end: boolean;
}

// Full subscription response from API
export interface UserSubscriptionResponse {
  subscription: Subscription;
  transcription_seconds_used: number;
  transcription_seconds_limit: number;
  words_transcribed_used: number;
  words_transcribed_limit: number;
  insights_gained_used: number;
  insights_gained_limit: number;
  memories_created_used: number;
  memories_created_limit: number;
  available_plans: Array<{
    id: string;
    title: string;
    features: string[];
    prices: Array<{
      id: string;
      title: string;
      description?: string;
      price_string: string;
    }>;
  }>;
  show_subscription_ui: boolean;
}

// Simplified types for component use
export interface UserUsage {
  transcription_seconds: number;
  words_transcribed: number;
  insights_gained: number;
  memories_created: number;
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

export interface Integration {
  id: string;
  name: string;
  description: string;
  icon: string;
  connected: boolean;
  connect_url?: string;
  disconnect_url?: string;
  coming_soon?: boolean;
}

export interface DeveloperApiKey {
  id: string;
  key: string;
  name?: string;
  created_at: string;
  last_used_at?: string;
}

export interface CustomVocabulary {
  words: string[];
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
