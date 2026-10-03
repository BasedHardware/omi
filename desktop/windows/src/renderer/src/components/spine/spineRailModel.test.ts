import { describe, expect, it } from 'vitest'
import {
  HOT_THRESHOLD,
  LABELLED_HOURS,
  RENDERED_HOURS,
  hourDensity,
  railFooter,
  railHeadline
} from './spineRailModel'

describe('RENDERED_HOURS', () => {
  it('runs the same direction as the newest-first list', () => {
    // 23 at the top, 0 at the bottom. Reversed, the eye would travel backwards
    // through the day while the list beside it travels forwards.
    expect(RENDERED_HOURS[0]).toBe(23)
    expect(RENDERED_HOURS[RENDERED_HOURS.length - 1]).toBe(0)
    expect(RENDERED_HOURS.length).toBe(24)
  })
})

describe('hourDensity', () => {
  it('normalises against the day, not the account', () => {
    const counts = new Array<number>(24).fill(0)
    counts[9] = 50
    counts[14] = 100
    const density = hourDensity(counts)
    // A quiet day and a busy day both use their own peak, so an ordinary day
    // does not render as a blank column next to one all-night capture session.
    expect(density[14]).toBe(1)
    expect(density[9]).toBe(0.5)
    expect(density[3]).toBe(0)
  })

  it('returns a flat column for a day with no capture instead of dividing by zero', () => {
    expect(hourDensity(new Array<number>(24).fill(0))).toEqual(new Array<number>(24).fill(0))
  })

  it('marks an hour hot only at or above the threshold', () => {
    const counts = new Array<number>(24).fill(0)
    counts[9] = 6
    counts[10] = 5
    counts[11] = 10
    const density = hourDensity(counts)
    expect(density[9] >= HOT_THRESHOLD).toBe(true)
    expect(density[10] >= HOT_THRESHOLD).toBe(false)
  })
})

describe('railHeadline', () => {
  it('shows an em dash and counting for a day not read yet', () => {
    // Rendering 0 here would claim the user captured nothing on a day that is
    // still being counted.
    expect(railHeadline(null)).toEqual({ value: '—', caption: 'counting screen moments' })
  })

  it('shows zero for a day that was read and held nothing', () => {
    expect(railHeadline(0)).toEqual({ value: '0', caption: 'screen moments' })
  })

  it('agrees with itself on the singular', () => {
    expect(railHeadline(1)).toEqual({ value: '1', caption: 'screen moment' })
  })

  it('groups thousands so a busy day stays readable', () => {
    expect(railHeadline(4213).value).toBe('4,213')
  })
})

describe('railFooter', () => {
  it('is absent when the day held no conversation', () => {
    expect(railFooter(0)).toBeNull()
  })

  it('reads naturally at one and many', () => {
    expect(railFooter(1)).toBe('1 conversation')
    expect(railFooter(12)).toBe('12 conversations')
  })
})

describe('LABELLED_HOURS', () => {
  it('labels the quarters of the day', () => {
    expect([...LABELLED_HOURS].sort((a, b) => a - b)).toEqual([0, 6, 12, 18])
  })
})
