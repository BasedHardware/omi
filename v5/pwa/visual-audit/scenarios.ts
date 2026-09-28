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
  /** Appearances to capture. */
  appearances: readonly ("dark" | "light")[];
};

const desktop: Viewport = { width: 1280, height: 900 };
const desktopCompact: Viewport = { width: 900, height: 700 };
const phone: Viewport = { width: 390, height: 844 };
const phoneSmall: Viewport = { width: 375, height: 812 };
const phoneLarge: Viewport = { width: 430, height: 932 };
const both = ["light", "dark"] as const;

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
  // Mobile. Every phone query pins the preview's phone frame to the viewport
  // width (frame=…): headless Chrome lays out at least 500 px wide, so an
  // unpinned frame would be centred and clipped by the screenshot.
  ...[
    ["mobile-home", "Home", "data=example"],
    ["mobile-conversations", "Conversations tab", "data=example&route=chat"],
    [
      "mobile-conversations-loading",
      "Conversations loading",
      "data=example&conversations=loading",
    ],
    [
      "mobile-conversations-error",
      "Conversations failed to load",
      "data=example&conversations=error",
    ],
    [
      "mobile-conversation-detail",
      "Conversation detail (detail reads are stubbed)",
      "data=example&route=chat&conversation=preview-conversation-0",
    ],
    ["mobile-tasks", "Tasks tab", "data=example&route=tasks"],
    ["mobile-tasks-empty", "Tasks tab with no tasks", "data=empty&route=tasks"],
    ["mobile-settings", "Settings tab", "data=example&route=settings"],
    ["mobile-apps", "Apps", "data=example&route=apps"],
    ["mobile-ask", "Ask Omi with an answer", "data=example&chat=ready"],
    [
      "mobile-ask-waiting",
      "Ask Omi while Omi answers",
      "data=example&chat=waiting",
    ],
    [
      "mobile-ask-empty",
      "Ask Omi before the first message",
      "data=example&chat=empty",
    ],
    [
      "mobile-ask-error",
      "Ask Omi with a send error",
      "data=example&chat=error",
    ],
    [
      "mobile-device-listening",
      "Device panel, listening",
      "data=example&device=listening",
    ],
    ["mobile-search", "Search results on Home", "data=example&q=review"],
    ["mobile-empty", "Home with no data", "data=empty"],
    ["mobile-unavailable", "Home when reads are unavailable", ""],
  ].map(
    ([id, title, query]): AuditScenario => ({
      id,
      title,
      query: `surface=mobile&frame=${phone.width}${query ? `&${query}` : ""}`,
      viewport: phone,
      appearances: both,
    })
  ),
  ...[phoneSmall, phoneLarge].map(
    (viewport): AuditScenario => ({
      id: `mobile-home-${viewport.width}`,
      title: `Home at ${viewport.width} pt`,
      query: `surface=mobile&frame=${viewport.width}&data=example`,
      viewport,
      appearances: both,
    })
  ),
  {
    id: "mobile-setup",
    title: "Mobile onboarding, first step",
    query: `surface=mobile-setup&frame=${phone.width}`,
    viewport: phone,
    appearances: both,
  },
];
