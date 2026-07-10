// Physical key-state sampling for the summon gesture (Win32 GetAsyncKeyState
// via koffi). globalShortcut never reports key-up; sampling the chord's
// non-modifier key is what turns auto-repeat fires into ONE gesture with a
// real release edge (and unlocks the PTT-hold reveal path). Sampling happens
// only while a gesture is live — never while idle.
import koffi from 'koffi'

// Electron accelerator key → Win32 virtual-key code (the non-modifier key of
// the chord; modifiers don't matter for release detection).
const VK: Record<string, number> = {
  SPACE: 0x20,
  TAB: 0x09,
  ENTER: 0x0d,
  RETURN: 0x0d,
  ESC: 0x1b,
  ESCAPE: 0x1b,
  BACKSPACE: 0x08,
  DELETE: 0x2e,
  INSERT: 0x2d,
  HOME: 0x24,
  END: 0x23,
  PAGEUP: 0x21,
  PAGEDOWN: 0x22,
  UP: 0x26,
  DOWN: 0x28,
  LEFT: 0x25,
  RIGHT: 0x27,
  PLUS: 0xbb,
  MINUS: 0xbd,
  COMMA: 0xbc,
  PERIOD: 0xbe,
  SEMICOLON: 0xba,
  QUOTE: 0xde,
  SLASH: 0xbf,
  BACKSLASH: 0xdc,
  BACKQUOTE: 0xc0,
  '`': 0xc0,
  '[': 0xdb,
  ']': 0xdd
}
for (let i = 0; i < 26; i++) VK[String.fromCharCode(65 + i)] = 0x41 + i // A-Z
for (let i = 0; i <= 9; i++) VK[String(i)] = 0x30 + i // 0-9
for (let i = 1; i <= 24; i++) VK[`F${i}`] = 0x70 + (i - 1) // F1-F24

/** The chord's non-modifier key, or null if it's modifier-only. */
export function acceleratorMainKey(accelerator: string): string | null {
  const MODS = new Set([
    'CTRL',
    'CONTROL',
    'CMDORCTRL',
    'COMMANDORCONTROL',
    'ALT',
    'ALTGR',
    'OPTION',
    'SHIFT',
    'SUPER',
    'META',
    'CMD',
    'COMMAND'
  ])
  const parts = accelerator
    .split('+')
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean)
  const main = parts.filter((x) => !MODS.has(x))
  return main.length === 1 ? main[0] : null
}

type GetAsyncKeyState = (vk: number) => number
let getAsyncKeyState: GetAsyncKeyState | null = null
let loadFailed = false

function loadUser32(): GetAsyncKeyState | null {
  if (getAsyncKeyState) return getAsyncKeyState
  if (loadFailed) return null
  try {
    const user32 = koffi.load('user32.dll')
    getAsyncKeyState = user32.func('int16 GetAsyncKeyState(int vKey)') as GetAsyncKeyState
    return getAsyncKeyState
  } catch (e) {
    console.warn('[bar] GetAsyncKeyState unavailable; hold detection degraded to gap mode:', e)
    loadFailed = true
    return null
  }
}

/**
 * Build a "is the chord's key physically down right now" sampler for an
 * accelerator, or null when unavailable (off-Windows, koffi failure, unmapped
 * key) — the gesture machine then falls back to repeat-gap grouping.
 */
export function makeKeySampler(accelerator: string): (() => boolean) | null {
  if (process.platform !== 'win32') return null
  const key = acceleratorMainKey(accelerator)
  if (!key) return null
  const vk = VK[key]
  if (vk === undefined) return null
  const fn = loadUser32()
  if (!fn) return null
  return () => {
    try {
      // High bit set = key currently down. int16 → negative when set.
      return (fn(vk) & 0x8000) !== 0
    } catch {
      return false
    }
  }
}
