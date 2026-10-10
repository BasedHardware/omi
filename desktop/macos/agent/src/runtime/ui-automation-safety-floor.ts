/**
 * The apps and System Settings panes Omi's Accessibility tools never read or
 * touch, whatever the person or the model asks. This is a safety floor, not
 * knowledge about how any app works: it names apps whose windows hold
 * credentials, show them, or run arbitrary code.
 *
 * It is declared once, here. The kernel refuses these bundle ids before any
 * approval card appears, and `scripts/generate-tool-surfaces.mjs` writes the
 * same values into `GeneratedUIAutomationSafetyFloor.swift`, where the Swift
 * executor checks them again against the running process it actually reads.
 * Never copy these lists by hand.
 *
 * Provenance: Apple ids were read from the installed bundles on macOS 27;
 * third-party ids come from each app's Homebrew cask (quit or preferences
 * domain) unless marked otherwise.
 */

/** Every Omi build (stable, Beta, dev and named test bundles) is `com.omi.*`. */
export const UI_AUTOMATION_REFUSED_BUNDLE_ID_PREFIXES: readonly string[] = Object.freeze(["com.omi."]);

/** Bundle ids refused outright, as written; the exported list is lowercased. */
const REFUSED_APPS: readonly string[] = [
  // System sign-in, authorization and credential prompts.
  "com.apple.SecurityAgent",
  "com.apple.loginwindow",
  // Listed in the plan as coreautha; the bundle's real id is the next one.
  "com.apple.coreautha",
  "com.apple.LocalAuthentication.UIAgent",
  "com.apple.tcc.AuthorizationPromptService",
  "com.apple.NetAuthAgent",
  "com.apple.PlatformSSO.PlatformSSOUIAgent",
  "com.apple.security.Keychain-Circle-Notification",
  "com.apple.UserNotificationCenter",
  "com.apple.keychainaccess",
  "com.apple.Passwords",
  "com.apple.Passwords.MenuBarExtra",
  "com.apple.AutoFillPanelService",
  // XPC view services that host password AutoFill and passkey sign-in UI.
  "com.apple.SafariPlatformSupport.Helper",
  "com.apple.AuthenticationServices.Helper",
  // Notification banners carry one-time codes from every app.
  "com.apple.notificationcenterui",
  // Terminals and shells: whatever they show can be anything, and acting in
  // one is arbitrary code execution.
  "com.apple.Terminal",
  "com.googlecode.iterm2",
  "dev.warp.Warp-Stable",
  "com.mitchellh.ghostty",
  "org.alacritty",
  "net.kovidgoyal.kitty",
  // WezTerm's cask names no domain; this is the id in its published Info.plist, unverified here.
  "com.github.wez.wezterm",
  "co.zeit.hyper",
  "org.tabby",
  "com.raphaelamorim.rio",
  "com.termius-dmg.mac",
  "com.cmuxterm.app",
  // Password managers. Capture exclusion also names several by display name;
  // the bundle id is the stronger check.
  "com.1password.1password",
  "com.agilebits.onepassword7",
  "com.bitwarden.desktop",
  "com.lastpass.LastPass",
  "com.lastpass.lastpassmacdesktop",
  // Dashlane has no current cask; this is its commonly documented id, unverified.
  "com.dashlane.dashlanephonefinal",
  "com.keepersecurity.passwordmanager",
  "in.sinew.Enpass-Desktop",
  "org.keepassxc.keepassxc",
  "me.proton.pass.electron",
  "com.nordsec.nordpass",
  "com.SiberSystems.RoboForm",
  "com.sibersystems.RoboFormMac",
];

/**
 * System Settings is not refused as a whole: Sound or Displays are ordinary
 * to read. Only Swift can tell which pane is open, so the kernel lets the
 * request reach the card and Swift checks the open pane on every read. The
 * check is an allow-list: a pane is read only when it is positively
 * identified as one of the ordinary panes; anything else is refused.
 */
export const UI_AUTOMATION_PANE_CHECKED_BUNDLE_ID = "com.apple.systempreferences";

/** Strings in one System Settings extension's string table that name a pane, in every language it ships. */
export interface UIAutomationSettingsStrings {
  extensionBundleId: string;
  table: string;
  keys: readonly string[];
}

/** One way of naming a set of panes: English titles, extension display names, and table strings. */
export interface UIAutomationSettingsNames {
  titles: readonly string[];
  /** Every localized display name these extensions ship names the pane. */
  extensionBundleIds: readonly string[];
  strings: readonly UIAutomationSettingsStrings[];
}

export interface UIAutomationSensitiveSettingsPane extends UIAutomationSettingsNames {
  /** A stable name for logs and the refusal reason; never matched. */
  name: string;
}

