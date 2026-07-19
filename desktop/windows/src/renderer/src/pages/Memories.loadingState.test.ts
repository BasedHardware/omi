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

  it('fades the canvas in once BrainGraph reports it is ready', () => {
    expect(source).toContain('onReady={() => setCanvasLive(true)}')
    expect(source).toMatch(/graphReady\s*\?\s*'opacity-100'\s*:\s*'opacity-0'/)
  })

  it('gates the reveal on BOTH a live canvas AND settled data (not canvas creation alone)', () => {
    expect(source).toMatch(/const normalReady = canvasLive && settled/)
    expect(source).toMatch(/const graphReady = normalReady \|\| revealForced/)
  })

  it('bounds the placeholder with a FULL reveal so a chunk/canvas failure cannot hang it forever', () => {
    // Must force the whole reveal (revealForced feeds graphReady), not just the
    // data-`settled` axis: if the lazy 3D chunk fails, onReady never fires and
    // canvasLive would stay false, leaving the placeholder on top of the fallback.
    expect(source).toMatch(/setTimeout\(\(\) => setRevealForced\(true\)/)
    expect(source).toMatch(/const graphReady = normalReady \|\| revealForced/)
  })

  it('keeps the placeholder off-brand-color free', () => {
    expect(source).not.toMatch(/purple|violet/i)
  })
})
