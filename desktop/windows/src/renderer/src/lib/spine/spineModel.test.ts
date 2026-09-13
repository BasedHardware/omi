// Composition rules for the Activity spine.
//
// Timestamps are built with the LOCAL Date constructor so day bucketing is
// deterministic in any timezone the suite runs in - a UTC literal would land on
// a different local day depending on the runner's offset, which is the exact
// class of bug the model buckets locally to avoid.
import { describe, expect, it } from 'vitest'
import {
  MOMENTS_PER_STRIP,
  attachMoments,
  compareRows,
  clusterMoments,
  composeSpine,
  countRows,
  filterSpine,
  formatDayTitle,
  formatHourLabel,
  ownerIdOf,
  reseatAttachments,
  startOfLocalDay,
  uniqueById,
  type SpineConversation,
  type SpineDayScreen,
  type SpineInput,
  type SpineMemory,
  type SpineMoment,
  type SpineRow,
  type SpineTask
} from './spineModel'

const at = (day: number, hour: number, minute = 0): number =>
  new Date(2026, 7, day, hour, minute, 0, 0).getTime()

const NOW = at(15, 18)
const DAY_15 = startOfLocalDay(at(15, 12))
const DAY_14 = startOfLocalDay(at(14, 12))

const conversation = (over: Partial<SpineConversation> = {}): SpineConversation => ({
  id: 'c1',
  title: 'Lease renewal',
  overview: 'We agreed to renew',
  category: 'personal',
  emoji: '🏠',
  startedAt: at(15, 10),
  finishedAt: at(15, 11),
  starred: false,
  ...over
})

const memory = (over: Partial<SpineMemory> = {}): SpineMemory => ({
  id: 'm1',
  text: 'Prefers oat milk',
  timestamp: at(15, 10, 30),
  conversationId: null,
  ...over
})

const task = (over: Partial<SpineTask> = {}): SpineTask => ({
  id: 't1',
  text: 'Send the lease',
  timestamp: at(15, 10, 45),
  conversationId: null,
  completed: false,
  sourceLabel: 'Slack',
  ...over
})

const moment = (over: Partial<SpineMoment> = {}): SpineMoment => ({
  id: 1,
  timestamp: at(15, 10, 15),
  appName: 'Chrome',
  windowTitle: 'Docs',
  imagePath: 'C:/f/1.jpg',
  ...over
})

const screenDay = (moments: SpineMoment[], total = moments.length): SpineDayScreen => ({
  total,
  hourCounts: new Array<number>(24).fill(0),
  sampled: moments
})

const input = (over: Partial<SpineInput> = {}): SpineInput => ({
  conversations: [],
  memories: [],
  tasks: [],
  screen: {},
  ...over
})

const rowIds = (days: ReturnType<typeof composeSpine>): string[] =>
  days.flatMap((d) => d.rows.map((r) => r.id))

describe('uniqueById', () => {
  it('keeps the first sighting and the original order', () => {
    // Both upstream stores page by offset against a server-resorted list, so
    // overlapping pages are normal rather than exceptional.
    const out = uniqueById([{ id: 'a' }, { id: 'b' }, { id: 'a' }, { id: 'c' }])
    expect(out.map((x) => x.id)).toEqual(['a', 'b', 'c'])
  })
})

describe('composeSpine day bucketing', () => {
  it('orders days newest first', () => {
    const days = composeSpine(
      input({
        conversations: [
          conversation({ id: 'old', startedAt: at(14, 9), finishedAt: at(14, 10) }),
          conversation({ id: 'new', startedAt: at(15, 9), finishedAt: at(15, 10) })
        ]
      }),
      NOW
    )
    expect(days.map((d) => d.id)).toEqual([DAY_15, DAY_14])
  })

  it('files an attached memory under its conversation day, not its own', () => {
    // A conversation that runs past midnight can produce a memory stamped the
    // next day; it belongs with the conversation that produced it.
    const days = composeSpine(
      input({
        conversations: [conversation({ startedAt: at(14, 23, 30), finishedAt: at(15, 0, 30) })],
        memories: [memory({ timestamp: at(15, 0, 15), conversationId: 'c1' })]
      }),
      NOW
    )
    expect(days.map((d) => d.id)).toEqual([DAY_14])
    expect(days[0].rows.map((r) => r.id)).toContain('conv-mem:c1')
  })

  it('collapses a conversation that arrived on two overlapping pages', () => {
    // Both upstream stores page by offset against a server-resorted list, so the
    // same record legitimately arrives twice; rendering it twice would look like
    // the user had the same conversation two times.
    const days = composeSpine(input({ conversations: [conversation(), conversation()] }), NOW)
    expect(rowIds(days)).toEqual(['conv:c1'])
  })

  it('titles days Today, Yesterday, then by name', () => {
    expect(formatDayTitle(DAY_15, NOW)).toBe('Today')
    expect(formatDayTitle(DAY_14, NOW)).toBe('Yesterday')
    expect(formatDayTitle(startOfLocalDay(at(10, 12)), NOW)).toMatch(/August/)
  })
})

