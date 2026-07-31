// TaskAssistant app-gating lists — pure. Windows port of Mac's
// TaskAssistantSettings whitelist/browser lists (Set:21–80) + TaskAssistant's
// messaging sets (TA:57–66, 894).
//
// Every entry is a lowercased substring, matched via
// `value.toLowerCase().includes(entry)` — the exact idiom `distributionGate.ts`
// already uses, so a Windows `frame.app` of "Google Chrome" / "Chrome" /
// "chrome.exe" all resolve through the `chrome` substring. macOS display-name
// isms are normalized at port time: `zoom.us`→`zoom`, `Google Chrome`→`chrome`,
// `Microsoft Edge`→`edge`, `Brave Browser`→`brave`, and the hidden LTR-mark
// WhatsApp variants collapse to `whatsapp`.
//
// FOUR SEPARATE lists gate four different things (do not collapse them):
//  - MESSAGING_APPS        — the ~15s messaging fast-path (reused, not duplicated)
//  - ALLOWED_APPS          — the positive whitelist (Task gates on this, NOT the
//                            builtin exclude list the other assistants use)
//  - BROWSER_APPS          — browsers, whose window title must also clear a keyword
//  - PROMPT_MESSAGING_APPS — whether to append the "THIS IS A MESSAGING APP" block

import { MESSAGING_APPS } from '../core/distributionGate'

// Re-export so the assistant imports one appLists module for every gate.
export { MESSAGING_APPS }

/** Whitelist (Mac `defaultAllowedApps`, Set:21–41 — 16 entries → 15 after the two
 *  WhatsApp variants collapse). Non-whitelisted apps are skipped entirely. */
export const ALLOWED_APPS: readonly string[] = [
  'telegram',
  'whatsapp',
  'messages',
  'slack',
  'discord',
  'zoom',
  'chrome',
  'arc',
  'safari',
  'firefox',
  'edge',
  'brave',
  'opera',
  'notes',
  'superhuman'
]

/** Browsers (Mac `browserApps`, Set:43–51 — 7). These get the extra
 *  window-title keyword filter below. */
export const BROWSER_APPS: readonly string[] = [
  'chrome',
  'arc',
  'safari',
  'firefox',
  'edge',
  'brave',
  'opera'
]

/** Browser window-title allow keywords (Mac `defaultBrowserKeywords`, Set:61–80),
 *  every entry lowercased for substring matching against a lowercased title. */
export const BROWSER_KEYWORDS: readonly string[] = [
  // Email
  'gmail',
  'outlook',
  'yahoo mail',
  'protonmail',
  'superhuman',
  'fastmail',
  // Messaging
  'slack',
  'discord',
  'whatsapp',
  'telegram',
  'messenger',
  'signal',
  'crisp',
  // Project management
  'jira',
  'linear',
  'trello',
  'asana',
  'notion',
  'monday',
  'clickup',
  'basecamp',
  // Calendar
  'google calendar',
  'outlook calendar',
  'cal.com',
  'calendly',
  // Code & collaboration
  'github',
  'github.com',
  'google docs',
  'google sheets',
  'google slides',
  // Finance
  'stripe',
  'paypal',
  'invoice',
  'billing',
  'quickbooks',
  // Forms
  'google forms',
  'typeform',
  'docusign',
  // Action keywords
  'todo',
  'task',
  'assign',
  'review',
  'approve',
  'request',
  'ticket',
  // Inbox patterns
  'inbox',
  'unread',
  'notification',
  'pending'
]

/** The messaging-reminder set (Mac TA:894 — 6 entries → 5 distinct after the
 *  WhatsApp variants collapse). Gates ONLY the "THIS IS A MESSAGING APP" prompt
 *  block; distinct from MESSAGING_APPS (the fast-path set). */
export const PROMPT_MESSAGING_APPS: readonly string[] = [
  'telegram',
  'whatsapp',
  'messages',
  'slack',
  'discord'
]

function matchesAny(value: string, list: readonly string[]): boolean {
  const v = value.toLowerCase()
  return list.some((entry) => v.includes(entry))
}

/** Fast-path messaging app (Mac `messagingFastPathApps`) — reuses the shared set. */
export function isMessagingApp(app: string): boolean {
  return matchesAny(app, MESSAGING_APPS)
}

/** Whitelist gate (Mac `isAppAllowed`). */
export function isAppAllowed(app: string): boolean {
  return matchesAny(app, ALLOWED_APPS)
}

/** True when the app is one of the browsers subject to title filtering. */
export function isBrowserApp(app: string): boolean {
  return matchesAny(app, BROWSER_APPS)
}

/** Window gate (Mac `isWindowAllowed`): a browser must show a title containing at
 *  least one keyword; non-browser apps always pass. */
export function isWindowAllowed(app: string, windowTitle: string): boolean {
  if (!isBrowserApp(app)) return true
  return matchesAny(windowTitle, BROWSER_KEYWORDS)
}

/** Whether to append the messaging-reminder block to the user prompt (Mac TA:894). */
export function isPromptMessagingApp(app: string): boolean {
  return matchesAny(app, PROMPT_MESSAGING_APPS)
}
