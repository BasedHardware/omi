import { t } from '@/lib/i18n';
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
    get label() {
      return t('Account');
    },
    get title() {
      return t('Account');
    },
    get description() {
      return t('Profile, language, notifications, plan, and usage');
    },
  },
  {
    id: 'privacy',
    get label() {
      return t('Privacy');
    },
    get title() {
      return t('Privacy');
    },
    get description() {
      return t('Data permissions and training settings');
    },
  },
  {
    id: 'developer',
    get label() {
      return t('Developer');
    },
    get title() {
      return t('Developer');
    },
    get description() {
      return t('API keys, webhooks, and data export');
    },
  },
] as const;

export type SettingsSectionId = (typeof SETTINGS_SECTIONS)[number]['id'];

export const CLAUDE_CONNECTOR_OAUTH = {
  clientId: 'omi-claude-prod',
  clientSecret: '',
} as const;

export const SIGNED_OUT_DESTINATION = '/login';

// Getters, not copies: the labels are translated, and this module loads before the
// UI catalog does, so reading them here would freeze the English text.
export const SECTION_INFO = Object.fromEntries(
  SETTINGS_SECTIONS.map((section) => [
    section.id,
    {
      get title() {
        return section.title;
      },
      get description() {
        return section.description;
      },
    },
  ]),
) as Record<SettingsSectionId, { title: string; description: string }>;

export function isSettingsSectionId(value: string): value is SettingsSectionId {
  return SETTINGS_SECTIONS.some((section) => section.id === value);
}
