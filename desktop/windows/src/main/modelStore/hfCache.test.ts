import { describe, it, expect } from 'vitest'
import { join } from 'path'
import {
  repoCacheDirName,
  cacheCandidates,
  planResume,
  refPath,
  defaultCacheRoots
} from './hfCache'
import { hfDownloadUrl, modelFilePath, modelPartPath, findModel, MODEL_REGISTRY } from './registry'
import type { ModelEntry } from '../../shared/types'

const entry: ModelEntry = {
  id: 'x',
  label: 'X',
  repo: 'bartowski/Qwen2.5-3B-Instruct-GGUF',
  file: 'Qwen2.5-3B-Instruct-Q4_K_M.gguf',
  revision: 'main',
  sizeBytes: 2_000_000_000,
  sha256: 'abc123',
  minRamGb: 6,
  vision: false
}

describe('hfCache.repoCacheDirName', () => {
  it('uses HF models--org--name convention', () => {
    expect(repoCacheDirName('bartowski/Qwen2.5-3B-Instruct-GGUF')).toBe(
      'models--bartowski--Qwen2.5-3B-Instruct-GGUF'
    )
  })
  it('replaces illegal chars with colons', () => {
    expect(repoCacheDirName('org/nm.ame')).toBe('models--org--nm.ame')
    expect(repoCacheDirName('a/b@c')).toContain(':')
  })
})

describe('hfCache.cacheCandidates', () => {
  const root = join('home', 'u', '.cache', 'huggingface', 'hub')
  it('prefers the content-addressed blob when sha256 is known', () => {
    const c = cacheCandidates(root, entry, 'deadbeef')
    expect(c[0]).toBe(join(root, 'models--bartowski--Qwen2.5-3B-Instruct-GGUF', 'blobs', 'abc123'))
    // and still offers the snapshot checkout as a fallback
    expect(c[1]).toContain(join('snapshots', 'deadbeef', entry.file))
  })
  it('omits the blob path when sha256 unknown but still uses the commit snapshot', () => {
    const noSha = { ...entry, sha256: undefined }
    const c = cacheCandidates(root, noSha, 'cafe')
    expect(c.find((p) => p.includes('blobs'))).toBeUndefined()
    expect(c[0]).toContain(join('snapshots', 'cafe', entry.file))
  })
  it('produces no snapshot candidate without a resolved commit', () => {
    const c = cacheCandidates(root, { ...entry, sha256: undefined }, undefined)
    expect(c).toEqual([])
  })
})

describe('hfCache.refPath + defaultCacheRoots', () => {
  it('points refs at the revision', () => {
    expect(refPath('/hub', entry)).toBe(
      join('/hub', 'models--bartowski--Qwen2.5-3B-Instruct-GGUF', 'refs', 'main')
    )
  })
  it('respects HF_HUB_CACHE / HF_HOME ordering and dedupes', () => {
    const roots = defaultCacheRoots({ HF_HUB_CACHE: '/a', HF_HOME: '/b' }, '/h')
    expect(roots[0]).toBe('/a')
    expect(roots[1]).toBe(join('/b', 'hub'))
    expect(new Set(roots).size).toBe(roots.length)
  })
})

describe('hfCache.planResume', () => {
  it('fresh download has no range header', () => {
    expect(planResume(0, 100)).toEqual({ start: 0, complete: false, rangeHeader: undefined })
  })
  it('partial resumes with a byte range', () => {
    expect(planResume(40, 100)).toEqual({ start: 40, complete: false, rangeHeader: 'bytes=40-' })
  })
  it('full part short-circuits to verify', () => {
    expect(planResume(100, 100).complete).toBe(true)
  })
  it('unknown total (0) never claims completion', () => {
    expect(planResume(500, 0)).toEqual({ start: 500, complete: false, rangeHeader: 'bytes=500-' })
  })
})

describe('registry', () => {
  it('builds the HF resolve URL + honors a mirror endpoint', () => {
    expect(hfDownloadUrl(entry)).toBe(
      'https://huggingface.co/bartowski/Qwen2.5-3B-Instruct-GGUF/resolve/main/' + entry.file
    )
    expect(hfDownloadUrl(entry, 'https://hf-mirror.com/')).toContain('https://hf-mirror.com/bartowski/')
  })
  it('keeps the file inside a per-model dir + adds a .part sibling', () => {
    expect(modelFilePath('/ud', entry)).toBe(join('/ud', 'models', 'x', entry.file))
    expect(modelPartPath('/ud', entry)).toBe(modelFilePath('/ud', entry) + '.part')
  })
  it('findModel by id + a coherent registry (unique ids, chat-capable set has >=1)', () => {
    expect(findModel('qwen2.5-3b-instruct-q4km')?.vision).toBe(false)
    expect(new Set(MODEL_REGISTRY.map((m) => m.id)).size).toBe(MODEL_REGISTRY.length)
    expect(MODEL_REGISTRY.some((m) => !m.vision)).toBe(true)
  })
})
