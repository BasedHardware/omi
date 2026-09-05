import { describe, expect, it } from 'vitest'
import {
  compact,
  parseWireTime,
  toScreenMap,
  toSpineConversation,
  toSpineMemory,
  toSpineTask
} from './spineSources'
import type { Conversation, MemoryDB } from '../omiApi.generated'
import type { ActionItemRecord, SpineScreenDay } from '../../../../shared/types'

const ISO = '2026-08-15T10:00:00Z'
const MS = Date.parse(ISO)

const conversation = (over: Partial<Conversation> = {}): Conversation =>
  ({
    id: 'c1',
    created_at: ISO,
    started_at: ISO,
    finished_at: '2026-08-15T11:00:00Z',
    structured: {
      title: 'Lease renewal',
      overview: 'We agreed',
      category: 'personal',
      emoji: '🏠'
    },
    ...over
  }) as Conversation

const memoryDb = (over: Partial<MemoryDB> = {}): MemoryDB =>
  ({ id: 'm1', content: 'Prefers oat milk', created_at: ISO, ...over }) as MemoryDB

const taskRecord = (over: Partial<ActionItemRecord> = {}): ActionItemRecord =>
  ({
    id: 7,
    description: 'Send the lease',
    completed: false,
    conversationId: null,
    createdAt: MS,
    source: 'conversation',
    sourceApp: null,
    ...over
  }) as ActionItemRecord

describe('parseWireTime', () => {
  it('reads an ISO string', () => {
    expect(parseWireTime(ISO)).toBe(MS)
  })

  it('returns null for anything unreadable', () => {
    for (const bad of ['', 'not a date', null, undefined]) {
      expect(parseWireTime(bad)).toBeNull()
    }
  })
})

describe('toSpineConversation', () => {
  it('maps the fields the stream renders', () => {
    expect(toSpineConversation(conversation())).toEqual({
      id: 'c1',
      title: 'Lease renewal',
      overview: 'We agreed',
      category: 'personal',
      emoji: '🏠',
      startedAt: MS,
      finishedAt: Date.parse('2026-08-15T11:00:00Z'),
      starred: false
    })
  })

  it('falls back to the creation time when there is no start', () => {
    expect(toSpineConversation(conversation({ started_at: null }))?.startedAt).toBe(MS)
  })

  it('keeps an unfinished conversation open at its start', () => {
    // Treating a null finish as zero would stop every frame captured during a
    // live conversation from attaching to it.
    const c = toSpineConversation(conversation({ finished_at: null }))
    expect(c?.finishedAt).toBe(c?.startedAt)
  })

  it('never lets the finish precede the start', () => {
    const c = toSpineConversation(
      conversation({ started_at: ISO, finished_at: '2026-08-15T09:00:00Z' })
    )
    // An inverted range would make the attachment window empty and silently
    // orphan every frame in it.
    expect(c?.finishedAt).toBe(c?.startedAt)
  })

  it('drops a conversation that cannot be placed in time', () => {
    // Showing it at epoch zero would claim the user had a conversation in 1970.
    expect(toSpineConversation(conversation({ started_at: null, created_at: '' }))).toBeNull()
  })

  it('supplies a default emoji rather than rendering a blank circle', () => {
    expect(toSpineConversation(conversation({ structured: {} }))?.emoji).toBe('💬')
  })
})

describe('toSpineMemory', () => {
  it('maps a memory and its conversation link', () => {
    expect(toSpineMemory(memoryDb({ conversation_id: 'c1' }))).toEqual({
      id: 'm1',
      text: 'Prefers oat milk',
      timestamp: MS,
      conversationId: 'c1'
    })
  })

  it('drops an untimed or empty memory', () => {
    expect(toSpineMemory(memoryDb({ created_at: '' }))).toBeNull()
    expect(toSpineMemory(memoryDb({ content: '   ' }))).toBeNull()
  })
})

describe('toSpineTask', () => {
  it('maps a task and prefers the app it came from as its label', () => {
    expect(toSpineTask(taskRecord({ sourceApp: 'Slack' }))).toMatchObject({
      id: '7',
      text: 'Send the lease',
      timestamp: MS,
      sourceLabel: 'Slack'
    })
  })

  it('falls back to the source when no app is recorded', () => {
    expect(toSpineTask(taskRecord())?.sourceLabel).toBe('conversation')
  })

  it('drops an untimed or empty task', () => {
    expect(toSpineTask(taskRecord({ createdAt: 0 }))).toBeNull()
    expect(toSpineTask(taskRecord({ description: '' }))).toBeNull()
  })
})

describe('toScreenMap', () => {
  const day = (over: Partial<SpineScreenDay> = {}): SpineScreenDay => ({
    dayId: 1_723_680_000_000,
    total: 12,
    hourCounts: new Array<number>(24).fill(0),
    sampled: [
      { id: 1, timestamp: MS, appName: 'Chrome', windowTitle: 'Docs', imagePath: 'C:/f/1.jpg' }
    ],
    ...over
  })

  it('keys days by their local midnight', () => {
    const map = toScreenMap([day()])
    expect(map[1_723_680_000_000]).toMatchObject({ total: 12 })
  })

  it('replaces a malformed histogram rather than rendering a short rail', () => {
    const map = toScreenMap([day({ hourCounts: [1, 2] })])
    expect(map[1_723_680_000_000].hourCounts.length).toBe(24)
  })
})

describe('compact', () => {
  it('drops the nulls the mappers produced', () => {
    expect(compact([1, null, 2, null])).toEqual([1, 2])
  })
})
