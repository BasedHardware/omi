/**
 * The settings sections, in nav order.
 *
 * Single source of truth for both the settings page and the sidebar menu.
 * The Privacy section shipped fully implemented but with no nav entry pointing
 * at it, so it was only reachable by typing `?section=privacy` by hand. Keeping
 * the list here and typing the sidebar's icon map as a total
 * `Record<SettingsSectionId, ...>` makes a section without a nav entry a
 * compile error rather than a silently unreachable page.
 */
export const SETTINGS_SECTIONS = [
  {
    id: 'account',
    label: 'Account',
    title: 'Account',
    description: 'Profile, language, notifications, plan, and usage',
  },
  {
    id: 'privacy',
    label: 'Privacy',
    title: 'Privacy',
    description: 'Data permissions and training settings',
  },
  {
    id: 'developer',
    label: 'Developer',
    title: 'Developer',
    description: 'API keys, webhooks, and data export',
  },
] as const;

export type SettingsSectionId = (typeof SETTINGS_SECTIONS)[number]['id'];

export const CLAUDE_CONNECTOR_OAUTH = {
  clientId: 'omi-claude-prod',
  clientSecret: '',
} as const;

export const SIGNED_OUT_DESTINATION = '/login';

export const SECTION_INFO = Object.fromEntries(
  SETTINGS_SECTIONS.map(({ id, title, description }) => [id, { title, description }]),
) as Record<SettingsSectionId, { title: string; description: string }>;

export function isSettingsSectionId(value: string): value is SettingsSectionId {
  return SETTINGS_SECTIONS.some((section) => section.id === value);
}

export type WebhookApiType =
  | 'memory_created'
  | 'realtime_transcript'
  | 'audio_bytes'
  | 'day_summary';

/** UI uses transcript_received; the API names that hook realtime_transcript. */
export function toWebhookApiType(uiType: string): WebhookApiType {
  if (uiType === 'transcript_received') return 'realtime_transcript';
  return uiType as WebhookApiType;
}

export const ACCOUNT_QUICK_NAV = [
  { id: 'account-info', label: 'Account' },
  { id: 'language', label: 'Language' },
  { id: 'vocabulary', label: 'Vocabulary' },
  { id: 'notifications', label: 'Notifications' },
  { id: 'plan-usage', label: 'Plan & Usage' },
  { id: 'fair-use', label: 'Fair Use' },
  { id: 'actions', label: 'Actions' },
  { id: 'support', label: 'Support' },
] as const;

export const DEVELOPER_QUICK_NAV = [
  { id: 'api-keys', label: 'API Keys' },
  { id: 'mcp', label: 'MCP' },
  { id: 'webhooks', label: 'Webhooks' },
  { id: 'data-management', label: 'Data' },
  { id: 'experimental', label: 'Experimental' },
] as const;
