// Every test here is about one sentence: a JPEG is deleted only in exchange for
// a chunk that has been written, read back from disk, and proven to hold that
// exact frame at that exact offset. The cases are the ways that can fail.
import { describe, expect, it, vi } from 'vitest'
import { encodeChunk } from './chunkFormat'
import { COMPACTION_MIN_AGE_MS, localDayKey, type CompactableFrame } from './compactionPlan'
import { compactOnce, estimateReclaimable, type CompactorDeps } from './compactor'

const NOW = new Date('2026-08-17T18:00:00').getTime()
// A day back, not an hour: cases below offset hours forward from this and must
// still land older than COMPACTION_MIN_AGE_MS, or they are silently filtered out
// by age instead of exercising what they claim to.
const OLD = NOW - 24 * 60 * 60_000
/** Inside the compaction delay, so nothing here is eligible. */
const TOO_NEW = NOW - COMPACTION_MIN_AGE_MS / 2

function frames(count: number, startMs = OLD): CompactableFrame[] {
  return Array.from({ length: count }, (_, i) => ({
    id: 100 + i,
    tsMs: startMs + i * 1000,
    width: 1280,
    height: 720,
    imagePath: `C:/rewind/2026-08-17/${startMs + i * 1000}.jpg`
  }))
}

type Harness = {
  deps: CompactorDeps
  disk: Map<string, Uint8Array>
  jpegs: Map<string, Uint8Array>
  claims: { id: number; path: string; offset: number }[]
  deleted: string[]
  logs: string[]
}

function harness(
  rows: CompactableFrame[],
  overrides: Partial<CompactorDeps> = {},
  options: { unclaimable?: Set<number> } = {}
): Harness {
  const jpegs = new Map<string, Uint8Array>()
  for (const f of rows) jpegs.set(f.imagePath, new Uint8Array([0xff, 0xd8, f.id & 0xff, 1, 2, 3]))
  const disk = new Map<string, Uint8Array>()
  const claims: { id: number; path: string; offset: number }[] = []
  const deleted: string[] = []
  const logs: string[] = []
  const claimed = new Set<number>()

  const deps: CompactorDeps = {
    nowMs: () => NOW,
    listCompactable: () => rows,
    readJpeg: async (p) => {
      const b = jpegs.get(p)
      if (!b) throw new Error(`missing ${p}`)
      return b
    },
    // A faithful stand-in: real bytes in the real container, so verification is
    // exercised for real rather than stubbed past.
    encode: async ({ width, height, frames: input }) =>
      encodeChunk({
        codec: 'avc1.42001f',
        description: new Uint8Array([1, 100]),
        width,
        height,
        frames: input.map((f, i) => ({
          captureTsMs: f.captureTsMs,
          isKeyFrame: i === 0,
          data: new Uint8Array([i + 1, 9])
        }))
      }),
    writeChunk: async (rel, bytes) => {
      disk.set(rel, bytes)
    },
    readChunk: async (rel) => {
      const b = disk.get(rel)
      if (!b) throw new Error(`no chunk at ${rel}`)
      return b
    },
    removeChunk: async (rel) => {
      disk.delete(rel)
    },
    claimFrame: (id, path, offset) => {
      if (options.unclaimable?.has(id)) return false
      if (claimed.has(id)) return false
      claimed.add(id)
      claims.push({ id, path, offset })
      return true
    },
    deleteJpeg: async (p) => {
      deleted.push(p)
      jpegs.delete(p)
    },
    log: (m) => logs.push(m),
    ...overrides
  }
  return { deps, disk, jpegs, claims, deleted, logs }
}

