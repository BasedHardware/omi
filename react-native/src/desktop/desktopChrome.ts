// v5.1: Chat is not a page (it lives in an overlay opened from the omnibar)
// and Conversations/Recall/Tasks are not pages either — they filter the
// Activity timeline. The chrome's second row IS the filter row; the first row
// is the omnibar. The v5 pages IA lives on as a selectable interface version
// (DesktopShellV5 + DesktopChromeV5).
export const desktopActivityFilters = [
  'all',
  'conversations',
  'recall',
  'tasks',
] as const;

export type ActivityFilterId = (typeof desktopActivityFilters)[number];

export const desktopTimelineGroupings = ['date', 'type', 'topic'] as const;

export type TimelineGrouping = (typeof desktopTimelineGroupings)[number];

export function desktopFilterLabel(id: ActivityFilterId): string {
  if (id === 'recall') {
    return 'Recall';
  }
  if (id === 'all') {
    return 'All';
  }
  if (id === 'conversations') {
    return 'Conversations';
  }
  return 'Tasks';
}

export function isShippingActivityFilter(label: string): boolean {
  return (desktopActivityFilters as readonly string[]).includes(label);
}

export const desktopSettingsPanes = [
  'General',
  'Account & Plan',
  'Transcription',
  'Rewind',
  'Alerts & Privacy',
  'AI & Automation',
  'Apps',
  'About',
] as const;

export type DesktopSettingsPane = (typeof desktopSettingsPanes)[number];

export const desktopSearchPlaceholder = "Search what you've seen and heard…";

// Even 12pt inset from every window edge. Traffic lights sit on the FIRST
// chrome row — the omnibar row — and share that row's vertical center.
// AppDelegate.mm mirrors these numbers (OmiChromeRowHeight == omnibar height).
export const desktopWindowInset = 12;
export const desktopOmnibarHeight = 44;
export const desktopFilterRowHeight = 36;
export const desktopTrafficLightButton = 14;
export const desktopTrafficLightSpacing = 8;
export const desktopTrafficLightTrailing = 16;
export const desktopTrafficLightClusterWidth =
  3 * desktopTrafficLightButton + 2 * desktopTrafficLightSpacing;
export const desktopTrafficLightRowWidth =
  desktopTrafficLightClusterWidth + desktopTrafficLightTrailing;
export const desktopGlassCornerRadius = 22;
export const desktopSystemFontFamily = 'System';

// transitions.dev motion tokens (https://transitions.dev), mapped onto RN.
// Durations: stagger 40 / micro 80 / quick 150 / fast 250 / medium 350 /
// slow 400 / very-slow 500. Easing lives in desktopMotion.ts (smooth-out).
export const desktopMotion = {
  staggerMs: 40,
  microMs: 80,
  quickMs: 150,
  fastMs: 250,
  mediumMs: 350,
  slowMs: 400,
  verySlowMs: 500,
  navMs: 250,
  pressMs: 80,
  stepMs: 250,
  settleMs: 350,
  overlayMs: 400,
  checkboxMs: 150,
  searchExpandMs: 150,
  listInsertMs: 0,
  glassMs: 0,
} as const;

export const desktopStageFade = {
  chatRiseY: 10,
  dropScale: 0.98,
  hubOffsetY: 8,
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

// Legacy v5 chrome support: the pages-IA shell still slides a selection pill
// across measured rail items, so the frame-diff helper stays exported.
export const desktopNavLayoutEpsilon = 0.5;

export type DesktopNavFrame = {x: number; width: number};

export function navFrameMoved(
  previous: DesktopNavFrame | undefined,
  next: DesktopNavFrame,
): boolean {
  if (previous === undefined) {
    return true;
  }
  return (
    Math.abs(previous.x - next.x) > desktopNavLayoutEpsilon ||
    Math.abs(previous.width - next.width) > desktopNavLayoutEpsilon
  );
}
