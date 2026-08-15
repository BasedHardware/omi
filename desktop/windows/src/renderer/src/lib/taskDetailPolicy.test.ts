import { describe, it, expect } from 'vitest'
import type { ActionItemRecord } from '../../../shared/types'
import {
  availableActions,
  contextBlocks,
  detailFields,
  isPriorityEditable,
  sourceLinks,
  whyOmiAddedThis
} from './taskDetailPolicy'

const rec = (over: Partial<ActionItemRecord> = {}): ActionItemRecord =>
  ({
    id: 1,
    backendId: 'b-1',
    backendSynced: true,
    description: 'task',
    completed: false,
    deleted: false,
    deletedBy: null,
    source: null,
    conversationId: null,
    priority: null,
    category: null,
    tags: [],
    dueAt: null,
    screenshotId: null,
    confidence: null,
    sourceApp: null,
    windowTitle: null,
    contextSummary: null,
    currentActivity: null,
    metadataJson: null,
    createdAt: Date.UTC(2026, 7, 10, 15, 0),
    updatedAt: 1,
    ...over
  }) as ActionItemRecord

describe('whyOmiAddedThis', () => {
  it('matches the mac copy per source class', () => {
    expect(whyOmiAddedThis(null)).toBe('You added this task directly.')
    expect(whyOmiAddedThis('manual')).toBe('You added this task directly.')
    expect(whyOmiAddedThis('screenshot')).toBe('It matched context on this PC.')
    expect(whyOmiAddedThis('screen_capture')).toBe('It matched context on this PC.')
    expect(whyOmiAddedThis('conversation')).toBe('It came from a conversation you captured.')
    expect(whyOmiAddedThis('transcription:omi')).toBe('It came from a conversation you captured.')
    expect(whyOmiAddedThis('omi')).toBe('It came from an authorized Omi source.')
  })
})

describe('sourceLinks', () => {
  it('links the conversation when one exists', () => {
    expect(sourceLinks(rec({ conversationId: 'conv-1' }))).toEqual([
      {
        kind: 'conversation',
        id: 'conv-1',
        title: 'Conversation',
        subtitle: 'Open conversation'
      }
    ])
  })

  it('links Rewind for screenshot-captured tasks and skips blank ids', () => {
    const links = sourceLinks(rec({ conversationId: '  ', screenshotId: 42 }))
    expect(links).toEqual([{ kind: 'rewind', title: 'Screen context', subtitle: 'Open Rewind' }])
  })

  it('returns both when both origins exist, conversation first', () => {
    const links = sourceLinks(rec({ conversationId: 'c', screenshotId: 1 }))
    expect(links.map((l) => l.kind)).toEqual(['conversation', 'rewind'])
  })

  it('returns empty for a plain manual task', () => {
    expect(sourceLinks(rec())).toEqual([])
  })
})

describe('detailFields', () => {
  it('always includes Status and omits absent fields entirely', () => {
    const fields = detailFields(rec())
    expect(fields[0]).toEqual({ label: 'Status', value: 'Active' })
    const labels = fields.map((f) => f.label)
    expect(labels).not.toContain('Priority')
    expect(labels).not.toContain('Tags')
    expect(labels).not.toContain('Due')
    expect(labels).not.toContain('Confidence')
  })

  it('renders the populated field set in mac order', () => {
    const fields = detailFields(
      rec({
        completed: true,
        priority: 'high',
        category: 'work',
        tags: ['a', 'b'],
        source: 'conversation',
        sourceApp: 'Slack',
        windowTitle: '#general',
        dueAt: Date.UTC(2026, 7, 20, 12),
        confidence: 0.876
      })
    )
    expect(fields.map((f) => f.label)).toEqual([
      'Status',
      'Priority',
      'Category',
      'Tags',
      'Source',
      'Source app',
      'Window',
      'Created',
      'Due',
      'Confidence'
    ])
    expect(fields[0].value).toBe('Completed')
    expect(fields[1].value).toBe('High')
    expect(fields[2].value).toBe('Work')
    expect(fields[3].value).toBe('a, b')
    expect(fields[9].value).toBe('88%')
  })
})

describe('actions and priority gating', () => {
  it('offers toggle, edit, delete always and investigate only with chat', () => {
    expect(availableActions(rec(), { hasChat: false })).toEqual([
      'toggleCompletion',
      'edit',
      'delete'
    ])
    expect(availableActions(rec(), { hasChat: true })).toEqual([
      'toggleCompletion',
      'edit',
      'investigate',
      'delete'
    ])
  })

  it('priority is editable only while the task is active', () => {
    expect(isPriorityEditable(rec())).toBe(true)
    expect(isPriorityEditable(rec({ completed: true }))).toBe(false)
  })
})

describe('contextBlocks', () => {
  it('collects summary and activity when present', () => {
    expect(contextBlocks(rec())).toEqual([])
    expect(
      contextBlocks(rec({ contextSummary: 'was chatting', currentActivity: 'in Slack' }))
    ).toEqual([
      { label: 'Summary', text: 'was chatting' },
      { label: 'Activity', text: 'in Slack' }
    ])
  })
})
