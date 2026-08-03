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
    id: 'profile',
    label: 'Profile',
    title: 'Profile',
    description: 'Account details, language, and notifications',
  },
  {
    id: 'privacy',
    label: 'Privacy',
    title: 'Privacy',
    description: 'Data permissions and training settings',
  },
  {
    id: 'integrations',
    label: 'Integrations',
    title: 'Integrations',
    description: 'Connected services and apps',
  },
  {
    id: 'developer',
    label: 'Developer',
    title: 'Developer',
    description: 'API keys, webhooks, and data export',
  },
  {
    id: 'account',
    label: 'Account',
    title: 'Account',
    description: 'Plan, usage, and account management',
  },
] as const;

export type SettingsSectionId = (typeof SETTINGS_SECTIONS)[number]['id'];

export const SECTION_INFO = Object.fromEntries(
  SETTINGS_SECTIONS.map(({ id, title, description }) => [id, { title, description }]),
) as Record<SettingsSectionId, { title: string; description: string }>;

export function isSettingsSectionId(value: string): value is SettingsSectionId {
  return SETTINGS_SECTIONS.some((section) => section.id === value);
}
