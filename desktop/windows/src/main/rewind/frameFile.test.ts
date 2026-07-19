import { afterEach, describe, expect, it } from 'vitest'
import { mkdtemp, mkdir, open, rm, symlink, writeFile } from 'fs/promises'
import { tmpdir } from 'os'
import { join } from 'path'
import {
  MAX_REWIND_FRAME_BYTES,
  isRewindFramePath,
  isRewindFrameSizeAllowed,
  readRewindFrame
} from './frameFile'

describe('Rewind frame file boundary', () => {
  const root = join('safe', 'rewind')
  const tempPaths: string[] = []

  afterEach(async () => {
    await Promise.all(tempPaths.splice(0).map((path) => rm(path, { recursive: true, force: true })))
  })

  it('accepts only JPEG files inside the frame root', () => {
    expect(isRewindFramePath(root, join(root, '2026-07-19', '1.jpg'))).toBe(true)
    expect(isRewindFramePath(root, join(root, '..', 'outside.jpg'))).toBe(false)
    expect(isRewindFramePath(root, join(root, '1.png'))).toBe(false)
  })

  it('rejects a canonical path that escaped through a link', async () => {
    const temp = await mkdtemp(join(tmpdir(), 'omi-rewind-link-'))
    tempPaths.push(temp)
    const frameRoot = join(temp, 'rewind')
    const outside = join(temp, 'outside')
    const linked = join(frameRoot, 'linked')
    await Promise.all([mkdir(frameRoot), mkdir(outside)])
    await writeFile(join(outside, '1.jpg'), Buffer.from('jpeg'))
    await symlink(outside, linked, process.platform === 'win32' ? 'junction' : 'dir')
    await expect(readRewindFrame(frameRoot, join(linked, '1.jpg'))).rejects.toThrow('invalid frame path')
  })

  it('caps frame bytes before preview or ingest', async () => {
    expect(isRewindFrameSizeAllowed(MAX_REWIND_FRAME_BYTES)).toBe(true)
    expect(isRewindFrameSizeAllowed(MAX_REWIND_FRAME_BYTES + 1)).toBe(false)
    const temp = await mkdtemp(join(tmpdir(), 'omi-rewind-size-'))
    tempPaths.push(temp)
    const frameRoot = join(temp, 'rewind')
    const frame = join(frameRoot, '1.jpg')
    await mkdir(frameRoot)
    const handle = await open(frame, 'w')
    await handle.truncate(MAX_REWIND_FRAME_BYTES + 1)
    await handle.close()
    await expect(readRewindFrame(frameRoot, frame)).rejects.toThrow('frame exceeds preview size limit')
  })

  it('reads a bounded JPEG from the canonical frame root', async () => {
    const temp = await mkdtemp(join(tmpdir(), 'omi-rewind-frame-'))
    tempPaths.push(temp)
    const frameRoot = join(temp, 'rewind')
    const frame = join(frameRoot, '1.jpg')
    await mkdir(frameRoot)
    await writeFile(frame, Buffer.from('jpeg'))
    expect(await readRewindFrame(frameRoot, frame)).toEqual(Buffer.from('jpeg'))
  })
})
