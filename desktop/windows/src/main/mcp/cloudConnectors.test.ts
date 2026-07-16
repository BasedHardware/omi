import { describe, it, expect } from 'vitest'
import { buildCloudConnectors } from './cloudConnectors'

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

  it('uses the dev ChatGPT client id on a non-prod base', () => {
    const chatgpt = buildCloudConnectors('https://dev.example.com')[1]
    expect(chatgpt.rows.find((r) => r.label === 'OAuth Client ID')?.value).toBe('omi-chatgpt-dev')
  })
})
