import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const here = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(here, 'Memories.tsx'), 'utf8')

// The brain-map canvas needs a real WebGL context, so it can't be rendered in
// jsdom — Memories.performance.test.ts already establishes the pattern of
// asserting on the page source directly for this component.
describe('Memories brain-map loading state', () => {
  it('shows a placeholder immediately while the graph loads, not a blank box', () => {
    expect(source).toContain('Building your memory map')
    expect(source).toMatch(/graphReady\s*\?\s*'pointer-events-none opacity-0'\s*:\s*'opacity-100'/)
  })

  it('reveals on a PAINTED CONTENT FRAME (onPresentable), not on canvas creation', () => {
    // The load-bearing fix: gate the crossfade on BrainGraph having actually
    // painted the laid-out graph (onPresentable), not on the WebGL context merely
    // existing. Revealing on canvas creation uncovered the raw warmup (placeholder
    // dot, blank card, fly-in's first frames) — Chris's "dot → blackout → fly-in".
    expect(source).toMatch(/onPresentable={\(\) => setPresentable\(true\)}/)
    expect(source).toMatch(/const graphReady = presentable \|\| revealForced/)
  })

  it('bounds the placeholder with a FULL reveal so a chunk/canvas failure cannot hang it forever', () => {
    // Must force the whole reveal (revealForced feeds graphReady): if the lazy 3D
    // chunk / GPU is dead there is no content frame to fire onPresentable, so a
    // timer forces the reveal (and BrainGraph's fallback paths fire onPresentable
    // directly). Long delay so a slow-but-succeeding load is never pre-empted.
    expect(source).toMatch(/setTimeout\(\(\) => setRevealForced\(true\)/)
    expect(source).toMatch(/const graphReady = presentable \|\| revealForced/)
  })

  it('keeps the placeholder off-brand-color free', () => {
    expect(source).not.toMatch(/purple|violet/i)
  })
})