describe('composeSpine attachment', () => {
  it('attaches a memory and a task to their conversation', () => {
    const days = composeSpine(
      input({
        conversations: [conversation()],
        memories: [memory({ conversationId: 'c1' })],
        tasks: [task({ conversationId: 'c1' })]
      }),
      NOW
    )
    expect(rowIds(days)).toEqual(['conv:c1', 'conv-mem:c1', 'conv-task:c1', 'map:' + DAY_15])
    const conv = days[0].rows[0]
    expect(conv.content).toMatchObject({ type: 'conversation', memoryCount: 1, taskCount: 1 })
  })

  it('keeps a memory whose conversation is not loaded as its own row', () => {
    // Dropping it would silently hide the user's data behind a paging boundary.
    const days = composeSpine(input({ memories: [memory({ conversationId: 'not-loaded' })] }), NOW)
    expect(rowIds(days)).toEqual(['mem:m1', 'map:' + DAY_15])
  })

  it('batches attached memories into one row but gives each loose one its own', () => {
    const days = composeSpine(
      input({
        conversations: [conversation()],
        memories: [
          memory({ id: 'a', conversationId: 'c1' }),
          memory({ id: 'b', conversationId: 'c1' }),
          memory({ id: 'c', timestamp: at(15, 14) }),
          memory({ id: 'd', timestamp: at(15, 15) })
        ]
      }),
      NOW
    )
    const ids = rowIds(days)
    expect(ids.filter((i) => i.startsWith('conv-mem'))).toEqual(['conv-mem:c1'])
    expect(ids.filter((i) => i.startsWith('mem:'))).toEqual(['mem:d', 'mem:c'])
  })

  it('sorts attached memories newest first inside their row', () => {
    const days = composeSpine(
      input({
        conversations: [conversation()],
        memories: [
          memory({ id: 'early', timestamp: at(15, 10, 10), conversationId: 'c1' }),
          memory({ id: 'late', timestamp: at(15, 10, 50), conversationId: 'c1' })
        ]
      }),
      NOW
    )
    const row = days[0].rows.find((r) => r.id === 'conv-mem:c1')
    expect(row?.content.type === 'memories' && row.content.memories.map((m) => m.id)).toEqual([
      'late',
      'early'
    ])
  })
})

describe('attachMoments (the two-pointer merge)', () => {
  it('attaches a frame captured inside a conversation', () => {
    const c = conversation()
    const m = moment({ timestamp: at(15, 10, 30) })
    const { momentsByConversation, looseMoments } = attachMoments([c], [m])
    expect(momentsByConversation.get('c1')?.length).toBe(1)
    expect(looseMoments).toEqual([])
  })

  it('leaves a frame outside every conversation loose', () => {
    const { momentsByConversation, looseMoments } = attachMoments(
      [conversation()],
      [moment({ timestamp: at(15, 15) })]
    )
    expect(momentsByConversation.size).toBe(0)
    expect(looseMoments.length).toBe(1)
  })

  it('a frame newer than every conversation does not orphan the ones behind it', () => {
    // The regression macOS pins by name. If the cursor advanced on finishedAt,
    // this one future frame would consume the whole list and every conversation
    // after it would lose its frames.
    const newer = conversation({ id: 'newer', startedAt: at(15, 14), finishedAt: at(15, 15) })
    const older = conversation({ id: 'older', startedAt: at(15, 9), finishedAt: at(15, 10) })
    const { momentsByConversation, looseMoments } = attachMoments(
      [newer, older],
      [
        moment({ id: 1, timestamp: at(15, 17) }), // after everything
        moment({ id: 2, timestamp: at(15, 9, 30) }) // inside `older`
      ]
    )
    expect(looseMoments.map((m) => m.id)).toEqual([1])
    expect(momentsByConversation.get('older')?.map((m) => m.id)).toEqual([2])
  })

  it('attaches at both boundaries of a conversation', () => {
    const c = conversation()
    const { looseMoments } = attachMoments(
      [c],
      [moment({ id: 1, timestamp: c.startedAt }), moment({ id: 2, timestamp: c.finishedAt })]
    )
    expect(looseMoments).toEqual([])
  })
})

