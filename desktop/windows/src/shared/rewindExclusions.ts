// Built-in Rewind capture exclusions. Always on (not user-editable), matched
// case-insensitively as a substring — the same matcher as user-added exclusions.
// NOTE: Omi's own main window is NOT excluded — it's intentionally captured like
// any other app (see index.ts). Only the transient overlay HUD is hidden, via
// setContentProtection in overlay/window.ts (not this list).

// Apps Rewind should never capture while frontmost — matched against the
// foreground app/process name. Two groups:
//  - screenshot / screen-recording tools (ported from the macOS app's
//    ProactiveAssistantsPlugin, translated from bundle IDs to Windows names)
//  - password managers (so their windows are never stored)
export const BUILT_IN_EXCLUDED_APPS: string[] = [
  // Screenshot / screen recording
  'CleanShot',
  'Loom',
  'Snagit',
  'OBS',
  'Monosnap',
  'Lightshot',
  'ShareX',
  'Greenshot',
  'Snipping Tool',
  'Snip & Sketch',
  'Camtasia',
  // Password managers
  '1Password',
  'Bitwarden',
  'KeePass', // also covers KeePassXC
  'LastPass',
  'Dashlane',
  'NordPass',
  'Proton Pass',
  'Keeper Password',
  'RoboForm',
  'Enpass'
]

// Sensitive WINDOW-TITLE markers — matched against the foreground window title so
// Rewind skips login / password / private-browsing screens even in a normal
// browser (where the app is just "Chrome"). Substring, case-insensitive.
export const SENSITIVE_WINDOW_MARKERS: string[] = [
  // Private/incognito browsing
  'incognito',
  'inprivate',
  'private browsing',
  // Auth / credential screens
  'log in',
  'login',
  'sign in',
  'sign-in',
  'log into',
  'password',
  'two-factor',
  '2fa',
  'one-time code'
]
