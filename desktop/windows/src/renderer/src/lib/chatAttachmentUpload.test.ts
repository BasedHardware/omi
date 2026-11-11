import { describe, it, expect, vi } from 'vitest'
import { uploadChatFile } from './chatAttachmentUpload'

// firebase auth is only reached when no getToken dep is injected; every test
// injects one, so the real module never runs. Mock it anyway so the import is inert.
vi.mock('./firebase', () => ({ auth: { currentUser: null } }))

const okResponse = (body: unknown): Response =>
  ({ ok: true, status: 200, json: async () => body }) as unknown as Response

const file = { name: 'notes.txt', mimeType: 'text/plain', bytes: new Uint8Array([1, 2, 3]) }

describe('uploadChatFile', () => {
  it('POSTs a `files` multipart field with the auth + platform headers and returns the FileChat', async () => {
    let capturedUrl = ''
    let capturedInit: RequestInit | undefined
    const fetchImpl = vi.fn(async (url: unknown, init?: RequestInit) => {
      capturedUrl = String(url)
      capturedInit = init
      return okResponse([
        { id: 'srv-file-1', name: 'notes.txt', mime_type: 'text/plain', openai_file_id: 'oai-9' }
      ])
    }) as unknown as typeof fetch

    const fc = await uploadChatFile(file, { fetchImpl, getToken: async () => 'tok-123' })

    // The server id (FileChat.id) is what goes into /v2/messages file_ids.
    expect(fc.id).toBe('srv-file-1')
    expect(capturedUrl).toMatch(/\/v2\/files$/)
    expect(capturedInit?.method).toBe('POST')

    const headers = capturedInit?.headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer tok-123')
    expect(headers['X-App-Platform']).toBe('windows')
    // Content-Type must NOT be set — the browser supplies the multipart boundary.
    expect(headers['Content-Type']).toBeUndefined()

    const body = capturedInit?.body as FormData
    expect(body).toBeInstanceOf(FormData)
    // Exactly one part, under the field name `files`.
    expect(body.getAll('files')).toHaveLength(1)
    const part = body.get('files') as File
    expect(part).toBeInstanceOf(Blob)
    expect(part.name).toBe('notes.txt')
  })

  it('throws on a non-OK response so the caller can mark that attachment failed', async () => {
    const fetchImpl = vi.fn(
      async () => ({ ok: false, status: 500 }) as unknown as Response
    ) as unknown as typeof fetch
    await expect(uploadChatFile(file, { fetchImpl, getToken: async () => 't' })).rejects.toThrow(
      'HTTP 500'
    )
  })

  it('throws when the response carries no file id', async () => {
    const fetchImpl = vi.fn(async () => okResponse([])) as unknown as typeof fetch
    await expect(uploadChatFile(file, { fetchImpl, getToken: async () => 't' })).rejects.toThrow(
      /no file id/
    )
  })
})
