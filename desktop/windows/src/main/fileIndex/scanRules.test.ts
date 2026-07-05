import { describe, it, expect } from 'vitest'
import { shouldVisitDir, shouldIndexFile, MAX_DEPTH, MAX_FILE_SIZE } from './scanRules'

describe('shouldVisitDir', () => {
  it('skips noise directories', () => {
    expect(shouldVisitDir('node_modules', 1)).toBe(false)
    expect(shouldVisitDir('.git', 1)).toBe(false)
    expect(shouldVisitDir('__pycache__', 1)).toBe(false)
    expect(shouldVisitDir('.Trash', 1)).toBe(false)
  })
  it('visits normal dirs within depth', () => {
    expect(shouldVisitDir('src', 1)).toBe(true)
    expect(shouldVisitDir('src', MAX_DEPTH)).toBe(true)
  })
  it('stops past max depth', () => {
    expect(shouldVisitDir('src', MAX_DEPTH + 1)).toBe(false)
  })
})

describe('shouldIndexFile', () => {
  it('accepts files up to the size cap', () => {
    expect(shouldIndexFile(0)).toBe(true)
    expect(shouldIndexFile(MAX_FILE_SIZE)).toBe(true)
  })
  it('rejects oversized files', () => {
    expect(shouldIndexFile(MAX_FILE_SIZE + 1)).toBe(false)
  })
})
