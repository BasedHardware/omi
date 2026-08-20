import { describe, it, expect, vi } from 'vitest'
import { buildGmailPrompt, parseGmailMemories } from './gmailExtract'
import type { GmailItem } from '../../../shared/types'

vi.mock('./apiClient', () => ({
  desktopApi: {
    post: vi.fn()
  }
}))

const item = (over: Partial<GmailItem>): GmailItem => ({
  id: 'm1',
  subject: 'Order shipped',
  from: 'Shop <s@x.com>',
  snippet: 'Your order is on the way',
  internalDateMs: 0,
  ...over
})

describe('buildGmailPrompt', () => {
  it('includes the atomic-decomposition rule and the metadata-only framing', () => {
    const p = buildGmailPrompt([item({})], [])
    expect(p).toContain('atomic')
    expect(p).toContain('subject, sender, snippet only')
  })

  it('lists each email and any existing memories to avoid', () => {
    const p = buildGmailPrompt([item({ subject: 'Flight to Bilbao' })], ['Has a girlfriend'])
    expect(p).toContain('Flight to Bilbao')
    expect(p).toContain('Has a girlfriend')
    expect(p).toContain('EXISTING MEMORIES')
  })
})

describe('parseGmailMemories', () => {
  it('parses memories, drops blanks, and dedups against existing (case-insensitive)', () => {
    const json = JSON.stringify({ memories: ['Has a dog', '  ', 'Lives in Bilbao'] })
    expect(parseGmailMemories(json, ['lives in bilbao'])).toEqual(['Has a dog'])
  })

  it('tolerates fenced JSON and returns [] on garbage', () => {
    expect(parseGmailMemories('```json\n{"memories":[]}\n```', [])).toEqual([])
    expect(parseGmailMemories('not json at all', [])).toEqual([])
  })
})
