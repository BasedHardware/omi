import { it, expect } from 'vitest'
import {
  transcriptWordCount,
  isEmptyConversation,
  isMetaJunkMemory,
  junkMemoryIds,
  memoryJunkBreakdown,
  planRetention,
  type SweepConvo
} from './retentionRules'
import { SCREEN_TAG } from './screenTag'

const mem = (
  id: string,
  content: string,
  tags?: string[]
): {
  id: string
  uid: string
  content: string
  created_at: string
  updated_at: string
  tags?: string[]
} => ({ id, uid: '', content, created_at: '', updated_at: '', tags })

it('transcriptWordCount ignores speaker/section scaffolding', () => {
  expect(transcriptWordCount('Microphone:\nYou: hello there friend')).toBe(3)
  expect(transcriptWordCount('')).toBe(0)
  expect(transcriptWordCount('System audio:\n')).toBe(0)
})

it('isEmptyConversation is true under 5 real words', () => {
  expect(isEmptyConversation('You: hey ok bye')).toBe(true) // 3 words
  expect(isEmptyConversation('You: this is a real sentence now')).toBe(false) // 6 words
})

it('isMetaJunkMemory matches the store phrasing but NOT substantive "memories of/from"', () => {
  expect(isMetaJunkMemory('The user has 547 memories stored within the Omi application.')).toBe(
    true
  )
  expect(isMetaJunkMemory('The user has 12 memories saved.')).toBe(true)
  expect(isMetaJunkMemory('The user has 8 memories in Omi.')).toBe(true)
  expect(isMetaJunkMemory('The user has 3 cats.')).toBe(false)
  expect(isMetaJunkMemory('The user uses an experiment branch for tinkering.')).toBe(false)
  // Substantive personal memories — must NOT be flagged as junk.
  expect(isMetaJunkMemory('The user has 5 memories from childhood that shaped him.')).toBe(false)
  expect(isMetaJunkMemory('The user has 2 memories of the trip he wants to preserve.')).toBe(false)
  expect(isMetaJunkMemory('The user has 4 memories in his hometown he revisits.')).toBe(false)
})

it('junkMemoryIds unions app-index, meta-junk, and exact duplicates', () => {
  const mems = [
    mem('a', 'Uses Warp'), // app-index template
    mem('b', 'The user has 12 memories stored.'), // meta junk
    mem('c', 'The user is planning a trip to Japan.'), // keep
    mem('d', 'The user is planning a trip to Japan.'), // exact dup of c → drop
    mem('e', 'Used to work at Google.') // keep
  ]
  const ids = junkMemoryIds(mems).sort()
  expect(ids).toEqual(['a', 'b', 'd'])
})

it('planRetention selects only empty local recordings and junk memories', () => {
  const convos: SweepConvo[] = [
    { id: 'l1', source: 'local', kind: 'recording', text: 'You: hi bye' }, // empty → drop
    {
      id: 'l2',
      source: 'local',
      kind: 'recording',
      text: 'You: this is clearly a real conversation'
    }, // keep
    { id: 'l3', source: 'local', kind: 'chat', text: 'hi' }, // chat → never touch
    { id: 'c1', source: 'cloud', text: '' } // may be redacted; never delete
  ]
  const plan = planRetention(convos, [mem('a', 'Uses Warp')])
  expect(plan.localConvoIds).toEqual(['l1'])
  expect(plan.memoryIds).toEqual(['a'])
})

it('memoryJunkBreakdown categorizes junk by reason and sums to junkMemoryIds', () => {
  const mems = [
    mem('s1', 'Screen thing', [SCREEN_TAG]), // screen-synth
    mem('a1', 'Uses Warp'), // app-index
    mem('m1', 'The user has 9 memories stored.'), // meta
    mem('k1', 'The user likes hiking.'), // keep
    mem('k2', 'The user likes hiking.'), // duplicate of k1
    mem('keep', 'Used to work at Google.') // keep
  ]
  const b = memoryJunkBreakdown(mems)
  expect(b).toEqual({ total: 4, screenSynth: 1, appIndex: 1, meta: 1, duplicate: 1 })
  expect(b.total).toBe(junkMemoryIds(mems).length)
})

it('never plans deletion of cloud conversations with omitted or redacted transcripts', () => {
  const convos: SweepConvo[] = [
    { id: 'cShort', source: 'cloud', text: 'You: quick note here' },
    { id: 'cRedacted', source: 'cloud', text: '' },
    { id: 'cOmitted', source: 'cloud', text: '   ' },
    { id: 'lShort', source: 'local', kind: 'recording', text: 'You: quick note here' }
  ]
  const plan = planRetention(convos, [])
  expect(plan).toEqual({ localConvoIds: ['lShort'], memoryIds: [] })
})
