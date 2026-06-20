import { describe, it, expect } from 'vitest'
import {
  worksWithChat,
  chatMessagesUrl,
  normalizeAppResults,
  type CatalogApp
} from './chatApps'

const app = (over: Partial<CatalogApp>): CatalogApp => ({ id: 'a', ...over })

describe('worksWithChat', () => {
  it('is true when capabilities include "chat"', () => {
    expect(worksWithChat(app({ capabilities: ['chat'] }))).toBe(true)
  })

  it('is true when capabilities include "persona"', () => {
    expect(worksWithChat(app({ capabilities: ['memories', 'persona'] }))).toBe(true)
  })

  it('is false for non-chat capabilities', () => {
    expect(worksWithChat(app({ capabilities: ['memories', 'external_integration'] }))).toBe(false)
  })

  it('is false when capabilities are missing', () => {
    expect(worksWithChat(app({}))).toBe(false)
  })
})

describe('chatMessagesUrl', () => {
  const base = 'https://api.omi.me'

  it('returns the bare messages url when no app is selected', () => {
    expect(chatMessagesUrl(base, undefined)).toBe('https://api.omi.me/v2/messages')
  })

  it('appends app_id as a query param when an app is selected', () => {
    expect(chatMessagesUrl(base, 'app-123')).toBe('https://api.omi.me/v2/messages?app_id=app-123')
  })

  it('url-encodes the app id', () => {
    expect(chatMessagesUrl(base, 'a b/c')).toBe('https://api.omi.me/v2/messages?app_id=a%20b%2Fc')
  })
})

describe('normalizeAppResults', () => {
  it('keeps only entries with non-empty content', () => {
    expect(
      normalizeAppResults([
        { app_id: 'x', content: 'hello' },
        { app_id: 'y', content: '' },
        { app_id: 'z', content: '   ' }
      ])
    ).toEqual([{ app_id: 'x', content: 'hello' }])
  })

  it('returns [] for non-array / missing input', () => {
    expect(normalizeAppResults(undefined)).toEqual([])
    expect(normalizeAppResults(null)).toEqual([])
    expect(normalizeAppResults('nope' as unknown)).toEqual([])
  })

  it('tolerates a missing app_id', () => {
    expect(normalizeAppResults([{ content: 'orphan' }])).toEqual([
      { app_id: undefined, content: 'orphan' }
    ])
  })
})
