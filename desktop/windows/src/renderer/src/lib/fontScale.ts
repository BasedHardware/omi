// Global UI font-scale — the Windows port of macOS `FontScaleSettings.shared`
// (General → Font Size). Tailwind is rem-based, so multiplying the ROOT element's
// font-size scales the whole main-window UI ("root rem multiplier").
//
// Explicit-init model: this module runs NO side effects on import. `main.tsx` (the
// renderer composition root) calls `initFontScale()` once at startup — main window
// only — which applies the persisted scale, registers the app-wide Ctrl+= /
// Ctrl+- / Ctrl+0 shortcuts, and subscribes to preference changes for live
// re-apply. The dependency is strictly one-directional (fontScale.ts → preferences.ts)
// so there is no import cycle. The FONT_SCALE_* bounds are declared in preferences.ts
// (the SSOT, so its eval-time clamp is order-safe) and re-exported here — the surface
// consumers import from.
import {
  getPreferences,
  setPreferences,
  onPreferencesChange,
  FONT_SCALE_MIN,
  FONT_SCALE_MAX,
  FONT_SCALE_DEFAULT
} from './preferences'
import { isSecondaryWindow } from './windowRole'
import { snapToStep } from '../components/settings/controls/sliderMath'

export { FONT_SCALE_MIN, FONT_SCALE_MAX, FONT_SCALE_DEFAULT }
/** Base root font-size the scale multiplies (matches globals.css `html`). */
const ROOT_FONT_PX = 16
/** Keyboard nudge per Ctrl+= / Ctrl+- (macOS parity: 0.1 steps). */
const KEY_STEP = 0.1

/** Clamp any input into the supported [0.5, 2.0] range, defaulting junk to 1.0. */
export function clampFontScale(n: number | undefined | null): number {
  if (typeof n !== 'number' || !Number.isFinite(n)) return FONT_SCALE_DEFAULT
  return Math.min(FONT_SCALE_MAX, Math.max(FONT_SCALE_MIN, n))
}

/**
 * Apply the scale as the root rem multiplier. No-op outside a DOM and in every
 * SECONDARY window (bar / insight-toast / capture): those are visually exempt, so
 * scaling their root would resize the floating bar. Rounded to 2dp so the inline
 * style string stays clean. Skips the DOM write when the value is unchanged, so
 * unrelated preference changes flowing through the subscriber don't force a
 * needless root-style mutation.
 */
export function applyFontScale(scale: number | undefined | null): void {
  if (typeof document === 'undefined' || typeof window === 'undefined') return
  if (isSecondaryWindow()) return
  const px = Math.round(ROOT_FONT_PX * clampFontScale(scale) * 100) / 100
  const next = `${px}px`
  if (document.documentElement.style.fontSize === next) return
  document.documentElement.style.fontSize = next
}

// ── App-wide keyboard shortcuts (main window only) ────────────────────────────
// Ctrl+= / Ctrl++ increase, Ctrl+- decrease (0.1, clamped), Ctrl+0 reset. Writes
// route through setPreferences so every window + subscriber stays in sync.
function nudgeFontScale(delta: number): void {
  // Single read-side clamp on `current`; setPreferences clamps the write too.
  // Snap the result to the same 0.05 grid the Slider uses so equal up/down nudges
  // return to exact grid values (and exactly 1.0) — plain `current + delta` with a
  // 0.1 step accumulates binary-float drift (1.0000000000000002), which would keep
  // FontSizeCard's `isDefault` false and leave the "Reset" affordance showing at 100%.
  const current = clampFontScale(getPreferences().fontScale)
  setPreferences({ fontScale: snapToStep(current + delta, FONT_SCALE_MIN, FONT_SCALE_MAX, 0.05) })
}

/**
 * One-time startup wiring, called by main.tsx (primary window only). Applies the
 * persisted scale, registers the Ctrl+font shortcuts, and subscribes to live
 * preference changes. Idempotent — a second call (e.g. in tests) is a no-op so the
 * keydown listener is never double-registered.
 */
let initialized = false
export function initFontScale(): void {
  if (isSecondaryWindow()) return
  if (typeof window === 'undefined' || typeof document === 'undefined') return
  if (initialized) return
  initialized = true

  applyFontScale(getPreferences().fontScale)

  window.addEventListener('keydown', (e: KeyboardEvent) => {
    // Ctrl (not Alt/Meta) — matches macOS ⌘ shortcuts adapted to Windows.
    if (!e.ctrlKey || e.altKey || e.metaKey) return
    if (e.key === '=' || e.key === '+') {
      e.preventDefault()
      nudgeFontScale(KEY_STEP)
    } else if (e.key === '-' || e.key === '_') {
      e.preventDefault()
      nudgeFontScale(-KEY_STEP)
    } else if (e.key === '0') {
      e.preventDefault()
      setPreferences({ fontScale: FONT_SCALE_DEFAULT })
    }
  })

  // Keep the root rem multiplier in sync with the persisted scale on EVERY change —
  // same-window writes (setPreferences) and cross-window 'storage' refreshes both
  // fan out through the preferences listener set. applyFontScale no-ops in
  // secondary windows and skips redundant writes, so this is cheap.
  onPreferencesChange((p) => applyFontScale(p.fontScale))
}
