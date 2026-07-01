import { describe, expect, it } from 'vitest'
import {
  errorToObservabilityPayload,
  redactStringForObservability,
  sanitizeObservabilityValue
} from './observabilityRedaction'

describe('observability redaction', () => {
  it('redacts authorization headers, JWTs, and likely API keys in strings', () => {
    const jwt =
      'eyJhbGciOiJIUzI1NiJ9.eyJ1aWQiOiJ1c2VyXzEyMyIsImVtYWlsIjoidEBleGFtcGxlLmNvbSJ9.signaturevalue123'
    const text = [
      'Authorization: Bearer firebase-token-abcdef123456',
      `id token ${jwt}`,
      'openai sk-proj-abcdefghijklmnopqrstuvwxyz1234567890',
      'url https://api.example.test/path?api_key=secret-value&ok=1'
    ].join('\n')

    const redacted = redactStringForObservability(text)

    expect(redacted).not.toContain('firebase-token-abcdef123456')
    expect(redacted).not.toContain(jwt)
    expect(redacted).not.toContain('sk-proj-abcdefghijklmnopqrstuvwxyz1234567890')
    expect(redacted).not.toContain('secret-value')
    expect(redacted).toContain('Authorization: Bearer [Filtered]')
    expect(redacted).toContain('api_key=[Filtered]')
  })

  it('redacts secret and content fields in nested metadata', () => {
    const sanitized = sanitizeObservabilityValue({
      event: 'mcp_key.test_finished',
      status: 200,
      toolCount: 7,
      authorization: 'Bearer live_secret',
      hostedKey: 'mcp_hosted_secret',
      mcp: { key: 'mcp_nested_secret' },
      transcript: 'User said private text',
      ocrText: 'Screen shows private data',
      body: { token: 'nested_token', ok: true },
      messages: [{ role: 'user', content: 'private prompt' }],
      sql: 'SELECT * FROM local_conversations'
    }) as Record<string, unknown>

    expect(sanitized).toMatchObject({
      event: 'mcp_key.test_finished',
      status: 200,
      toolCount: 7,
      authorization: '[Filtered]',
      hostedKey: '[Filtered]',
      transcript: '[Filtered content]',
      ocrText: '[Filtered content]',
      body: '[Filtered content]',
      messages: '[Filtered content]',
      sql: '[Filtered content]'
    })
    expect(sanitized.mcp).toEqual({ key: '[Filtered]' })
    expect(JSON.stringify(sanitized)).not.toContain('private')
    expect(JSON.stringify(sanitized)).not.toContain('nested_token')
    expect(JSON.stringify(sanitized)).not.toContain('local_conversations')
  })

  it('redacts screenshot data URLs and long base64 payloads', () => {
    const image = `data:image/jpeg;base64,${'a'.repeat(240)}`
    const sanitized = sanitizeObservabilityValue({
      preview: image,
      screenshot: image,
      blob: 'b'.repeat(220)
    }) as Record<string, unknown>

    expect(sanitized.preview).toBe('data:image/[Filtered]')
    expect(sanitized.screenshot).toBe('[Filtered content]')
    expect(sanitized.blob).toBe('[Filtered]')
  })

  it('sanitizes Error payloads without keeping secret values', () => {
    const error = new Error(
      'request failed: Authorization: Bearer secret-token-1234567890 and responseText=private-body'
    )
    error.stack = `Error: ${error.message}\n    at test (file.ts:1:1)`

    const payload = errorToObservabilityPayload(error)
    const encoded = JSON.stringify(payload)

    expect(encoded).not.toContain('secret-token-1234567890')
    expect(encoded).not.toContain('private-body')
    expect(payload.message).toContain('Authorization: Bearer [Filtered]')
  })

  it('redacts multi-word inline content values', () => {
    const text =
      'request failed: response_text=hello world with private words, transcript="User said something private"'

    const redacted = redactStringForObservability(text)

    expect(redacted).not.toContain('hello world')
    expect(redacted).not.toContain('User said something private')
    expect(redacted).toContain('response_text=[Filtered content]')
    expect(redacted).toContain('transcript="[Filtered content]"')
  })

  it('guards cyclic Error causes', () => {
    const first = new Error('first')
    const second = new Error('second')
    ;(first as Error & { cause?: unknown }).cause = second
    ;(second as Error & { cause?: unknown }).cause = first

    const payload = errorToObservabilityPayload(first)
    const encoded = JSON.stringify(payload)

    expect(encoded).toContain('[Circular]')
    expect(payload.cause).toBeDefined()
  })

  it('serializes repeated Error references without labeling siblings circular', () => {
    const error = new Error('shared failure')

    const payload = sanitizeObservabilityValue({ primary: error, secondary: error }) as Record<
      string,
      Record<string, unknown>
    >

    expect(payload.primary.message).toBe('shared failure')
    expect(payload.secondary.message).toBe('shared failure')
  })
})