const GENERAL_EXTENSION = "com.apple.systempreferences.GeneralSettings";
const generalStrings = (...keys: string[]): UIAutomationSettingsStrings[] => [
  { extensionBundleId: GENERAL_EXTENSION, table: "Localizable", keys },
];

export const UI_AUTOMATION_SENSITIVE_SETTINGS_PANES: readonly UIAutomationSensitiveSettingsPane[] = Object.freeze([
  {
    name: "privacy_security",
    titles: ["Privacy & Security", "Security & Privacy"],
    extensionBundleIds: ["com.apple.settings.PrivacySecurity.extension"],
    strings: [],
  },
  {
    name: "passwords",
    titles: ["Passwords", "AutoFill & Passwords"],
    extensionBundleIds: [],
    strings: generalStrings("AutoFill & Passwords"),
  },
  {
    name: "users_groups",
    titles: ["Users & Groups"],
    extensionBundleIds: ["com.apple.Users-Groups-Settings.extension"],
    strings: [],
  },
  {
    name: "touch_id_password",
    titles: ["Touch ID & Password", "Login Password"],
    extensionBundleIds: ["com.apple.Touch-ID-Settings.extension"],
    strings: [],
  },
  {
    name: "lock_screen",
    titles: ["Lock Screen"],
    extensionBundleIds: ["com.apple.Lock-Screen-Settings.extension"],
    strings: [],
  },
  {
    name: "wallet_apple_pay",
    titles: ["Wallet & Apple Pay"],
    extensionBundleIds: ["com.apple.WalletSettingsExtension"],
    strings: [],
  },
  {
    name: "apple_account",
    titles: ["Apple Account", "Apple ID", "iCloud", "Family", "Family Sharing"],
    extensionBundleIds: ["com.apple.systempreferences.AppleIDSettings", "com.apple.Family-Settings.extension"],
    strings: [],
  },
  {
    name: "internet_accounts",
    titles: ["Internet Accounts"],
    extensionBundleIds: ["com.apple.Internet-Accounts-Settings.extension"],
    strings: [],
  },
  {
    name: "game_center",
    titles: ["Game Center"],
    extensionBundleIds: ["com.apple.Game-Center-Settings.extension"],
    strings: [],
  },
  {
    name: "screen_time",
    titles: ["Screen Time"],
    extensionBundleIds: ["com.apple.Screen-Time-Settings.extension"],
    strings: [],
  },
  {
    name: "sharing",
    titles: ["Sharing"],
    extensionBundleIds: ["com.apple.Sharing-Settings.extension"],
    strings: generalStrings("Sharing"),
  },
  {
    name: "login_items",
    titles: ["Login Items & Extensions", "Login Items"],
    extensionBundleIds: ["com.apple.LoginItems-Settings.extension"],
    strings: generalStrings("Login Items & Extensions"),
  },
  {
    // Saved networks live under Network, Wi-Fi and VPN alike.
    name: "network",
    titles: ["Network", "Wi-Fi", "VPN"],
    extensionBundleIds: [
      "com.apple.Network-Settings.extension",
      "com.apple.wifi-settings-extension",
      "com.apple.NetworkExtensionSettingsUI.NESettingsUIExtension",
    ],
    strings: [],
  },
]);

/**
 * Top-level panes that may be read when the sidebar selects them. Every
 * installed System Settings extension that is not a sensitive pane also
 * counts, by every display name it ships; these add English fallbacks and
 * the panes whose name lives in a string table instead.
 */
export const UI_AUTOMATION_ALLOWED_SETTINGS_PANES: UIAutomationSettingsNames = Object.freeze({
  titles: [
    "Accessibility", "Appearance", "Apple Intelligence & Siri", "Siri", "Battery", "Energy", "Bluetooth",
    "Control Center", "Menu Bar", "Desktop & Dock", "Displays", "Focus", "Notifications", "Sound", "Spotlight",
    "Wallpaper", "Screen Saver", "Keyboard", "Mouse", "Trackpad", "Printers & Scanners", "Game Controllers",
  ],
  extensionBundleIds: [],
  strings: [
    { extensionBundleId: "com.apple.Battery-Settings.extension", table: "Localizable", keys: ["BATTERY_PREF_TITLE", "ENERGY_SAVER_PREF_TITLE"] },
  ],
});

/**
 * General hosts subpages, some sensitive (Sharing, Login Items, AutoFill &
 * Passwords). With General selected in the sidebar, the window title must be
 * one of these ordinary subpages, in any language General ships, or the read
 * is refused.
 */
