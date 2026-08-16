// The halo's APPEARANCE — the only file that knows what a halo means.
//
// Everything else in main/glow/ is deliberately colour-agnostic: glowWindow.ts
// draws "a halo around the active window" and glowGeometry.ts computes where. Add
// a new look (a recording indicator, a listening cue) by adding a preset here —
// no window, geometry, gate or renderer code has to move.
import type { GlowPaint, GlowPresetName } from '../../shared/types'

/**
 * ⚠ THESE ALPHAS ARE THE APPROVED BASELINE — the user picked this faintness over a
 * brighter variant, verbatim: "it had a bright outline then switched to a faint
 * outline, i liked the faint one better". Do not push intensity, alpha or
 * brightness back up in a later tuning pass. This fires when an AI *thinks* the
 * user is distracted, so an ambient hint is the goal, not an alarm — when in doubt
 * between two intensities, ship the fainter.
 *
 * `intensity` is the envelope's peak opacity (0.85). The per-layer alphas of the
 * shadow stack live in glow.css and are shared by every preset, so both presets are
 * automatically the same faintness — green can never drift brighter than red.
 */
export const GLOW_PRESETS: Record<GlowPresetName, GlowPaint> = {
  // The Focus assistant judged the user distracted.
  distracted: {
    hues: ['239 68 68', '248 113 113', '220 38 38'],
    intensity: 0.85
  },
  // The Focus assistant saw them come back to the work.
  focused: {
    hues: ['34 197 94', '74 222 128', '16 185 129'],
    intensity: 0.85
  }
}

/**
 * `Object.hasOwn`, NOT `name in GLOW_PRESETS`: `in` walks the prototype chain, so
 * `'constructor' in GLOW_PRESETS` is true. A renderer calling
 * `omiGlow.trigger('constructor')` would then pass this guard, and
 * `GLOW_PRESETS['constructor']` — the `Object` function — would be handed to
 * `webContents.send`, which throws "An object could not be cloned" INSIDE an
 * `ipcMain.on` handler: an uncaught exception in the main process. Matters more
 * once the Focus assistant feeds a model-derived verdict string in here.
 */
export function isGlowPreset(name: unknown): name is GlowPresetName {
  return typeof name === 'string' && Object.hasOwn(GLOW_PRESETS, name)
}
