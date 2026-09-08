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

type User32 = {
  getAsyncKeyState: (vk: number) => number
  getSystemMetrics: (index: number) => number
}
let user32: User32 | null = null
let loadFailed = false

function loadUser32(): User32 | null {
  if (user32) return user32
  if (loadFailed) return null
  try {
    const lib = koffi.load('user32.dll')
    user32 = {
      getAsyncKeyState: lib.func('int16 GetAsyncKeyState(int vKey)') as (vk: number) => number,
      getSystemMetrics: lib.func('int GetSystemMetrics(int nIndex)') as (i: number) => number
    }
    return user32
  } catch (e) {
    console.warn('[bar] user32 unavailable; hold/click detection degraded to gap mode:', e)
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
  const api = loadUser32()
  if (!api) return null
  return () => {
    try {
      // High bit set = key currently down. int16 → negative when set.
      return (api.getAsyncKeyState(vk) & 0x8000) !== 0
    } catch {
      return false
    }
  }
}

const VK_LBUTTON = 0x01
const VK_RBUTTON = 0x02
const SM_SWAPBUTTON = 23

/**
 * Build an "was the PRIMARY mouse button just down" sampler, or null when
 * unavailable (off-Windows / koffi failure). Uses GetAsyncKeyState so a press is
 * caught regardless of how it was delivered — the bar window never receives the
 * click message at all (see the clickTick block in window.ts for why: DWM/DComp
 * alpha hit-testing + non-activatable-window activation eat hardware clicks on a
 * transparent overlay), but the physical primary button still registers here for
 * BOTH an external mouse and a Precision Touchpad button.
 *
 * Reads BOTH bits of GetAsyncKeyState in one call:
 *   0x8000 — level: the button is down right now (a held/slow press).
 *   0x0001 — latch: pressed since the previous call (a fast press+release that
 *            went down AND up entirely between two samples). The latch is a
 *            SHARED, best-effort systemwide flag — another GetAsyncKeyState
 *            caller can consume it first — which is why the DOM onClick path
 *            stays as a second belt and we sample fast (see CLICK_SAMPLE_MS).
 *
 * Swap-aware: with SwapMouseButton set, the physical primary reports as
 * VK_RBUTTON (read once at creation — it changes only via a system setting).
 */
export function makePrimaryMouseButtonSampler(): (() => boolean) | null {
  if (process.platform !== 'win32') return null
  const api = loadUser32()
  if (!api) return null
  let primaryVk = VK_LBUTTON
  try {
    if (api.getSystemMetrics(SM_SWAPBUTTON) !== 0) primaryVk = VK_RBUTTON
  } catch {
    /* default to the left button */
  }
  return () => {
    try {
      return (api.getAsyncKeyState(primaryVk) & 0x8001) !== 0
    } catch {
      return false
    }
  }
}
