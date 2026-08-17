/**
 * The HTTP half of offline-audio sync: multipart upload, capture manifest, and
 * job polling. Kept separate from the engine so the wire format is testable on
 * its own, and so the engine never has to know about headers or encoding.
 *
 * Two details are contractual rather than incidental:
 *  - `X-Device-Id-Hash` is what binds the capture time to this install. Without
 *    it the server classifies every upload as untrusted backfill, which is the
 *    slow lane with a shorter recovery window.
 *  - The upload filename carries the capture time in its last underscore field,
 *    so the multipart part name must be the WAL file name verbatim.
 */

import type { UploadResponseLike } from './syncPolicy'
import type { WalUploadFile } from './syncEngine'

export interface WalHttpConfig {
  baseUrl: string
  /** Firebase ID token; the request is not attempted without one. */
  getToken: () => Promise<string | null>
  /** First eight hex chars of the install id the renderer uses. Null before
   *  any session has run, which is the only time it is unknown. */
  getDeviceIdHash: () => Promise<string | null>
  appVersion: string
  fetchImpl?: typeof fetch
}

const PLATFORM = 'windows'

/** Multipart boundary. Random enough that it cannot appear in audio bytes. */
function makeBoundary(): string {
  const random = Math.random().toString(16).slice(2)
  return `----omiWalBoundary${Date.now().toString(16)}${random}`
}

/**
 * Builds a multipart/form-data body for the audio files. Written by hand
 * because the payload is raw binary: FormData in the main process would need a
 * Blob per file and copy every buffer again.
 */
export function buildMultipartBody(
  files: WalUploadFile[],
  boundary: string
): { body: Uint8Array; contentType: string } {
  const encoder = new TextEncoder()
  const parts: Uint8Array[] = []
  for (const file of files) {
    parts.push(
      encoder.encode(
        `--${boundary}\r\n` +
          `Content-Disposition: form-data; name="files"; filename="${file.fileName}"\r\n` +
          `Content-Type: application/octet-stream\r\n\r\n`
      )
    )
    parts.push(file.bytes)
    parts.push(encoder.encode('\r\n'))
  }
  parts.push(encoder.encode(`--${boundary}--\r\n`))

  const total = parts.reduce((sum, p) => sum + p.byteLength, 0)
  const body = new Uint8Array(total)
  let offset = 0
  for (const part of parts) {
    body.set(part, offset)
    offset += part.byteLength
  }
  return { body, contentType: `multipart/form-data; boundary=${boundary}` }
}

export class WalHttpClient {
  private readonly fetchImpl: typeof fetch

  constructor(private readonly config: WalHttpConfig) {
    this.fetchImpl = config.fetchImpl ?? fetch
  }

  private async headers(): Promise<Record<string, string> | null> {
    const token = await this.config.getToken()
    if (token === null || token.length === 0) return null
    const deviceIdHash = await this.config.getDeviceIdHash()
    // Without the hash the backend cannot bind the capture time to this
    // install and classifies the upload as untrusted backfill: a shorter
    // recovery window and the slow lane. Waiting for it costs one pass; going
    // without it can cost the recording.
    if (deviceIdHash === null || deviceIdHash.length === 0) return null
    return {
      Authorization: `Bearer ${token}`,
      'X-App-Platform': PLATFORM,
      'X-Device-Id-Hash': deviceIdHash,
      'X-App-Version': this.config.appVersion
    }
  }

  async uploadFiles(args: {
    files: WalUploadFile[]
    conversationId: string | null
    manifest: string | null
  }): Promise<UploadResponseLike> {
    const headers = await this.headers()
    // No identity, no upload. Reported as an auth failure so the engine leaves
    // the recordings untouched rather than spending a retry.
    if (headers === null) return { status: 401 }

    const boundary = makeBoundary()
    const { body, contentType } = buildMultipartBody(args.files, boundary)
    const query =
      args.conversationId === null
        ? ''
        : `?conversation_id=${encodeURIComponent(args.conversationId)}`
    const requestHeaders: Record<string, string> = {
      ...headers,
      'Content-Type': contentType,
      'X-Request-ID': `wal-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`
    }
    if (args.manifest !== null) {
      requestHeaders['X-Omi-Sync-Capture-Manifest'] = args.manifest
    }

    const response = await this.fetchImpl(`${this.config.baseUrl}/v2/sync-local-files${query}`, {
      method: 'POST',
      headers: requestHeaders,
      body: body as unknown as BodyInit
    })
    return toUploadResponse(response)
  }

  async fetchJobStatus(jobId: string): Promise<{ status: number; body?: unknown }> {
    const headers = await this.headers()
    if (headers === null) return { status: 401 }
    const response = await this.fetchImpl(
      `${this.config.baseUrl}/v2/sync-local-files/${encodeURIComponent(jobId)}`,
      { method: 'GET', headers }
    )
    return { status: response.status, body: await readJson(response) }
  }

  /**
   * Asks the server to sign a claim that this install captured these files.
   * Returns null on any failure: the manifest only buys the trusted lane, so
   * losing it must never cost the upload.
   */
  async requestCaptureManifest(args: {
    files: Array<{ name: string; size: number }>
    conversationId: string | null
  }): Promise<string | null> {
    const headers = await this.headers()
    if (headers === null) return null
    try {
      const response = await this.fetchImpl(`${this.config.baseUrl}/v2/sync-capture-manifest`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          files: args.files,
          conversation_id: args.conversationId
        })
      })
      if (!response.ok) return null
      const body = (await readJson(response)) as { manifest?: unknown } | null
      const manifest = body?.manifest
      return typeof manifest === 'string' && manifest.length > 0 ? manifest : null
    } catch {
      return null
    }
  }
}

async function toUploadResponse(response: Response): Promise<UploadResponseLike> {
  return {
    status: response.status,
    body: await readJson(response),
    header: (name) => response.headers.get(name)
  }
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    // A body that is not JSON (a proxy error page) is not a reason to treat the
    // response as anything other than its status code.
    return null
  }
}
