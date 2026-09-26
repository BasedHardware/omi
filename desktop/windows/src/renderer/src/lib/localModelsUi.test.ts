import { describe, it, expect } from 'vitest'
import { formatBytes, downloadPct, actionLabel, ramWarning } from './localModelsUi'
import type { ModelEntry } from '../../../shared/types'

const entry = (over: Partial<ModelEntry> = {}): ModelEntry => ({
  id: 'x',
  label: 'X',
  repo: 'o/r',
  file: 'x.gguf',
  revision: 'c',
  sizeBytes: 1,
  minRamGb: 6,
  vision: false,
  ...over
})

describe('formatBytes', () => {
  it('renders GB with one decimal', () => expect(formatBytes(4_683_074_240)).toBe('4.7 GB'))
  it('renders MB under a gig', () => expect(formatBytes(812_000_000)).toBe('812 MB'))
  it('treats zero/negative/NaN as 0 B', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(-5)).toBe('0 B')
    expect(formatBytes(Number.NaN)).toBe('0 B')
  })
})

describe('downloadPct', () => {
  it('computes a rounded percentage', () => expect(downloadPct(50, 200)).toBe(25))
  it('clamps to 100', () => expect(downloadPct(999, 200)).toBe(100))
  it('guards divide-by-zero / unknown total', () => {
    expect(downloadPct(10, 0)).toBe(0)
    expect(downloadPct(10, Number.NaN)).toBe(0)
    expect(downloadPct(-1, 5)).toBe(0)
  })
})

describe('actionLabel', () => {
  it('maps install state to a label', () => {
    expect(actionLabel('installed')).toBe('Installed')
    expect(actionLabel('partial')).toBe('Resume')
    expect(actionLabel('absent')).toBe('Download')
  })
})

describe('ramWarning', () => {
  it('is silent when device RAM is unknown (never guesses)', () => {
    expect(ramWarning(entry({ minRamGb: 8 }), undefined)).toBeUndefined()
  })
  it('is silent when RAM is sufficient', () => {
    expect(ramWarning(entry({ minRamGb: 6 }), 16)).toBeUndefined()
  })
  it('warns when below the floor', () => {
    const w = ramWarning(entry({ minRamGb: 8 }), 4)
    expect(w).toBeTruthy()
    expect(w).toContain('8 GB')
  })
})
