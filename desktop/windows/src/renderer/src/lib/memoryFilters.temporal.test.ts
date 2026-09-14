import { describe, expect, it } from 'vitest'
import type { Memory } from '../hooks/useMemories'
import {
  canUseMemory,
  currencyBandLabel,
  formatMemoryAssessmentDate,
  formatMemoryEvidenceDate,
  isUsefulNowMemory,
  memoryCurrencyBand,
  memoryUseSuppressed
} from './memoryFilters'

const memory = (overrides: Partial<Memory> = {}): Memory => ({
  id: 'memory-1',
  uid: 'user-1',
  content: 'A memory',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  ...overrides
})

describe('memory temporal projection', () => {
  it('keeps current, fading, and unknown rows in useful-now', () => {
    expect(isUsefulNowMemory(memory({ currency_band: 'current' }))).toBe(true)
    expect(isUsefulNowMemory(memory({ currency_band: 'fading' }))).toBe(true)
    expect(isUsefulNowMemory(memory())).toBe(true)
    expect(isUsefulNowMemory(memory({ currency_band: 'stale' }))).toBe(false)
    expect(memoryCurrencyBand(memory({ currency_band: 'history' }))).toBe('stale')
    expect(currencyBandLabel(memory({ currency_band: 'history' }))).toBe('Historical')
    expect(isUsefulNowMemory(memory({ currency_band: 'history' }))).toBe(false)
  })

  it('does not invent currentness from ordinary timestamps', () => {
    const legacy = memory({ updated_at: '2026-09-13T00:00:00Z' })
    expect(memoryCurrencyBand(legacy)).toBe('unknown')
    expect(currencyBandLabel(legacy)).toBe('Currentness unknown')
    expect(formatMemoryAssessmentDate(legacy)).toBeNull()
  })

  it('keeps evidence and assessment timestamps distinct', () => {
    const assessed = memory({
      currency_band: 'fading',
      as_of: '2026-09-12T10:30:00Z',
      belief_computed_at: '2026-09-13T10:30:00Z'
    })
    const evidenceDate = formatMemoryEvidenceDate(assessed)
    const assessmentDate = formatMemoryAssessmentDate(assessed)
    expect(evidenceDate).toContain('12')
    expect(assessmentDate).toContain('13')
    expect(assessmentDate).not.toBe(evidenceDate)
    expect(currencyBandLabel(assessed)).toBe('Fading')
  })

  it('reads the worker-confirmed suppression state without treating missing state as suppressed', () => {
    expect(memoryUseSuppressed(memory())).toBe(false)
    expect(memoryUseSuppressed(memory({ arguments: { memory_use: { suppressed: true } } }))).toBe(
      true
    )
    expect(memoryUseSuppressed(memory({ arguments: { memory_use: { suppressed: false } } }))).toBe(
      false
    )
  })

  it('only exposes use feedback for active, non-superseded rows', () => {
    expect(canUseMemory(memory({ status: 'active', valid_to: '2026-09-01T00:00:00Z' }))).toBe(true)
    expect(
      canUseMemory(memory({ status: 'active', arguments: { memory_use: { suppressed: true } } }))
    ).toBe(true)

    expect(canUseMemory(memory({ status: 'active', invalid_at: '2026-09-02T00:00:00Z' }))).toBe(
      false
    )
    expect(canUseMemory(memory({ status: 'active', superseded_by: 'memory-2' }))).toBe(false)
    for (const status of ['superseded', 'tombstoned', 'purged', 'unknown'] as const) {
      expect(canUseMemory(memory({ status }))).toBe(false)
    }
  })
})
