import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { GmailItem } from '../../../shared/types'

const { omiPost } = vi.hoisted(() => ({ omiPost: vi.fn() }))
vi.mock('./apiClient', () => ({
  omiApi: { post: omiPost }
}))

import { formatGmailItems, extractGmailMemories } from './gmailExtract'

const item = (over: Partial<GmailItem>): GmailItem => ({
  id: 'm1',
  subject: 'Order shipped',
  from: 'Shop <s@x.com>',
  snippet: 'Your order is on the way',
  internalDateMs: 0,
  ...over
})

beforeEach(() => {
  omiPost.mockReset()
})

describe('formatGmailItems', () => {
  it('renders sender, subject and snippet only — never a body', () => {
    expect(formatGmailItems([item({ subject: 'Flight to Bilbao' })])).toEqual([
      'From: Shop <s@x.com> | Subject: Flight to Bilbao | Your order is on the way'
    ])
  })
})

describe('extractGmailMemories', () => {
  it('sends existing memories to the backend and dedups the response case-insensitively', async () => {
    omiPost.mockResolvedValue({
      data: { memories: ['Has a dog', '  ', 'Lives in Bilbao'], tasks: [], profile: '' }
    })

    const memories = await extractGmailMemories([item({})], ['lives in bilbao'])

    expect(omiPost).toHaveBeenCalledWith(
      '/v1/connectors/synthesize',
      expect.objectContaining({ source: 'gmail', existing_memories: ['lives in bilbao'] }),
      expect.anything()
    )
    expect(memories).toEqual(['Has a dog'])
  })

  it('never calls the backend for an empty inbox page', async () => {
    expect(await extractGmailMemories([])).toEqual([])
    expect(omiPost).not.toHaveBeenCalled()
  })
})
