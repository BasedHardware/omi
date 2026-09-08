import { describe, it, expect } from 'vitest'
import { filesToPickedChatFiles } from './chatDropFiles'

// A minimal File-like with a controllable arrayBuffer — jsdom's File.arrayBuffer
// is not guaranteed in this env, and we're asserting the mapping, not the DOM
// File implementation.
function fakeFile(name: string, type: string, bytes: number[], opts?: { throws?: boolean }): File {
  return {
    name,
    type,
    size: bytes.length,
    arrayBuffer: opts?.throws
      ? (): Promise<ArrayBuffer> => Promise.reject(new Error('unreadable'))
      : (): Promise<ArrayBuffer> => Promise.resolve(new Uint8Array(bytes).buffer)
  } as unknown as File
}

describe('filesToPickedChatFiles', () => {
  it('maps name/type/size and reads the bytes', async () => {
    const [picked] = await filesToPickedChatFiles([fakeFile('a.png', 'image/png', [1, 2, 3])])
    expect(picked.name).toBe('a.png')
    expect(picked.mimeType).toBe('image/png')
    expect(picked.size).toBe(3)
    expect(Array.from(picked.bytes as Uint8Array)).toEqual([1, 2, 3])
  })

  it('defaults a missing mime type to octet-stream', async () => {
    const [picked] = await filesToPickedChatFiles([fakeFile('blob', '', [9])])
    expect(picked.mimeType).toBe('application/octet-stream')
  })

  it('returns bytes:null for an unreadable file instead of throwing', async () => {
    const [picked] = await filesToPickedChatFiles([
      fakeFile('bad', 'image/png', [1], { throws: true })
    ])
    expect(picked.bytes).toBeNull()
    expect(picked.name).toBe('bad')
  })
})
