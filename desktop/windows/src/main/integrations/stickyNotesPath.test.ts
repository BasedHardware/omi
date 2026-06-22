import { describe, it, expect } from 'vitest'
import { join } from 'path'
import { resolveStickyNotesDb } from './stickyNotesPath'

describe('resolveStickyNotesDb', () => {
  const local = 'C:\\Users\\me\\AppData\\Local'
  const pkgDir = 'Microsoft.MicrosoftStickyNotes_8wekyb3d8bbwe'
  const dbPath = join(local, 'Packages', pkgDir, 'LocalState', 'plum.sqlite')

  it('resolves the plum.sqlite path under the matching package dir', () => {
    const got = resolveStickyNotesDb(
      { LOCALAPPDATA: local },
      () => [pkgDir, 'Some.Other.Package_abc'],
      (p) => p === dbPath
    )
    expect(got).toBe(dbPath)
  })

  it('picks the first listed package whose db exists (caller pre-sorts newest-first)', () => {
    const newer = 'Microsoft.MicrosoftStickyNotes_new'
    const older = 'Microsoft.MicrosoftStickyNotes_old'
    const olderDb = join(local, 'Packages', older, 'LocalState', 'plum.sqlite')
    const got = resolveStickyNotesDb(
      { LOCALAPPDATA: local },
      () => [newer, older], // newest-first
      (p) => p === olderDb // only the older one actually has a db
    )
    expect(got).toBe(olderDb)
  })

  it('returns null when no Sticky Notes package dir exists', () => {
    expect(
      resolveStickyNotesDb({ LOCALAPPDATA: local }, () => ['Some.Other_x'], () => true)
    ).toBeNull()
  })

  it('returns null when the package exists but plum.sqlite does not', () => {
    expect(
      resolveStickyNotesDb({ LOCALAPPDATA: local }, () => [pkgDir], () => false)
    ).toBeNull()
  })

  it('returns null when LOCALAPPDATA is unset', () => {
    expect(resolveStickyNotesDb({}, () => [pkgDir], () => true)).toBeNull()
  })
})
