import { describe, it, expect } from 'vitest'
import { shouldVisitDir, shouldIndexFile, SKIP_DIRS, MAX_DEPTH, MAX_FILE_SIZE } from './scanRules'

const GENERATED_AND_DEPENDENCY_DIRS = [
  '.Trash',
  'node_modules',
  '.git',
  '__pycache__',
  '.venv',
  'venv',
  '.cache',
  '.npm',
  '.yarn',
  'Pods',
  'DerivedData',
  '.build',
  'build',
  'dist',
  '.next',
  '.nuxt',
  'target',
  'vendor',
  'Library',
  '.local',
  '.cargo',
  '.rustup'
] as const

describe('shouldVisitDir', () => {
  it.each(GENERATED_AND_DEPENDENCY_DIRS)('skips ignored directory %s', (name) => {
    expect(SKIP_DIRS.has(name)).toBe(true)
    expect(shouldVisitDir(name, 1)).toBe(false)
  })

  it.each(['Node_Modules', '.GIT', '__PYCACHE__', 'DERIVEDDATA', '.NEXT', 'LIBRARY'])(
    'skips %s case-insensitively on Windows paths',
    (name) => {
      expect(shouldVisitDir(name, 1)).toBe(false)
    }
  )

  it('does not skip similarly named project directories', () => {
    expect(shouldVisitDir('build-tools', 1)).toBe(true)
    expect(shouldVisitDir('vendor-notes', 1)).toBe(true)
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