describe('clusterMoments', () => {
  it('splits only on a gap strictly greater than 45 minutes', () => {
    const runs = clusterMoments([
      moment({ id: 1, timestamp: at(15, 9, 0) }),
      moment({ id: 2, timestamp: at(15, 9, 45) }), // exactly 45m after 1: same run
      moment({ id: 3, timestamp: at(15, 10, 31) }) // 46m after 2: new run
    ])
    expect(runs.map((r) => r.map((m) => m.id))).toEqual([[3], [2, 1]])
  })

  it('keeps runs and their contents newest first', () => {
    const runs = clusterMoments([
      moment({ id: 1, timestamp: at(15, 9) }),
      moment({ id: 2, timestamp: at(15, 9, 10) })
    ])
    expect(runs).toEqual([[expect.objectContaining({ id: 2 }), expect.objectContaining({ id: 1 })]])
  })
})

describe('composeSpine screen rows', () => {
  it('caps a strip at eight frames but reports the whole cluster', () => {
    const moments = Array.from({ length: 20 }, (_v, i) =>
      moment({ id: i, timestamp: at(15, 14, i) })
    )
    const days = composeSpine(input({ screen: { [DAY_15]: screenDay(moments) } }), NOW)
    const row = days[0].rows.find((r) => r.content.type === 'moments')
    expect(row?.content.type === 'moments' && row.content.shown.length).toBe(MOMENTS_PER_STRIP)
    // A strip that reported 8 would claim the other 12 do not exist.
    expect(row?.content.type === 'moments' && row.content.total).toBe(20)
  })

  it('reports a null moment count for a day whose screen was never read', () => {
    const days = composeSpine(
      input({ conversations: [conversation()], screen: {}, loadedScreenDays: new Set() }),
      NOW
    )
    // null is "not read yet"; 0 is "read, and there was nothing". Collapsing
    // them makes an unread day claim the user captured nothing.
    expect(days[0].momentCount).toBeNull()
  })

  it('reports zero for a day that was read and had nothing', () => {
    const days = composeSpine(
      input({
        conversations: [conversation()],
        screen: { [DAY_15]: screenDay([], 0) },
        loadedScreenDays: new Set([DAY_15])
      }),
      NOW
    )
    expect(days[0].momentCount).toBe(0)
  })

  it('carries the exact per-day total, not the sample size', () => {
    const days = composeSpine(input({ screen: { [DAY_15]: screenDay([moment()], 4213) } }), NOW)
    expect(days[0].momentCount).toBe(4213)
  })
})

describe('composeSpine ordering', () => {
  it('orders rows by anchor, newest first', () => {
    const days = composeSpine(
      input({
        memories: [
          memory({ id: 'early', timestamp: at(15, 9) }),
          memory({ id: 'late', timestamp: at(15, 17) })
        ]
      }),
      NOW
    )
    expect(rowIds(days).slice(0, 2)).toEqual(['mem:late', 'mem:early'])
  })

  it('puts a conversation above anything else sharing its anchor', () => {
    const days = composeSpine(
      input({
        conversations: [conversation()],
        memories: [memory({ id: 'tie', timestamp: at(15, 10) })]
      }),
      NOW
    )
    expect(rowIds(days).slice(0, 2)).toEqual(['conv:c1', 'mem:tie'])
  })

  it('re-seats an attachment under its owner even when the anchors interleave', () => {
    // The attached memory is older than a later standalone one, so pure anchor
    // ordering would put an unrelated row between the conversation and its own
    // memory.
    const days = composeSpine(
      input({
        conversations: [conversation()],
        memories: [
          memory({ id: 'attached', timestamp: at(15, 10, 30), conversationId: 'c1' }),
          memory({ id: 'later', timestamp: at(15, 16) })
        ]
      }),
      NOW
    )
    expect(rowIds(days).slice(0, 3)).toEqual(['mem:later', 'conv:c1', 'conv-mem:c1'])
  })
})

