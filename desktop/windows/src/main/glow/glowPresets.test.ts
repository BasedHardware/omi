import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { GLOW_PRESETS, isGlowPreset } from './glowPresets'

describe('isGlowPreset', () => {
  it('accepts the real presets', () => {
    expect(isGlowPreset('distracted')).toBe(true)
    expect(isGlowPreset('focused')).toBe(true)
  })

  it('rejects non-strings and unknown names', () => {
    expect(isGlowPreset(undefined)).toBe(false)
    expect(isGlowPreset(null)).toBe(false)
    expect(isGlowPreset(42)).toBe(false)
    expect(isGlowPreset('nope')).toBe(false)
  })

  // The guard used `name in GLOW_PRESETS`, and `in` walks the prototype chain — so
  // `omiGlow.trigger('constructor')` passed it, GLOW_PRESETS['constructor'] resolved
  // to the `Object` FUNCTION, and webContents.send() threw "An object could not be
  // cloned" inside an ipcMain.on handler: an uncaught exception in the MAIN process.
  // The renderer picks the preset name, and soon a model-derived verdict string will.
  it('rejects Object.prototype keys (would crash the main process on send)', () => {
    for (const key of ['constructor', 'toString', 'hasOwnProperty', '__proto__', 'valueOf']) {
      expect(isGlowPreset(key), `${key} must not be treated as a preset`).toBe(false)
    }
  })
})

describe('GLOW_PRESETS', () => {
  // The user was shown a bright variant and a faint one and picked the faint one:
  // "i liked the faint one better... the second one looked really good". Both presets
  // share ONE shadow stack in glow.css and differ only in hue, so green can never
  // drift brighter than the approved red. This pins that they stay in lockstep.
  it('keeps every preset at the same approved intensity', () => {
    const intensities = Object.values(GLOW_PRESETS).map((p) => p.intensity)
    expect(new Set(intensities).size).toBe(1)
    expect(intensities[0]).toBeLessThanOrEqual(0.85)
  })

  it('gives every preset exactly three hues', () => {
    for (const [name, paint] of Object.entries(GLOW_PRESETS)) {
      expect(paint.hues, name).toHaveLength(3)
    }
  })
})

// A CSS guard, living with the code it protects.
//
// There is ONE renderer bundle and ONE index.html for EVERY window (main, bar,
// insight-toast, capture, glow), so glow.css is loaded everywhere — but only the
// halo window ever gets `body.glow-body`. `pointer-events` is INHERITED, so putting
// it on a bare `html` selector propagates it to <body>, #root and every descendant
// of the MAIN window: the sidebar, chat input, buttons and scrolling all silently
// stop responding to the mouse. An audit caught exactly that before it shipped.
// Screenshot verification cannot catch it — the pixels look perfect.
describe('glow.css scoping (main-window input killer)', () => {
  const css = readFileSync(new URL('../../renderer/src/components/glow/glow.css', import.meta.url), 'utf8')

  it('never applies pointer-events in a rule that includes a bare `html` selector', () => {
    // Each rule = "selector { body }". Any rule whose selector list mentions `html`
    // must not set pointer-events, or it escapes the glow window.
    const rules = [...css.matchAll(/([^{}]+)\{([^}]*)\}/g)]
    const offenders = rules
      .filter(([, sel, body]) => /(^|,)\s*html\b/.test(sel) && /pointer-events/.test(body))
      .map(([, sel]) => sel.trim())
    expect(offenders, `pointer-events must be scoped to body.glow-body, not html`).toEqual([])
  })

  it('still disables pointer events on the glow body itself', () => {
    expect(css).toMatch(/body\.glow-body\s*\{[^}]*pointer-events:\s*none/)
  })
})
