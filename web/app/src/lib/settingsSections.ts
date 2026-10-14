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
] as const;

export type SettingsSectionId = (typeof SETTINGS_SECTIONS)[number]['id'];

/**
 * Developer tools (agent connection, API and MCP keys, webhooks, data export)
 * are their own destination now, not a settings section.
 */
export const DEVELOPERS_PATH = '/developers';

/**
 * Where a retired `/settings?section=developer` link should go, keeping its
 * `#api-keys` / `#mcp` / `#webhooks` anchor; null for every other section.
 */
export function developerRedirectTarget(
  sectionParam: string | null,
  hash: string,
): string | null {
  if (sectionParam !== 'developer') return null;
  return `${DEVELOPERS_PATH}${hash.startsWith('#') ? hash : ''}`;
}

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
