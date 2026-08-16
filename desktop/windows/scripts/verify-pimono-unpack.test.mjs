import { describe, it, expect } from 'vitest'
import { globToPackageName } from './gen-pimono-unpack.mjs'

describe('verify-pimono-unpack cross-platform filters', () => {
  it('globToPackageName strips node_modules prefix and trailing glob', () => {
    expect(globToPackageName('node_modules/@mariozechner/clipboard-linux-x64-gnu/**')).toBe(
      '@mariozechner/clipboard-linux-x64-gnu'
    )
  })

  it('drift removed filter keeps optional platform siblings not installed on host', () => {
    const fresh = ['node_modules/@mariozechner/clipboard-linux-x64-gnu/**']
    const committed = [
      'node_modules/@mariozechner/clipboard-linux-x64-gnu/**',
      'node_modules/@mariozechner/clipboard-win32-x64-msvc/**'
    ]
    const optionalPlatformSiblingGlobs = ['node_modules/@mariozechner/clipboard-win32-x64-msvc/**']
    const freshSet = new Set(fresh)
    const optionalPlatformSiblingSet = new Set(optionalPlatformSiblingGlobs)

    const added = fresh.filter((g) => !new Set(committed).has(g))
    const removed = committed.filter((g) => !freshSet.has(g) && !optionalPlatformSiblingSet.has(g))

    expect(added).toEqual([])
    expect(removed).toEqual([])
  })

  it('completeness skips optional platform siblings missing on disk', () => {
    const committed = [
      'node_modules/@mariozechner/clipboard-linux-x64-gnu/**',
      'node_modules/@mariozechner/clipboard-win32-x64-msvc/**'
    ]
    const optionalPlatformSiblingGlobs = ['node_modules/@mariozechner/clipboard-win32-x64-msvc/**']
    const optionalPlatformSiblingSet = new Set(optionalPlatformSiblingGlobs)
    const installed = new Set(['node_modules/@mariozechner/clipboard-linux-x64-gnu/**'])

    const missingOnDisk = []
    for (const glob of committed) {
      if (installed.has(glob)) continue
      if (optionalPlatformSiblingSet.has(glob)) continue
      missingOnDisk.push(globToPackageName(glob))
    }

    expect(missingOnDisk).toEqual([])
  })
})
