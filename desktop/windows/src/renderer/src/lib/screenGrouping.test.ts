import { describe, it, expect } from 'vitest'
import { groupFrames, budgetSegments, type ScreenSegment } from './screenGrouping'

const f = (ts: number, app: string, windowTitle: string, ocrText: string) => ({
  ts,
  app,
  windowTitle,
  processName: app.toLowerCase() + '.exe',
  ocrText
})

describe('groupFrames', () => {
  it('groups consecutive frames of the same app/window and dedupes identical OCR', () => {
    const segs = groupFrames([
      f(1, 'Code', 'plan.md', 'writing the plan'),
      f(2, 'Code', 'plan.md', 'writing the plan'), // dup OCR → collapsed
      f(3, 'Code', 'plan.md', 'now adding tests'),
      f(4, 'Chrome', 'Docs', 'reading the api docs')
    ])
    expect(segs.length).toBe(2)
    expect(segs[0]).toMatchObject({ app: 'Code', windowTitle: 'plan.md' })
    expect(segs[0].text).toContain('writing the plan')
    expect(segs[0].text).toContain('now adding tests')
    expect(segs[1]).toMatchObject({ app: 'Chrome', windowTitle: 'Docs' })
  })
  it('drops empty-OCR frames', () => {
    expect(groupFrames([f(1, 'Code', 'x', '   ')])).toEqual([])
  })
})

describe('budgetSegments', () => {
  it('caps total text at the budget, keeping whole segments', () => {
    const segs: ScreenSegment[] = [
      { app: 'A', windowTitle: 'a', text: 'x'.repeat(60) },
      { app: 'B', windowTitle: 'b', text: 'y'.repeat(60) }
    ]
    const out = budgetSegments(segs, 80)
    expect(out.length).toBe(1)
    expect(out[0].app).toBe('A')
  })
})
