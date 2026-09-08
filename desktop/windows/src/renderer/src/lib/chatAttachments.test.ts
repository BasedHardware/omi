import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { PickedChatFile } from '../../../shared/types'
import type { FileChat } from './omiApi.generated'
import {
  addAttachments,
  awaitUploadsSettled,
  clearAttachments,
  getPendingAttachments,
  getUploadedFileIds,
  onPendingAttachments,
  removeAttachment,
  MAX_CHAT_ATTACHMENTS
} from './chatAttachments'

// firebase is only reached by the real uploader, which we never call (every test
// injects an upload). Mock it so the transitive import is inert.
vi.mock('./firebase', () => ({ auth: { currentUser: null } }))

const flush = (): Promise<void> => new Promise((r) => setTimeout(r, 0))

const pick = (name: string, over = false, empty = false): PickedChatFile => ({
  name,
  mimeType: 'text/plain',
  size: empty ? 0 : over ? 30 * 1024 * 1024 : 3,
  bytes: empty ? null : new Uint8Array([1, 2, 3])
})

const fileChat = (name: string): FileChat => ({
  id: `srv-${name}`,
  name,
  mime_type: 'text/plain',
  openai_file_id: `oai-${name}`,
  created_at: '2026-07-14T00:00:00Z'
})

// An upload whose settlement each test controls, keyed by file name.
function deferredUpload(): {
  upload: (f: { name: string }) => Promise<FileChat>
  resolve: (name: string) => void
  reject: (name: string) => void
} {
  const resolvers = new Map<
    string,
    { resolve: (fc: FileChat) => void; reject: (e: unknown) => void }
  >()
  const upload = vi.fn(
    (f: { name: string }) =>
      new Promise<FileChat>((resolve, reject) => resolvers.set(f.name, { resolve, reject }))
  )
  return {
    upload: upload as unknown as (f: { name: string }) => Promise<FileChat>,
    resolve: (name) => resolvers.get(name)?.resolve(fileChat(name)),
    reject: (name) => resolvers.get(name)?.reject(new Error('boom'))
  }
}

// An upload that resolves immediately (for tests that don't care about timing).
const immediateUpload = async (f: { name: string }): Promise<FileChat> => fileChat(f.name)

beforeEach(() => clearAttachments())

describe('chatAttachments — cap', () => {
  it('rejects files beyond the 4-file cap and surfaces the rejection', () => {
    const first = addAttachments([pick('1'), pick('2'), pick('3'), pick('4')], {
      upload: immediateUpload
    })
    expect(first.accepted).toHaveLength(MAX_CHAT_ATTACHMENTS)
    expect(first.rejected).toEqual([])

    const fifth = addAttachments([pick('5')], { upload: immediateUpload })
    expect(fifth.accepted).toHaveLength(0)
    expect(fifth.rejected).toEqual([{ name: '5', reason: 'cap_exceeded' }])
    expect(getPendingAttachments()).toHaveLength(4)
  })

  it('rejects an over-cap or empty file with a reason', () => {
    const r = addAttachments([pick('big', true), pick('empty', false, true)], {
      upload: immediateUpload
    })
    expect(r.accepted).toEqual([])
    expect(r.rejected).toContainEqual({ name: 'big', reason: 'too_large' })
    expect(r.rejected).toContainEqual({ name: 'empty', reason: 'empty' })
    expect(getPendingAttachments()).toEqual([])
  })
})

describe('chatAttachments — upload lifecycle', () => {
  it('marks an attachment uploaded with its server id on success', async () => {
    const { upload, resolve } = deferredUpload()
    addAttachments([pick('a')], { upload })
    expect(getPendingAttachments()[0].status).toBe('uploading')
    expect(getUploadedFileIds()).toEqual([])

    resolve('a')
    await awaitUploadsSettled()

    const att = getPendingAttachments()[0]
    expect(att.status).toBe('uploaded')
    expect(att.serverId).toBe('srv-a')
    expect(getUploadedFileIds()).toEqual(['srv-a'])
  })

  it('one failing upload marks only that attachment failed; the others still upload', async () => {
    const { upload, resolve, reject } = deferredUpload()
    addAttachments([pick('ok'), pick('bad')], { upload })

    resolve('ok')
    reject('bad')
    await awaitUploadsSettled()

    const [ok, bad] = getPendingAttachments()
    expect(ok.status).toBe('uploaded')
    expect(ok.serverId).toBe('srv-ok')
    expect(bad.status).toBe('failed')
    expect(bad.serverId).toBeUndefined()
    // Only the uploaded one contributes a file id.
    expect(getUploadedFileIds()).toEqual(['srv-ok'])
  })
})

describe('chatAttachments — thumbnail capture', () => {
  it('captures the public thumbnail URL from the upload response (images)', async () => {
    const upload = async (f: { name: string }): Promise<FileChat> => ({
      ...fileChat(f.name),
      mime_type: 'image/png',
      thumbnail: 'https://cdn.omi/thumb.png'
    })
    addAttachments([pick('img')], { upload })
    await awaitUploadsSettled()
    expect(getPendingAttachments()[0].thumbnailUrl).toBe('https://cdn.omi/thumb.png')
  })

  it('leaves thumbnailUrl undefined when the response carries no thumbnail (documents)', async () => {
    addAttachments([pick('doc')], { upload: immediateUpload })
    await awaitUploadsSettled()
    expect(getPendingAttachments()[0].thumbnailUrl).toBeUndefined()
  })
})

describe('chatAttachments — await settling', () => {
  it('awaitUploadsSettled blocks until in-flight uploads finish', async () => {
    const { upload, resolve } = deferredUpload()
    addAttachments([pick('a')], { upload })

    let settled = false
    const wait = awaitUploadsSettled().then(() => {
      settled = true
    })
    await flush()
    expect(settled).toBe(false) // still uploading — must not resolve early

    resolve('a')
    await wait
    expect(settled).toBe(true)
    expect(getUploadedFileIds()).toEqual(['srv-a'])
  })
})

describe('chatAttachments — remove', () => {
  it('removeAttachment drops it from the list and from the uploaded file ids', async () => {
    addAttachments([pick('a')], { upload: immediateUpload })
    await awaitUploadsSettled()
    expect(getUploadedFileIds()).toEqual(['srv-a'])

    const id = getPendingAttachments()[0].id
    removeAttachment(id)
    expect(getPendingAttachments()).toEqual([])
    expect(getUploadedFileIds()).toEqual([])
  })

  it('a removed attachment whose upload later resolves does not reappear', async () => {
    const { upload, resolve } = deferredUpload()
    addAttachments([pick('a')], { upload })
    const id = getPendingAttachments()[0].id
    removeAttachment(id)

    resolve('a') // resolves after removal — patch must be a no-op
    await awaitUploadsSettled()
    expect(getPendingAttachments()).toEqual([])
  })
})

describe('chatAttachments — reactivity', () => {
  it('notifies subscribers on add and replays the current value on subscribe', async () => {
    const seen: number[] = []
    const unsub = onPendingAttachments((list) => seen.push(list.length))
    expect(seen).toEqual([0]) // immediate replay of the empty initial value

    addAttachments([pick('a')], { upload: immediateUpload })
    await awaitUploadsSettled()
    // add → 1 entry; uploaded patch → still 1 entry (new array emitted).
    expect(seen[seen.length - 1]).toBe(1)
    unsub()
  })
})
