import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn() }))
vi.mock('./apiClient', () => ({ omiApi: api }))

import {
  MAX_VOCABULARY_TERMS,
  fetchVocabulary,
  normalizeVocabulary,
  parseVocabularyInput,
  saveVocabulary
} from './transcriptionVocabulary'

beforeEach(() => {
  api.get.mockReset()
  api.patch.mockReset()
})

describe('normalizeVocabulary', () => {
  it('trims, collapses spaces, drops empties, and de-duplicates case-insensitively', () => {
    expect(normalizeVocabulary(['  Omi ', 'omi', '', 'Open  AI', 'Callie', 'OMI'])).toEqual([
      'Omi',
      'Open AI',
      'Callie'
    ])
  })

  it('drops over-long terms and caps the list at the backend limit', () => {
    const many = Array.from({ length: 150 }, (_, i) => `term${i}`)
    expect(normalizeVocabulary(many)).toHaveLength(MAX_VOCABULARY_TERMS)
    expect(normalizeVocabulary(['x'.repeat(61), 'ok'])).toEqual(['ok'])
  })
})

describe('parseVocabularyInput', () => {
  it('splits a pasted comma list into terms', () => {
    expect(normalizeVocabulary(parseVocabularyInput('Omi, Callie,OpenAI,'))).toEqual([
      'Omi',
      'Callie',
      'OpenAI'
    ])
  })
})

describe('fetch/save', () => {
  it('reads the saved vocabulary and ignores malformed entries', async () => {
    api.get.mockResolvedValue({ data: { vocabulary: ['Omi', 3, 'Callie'] } })
    await expect(fetchVocabulary()).resolves.toEqual(['Omi', 'Callie'])
    expect(api.get).toHaveBeenCalledWith('/v1/users/transcription-preferences')
  })

  it('treats a missing vocabulary as empty', async () => {
    api.get.mockResolvedValue({ data: {} })
    await expect(fetchVocabulary()).resolves.toEqual([])
  })

  it('saves only the vocabulary field, normalized', async () => {
    api.patch.mockResolvedValue({})
    await saveVocabulary(['Omi', 'omi', ' Callie '])
    expect(api.patch).toHaveBeenCalledWith('/v1/users/transcription-preferences', {
      vocabulary: ['Omi', 'Callie']
    })
  })
})
