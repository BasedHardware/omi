import { describe, it, expect } from 'vitest'
import { nodeColor } from './nodeColor'

describe('nodeColor', () => {
  it('maps node types to the palette (macOS scheme, de-purpled)', () => {
    expect(nodeColor('concept', false)).toBe('#0a84ff') // blue
    expect(nodeColor('thing', false)).toBe('#ff375f') // pink — never purple (INV-UI-1)
    expect(nodeColor('person', false)).toBe('#22d3d3') // cyan
    expect(nodeColor('place', false)).toBe('#00ff9e') // mint
    expect(nodeColor('organization', false)).toBe('#ff9f0a') // orange
  })

  it('never returns a purple hue for any node type', () => {
    for (const t of ['concept', 'thing', 'person', 'place', 'organization', 'mystery']) {
      const hex = nodeColor(t, false)
      const r = parseInt(hex.slice(1, 3), 16)
      const g = parseInt(hex.slice(3, 5), 16)
      const b = parseInt(hex.slice(5, 7), 16)
      // Purple reads as blue+red both dominating green. Pink/red keeps
      // blue clearly below red; blue keeps red clearly below blue.
      const isPurple = r > g + 40 && b > g + 40 && Math.abs(r - b) < 90
      expect(isPurple, `${t} → ${hex} must not be purple`).toBe(false)
    }
  })

  it('returns white for the fixed (user) node regardless of type', () => {
    expect(nodeColor('person', true)).toBe('#ffffff')
    expect(nodeColor('thing', true)).toBe('#ffffff')
  })

  it('defaults unknown types to blue', () => {
    expect(nodeColor('mystery', false)).toBe('#0a84ff')
  })
})
