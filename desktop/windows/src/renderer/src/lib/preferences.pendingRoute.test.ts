import { describe, it, expect } from 'vitest'
import { setPendingRoute, consumePendingRoute } from './preferences'

describe('pending route handoff', () => {
  it('returns the route once, then null', () => {
    setPendingRoute('/tasks')
    expect(consumePendingRoute()).toBe('/tasks')
    // Second consume is empty — the shell must not re-navigate on remount.
    expect(consumePendingRoute()).toBe(null)
  })

  it('is null by default', () => {
    expect(consumePendingRoute()).toBe(null)
  })
})
