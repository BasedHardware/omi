// A chunk path comes out of the database and turns into a file read, so these
// are the same containment properties frameFile.ts already defends for JPEGs.
import { describe, expect, it } from 'vitest'
import { resolve } from 'path'
import { chunkDay, chunkRelativePath, isChunkRelativePath, resolveChunkPath } from './chunkPaths'

const ROOT = resolve('C:/Users/someone/AppData/Roaming/omi-windows/rewind')

describe('naming a chunk', () => {
  it('names it for the span it covers', () => {
    // A directory listing then sorts chronologically and says what is inside
    // each file without opening it.
    expect(chunkRelativePath('2026-08-17', 1781329148845, 1781329208845)).toBe(
      '2026-08-17/1781329148845-1781329208845.omichunk'
    )
  })

  it('is stable for the same frames', () => {
    // Two runs over the same plan must not produce two files.
    const a = chunkRelativePath('2026-08-17', 100, 200)
    const b = chunkRelativePath('2026-08-17', 100, 200)
    expect(a).toBe(b)
  })

  it('refuses a malformed day', () => {
    expect(() => chunkRelativePath('2026-8-17', 100, 200)).toThrow(/invalid chunk day/)
    expect(() => chunkRelativePath('../../etc', 100, 200)).toThrow(/invalid chunk day/)
  })

  it('refuses a span that ends before it starts', () => {
    expect(() => chunkRelativePath('2026-08-17', 200, 100)).toThrow(/end timestamp/)
  })
})

describe('validating a stored path', () => {
  it('accepts what this app writes', () => {
    expect(isChunkRelativePath('2026-08-17/1781329148845-1781329208845.omichunk')).toBe(true)
  })

  it.each([
    ['parent traversal', '../../../Windows/System32/config.omichunk'],
    ['embedded traversal', '2026-08-17/../../secrets.omichunk'],
    ['absolute path', 'C:/Windows/System32/x.omichunk'],
    ['UNC path', '//attacker/share/x.omichunk'],
    ['wrong extension', '2026-08-17/1-2.jpg'],
    ['no day directory', '1781329148845-1781329208845.omichunk'],
    ['nested too deep', '2026-08-17/sub/1-2.omichunk'],
    ['non-numeric span', '2026-08-17/first-last.omichunk'],
    ['leading whitespace', ' 2026-08-17/1-2.omichunk'],
    ['trailing whitespace', '2026-08-17/1-2.omichunk '],
    ['empty', '']
  ])('rejects %s', (_label, value) => {
    expect(isChunkRelativePath(value)).toBe(false)
    expect(resolveChunkPath(ROOT, value)).toBeNull()
  })

  it('rejects a non-string without throwing', () => {
    // Rows come back from SQLite, where the column is only nominally typed.
    expect(isChunkRelativePath(null as unknown as string)).toBe(false)
    expect(isChunkRelativePath(42 as unknown as string)).toBe(false)
  })
})

describe('resolving to disk', () => {
  it('resolves inside the root', () => {
    const resolved = resolveChunkPath(ROOT, '2026-08-17/1-2.omichunk')
    expect(resolved).toBe(resolve(ROOT, '2026-08-17/1-2.omichunk'))
    expect(resolved?.startsWith(ROOT)).toBe(true)
  })

  it('returns null rather than throwing on a corrupt row', () => {
    // These callers serve a UI: one bad row should render one missing frame,
    // not take down the page.
    expect(resolveChunkPath(ROOT, '../escape.omichunk')).toBeNull()
  })

  it('does not treat a sibling directory with the same prefix as inside', () => {
    // `<root>-evil` starts with `<root>` as a string but is not under it.
    expect(resolveChunkPath(ROOT, '../rewind-evil/2026-08-17/1-2.omichunk')).toBeNull()
  })
})

describe('day extraction', () => {
  it('reads the day a chunk is filed under', () => {
    expect(chunkDay('2026-08-17/1-2.omichunk')).toBe('2026-08-17')
  })

  it('returns null for a path it would not have written', () => {
    expect(chunkDay('../x.omichunk')).toBeNull()
  })
})
