import { describe, it, expect } from 'vitest'
import {
  planRetrievalHop,
  retrieveForQuery,
  mergeRetrievedItems,
  partitionCitedRefs,
  validatedRetrievedRefs,
  type RetrievalSource
} from './retrieval'

const source = (over: Partial<RetrievalSource> = {}): RetrievalSource => ({
  kind: 'conversation',
  id: 'c1',
  title: 'Standup',
  preview: 'talked about the demo',
  createdAt: '2026-08-16T20:00:00Z',
  ...over
})

describe('planRetrievalHop', () => {
  it('admits only with the flag on, zero prior hops, and a 3-200 char flattened query', () => {
    expect(planRetrievalHop('demo recording', true, 0)).toBe('demo recording')
    expect(planRetrievalHop('a\nb   c', true, 0)).toBe('a b c')
    expect(planRetrievalHop('demo', false, 0)).toBeNull()
    expect(planRetrievalHop('demo', true, 1)).toBeNull()
    expect(planRetrievalHop(null, true, 0)).toBeNull()
    expect(planRetrievalHop('ab', true, 0)).toBeNull()
    expect(planRetrievalHop('x'.repeat(300), true, 0)?.length).toBe(200)
  })
})

describe('retrieveForQuery', () => {
  it('maps sources fail-closed and merges with chunks leading', async () => {
    const outcome = await retrieveForQuery('q', {
      conversations: async () => [
        source({ id: 'summary-1' }),
        source({ id: 'bad id with spaces' }),
        source({ id: 'x'.repeat(600) })
      ],
      conversationChunks: async () => [
        source({ id: 'chunk-1' }),
        source({ id: 'summary-1', preview: 'verbatim' })
      ],
      memories: async () => [
        source({ kind: 'memory', id: 'm1' }),
        source({ kind: 'conversation', id: 'wrong-kind' })
      ]
    })
    // Chunks lead; the chunk wins the summary-1 collision; malformed ids drop.
    expect(outcome.items.map((i) => i.ref)).toEqual([
      'conversation:chunk-1',
      'conversation:summary-1',
      'memory:m1'
    ])
    expect(outcome.items[1].preview).toBe('verbatim')
    expect(outcome.allowedRefs.has('conversation:chunk-1')).toBe(true)
  })

  it('a failing source yields [] without sinking the others', async () => {
    const outcome = await retrieveForQuery('q', {
      conversations: async () => {
        throw new Error('down')
      },
      conversationChunks: async () => [source({ id: 'chunk-1' })],
      memories: async () => [source({ kind: 'memory', id: 'm1' })]
    })
    expect(outcome.items.map((i) => i.ref)).toEqual(['conversation:chunk-1', 'memory:m1'])
  })

  it('caps combined conversations at 6 and the prompt list at 9', () => {
    const chunks = Array.from({ length: 5 }, (_, i) => ({
      ref: `conversation:chunk-${i}`,
      title: '',
      preview: 'p',
      createdAt: ''
    }))
    const summaries = Array.from({ length: 5 }, (_, i) => ({
      ref: `conversation:sum-${i}`,
      title: '',
      preview: 'p',
      createdAt: ''
    }))
    const memories = Array.from({ length: 5 }, (_, i) => ({
      ref: `memory:m-${i}`,
      title: '',
      preview: 'p',
      createdAt: ''
    }))
    const merged = mergeRetrievedItems(summaries, chunks, memories)
    expect(merged.filter((i) => i.ref.startsWith('conversation:')).length).toBe(6)
    expect(merged.length).toBe(9)
  })
})

describe('ref partition and allowlist validation', () => {
  it('splits namespaces and validates retrieved refs against the allowlist with dedup', () => {
    const { bucketRefs, retrievedRefs } = partitionCitedRefs([
      'entry:e1',
      'conversation:c1',
      'memory:m1',
      'plain-id'
    ])
    expect(bucketRefs).toEqual(['entry:e1', 'plain-id'])
    expect(retrievedRefs).toEqual(['conversation:c1', 'memory:m1'])

    const allowed = new Set(['conversation:c1'])
    expect(
      validatedRetrievedRefs(['conversation:c1', 'conversation:c1', 'memory:m1'], allowed)
    ).toEqual(['conversation:c1'])
    expect(validatedRetrievedRefs(['conversation:c1'], new Set())).toEqual([])
  })
})