describe('compareRows', () => {
  const row = (over: Partial<SpineRow>): SpineRow => ({
    id: 'r',
    anchor: 0,
    kind: 'memories',
    isAttached: false,
    content: { type: 'memories', memories: [memory()] },
    searchText: '',
    ...over
  })

  it('orders newest first', () => {
    expect(compareRows(row({ anchor: 2 }), row({ anchor: 1 }))).toBeLessThan(0)
    expect(compareRows(row({ anchor: 1 }), row({ anchor: 2 }))).toBeGreaterThan(0)
  })

  it('puts a conversation first at an identical anchor, whichever side it is on', () => {
    // Tested directly rather than through composeSpine: rows are emitted
    // conversation-first and Array.prototype.sort is stable, so the current emit
    // order already produces this and a composed test could not tell the rule
    // from the accident.
    const conv = row({ anchor: 5, kind: 'conversations' })
    const mem = row({ anchor: 5, kind: 'memories' })
    expect(compareRows(conv, mem)).toBeLessThan(0)
    expect(compareRows(mem, conv)).toBeGreaterThan(0)
  })

  it('leaves two non-conversation rows at the same anchor alone', () => {
    expect(compareRows(row({ anchor: 5, kind: 'tasks' }), row({ anchor: 5, kind: 'screen' }))).toBe(
      0
    )
  })
})

describe('reseatAttachments', () => {
  const row = (id: string, attached: boolean, content: SpineRow['content']): SpineRow => ({
    id,
    anchor: 0,
    kind: 'memories',
    isAttached: attached,
    content,
    searchText: ''
  })

  it('keeps an attachment whose owner is missing rather than dropping it', () => {
    const orphan = row('conv-mem:gone', true, { type: 'memories', memories: [memory()] })
    expect(reseatAttachments([orphan]).map((r) => r.id)).toEqual(['conv-mem:gone'])
  })

  it('parses the owner id off the row id', () => {
    expect(ownerIdOf('conv-mem:abc:123')).toBe('abc:123')
    expect(ownerIdOf('nocolon')).toBe('')
  })
})

describe('composeSpine brain map card', () => {
  it('appends it last on a day that has memories', () => {
    const days = composeSpine(input({ memories: [memory()] }), NOW)
    const last = days[0].rows[days[0].rows.length - 1]
    expect(last.id).toBe(`map:${DAY_15}`)
    expect(last.content).toEqual({ type: 'brainMap', memoryCount: 1 })
  })

  it('is absent on a day with no memories', () => {
    const days = composeSpine(input({ conversations: [conversation()] }), NOW)
    expect(rowIds(days).some((i) => i.startsWith('map:'))).toBe(false)
  })

  it('counts as a memories row so soloing Conversations drops a memories-only day', () => {
    const days = composeSpine(input({ memories: [memory()] }), NOW)
    // Otherwise the day would survive the filter carrying nothing but an orphan
    // map card.
    expect(filterSpine(days, 'conversations', '')).toEqual([])
    expect(filterSpine(days, 'memories', '').length).toBe(1)
  })
})

describe('filterSpine', () => {
  const days = (): ReturnType<typeof composeSpine> =>
    composeSpine(
      input({
        conversations: [conversation()],
        memories: [memory({ id: 'loose', text: 'Prefers oat milk', timestamp: at(15, 16) })],
        tasks: [task({ id: 'loose-task', timestamp: at(15, 17) })]
      }),
      NOW
    )

  it('returns everything unchanged with no kind and no query', () => {
    const all = days()
    expect(filterSpine(all, null, '')).toBe(all)
  })

  it('keeps only the chosen kind and drops days left empty', () => {
    const out = filterSpine(days(), 'tasks', '')
    expect(out.length).toBe(1)
    expect(out[0].rows.map((r) => r.id)).toEqual(['task:loose-task'])
  })

  it('matches the query case-insensitively against the row text', () => {
    expect(filterSpine(days(), null, 'OAT MILK').flatMap((d) => d.rows).length).toBe(1)
    // Both the conversation title and the task text contain "lease", and the
    // task is the newer row.
    expect(filterSpine(days(), null, 'lease').flatMap((d) => d.rows.map((r) => r.id))).toEqual([
      'task:loose-task',
      'conv:c1'
    ])
  })

  it('drops every day when nothing matches', () => {
    expect(filterSpine(days(), null, 'zzz')).toEqual([])
  })

  it('counts rows across days without regard to folding', () => {
    expect(countRows(days())).toBe(countRows(days()))
    expect(countRows(filterSpine(days(), 'conversations', ''))).toBe(1)
  })
})

describe('formatHourLabel', () => {
  it('reads as a clock, not a number', () => {
    expect([0, 6, 9, 12, 18, 23].map(formatHourLabel)).toEqual([
      '12 AM',
      '6 AM',
      '9 AM',
      '12 PM',
      '6 PM',
      '11 PM'
    ])
  })
})
