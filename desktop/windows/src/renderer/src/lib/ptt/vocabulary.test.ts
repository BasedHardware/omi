import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  collectPttKeywords,
  pttKeywordsParam,
  startPttKeywordCollection,
  consumePttKeywords,
  __resetPttKeywordsForTests
} from './vocabulary'
import type { RewindFrame } from '../../../../shared/types'

type Bridge = {
  screenReadText?: () => Promise<string>
  rewindFrames?: (from: number, to: number) => Promise<RewindFrame[]>
}

function setBridge(omi: Bridge): void {
  ;(globalThis as Record<string, unknown>).window = { omi }
}

function frame(p: Partial<RewindFrame>): RewindFrame {
  return {
    ts: 0,
    app: '',
    windowTitle: '',
    processName: '',
    ocrText: '',
    imagePath: '',
    width: 0,
    height: 0,
    indexed: 1,
    ...p
  }
}

beforeEach(() => {
  setBridge({}) // no context methods by default
  __resetPttKeywordsForTests()
})

describe('collectPttKeywords', () => {
  it('dedups the same term arriving from several sources (case-insensitive)', async () => {
    setBridge({
      screenReadText: async () => 'Photoshop Illustrator',
      rewindFrames: async () => [
        frame({ app: 'Photoshop', windowTitle: 'Illustrator', ocrText: 'Photoshop' })
      ]
    })
    const terms = await collectPttKeywords(1000)
    const lower = terms.map((t) => t.toLowerCase())
    expect(new Set(lower).size).toBe(lower.length) // no case-insensitive duplicates
    expect(lower.filter((t) => t === 'photoshop')).toHaveLength(1)
    expect(lower).toContain('illustrator')
  })

  it('caps the collector at 100 terms', async () => {
    // 200 distinct 3-letter uppercase tokens (AAA, AAB, …) — all valid, none stop-words.
    const tok = (i: number): string =>
      String.fromCharCode(
        65 + (Math.floor(i / 676) % 26),
        65 + (Math.floor(i / 26) % 26),
        65 + (i % 26)
      )
    const words = Array.from({ length: 200 }, (_, i) => tok(i)).join(' ')
    setBridge({ screenReadText: async () => words, rewindFrames: async () => [] })
    const terms = await collectPttKeywords(1000)
    expect(terms.length).toBe(100)
  })

  it('returns [] when every source throws (resilience — never breaks the turn)', async () => {
    setBridge({
      screenReadText: async () => {
        throw new Error('ocr down')
      },
      rewindFrames: async () => {
        throw new Error('db down')
      }
    })
    expect(await collectPttKeywords(1000)).toEqual([])
  })

  it('returns [] when the context bridge has no capture methods', async () => {
    setBridge({})
    expect(await collectPttKeywords(1000)).toEqual([])
  })
})

describe('pttKeywordsParam', () => {
  it('always prepends the brand terms and dedups them against collected terms', () => {
    expect(pttKeywordsParam(['omi', 'Foo', 'Bar'])).toBe('Omi,OMI,Foo,Bar')
  })

  it('assembles a comma-separated param, dropping too-short/long and comma-bearing terms', () => {
    expect(pttKeywordsParam(['ok', 'a', 'x'.repeat(81), 'Foo, Bar', 'Baz'])).toBe('Omi,OMI,ok,Baz')
  })

  it('hard-caps the wire list at 40 terms (brand prepend included)', () => {
    const many = Array.from({ length: 100 }, (_, i) => `Term${i}`)
    const parts = pttKeywordsParam(many).split(',')
    expect(parts).toHaveLength(40)
    expect(parts.slice(0, 2)).toEqual(['Omi', 'OMI'])
    expect(parts[2]).toBe('Term0')
  })

  it('returns just the brand prepend for an empty collection', () => {
    expect(pttKeywordsParam([])).toBe('Omi,OMI')
  })
})

describe('hold-start collection cache (start/consume)', () => {
  it('consume returns the terms collected at hold-start (normal hold — resolved by key-up)', async () => {
    setBridge({ screenReadText: async () => 'Photoshop Illustrator' })
    startPttKeywordCollection(1000)
    const terms = (await consumePttKeywords()).map((t) => t.toLowerCase())
    expect(terms).toContain('photoshop')
    expect(terms).toContain('illustrator')
  })

  it('consume with nothing collected this turn returns [] (⇒ brand prepend only)', async () => {
    expect(await consumePttKeywords()).toEqual([])
  })

  it('is one-shot: a second consume without a fresh start returns [] (no stale reuse)', async () => {
    setBridge({ screenReadText: async () => 'Charlie' })
    startPttKeywordCollection(1000)
    expect((await consumePttKeywords()).map((t) => t.toLowerCase())).toContain('charlie')
    expect(await consumePttKeywords()).toEqual([]) // cache cleared by the first consume
  })

  it('a fresh start overwrites the prior turn — stale terms are never carried forward', async () => {
    setBridge({ screenReadText: async () => 'Alpha' })
    startPttKeywordCollection(1) // turn 1
    setBridge({ screenReadText: async () => 'Bravo' })
    startPttKeywordCollection(2) // turn 2 overwrites turn 1
    const terms = (await consumePttKeywords()).map((t) => t.toLowerCase())
    expect(terms).toContain('bravo')
    expect(terms).not.toContain('alpha')
  })

  it('short hold: consume degrades to [] when collection has not finished within the bound', async () => {
    vi.useFakeTimers()
    try {
      // OCR that never resolves within the consume window (a very short hold that
      // released before the bounded collection could complete).
      setBridge({ screenReadText: () => new Promise<string>(() => {}) })
      startPttKeywordCollection(1000)
      const pending = consumePttKeywords(300)
      await vi.advanceTimersByTimeAsync(300)
      expect(await pending).toEqual([])
    } finally {
      vi.useRealTimers()
    }
  })
})
