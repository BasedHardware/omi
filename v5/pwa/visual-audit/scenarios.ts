// Screenshot scenarios for the v5 design preview (pwa/design-preview.html).
// Each id names the PNG. Query parameters are documented in
// pwa/src/design-preview.ts; the preview stubs every backend request.

export type Viewport = { width: number; height: number };

export type AuditScenario = {
  id: string;
  title: string;
  /** design-preview.html query string, without appearance/notice. */
  query: string;
  viewport: Viewport;
  /** Appearances to capture. Mobile has no light theme yet. */
  appearances: readonly ("dark" | "light")[];
};

const desktop: Viewport = { width: 1280, height: 900 };
const desktopCompact: Viewport = { width: 900, height: 700 };
const phone: Viewport = { width: 390, height: 844 };
const both = ["light", "dark"] as const;
const darkOnly = ["dark"] as const;

export const scenarios: AuditScenario[] = [
  // macOS desktop
  {
    id: "desktop-home",
    title: "Activity, all",
    query: "surface=desktop&data=example",
    viewport: desktop,
    appearances: both,
  },
  {
    id: "desktop-home-compact",
    title: "Activity at the minimum window size",
    query: "surface=desktop&data=example",
    viewport: desktopCompact,
    appearances: both,
  },
  {
    id: "desktop-conversations",
    title: "Activity, Conversations filter",
    query: "surface=desktop&data=example&filter=conversations",
    viewport: desktop,
    appearances: both,
  },
  {
    id: "desktop-tasks",
    title: "Activity, Tasks filter",
    query: "surface=desktop&data=example&filter=tasks",
    viewport: desktop,
    appearances: both,
  },
  {
    id: "desktop-recall",
    title: "Activity, Recall filter",
    query: "surface=desktop&data=example&filter=recall",
    viewport: desktop,
    appearances: both,
  },
  {
    id: "desktop-chat",
    title: "Chat overlay with an answer",
    query: "surface=desktop&data=example&chat=ready",
    viewport: desktop,
    appearances: both,
  },
  {
    id: "desktop-chat-waiting",
    title: "Chat overlay while Omi answers",
    query: "surface=desktop&data=example&chat=waiting",
    viewport: desktop,
    appearances: both,
  },
  {
    id: "desktop-chat-error",
    title: "Chat overlay with a send error",
    query: "surface=desktop&data=example&chat=error",
    viewport: desktop,
    appearances: both,
  },
  {
    id: "desktop-settings",
    title: "Settings",
    query: "surface=desktop&data=example&route=settings",
    viewport: desktop,
    appearances: both,
  },
  {
    id: "desktop-empty",
    title: "Activity with no data",
    query: "surface=desktop&data=empty",
    viewport: desktop,
    appearances: both,
  },
  {
    id: "desktop-unavailable",
    title: "Activity when reads are unavailable",
    query: "surface=desktop",
    viewport: desktop,
    appearances: both,
  },
  {
    id: "desktop-setup",
    title: "Desktop onboarding, first step",
    query: "surface=setup",
    viewport: desktop,
    appearances: both,
  },
  // Mobile
  {
    id: "mobile-home",
    title: "Home",
    query: "surface=mobile&data=example",
    viewport: phone,
    appearances: darkOnly,
  },
  {
    id: "mobile-conversations",
    title: "Conversations tab",
    query: "surface=mobile&data=example&route=chat",
    viewport: phone,
    appearances: darkOnly,
  },
  {
    id: "mobile-conversations-loading",
    title: "Conversations loading",
    query: "surface=mobile&data=example&conversations=loading",
    viewport: phone,
    appearances: darkOnly,
  },
  {
    id: "mobile-conversations-error",
    title: "Conversations failed to load",
    query: "surface=mobile&data=example&conversations=error",
    viewport: phone,
    appearances: darkOnly,
  },
  {
    id: "mobile-tasks",
    title: "Tasks tab",
    query: "surface=mobile&data=example&route=tasks",
    viewport: phone,
    appearances: darkOnly,
  },
  {
    id: "mobile-settings",
    title: "Settings tab",
    query: "surface=mobile&data=example&route=settings",
    viewport: phone,
    appearances: darkOnly,
  },
  {
    id: "mobile-apps",
    title: "Apps",
    query: "surface=mobile&data=example&route=apps",
    viewport: phone,
    appearances: darkOnly,
  },
  {
    id: "mobile-ask",
    title: "Ask Omi with an answer",
    query: "surface=mobile&data=example&chat=ready",
    viewport: phone,
    appearances: darkOnly,
  },
  {
    id: "mobile-ask-waiting",
    title: "Ask Omi while Omi answers",
    query: "surface=mobile&data=example&chat=waiting",
    viewport: phone,
    appearances: darkOnly,
  },
  {
    id: "mobile-device-listening",
    title: "Device panel, listening",
    query: "surface=mobile&data=example&device=listening",
    viewport: phone,
    appearances: darkOnly,
  },
  {
    id: "mobile-empty",
    title: "Home with no data",
    query: "surface=mobile&data=empty",
    viewport: phone,
    appearances: darkOnly,
  },
  {
    id: "mobile-setup",
    title: "Mobile onboarding, first step",
    query: "surface=mobile-setup",
    viewport: phone,
    appearances: darkOnly,
  },
];
