import { mkdir, mkdtemp, rm, writeFile } from 'fs/promises'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { readRewindFrameImage } from './frameImage'
import type { RewindFrame } from '../../shared/types'

let root = ''

function frame(over: Partial<RewindFrame>): RewindFrame {
  return {
    id: 7,
    ts: 1234,
    app: 'Code.exe',
    windowTitle: 'feature.ts',
    processName: 'Code',
    ocrText: '  first line\nsecond line  ',
    imagePath: join(root, 'frames', '7.jpg'),
    width: 100,
    height: 100,
    indexed: 1,
    ...over
  }
}

describe('readRewindFrameImage', () => {
  beforeEach(async () => {
    root = await mkdtemp(join(tmpdir(), 'omi-rewind-frame-'))
    await mkdir(join(root, 'frames'), { recursive: true })
  })

  afterEach(async () => {
    await rm(root, { recursive: true, force: true })
    root = ''
  })

  it('returns metadata and base64 image data for an existing frame', async () => {
    const bytes = Buffer.from([1, 2, 3, 4])
    await writeFile(join(root, 'frames', '7.jpg'), bytes)

    const result = await readRewindFrameImage(frame({}), root)

    expect(result).toMatchObject({
      ok: true,
      id: 7,
      ts: 1234,
      app: 'Code.exe',
      windowTitle: 'feature.ts',
      ocrPreview: 'first line second line',
      imageMimeType: 'image/jpeg',
      imageBase64: bytes.toString('base64')
    })
  })

  it('returns structured not_found for missing rows, deleted files, and invalid paths', async () => {
    await expect(readRewindFrameImage(null, root)).resolves.toMatchObject({
      ok: false,
      code: 'not_found'
    })
    await expect(readRewindFrameImage(frame({}), root)).resolves.toMatchObject({
      ok: false,
      code: 'not_found'
    })
    await expect(
      readRewindFrameImage(frame({ imagePath: join(root, '..', 'outside.jpg') }), root)
    ).resolves.toMatchObject({
      ok: false,
      code: 'not_found'
    })
  })
})
