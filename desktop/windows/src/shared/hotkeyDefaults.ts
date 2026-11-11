// Default global-shortcut accelerators. Shared by main (registers + persists
// them, see main/shortcuts.ts and main/overlay/shortcut.ts) and the renderer
// (displays them in Settings → Shortcuts) so the two literal strings can't
// hand-copy out of step. Electron-free — importable from either side.

/** Default summon-the-bar chord. */
export const DEFAULT_SUMMON_HOTKEY = 'Shift+Space'
/** Default mic-record chord. */
export const DEFAULT_RECORD_HOTKEY = 'Ctrl+Space'
