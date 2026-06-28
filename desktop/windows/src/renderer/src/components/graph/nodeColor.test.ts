import { describe, it, expect } from 'vitest'
import { nodeColor } from './nodeColor'

describe('nodeColor', () => {
  it('maps node types to the macOS palette', () => {
    expect(nodeColor('concept', false)).toBe('#0a84ff') // blue
    expect(nodeColor('thing', false)).toBe('#a855f7') // purple
    expect(nodeColor('person', false)).toBe('#22d3d3') // cyan
    expect(nodeColor('place', false)).toBe('#00ff9e') // mint
    expect(nodeColor('organization', false)).toBe('#ff9f0a') // orange
  })

  it('returns white for the fixed (user) node regardless of type', () => {
    expect(nodeColor('person', true)).toBe('#ffffff')
    expect(nodeColor('thing', true)).toBe('#ffffff')
  })

  it('defaults unknown types to blue', () => {
    expect(nodeColor('mystery', false)).toBe('#0a84ff')
  })
})
