import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const here = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(here, 'Memories.tsx'), 'utf8')

describe('Memories WebGL performance guards', () => {
  it('keeps the BrainGraph canvas out of blurred glass surfaces', () => {
    const brainGraphPane = source.match(
      /<div className="mx-auto mb-6 max-w-4xl">[\s\S]*?<BrainGraph[\s\S]*?<\/div>\s*<\/div>/
    )

    expect(brainGraphPane?.[0]).toContain('bg-black/40')
    expect(brainGraphPane?.[0]).not.toMatch(/className="[^"]*(?:surface-card|glass)/)
  })

  it('renders the Memories BrainGraph on demand instead of every frame', () => {
    expect(source).toContain('frameLoop="demand"')
  })
})
