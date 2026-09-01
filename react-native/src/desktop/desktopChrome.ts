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
  'Alerts & Privacy',
  'AI & Automation',
  'About',
] as const;

export type DesktopSettingsPane = (typeof desktopSettingsPanes)[number];

export const desktopSearchPlaceholder = "Search what you've seen and heard…";

// Even 12pt inset from every window edge. Traffic lights sit on the nav row
// (not the omnibar row) and share that row's vertical center with Home.
// AppDelegate.mm mirrors the nav-row numbers.
export const desktopWindowInset = 12;
export const desktopNavBarHeight = 52;
export const desktopOmnibarHeight = 40;
export const desktopTrafficLightButton = 14;
export const desktopTrafficLightSpacing = 8;
export const desktopTrafficLightTrailing = 16;
export const desktopTrafficLightClusterWidth =
  3 * desktopTrafficLightButton + 2 * desktopTrafficLightSpacing;
export const desktopTrafficLightRowWidth =
  desktopTrafficLightClusterWidth + desktopTrafficLightTrailing;
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

// Chat transport errors never take over the currents/tasks stage. They are
// only surfaced under the omnibar that owns chat, and only once the session
// is ready; a signed-out or probing first paint stays quiet.
export function visibleChatError(
  session: DesktopSession,
  chatError: string | null,
): string | null {
  if (session !== 'ready' || chatError === null || chatError === '') {
    return null;
  }
  return chatError;
}

export function isShippingDesktopNav(label: string): boolean {
  return (desktopNavItems as readonly string[]).includes(label);
}