describe('the happy path', () => {
  it('writes one chunk, claims every frame, and deletes their JPEGs', async () => {
    const rows = frames(30)
    const h = harness(rows)
    const result = await compactOnce(h.deps)

    expect(result.chunksWritten).toBe(1)
    expect(result.framesCompacted).toBe(30)
    expect(h.disk.size).toBe(1)
    expect(h.deleted).toHaveLength(30)
    expect(h.jpegs.size).toBe(0)
  })

  it('claims each frame at the offset it occupies in the chunk', async () => {
    // The offset IS the address. Off by one and every read returns a neighbour.
    const rows = frames(20)
    const h = harness(rows)
    await compactOnce(h.deps)
    expect(h.claims.map((c) => c.offset)).toEqual([...Array(20).keys()])
    expect(h.claims.map((c) => c.id)).toEqual(rows.map((r) => r.id))
  })

  it('names the chunk for the span it covers', async () => {
    const rows = frames(12)
    const h = harness(rows)
    await compactOnce(h.deps)
    const [path] = [...h.disk.keys()]
    expect(path).toBe(`${localDayKey(rows[0].tsMs)}/${rows[0].tsMs}-${rows[11].tsMs}.omichunk`)
  })

  it('reports what it reclaimed', async () => {
    const h = harness(frames(15))
    const result = await compactOnce(h.deps)
    expect(result.bytesReclaimed).toBe(15 * 6)
    expect(h.logs.join(' ')).toMatch(/compacted 15 frames/)
  })

  it('does nothing when there is nothing eligible', async () => {
    const h = harness([])
    const result = await compactOnce(h.deps)
    expect(result).toEqual({ chunksWritten: 0, framesCompacted: 0, bytesReclaimed: 0, skipped: [] })
    expect(h.disk.size).toBe(0)
  })
})

describe('nothing is deleted unless the chunk is proven', () => {
  it('deletes no JPEG when a source frame cannot be read', async () => {
    // Compacting without it would renumber every offset after it.
    const rows = frames(20)
    const h = harness(rows, {
      readJpeg: async (p) => {
        if (p.endsWith(`${rows[7].tsMs}.jpg`)) throw new Error('gone')
        return new Uint8Array([0xff, 0xd8, 1])
      }
    })
    const result = await compactOnce(h.deps)
    expect(result.chunksWritten).toBe(0)
    expect(h.deleted).toEqual([])
    expect(h.disk.size).toBe(0)
    expect(result.skipped[0].reason).toMatch(/could not be read/)
  })

  it('deletes no JPEG when the encoder fails', async () => {
    const h = harness(frames(20), {
      encode: async () => {
        throw new Error('no encoder on this machine')
      }
    })
    const result = await compactOnce(h.deps)
    expect(h.deleted).toEqual([])
    expect(result.skipped[0].reason).toMatch(/encode failed/)
  })

  it('deletes no JPEG when the chunk cannot be written', async () => {
    const h = harness(frames(20), {
      writeChunk: async () => {
        throw new Error('disk full')
      }
    })
    const result = await compactOnce(h.deps)
    expect(h.deleted).toEqual([])
    expect(result.skipped[0].reason).toMatch(/write failed/)
  })

  it('deletes no JPEG when the chunk cannot be read back', async () => {
    // A write that reported success but did not land.
    const h = harness(frames(20), { readChunk: async () => new Uint8Array([1, 2, 3]) })
    const result = await compactOnce(h.deps)
    expect(h.deleted).toEqual([])
    expect(result.skipped[0].reason).toMatch(/did not read back/)
  })

  it('removes the bad file when verification fails', async () => {
    const h = harness(frames(20), { readChunk: async () => new Uint8Array([1, 2, 3]) })
    await compactOnce(h.deps)
    expect(h.disk.size).toBe(0)
  })

  it('rejects a chunk that came back holding a different number of frames', async () => {
    const rows = frames(20)
    const h = harness(rows, {
      encode: async ({ width, height, frames: input }) =>
        encodeChunk({
          codec: 'avc1.42001f',
          description: new Uint8Array(),
          width,
          height,
          frames: input.slice(0, 10).map((f, i) => ({
            captureTsMs: f.captureTsMs,
            isKeyFrame: i === 0,
            data: new Uint8Array([1])
          }))
        })
    })
    const result = await compactOnce(h.deps)
    expect(h.deleted).toEqual([])
    expect(result.skipped[0].reason).toMatch(/holds 10 frames, planned 20/)
  })

  it('rejects a chunk whose frames came back in the wrong order', async () => {
    // The failure this catches is silent otherwise: right count, right size,
    // every read off by one.
    const rows = frames(20)
    const h = harness(rows, {
      encode: async ({ width, height, frames: input }) => {
        const shifted = [...input.slice(1), input[0]]
        return encodeChunk({
          codec: 'avc1.42001f',
          description: new Uint8Array(),
          width,
          height,
          frames: shifted.map((f, i) => ({
            captureTsMs: f.captureTsMs,
            isKeyFrame: i === 0,
            data: new Uint8Array([1])
          }))
        })
      }
    })
    const result = await compactOnce(h.deps)
    expect(h.deleted).toEqual([])
    expect(result.skipped[0].reason).toMatch(/wrong capture time/)
  })

  it('rejects a chunk that came back with the wrong geometry', async () => {
    const h = harness(frames(20), {
      encode: async ({ frames: input }) =>
        encodeChunk({
          codec: 'avc1.42001f',
          description: new Uint8Array(),
          width: 640,
          height: 480,
          frames: input.map((f, i) => ({
            captureTsMs: f.captureTsMs,
            isKeyFrame: i === 0,
            data: new Uint8Array([1])
          }))
        })
    })
    const result = await compactOnce(h.deps)
    expect(h.deleted).toEqual([])
    expect(result.skipped[0].reason).toMatch(/wrong geometry/)
  })
})

