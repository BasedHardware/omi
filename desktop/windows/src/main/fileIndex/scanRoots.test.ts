import { describe, it, expect } from 'vitest'
import { join } from 'path'
import { resolveScanRoots } from './scanRoots'

describe('resolveScanRoots', () => {
  const env = {
    USERPROFILE: 'C:\\Users\\me',
    ProgramData: 'C:\\ProgramData',
    APPDATA: 'C:\\Users\\me\\AppData\\Roaming'
  }

  it('includes existing doc + dev roots as files, Start-Menu as apps', () => {
    const present = new Set([
      join('C:\\Users\\me', 'Downloads'),
      join('C:\\Users\\me', 'Documents'),
      join('C:\\Users\\me', 'source', 'repos'),
      join('C:\\ProgramData', 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
      join('C:\\Users\\me\\AppData\\Roaming', 'Microsoft', 'Windows', 'Start Menu', 'Programs')
    ])
    const roots = resolveScanRoots(env, (p) => present.has(p))
    const files = roots.filter((r) => r.kind === 'files').map((r) => r.path)
    const apps = roots.filter((r) => r.kind === 'apps').map((r) => r.path)
    expect(files).toContain(join('C:\\Users\\me', 'Downloads'))
    expect(files).toContain(join('C:\\Users\\me', 'source', 'repos'))
    expect(files).not.toContain(join('C:\\Users\\me', 'Desktop')) // not present
    expect(apps).toHaveLength(2)
  })

  it('returns nothing when env is empty', () => {
    expect(resolveScanRoots({}, () => true)).toEqual([])
  })
})
