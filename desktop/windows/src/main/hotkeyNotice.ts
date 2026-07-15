// Turn a set of global-shortcut registration outcomes into a single, actionable
// user notice. A chord fails to register when the OS won't claim it — typically
// another app (or a second Omi instance) already owns it. The only in-app signal
// otherwise is Settings → Shortcuts, which a new user never opens, so a failed
// summon/record chord leaves their hotkey silently dead. Kept pure (no Electron)
// so the decision is unit-tested in isolation; the caller shows the result via
// the shared notification path.

export interface HotkeyRegistration {
  /** User-facing name matching the Settings → Shortcuts card title ("Summon",
   *  "Record"). */
  name: string
  /** The Electron accelerator the user sees, e.g. "Shift+Space". */
  accelerator: string
  /** Whether the OS actually claimed the chord. */
  registered: boolean
  /** Whether the chord was meant to be claimed at all. A chord the user turned
   *  off (e.g. the record chord) is expectedly unregistered — never a conflict.
   *  Defaults to true. */
  enabled?: boolean
}

export interface HotkeyConflictNotice {
  title: string
  body: string
}

/** Build the one notice for whichever enabled chords failed to register, or null
 *  when every enabled chord registered. Combines multiple failures into a single
 *  notice so the user is never shown two toasts at once. */
export function buildHotkeyConflictNotice(
  registrations: HotkeyRegistration[]
): HotkeyConflictNotice | null {
  const failed = registrations.filter((r) => r.enabled !== false && !r.registered)
  if (failed.length === 0) return null
  const one = failed.length === 1
  const list = failed.map((r) => `${r.name} (${r.accelerator})`).join(' and ')
  return {
    title: one ? 'Shortcut unavailable' : 'Shortcuts unavailable',
    body: `Omi couldn't register the ${list} ${one ? 'shortcut' : 'shortcuts'} — another app may already be using ${one ? 'it' : 'them'}. Pick another in Settings → Shortcuts.`
  }
}