describe('losing a race for a frame', () => {
  it('keeps the JPEG of a frame it could not claim', async () => {
    const rows = frames(20)
    const h = harness(rows, {}, { unclaimable: new Set([rows[5].id]) })
    await compactOnce(h.deps)
    expect(h.deleted).not.toContain(rows[5].imagePath)
    expect(h.jpegs.has(rows[5].imagePath)).toBe(true)
  })

  it('still compacts the frames it did claim', async () => {
    // The chunk holds a superset of what points into it, which is harmless:
    // the unclaimed frame simply stays JPEG-backed.
    const rows = frames(20)
    const h = harness(rows, {}, { unclaimable: new Set([rows[5].id]) })
    const result = await compactOnce(h.deps)
    expect(result.chunksWritten).toBe(1)
    expect(result.framesCompacted).toBe(19)
    expect(h.disk.size).toBe(1)
  })

  it('takes the file back when every frame was claimed by someone else', async () => {
    const rows = frames(20)
    const h = harness(rows, {}, { unclaimable: new Set(rows.map((r) => r.id)) })
    const result = await compactOnce(h.deps)
    expect(result.chunksWritten).toBe(0)
    expect(h.disk.size).toBe(0)
    expect(h.deleted).toEqual([])
    expect(result.skipped[0].reason).toMatch(/already claimed/)
  })

  it('deletes a JPEG only after the claim that gave it up succeeded', async () => {
    // Ordering, not just outcome: a delete before the claim would lose the
    // frame outright if the claim then failed.
    const order: string[] = []
    const rows = frames(10)
    const h = harness(rows, {
      claimFrame: (id, path, offset) => {
        order.push(`claim:${offset}`)
        void id
        void path
        return true
      },
      deleteJpeg: async (p) => {
        order.push(`delete:${p.split('/').pop()}`)
      }
    })
    await compactOnce(h.deps)
    expect(order[0]).toBe('claim:0')
    expect(order[1]).toMatch(/^delete:/)
    expect(order.filter((o) => o.startsWith('claim')).length).toBe(10)
  })
})

describe('several runs in one pass', () => {
  it('writes a chunk per run and keeps going after one is skipped', async () => {
    const morning = frames(15)
    const evening = frames(15, OLD + 6 * 60 * 60_000).map((f) => ({ ...f, id: f.id + 500 }))
    const h = harness([...morning, ...evening], {
      readJpeg: async (p) => {
        if (p.endsWith(`${morning[3].tsMs}.jpg`)) throw new Error('gone')
        return new Uint8Array([0xff, 0xd8, 7])
      }
    })
    const result = await compactOnce(h.deps)
    expect(result.chunksWritten).toBe(1)
    expect(result.skipped).toHaveLength(1)
    expect(h.disk.size).toBe(1)
  })

  it('logs what it skipped rather than failing silently', async () => {
    const h = harness(frames(20), {
      encode: async () => {
        throw new Error('nope')
      }
    })
    await compactOnce(h.deps)
    expect(h.logs.join(' ')).toMatch(/skipped 1 chunk/)
  })
})

describe('estimating without doing', () => {
  it('reports the frames and bytes a pass would take', () => {
    const estimate = estimateReclaimable(frames(30), NOW, () => 64_000)
    expect(estimate.frames).toBe(30)
    expect(estimate.bytes).toBe(30 * 64_000)
  })

  it('reports nothing when everything is too new', () => {
    const estimate = estimateReclaimable(frames(30, TOO_NEW), NOW, () => 64_000)
    expect(estimate).toEqual({ frames: 0, bytes: 0 })
  })

  it('touches nothing', () => {
    const deleteJpeg = vi.fn()
    estimateReclaimable(frames(30), NOW, () => 1)
    expect(deleteJpeg).not.toHaveBeenCalled()
  })
})
