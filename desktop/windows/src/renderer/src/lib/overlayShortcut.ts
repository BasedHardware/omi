// Pure helpers for the overlay summon shortcut: convert between an Electron
// accelerator string (e.g. "CommandOrControl+Space") and the display keycaps the
// onboarding step renders, and turn a browser KeyboardEvent into an accelerator
// while the user records a custom shortcut. No DOM/Electron deps — unit-tested.

/** Default summon accelerator (mirrors main's OVERLAY_ACCELERATOR). */
export const DEFAULT_OVERLAY_ACCELERATOR = 'Shift+Space'

// Accelerator token → the label shown on a keycap (Windows wording).
const TOKEN_LABELS: Record<string, string> = {
  CommandOrControl: 'Ctrl',
  CmdOrCtrl: 'Ctrl',
  Control: 'Ctrl',
  Ctrl: 'Ctrl',
  Command: 'Win',
  Cmd: 'Win',
  Super: 'Win',
  Meta: 'Win',
  Shift: 'Shift',
  Alt: 'Alt',
  Option: 'Alt',
  Space: 'Space',
  Return: 'Enter',
  Enter: 'Enter',
  Escape: 'Esc',
  Backspace: 'Backspace',
  Tab: 'Tab'
}

/**
 * Split an Electron accelerator into the keycap labels to render, in modifier-
 * first order. Unknown single characters are upper-cased (e.g. "j" → "J").
 */
export function acceleratorToTokens(accel: string): string[] {
  if (!accel) return []
  return accel
    .split('+')
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => TOKEN_LABELS[p] ?? (p.length === 1 ? p.toUpperCase() : p))
}

// A pressed key (KeyboardEvent.key) → its accelerator key token. Modifiers are
// handled separately; this maps the single non-modifier key.
function mainKeyToAccelToken(key: string): string | null {
  if (key === ' ' || key === 'Spacebar') return 'Space'
  if (key === 'Enter') return 'Return'
  if (key === 'Escape') return null // Esc cancels capture; never a shortcut key here
  if (key === 'Tab') return 'Tab'
  if (key === 'Backspace') return 'Backspace'
  if (/^Arrow(Up|Down|Left|Right)$/.test(key)) return key.replace('Arrow', '')
  if (/^F\d{1,2}$/.test(key)) return key // function keys
  if (key.length === 1) {
    const c = key.toUpperCase()
    // Letters and digits are valid accelerator keys; punctuation we pass through.
    return c
  }
  return null
}

const MODIFIER_KEYS = new Set(['Control', 'Shift', 'Alt', 'Meta', 'OS'])

// Accelerator-token sets for validation.
const MODIFIER_TOKENS = new Set([
  'CommandOrControl',
  'CmdOrCtrl',
  'Control',
  'Ctrl',
  'Command',
  'Cmd',
  'Super',
  'Meta',
  'Alt',
  'Option',
  'Shift'
])
// Alt is dangerous on Windows: it activates window menus and the menu-mnemonic
// system, so a global Alt+<key> hotkey routinely clashes. We reject Alt outright.
const ALT_TOKENS = new Set(['Alt', 'Option'])

// Combos that are unstable to claim globally — they'd hijack everyday system or
// editor actions. Compared case-insensitively against the built accelerator.
// (Ctrl is "CommandOrControl"; Enter is "Return" in accelerator form.)
const UNSTABLE_ACCELERATORS = new Set(
  [
    // System / window manager
    'CommandOrControl+Alt+Delete',
    'CommandOrControl+Escape',
    'CommandOrControl+Shift+Escape',
    'Super+L',
    'Super+D',
    'Super+E',
    'Super+R',
    'Super+Tab',
    // Universal editor shortcuts (would steal copy/paste/save/etc.)
    'CommandOrControl+C',
    'CommandOrControl+V',
    'CommandOrControl+X',
    'CommandOrControl+Z',
    'CommandOrControl+Y',
    'CommandOrControl+A',
    'CommandOrControl+S',
    'CommandOrControl+F',
    'CommandOrControl+P',
    'CommandOrControl+W',
    'CommandOrControl+N',
    'CommandOrControl+T',
    'CommandOrControl+O',
    'CommandOrControl+Return', // Ctrl+Enter — common "send"
    'CommandOrControl+Tab'
  ].map((a) => a.toLowerCase())
)

export type ShortcutValidation = { ok: true } | { ok: false; reason: string }

/**
 * Reject custom shortcuts that would clash with the OS or be unstable on Windows:
 * exactly one key plus a modifier; no Alt (menu hijack); Shift may stand alone
 * only with a non-typing key (Shift+Space/Enter/Tab/arrows is fine, Shift+letter
 * just types a capital); and not a common system/editor combo. A combo already
 * owned by another app is caught separately, when registration fails.
 */
export function validateCustomAccelerator(accel: string): ShortcutValidation {
  if (!accel) return { ok: false, reason: 'No keys captured.' }
  const parts = accel
    .split('+')
    .map((p) => p.trim())
    .filter(Boolean)
  const keys = parts.filter((p) => !MODIFIER_TOKENS.has(p))
  const mods = parts.filter((p) => MODIFIER_TOKENS.has(p))
  if (keys.length !== 1) return { ok: false, reason: 'Use one key plus a modifier.' }
  if (mods.length === 0) return { ok: false, reason: 'Add a modifier — Ctrl, Win, or Shift.' }
  if (mods.some((m) => ALT_TOKENS.has(m))) {
    return { ok: false, reason: 'Avoid Alt — it triggers Windows menus.' }
  }
  // A single-character key (letter/digit/punctuation) is a "typing" key; Space,
  // Enter, Tab, arrows and function keys are multi-character tokens.
  const isTypingKey = keys[0].length === 1
  if (mods.every((m) => m === 'Shift') && isTypingKey) {
    return { ok: false, reason: 'Shift + a letter just types — add Ctrl or Win.' }
  }
  if (UNSTABLE_ACCELERATORS.has(accel.toLowerCase())) {
    return { ok: false, reason: 'That clashes with a common shortcut — pick another.' }
  }
  return { ok: true }
}

/**
 * Build an Electron accelerator from a recorded keydown, or null if the event
 * isn't yet a complete, valid shortcut. Requires at least one modifier plus one
 * non-modifier key, so a bare letter can't claim a global hotkey.
 */
export function eventToAccelerator(e: {
  key: string
  ctrlKey: boolean
  shiftKey: boolean
  altKey: boolean
  metaKey: boolean
}): string | null {
  // Ignore a keydown that is itself only a modifier (the user is still building
  // the chord).
  if (MODIFIER_KEYS.has(e.key)) return null

  const mainKey = mainKeyToAccelToken(e.key)
  if (!mainKey) return null

  const mods: string[] = []
  if (e.ctrlKey) mods.push('CommandOrControl')
  if (e.altKey) mods.push('Alt')
  if (e.shiftKey) mods.push('Shift')
  if (e.metaKey) mods.push('Super')

  if (mods.length === 0) return null // a global shortcut needs a modifier
  return [...mods, mainKey].join('+')
}
