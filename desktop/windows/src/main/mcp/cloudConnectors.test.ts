import { describe, it, expect, afterEach, vi } from 'vitest'
import {
  buildCloudConnectors,
  cloudConnectorClientId,
  connectedCloudConnectors
} from './cloudConnectors'

function rowValue(rows: { label: string; value: string; blank?: boolean }[], label: string) {
  return rows.find((r) => r.label === label)
}

describe('buildCloudConnectors (field correctness — Mac parity)', () => {
  it('Claude card: omi-claude-prod, blank secret, add-custom-connector URL', () => {
    const [claude] = buildCloudConnectors('https://api.omi.me')
    expect(claude.id).toBe('claude')
    expect(claude.connectorUrl).toBe(
      'https://claude.ai/customize/connectors?modal=add-custom-connector'
    )
    expect(rowValue(claude.rows, 'Name')?.value).toBe('Omi Memory')
    expect(rowValue(claude.rows, 'Server URL')?.value).toBe('https://api.omi.me/v1/mcp/sse')
    expect(rowValue(claude.rows, 'OAuth Client ID')?.value).toBe('omi-claude-prod')
    expect(rowValue(claude.rows, 'OAuth Client Secret')?.blank).toBe(true)
  })

  it('ChatGPT card: omi-chatgpt-prod, token_auth_method none, authorize/token URLs', () => {
    const chatgpt = buildCloudConnectors('https://api.omi.me')[1]
    expect(chatgpt.id).toBe('chatgpt')
    expect(chatgpt.connectorUrl).toBe('https://chatgpt.com/#settings/Connectors')
    expect(rowValue(chatgpt.rows, 'OAuth Client ID')?.value).toBe('omi-chatgpt-prod')
    expect(rowValue(chatgpt.rows, 'Client Secret')?.blank).toBe(true)
    expect(rowValue(chatgpt.rows, 'Token auth method')?.value).toBe('none')
    expect(rowValue(chatgpt.rows, 'Authorization URL')?.value).toBe('https://api.omi.me/authorize')
    expect(rowValue(chatgpt.rows, 'Token URL')?.value).toBe('https://api.omi.me/token')
  })

  it('non-prod base uses the dev ChatGPT client id', () => {
    expect(cloudConnectorClientId('chatgpt', 'https://dev.example.com')).toBe('omi-chatgpt-dev')
    expect(cloudConnectorClientId('chatgpt', 'https://api.omi.me')).toBe('omi-chatgpt-prod')
    expect(cloudConnectorClientId('claude', 'https://api.omi.me')).toBe('omi-claude-prod')
  })
})

describe('connectedCloudConnectors', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('returns the ids whose client_id appears in the grants list', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({ grants: [{ client_id: 'omi-claude-prod' }] }),
        text: async () => ''
      }))
    )
    const connected = await connectedCloudConnectors('https://api.omi.me', 'token')
    expect(connected.has('claude')).toBe(true)
    expect(connected.has('chatgpt')).toBe(false)
  })

  it('is empty when signed out (no token)', async () => {
    const connected = await connectedCloudConnectors('https://api.omi.me', null)
    expect(connected.size).toBe(0)
  })
})
