import { describe, it, expect, vi } from 'vitest'
import { WalHttpClient, buildMultipartBody } from './walHttp'

const decoder = new TextDecoder()

const client = (
  fetchImpl: typeof fetch,
  over: { token?: string | null; deviceIdHash?: string | null } = {}
): WalHttpClient =>
  new WalHttpClient({
    baseUrl: 'https://api.omi.me',
    getToken: async () => (over.token === undefined ? 'token-123' : over.token),
    getDeviceIdHash: async () => (over.deviceIdHash === undefined ? 'abcd1234' : over.deviceIdHash),
    appVersion: '1.0.33',
    fetchImpl
  })

const jsonResponse = (
  status: number,
  body: unknown,
  headers: Record<string, string> = {}
): Response =>
  ({
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
    headers: { get: (name: string) => headers[name.toLowerCase()] ?? null }
  }) as unknown as Response

describe('buildMultipartBody', () => {
  it('names each part with the file name the backend parses', () => {
    const { body, contentType } = buildMultipartBody(
      [
        { fileName: 'audio_mic_pcm16_16000_1_fs160_1723800000.bin', bytes: new Uint8Array([1, 2]) },
        { fileName: 'audio_mic_pcm16_16000_1_fs160_1723800060.bin', bytes: new Uint8Array([3]) }
      ],
      'BOUNDARY'
    )
    const text = decoder.decode(body)
    expect(contentType).toBe('multipart/form-data; boundary=BOUNDARY')
    // The capture time lives in the filename, so the part name must carry it
    // verbatim or the server cannot classify the recording.
    expect(text).toContain('name="files"; filename="audio_mic_pcm16_16000_1_fs160_1723800000.bin"')
    expect(text).toContain('name="files"; filename="audio_mic_pcm16_16000_1_fs160_1723800060.bin"')
    expect(text.endsWith('--BOUNDARY--\r\n')).toBe(true)
  })

  it('carries the audio bytes through untouched', () => {
    const bytes = new Uint8Array([0, 255, 128, 7])
    const { body } = buildMultipartBody([{ fileName: 'a_1.bin', bytes }], 'B')
    // Find the payload between the header terminator and the trailing CRLF.
    const haystack = Array.from(body)
    const needle = Array.from(bytes)
    let found = false
    for (let i = 0; i + needle.length <= haystack.length; i += 1) {
      if (needle.every((v, j) => haystack[i + j] === v)) {
        found = true
        break
      }
    }
    expect(found).toBe(true)
  })
})

