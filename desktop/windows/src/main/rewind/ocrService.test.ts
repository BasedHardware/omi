// The backlog sweep's idle-burn gate: it must NOT hit the DB every 4s when there
// is nothing to OCR, and it must reliably wake when capture leaves a frame
// un-OCR'd. Every impure edge (DB, OCR helper, persistence, filesystem) is mocked,
// so this runs with no native binding.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mkdtemp, mkdir, open, rm, symlink, writeFile } from 'fs/promises'
import { tmpdir } from 'os'
import { join } from 'path'
import { MAX_REWIND_FRAME_BYTES } from './frameFile'

const unindexedRewindFrames = vi.fn<(limit: number) => unknown[]>(() => [])
const persistFrameOcr = vi.fn()

vi.mock('../ipc/db', () => ({ unindexedRewindFrames: (n: number) => unindexedRewindFrames(n) }))
vi.mock('../ocr/helperProcess', () => ({
  helperProcess: { ocr: vi.fn(async () => ({ ok: true, fullText: 'x', lines: [] })) }
}))
vi.mock('./ocrPersist', () => ({ persistFrameOcr: (...args: unknown[]) => persistFrameOcr(...args) }))
vi.mock('./paths', () => ({ rewindRoot: () => boundaryState.root }))

const boundaryState = vi.hoisted(() => ({
  root: '',
  frames: [] as Array<{ id: number; imagePath: string; app: string; windowTitle: string }>,
  ocr: vi.fn()
}))

import { helperProcess } from '../ocr/helperProcess'
import { signalRewindOcrPending, __rewindOcrTestHooks } from './ocrService'

const { backfill, setPending, getPending } = __rewindOcrTestHooks

function frames(n: number): { id: number; imagePath: string; app: string; windowTitle: string }[] {
  return Array.from({ length: n }, (_, i) => ({
    id: i + 1,
    imagePath: `/f/${i}.jpg`,
    app: 'App',
    windowTitle: 'w'
  }))
}

beforeEach(() => {
  unindexedRewindFrames.mockReset().mockReturnValue([])
  persistFrameOcr.mockReset()
  setPending(false)
})

describe('OCR backlog sweep — idle gate', () => {
  it('skips the DB read entirely when nothing is pending', async () => {
    await backfill()
    expect(unindexedRewindFrames).not.toHaveBeenCalled()
  })

  it('reads once when pending, then re-gates after draining a short page', async () => {
    signalRewindOcrPending()
    expect(getPending()).toBe(true)

    unindexedRewindFrames.mockReturnValue(frames(2))
    await backfill()
    expect(unindexedRewindFrames).toHaveBeenCalledTimes(1)
    expect(getPending()).toBe(false)

    await backfill()
    expect(unindexedRewindFrames).toHaveBeenCalledTimes(1)
  })

  it('keeps sweeping while a full page suggests more remain', async () => {
    signalRewindOcrPending()
    unindexedRewindFrames.mockReturnValue(frames(5))
    await backfill()
    expect(getPending()).toBe(true)

    await backfill()
    expect(unindexedRewindFrames).toHaveBeenCalledTimes(2)
  })

  it('a signal arriving during a sweep re-arms the gate (work is never lost)', async () => {
    signalRewindOcrPending()
    unindexedRewindFrames.mockImplementation(() => {
      signalRewindOcrPending()
      return frames(1)
    })
    await backfill()
    expect(getPending()).toBe(true)
  })
})

describe('Rewind OCR backfill boundary', () => {
  const tempPaths: string[] = []

  beforeEach(() => {
    boundaryState.frames = []
    boundaryState.ocr.mockReset()
    persistFrameOcr.mockReset()
    vi.mocked(helperProcess.ocr).mockImplementation((jpeg: Buffer) => boundaryState.ocr(jpeg))
    unindexedRewindFrames.mockImplementation(() => boundaryState.frames)
  })

  afterEach(async () => {
    await Promise.all(tempPaths.splice(0).map((path) => rm(path, { recursive: true, force: true })))
  })

  async function frameRoot(): Promise<string> {
    const temp = await mkdtemp(join(tmpdir(), 'omi-rewind-ocr-'))
    tempPaths.push(temp)
    const root = join(temp, 'rewind')
    await mkdir(root)
    boundaryState.root = root
    return root
  }

  it('OCRs a valid persisted frame', async () => {
    const root = await frameRoot()
    const frame = join(root, '1.jpg')
    await writeFile(frame, Buffer.from('jpeg'))
    boundaryState.frames = [{ id: 1, imagePath: frame, app: 'App', windowTitle: 'w' }]
    boundaryState.ocr.mockResolvedValue({ ok: true, fullText: 'text', lines: [] })
    signalRewindOcrPending()

    await backfill()

    expect(boundaryState.ocr).toHaveBeenCalledWith(Buffer.from('jpeg'))
    expect(persistFrameOcr).toHaveBeenCalledWith(1, 'text', { app: 'App', windowTitle: 'w' }, [])
  })

  it('does not OCR a frame that escapes through a reparse link', async () => {
    const root = await frameRoot()
    const outside = join(root, '..', 'outside')
    const linked = join(root, 'linked')
    await mkdir(outside)
    await writeFile(join(outside, '1.jpg'), Buffer.from('jpeg'))
    await symlink(outside, linked, process.platform === 'win32' ? 'junction' : 'dir')
    boundaryState.frames = [{ id: 2, imagePath: join(linked, '1.jpg'), app: 'App', windowTitle: 'w' }]
    signalRewindOcrPending()

    await backfill()

    expect(boundaryState.ocr).not.toHaveBeenCalled()
    expect(persistFrameOcr).toHaveBeenCalledWith(2, '', { app: 'App', windowTitle: 'w' })
  })

  it('does not OCR an oversized persisted frame', async () => {
    const root = await frameRoot()
    const frame = join(root, 'large.jpg')
    const handle = await open(frame, 'w')
    await handle.truncate(MAX_REWIND_FRAME_BYTES + 1)
    await handle.close()
    boundaryState.frames = [{ id: 3, imagePath: frame, app: 'App', windowTitle: 'w' }]
    signalRewindOcrPending()

    await backfill()

    expect(boundaryState.ocr).not.toHaveBeenCalled()
    expect(persistFrameOcr).toHaveBeenCalledWith(3, '', { app: 'App', windowTitle: 'w' })
  })
})
