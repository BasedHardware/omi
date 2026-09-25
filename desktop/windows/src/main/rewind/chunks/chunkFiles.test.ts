// Chunk files on disk: the atomic write, and the sweep that decides a chunk is
// garbage. The sweep is the one that can lose data if it is wrong, so most of
// this file is about what it declines to delete.
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { mkdtemp, readdir, readFile, rm, writeFile, mkdir } from 'fs/promises'
import { tmpdir } from 'os'
import { join } from 'path'
import {
  CHUNK_SWEEP_GRACE_MS,
  daysTouched,
  listChunkFiles,
  readChunkFile,
  removeChunkFile,
  selectUnreferencedChunks,
  writeChunkFile
} from './chunkFiles'

let root: string

beforeEach(async () => {
  root = await mkdtemp(join(tmpdir(), 'omi-chunks-'))
})
afterEach(async () => {
  await rm(root, { recursive: true, force: true })
})

describe('writing a chunk', () => {
  it('creates the day directory and writes the bytes', async () => {
    await writeChunkFile(root, '2026-08-17/100-200.omichunk', new Uint8Array([1, 2, 3]))
    const back = await readChunkFile(root, '2026-08-17/100-200.omichunk')
    expect([...back]).toEqual([1, 2, 3])
  })

  it('leaves no temporary file behind', async () => {
    // A `.tmp` is deliberately not a legal chunk path, but one left lying
    // around is still litter that grows without bound.
    await writeChunkFile(root, '2026-08-17/100-200.omichunk', new Uint8Array([1]))
    const entries = await readdir(join(root, '2026-08-17'))
    expect(entries).toEqual(['100-200.omichunk'])
  })

  it('replaces an existing chunk atomically', async () => {
    await writeChunkFile(root, '2026-08-17/100-200.omichunk', new Uint8Array([1, 1, 1]))
    await writeChunkFile(root, '2026-08-17/100-200.omichunk', new Uint8Array([2, 2]))
    expect([...(await readChunkFile(root, '2026-08-17/100-200.omichunk'))]).toEqual([2, 2])
  })

  it('refuses a path outside the root', async () => {
    // Same containment property frameFile.ts enforces for JPEGs.
    await expect(writeChunkFile(root, '../escape.omichunk', new Uint8Array([1]))).rejects.toThrow(
      /refusing to write/
    )
    await expect(readChunkFile(root, '../../etc/passwd.omichunk')).rejects.toThrow(
      /refusing to read/
    )
    await expect(removeChunkFile(root, '../x.omichunk')).rejects.toThrow(/refusing to delete/)
  })
})

describe('listing chunks', () => {
  it('finds chunks under day directories', async () => {
    await writeChunkFile(root, '2026-08-16/1-2.omichunk', new Uint8Array([1]))
    await writeChunkFile(root, '2026-08-17/3-4.omichunk', new Uint8Array([1]))
    const found = await listChunkFiles(root)
    expect(found.map((f) => f.relativePath).sort()).toEqual([
      '2026-08-16/1-2.omichunk',
      '2026-08-17/3-4.omichunk'
    ])
  })

  it('ignores the JPEGs it shares the directory with', async () => {
    await mkdir(join(root, '2026-08-17'), { recursive: true })
    await writeFile(join(root, '2026-08-17', '1781329148845.jpg'), 'not a chunk')
    await writeChunkFile(root, '2026-08-17/1-2.omichunk', new Uint8Array([1]))
    const found = await listChunkFiles(root)
    expect(found).toHaveLength(1)
  })

  it('ignores a leftover temporary file', async () => {
    await mkdir(join(root, '2026-08-17'), { recursive: true })
    await writeFile(join(root, '2026-08-17', '1-2.omichunk.tmp'), 'half a chunk')
    expect(await listChunkFiles(root)).toHaveLength(0)
  })

  it('ignores directories that are not days', async () => {
    await mkdir(join(root, 'videos'), { recursive: true })
    await writeFile(join(root, 'videos', '1-2.omichunk'), 'x')
    expect(await listChunkFiles(root)).toHaveLength(0)
  })

  it('returns nothing for a root that does not exist yet', async () => {
    expect(await listChunkFiles(join(root, 'nope'))).toEqual([])
  })
})