describe('uploadFiles', () => {
  it('sends the identity headers that put the upload in the trusted lane', async () => {
    const calls: Array<{ url: string; init: RequestInit }> = []
    const fetchImpl = vi.fn(async (url: string, init: RequestInit) => {
      calls.push({ url, init })
      return jsonResponse(202, { job_id: 'job-1' })
    }) as unknown as typeof fetch

    const response = await client(fetchImpl).uploadFiles({
      files: [{ fileName: 'a_1723800000.bin', bytes: new Uint8Array([1]) }],
      conversationId: null,
      manifest: null
    })

    expect(response.status).toBe(202)
    const headers = calls[0].init.headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer token-123')
    expect(headers['X-App-Platform']).toBe('windows')
    // Without this the server treats the capture time as unbound and every
    // recovery lands in the slow backfill lane.
    expect(headers['X-Device-Id-Hash']).toBe('abcd1234')
    expect(headers['X-App-Version']).toBe('1.0.33')
    expect(headers['X-Request-ID']).toMatch(/^wal-/)
    expect(calls[0].url).toBe('https://api.omi.me/v2/sync-local-files')
  })

  it('attaches the conversation and the capture manifest when present', async () => {
    const calls: Array<{ url: string; init: RequestInit }> = []
    const fetchImpl = vi.fn(async (url: string, init: RequestInit) => {
      calls.push({ url, init })
      return jsonResponse(202, { job_id: 'j' })
    }) as unknown as typeof fetch

    await client(fetchImpl).uploadFiles({
      files: [{ fileName: 'a_1.bin', bytes: new Uint8Array([1]) }],
      conversationId: 'conv 1/2',
      manifest: 'signed-manifest'
    })
    expect(calls[0].url).toBe('https://api.omi.me/v2/sync-local-files?conversation_id=conv%201%2F2')
    expect((calls[0].init.headers as Record<string, string>)['X-Omi-Sync-Capture-Manifest']).toBe(
      'signed-manifest'
    )
  })

  it('reports a missing identity as unauthorized instead of uploading', async () => {
    const fetchImpl = vi.fn() as unknown as typeof fetch
    const response = await client(fetchImpl, { token: null }).uploadFiles({
      files: [{ fileName: 'a_1.bin', bytes: new Uint8Array([1]) }],
      conversationId: null,
      manifest: null
    })
    // The engine leaves the recording untouched for an auth failure rather than
    // spending one of its retries.
    expect(response.status).toBe(401)
    expect(fetchImpl).not.toHaveBeenCalled()
  })

  it('defers rather than uploading without the device provenance hash', async () => {
    const fetchImpl = vi.fn() as unknown as typeof fetch
    const response = await client(fetchImpl, { deviceIdHash: null }).uploadFiles({
      files: [{ fileName: 'a_1.bin', bytes: new Uint8Array([1]) }],
      conversationId: null,
      manifest: null
    })
    // Sending it unbound would put the recording in the untrusted backfill
    // lane, which has a shorter recovery window than waiting one pass costs.
    expect(response.status).toBe(401)
    expect(fetchImpl).not.toHaveBeenCalled()
  })

  it('surfaces the Retry-After header and the error code the server sends', async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(503, { code: 'backfill_capacity' }, { 'retry-after': '3600' })
    ) as unknown as typeof fetch
    const response = await client(fetchImpl).uploadFiles({
      files: [{ fileName: 'a_1.bin', bytes: new Uint8Array([1]) }],
      conversationId: null,
      manifest: null
    })
    expect(response.status).toBe(503)
    expect(response.header?.('Retry-After')).toBe('3600')
    expect((response.body as { code: string }).code).toBe('backfill_capacity')
  })

  it('a non-JSON body does not change what the status means', async () => {
    const fetchImpl = vi.fn(
      async () =>
        ({
          status: 502,
          ok: false,
          json: async () => {
            throw new Error('not json')
          },
          headers: { get: () => null }
        }) as unknown as Response
    ) as unknown as typeof fetch
    const response = await client(fetchImpl).uploadFiles({
      files: [{ fileName: 'a_1.bin', bytes: new Uint8Array([1]) }],
      conversationId: null,
      manifest: null
    })
    expect(response.status).toBe(502)
    expect(response.body).toBeNull()
  })
})

describe('fetchJobStatus', () => {
  it('polls the job endpoint with the identity headers', async () => {
    const calls: string[] = []
    const fetchImpl = vi.fn(async (url: string) => {
      calls.push(url)
      return jsonResponse(200, { job_id: 'j', status: 'completed' })
    }) as unknown as typeof fetch

    const result = await client(fetchImpl).fetchJobStatus('job/1')
    expect(calls[0]).toBe('https://api.omi.me/v2/sync-local-files/job%2F1')
    expect(result).toEqual({ status: 200, body: { job_id: 'j', status: 'completed' } })
  })
})

describe('requestCaptureManifest', () => {
  it('returns the signed manifest', async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(200, { manifest: 'signed' })
    ) as unknown as typeof fetch
    const manifest = await client(fetchImpl).requestCaptureManifest({
      files: [{ name: 'a_1.bin', size: 10 }],
      conversationId: null
    })
    expect(manifest).toBe('signed')
  })

  it('returns null on any failure rather than blocking the upload', async () => {
    // The manifest only buys the trusted lane; losing it must not cost the
    // upload, which is the thing that saves the audio.
    // A failing response whose body still looks manifest-shaped (a proxy error
    // page, a cached body) must not be trusted just because the field is there.
    const failing = vi.fn(async () =>
      jsonResponse(500, { manifest: 'not-a-real-manifest' })
    ) as unknown as typeof fetch
    expect(
      await client(failing).requestCaptureManifest({ files: [], conversationId: null })
    ).toBeNull()

    const throwing = vi.fn(async () => {
      throw new Error('offline')
    }) as unknown as typeof fetch
    expect(
      await client(throwing).requestCaptureManifest({ files: [], conversationId: null })
    ).toBeNull()

    const empty = vi.fn(async () => jsonResponse(200, { manifest: '' })) as unknown as typeof fetch
    expect(
      await client(empty).requestCaptureManifest({ files: [], conversationId: null })
    ).toBeNull()
  })
})