export const UI_AUTOMATION_SETTINGS_GENERAL = Object.freeze({
  extensionBundleId: GENERAL_EXTENSION,
  allowedSubpages: Object.freeze({
    titles: [
      "General", "About", "Software Update", "Storage", "AirDrop & Continuity", "AirDrop & Handoff",
      "Language & Region", "Date & Time", "Time Machine", "Transfer or Reset", "Startup Disk", "Device Management",
      "AppleCare & Warranty",
    ],
    extensionBundleIds: [GENERAL_EXTENSION],
    strings: generalStrings(
      "General", "About", "Software Update", "Storage", "AirDrop & Continuity", "Language & Region", "Date & Time",
      "Time Machine", "Transfer or Reset", "Startup Disk", "Device Management", "AppleCare & Warranty",
    ),
  }) as UIAutomationSettingsNames,
});

/**
 * Pages inside Privacy & Security. Their names also appear as ordinary panes
 * (Accessibility, Bluetooth, Focus, Home), so a window titled with one is
 * refused unless the selected sidebar row is that same name: the page could
 * otherwise be reached by a link or history while the sidebar still selects
 * an ordinary pane. Keys are in Privacy & Security's `Localizable` table;
 * Accessibility is named by the Accessibility pane's own display names.
 */
export const UI_AUTOMATION_SETTINGS_PRIVACY_SUBPAGES: UIAutomationSettingsNames = Object.freeze({
  titles: [
    "Full Disk Access", "Location Services", "FileVault", "Accessibility", "Screen & System Audio Recording",
    "Screen Recording", "Input Monitoring", "Files & Folders", "Automation", "Developer Tools", "Camera",
    "Microphone", "Contacts", "Calendars", "Reminders", "Photos", "Bluetooth", "App Management",
    "Analytics & Improvements", "Apple Advertising", "Lockdown Mode", "Media & Apple Music", "Speech Recognition",
    "Passkeys Access for Web Browsers", "Local Network", "Remote Desktop", "Focus", "Home", "HomeKit",
    "Motion & Fitness", "Sensitive Content Warning", "Paste from Other Apps", "App Data", "Extensions",
  ],
  extensionBundleIds: ["com.apple.Accessibility-Settings.extension"],
  strings: [
    {
      extensionBundleId: "com.apple.settings.PrivacySecurity.extension",
      table: "Localizable",
      keys: [
        "ALL_FILES", "LOCATION_SERVICES", "FileVault", "SCREEN_CAPTURE_HEADER", "SCREENANDAUDIOCAPTURE", "LISTEN_EVENT",
        "FILE_ACCESS_COMBINED", "AUTOMATION", "DEV_TOOLS", "CAMERA", "MICROPHONE", "CONTACTS", "CALENDARS", "REMINDERS",
        "Photos", "PHOTOS", "BLUETOOTH", "APPLICATION_BUNDLES", "ANALYTICS", "ADVERTISING", "Lockdown Mode", "MEDIA",
        "SPEECH_RECOGNITION", "WEB_BROWSER_PASSKEY_ACCESS", "LOCAL_NETWORK", "REMOTE_DESKTOP", "DND", "HomeKit",
        "HOMEKIT", "MOTION", "Sensitive Content Warning", "PASTEBOARD_ACCESS",
      ],
    },
  ],
});

/**
 * Lowercased bundle ids refused outright: the apps above plus every sensitive
 * pane's own extension, so a request naming the extension process is refused
 * instead of skipping the pane check.
 */
export const UI_AUTOMATION_REFUSED_BUNDLE_IDS: readonly string[] = Object.freeze([
  ...new Set([
    ...REFUSED_APPS,
    ...UI_AUTOMATION_SENSITIVE_SETTINGS_PANES.flatMap((pane) => pane.extensionBundleIds),
  ].map((id) => id.toLowerCase())),
]);

const BUNDLE_ID_SHAPE = /^[a-z0-9-]+(\.[a-z0-9-]+)+$/;
const MAX_BUNDLE_ID_LENGTH = 255;

/** Trimmed and lowercased: LaunchServices treats bundle ids case-insensitively. */
export function normalizedUIAutomationBundleId(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const normalized = value.trim().toLowerCase();
  return normalized || undefined;
}

export function isWellFormedUIAutomationBundleId(normalized: string): boolean {
  return normalized.length <= MAX_BUNDLE_ID_LENGTH && BUNDLE_ID_SHAPE.test(normalized);
}

/** Whether a normalized bundle id is on the floor (Omi itself or the refused list). */
export function isRefusedUIAutomationBundleId(normalized: string): boolean {
  return UI_AUTOMATION_REFUSED_BUNDLE_ID_PREFIXES.some((prefix) => normalized.startsWith(prefix))
    || UI_AUTOMATION_REFUSED_BUNDLE_IDS.includes(normalized);
}
