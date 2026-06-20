import { describe, it, expect } from 'vitest'
import { nodeColor } from './nodeColor'

const PURPLE = '#a855f7'
const BLUE = '#0a84ff'
const ORANGE = '#ff9f0a'

describe('nodeColor', () => {
  it('colors apps purple (onboarding app_ ids, local-KG :app / app type)', () => {
    expect(nodeColor('thing', false, 'app_slack')).toBe(PURPLE)
    expect(nodeColor('app', false, 'slack:app')).toBe(PURPLE)
    expect(nodeColor('app', false)).toBe(PURPLE)
  })

  it('colors languages blue (language_ ids)', () => {
    expect(nodeColor('concept', false, 'language_en')).toBe(BLUE)
    expect(nodeColor('concept', false, 'language_es')).toBe(BLUE)
  })

  it('colors everything else orange (people, places, orgs, bare concepts, unknown)', () => {
    expect(nodeColor('person', false, 'n1')).toBe(ORANGE)
    expect(nodeColor('place', false, 'n2')).toBe(ORANGE)
    expect(nodeColor('organization', false, 'n3')).toBe(ORANGE)
    expect(nodeColor('concept', false, 'topic_typescript')).toBe(ORANGE)
    expect(nodeColor('mystery', false, 'whatever')).toBe(ORANGE)
    expect(nodeColor('concept', false)).toBe(ORANGE)
  })

  it('returns white for the fixed (user) node regardless of type or id', () => {
    expect(nodeColor('person', true, 'user')).toBe('#ffffff')
    expect(nodeColor('app', true, 'app_slack')).toBe('#ffffff')
  })
})
