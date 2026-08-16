import { describe, it, expect } from 'vitest'
import {
  shouldVisitDir,
  shouldIndexFile,
  isHiddenEntry,
  pathsToDelete,
  SKIP_DIRS,
  MAX_DEPTH,
  MAX_FILE_SIZE
} from './scanRules'

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
  it('skips build/cache outputs ported from macOS', () => {
    for (const d of ['dist', 'build', 'target', 'vendor', '.venv', 'venv', '.cache', 'Pods']) {
      expect(shouldVisitDir(d, 1)).toBe(false)
    }
  })
  it('skips Windows/.NET build + cache analogs', () => {
    for (const d of ['obj', 'bin', 'packages', '$RECYCLE.BIN', 'OneDriveTemp']) {
      expect(shouldVisitDir(d, 1)).toBe(false)
    }
  })
  it('skips any dot-directory even when not in the skip-list', () => {
    expect(shouldVisitDir('.vscode', 1)).toBe(false)
    expect(shouldVisitDir('.idea', 1)).toBe(false)
    expect(shouldVisitDir('.hidden-thing', 1)).toBe(false)
  })
  it.each(['Node_Modules', '.GIT', '__PYCACHE__', 'DIST', 'DERIVEDDATA', '.NEXT', 'LIBRARY'])(
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

describe('isHiddenEntry', () => {
  it('flags dotfiles and dot-directories', () => {
    expect(isHiddenEntry('.env')).toBe(true)
    expect(isHiddenEntry('.DS_Store')).toBe(true)
    expect(isHiddenEntry('.vscode')).toBe(true)
  })
  it('does not flag ordinary names', () => {
    expect(isHiddenEntry('README.md')).toBe(false)
    expect(isHiddenEntry('src')).toBe(false)
    expect(isHiddenEntry('a.b.c')).toBe(false)
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

describe('pathsToDelete (retention diff)', () => {
  const sep = '\\'

  it('prunes only genuinely-deleted paths under healthy roots', () => {
    const existing = new Set(['C:\\U\\keep.txt', 'C:\\U\\gone.txt'])
    const scanned = new Set(['C:\\U\\keep.txt'])
    const result = pathsToDelete(scanned, existing, new Set(), sep)
    expect([...result]).toEqual(['C:\\U\\gone.txt'])
  })

  it('protects the whole subtree of a failed/absent prefix', () => {
    const existing = new Set(['C:\\U\\Documents\\a.txt', 'C:\\U\\Documents\\sub\\b.txt'])
    const scanned = new Set<string>() // enumeration failed → nothing scanned under it
    const protectedPrefixes = new Set(['C:\\U\\Documents'])
    const result = pathsToDelete(scanned, existing, protectedPrefixes, sep)
    expect(result.size).toBe(0)
  })

  it('protects a failed subtree while still pruning a deleted file elsewhere', () => {
    const existing = new Set([
      'C:\\U\\Documents\\protected.txt', // under a failed dir → must survive
      'C:\\U\\Downloads\\removed.txt' // healthy root, gone from disk → prune
    ])
    const scanned = new Set(['C:\\U\\Downloads\\keep.txt'])
    const protectedPrefixes = new Set(['C:\\U\\Documents'])
    const result = pathsToDelete(scanned, existing, protectedPrefixes, sep)
    expect([...result]).toEqual(['C:\\U\\Downloads\\removed.txt'])
  })

  it('treats the prefix as a path-segment boundary (no false sibling match)', () => {
    // 'C:\\U\\Doc' must NOT protect 'C:\\U\\Documents\\x' — only 'C:\\U\\Doc' + sep does.
    const existing = new Set(['C:\\U\\Documents\\x.txt'])
    const scanned = new Set<string>()
    const result = pathsToDelete(scanned, existing, new Set(['C:\\U\\Doc']), sep)
    expect([...result]).toEqual(['C:\\U\\Documents\\x.txt'])
  })

  it('protects the exact prefix path itself', () => {
    const existing = new Set(['C:\\U\\Documents'])
    const scanned = new Set<string>()
    const result = pathsToDelete(scanned, existing, new Set(['C:\\U\\Documents']), sep)
    expect(result.size).toBe(0)
  })
})
