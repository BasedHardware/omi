import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'fs/promises'
import { tmpdir } from 'os'
import { join } from 'path'

// Regression for the reported incident: signing out wiped rewind_frames, which
// left every historical JPEG with no DB row, and the sweep's grace-only rule
// (<60s => keep) then unlinked the entire history within minutes. The sweep now
// bounds deletion by the retention cutoff (orphanSelection.ts retireBeforeMs),
// so an index reset can never again arm it against in-retention files.
//
// Mock seams mirror retentionRunner.test.ts: ../ipc/db and ./captureService and
// ./paths are Electron/native-laden, the runner is not.

const state = vi.hoisted(() => ({
  root: '',
  // image_path values the DB (live rows + parked rows) currently owns.
  dbImagePaths: new Set<string>()
}))

vi.mock('../ipc/db', () => ({
  rewindImagePathsBetween: () => [...state.dbImagePaths]
}))
vi.mock('./captureService', () => ({
  getRewindSettings: () => ({
    captureEnabled: true,
    intervalMs: 1000,
    retentionDays: 14,
    excludedApps: [],
    captureQuality: 'standard'
  })
}))
vi.mock('./paths', () => ({ rewindRoot: () => state.root }))

import { sweepOrphanedFramesOnce } from './orphanSweep'

const DAY_MS = 24 * 60 * 60 * 1000
const NOW = 1_800_000_000_000 // fixed clock, deterministic ages

async function makeFrameFile(ageMs: number): Promise<{ fullPath: string; ts: number }> {
  const ts = NOW - ageMs
  const dayName = new Date(ts).toISOString().slice(0, 10)
  const dir = join(state.root, dayName)
  await mkdir(dir, { recursive: true })
  const fullPath = join(dir, `${ts}.jpg`)
  await writeFile(fullPath, Buffer.from('jpeg-bytes'))
  return { fullPath, ts }
}

describe('orphan sweep vs a sign-out index reset (data-loss regression)', () => {
  const tempPaths: string[] = []

  beforeEach(async () => {
    const temp = await mkdtemp(join(tmpdir(), 'omi-rewind-orphansweep-'))
    tempPaths.push(temp)
    state.root = join(temp, 'rewind')
    await mkdir(state.root)
    state.dbImagePaths = new Set()
  })

  afterEach(async () => {
    await Promise.all(tempPaths.splice(0).map((path) => rm(path, { recursive: true, force: true })))
  })

  it('keeps an in-retention file whose row vanished (the incident: empty keep-set)', async () => {
    // The violating input: the index was wiped, so the keep-set is empty and the
    // 5-day-old file has no row. Pre-fix, the grace-only sweep deleted it.
    const f = await makeFrameFile(5 * DAY_MS)

    await expect(sweepOrphanedFramesOnce(NOW)).resolves.toBe(0)

    await expect(readFile(f.fullPath)).resolves.toBeDefined()
  })

  it('still deletes a no-row file past the retention cutoff (crash-orphan cleanup survives)', async () => {
    const f = await makeFrameFile(20 * DAY_MS)

    await expect(sweepOrphanedFramesOnce(NOW)).resolves.toBe(1)

    await expect(readFile(f.fullPath)).rejects.toThrow()
  })

  it('keeps every file the index still owns, live or parked', async () => {
    const young = await makeFrameFile(5 * DAY_MS)
    const old = await makeFrameFile(20 * DAY_MS)
    // Old file covered ONLY by a parked row (the sign-out park): the keep-set
    // (REWIND_IMAGE_PATHS_SQL covers parked rows) must protect it from the
    // cutoff rule too: no row's age matters when the index still owns the path.
    state.dbImagePaths = new Set([young.fullPath, old.fullPath])

    await expect(sweepOrphanedFramesOnce(NOW)).resolves.toBe(0)

    await expect(readFile(young.fullPath)).resolves.toBeDefined()
    await expect(readFile(old.fullPath)).resolves.toBeDefined()
  })

  it('keeps a file inside the 60s grace window even with an empty keep-set', async () => {
    const f = await makeFrameFile(5_000)

    await expect(sweepOrphanedFramesOnce(NOW)).resolves.toBe(0)

    await expect(readFile(f.fullPath)).resolves.toBeDefined()
  })
})
