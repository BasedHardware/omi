export const desktopNavItems = [
  'Home',
  'Library',
  'Tasks',
  'Rewind',
  'Apps',
] as const;

export type DesktopNavItem = (typeof desktopNavItems)[number];

export const desktopSettingsPanes = [
  'General',
  'Account & Plan',
  'Transcription',
  'Rewind',
  'Floating Bar',
  'Alerts & Privacy',
  'Permissions',
  'Shortcuts',
  'AI & Automation',
  'About',
] as const;

export type DesktopSettingsPane = (typeof desktopSettingsPanes)[number];

export const desktopSearchPlaceholder = "Search what you've seen and heard…";

export const desktopTrafficLightLeading = 16;
export const desktopTrafficLightRowWidth = 78;
export const desktopNavBarHeight = 52;
export const desktopWindowInset = 8;
export const desktopNavTopInset = 0;
export const desktopGlassCornerRadius = 22;
export const desktopSystemFontFamily = 'System';

export const desktopMotion = {
  navMs: 80,
  pressMs: 90,
  stepMs: 240,
  settleMs: 280,
  overlayMs: 300,
  checkboxMs: 180,
  searchExpandMs: 160,
  listInsertMs: 0,
  glassMs: 0,
} as const;

export const desktopStageFade = {
  chatRiseY: 54,
  dropScale: 0.98,
  hubOffsetY: 14,
} as const;

export type DesktopSession = 'probing' | 'signed-out' | 'ready';

export function visibleChatError(
  session: DesktopSession,
  chatError: string | null,
): string | null {
  if (session !== 'ready') {
    return null;
  }
  return chatError;
}

export function isShippingDesktopNav(label: string): boolean {
  return (desktopNavItems as readonly string[]).includes(label);
}
