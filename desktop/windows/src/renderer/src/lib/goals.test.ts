import { describe, it, expect } from 'vitest'
import { buildGoalPrompt, parseTargetValue } from './goals'

describe('buildGoalPrompt', () => {
  it('includes the apps the user works with', () => {
    const p = buildGoalPrompt(['Cursor', 'Canva', 'ChatGPT'])
    expect(p).toContain('Cursor, Canva, ChatGPT')
    expect(p).toContain('measurable number')
  })

  it('trims and drops blank app names', () => {
    const p = buildGoalPrompt(['  Figma  ', '', '   '])
    expect(p).toContain('I work with these apps and tools: Figma.')
  })

  it('omits the apps clause when none are known', () => {
    const p = buildGoalPrompt([])
    expect(p).not.toContain('I work with these apps')
    expect(p.startsWith('Suggest ONE')).toBe(true)
  })
})

describe('parseTargetValue', () => {
  it('extracts the first number from the goal text', () => {
    expect(parseTargetValue('Ship 2 features per week')).toBe(2)
  })

  it('handles decimals', () => {
    expect(parseTargetValue('Run 5.5 km every morning')).toBe(5.5)
  })

  it('strips thousands separators', () => {
    expect(parseTargetValue('Write 1,000 words a day')).toBe(1000)
  })

  it('defaults to 1 when there is no number', () => {
    expect(parseTargetValue('Be more productive and focused every day')).toBe(1)
  })

  it('defaults to 1 for a zero target', () => {
    expect(parseTargetValue('Reach 0 unread emails')).toBe(1)
  })
})
