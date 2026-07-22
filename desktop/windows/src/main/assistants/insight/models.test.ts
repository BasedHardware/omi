import { describe, expect, it } from 'vitest'
import { PHASE1_TOOL, PHASE2_TOOL, parseProvideAdvice, parseScreenshotId } from './models'

describe('tool declarations', () => {
  it('Phase 1 offers execute_sql / request_screenshot / no_advice, re-grounded to rewind_frames', () => {
    const names = PHASE1_TOOL.function_declarations.map((d) => d.name)
    expect(names).toEqual(['execute_sql', 'request_screenshot', 'no_advice'])
    const sql = PHASE1_TOOL.function_declarations[0]
    expect(sql.description).toContain('rewind_frames')
    expect(sql.description).not.toContain('screenshots table')
    expect(sql.parameters.required).toEqual(['query'])
  })

  it('Phase 2 offers execute_sql / provide_advice / no_advice; reasoning is the only optional provide_advice arg', () => {
    const names = PHASE2_TOOL.function_declarations.map((d) => d.name)
    expect(names).toEqual(['execute_sql', 'provide_advice', 'no_advice'])
    const advice = PHASE2_TOOL.function_declarations[1]
    expect(advice.parameters.required).not.toContain('reasoning')
    expect(advice.parameters.required).toContain('advice')
    expect(advice.parameters.properties.category.enum).toEqual([
      'productivity',
      'communication',
      'learning',
      'other'
    ])
  })
})

describe('parseScreenshotId', () => {
  it('parses integer, numeric string, and truncates a float', () => {
    expect(parseScreenshotId({ screenshot_id: 42 })).toBe(42)
    expect(parseScreenshotId({ screenshot_id: '77' })).toBe(77)
    expect(parseScreenshotId({ screenshot_id: 12.9 })).toBe(12)
  })
  it('returns null for junk or missing', () => {
    expect(parseScreenshotId({})).toBeNull()
    expect(parseScreenshotId({ screenshot_id: 'abc' })).toBeNull()
    expect(parseScreenshotId({ screenshot_id: null })).toBeNull()
  })
})

describe('parseProvideAdvice', () => {
  it('maps args with Mac fallbacks', () => {
    const insight = parseProvideAdvice({
      advice: 'Mask the token before sharing',
      headline: 'Token visible',
      category: 'productivity',
      source_app: 'Terminal',
      confidence: 0.92,
      context_summary: 'ctx',
      current_activity: 'act'
    })
    expect(insight.advice).toBe('Mask the token before sharing')
    expect(insight.headline).toBe('Token visible')
    expect(insight.category).toBe('productivity')
    expect(insight.confidence).toBe(0.92)
    expect(insight.reasoning).toBeNull()
  })

  it('falls back: bad category → other, unparseable confidence → 0.5, missing strings → ""', () => {
    const insight = parseProvideAdvice({ category: 'nonsense', confidence: 'xx' })
    expect(insight.category).toBe('other')
    expect(insight.confidence).toBe(0.5)
    expect(insight.advice).toBe('')
    expect(insight.sourceApp).toBe('')
    expect(insight.headline).toBeNull()
  })

  it('coerces a numeric-string confidence', () => {
    expect(parseProvideAdvice({ confidence: '0.88' }).confidence).toBe(0.88)
  })
})
