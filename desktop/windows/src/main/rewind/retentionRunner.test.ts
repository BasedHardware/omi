import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mkdtemp, mkdir, readFile, rm, symlink, writeFile } from 'fs/promises'
import { tmpdir } from 'os'
import { join } from 'path'

const state = vi.hoisted(() => ({
  root: '',
  removed: [] as Array<{ imagePath: string }>
}))

vi.mock('../ipc/db', () => ({ deleteRewindFramesOlderThan: () => state.removed }))
vi.mock('./captureService', () => ({ getRewindSettings: () => ({ retentionDays: 30 }) }))
vi.mock('./paths', () => ({ rewindRoot: () => state.root }))

import { pruneRewindOnce } from './retentionRunner'

describe('Rewind retention boundary', () => {
  const tempPaths: string[] = []

  beforeEach(() => {
    state.removed = []
  })

  afterEach(async () => {
    await Promise.all(tempPaths.splice(0).map((path) => rm(path, { recursive: true, force: true })))
  })

  it('removes valid frames while preserving outside and reparse targets', async () => {
    const temp = await mkdtemp(join(tmpdir(), 'omi-rewind-retention-'))
    tempPaths.push(temp)
    const root = join(temp, 'rewind')
    const outside = join(temp, 'outside')
    const valid = join(root, 'valid.jpg')
    const escaped = join(outside, 'escaped.jpg')
    const linked = join(root, 'linked')
    const reparseTarget = join(outside, 'linked.jpg')
    await Promise.all([mkdir(root), mkdir(outside)])
    await Promise.all([writeFile(valid, Buffer.from('valid')), writeFile(escaped, Buffer.from('outside')), writeFile(reparseTarget, Buffer.from('linked'))])
    await symlink(outside, linked, process.platform === 'win32' ? 'junction' : 'dir')
    state.root = root
    state.removed = [{ imagePath: valid }, { imagePath: escaped }, { imagePath: join(linked, 'linked.jpg') }]

    await expect(pruneRewindOnce()).resolves.toBe(3)

    await expect(readFile(valid)).rejects.toThrow()
    expect(await readFile(escaped)).toEqual(Buffer.from('outside'))
    expect(await readFile(reparseTarget)).toEqual(Buffer.from('linked'))
  })
})
