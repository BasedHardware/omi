import { describe, it, expect } from 'vitest'
import { categorizeExtension } from './fileTypes'

describe('categorizeExtension', () => {
  it('maps known extensions to categories (case- and dot-insensitive)', () => {
    expect(categorizeExtension('pdf')).toBe('document')
    expect(categorizeExtension('.PDF')).toBe('document')
    expect(categorizeExtension('ts')).toBe('code')
    expect(categorizeExtension('png')).toBe('image')
    expect(categorizeExtension('mp4')).toBe('media')
    expect(categorizeExtension('zip')).toBe('archive')
    expect(categorizeExtension('lnk')).toBe('application')
  })
  it('falls back to "other" for unknown/empty', () => {
    expect(categorizeExtension('xyz')).toBe('other')
    expect(categorizeExtension('')).toBe('other')
  })
})
