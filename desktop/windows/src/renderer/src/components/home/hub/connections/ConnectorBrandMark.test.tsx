// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { render, cleanup } from '@testing-library/react'
import { ConnectorBrandMark } from './ConnectorBrandMark'

afterEach(cleanup)

// Guards the connector marks that used placeholder / hand-drawn artwork instead of the
// real brand logo (parity with macOS's ConnectorBrandIcon):
//  - ChatGPT rendered a lossy retype of the OpenAI knot with a visible notch ("chip").
//  - Notion rendered a hand-drawn three-stroke "N" that looked like a letter avatar.
//  - Claude rendered a hand-drawn twelve-ray star, not the real Anthropic spark.
//  - Gemini rendered a neutral lucide Sparkles glyph, not the real Gemini logo.
describe('ConnectorBrandMark', () => {
  it('renders ChatGPT as the official OpenAI knot path (no chipped retype)', () => {
    const { container } = render(<ConnectorBrandMark brand="chatgpt" />)
    const path = container.querySelector('path')
    const d = path?.getAttribute('d') ?? ''
    // The official path carries full-precision coordinates; the chipped version was a
    // two-decimal retype whose central-lobe segment collapsed to "2.6-1.5 2.6 1.5v3".
    expect(d.startsWith('M22.2819')).toBe(true)
    expect(d).not.toContain('2.6-1.5 2.6 1.5v3')
  })

  it('renders Notion as the real two-tone logomark, not a plain letter', () => {
    const { container } = render(<ConnectorBrandMark brand="notion" />)
    const svg = container.querySelector('svg')
    expect(svg?.getAttribute('viewBox')).toBe('0 0 100 100')
    const paths = container.querySelectorAll('path')
    // Real logo = a white page path plus a black border/"N" path. The placeholder was a
    // single stroked (unfilled) three-line "N" over a <rect>.
    expect(paths.length).toBe(2)
    const fills = Array.from(paths).map((p) => p.getAttribute('fill'))
    expect(fills).toContain('#fff')
    expect(fills).toContain('#000')
    expect(container.querySelector('rect')).toBeNull()
  })

  it('renders Claude as the official Anthropic spark path, not a ray star', () => {
    const { container } = render(<ConnectorBrandMark brand="claude" />)
    const path = container.querySelector('path')
    // The real spark is a single filled path in the clay brand colour; the placeholder
    // was twelve stroked <line> rays with no <path>.
    expect(path?.getAttribute('fill')).toBe('#D97757')
    expect(path?.getAttribute('d')?.startsWith('m4.7144')).toBe(true)
    expect(container.querySelector('line')).toBeNull()
  })

  it('renders Gemini as the real bundled logo image, not a lucide glyph', () => {
    const { container } = render(<ConnectorBrandMark brand="gemini" />)
    // PNG brands render through BrandImage as an <img>; the placeholder was an inline svg.
    const img = container.querySelector('img')
    expect(img).not.toBeNull()
    expect(img?.getAttribute('src') ?? '').toContain('gemini')
  })
})
