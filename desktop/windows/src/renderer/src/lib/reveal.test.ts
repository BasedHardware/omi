import { describe, expect, it } from 'vitest'
import { revealStep } from './reveal'

describe('revealStep', () => {
  it('makes bounded progress for a pending backlog', () => {
    expect(revealStep(0, 16)).toBe(0)
    expect(revealStep(5, 0)).toBeGreaterThanOrEqual(1)
    expect(revealStep(5, 16)).toBeLessThanOrEqual(5)
  })

  it('accelerates to drain a large backlog', () => {
    expect(revealStep(800, 16)).toBe(100)
    expect(revealStep(100, 140)).toBe(28)
  })
})
