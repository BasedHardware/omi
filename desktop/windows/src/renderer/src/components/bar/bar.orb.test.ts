import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

// Guards the "one persistent orb" anti-flash fix. The bar's logo used to flash on
// expand because the pill and the panel header each mounted their OWN <Orb>, which
// crossfaded (and the fresh mount re-initialized its WebGL canvas → blank frames).
// The fix is a single persistent orb hoisted above both content layers, moved
// between its pill seat and panel-header seat by a transform-only FLIP. Two ways
// to reintroduce the flash: (1) add a second <Orb>, (2) animate the orb's size
// (Orb.tsx rebuilds the animator when cssW/cssH/preset change). Both are pinned.
const here = path.dirname(fileURLToPath(import.meta.url))
const read = (f: string): string => readFileSync(path.join(here, f), 'utf8')

describe('bar orb persistence (anti-flash)', () => {
  it('renders exactly ONE Orb mount — a second orb brings back the crossfade/reinit flash', () => {
    const mounts = (read('BarApp.tsx').match(/<Orb\b/g) ?? []).length
    expect(mounts).toBe(1)
  })

  it('the persistent orb moves by transform only — never by size (a size change rebuilds the WebGL animator = a blink)', () => {
    const css = read('bar.css')
    const transitions = [...css.matchAll(/\.bar-orb-wrap[^{]*\{([^}]*)\}/g)]
      .map((m) => m[1].match(/transition:\s*([^;]*)/)?.[1]?.trim() ?? '')
      .filter(Boolean)
    // The animating rules (base pill seat + expanded panel seat); reduced-motion
    // sets transition:none and is intentionally excluded.
    const animating = transitions.filter((t) => t !== 'none')
    expect(animating.length).toBeGreaterThanOrEqual(2)
    for (const t of animating) {
      expect(t).toMatch(/transform/)
      expect(t).not.toMatch(/\b(width|height)\b/)
    }
  })
})