describe('deciding a chunk is garbage', () => {
  const NOW = 1_781_400_000_000
  const old = (path: string) => ({ relativePath: path, modifiedMs: NOW - 60 * 60_000 })

  it('collects a chunk no frame points at', async () => {
    expect(selectUnreferencedChunks([old('2026-08-17/1-2.omichunk')], [], NOW)).toEqual([
      '2026-08-17/1-2.omichunk'
    ])
  })

  it('keeps a chunk that is still referenced', () => {
    const files = [old('2026-08-17/1-2.omichunk'), old('2026-08-17/3-4.omichunk')]
    expect(selectUnreferencedChunks(files, ['2026-08-17/1-2.omichunk'], NOW)).toEqual([
      '2026-08-17/3-4.omichunk'
    ])
  })

  it('spares a chunk written moments ago', () => {
    // THE case this grace exists for: between writing a chunk and claiming its
    // first frame the file is legitimately unreferenced, and deleting it there
    // would pull the ground out from under the compactor that just wrote it.
    const fresh = { relativePath: '2026-08-17/1-2.omichunk', modifiedMs: NOW - 1000 }
    expect(selectUnreferencedChunks([fresh], [], NOW)).toEqual([])
  })

  it('collects it once the grace has passed', () => {
    const file = { relativePath: '2026-08-17/1-2.omichunk', modifiedMs: NOW - CHUNK_SWEEP_GRACE_MS }
    expect(selectUnreferencedChunks([file], [], NOW)).toEqual(['2026-08-17/1-2.omichunk'])
  })

  it('collects a chunk the database never heard of', () => {
    // The crash-after-write case: the file exists, nothing ever claimed into it.
    expect(
      selectUnreferencedChunks([old('2026-08-17/9-9.omichunk')], ['2026-08-17/1-2.omichunk'], NOW)
    ).toEqual(['2026-08-17/9-9.omichunk'])
  })

  it('collects nothing when everything is referenced', () => {
    const files = [old('2026-08-17/1-2.omichunk')]
    expect(selectUnreferencedChunks(files, ['2026-08-17/1-2.omichunk'], NOW)).toEqual([])
  })
})

describe('day extraction', () => {
  it('lists the days a set of chunks touches, sorted', () => {
    expect(
      daysTouched(['2026-08-17/1-2.omichunk', '2026-08-16/3-4.omichunk', '2026-08-17/5-6.omichunk'])
    ).toEqual(['2026-08-16', '2026-08-17'])
  })

  it('skips a path it would not have written', () => {
    expect(daysTouched(['../evil.omichunk'])).toEqual([])
  })
})

describe('round trip through the real filesystem', () => {
  it('writes, lists, reads and removes', async () => {
    const path = '2026-08-17/1781329148845-1781329208845.omichunk'
    await writeChunkFile(root, path, new Uint8Array([7, 7, 7, 7]))
    expect((await listChunkFiles(root)).map((f) => f.relativePath)).toEqual([path])
    expect([...(await readChunkFile(root, path))]).toEqual([7, 7, 7, 7])
    await removeChunkFile(root, path)
    expect(await listChunkFiles(root)).toEqual([])
  })

  it('removing an absent chunk is not an error', async () => {
    // Retention runs repeatedly and must be idempotent.
    await expect(removeChunkFile(root, '2026-08-17/1-2.omichunk')).resolves.toBeUndefined()
  })

  it('does not read a file whose bytes were never renamed into place', async () => {
    await mkdir(join(root, '2026-08-17'), { recursive: true })
    await writeFile(join(root, '2026-08-17', '1-2.omichunk.tmp'), 'partial')
    await expect(readChunkFile(root, '2026-08-17/1-2.omichunk')).rejects.toThrow()
    // ...and the partial write is still sitting there under its temp name only.
    expect(await readFile(join(root, '2026-08-17', '1-2.omichunk.tmp'), 'utf8')).toBe('partial')
  })
})
