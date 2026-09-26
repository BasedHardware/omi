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
export const CATALOG_PLAN_IDS = [
  'basic',
  'plus',
  'unlimited',
  'unlimited_v2',
  'operator',
  'architect',
] as const;

export type CatalogPlanId = (typeof CATALOG_PLAN_IDS)[number];

// `pro` is the retained wire alias for the Architect catalog identity. Keep
// the raw value on decoded plans so a round trip never silently rewrites a
// persisted or echoed wire value.
const WIRE_PLAN_ALIASES: Readonly<Record<string, CatalogPlanId>> = {
  pro: 'architect',
};

export interface KnownPlanIdentity {
  kind: 'known';
  id: CatalogPlanId;
  raw: string;
}

export interface UnknownPlanIdentity {
  kind: 'unknown';
  raw: string | null;
}

export type PlanIdentity = KnownPlanIdentity | UnknownPlanIdentity;

const PAID_CATALOG_PLAN_IDS: ReadonlySet<CatalogPlanId> = new Set([
  'plus',
  'unlimited',
  'unlimited_v2',
  'operator',
  'architect',
]);

/** Decode a plan without throwing or replacing an unrecognized value. */
export function decodePlan(value: unknown): PlanIdentity {
  if (typeof value !== 'string' || value.length === 0) {
    return { kind: 'unknown', raw: null };
  }

  if ((CATALOG_PLAN_IDS as readonly string[]).includes(value)) {
    return { kind: 'known', id: value as CatalogPlanId, raw: value };
  }

  const aliasedPlan = Object.prototype.hasOwnProperty.call(WIRE_PLAN_ALIASES, value)
    ? WIRE_PLAN_ALIASES[value]
    : undefined;
  if (aliasedPlan) {
    return { kind: 'known', id: aliasedPlan, raw: value };
  }

  return { kind: 'unknown', raw: value };
}

/** Re-encode a decoded plan, preserving aliases and future wire values. */
export function encodePlan(plan: PlanIdentity): string | null {
  return plan.raw;
}

/** Only catalog identities with declared paid status can grant paid UI. */
export function planGrantsPaidCapability(plan: PlanIdentity): boolean {
  return plan.kind === 'known' && PAID_CATALOG_PLAN_IDS.has(plan.id);
}

export function planDisplayName(plan: PlanIdentity): string {
  if (plan.kind === 'unknown') return 'Plan unavailable';

  switch (plan.id) {
    case 'basic':
      return 'Free';
    case 'unlimited':
      return 'Neo';
    case 'unlimited_v2':
      return 'Unlimited';
    default:
      return plan.id.charAt(0).toUpperCase() + plan.id.slice(1);
  }
}

export interface Subscription {
  plan?: string | null;
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

// Usage history data point
export interface UsageHistoryPoint {
  date: string;
  transcription_seconds: number;
  words_transcribed: number;
  insights_gained: number;
  memories_created: number;
}

// Simplified types for component use
export interface UserUsage {
  transcription_seconds: number;
  words_transcribed: number;
  insights_gained: number;
  memories_created: number;
  history?: UsageHistoryPoint[];
}

// All usage data for all periods
export interface AllUsageData {
  today: UserUsage | null;
  monthly: UserUsage | null;
  yearly: UserUsage | null;
  all_time: UserUsage | null;
}

export interface UserSubscription {
  // Keep the raw wire value for callers and round trips. `plan_identity` is
  // the lossless, capability-safe interpretation of this value.
  plan: string;
  plan_identity?: PlanIdentity;
  status: string;
  is_unlimited: boolean;
  current_period_end?: number;
  stripe_subscription_id?: string;
  cancel_at_period_end?: boolean;
  current_price_id?: string;
  features?: string[];
}

// Pricing option for a plan (matches backend PricingOption)
export interface PricingOption {
  id: string;
  plan_id?: string;
  title: string;
  description?: string;
  subtitle?: string;
  eyebrow?: string;
  price_string: string;
  interval?: string;
  unit_amount?: number;
  is_active?: boolean;
}

// Response from available-plans endpoint (matches backend AvailablePlansResponse)
export interface AvailablePlansResponse {
  plans: PricingOption[]; // Backend returns flat list of PricingOption, not nested SubscriptionPlan
}

// Response from checkout-session endpoint
export interface CheckoutSessionResponse {
  url?: string;
  session_id?: string;
  status?: string;
  message?: string;
  next_billing_date?: string;
}

// Response from customer-portal endpoint
export interface CustomerPortalResponse {
  url: string;
}

// Response from cancel subscription
export interface CancelSubscriptionResponse {
  status: string;
  message: string;
  cancel_at_period_end?: boolean;
  current_period_end?: number;
}

// Response from upgrade subscription
export interface UpgradeSubscriptionResponse {
  status: string;
  message?: string;
  days_remaining?: number;
  scheduled_start?: number;
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
  key_prefix: string; // For existing keys, only prefix is returned
  key?: string; // Full key only returned when creating
  name: string;
  created_at: string;
  last_used_at?: string;
  scopes?: string[];
}

// Available scopes for Developer API keys
export const API_KEY_SCOPES = [
  { id: 'conversations:read', label: 'Conversations', type: 'read' },
  { id: 'conversations:write', label: 'Conversations', type: 'write' },
  { id: 'memories:read', label: 'Memories', type: 'read' },
  { id: 'memories:write', label: 'Memories', type: 'write' },
  { id: 'action_items:read', label: 'Action Items', type: 'read' },
  { id: 'action_items:write', label: 'Action Items', type: 'write' },
] as const;

export type ApiKeyScope = (typeof API_KEY_SCOPES)[number]['id'];

// MCP API Key types
export interface McpApiKey {
  id: string;
  key_prefix: string;
  key?: string; // Full key only returned when creating
  name: string;
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
  // Regional variants, matching the mobile app and desktop lists, so an account
  // set to Brazilian Portuguese elsewhere still renders here (#7461).
  { code: 'pt-BR', name: 'Portuguese (Brazil)' },
  { code: 'pt-PT', name: 'Portuguese (Portugal)' },
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
